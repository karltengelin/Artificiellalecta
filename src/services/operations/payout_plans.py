"""Begäran, uttagsplan, beslut och delning (paket B steg 4, B-047 punkt 3, P1-PENSION-001 §5 och §10).

Fem operationer, alla `HUMAN_ONLY` (PB12, Karls val V8–V9 2026-11-21). Agenter nekas även i
operationen, och de skrivande nekar också systemaktören: agenter och skript föreslår inga planer.

- `register_payout_request` sparar kundens begäran med frist, kanal och aktör och skapar ett ärende
  `payout_request`. Sen, ofullständig, stoppad och blockerad begäran sparas också, med utfallet.
- `preview_payout_plan` räknar planversionen eller delningen för en begäran – G, B, M, omräknade
  garantidelar och kalender – med granskningssumma. Skriver ingenting.
- `decide_payout_plan` binder summan och sparar en ny planversion (start, uppskov, paus, förlängning).
- `split_payout_part` binder summan och sparar delningsbeslutet (PR-ITP1-024).
- `get_payout_part` visar en uttagsdels planer, begäran och delningar med kapital och garanti.

Besluten ändrar inte journalen: ändringsmånadens stängning genomför dem i steg 1 (V2). Logiken ligger
i `services.payout_plans` och den rena beräkningen i `skills.calculation.payout_plan`.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Literal

from pydantic import Field

from models import PayoutRequest
from models.case import CASE_CHANNELS
from services import capital_ledger as cl
from services import payout_plans as plans
from services.contract import OperationContext, OperationKind, operation
from services.errors import AccessDeniedError, BlockedError, ConflictError
from services.operations import common
from services.operations.actuarial_analysis import JsonResult
from services.operations.capital_ledger import _require_journal
from services.premium_month_inputs import HASH, Strict
from services.valuation_extract import month_end
from skills.calculation import actuarial_annuity as aa

RULES = ["PR-ITP1-003", "PR-ITP1-004", "PR-ITP1-005", "PR-ITP1-006", "PR-ITP1-007", "PR-ITP1-008",
         "PR-ITP1-009", "PR-ITP1-025", "UTTAG_GEMENSAMT"]
SPLIT_RULES = ["PR-ITP1-015", "PR-ITP1-024", "UTTAG_GEMENSAMT"]
Channel = Literal[CASE_CHANNELS]  # type: ignore[valid-type]


def _human(ctx: OperationContext, name: str) -> None:
    if ctx.actor.type != "human":
        raise AccessDeniedError("Planer och delningar beslutas av en människa (PB12)", operation=name,
                                actor_id=ctx.actor.id)


def _no_agent(ctx: OperationContext, name: str) -> None:
    if ctx.actor.is_agent:
        raise AccessDeniedError("Uttagsplanerna läses av människa eller betrodd systemkod", operation=name,
                                actor_id=ctx.actor.id)


def _session(ctx: OperationContext):
    session = ctx.require_session()
    _require_journal(session)
    if not plans.plans_present(session):
        raise BlockedError("Uttagsplanerna är inte införda i vald databas – migrate_payout_plans.py först")
    return session


def _request(session, request_id: str) -> PayoutRequest:
    request = session.get(PayoutRequest, uuid.UUID(request_id))
    if request is None:
        raise BlockedError(f"Begäran {request_id} finns inte")
    return request


class PartRef(Strict):
    policy_number: str = Field(min_length=1, max_length=20, description="Försäkringsnumret")
    part_number: int = Field(default=1, ge=1, le=3, description="Uttagsdelens nummer (1–3)")


class RequestInput(PartRef):
    kind: Literal["start", "pause", "extend", "split"] = Field(
        description="start: första start, uppskov eller ändrad framtida start; pause: paus med återstart; "
                    "extend: förlängning eller övergång till livsvarig; split: delning (PR-ITP1-024)")
    content: dict[str, Any] = Field(
        description="start: first_right (ÅÅÅÅ-MM-01), form (lifelong/fixed_term), payments för tidsbegränsad; "
                    "pause: first och resume (ÅÅÅÅ-MM-01); extend: month, form och payments; "
                    "split: month, share (0,1–0,9) och premium_receiver (delnummer)")
    received_date: date = Field(description="Dagen begäran togs emot (Europe/Stockholm)")
    channel: Channel = Field(description="Kanalen begäran kom in genom")
    requester: Literal["insured", "representative"] = "insured"
    authority_verified: bool = Field(default=False, description="Ombudets behörighet verifierad")
    confirms_request_id: str | None = Field(default=None, description="Den sena begäran som denna bekräftar")


class RequestRef(Strict):
    request_id: str = Field(min_length=36, max_length=36, description="Begärans id ur register_payout_request")


class DecideInput(RequestRef):
    reviewed_checksum: str = Field(pattern=HASH, description="review_checksum ur den granskade preview_payout_plan")
    reason: str = Field(min_length=3, max_length=2000, description="Motivering till beslutet")


class PartLookup(PartRef):
    on: date | None = Field(default=None, description="Månadsslut för kapital och garanti; standard senast bokade")


@operation(
    name="register_payout_request",
    description="Registrerar kundens begäran om start, uppskov, paus, förlängning eller delning med mottagningsdag, "
                "kanal och aktör, prövar fristen (sista dagen i månaden före ändringsmånaden) och skapar ett ärende "
                "payout_request. Sen begäran får förslag på nästa möjliga månad; ofullständig får komplettering.",
    kind=OperationKind.WRITE,
    rules=RULES,
    pii=True,
)
def register_payout_request(ctx: OperationContext, data: RequestInput) -> JsonResult:
    _human(ctx, "register_payout_request")
    session = _session(ctx)
    try:
        owner = plans.find_part(session, data.policy_number, data.part_number)
        request, created = plans.register_request(
            session, owner, data.kind, data.content, data.received_date, data.channel, data.requester,
            data.authority_verified, uuid.UUID(data.confirms_request_id) if data.confirms_request_id else None,
            ctx.actor.id)
    except plans.PlanServiceError as exc:
        raise BlockedError(str(exc)) from exc
    return JsonResult(payload={
        "request_id": str(request.id), "created": created, "outcome": request.outcome, "kind": request.kind,
        "change_month": request.change_month.isoformat(), "deadline": request.deadline.isoformat(),
        "proposed_month": request.proposed_month.isoformat() if request.proposed_month else None,
        "missing": request.missing, "case_id": str(request.case_id)})


@operation(
    name="preview_payout_plan",
    description="Räknar planversionen eller delningen för en begäran utan att skriva: ny kalender, omräknade "
                "garantidelar på sin historiska grund, G, B och M på värderingen vid månadsslutet före "
                "ändringsmånaden, med granskningssumma. Utanför beslutsfönstret är beräkningen vägledande.",
    kind=OperationKind.READ,
    rules=RULES,
    pii=True,
)
def preview_payout_plan(ctx: OperationContext, data: RequestRef) -> JsonResult:
    _no_agent(ctx, "preview_payout_plan")
    session = _session(ctx)
    try:
        return JsonResult(payload=plans.preview_request(session, _request(session, data.request_id)))
    except plans.PlanServiceError as exc:
        raise BlockedError(str(exc)) from exc


@operation(
    name="decide_payout_plan",
    description="Beslutar planversionen för en begäran i tid med den granskade summan: originalstart, form, N, "
                "pauser, slutmånad, grunder, faktorer, G, B och M. Ändringsmånadens stängning genomför planen.",
    kind=OperationKind.WRITE,
    rules=RULES,
    pii=True,
)
def decide_payout_plan(ctx: OperationContext, data: DecideInput) -> JsonResult:
    _human(ctx, "decide_payout_plan")
    session = _session(ctx)
    try:
        plan = plans.decide_plan(session, _request(session, data.request_id), data.reviewed_checksum, data.reason,
                                 ctx.actor.id)
    except plans.PlanConflict as exc:
        raise ConflictError(str(exc)) from exc
    except plans.PlanServiceError as exc:
        raise BlockedError(str(exc)) from exc
    return JsonResult(payload={"plan_id": str(plan.id), "version": plan.version, "form": plan.form,
                               "first_right": plan.first_right.isoformat(),
                               "effective_month": plan.effective_month.isoformat(), "m_sek": str(plan.m_sek),
                               "checksum": plan.checksum})


@operation(
    name="split_payout_part",
    description="Beslutar delning av en ej startad uttagsdel med den granskade summan (PR-ITP1-024): andel, "
                "ändringsmånad och primär premiemottagare. Ändringsmånadens stängning skapar den nya delen och "
                "delar kapital och garanti.",
    kind=OperationKind.WRITE,
    rules=SPLIT_RULES,
    pii=True,
)
def split_payout_part(ctx: OperationContext, data: DecideInput) -> JsonResult:
    _human(ctx, "split_payout_part")
    session = _session(ctx)
    try:
        split = plans.decide_split(session, _request(session, data.request_id), data.reviewed_checksum, data.reason,
                                   ctx.actor.id)
    except plans.PlanConflict as exc:
        raise ConflictError(str(exc)) from exc
    except plans.PlanServiceError as exc:
        raise BlockedError(str(exc)) from exc
    return JsonResult(payload={"split_id": str(split.id), "new_part_number": split.new_part_number,
                               "share": str(split.share), "effective_month": split.effective_month.isoformat(),
                               "checksum": split.checksum})


@operation(
    name="get_payout_part",
    description="Visar en uttagsdels planversioner, begäran och delningar med kapital och garanti vid ett "
                "månadsslut.",
    kind=OperationKind.READ,
    rules=RULES,
    pii=True,
)
def get_payout_part(ctx: OperationContext, data: PartLookup) -> JsonResult:
    _no_agent(ctx, "get_payout_part")
    session = ctx.require_session()
    _require_journal(session)
    on = data.on
    if on is None:
        opening = cl.opening_batch(session)
        known = [opening.period_end] if opening else []
        on = max([*known, *cl.closed_month_ends(session)], default=month_end(aa.add_months(common.today(), -1)))
    try:
        owner = plans.find_part(session, data.policy_number, data.part_number)
        return JsonResult(payload=plans.part_view(session, owner, on))
    except plans.PlanServiceError as exc:
        raise BlockedError(str(exc)) from exc
