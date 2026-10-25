"""Flödet `rule_change_parameter`: från regeländring till verifierad produktparameter (Fas 3c 3c-3, B-035).

Design: 02_system/flaggskeppsflöde.md §2 och §7, val C, D, F och H. Stegen:

| Steg          | Slag   | Vad                                                                         |
|---------------|--------|-----------------------------------------------------------------------------|
| `tolkning`    | agent  | compliance tolkar källan (`InterpretationProposal`) och skriver utkast     |
| `g1`          | grind  | operatören godkänner tolkningen; flödet bär exakt en parameterändring    |
| `insikt`      | agent  | aktuarien räknar på den godkända ändringen (`PortfolioImpactResult`)        |
| `g2`          | grind  | operatören antar ändringen: regelns version, giltighet och valfritt B-nummer |
| `regeltext`   | manuell| operatören för in berörda regler och parameterregistret, med commit-referensen |
| `aktivering`  | system | förslaget i godkännandekön under compliance-agentens identitet (val C)     |
| `verifiering` | system | `ReleaseEvidence`: lagrade versioner före och efter giltighetsdagen       |

Insikten kommer före beslutet (val D). Agenterna ändrar aldrig regeltext (val H) och lägger
aldrig själva aktiveringsförslaget: motorn gör det i betrodd kod, länkat till tolkningens
körning, och förslaget avgörs i `/godkannanden` – grinden ersätter inte det godkännandet.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agents.assignments import (
    mandate_from_interpretation,
    request_for_impact,
    request_for_interpretation,
)
from agents.flows.definition import (
    AgentStep,
    FlowContext,
    FlowDefinition,
    GateStep,
    ManualStep,
    SystemOutcome,
    SystemStep,
)
from agents.flows.store import FlowError
from agents.gateways.regulatory import HANDLE_PATTERN
from agents.scope import ParameterChangeMandate
from services import Actor, OperationContext, ServiceLayer

FLOW_TYPE = "rule_change_parameter"
#: Aktören som lägger aktiveringsförslaget – compliance-teamets ledande agent (val C)
COMPLIANCE_AGENT = Actor.agent("compliance_agent", team="compliance")
VERIFIER = Actor.system("flow_engine")


# --- indata och operatörens uppgifter ------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuleChangeInput(_Strict):
    source_handle: str = Field(pattern=HANDLE_PATTERN, description="Källan i regelverksgatewayen, valt bevakningsunderlag")


class RuleAdoption(_Strict):
    """Grind 2: regeländringen som operatören antar."""

    rule_version: str = Field(pattern=r"^\d+\.\d+$", description="Produktregelns nya version, t.ex. 1.1")
    valid_from: date = Field(description="Giltighetsdagen – samma som i den godkända tolkningen")
    decision_number: str | None = Field(default=None, pattern=r"^B-\d{3}$", description="B-nummer, om beslutet loggas")


class RuleTextCommit(_Strict):
    """Steg 3: regeltexten är införd i repot."""

    commit: str = Field(pattern=r"^[0-9a-f]{7,40}$", description="Commit med berörda produktregler och parameterregistret")
    note: str | None = Field(default=None, max_length=500)


# --- systemstegens resultat --------------------------------------------------------------------------


class VersionEvidence(_Strict):
    value: Decimal
    valid_from: date
    valid_to: date | None
    rule_id: str
    rule_version: str
    source_ref: str
    decision_ref: str


class ReleaseEvidence(_Strict):
    """Steg 5: avstämning av lagrade parameterversioner mot det godkända beslutet."""

    key: str
    approval_id: str
    before: VersionEvidence | None
    after: VersionEvidence | None
    verified: bool
    problems: list[str]


# --- hjälpare --------------------------------------------------------------------------------------


def proposed_change(ctx: FlowContext) -> dict[str, Any]:
    """Den godkända tolkningens parameterändring (exakt en)."""
    return ctx.result("tolkning")["output"]["result"]["parameter_changes"][0]


def mandate(ctx: FlowContext) -> ParameterChangeMandate:
    return mandate_from_interpretation(ctx.result("tolkning")["output"], ref=f"pc-{ctx.flow_id}")


def decision_ref(ctx: FlowContext) -> str:
    adoption = ctx.result("g2")["details"]
    number = adoption.get("decision_number")
    return f"{ctx.flow_id} G2" + (f" {number}" if number else "")


def _version_on(trusted: ServiceLayer, key: str, on: date) -> VersionEvidence | None:
    listing = trusted.execute("get_product_parameters", OperationContext(actor=VERIFIER), {"on_date": on.isoformat()}).output
    for v in listing.versions:
        if v.key == key and v.state == "gällande":
            return VersionEvidence(
                value=v.value, valid_from=v.valid_from, valid_to=v.valid_to, rule_id=v.rule_id,
                rule_version=v.rule_version, source_ref=v.source_ref, decision_ref=v.decision_ref,
            )
    return None


# --- grindarnas kontroller och systemstegen ---------------------------------------------------------


def check_interpretation(ctx: FlowContext, _details: None) -> None:
    """Grind 1: flödet för in exakt en parameterändring – fler ändringar är fler flöden."""
    changes = ctx.result("tolkning")["output"]["result"]["parameter_changes"]
    if len(changes) != 1:
        raise FlowError(
            f"Tolkningen föreslår {len(changes)} parameterändringar – flödet för in exakt en. "
            "Avslå och starta ett flöde per ändring"
        )


def check_adoption(ctx: FlowContext, adoption: RuleAdoption) -> None:
    """Grind 2: giltigheten är den som tolkningen föreslog och insikten räknade på."""
    proposed = date.fromisoformat(proposed_change(ctx)["valid_from"])
    if adoption.valid_from != proposed:
        raise FlowError(
            f"Giltighetsdagen {adoption.valid_from} är inte den godkända tolkningens {proposed}. "
            "Beståndsinsikten gäller den dagen – avslå och starta ett nytt flöde för en annan giltighet"
        )


def activate(ctx: FlowContext, trusted: ServiceLayer) -> SystemOutcome:
    """Steg 4: förslaget i kön under compliance-agentens identitet, länkat till tolkningen (val C)."""
    change = proposed_change(ctx)
    adoption = ctx.result("g2")["details"]
    data = {
        "key": change["key"], "value": str(change["new_value"]), "valid_from": adoption["valid_from"],
        "rule_version": adoption["rule_version"], "source_ref": ctx.input["source_handle"],
        "decision_ref": decision_ref(ctx),
    }
    commit = ctx.result("regeltext")["commit"]
    agent = OperationContext(
        actor=COMPLIANCE_AGENT, run_id=ctx.run_ids["tolkning"],
        reason=f"Regeländringen antagen i {ctx.flow_id} (grind 2); regeltexten införd i {commit}",
    )
    result = trusted.execute("schedule_product_parameter_change", agent, data)
    if result.approval_id is None:
        raise FlowError("Parameterändringen lades inte i godkännandekön – stäm av händelseloggen")
    return SystemOutcome(
        result={"operation": "schedule_product_parameter_change", "input": data,
                "proposed_by": COMPLIANCE_AGENT.id, "run_id": ctx.run_ids["tolkning"]},
        approval_id=result.approval_id,
    )


def verify(ctx: FlowContext, trusted: ServiceLayer) -> SystemOutcome:
    """Steg 5: stäm av beslutet mot lagrade parameterversioner på båda sidor om giltighetsdagen."""
    change = proposed_change(ctx)
    activation = ctx.result("aktivering")
    scheduled = activation["input"]
    key = scheduled["key"]
    valid_from = date.fromisoformat(scheduled["valid_from"])
    current, new = Decimal(str(change["current_value"])), Decimal(str(scheduled["value"]))
    day_before = valid_from - timedelta(days=1)

    before = _version_on(trusted, key, day_before)
    after = _version_on(trusted, key, valid_from)
    problems = []
    if after is None:
        problems.append(f"Ingen gällande version av {key} från {valid_from}")
    else:
        expected = {"value": new, "valid_from": valid_from, "rule_version": scheduled["rule_version"],
                    "source_ref": scheduled["source_ref"], "decision_ref": scheduled["decision_ref"]}
        for field, value in expected.items():
            if getattr(after, field) != value:
                problems.append(f"Versionen från {after.valid_from} har {field} {getattr(after, field)}, väntat {value}")
    if before is None or before.value != current:
        problems.append(f"Värdet före giltighetsdagen är {before.value if before else 'okänt'}, tolkningen angav {current}")
    elif before.valid_to != day_before:
        problems.append(f"Versionen före giltighetsdagen slutar {before.valid_to}, väntat {day_before}")
    evidence = ReleaseEvidence(
        key=key, approval_id=activation["approval"]["approval_id"], before=before, after=after,
        verified=not problems, problems=problems,
    )
    return SystemOutcome(result={"schema": "ReleaseEvidence", "evidence": evidence.model_dump(mode="json")})


RULE_CHANGE_PARAMETER = FlowDefinition(
    flow_type=FLOW_TYPE,
    version="2",
    title="Regeländring till produktparameter",
    input_model=RuleChangeInput,
    steps=(
        AgentStep("tolkning", "Tolkning och konsekvens", "compliance",
                  lambda ctx: request_for_interpretation(ctx.input["source_handle"])),
        GateStep("g1", "Godkänn tolkningen", binds=("tolkning",), check=check_interpretation),
        AgentStep("insikt", "Beståndsinsikt", "aktuarie", lambda ctx: request_for_impact(mandate(ctx)), mandate=mandate),
        GateStep("g2", "Anta regeländringen", binds=("tolkning", "insikt"), decision_model=RuleAdoption,
                 check=check_adoption),
        ManualStep("regeltext", "För in regeltexten", RuleTextCommit),
        SystemStep("aktivering", "Schemalägg parametern", activate),
        SystemStep("verifiering", "Verifiera i systemet", verify),
    ),
)
