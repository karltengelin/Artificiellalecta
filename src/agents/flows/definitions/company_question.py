"""Flödet `company_question` – första fråge- och rapportkedjan (OC-3a, B-041).

    definition = company_question_definition(renderer, DeliveryStore())

Fyra steg (`fragekedja_beslutsforslag.md` §5):

1. `answer` – aktuarien läser ledningsaggregatet och svarar enligt `CompanyAnswer` (val F).
2. `render` – betrodd kod bygger rapportens Markdown ur svaret och verktygets resultat,
   renderar A4-PDF och sparar leveransen med kontrollsummor (val G). Talen i rapporten kommer
   ur `get_company_metrics` via samma översättning som centralen (`company_observations`).
3. `review` – operatören granskar rapporten; grinden binder svaret och leveransen.
4. `deliver` – leveransen kontrolleras mot kontrollsummorna och markeras godkänd.

Definitionen byggs med en renderare (`Renderer`, underlagets §10.1) och en leveranslagring,
eftersom systemstegen bara får flödets kontext och det betrodda tjänstelagret av motorn.
Måtten och deras gränser följer datakontraktet P2-FRAGA-001 (projekt 2).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agents.assignments import COMPANY_QUESTION_FIXED_LIMITATIONS, request_for_company_question
from agents.deliveries import DeliveryError, DeliveryStore
from agents.flows.definition import AgentStep, FlowContext, FlowDefinition, GateStep, SystemOutcome, SystemStep
from agents.trace import RunTrace, read_run_trace
from management.metrics import DEFINITIONS, READ_FAILED_NOTE, MetricObservation, company_observations
from reporting.template import TOKENS, ReportMetadata
from services import ServiceLayer

FLOW_TYPE = "company_question"
CONTRACT_ID = "P2-FRAGA-001"
CONTRACT_VERSION = "1.0"
TEAM = "aktuarie"
#: Rapportmallens Markdown-struktur och designversion (06_design/rapportmall.md)
TEMPLATE_REF = f"A4 rapportmall, Digital klarhet v{TOKENS['version']}"

#: Renderaren: rapportens Markdown och metadata till PDF (`reporting.render_report`, underlagets §10.1)
Renderer = Callable[[str, ReportMetadata], bytes]

STATUS_TEXT = {
    "answered": "Besvarad",
    "partial": "Delvis besvarad",
    "unavailable": "Kan inte besvaras med underlaget",
    "needs_clarification": "Frågan behöver förtydligas",
}
AVAILABILITY_TEXT = {"available": "tillgängligt", "suppressed": "dolt", "missing": "saknas"}
QUALITY_TEXT = {"verified": "kontrollerat", "provisional": "preliminärt", "failed": "underkänt", "unknown": "okänt"}
NOT_READ_NOTE = "Inte läst – frågan kunde inte besvaras med underlaget."
CONTRACT_LIMITATIONS = COMPANY_QUESTION_FIXED_LIMITATIONS
TOOL_STATUS_TEXT = {"done": "klar", "error": "fel", "denied": "nekad", "pending_approval": "väntar på godkännande",
                    "not_executed": "inte utförd", "unknown": "utfall saknas i journalen"}


class CompanyQuestion(BaseModel):
    """Beställningen (OC-0 §6.2). Miljö, dataset och körbild binds av betrodd kod, inte av formuläret."""

    model_config = ConfigDict(extra="forbid")

    question_type: Literal["portfolio_overview"] = "portfolio_overview"
    month: date
    note: str = Field(default="", max_length=500)
    environment_id: str = Field(min_length=1, max_length=100)
    dataset_ref: str = Field(min_length=1, max_length=200)
    policy_ref: str = Field(min_length=1, max_length=200)
    supersedes: str | None = Field(default=None, pattern=r"^FLOW-\d{6}$")  # ett avslaget uppdrag

    @field_validator("month")
    @classmethod
    def first_of_month(cls, value: date) -> date:
        if value.day != 1:
            raise ValueError("Välj en hel kalendermånad")
        return value


def month_end(month: date) -> date:
    """Periodens exklusiva slut: första dagen i nästa månad."""
    return date(month.year + (month.month == 12), month.month % 12 + 1, 1)


def closed_months(today: date, count: int = 11) -> list[date]:
    """De avslutade månader som kan väljas: de elva före innevarande månad, senaste först (kontraktet §3)."""
    index = today.year * 12 + today.month - 2
    return [date((index - i) // 12, (index - i) % 12 + 1, 1) for i in range(count)]


def _sek(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " SEK"


def _text(value: str) -> str:
    """Modellens text som löptext: inga rubriker, ingen HTML."""
    return " ".join(value.replace("<", "&lt;").replace(">", "&gt;").split()).lstrip("#").strip()


def _value(obs: MetricObservation) -> str:
    if obs.value is None:
        return f"Visas inte – {obs.note}"
    if obs.metric_id == "premium_paid_recorded_sek":
        return _sek(Decimal(str(obs.value)))
    return f"{obs.value} {DEFINITIONS[obs.metric_id].unit}"


def _time(obs: MetricObservation) -> str:
    if obs.as_of_date is not None:
        return f"läsdag {obs.as_of_date.isoformat()}"
    return f"{obs.period_from.isoformat()} till {obs.period_to.isoformat()} (slutet ingår inte)"


def _usd(value: float | None) -> str:
    return "okänd" if value is None else f"{value:.4f}".replace(".", ",") + " USD"


def _tool(tool) -> str:
    detail = ", ".join(x for x in (tool.kind and f"typ {tool.kind}", tool.level and f"nivå {tool.level}") if x)
    name = f"`{tool.skill}`" + (f" (operation `{tool.operation}`)" if tool.operation and tool.operation != tool.skill else "")
    return f"{name}{f', {detail}' if detail else ''}: {TOOL_STATUS_TEXT.get(tool.status, tool.status)}"


def _trace_lines(run: dict[str, Any], trace: RunTrace | None) -> list[str]:
    """Hur svaret togs fram enligt körjournalen; utan journal sägs det, inget fylls i."""
    lines = [f"- Körning `{run.get('run_id', '–')}`, team `{TEAM}`, kostnad {_usd(run.get('cost_usd'))}"]
    if trace is None:
        return lines + ["- Körjournalen finns inte i den här miljön – modell och verktyg kan inte visas"]
    lines += [
        f"- Agent `{trace.agent or '–'}`, modellroll `{trace.model_role or '–'}`, "
        f"modell {', '.join(f'`{m}`' for m in trace.models) or 'okänd'}"
        + (f" (reserv efter {', '.join(f'`{m}`' for m in trace.fallback_from)})" if trace.fallback_from else ""),
        f"- Modellsteg {trace.steps if trace.steps is not None else 'okänt'}, verktygsanrop {len(trace.tools)}"
        + (f", körpolicy `{trace.policy_id}`" if trace.policy_id else ""),
    ]
    lines += [f"- Verktyg {_tool(t)}" for t in trace.tools] or ["- Inga verktyg användes"]
    if not trace.complete:
        lines.append("- Körjournalen är ofullständig – avstäm körningen innan rapporten godtas")
    return lines


def report_markdown(
    question: CompanyQuestion, *, flow_id: str, answer: dict[str, Any] | None, run: dict[str, Any],
    observations: list[MetricObservation], read_at: datetime | None, trace: RunTrace | None = None,
) -> str:
    """Rapportens Markdown med fast struktur: svaret för läsaren först, underlag och spårbarhet sist.

    Värdena kommer ur observationerna, aldrig ur modellens text.
    """
    period = question.month.strftime("%Y-%m")
    lines = [
        f"# Beståndsöversikt {period}",
        "",
        f"Uppdrag {flow_id} · Aktuarieteamet",
        "",
        "## Svar",
        "",
    ]
    if answer is None:
        lines += ["**Status:** Inget godkänt svar", "", "Aktuarien lämnade inget svar som kunde godtas."]
    else:
        lines += [f"**Status:** {STATUS_TEXT[answer['status']]}", "", _text(answer["conclusion"])]
    lines += ["", "## Värden", "", "| Mått | Värde | Tillgänglighet | Kvalitet | Tid |", "|---|---|---|---|---|"]
    for obs in observations:
        lines.append(
            f"| {DEFINITIONS[obs.metric_id].name} | {_value(obs)} | {AVAILABILITY_TEXT[obs.availability]} | "
            f"{QUALITY_TEXT[obs.quality]} | {_time(obs)} |"
        )
    fixed = set(CONTRACT_LIMITATIONS)
    lines += ["", "## Begränsningar", ""]
    lines += [f"- {t}" for t in CONTRACT_LIMITATIONS]
    lines += [f"- {_text(t)}" for t in (answer or {}).get("limitations", []) if _text(t) not in fixed]
    for title, key in (("Antaganden", "assumptions"), ("Nästa steg", "next_steps")):
        items = (answer or {}).get(key, [])
        if items:
            lines += ["", f"## {title}", ""] + [f"- {_text(t)}" for t in items]
    lines += ["", "## Definitioner", ""]
    for obs in observations:
        d = DEFINITIONS[obs.metric_id]
        lines += [
            f"**{d.name}** (`{d.metric_id}`, version {d.definition_version}). {d.definition} "
            f"Population: {d.population} Källa: {d.source}. Kontroller: {d.controls}",
            "",
        ]
    lines += [
        "## Datakälla och kontroller",
        "",
        f"- Miljö: `{question.environment_id}`, dataset `{question.dataset_ref}` (en etikett, inte en låst databasversion)",
        f"- Läsväg: `get_company_metrics`, läst {read_at.isoformat() if read_at else 'inte'}",
        f"- Källbevis: {', '.join(sorted({r for o in observations for r in o.evidence_refs})) or 'inget – måtten lästes inte'}",
        f"- Observationer: {', '.join(o.observation_id[:12] for o in observations)}",
        f"- Vald månad {period} är avslutad; båda måtten kommer från samma läsning; småcellsgräns 10 personer",
        "- Inte kontrollerat: bankavstämning, fullständig premieinläsning och historiskt bestånd",
        "",
        "## Så togs rapporten fram",
        "",
        f"- Uppdrag `{flow_id}`, kontrakt {CONTRACT_ID} v{CONTRACT_VERSION}. Rapporten granskas i uppdraget; "
        "beslut, granskare och datum registreras där, inte i filen",
        *_trace_lines(run, trace),
        f"- Körbild `{question.policy_ref}`",
        f"- Mall: {TEMPLATE_REF}",
    ]
    if question.note.strip():
        lines += [f"- Operatörens precisering: {_text(question.note)}"]
    if question.supersedes:
        lines += [f"- Ersätter det avslagna uppdraget `{question.supersedes}`"]
    return "\n".join(lines) + "\n"


def company_question_definition(
    renderer: Renderer, store: DeliveryStore, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    journal_dir: Path | None = None,
) -> FlowDefinition:
    """`journal_dir` är körjournalernas mapp; rapporten visar då modell och verktyg ur journalen."""
    def request(ctx: FlowContext):
        q = CompanyQuestion.model_validate(ctx.input)
        return request_for_company_question(q.month, q.note, task_id=f"task-{ctx.flow_id}")

    def render(ctx: FlowContext, trusted: ServiceLayer) -> SystemOutcome:
        q = CompanyQuestion.model_validate(ctx.input)
        step = ctx.result("answer")
        output = step.get("output") or {}
        answer = output.get("result")
        metrics = (output.get("evidence") or {}).get("metrics")
        if answer is not None and answer["month"] != q.month.isoformat():
            return SystemOutcome(result={"error": "month"},
                                 error=f"Svaret gäller {answer['month']}, beställningen {q.month.isoformat()}")
        now = clock()
        period = (q.month, month_end(q.month))
        failed = (output.get("evidence") or {}).get("metrics_failed", False)
        observations = company_observations(
            metrics, environment_id=q.environment_id, dataset_ref=q.dataset_ref, period=period,
            today=now.date(), now=now, missing_note=READ_FAILED_NOTE if failed else NOT_READ_NOTE,
        )
        read_at = datetime.fromisoformat(metrics["read_at"]) if metrics else None
        run = step.get("run") or {}
        trace = read_run_trace(journal_dir, run.get("run_id")) if journal_dir is not None else None
        markdown = report_markdown(q, flow_id=ctx.flow_id, answer=answer, run=run,
                                   observations=observations, read_at=read_at, trace=trace)
        metadata = ReportMetadata(title=f"Beståndsöversikt {q.month.strftime('%Y-%m')}",
                                  header=f"Uppdrag {ctx.flow_id}", footer=f"{CONTRACT_ID} v{CONTRACT_VERSION}")
        try:
            pdf = renderer(markdown, metadata)
        except Exception as exc:  # noqa: BLE001 – exporten misslyckades innan något skrevs; utfallet är känt
            return SystemOutcome(result={"error": "export"}, error=f"Exporten misslyckades: {type(exc).__name__}")
        manifest = {
            "contract": f"{CONTRACT_ID} v{CONTRACT_VERSION}", "template": TEMPLATE_REF, "team": TEAM,
            "run_id": (step.get("run") or {}).get("run_id"), "created_at": now.isoformat(),
            "environment_id": q.environment_id, "dataset_ref": q.dataset_ref, "policy_ref": q.policy_ref,
            "observations": [o.observation_id for o in observations], "status": "för granskning",
        }
        try:
            receipt = store.publish(ctx.flow_id, {"rapport.md": markdown.encode("utf-8"), "rapport.pdf": pdf}, manifest)
        except DeliveryError as exc:
            return SystemOutcome(result={"error": "store"}, error=str(exc))
        return SystemOutcome(result={
            "delivery": receipt,
            "answer_status": answer["status"] if answer else None,
            "observations": [o.model_dump(mode="json") for o in observations],
        })

    def deliver(ctx: FlowContext, trusted: ServiceLayer) -> SystemOutcome:
        receipt = ctx.result("render")["delivery"]
        try:
            for name, checksum in receipt["files"].items():
                store.read(ctx.flow_id, receipt["version"], name, checksum)
        except DeliveryError as exc:
            return SystemOutcome(result={"error": "delivery"}, error=str(exc))
        return SystemOutcome(result={
            "delivery_id": f"{ctx.flow_id}-v{receipt['version']}", "accepted_version": receipt["version"],
            "files": receipt["files"], "status": "accepted",
        })

    return FlowDefinition(
        flow_type=FLOW_TYPE,
        version="1",
        title="Fråga bolaget: beståndsöversikt",
        input_model=CompanyQuestion,
        steps=(
            AgentStep(key="answer", title="Aktuarien besvarar frågan", team=TEAM, request=request),
            SystemStep(key="render", title="Rapporten skapas", run=render),
            GateStep(key="review", title="Operatören granskar rapporten", binds=("answer", "render")),
            SystemStep(key="deliver", title="Leveransen godkänns", run=deliver),
        ),
    )
