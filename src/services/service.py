"""ServiceLayer – den enda vägen in till försäkringssystemets operationer (B-028).

Handläggar-UI:t, agenter (via harness) och skript anropar `execute()`. Här
kontrolleras aktören mot åtkomstregistret, förslag från agenter läggs i
godkännandekön, och varje ändring loggas i händelseloggen.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ValidationError

from services.access import AccessDecision, AccessRegister, effective_access
from services.approvals import (
    ApprovalRequest,
    ApprovalStore,
    DatabaseApprovalStore,
    MemoryApprovalStore,
    decided,
)
from services.contract import (
    AgentAccess,
    Operation,
    OperationContext,
    OperationRegistry,
    default_registry,
)
from services.errors import (
    AccessDeniedError,
    ApprovalError,
    InvalidInputError,
    MissingReasonError,
)
from services.events import DatabaseEventLog, EventLog, OperationEvent, default_event_log
from services.rules import ProductRuleCatalog

SessionFactory = Callable[[], AbstractContextManager[Any]]  # se services.db


class ResultStatus(StrEnum):
    DONE = "done"
    PENDING_APPROVAL = "pending_approval"


@dataclass(frozen=True)
class OperationResult:
    status: ResultStatus
    operation: str
    output: BaseModel | None = None
    approval_id: str | None = None

    @property
    def pending(self) -> bool:
        return self.status == ResultStatus.PENDING_APPROVAL


class ServiceLayer:
    def __init__(
        self,
        registry: OperationRegistry | None = None,
        register: AccessRegister | None = None,
        rules: ProductRuleCatalog | None = None,
        events: EventLog | None = None,
        approvals: ApprovalStore | None = None,
        session_factory: SessionFactory | None = None,
    ) -> None:
        """
        session_factory: öppnar en databastransaktion per operation (services.db). Med den
        hamnar händelselogg och godkännandekö i databasen om inget annat anges; utan den
        körs operationerna utan session och loggen hamnar i fil/minne.
        """
        self.registry = registry if registry is not None else default_registry
        self.register = register if register is not None else AccessRegister.load()
        self.register.validate_against(self.registry)
        self.rules = rules if rules is not None else ProductRuleCatalog()
        if events is None:
            events = DatabaseEventLog(session_factory) if session_factory else default_event_log()
        if approvals is None:
            approvals = DatabaseApprovalStore(session_factory) if session_factory else MemoryApprovalStore()
        self.events = events
        self.approvals = approvals
        self._session_factory = session_factory

    # --- insyn -------------------------------------------------------------

    def decision(self, name: str) -> AccessDecision:
        """Effektiv agentåtkomst för en operation och varför."""
        return effective_access(self.registry.get(name), self.register, self.rules)

    def operations_for_agents(self) -> list[Operation]:
        """Operationer som agenter får se som verktyg – allt utom HUMAN_ONLY (för harness)."""
        return [
            op for op in self.registry
            if self.decision(op.name).effective != AgentAccess.HUMAN_ONLY
        ]

    # --- anrop ------------------------------------------------------------

    def execute(
        self, name: str, ctx: OperationContext, data: BaseModel | dict[str, Any]
    ) -> OperationResult:
        op = self.registry.get(name)
        validated = self._validate_input(op, data)
        if op.kind.changes_state and not (ctx.reason or "").strip():
            raise MissingReasonError(f"'{op.name}' ändrar data och kräver en motivering (reason)")

        if ctx.actor.is_agent:
            decision = effective_access(op, self.register, self.rules)
            if decision.effective == AgentAccess.HUMAN_ONLY:
                detail = "; ".join(decision.reasons) or "HUMAN_ONLY i registret"
                self._record(op, ctx, validated, outcome="denied", detail=detail)
                raise AccessDeniedError(
                    f"Agenten '{ctx.actor.id}' får inte utföra '{op.name}' – endast handläggare"
                    + (f" ({'; '.join(decision.reasons)})" if decision.reasons else ""),
                    operation=op.name,
                    actor_id=ctx.actor.id,
                    reasons=decision.reasons,
                )
            if decision.effective == AgentAccess.APPROVAL:
                request = ApprovalRequest(
                    operation=op.name,
                    input=validated.model_dump(mode="json"),
                    reason=ctx.reason,
                    proposed_by=ctx.actor.id,
                    proposed_by_team=ctx.actor.team,
                    run_id=ctx.run_id,
                    case_id=ctx.case_id,
                )
                self.approvals.add(request)
                self._record(op, ctx, validated, outcome="proposed", approval_id=request.id)
                return OperationResult(
                    ResultStatus.PENDING_APPROVAL, op.name, approval_id=request.id
                )

        output = self._run(op, ctx, validated)
        return OperationResult(ResultStatus.DONE, op.name, output=output)

    def approve(
        self, approval_id: str, ctx: OperationContext, note: str | None = None
    ) -> OperationResult:
        """En handläggare godkänner ett agentförslag – operationen körs mot aktuellt läge."""
        request = self._pending_request(approval_id, ctx)
        op = self.registry.get(request.operation)
        validated = self._validate_input(op, request.input)
        run_ctx = replace(
            ctx,
            reason=request.reason,
            run_id=request.run_id,
            case_id=request.case_id or ctx.case_id,
        )
        output = self._run(op, run_ctx, validated, proposed_by=request.proposed_by, approval_id=request.id)
        self.approvals.update(decided(request, "approved", ctx.actor.id, note))
        return OperationResult(ResultStatus.DONE, op.name, output=output, approval_id=request.id)

    def reject(self, approval_id: str, ctx: OperationContext, note: str | None = None) -> None:
        request = self._pending_request(approval_id, ctx)
        op = self.registry.get(request.operation)
        self.approvals.update(decided(request, "rejected", ctx.actor.id, note))
        self._record(
            op,
            replace(ctx, reason=request.reason, run_id=request.run_id),
            self._validate_input(op, request.input),
            outcome="rejected",
            proposed_by=request.proposed_by,
            approval_id=request.id,
            detail=note,
        )

    # --- interna hjälpare ---------------------------------------------------

    @staticmethod
    def _validate_input(op: Operation, data: BaseModel | dict[str, Any]) -> BaseModel:
        try:
            if isinstance(data, op.input_model):
                return data
            payload = data.model_dump() if isinstance(data, BaseModel) else data
            return op.input_model.model_validate(payload)
        except ValidationError as exc:
            raise InvalidInputError(f"Ogiltig indata till '{op.name}': {exc}") from exc

    def _pending_request(self, approval_id: str, ctx: OperationContext) -> ApprovalRequest:
        if ctx.actor.type != "human":
            raise ApprovalError("Bara en människa kan godkänna eller avslå ett agentförslag")
        request = self.approvals.get(approval_id)
        if request is None:
            raise ApprovalError(f"Okänt godkännandeärende: {approval_id}")
        if request.status != "pending":
            raise ApprovalError(f"Ärendet {approval_id} är redan {request.status}")
        return request

    def _run(
        self,
        op: Operation,
        ctx: OperationContext,
        data: BaseModel,
        proposed_by: str | None = None,
        approval_id: str | None = None,
    ) -> BaseModel | None:
        scope = self._session_factory() if self._session_factory else nullcontext(None)
        with scope as session:
            output = op.func(replace(ctx, session=session), data)
            if op.output_model is not None and not isinstance(output, op.output_model):
                raise TypeError(
                    f"'{op.name}' returnerade {type(output).__name__}, väntade {op.output_model.__name__}"
                )
            if op.kind.changes_state or op.pii:
                # I samma transaktion som operationen när loggen ligger i databasen (T3)
                self._record(
                    op, ctx, data, outcome="executed", output=output,
                    proposed_by=proposed_by, approval_id=approval_id, session=session,
                )
        return output

    def _record(
        self,
        op: Operation,
        ctx: OperationContext,
        data: BaseModel,
        *,
        outcome: str,
        output: BaseModel | None = None,
        proposed_by: str | None = None,
        approval_id: str | None = None,
        detail: str | None = None,
        session: Any = None,
    ) -> None:
        self.events.record(
            OperationEvent(
                operation=op.name,
                kind=op.kind.value,
                outcome=outcome,
                actor_type=ctx.actor.type,
                actor_id=ctx.actor.id,
                actor_team=ctx.actor.team,
                proposed_by=proposed_by,
                approval_id=approval_id,
                run_id=ctx.run_id,
                case_id=ctx.case_id,
                reason=ctx.reason,
                rules=list(op.rules),
                pii=op.pii,
                input=data.model_dump(mode="json"),
                # Läsresultat loggas inte (kan vara stora och fulla av personuppgifter)
                output=output.model_dump(mode="json") if output is not None and op.kind.changes_state else None,
                detail=detail,
            ),
            session=session,
        )
