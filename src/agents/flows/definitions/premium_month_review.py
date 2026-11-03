"""Mänsklig granskning av färdig månadsanalys i den befintliga flödesmotorn."""

from agents.flows.definition import (
    FlowContext,
    FlowDefinition,
    GateStep,
    SystemOutcome,
    SystemStep,
)
from agents.flows.store import FlowError, bound_hash, canonical_hash, load
from services import Actor, OperationContext, ServiceLayer
from services.operations.premium_month import JournalQuery

FLOW_TYPE = "premium_month_review"


def premium_month_review_definition() -> FlowDefinition:
    def prepare(ctx: FlowContext, service: ServiceLayer) -> SystemOutcome:
        query = JournalQuery.model_validate(ctx.input)
        context = OperationContext(actor=Actor.system(FLOW_TYPE))
        status = service.execute("get_premium_month", context, query).output.payload
        if status["review_checksum"] is None:
            return SystemOutcome(result={}, error="Stäng och stäm av månaden före granskningen")
        result = service.execute("perform_actuarial_analysis", context,
            {"analysis": "monthly_fta_change", "parameters_json": query.model_dump_json()}).output.payload
        if result["status"] != "reconciled":
            return SystemOutcome(result={"status": result["status"]}, error="Underlaget kan inte granskas som avstämt")
        return SystemOutcome(result={"status": status, "analysis": result})

    def accept(ctx: FlowContext, service: ServiceLayer) -> SystemOutcome:
        # Identiteten kommer endast ur flödesmotorns varaktiga mänskliga grindbeslut,
        # aldrig ur prompten, flödets indata eller ett systemaktörsnamn.
        with service._session_factory() as session:
            flow, steps, decisions = load(session, ctx.flow_id)
            gate = next((d for d in reversed(decisions) if d.step_key == "review"), None)
            prepared = next((s for s in steps if s.step_key == "prepare"), None)
            if (flow.flow_type != FLOW_TYPE or gate is None or gate.decision != "approved"
                    or gate.bound_hash != bound_hash({s.step_key: s for s in steps}, ("prepare",))
                    or prepared is None or canonical_hash(ctx.result("prepare")) != prepared.result_hash):
                raise FlowError("Ett giltigt mänskligt beslut om exakt analysunderlag krävs")
            operator = gate.decided_by
        query = JournalQuery.model_validate(ctx.input)
        result = service.execute("approve_premium_month", OperationContext(actor=Actor.human(operator),
            reason=f"Granskningsbeslut {ctx.flow_id}/review", run_id=ctx.flow_id),
            {"journal_id": query.journal_id,
             "reviewed_checksum": ctx.result("prepare")["status"]["review_checksum"]})
        return SystemOutcome(result=result.output.payload)

    return FlowDefinition(flow_type=FLOW_TYPE, version="1", title="Granska avstämd syntetisk FTA-månad",
        input_model=JournalQuery, steps=(
            SystemStep(key="prepare", title="Verifiera och visa månadsanalys", run=prepare),
            GateStep(key="review", title="Aktuarien granskar månadsleveransen", binds=("prepare",)),
            SystemStep(key="accept", title="Registrera analysgodkännandet", run=accept),
        ))
