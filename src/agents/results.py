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
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any

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


RESULT_SCHEMAS: dict[str, type[_Strict]] = {
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
    return getattr(result, "summary", None) or getattr(result, "insight", "")


def verify(
    result: BaseModel, profile: EffectiveProfile, dispatches: Iterable[DispatchOutcome]
) -> dict[str, Any]:
    """Resultatet med harness bevis – eller ResultError med alla skäl."""
    operation_of = {d.skill: d.operation for d in profile.decisions}
    sources: dict[str, dict] = {}
    drafts: dict[str, dict] = {}
    estimate: dict | None = None
    for outcome in dispatches:
        for call in outcome.calls:
            if call.status != CallStatus.DONE:
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

    problems = [f"källan {h} är inte läst i körningen" for h in result.source_handles if h not in sources]
    problems += [f"utkastet {n} är inte skrivet i körningen" for n in result.draft_names if n not in drafts]
    evidence: dict[str, Any] = {
        "sources": [sources[h] for h in result.source_handles if h in sources],
        "drafts": [drafts[n] for n in result.draft_names if n in drafts],
    }
    if isinstance(result, InterpretationProposal):
        if not result.source_handles:
            problems.append("tolkningen anger ingen läst källa")
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
