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
COMPANY_METRICS = "get_company_metrics"
SNAPSHOT = "get_portfolio_snapshot"
PREMIUM_FLOWS = "get_premium_flows"


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


class CompanyAnswer(_Strict):
    """Bolagsfrågan (OC-3a, B-041): aktuarien besvarar en beståndsfråga ur ledningsaggregatet.

    Talen i rapporten kommer ur get_company_metrics, inte ur texten (val F).
    """

    status: Literal["answered", "partial", "unavailable", "needs_clarification"] = Field(
        description="answered bara när båda måtten finns och operatörens precisering kan besvaras med dem; "
                    "partial när något mått är dolt eller underkänt; unavailable när preciseringen frågar efter "
                    "något underlaget inte innehåller (t.ex. andra mått eller tidsjämförelser), även om måtten "
                    "kunde läsas; needs_clarification vid oklar fråga")
    month: date = Field(description="Månaden du läste med get_company_metrics (månadsförsta)")
    conclusion: str = Field(description="Slutsatsen för en VD: svaret först, i vanlig svenska utan verktygs-, "
                                        "funktions- eller kolumnnamn. Skriv inga andra tal än dem i "
                                        "get_company_metrics-svaret")
    limitations: list[str] = Field(description="Begränsningar utöver rapportens fasta (läsdag, bankavstämning, "
                                               "tidsjämförelser) som påverkar slutsatsen – ofta inga")
    assumptions: list[str] = Field(description="Antaganden du har gjort")
    next_steps: list[str] = Field(description="Vad som behövs för ett fullständigare svar, om något")


class ProductReportSummary(_Strict):
    """Produktrapporten (A2, B-042): aktuarien sammanfattar bestånd och premier för ett år.

    Tabellerna i rapporten kommer ur get_portfolio_snapshot och get_premium_flows, inte ur texten.
    """

    year: int = Field(description="Året du läste med get_portfolio_snapshot och get_premium_flows")
    conclusion: str = Field(description="Sammanfattningen för VD och styrelse: slutsatsen först, i vanlig svenska "
                                        "utan verktygs-, funktions- eller kolumnnamn. Skriv inga andra tal än dem "
                                        "i verktygens svar")
    key_findings: list[str] = Field(description="De viktigaste iakttagelserna om bestånd och premier")
    recommendations: list[str] = Field(description="Åtgärder eller utredningar du föreslår, om några")
    limitations: list[str] = Field(description="Begränsningar utöver rapportens fasta (ej beräknade avsnitt, läsdag, "
                                               "bankavstämning) – ofta inga")


