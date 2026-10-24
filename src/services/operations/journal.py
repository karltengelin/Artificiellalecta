"""Läsoperationer för godkännandekön och händelseloggen (Fas 4, handläggar-UI:t).

Kön och loggen ligger i tjänstelagrets egna tabeller (`approval_requests`,
`operation_events`, tjänstelager.md §6–7). Handläggar-UI:t läser dem här – som
operationer – i stället för direkt, så att läsningen går samma väg som allt
annat. Båda innehåller personuppgifter (förslagens och händelsernas indata) och
loggas därför som läsningar. Att räkna väntande förslag gör det inte.

Händelseloggen per försäkrad: loggen har ingen egen kolumn för berörd person,
så urvalet görs på indata och resultat – personnumret, försäkringsnumren och
premieradernas id – som tjänstelagret redan sparar för varje händelse.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from models import ApprovalRequestRecord, InsuredPerson, OperationEventRecord, Policy, PolicyBenefit, PremiumTransaction
from services.contract import OperationContext, OperationKind, operation
from services.errors import NotFoundError

ApprovalStatus = Literal["pending", "approved", "rejected"]
Outcome = Literal["executed", "proposed", "rejected", "denied"]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


# --- godkännandekön -----------------------------------------------------------------------------


class ApprovalQuery(BaseModel):
    status: ApprovalStatus | None = Field(default="pending", description="Urval på status; None = alla")
    approval_id: str | None = Field(default=None, max_length=32, description="Ett enskilt förslag")
    case_id: str | None = Field(default=None, max_length=100, description="Bara förslag i ett ärende (CASE-NNNNNN)")
    limit: int = Field(default=100, ge=1, le=500)


class ApprovalItem(BaseModel):
    approval_id: str
    created_at: str
    operation: str
    input: dict[str, Any]
    reason: str | None
    proposed_by: str
    proposed_by_team: str | None
    run_id: str | None
    case_id: str | None
    status: str
    decided_by: str | None
    decided_at: str | None
    decision_note: str | None


class ApprovalList(BaseModel):
    requests: list[ApprovalItem] = Field(description="Äldst först bland väntande; senast avgjorda först annars")
    count: int


@operation(
    name="list_approval_requests",
    description=(
        "Visar godkännandekön: agentförslag med operation, indata, motivering och förslagsställare, "
        "och avgjorda förslag med beslut. Urval på status, ärende eller ett enskilt förslag."
    ),
    kind=OperationKind.READ,
    pii=True,
)
def list_approval_requests(ctx: OperationContext, data: ApprovalQuery) -> ApprovalList:
    session = ctx.require_session()
    query = select(ApprovalRequestRecord)
    if data.approval_id is not None:
        query = query.where(ApprovalRequestRecord.id == data.approval_id)
    if data.case_id is not None:
        query = query.where(ApprovalRequestRecord.case_id == data.case_id)
    if data.status is not None:
        query = query.where(ApprovalRequestRecord.status == data.status)
    if data.status == "pending":
        query = query.order_by(ApprovalRequestRecord.created_at)
    else:
        query = query.order_by(
            func.coalesce(ApprovalRequestRecord.decided_at, ApprovalRequestRecord.created_at).desc()
        )
    rows = session.scalars(query.limit(data.limit)).all()
    items = [
        ApprovalItem(
            approval_id=r.id, created_at=_iso(r.created_at), operation=r.operation, input=r.input,
            reason=r.reason, proposed_by=r.proposed_by, proposed_by_team=r.proposed_by_team, run_id=r.run_id,
            case_id=r.case_id, status=r.status, decided_by=r.decided_by, decided_at=_iso(r.decided_at),
            decision_note=r.decision_note,
        )
        for r in rows
    ]
    if data.approval_id is not None and not items:
        raise NotFoundError(f"Okänt godkännandeärende: {data.approval_id}")
    return ApprovalList(requests=items, count=len(items))


class Empty(BaseModel):
    pass


class ApprovalCounts(BaseModel):
    pending: int
    approved: int
    rejected: int


@operation(
    name="count_approval_requests",
    description="Räknar ärendena i godkännandekön per status. Inga personuppgifter.",
    kind=OperationKind.READ,
)
def count_approval_requests(ctx: OperationContext, data: Empty) -> ApprovalCounts:
    session = ctx.require_session()
    rows = dict(
        session.execute(
            select(ApprovalRequestRecord.status, func.count()).group_by(ApprovalRequestRecord.status)
        ).all()
    )
    return ApprovalCounts(
        pending=rows.get("pending", 0), approved=rows.get("approved", 0), rejected=rows.get("rejected", 0)
    )


# --- händelseloggen -----------------------------------------------------------------------------


class EventQuery(BaseModel):
    personal_id_number: str | None = Field(
        default=None, pattern=r"^\d{12}$", description="Bara händelser som rör den försäkrade"
    )
    operation: str | None = Field(default=None, max_length=64, description="Bara en operation")
    outcome: Outcome | None = Field(default=None, description="Bara ett utfall")
    case_id: str | None = Field(default=None, max_length=100, description="Bara händelser i ett ärende (CASE-NNNNNN)")
    include_reads: bool = Field(default=False, description="Ta med läsningar av personuppgifter")
    limit: int = Field(default=200, ge=1, le=1000)


class EventItem(BaseModel):
    event_id: str
    occurred_at: str
    operation: str
    kind: str
    outcome: str
    actor_type: str
    actor_id: str
    actor_team: str | None
    proposed_by: str | None
    approval_id: str | None
    run_id: str | None
    case_id: str | None
    reason: str | None
    rules: list[str]
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    detail: str | None


class EventList(BaseModel):
    events: list[EventItem] = Field(description="Senaste först")
    count: int
    truncated: bool = Field(description="Sant om fler händelser matchar än limit")


@operation(
    name="get_operation_events",
    description=(
        "Visar tjänstelagrets händelselogg – vem som gjorde vad, när, varför och enligt vilka regler – "
        "senaste först. Urval på försäkrad, ärende, operation och utfall; läsningar tas med på begäran."
    ),
    kind=OperationKind.READ,
    pii=True,
)
def get_operation_events(ctx: OperationContext, data: EventQuery) -> EventList:
    session = ctx.require_session()
    E = OperationEventRecord
    query = select(E)
    if not data.include_reads:
        query = query.where(E.kind != OperationKind.READ.value)
    if data.operation is not None:
        query = query.where(E.operation == data.operation)
    if data.outcome is not None:
        query = query.where(E.outcome == data.outcome)
    if data.case_id is not None:
        query = query.where(E.case_id == data.case_id)
    if data.personal_id_number is not None:
        query = query.where(_concerns_person(session, data.personal_id_number))
    rows = session.scalars(query.order_by(E.occurred_at.desc()).limit(data.limit + 1)).all()
    events = [
        EventItem(
            event_id=r.id, occurred_at=_iso(r.occurred_at), operation=r.operation, kind=r.kind, outcome=r.outcome,
            actor_type=r.actor_type, actor_id=r.actor_id, actor_team=r.actor_team, proposed_by=r.proposed_by,
            approval_id=r.approval_id, run_id=r.run_id, case_id=r.case_id, reason=r.reason, rules=r.rules or [],
            input=r.input, output=r.output, detail=r.detail,
        )
        for r in rows[: data.limit]
    ]
    return EventList(events=events, count=len(events), truncated=len(rows) > data.limit)


def _concerns_person(session, personal_id_number: str):
    """Händelser vars indata eller resultat pekar på personen, en av dess försäkringar eller premierader."""
    person = session.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == personal_id_number))
    if person is None:
        raise NotFoundError("Ingen försäkrad med det personnumret")
    E = OperationEventRecord
    policy_numbers = list(session.scalars(select(Policy.policy_number).where(Policy.insured_person_id == person.id)))
    transaction_ids = [
        str(tx_id)
        for tx_id in session.scalars(
            select(PremiumTransaction.id)
            .join(PolicyBenefit, PremiumTransaction.benefit_id == PolicyBenefit.id)
            .join(Policy, PolicyBenefit.policy_id == Policy.id)
            .where(Policy.insured_person_id == person.id)
        )
    ]
    conditions = [E.input["personal_id_number"].as_string() == personal_id_number]
    if policy_numbers:
        conditions.append(E.input["policy_number"].as_string().in_(policy_numbers))
        conditions.append(E.output["policy_number"].as_string().in_(policy_numbers))
    if transaction_ids:
        conditions.append(E.input["transaction_id"].as_string().in_(transaction_ids))
    return or_(*conditions)
