"""Dispatcher: prövar och kör modellens verktygsanrop (Fas 3b-3, harness.md §3.1, §6.2 steg 5–7).

    dispatcher = Dispatcher(profile, service, run_id="run-1", scope=scope)
    outcome = dispatcher.dispatch(response.tool_calls)
    history.append(Message.from_tool_results(outcome.results))

Samma prövning görs vid varje anrop, även om modellen redan sett verktyget –
listfiltrering ensam räcker inte. Modellen kan hitta på ett namn, skicka fel
personnummer eller återanvända ett anrop som var tillåtet tidigare.

Ordningen för en grupp anrop i samma modellsvar:
  1. Hela gruppen prövas först: dubbla call-id, okänt eller dolt verktyg, okända
     fält, ändrad policy och resursmandat är säkerhetsbrott (DENIED); ett ogiltigt
     värde är ett vanligt fel som modellen kan rätta (INVALID). Båda stoppar gruppen
     innan något körs – alla anrop får ett svar med skälet.
  2. Giltiga anrop körs sekventiellt via tjänstelagret, som agenten. Policyn prövas
     igen före varje anrop.
  3. Första förslaget som väntar på godkännande stoppar resten; de får svaret
     "inte utfört – väntar på godkännande".
  4. Resultatet prövas mot resursmandatet innan det lämnas till modellen.
En grupp är ingen affärstransaktion: ett tidigare utfört anrop står kvar om ett
senare fallerar. Identiteten (Actor.agent med team) kommer från profilen, aldrig
från modellen.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from agents.errors import HarnessError, ScopeError, SkillDeniedError, SkillInputError
from agents.profile import EffectiveProfile, SkillDecision
from agents.scope import ExecutionScope
from agents.skills import ServiceSkill
from ai import ToolCall, ToolResult
from services import Actor, OperationContext, ServiceError, ServiceLayer

GROUP_STOPPED = "Inte utfört: ett annat anrop i samma svar avvisades, så inget i gruppen kördes."
WAITING = "Inte utfört: ett tidigare anrop i samma svar väntar på handläggarens godkännande."


class CallStatus(StrEnum):
    DONE = "done"
    PENDING_APPROVAL = "pending_approval"
    DENIED = "denied"  # nekat av harness före tjänstelagret – säkerhetsgräns
    INVALID = "invalid"  # ogiltigt värde i argumenten – modellen kan rätta; ingenting kört
    ERROR = "error"  # tjänstelagret avböjde (stopp, krock, saknas) – ingenting ändrat
    WITHHELD = "withheld"  # utfört, men resultatet låg utanför scopet och lämnades inte ut
    NOT_EXECUTED = "not_executed"


@dataclass(frozen=True)
class CallOutcome:
    call_id: str
    skill: str
    status: CallStatus
    result: ToolResult
    approval_id: str | None = None
    reasons: tuple[str, ...] = ()
    error_type: str | None = None  # vid INVALID/ERROR: felklassen, t.ex. "BlockedError"


@dataclass(frozen=True)
class DispatchOutcome:
    calls: tuple[CallOutcome, ...]

    @property
    def results(self) -> tuple[ToolResult, ...]:
        """Ett svar per call-id, i modellens ordning."""
        return tuple(c.result for c in self.calls)

    @property
    def pending_approvals(self) -> tuple[str, ...]:
        return tuple(c.approval_id for c in self.calls if c.approval_id)

    @property
    def waiting_approval(self) -> bool:
        return any(c.status == CallStatus.PENDING_APPROVAL for c in self.calls)

    @property
    def denied(self) -> bool:
        return any(c.status == CallStatus.DENIED for c in self.calls)

    @property
    def withheld(self) -> bool:
        return any(c.status == CallStatus.WITHHELD for c in self.calls)

    @property
    def error_types(self) -> tuple[str, ...]:
        """Felklasser för anrop som avvisades som ogiltiga eller avböjdes av tjänstelagret."""
        return tuple(c.error_type for c in self.calls if c.error_type)


@dataclass(frozen=True)
class _Checked:
    call: ToolCall
    skill: ServiceSkill
    action: BaseModel


class Dispatcher:
    def __init__(
        self,
        profile: EffectiveProfile,
        service: ServiceLayer,
        *,
        run_id: str,
        case_id: str | None = None,
        scope: ExecutionScope | None = None,
    ) -> None:
        """`scope` byggs av betrodd kod och måste vara det uppdraget pekar ut."""
        if (scope.ref if scope else None) != profile.execution_scope_ref:
            raise HarnessError(
                "Resursmandatet stämmer inte med uppdraget "
                f"(uppdraget: {profile.execution_scope_ref!r}, scope: {scope.ref if scope else None!r})"
            )
        if scope is not None and scope.case_id is not None and case_id is not None and scope.case_id != case_id:
            raise HarnessError("Resursmandatet gäller ett annat ärende än körningen")
        self.profile = profile
        self.service = service
        self.scope = scope
        self.actor = Actor.agent(profile.agent_id, team=profile.team)
        self.run_id = run_id
        self.case_id = case_id

    def dispatch(self, calls: Sequence[ToolCall]) -> DispatchOutcome:
        checked: list[_Checked | CallOutcome] = []
        seen: set[str] = set()
        for call in calls:
            try:
                if call.id in seen:
                    raise SkillDeniedError(f"Dubbelt call-id '{call.id}'", skill=call.name)
                seen.add(call.id)
                checked.append(self._check(call))
            except SkillInputError as exc:
                checked.append(_denied(call, exc) if exc.security else _invalid(call, exc))
            except (SkillDeniedError, ScopeError) as exc:
                checked.append(_denied(call, exc))

        if any(isinstance(c, CallOutcome) for c in checked):
            return DispatchOutcome(tuple(
                c if isinstance(c, CallOutcome)
                else _outcome(c.call, CallStatus.NOT_EXECUTED, {"status": "not_executed", "message": GROUP_STOPPED})
                for c in checked
            ))

        outcomes: list[CallOutcome] = []
        waiting = False
        for c in checked:
            if waiting:
                outcomes.append(_outcome(c.call, CallStatus.NOT_EXECUTED, {"status": "not_executed", "message": WAITING}))
                continue
            outcome = self._execute(c)
            waiting = outcome.status == CallStatus.PENDING_APPROVAL
            outcomes.append(outcome)
        return DispatchOutcome(tuple(outcomes))

    # --- prövning ----------------------------------------------------------------

    def _check(self, call: ToolCall) -> _Checked:
        skill = self.profile.require(call.name)
        action = skill.parse(call.arguments)
        self._check_policy(self.profile.decision(call.name))
        if self.profile.decision(call.name).pii:
            if self.scope is None:
                raise ScopeError(f"'{call.name}' har personuppgifter men körningen saknar resursmandat")
            self.scope.check_input(call.name, action.data)
        return _Checked(call=call, skill=skill, action=action)

    def _check_policy(self, decision: SkillDecision) -> None:
        """Ingen ny förmåga mitt i en körning, och en indragning gäller direkt (harness.md §3.5)."""
        now = self.service.decision(decision.operation)
        if now.effective != decision.service_level:
            raise SkillDeniedError(
                f"Policyn för '{decision.skill}' har ändrats under körningen "
                f"({decision.service_level.value} → {now.effective.value}) – profilen måste byggas om",
                skill=decision.skill,
                reasons=("policyn ändrad under körningen",),
            )

    # --- körning ----------------------------------------------------------------

    def _execute(self, c: _Checked) -> CallOutcome:
        decision = self.profile.decision(c.call.name)
        try:
            self._check_policy(decision)
        except SkillDeniedError as exc:
            return _denied(c.call, exc)
        ctx = OperationContext(actor=self.actor, run_id=self.run_id, case_id=self.case_id)
        try:
            result = c.skill.execute(self.service, ctx, c.action)
        except ServiceError as exc:
            return _outcome(
                c.call, CallStatus.ERROR, {"status": "error", "message": str(exc)},
                error=True, error_type=type(exc).__name__,
            )

        payload = ServiceSkill.result_payload(result)
        if result.pending:
            return _outcome(c.call, CallStatus.PENDING_APPROVAL, payload, approval_id=result.approval_id)
        if decision.pii:
            try:
                self.scope.check_output(c.call.name, payload)
            except ScopeError as exc:
                return _outcome(
                    c.call, CallStatus.WITHHELD, {"status": "withheld", "message": str(exc)},
                    error=True, reasons=(str(exc),),
                )
        return _outcome(c.call, CallStatus.DONE, payload)


def _denied(call: ToolCall, exc: Exception) -> CallOutcome:
    reasons = tuple(getattr(exc, "reasons", ()) or (str(exc),))
    return _outcome(call, CallStatus.DENIED, {"status": "denied", "message": str(exc)}, error=True, reasons=reasons)


def _invalid(call: ToolCall, exc: SkillInputError) -> CallOutcome:
    return _outcome(
        call, CallStatus.INVALID, {"status": "invalid", "message": str(exc)},
        error=True, error_type="InvalidInput",
    )


def _outcome(
    call: ToolCall,
    status: CallStatus,
    payload: dict[str, Any],
    *,
    error: bool = False,
    approval_id: str | None = None,
    reasons: tuple[str, ...] = (),
    error_type: str | None = None,
) -> CallOutcome:
    content = json.dumps(payload, ensure_ascii=False, default=str)
    return CallOutcome(
        call_id=call.id,
        skill=call.name,
        status=status,
        result=ToolResult(call_id=call.id, content=content, is_error=error),
        approval_id=approval_id,
        reasons=reasons,
        error_type=error_type,
    )
