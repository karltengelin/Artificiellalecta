"""Stegresultat för agentkörningar (Fas 3c 3c-T, flaggskeppsflöde.md §7, harness.md §10.3).

Ett uppdrag kan begära ett resultatschema (`RunRequest.result_schema`). Modellens slutsvar
tvingas då till schemat av AI-lagret, och harness kontrollerar det mot det körningen
faktiskt gjorde innan resultatet godtas:

- Varje angiven källa ska ha lästs i körningen med `read_regulatory_document`. Källans
  version och kontrollsumma tas ur gatewayens svar, inte ur modellens text.
- Varje angivet utkast ska ha skrivits i körningen med `write_draft`; referensen tas ur kvittot.
- Beståndsinsikten bär beräkningen från `estimate_parameter_change_impact` oförändrad.
  Modellen skriver insikten i ord; tal kommer bara från betrodd kod (harness.md §9.2).

Ett resultat som inte håller blir `needs_human` med skälen – aldrig ett godkänt steg.
Strukturerat underlag är fortfarande ingen beslutstoken: grindarna i flödet (3c-2) beslutar.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.dispatcher import CallStatus, DispatchOutcome
from agents.profile import EffectiveProfile
from services.operations.product_parameters import ParameterKey

READ_DOCUMENT = "read_regulatory_document"
WRITE_DRAFT = "write_draft"
ESTIMATE = "estimate_parameter_change_impact"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProposedParameterChange(_Strict):
    key: ParameterKey = Field(description="Parametern som ändras, t.ex. premium_age_end")
    current_value: Decimal = Field(description="Värdet som gäller i dag enligt get_product_parameters")
    new_value: Decimal = Field(description="Värdet enligt källan")
    valid_from: date = Field(description="Första premiemånad som omfattas (månadsförsta)")
    rule_id: str = Field(description="Produktregeln som bär värdet, t.ex. PR-ITP1-013")
    rationale: str = Field(description="Var i källan ändringen står och hur den tolkas")


class InterpretationProposal(_Strict):
    """Steg 1: compliance tolkar en källa till produktregler och parametrar."""

    summary: str = Field(description="Ändringen och tolkningen i några meningar")
    affected_rules: list[str] = Field(description="Produktregler som berörs, t.ex. PR-ITP1-013 och PR-ITP1-016")
    parameter_changes: list[ProposedParameterChange] = Field(description="Föreslagna parameterändringar")
    customer_impact: str = Field(description="Vad ändringen betyder för de försäkrade, utan personuppgifter")
    uncertainties: list[str] = Field(description="Osäkerheter och frågor till operatören")
    source_handles: list[str] = Field(description="Handtag för dokument du har läst i den här körningen")
    draft_names: list[str] = Field(description="Filnamn för utkast du har skrivit i den här körningen")


class PortfolioImpactResult(_Strict):
    """Steg 2: aktuarien tar fram beståndsinsikten för den godkända ändringen."""

    insight: str = Field(description="Insikten i ord. Tal hämtas ur beräkningen – räkna inte själv")
    key_findings: list[str] = Field(description="De viktigaste iakttagelserna, med år där det passar")
    uncertainties: list[str] = Field(description="Begränsningar och antaganden som påverkar slutsatsen")
    source_handles: list[str] = Field(description="Handtag för dokument du har läst i den här körningen")
    draft_names: list[str] = Field(description="Filnamn för utkast du har skrivit i den här körningen")


class CompanyInterpretation(InterpretationProposal):
    change_kind: Literal["parameter", "code", "mixed", "unsupported", "interpretation_only"]
    effective_on: date | None = Field(description="Giltighet enligt källan, eller null om den ännu är okänd")
    code_dependency: str = Field(max_length=1200, description="Vilken ny logik eller annan förmåga som behövs")


class CaseAnswer(_Strict):
    """Deluppdrag i ett ärende. Ett modellsvar bevisar aldrig att ärendet är genomfört."""

    status: Literal["answered", "needs_information", "needs_human"]
    summary: str = Field(min_length=1, max_length=12000)
    questions: list[str] = Field(max_length=8)
    limitations: list[str] = Field(max_length=8)


class ActuarialAnswer(_Strict):
    """Öppet aktuariellt uppdrag, med verifierbara analysreferenser."""

    status: Literal["answered", "needs_information", "needs_human"]
    summary: str = Field(min_length=1, max_length=12000)
    questions: list[str] = Field(max_length=8)
    limitations: list[str] = Field(max_length=12)
    analysis_refs: list[str] = Field(max_length=15, description="Id:n som arbetsbänken gav eller läste i denna körning")


class CoordinationAnswer(_Strict):
    status: Literal["answered", "waiting", "needs_information", "needs_human"]
    summary: str = Field(min_length=1, max_length=2500)
    source_handles: list[str] = Field(max_length=12)
    assignment_refs: list[str] = Field(max_length=10)


RESULT_SCHEMAS: dict[str, type[_Strict]] = {
    "CoordinationAnswer": CoordinationAnswer,
    "CompanyInterpretation": CompanyInterpretation,
    "ActuarialAnswer": ActuarialAnswer,
    "CaseAnswer": CaseAnswer,
    "InterpretationProposal": InterpretationProposal,
    "PortfolioImpactResult": PortfolioImpactResult,
}


class ResultError(Exception):
    """Resultatet stämmer inte med körningen."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


