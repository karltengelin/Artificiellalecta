"""ServiceLayer – den enda vägen in till försäkringssystemets operationer (B-028).

Handläggar-UI:t, agenter (via harness) och skript anropar `execute()`. Här
kontrolleras aktören mot åtkomstregistret, förslag från agenter läggs i
godkännandekön, och varje ändring loggas i händelseloggen.

Transaktionsgräns (services.transaction): varje anrop är en transaktion.
Ändring + loggrad, förslag + loggrad, godkännandets status + ändring +
loggrad, avslag + loggrad – sparas tillsammans eller inte alls.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.access import AccessDecision, AccessRegister, effective_access
from services.approvals import (
    ApprovalRequest,
    ApprovalStore,
    DatabaseApprovalStore,
    MemoryApprovalStore,
)
from services.contract import (
    AgentAccess,
    Operation,
    OperationContext,
    OperationKind,
    OperationRegistry,
    default_registry,
)
from services.errors import (
    AccessDeniedError,
    ApprovalError,
    ConflictError,
    InvalidInputError,
    MissingReasonError,
    ServiceConfigError,
)
from services.events import DatabaseEventLog, EventLog, OperationEvent, default_event_log
from services.rules import ProductRuleCatalog
from services.transaction import SessionFactory, guard_operation, transaction


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


class _ValidationRun(Exception):
    """Avbryter provkörningen av ett förslag så att den rullas tillbaka."""


class ServiceLayer:
    def __init__(
        self,
        registry: OperationRegistry | None = None,
        register: AccessRegister | None = None,
        rules: ProductRuleCatalog | None = None,
        events: EventLog | None = None,
        approvals: ApprovalStore | None = None,
        session_factory: SessionFactory | None = None,
        validation_session_factory: SessionFactory | None = None,
        agent_role: str | None = None,
    ) -> None:
        """
        session_factory: öppnar en databastransaktion per anrop (services.db). Med den
        hamnar händelselogg och godkännandekö i databasen om inget annat anges; utan den
        körs operationerna utan session och loggen hamnar i fil/minne.

        validation_session_factory: betrodd anslutning för provkörning av agentförslag –
        transaktionen rullas alltid tillbaka. Behövs när session_factory är agentens
        begränsade databasroll, som inte får ändra affärsdata (harness.md §5.1).
        Standard: session_factory.

        agent_role: den begränsade databasroll som session_factory ansluter som. Sätts av
        betrodd kod (services.db.agent_service_layer); harness visar verktyg med
        personuppgifter för agenter först när tjänstelagret körs med en sådan roll.
        """
        self.registry = registry if registry is not None else default_registry
        self.register = register if register is not None else AccessRegister.load()
        self.register.validate_against(self.registry)
        self.rules = rules if rules is not None else ProductRuleCatalog()
        if events is None:
            events = DatabaseEventLog(session_factory) if session_factory else default_event_log()
        if approvals is None:
            approvals = DatabaseApprovalStore(session_factory) if session_factory else MemoryApprovalStore()
        if session_factory is None and isinstance(events, DatabaseEventLog):
            raise ServiceConfigError("Händelselogg i databasen kräver session_factory (gemensam transaktion)")
        if session_factory is None and isinstance(approvals, DatabaseApprovalStore):
            raise ServiceConfigError("Godkännandekö i databasen kräver session_factory (gemensam transaktion)")
        if validation_session_factory is not None and session_factory is None:
            raise ServiceConfigError("validation_session_factory kräver session_factory")
        if agent_role is not None and validation_session_factory is None:
            raise ServiceConfigError(
                "En begränsad agentroll kan inte provköra förslag – ange validation_session_factory"
            )
        self.events = events
        self.approvals = approvals
        self.agent_role = agent_role
        self._validation_session_factory = validation_session_factory
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
        ctx = self._with_case(ctx, validated)

        if ctx.actor.is_agent:
            decision = effective_access(op, self.register, self.rules)
            if decision.effective == AgentAccess.HUMAN_ONLY:
                detail = "; ".join(decision.reasons) or "HUMAN_ONLY i registret"
                with transaction(self._session_factory) as tx:
                    self._record(op, ctx, validated, outcome="denied", detail=detail, session=tx.session)
                raise AccessDeniedError(
                    f"Agenten '{ctx.actor.id}' får inte utföra '{op.name}' – endast handläggare"
                    + (f" ({'; '.join(decision.reasons)})" if decision.reasons else ""),
                    operation=op.name,
                    actor_id=ctx.actor.id,
                    reasons=decision.reasons,
                )
            if decision.effective == AgentAccess.APPROVAL:
                return self._propose(op, ctx, validated)

        with transaction(self._session_factory) as tx:
            output = self._call(op, ctx, validated, tx.session)
            if op.kind.changes_state or op.pii:
                # Ett nyskapat ärende har sitt nummer först i resultatet (create_case)
                created = getattr(output, "case_number", None)
                record_ctx = ctx if ctx.case_id or not isinstance(created, str) else replace(ctx, case_id=created)
                self._record(
                    op, record_ctx, validated, outcome="executed", output=output,
                    detail=self._rule_detail(op), session=tx.session,
                )
        return OperationResult(ResultStatus.DONE, op.name, output=output)

    @staticmethod
    def _with_case(ctx: OperationContext, data: BaseModel) -> OperationContext:
        """Ärendet som anropet gäller: kontextens `case_id`, annars indatans `case_number`.

        Så hamnar ärendeoperationerna i händelseloggen med ärendets nummer (B-033: historiken
        är loggen). Anger både kontext och indata ett ärende måste de vara samma.
        """
        case_number = getattr(data, "case_number", None)
        if not isinstance(case_number, str):
            return ctx
        if ctx.case_id is not None and ctx.case_id != case_number:
            raise InvalidInputError(
                f"Anropet gäller ärendet {case_number}, men körs i ärendet {ctx.case_id}"
            )
        return replace(ctx, case_id=case_number)

    def approve(
        self, approval_id: str, ctx: OperationContext, note: str | None = None
    ) -> OperationResult:
        """En handläggare godkänner ett agentförslag – operationen körs mot aktuellt läge.

        Beslutet, ändringen och loggraden sparas i en transaktion. Fallerar
        operationen (t.ex. för att läget har ändrats) rullas allt tillbaka och
        ärendet är fortfarande `pending` – det kan avslås eller godkännas på nytt.
        """
        self._require_human(ctx)
        with transaction(self._session_factory) as tx:
            request = self.approvals.decide(approval_id, "approved", ctx.actor.id, note, tx)
            op = self.registry.get(request.operation)
            validated = self._validate_input(op, request.input)
            run_ctx = replace(
                ctx,
                reason=request.reason,
                run_id=request.run_id,
                case_id=request.case_id or ctx.case_id,
            )
            output = self._call(op, run_ctx, validated, tx.session)
            self._record(
                op, run_ctx, validated, outcome="executed", output=output,
                proposed_by=request.proposed_by, approval_id=request.id,
                detail=self._rule_detail(op), session=tx.session,
            )
        return OperationResult(ResultStatus.DONE, op.name, output=output, approval_id=request.id)

    def reject(self, approval_id: str, ctx: OperationContext, note: str | None = None) -> None:
        """En handläggare avslår ett agentförslag. Beslut och loggrad sparas tillsammans."""
        self._require_human(ctx)
        with transaction(self._session_factory) as tx:
            request = self.approvals.decide(approval_id, "rejected", ctx.actor.id, note, tx)
            op = self.registry.get(request.operation)
            self._record(
                op,
                replace(ctx, reason=request.reason, run_id=request.run_id, case_id=request.case_id or ctx.case_id),
                request.input,
                outcome="rejected",
                proposed_by=request.proposed_by,
                approval_id=request.id,
                detail=note,
                session=tx.session,
            )

    # --- interna hjälpare ---------------------------------------------------

    def _propose(self, op: Operation, ctx: OperationContext, data: BaseModel) -> OperationResult:
        """Lägger ett agentförslag i kön – efter prövning mot aktuellt läge (§6 steg 2)."""
        self._validate_against_state(op, ctx, data)
        request = ApprovalRequest(
            operation=op.name,
            input=data.model_dump(mode="json"),
            reason=ctx.reason,
            proposed_by=ctx.actor.id,
            proposed_by_team=ctx.actor.team,
            run_id=ctx.run_id,
            case_id=ctx.case_id,
        )
        with transaction(self._session_factory) as tx:
            self.approvals.add(request, tx)
            self._record(op, ctx, data, outcome="proposed", approval_id=request.id, session=tx.session)
        return OperationResult(ResultStatus.PENDING_APPROVAL, op.name, approval_id=request.id)

    def _validate_against_state(self, op: Operation, ctx: OperationContext, data: BaseModel) -> None:
        """Provkör en write-operation mot databasen och rullar tillbaka.

        Ett förslag som inte går att genomföra nu (saknat underlag, fel läge,
        dubblett) avvisas direkt i stället för att hamna i kön. `external`
        provkörs aldrig – den påverkar omvärlden. Vid godkännande prövas
        förslaget igen mot det läge som då gäller.
        """
        if op.kind != OperationKind.WRITE or self._session_factory is None:
            return
        try:
            with transaction(self._validation_session_factory or self._session_factory) as tx:
                self._call(op, ctx, data, tx.session)
                raise _ValidationRun
        except _ValidationRun:
            pass

    def _call(self, op: Operation, ctx: OperationContext, data: BaseModel, session: Any) -> BaseModel | None:
        try:
            with guard_operation(session, op.name):
                output = op.func(replace(ctx, session=session), data)
                if isinstance(session, Session):
                    session.flush()  # databasens regler (unikhet, CHECK) prövas inom anropet
        except IntegrityError as exc:
            raise ConflictError(
                f"'{op.name}' krockar med databasens integritetsregler – dubblett eller samtidig ändring. "
                "Inget sparades"
            ) from exc
        if op.output_model is not None and not isinstance(output, op.output_model):
            raise TypeError(
                f"'{op.name}' returnerade {type(output).__name__}, väntade {op.output_model.__name__}"
            )
        return output

    @staticmethod
    def _validate_input(op: Operation, data: BaseModel | dict[str, Any]) -> BaseModel:
        try:
            if isinstance(data, op.input_model):
                return data
            payload = data.model_dump() if isinstance(data, BaseModel) else data
            return op.input_model.model_validate(payload)
        except ValidationError as exc:
            raise InvalidInputError(f"Ogiltig indata till '{op.name}': {exc}") from exc

    @staticmethod
    def _require_human(ctx: OperationContext) -> None:
        if ctx.actor.type != "human":
            raise ApprovalError("Bara en människa kan godkänna eller avslå ett agentförslag")

    def _rule_detail(self, op: Operation) -> str | None:
        """Regelstatus vid verkställigheten – vilken regelversion ändringen vilar på."""
        if not op.kind.changes_state or not op.rules:
            return None
        return self.rules.describe(op.rules)

    def _record(
        self,
        op: Operation,
        ctx: OperationContext,
        data: BaseModel | dict[str, Any],
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
                input=data.model_dump(mode="json") if isinstance(data, BaseModel) else data,
                # Läsresultat loggas inte (kan vara stora och fulla av personuppgifter)
                output=output.model_dump(mode="json") if output is not None and op.kind.changes_state else None,
                detail=detail,
            ),
            session=session,
        )
