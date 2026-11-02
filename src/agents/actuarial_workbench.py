"""Domängateway för aktuariellt arbete. Katalogen väljs av agenten, aldrig en ny UI-knapp.

Läsningar använder agentens verkliga roll. Beräkningar går till en avgränsad
systemarbetare med befintliga serverrättigheter och fasta tjänstekontrakt.
Arbetaren tar inte SQL, kod, filer, URL:er, identiteter eller valfria operationer.
Alla leveranser lagras i samma databas och binds till dialog och körning.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from agents.gateways.common import GatewayError
from agents.gateways.drafts import _check_content
from models import ActuarialAnalysis, ActuarialDataset, ActuarialTurn
from reporting.analysis_chart import render_analysis_chart
from services import Actor, OperationContext, default_registry
from services import valuation_bases as vb
from services.operations.actuarial_analysis import (
    ANALYSES,
    ROW_MODELS,
    DatasetInput,
    JsonResult,
)

READS = ("get_company_metrics", "get_portfolio_snapshot", "get_premium_flows", "get_product_parameters",
         "list_valuation_bases", "get_valuation_basis", "list_valuation_runs", "get_valuation_run")
TITLES = {"valuation": "Provvärdering av beståndet", "scenario": "Värderingsscenario",
          "cashflows": "Framtida kassaflöden", "experience": "Utfall mot antagande",
          "fit_mortality": "Prövning av dödlighetsmodell", "mortality_curve": "Dödlighet och överlevnad",
          "compare_valuations": "Jämförelse av värderingar",
          "get_company_metrics": "Bolagsmått", "get_portfolio_snapshot": "Beståndsunderlag",
          "get_premium_flows": "Premieflöden", "get_product_parameters": "Produktparametrar",
          "list_valuation_bases": "Antaganderegister", "get_valuation_basis": "Aktuariell grund",
          "list_valuation_runs": "Värderingsregister", "get_valuation_run": "Värderingsunderlag"}
FIELD_LABELS = {"age": "Ålder", "year": "År", "death_probability": "Årlig dödsrisk", "survival": "Kvar i livet",
                "label": "Underlag", "fta_sek": "FTA, kr", "capital_sek": "Pensionskapital, kr",
                "expenses_sek": "Kostnader, kr", "surplus_sek": "Villkorad återbäring, kr",
                "deficit_sek": "Underskott, kr", "guarantee_sek": "Garanterad pension, kr",
                "present_value_sek": "Nuvärde, kr", "observed": "Observerat", "expected": "Förväntat",
                "ae_ratio": "Utfall/förväntan", "observed_rate": "Observerad andel", "expected_rate": "Förväntad andel",
                "lower_95": "Undre gräns 95 %", "upper_95": "Övre gräns 95 %", "improvement": "Årlig förbättring",
                "intensity_factor": "Intensitetsfaktor", "training_deviance": "Avvikelse, skattning",
                "validation_deviance": "Avvikelse, validering", "validation_expected": "Förväntat i validering",
                "state": "Tillstånd", "actual_sek": "Utfall, kr", "expected_sek": "Förväntat, kr",
                "difference_sek": "Skillnad, kr", "event": "Händelse", "suppressed": "Dolt"}


def display_value(key, value):
    if value is None:
        return "Dolt/saknas"
    if isinstance(value, bool):
        return "Ja" if value else "Nej"
    if isinstance(value, (float, int)):
        if key in {"survival", "death_probability", "improvement", "observed_rate", "expected_rate"}:
            return f"{100*value:.3f}".replace(".", ",")+" %"
        if key.endswith("_sek"):
            return f"{value:,.2f}".replace(",", " ").replace(".", ",")
        return f"{value:.5g}".replace(".", ",")
    return str(value).replace("|", "/").replace("\n", " ")[:150]


class WorkbenchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["catalog", "read", "analyze", "chart", "report", "recall", "delivery", "propose_basis"]
    name: str = Field(max_length=100, description="Operations-/analysnamn från katalogen; tomt vid catalog/recall")
    arguments_json: str = Field(max_length=24000, description="JSON-objekt som följer katalogens indatakontrakt; {} för catalog/recall")


class ChartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: str
    title: str = Field(min_length=1, max_length=160)
    x: str
    y: str
    kind: str = "line"
    unit: str = Field(default="", max_length=80)
    lower: str | None = None
    upper: str | None = None


class ReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    conclusion: str = Field(min_length=1, max_length=6000)
    analysis_ids: list[str] = Field(min_length=1, max_length=8)
    chart_ids: list[str] = Field(default_factory=list, max_length=8)


class BasisProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=10, max_length=2000)
    analysis_ids: list[str] = Field(min_length=1, max_length=8)
    proposal_json: str = Field(max_length=20000, description="JSON enligt propose_valuation_basis i katalogen")


class Workbench:
    def __init__(self, trusted, agent_service, conversation_id):
        self.trusted, self.agent_service, self.conversation_id = trusted, agent_service, conversation_id
        self.session_factory = trusted._session_factory

    def _load(self, ident):
        with self.session_factory() as session:
            row = session.get(ActuarialAnalysis, ident)
            if row is None or row.conversation_id != self.conversation_id:
                raise ValueError("Analysreferensen hör inte till denna dialog")
            if vb.checksum(row.content) != row.checksum:
                raise ValueError("Analysens kontrollsumma stämmer inte")
            return {"id": row.id, "kind": row.kind, "title": row.title, "checksum": row.checksum, "content": row.content}

    def _save(self, run_id, kind, title, content):
        ident, checksum = uuid4().hex, vb.checksum(content)
        with self.session_factory() as session:
            self._active(session, run_id)
            session.add(ActuarialAnalysis(id=ident, conversation_id=self.conversation_id, run_id=run_id,
                                         kind=kind, title=title[:200], content=content, checksum=checksum))
        return {"id": ident, "kind": kind, "title": title[:200], "checksum": checksum, "content": content}

    def _active(self, session, run_id):
        turn = session.scalar(select(ActuarialTurn).where(ActuarialTurn.run_id == run_id,
                              ActuarialTurn.conversation_id == self.conversation_id).with_for_update())
        if turn is None or turn.status != "running":
            raise ValueError("Uppdraget är inte aktivt; inga fler verktyg eller leveranser får köras")

    def _catalog(self):
        allowed_reads = self._allowed_reads()
        with self.session_factory() as session:
            datasets = []
            for d in session.scalars(select(ActuarialDataset).order_by(ActuarialDataset.created_at.desc()).limit(100)):
                valid = vb.checksum(d.content) == d.checksum
                datasets.append({"id": d.id, "kind": d.kind, "title": d.title, "checksum": d.checksum,
                                 "checksum_ok": valid,
                                 "source_ref": d.content.get("source_ref") if valid else None,
                                 "synthetic": d.content.get("synthetic") if valid else None})
        return {"reads": [{"name": name, "description": default_registry.get(name).description,
                           "input_schema": default_registry.get(name).input_model.model_json_schema()} for name in sorted(allowed_reads)],
                "analyses": [{"name": name, "description": desc, "input_schema": model.model_json_schema()}
                             for name, (model, desc) in ANALYSES.items()],
                "chart_schema": ChartInput.model_json_schema(), "report_schema": ReportInput.model_json_schema(),
                "basis_proposal_schema": BasisProposalInput.model_json_schema(),
                "basis_content_schema": default_registry.get("propose_valuation_basis").input_model.model_json_schema(),
                "datasets": datasets, "dataset_import_schema": DatasetInput.model_json_schema(),
                "observation_schemas": {k: v.model_json_schema() for k, v in ROW_MODELS.items()},
                "data_needs": ["Dödlighet: avstämd exponering i personår och dödsfall per år/ålder.",
                               "Kostnader: utfall, exponering och källbunden förväntansgrund.",
                               "Beteende: valberättigade, händelser och referenssannolikhet.",
                               "Externa referensdata importeras och versionsmärks; inget nätinnehåll hämtas av modellen."],
                "limitations": ["Ingen tillgångssida för ALM eller full solvensmotor.",
                                 "Förändringsjämförelsen är en delanalys; ej separerade rörelser redovisas.",
                                 "Inga individuppgifter, fria databasfrågor eller fri kodexekvering.",
                                 "Fastställande av värdering och antagande av grund kräver mänskligt beslut."]}

    def _allowed_reads(self):
        from agents.ecosystem import Ecosystem
        from agents.profile import compile_profile
        from agents.skills import SkillRegistry

        eco = Ecosystem.load()
        profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), self.agent_service,
                                  agent_id="actuary_agent")
        return {d.skill for d in profile.visible()} & set(READS)

    def invoke(self, team, run_id, data: WorkbenchInput) -> JsonResult:
        if team != "aktuarie":
            raise GatewayError("security", "Arbetsbänken tillhör aktuarieteamet", security=True)
        with self.session_factory() as session:
            self._active(session, run_id)
        args = json.loads(data.arguments_json)
        if not isinstance(args, dict):
            raise ValueError("Argumenten ska vara ett JSON-objekt")  # noqa: TRY004 -- indatafel i gatewaykontraktet
        if data.action in {"catalog", "recall"} and (args or data.name):
            raise ValueError("Katalog och historik kräver tomt namn och {}")
        if data.action == "catalog":
            payload = self._catalog()
        elif data.action == "recall":
            with self.session_factory() as session:
                refs = session.scalars(select(ActuarialAnalysis.id).where(
                    ActuarialAnalysis.conversation_id == self.conversation_id)
                    .order_by(ActuarialAnalysis.created_at.desc()).limit(30)).all()
            payload = {"deliveries": [{k: v for k, v in self._load(ref).items() if k != "content"} for ref in refs]}
        elif data.action == "read":
            if data.name not in self._allowed_reads():
                raise ValueError("Läsoperationen finns inte i aktuariens katalog")
            result = self.agent_service.execute(data.name, OperationContext(
                actor=Actor.agent("actuary_agent", team="aktuarie"), run_id=run_id), args)
            payload = self._save(run_id, "data", TITLES[data.name], result.output.model_dump(mode="json"))
        elif data.action == "analyze":
            if data.name not in ANALYSES:
                raise ValueError("Analysen finns inte i aktuariens katalog")
            # Betrott systemsteg som B-042:s värderingsmotor. Inget rollbyte i agentanslutningen.
            result = self.trusted.execute("perform_actuarial_analysis", OperationContext(
                actor=Actor.system("actuarial-worker"), run_id=run_id),
                {"analysis": data.name, "parameters_json": data.arguments_json})
            payload = self._save(run_id, "analysis", TITLES[data.name], result.output.payload)
        elif data.action == "chart":
            q = ChartInput.model_validate(args)
            source = self._load(q.analysis_id)
            _check_content(q.title+q.unit)
            svg = render_analysis_chart(source["content"].get("rows", []), title=q.title, x=q.x, y=q.y,
                kind=q.kind, unit=q.unit, source=source["id"]+" / "+source["checksum"], lower=q.lower, upper=q.upper)
            payload = self._save(run_id, "chart", q.title, {"svg": svg, "source_id": source["id"],
                "source_checksum": source["checksum"], "chart": q.model_dump()})
            payload["content"] = {k: v for k, v in payload["content"].items() if k != "svg"}
        elif data.action == "report":
            q = ReportInput.model_validate(args)
            _check_content(q.title+q.conclusion)
            sources = [self._load(ref) for ref in q.analysis_ids]
            charts = [self._load(ref) for ref in q.chart_ids]
            if any(c["kind"] != "chart" or c["content"]["source_id"] not in q.analysis_ids for c in charts):
                raise ValueError("Rapportdiagrammen ska bygga på rapportens analysunderlag")
            if any(s["kind"] not in {"analysis", "data"} for s in sources):
                raise ValueError("Rapporten ska referera data eller analyser")
            # Samma talkontroll som övriga bolagsrapporter; alla tabeller binds till källan.
            from agents.results import _unsupported, _values_and_dates

            values, dates = _values_and_dates([s["content"] for s in sources])
            if _unsupported([q.conclusion], values, dates):
                raise ValueError("Rapportslutsatsen innehåller tal som saknas i underlaget")
            lines = ["# "+q.title, "", q.conclusion]
            for chart in charts:
                lines += ["", f"![{chart['title']}](chart:{chart['id']})"]
            lines += ["", "## Underlag och begränsningar"]
            for s in sources:
                lines += ["", "## "+s["title"], "", "Källa: "+s["id"]+" · "+s["checksum"]]
                rows = s["content"].get("rows", [])
                if rows:
                    keys = list(rows[0])[:5]
                    lines += ["", "| "+" | ".join(FIELD_LABELS.get(k, k) for k in keys)+" |", "| "+" | ".join("---" for _ in keys)+" |"]
                    selected = rows if len(rows) <= 15 else [rows[round(i*(len(rows)-1)/14)] for i in range(15)]
                    for row in selected:
                        lines.append("| "+" | ".join(display_value(k, row.get(k)) for k in keys)+" |")
                    if len(rows) > 15:
                        lines += ["", "Tabellen visar ett jämnt fördelat urval av rader. Fullständigt analysunderlag finns via källreferensen."]
                lines += ["", *["- "+item for item in s["content"].get("limitations", [])]]
            lines += ["", "Utkast för mänsklig granskning. Ingen grund eller värdering har fastställts."]
            payload = self._save(run_id, "report", q.title, {"markdown": "\n".join(lines),
                "sources": [{k: s[k] for k in ("id", "checksum")} for s in sources],
                "charts": [{k: c[k] for k in ("id", "checksum")} for c in charts],
                "created_at": datetime.now(UTC).isoformat(), "review_status": "not_reviewed"})
        elif data.action == "propose_basis":
            q = BasisProposalInput.model_validate(args)
            _check_content(q.reason)
            sources = [self._load(ref) for ref in q.analysis_ids]
            if not any(s["kind"] == "analysis" for s in sources):
                raise ValueError("Grundförslaget kräver ett beräknat analysunderlag")
            proposal = json.loads(q.proposal_json)
            proposal["source_refs"] = "; ".join(s["id"]+":"+s["checksum"][:12] for s in sources)[:300]
            digest = vb.checksum({"proposal": proposal, "reason": q.reason})
            with self.session_factory() as session:
                self._active(session, run_id)
                previous = session.scalars(select(ActuarialAnalysis).where(
                    ActuarialAnalysis.conversation_id == self.conversation_id,
                    ActuarialAnalysis.kind == "proposal", ActuarialAnalysis.run_id == run_id)).all()
                found = next((r for r in previous if r.content.get("request_checksum") == digest), None)
                if found:
                    return JsonResult(payload=self._load(found.id))
                ident = uuid4().hex
                content = {"request_checksum": digest, "state": "reconciliation_required", "executed": False,
                           "note": "Beställning registrerad. Utfallet behöver stämmas av innan nytt försök.",
                           "sources": [{"id": s["id"], "checksum": s["checksum"]} for s in sources]}
                session.add(ActuarialAnalysis(id=ident, conversation_id=self.conversation_id,
                    run_id=run_id, kind="proposal", title="Förslag till aktuariell grund", content=content,
                    checksum=vb.checksum(content)))
            # Beställningsjournalen består om processen dör efter könscommit. Ingen automatisk repris.
            with self.session_factory() as session:
                self._active(session, run_id)
                result = self.trusted.execute("propose_valuation_basis", OperationContext(
                    actor=Actor.agent("actuary_agent", team="aktuarie"), reason=q.reason, run_id=run_id), proposal)
                row = session.get(ActuarialAnalysis, ident)
                row.content = {**content, "pending_approval": result.approval_id, "state": "pending_approval",
                               "note": "Väntar i godkännandekön. Grunden är inte registrerad eller antagen."}
                row.checksum = vb.checksum(row.content)
            payload = self._load(ident)
        elif data.action == "delivery":
            if set(args) != {"id"}:
                raise ValueError("Leveransläsning kräver ett id")
            payload = self._load(args["id"])
            if payload["kind"] == "chart":
                payload["content"] = {k: v for k, v in payload["content"].items() if k != "svg"}
        else:
            raise ValueError("Okänd handling; välj catalog, read, analyze, chart, report, recall eller delivery")
        return JsonResult(payload=payload)