def schema_for(name: str | None) -> type[_Strict] | None:
    if name is None:
        return None
    try:
        return RESULT_SCHEMAS[name]
    except KeyError:
        raise ValueError(f"Okänt resultatschema: {name!r} (kända: {', '.join(RESULT_SCHEMAS)})") from None


def summary_of(result: BaseModel) -> str:
    return getattr(result, "summary", None) or getattr(result, "insight", None) or getattr(result, "conclusion", "")


def verify(
    result: BaseModel, profile: EffectiveProfile, dispatches: Iterable[DispatchOutcome]
) -> dict[str, Any]:
    """Resultatet med harness bevis – eller ResultError med alla skäl."""
    operation_of = {d.skill: d.operation for d in profile.decisions}
    sources: dict[str, dict] = {}
    source_text: dict[str, list[str]] = {}
    drafts: dict[str, dict] = {}
    estimate: dict | None = None
    read_case = False
    analyses = {}
    assignments = {}
    for outcome in dispatches:
        for call in outcome.calls:
            if call.status != CallStatus.DONE:
                continue
            output = json.loads(call.result.content).get("output") or {}
            operation = operation_of.get(call.skill)
            if operation == "coordinate_company_work":
                for item in output.get("data", {}).get("assignments", []):
                    assignments[item["id"]] = item
            if operation == "actuarial_workbench":
                delivery = output.get("payload", {})
                if "id" in delivery and "content" in delivery:
                    analyses[delivery["id"]] = delivery
            read_case |= operation == "get_case"
            if operation == READ_DOCUMENT:
                doc = output["document"]
                sources[doc["handle"]] = {
                    "handle": doc["handle"], "kind": doc["kind"], "title": doc["title"], "version": doc["version"],
                    "sha256": doc["sha256"], "fictional": doc["fictional"],
                }
                if isinstance(result, CoordinationAnswer):
                    source_text.setdefault(doc["handle"], []).append(output["text"])
            elif operation == WRITE_DRAFT:
                drafts[output["name"]] = {"name": output["name"], "title": output["title"],
                                          "reference": output["reference"], "sha256": output["sha256"]}
            elif operation == ESTIMATE:
                estimate = output
    handles, names = getattr(result, "source_handles", ()), getattr(result, "draft_names", ())
    problems = [f"källan {h} är inte läst i körningen" for h in handles if h not in sources]
    problems += [f"utkastet {n} är inte skrivet i körningen" for n in names if n not in drafts]
    evidence: dict[str, Any] = {
        "sources": [sources[h] for h in handles if h in sources],
        "drafts": [drafts[n] for n in names if n in drafts],
    }
    if isinstance(result, InterpretationProposal) and not result.source_handles:
        problems.append("tolkningen anger ingen läst källa")
    if isinstance(result, CaseAnswer) and not read_case:
        problems.append("ärendet har inte lästs med get_case i körningen")
    if isinstance(result, CoordinationAnswer):
        refs = result.assignment_refs
        problems += [f"deluppdraget {ref} har inte lästs i körningen" for ref in refs if ref not in assignments]
        if result.status == "answered" and not (handles or any(
                assignments.get(ref, {}).get("status") == "completed" for ref in refs)):
            problems.append("svaret kräver en läst bolagskälla eller ett läst specialistresultat")
        # Premiebelopp visas ur det sparade aggregatet. Kvalitativa slutsatser och
        # tal från lästa dokument får stå i svaret.
        source_snippets = [snippet for h in handles for snippet in source_text.get(h, ())]
        if any(assignments.get(ref, {}).get("capability") == "estimate_premium_effect" for ref in refs):
            problems += [f"ange premieeffekten i ord och hänvisa till analysens tabell i stället för talet {n}"
                         for n in _unsupported([result.summary], set(), set())]
        elif result.status == "answered" and not refs:
            doc_numbers = {n for n in _unsupported([result.summary], set(), set())
                           if not any(re.search(rf"(?<!\d){re.escape(n)}(?!\d)", snippet)
                                      for snippet in source_snippets)}
            problems += [f"talet {n} saknar stöd i det lästa källutdraget" for n in sorted(doc_numbers)]
        evidence["assignments"] = [assignments[ref] for ref in refs if ref in assignments]
    if isinstance(result, ActuarialAnswer):
        problems += [f"analysen {ref} har inte lästs eller skapats i körningen"
                     for ref in result.analysis_refs if ref not in analyses]
        cited = [analyses[ref]["content"] for ref in result.analysis_refs if ref in analyses]
        if cited:
            values, dates = _values_and_dates(cited)
            values |= {Decimal(n) for n in (0, 1, 2, 10, 95, 100)}
            problems += [f"talet {n} i svaret finns inte i analysunderlaget"
                         for n in _unsupported([result.summary, *result.limitations], values, dates)]
        else:
            problems += [f"talet {n} saknar läst analysunderlag"
                         for n in _unsupported([result.summary], {Decimal(0), Decimal(1)}, set())]
        evidence["analyses"] = [{k: v for k, v in analyses[ref].items() if k != "content"}
                                for ref in result.analysis_refs if ref in analyses]
    if isinstance(result, PortfolioImpactResult):
        if estimate is None:
            problems.append("ingen beräkning med estimate_parameter_change_impact i körningen")
        evidence["estimate"] = estimate
    if problems:
        raise ResultError(problems)
    return {
        "schema": type(result).__name__,
        "result": result.model_dump(mode="json"),
        "evidence": evidence,
    }