RESULT_SCHEMAS: dict[str, type[_Strict]] = {
    "InterpretationProposal": InterpretationProposal,
    "PortfolioImpactResult": PortfolioImpactResult,
    "CompanyAnswer": CompanyAnswer,
    "ProductReportSummary": ProductReportSummary,
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
    drafts: dict[str, dict] = {}
    estimate: dict | None = None
    metrics: dict[str, dict] = {}  # månad -> senaste lyckade get_company_metrics
    yearly: dict[str, dict[int, dict]] = {SNAPSHOT: {}, PREMIUM_FLOWS: {}}  # år -> senaste lyckade läsning
    metrics_failed = False  # ett anrop som tjänstelagret avböjde, t.ex. en datakälla som inte kunde läsas
    for outcome in dispatches:
        for call in outcome.calls:
            if call.status != CallStatus.DONE:
                metrics_failed |= call.status == CallStatus.ERROR and operation_of.get(call.skill) == COMPANY_METRICS
                continue
            output = json.loads(call.result.content).get("output") or {}
            operation = operation_of.get(call.skill)
            if operation == READ_DOCUMENT:
                doc = output["document"]
                sources[doc["handle"]] = {
                    "handle": doc["handle"], "kind": doc["kind"], "title": doc["title"], "version": doc["version"],
                    "sha256": doc["sha256"], "fictional": doc["fictional"],
                }
            elif operation == WRITE_DRAFT:
                drafts[output["name"]] = {"name": output["name"], "title": output["title"],
                                          "reference": output["reference"], "sha256": output["sha256"]}
            elif operation == ESTIMATE:
                estimate = output
            elif operation == COMPANY_METRICS:
                metrics[output["period_from"]] = output
            elif operation in yearly:
                yearly[operation][output["year"]] = output

    # CompanyAnswer läser inga dokument och skriver inga utkast (B-041 val A)
    handles, names = getattr(result, "source_handles", ()), getattr(result, "draft_names", ())
    problems = [f"källan {h} är inte läst i körningen" for h in handles if h not in sources]
    problems += [f"utkastet {n} är inte skrivet i körningen" for n in names if n not in drafts]
    evidence: dict[str, Any] = {
        "sources": [sources[h] for h in handles if h in sources],
        "drafts": [drafts[n] for n in names if n in drafts],
    }
    if isinstance(result, InterpretationProposal):
        if not result.source_handles:
            problems.append("tolkningen anger ingen läst källa")
    if isinstance(result, PortfolioImpactResult):
        if estimate is None:
            problems.append("ingen beräkning med estimate_parameter_change_impact i körningen")
        evidence["estimate"] = estimate
    if isinstance(result, CompanyAnswer):
        read = metrics.get(result.month.isoformat())
        if read is None and result.status in ("answered", "partial"):
            problems.append(f"ingen läsning med get_company_metrics för {result.month.isoformat()} i körningen")
        if read is not None:
            incomplete = read["insured_suppressed"] or read["paid_state"] != "available"
            if result.status == "answered" and incomplete:
                problems.append("svaret anges som fullständigt trots dolt eller underkänt mått")
            texts = [result.conclusion, *result.limitations, *result.assumptions, *result.next_steps]
            problems += [f"talet {n} i svaret finns inte i underlaget" for n in unsupported_numbers(texts, read)]
        evidence["metrics"] = read
        evidence["metrics_failed"] = read is None and metrics_failed
    if isinstance(result, ProductReportSummary):
        snapshot, flows = yearly[SNAPSHOT].get(result.year), yearly[PREMIUM_FLOWS].get(result.year)
        problems += [f"ingen läsning med {name} för {result.year} i körningen"
                     for name, read in ((SNAPSHOT, snapshot), (PREMIUM_FLOWS, flows)) if read is None]
        if snapshot is not None and flows is not None:
            texts = [result.conclusion, *result.key_findings, *result.recommendations, *result.limitations]
            values, dates = _values_and_dates([snapshot, flows])
            problems += [f"talet {n} i sammanfattningen finns inte i underlaget"
                         for n in _unsupported(texts, values | _SECTION_NUMBERS, dates)]
        evidence["snapshot"], evidence["premium_flows"] = snapshot, flows
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


#: Produktrapportens avsnittsnummer 1–10 får nämnas
_SECTION_NUMBERS = {Decimal(n) for n in range(1, 11)}


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


def unsupported_numbers(texts: Iterable[str], metrics: dict[str, Any]) -> list[str]:
    """Tal i modellens text som inte motsvarar ett mätvärde, ett datum i läsningen eller en känd gräns (val F).

    Belopp får skrivas exakt eller avrundat till hela kronor, med mellanslag som tusentalsavgränsare.
    """
    allowed: set[Decimal] = set()
    for key in ("insured_count", "paid_sek"):
        if metrics.get(key) is not None:
            value = Decimal(str(metrics[key]))
            allowed |= {value, value.quantize(Decimal(1))}
    dates = {date.fromisoformat(metrics[k]) for k in ("as_of_date", "period_from", "period_to") if metrics.get(k)}
    if metrics.get("period_to"):  # periodens sista dag; period_to är exklusivt
        dates.add(date.fromisoformat(metrics["period_to"]) - timedelta(days=1))
    if metrics.get("read_at"):
        dates.add(datetime.fromisoformat(metrics["read_at"]).date())
    return _unsupported(texts, allowed, dates)


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
