"""En antagen regel som kräver kod lämnas till utvecklingskön i demo."""

from functools import partial

from pydantic import ConfigDict, Field, ValidationError

from agents.assignments import request_for_interpretation
from agents.flows.definition import AgentStep, FlowContext, FlowDefinition, GateStep, SystemOutcome, SystemStep
from agents.flows.definitions.rule_change_parameter import RuleAdoption, RuleChangeInput
from agents.flows.store import FlowError
from agents.results import InterpretationProposal
from agents.run import RunRequest
from services import Actor, ConflictError, ServiceLayer
from services.change_requests import ChangeRequestOrder, ChangeRequestOrigin, ChangeRequests, Notes, ShortText

FLOW_TYPE = "rule_change_code"
ADOPTION = "g2"
HANDOFF = "bestall_utveckling"


class CodeRuleAdoption(RuleAdoption):
    model_config = ConfigDict(str_strip_whitespace=True)

    rule_id: str = Field(pattern=r"^PR-ITP1-\d{3}$")
    code_reason: Notes
    affected_system: ShortText
    expected_effect: Notes


def _request_interpretation(ctx: FlowContext) -> RunRequest:
    request = request_for_interpretation(ctx.input["source_handle"])
    return request.model_copy(update={
        "goal": request.goal + " Förklara vilken ny logik som krävs. Lämna parameterlistan tom om "
        "befintliga parametrar inte kan genomföra ändringen. Redovisa tillämpliga parameterändringar.",
        "expected_output": "Tolkning med källor och utkast för operatörens beslut",
    })


def _order(ctx: FlowContext, adoption: CodeRuleAdoption) -> ChangeRequestOrder:
    interpretation = ctx.result("tolkning")
    output = interpretation.get("output") or {}
    if interpretation.get("run", {}).get("status") != "completed" or output.get("schema") != "InterpretationProposal":
        raise FlowError("Beställningen kräver en slutförd och verifierad tolkning")
    proposal = InterpretationProposal.model_validate(output.get("result"))
    if proposal.parameter_changes:
        raise FlowError("Tolkningen innehåller en parameterändring. Hantera den i parameterflödet")
    if adoption.rule_id not in proposal.affected_rules:
        raise FlowError("Den antagna regeln måste finnas bland tolkningens berörda regler")
    handle = ctx.input["source_handle"]
    source = next((item for item in output.get("evidence", {}).get("sources", [])
                   if item.get("handle") == handle and item.get("kind") == "bevakning" and item.get("sha256")), None)
    if source is None or handle not in proposal.source_handles:
        raise FlowError("Tolkningen saknar verifierat källunderlag för den valda källan")
    version = f" v{source['version']}" if source.get("version") else ""
    decision = f" {adoption.decision_number}" if adoption.decision_number else ""
    return ChangeRequestOrder(
        origin=ChangeRequestOrigin(channel=FLOW_TYPE, reference=f"{ctx.flow_id}/{HANDOFF}"),
        kind="rule_change", title=f"Inför {adoption.rule_id} v{adoption.rule_version}",
        need=proposal.summary, motivation=adoption.code_reason, affected_system=adoption.affected_system,
        acceptance=adoption.expected_effect, source_refs=f"{handle}{version} · sha {source['sha256']}",
        decision_ref=f"{ctx.flow_id} {ADOPTION.upper()}{decision}", rule_version=adoption.rule_version,
        effective_on=adoption.valid_from,
    )


def _check_adoption(ctx: FlowContext, adoption: CodeRuleAdoption) -> None:
    try:
        _order(ctx, adoption)
    except ValidationError as exc:
        raise FlowError("Tolkningen eller beslutet saknar komplett underlag för utveckling") from exc


def _submit(ctx: FlowContext, _trusted: ServiceLayer | None, *, requests: ChangeRequests) -> SystemOutcome:
    if ctx.approved_by.get(ADOPTION) != ctx.created_by:
        return SystemOutcome(result={}, error="Beställningen kräver ett verifierat beslut av flödets operatör.")
    try:
        adoption = CodeRuleAdoption.model_validate(ctx.result(ADOPTION).get("details"))
        order = _order(ctx, adoption)
        request = requests.submit_order(Actor.human(ctx.created_by), order)
    except (FlowError, ConflictError) as exc:
        return SystemOutcome(result={}, error=str(exc))
    except ValidationError:
        return SystemOutcome(result={}, error="Tolkningen eller beslutet saknar komplett underlag för utveckling.")
    return SystemOutcome(result={"change_request_id": str(request.id)})


def rule_change_code(requests: ChangeRequests) -> FlowDefinition:
    return FlowDefinition(
        flow_type=FLOW_TYPE,
        version="1",
        title="Regeländring som kräver kod",
        input_model=RuleChangeInput,
        steps=(
            AgentStep("tolkning", "Tolkning och konsekvens", "compliance", _request_interpretation),
            GateStep(ADOPTION, "Anta regeln för utveckling", binds=("tolkning",),
                     decision_model=CodeRuleAdoption, check=_check_adoption),
            SystemStep(HANDOFF, "Lämna till utveckling", partial(_submit, requests=requests)),
        ),
    )