#: Tal som får stå i texten utan att vara mätvärden: småcellsgränsen 1–9/10 och fönstret 11/12 månader
_STRUCTURAL_NUMBERS = {Decimal(n) for n in (1, 9, 10, 11, 12)}
_ISO_DATE = re.compile(r"(?<![\w-])(\d{4})-(\d{2})(?:-(\d{2}))?(?![\w-])")
_SPACES = r"[ \u00a0\u202f]"  # mellanslag, hårt och smalt hårt mellanslag
_NUMBER = re.compile(rf"(?<![\w§.,-])\d{{1,3}}(?:{_SPACES}\d{{3}})+(?:[.,]\d+)?(?![\w-])"
                     r"|(?<![\w§.,-])\d+(?:[.,]\d+)?(?![\w-])")




def _values_and_dates(outputs: Iterable[dict[str, Any]]) -> tuple[set[Decimal], set[date]]:
    """Alla tal och datum i verktygssvaren – belopp exakt och avrundade till hela kronor."""
    values: set[Decimal] = set()
    dates: set[date] = set()

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif isinstance(node, bool) or node is None:
            return
        elif isinstance(node, (int, float)):
            values.add(Decimal(str(node)))
        elif isinstance(node, str):
            if key == "read_at":
                dates.add(datetime.fromisoformat(node).date())
            elif _ISO_DATE.fullmatch(node) and node.count("-") == 2:
                d = date.fromisoformat(node)
                dates.add(d)
                if key == "period_to":  # exklusivt slut: periodens sista dag
                    dates.add(d - timedelta(days=1))
            else:
                try:
                    value = Decimal(node)
                except InvalidOperation:  # etiketter som 1960–1969: talen i etiketten får nämnas
                    values.update(Decimal(n) for n in re.findall(r"\d+", node))
                    return
                values.update({value, value.quantize(Decimal(1))})

    for output in outputs:
        walk(output)
    return values, dates


def _unsupported(texts: Iterable[str], values: set[Decimal], dates: set[date]) -> list[str]:
    """Tal och ISO-datum i texterna som varken är bland värdena, datumens delar eller strukturella gränser."""
    allowed = set(_STRUCTURAL_NUMBERS) | values
    allowed |= {Decimal(part) for d in dates for part in (d.year, d.month, d.day)}
    months = {(d.year, d.month) for d in dates}
    found: list[str] = []
    for text in texts:
        for match in _ISO_DATE.finditer(text):
            year, month, day = int(match[1]), int(match[2]), match[3]
            ok = (year, month) in months if day is None else any(
                (d.year, d.month, d.day) == (year, month, int(day)) for d in dates)
            if not ok:
                found.append(match[0])
        for match in _NUMBER.finditer(_ISO_DATE.sub(" ", text)):
            raw = match[0]
            try:
                value = Decimal(re.sub(_SPACES, "", raw).replace(",", "."))
            except InvalidOperation:  # pragma: no cover – mönstret ger bara tal
                found.append(raw)
                continue
            if value not in allowed:
                found.append(raw)
    return found
