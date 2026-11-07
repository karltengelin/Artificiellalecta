"""Ändringsärenden i demo. Skrivoperationer använder demomotorns BEGIN IMMEDIATE."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    case,
    select,
)
from sqlalchemy.dialects.sqlite import insert

from services.contract import Actor
from services.db import SessionFactory
from services.errors import AccessDeniedError, ConflictError

# Egen metadata tills projektet får ett separat beslut om andra miljöer.
change_requests_table = Table(
    "change_requests", MetaData(),
    Column("id", String(36), primary_key=True),
    Column("requested_by", String(100), nullable=False, index=True),
    Column("status", String(24), nullable=False),
    Column("created_at", String(32), nullable=False),  # ISO 8601 i UTC
    Column("draft", JSON, nullable=False),
)
change_request_events = Table(
    "change_request_events", change_requests_table.metadata,
    Column("id", Integer, primary_key=True),
    Column("request_id", ForeignKey("change_requests.id"), nullable=False),
    Column("actor_id", String(100), nullable=False),
    Column("occurred_at", String(32), nullable=False),
    Column("action", String(12), nullable=False),
    Column("previous", String(300)),
    Column("current", String(300)),
    Index("ix_change_request_events_request_action_id", "request_id", "action", "id"),
)

ChangeStatus = Literal["new", "in_progress", "waiting_review"]
STATUS_MOVES: dict[ChangeStatus, tuple[ChangeStatus, ...]] = {
    "new": ("in_progress",),
    "in_progress": ("new", "waiting_review"),
    "waiting_review": ("in_progress",),
}
DEVELOPER = Actor.agent("utvecklaragent", "utveckling")
ASSIGNMENT_ACTIONS = ("agent_claim", "human_claim", "takeover", "release")


ShortText = Annotated[str, StringConstraints(min_length=1, max_length=160)]
Notes = Annotated[str, StringConstraints(min_length=1, max_length=1200)]


class ChangeRequestDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: Literal["defect", "rule_change", "improvement"]
    title: ShortText
    need: Annotated[str, StringConstraints(min_length=1, max_length=3000)]
    motivation: Notes | None = None
    affected_system: ShortText | None = None
    acceptance: Notes | None = None
    source_refs: Notes | None = None
    decision_ref: ShortText | None = None
    rule_version: ShortText | None = None
    effective_on: date | None = None

    @field_validator("effective_on", mode="before")
    @classmethod
    def parse_effective_date(cls, value: date | str | None) -> date | None:
        return date.fromisoformat(value) if isinstance(value, str) else value


class ChangeRequestOrigin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    channel: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,59}$")]
    reference: ShortText


class ChangeRequestOrder(ChangeRequestDraft):
    """Komplett beställning från en betrodd ingång som har kontrollerat underlag och mandat."""

    origin: ChangeRequestOrigin
    motivation: Notes
    affected_system: ShortText
    acceptance: Notes


class ChangeRequestEvent(BaseModel):
    actor_id: str
    occurred_at: datetime
    action: Literal["status", "github", "agent_claim", "human_claim", "takeover", "release", "review", "ordered"]
    previous: str | None
    current: str | None


class ChangeRequest(BaseModel):
    id: UUID
    requested_by: str
    status: ChangeStatus
    created_at: datetime
    draft: ChangeRequestDraft
    github_url: str | None = None
    assignee_id: str | None = None
    assignment: Literal["agent_claim", "human_claim", "takeover", "release"] | None = None
    agent_run_id: UUID | None = None
    history: tuple[ChangeRequestEvent, ...] = ()

    @property
    def origin(self) -> ChangeRequestOrigin | None:
        for event in self.history:
            if event.action == "ordered":
                return ChangeRequestOrigin(channel=event.previous, reference=event.current)
        return None

    @property
    def review(self) -> ReviewReferences | None:
        if self.status == "waiting_review" and self.history:
            event = next((event for event in self.history if event.action == "review"), None)
            if event is not None:
                return ReviewReferences(code_ref=event.previous, test_ref=event.current)
        return None


EvidenceRef = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class ReviewReferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code_ref: EvidenceRef
    test_ref: EvidenceRef


class ChangeQueueRun(BaseModel):
    """Mandat som den betrodda startaren utfärdar, utanför kodarens miljö."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor: Actor
    run_id: UUID
    requested_by: str
    allowed_requests: frozenset[UUID]


class ChangeRequests:
    def __init__(self, session_factory: SessionFactory):
        self._session_factory = session_factory

    def create(self, actor: Actor, request_id: UUID, draft: ChangeRequestDraft) -> ChangeRequest:
        return self._create(actor, request_id, draft.model_dump(mode="json"))

    def submit_order(self, actor: Actor, order: ChangeRequestOrder) -> ChangeRequest:
        """Registrera beställningen under den ansvariga operatörens identitet.

        Kanalen äger sin stabila referens och kontrollerar vem som får beställa.
        Omförsök med samma ursprung och underlag behåller ärendets status och ansvar.
        """
        origin = order.origin
        request_id = uuid5(NAMESPACE_URL, f"artificiellalecta/change-requests/{origin.channel}/{origin.reference}")
        return self._create(actor, request_id, order.model_dump(mode="json", exclude={"origin"}), origin)

    def _create(self, actor: Actor, request_id: UUID, draft: dict,
                origin: ChangeRequestOrigin | None = None) -> ChangeRequest:
        requested_by = self._requester(actor)
        values = {
            "id": str(request_id), "requested_by": requested_by, "status": "new",
            "created_at": datetime.now(UTC).isoformat(), "draft": draft,
        }
        table = change_requests_table
        with self._session_factory() as session:
            inserted = session.execute(insert(table).values(values).on_conflict_do_nothing(index_elements=[table.c.id]))
            row = session.execute(self._owned(requested_by).where(table.c.id == str(request_id))).mappings().one_or_none()
            if row is None or row["draft"] != draft:
                if origin is not None:
                    raise ConflictError("Beställningens ursprung är redan bundet till ett annat underlag eller en annan beställare.")
                raise ConflictError("Registreringen har redan använts. Öppna ett nytt formulär.")
            if origin is not None:
                if inserted.rowcount:
                    self._record(session, request_id, requested_by, "ordered", origin.channel, origin.reference)
                else:
                    events = change_request_events
                    saved = session.scalar(select(events.c.id).where(
                        events.c.request_id == str(request_id), events.c.action == "ordered",
                        events.c.previous == origin.channel, events.c.current == origin.reference,
                    ))
                    if saved is None:
                        raise ConflictError("Det befintliga ärendet saknar beställningens ursprung.")
            return ChangeRequest.model_validate(row)

    def list(self, actor: Actor) -> list[ChangeRequest]:
        table = change_requests_table
        statement = self._owned(self._requester(actor)).order_by(table.c.created_at.desc(), table.c.id.desc())
        with self._session_factory() as session:
            return [ChangeRequest.model_validate(row) for row in session.execute(statement).mappings()]

    def list_new(self, run: ChangeQueueRun) -> list[ChangeRequest]:
        table = change_requests_table
        statement = self._scoped(run).where(table.c.status == "new").order_by(table.c.created_at, table.c.id)
        with self._session_factory() as session:
            return [ChangeRequest.model_validate(row) for row in session.execute(statement).mappings()]

    def get(self, actor: Actor, request_id: UUID) -> ChangeRequest | None:
        with self._session_factory() as session:
            row = self._find(session, self._requester(actor), request_id)
            if row is None:
                return None
            events = change_request_events
            history = session.execute(
                select(events).where(events.c.request_id == str(request_id)).order_by(events.c.id.desc())
            ).mappings()
            return ChangeRequest.model_validate({**row, "history": tuple(history)})

    def claim(self, run: ChangeQueueRun, request_id: UUID) -> ChangeRequest:
        with self._session_factory() as session:
            row = self._agent_row(session, run, request_id)
            if row["status"] != "new":
                raise ConflictError("Ändringsärendet har redan tagits.")
            events = change_request_events
            used = select(events.c.id).where(events.c.action == "agent_claim",
                                             events.c.previous == str(run.run_id)).exists()
            if session.scalar(select(used)):
                raise ConflictError("Agentkörningen har redan tagit ett ändringsärende.")
            self._assign(session, request_id, run.actor.id, "agent_claim", str(run.run_id))
            self._set_status(session, request_id, run.actor.id, "new", "in_progress")
            return ChangeRequest.model_validate(self._agent_row(session, run, request_id))

    def check_claim(self, run: ChangeQueueRun, request_id: UUID) -> None:
        with self._session_factory() as session:
            self._require_claim(self._agent_row(session, run, request_id), run)

    def handoff(self, run: ChangeQueueRun, request_id: UUID, review: ReviewReferences) -> None:
        with self._session_factory() as session:
            row = self._agent_row(session, run, request_id)
            if row["status"] == "waiting_review" and row["agent_run_id"] == str(run.run_id):
                self._check_review_retry(session, request_id, review)
                return
            self._require_claim(row, run)
            self._submit_review(session, request_id, run.actor.id, review)

    def takeover(self, actor: Actor, request_id: UUID, expected_run: UUID) -> bool:
        requested_by = self._requester(actor)
        with self._session_factory() as session:
            row = self._find(session, requested_by, request_id)
            if row is None:
                return False
            if row["assignment"] == "takeover" and row["assignment_ref"] == str(expected_run):
                return True
            if row["agent_run_id"] != str(expected_run):
                raise ConflictError("Ärendet har bytt ansvarig. Öppna det igen och kontrollera historiken.")
            self._assign(session, request_id, requested_by, "takeover", str(expected_run))
            return True

    def move(self, actor: Actor, request_id: UUID, previous: str, status: str,
             review: ReviewReferences | None = None) -> bool:
        requested_by = self._requester(actor)
        with self._session_factory() as session:
            row = self._find(session, requested_by, request_id)
            if row is None:
                return False
            if status not in STATUS_MOVES.get(previous, ()):
                raise ValueError("Välj ett angränsande steg i ärendets arbetsflöde.")
            if row["agent_run_id"] is not None:
                raise ConflictError("Ta över ärendet innan du flyttar det.")
            if row["status"] == status:
                if status == "waiting_review":
                    self._check_review_retry(session, request_id, review)
                return True
            if row["status"] != previous:
                raise ConflictError("Ärendet har flyttats. Öppna ärendet igen och kontrollera status.")
            if status == "waiting_review":
                if review is None:
                    raise ValueError("Ange referenser till kodändringen och testbeviset.")
                if row["assignee_id"] is None:
                    self._assign(session, request_id, requested_by, "human_claim")
                self._submit_review(session, request_id, requested_by, review)
                return True
            if status == "new":
                self._record(session, request_id, requested_by, "release", row["assignee_id"], None)
            elif row["assignee_id"] is None:
                self._assign(session, request_id, requested_by, "human_claim")
            self._set_status(session, request_id, requested_by, previous, status)
            return True

    def link(self, actor: Actor, request_id: UUID, previous: str | None, url: str | None) -> bool:
        requested_by = self._requester(actor)
        with self._session_factory() as session:
            row = self._find(session, requested_by, request_id)
            if row is None:
                return False
            if row["github_url"] == url:
                return True
            if row["github_url"] != previous:
                raise ConflictError("GitHub-länken har ändrats. Öppna ärendet igen och kontrollera länken.")
            self._record(session, request_id, requested_by, "github", previous, url)
            return True

    @staticmethod
    def _record(session, request_id: UUID, actor_id: str, action: str, previous: str | None, current: str | None):
        session.execute(change_request_events.insert().values(
            request_id=str(request_id), actor_id=actor_id, occurred_at=datetime.now(UTC).isoformat(),
            action=action, previous=previous, current=current,
        ))

    def _find(self, session, requested_by: str, request_id: UUID):
        statement = self._owned(requested_by).where(change_requests_table.c.id == str(request_id))
        return session.execute(statement).mappings().one_or_none()

    def _agent_row(self, session, run: ChangeQueueRun, request_id: UUID):
        statement = self._scoped(run).where(change_requests_table.c.id == str(request_id))
        row = session.execute(statement).mappings().one_or_none()
        if row is None:
            self._deny(run)
        return row

    def _scoped(self, run: ChangeQueueRun):
        if run.actor != DEVELOPER:
            self._deny(run)
        table = change_requests_table
        return self._owned(run.requested_by).where(table.c.id.in_(str(value) for value in run.allowed_requests))

    @staticmethod
    def _deny(run: ChangeQueueRun):
        raise AccessDeniedError("Ändringsärendet ligger utanför körningens mandat.",
                                operation="change_requests", actor_id=run.actor.id)

    @staticmethod
    def _require_claim(row, run: ChangeQueueRun) -> None:
        if row["status"] != "in_progress" or row["agent_run_id"] != str(run.run_id):
            raise ConflictError("Körningen ansvarar inte längre för ändringsärendet.")

    def _assign(self, session, request_id: UUID, actor_id: str, action: str, run_ref: str | None = None):
        self._record(session, request_id, actor_id, action, run_ref, actor_id)

    def _set_status(self, session, request_id: UUID, actor_id: str, previous: str, status: str):
        table = change_requests_table
        session.execute(table.update().where(table.c.id == str(request_id)).values(status=status))
        self._record(session, request_id, actor_id, "status", previous, status)

    def _submit_review(self, session, request_id: UUID, actor_id: str, review: ReviewReferences):
        self._record(session, request_id, actor_id, "review", review.code_ref, review.test_ref)
        self._set_status(session, request_id, actor_id, "in_progress", "waiting_review")

    @staticmethod
    def _check_review_retry(session, request_id: UUID, review: ReviewReferences | None):
        events = change_request_events
        saved = session.execute(select(events.c.previous, events.c.current)
                                .where(events.c.request_id == str(request_id), events.c.action == "review")
                                .order_by(events.c.id.desc()).limit(1)).one_or_none()
        refs = (review.code_ref, review.test_ref) if review is not None else None
        if saved != refs:
            raise ConflictError("Ärendet har redan lämnats med ett annat granskningsunderlag.")

    @staticmethod
    def _owned(requested_by: str):
        table = change_requests_table
        events = change_request_events
        github_url = (select(events.c.current)
                      .where(events.c.request_id == table.c.id, events.c.action == "github")
                      .order_by(events.c.id.desc()).limit(1).scalar_subquery())
        assignment = events.alias("assignment")
        assignment_id = (select(events.c.id)
                         .where(events.c.request_id == table.c.id, events.c.action.in_(ASSIGNMENT_ACTIONS))
                         .order_by(events.c.id.desc()).limit(1).correlate(table).scalar_subquery())
        return (select(table, github_url.label("github_url"), assignment.c.current.label("assignee_id"),
                       assignment.c.action.label("assignment"), assignment.c.previous.label("assignment_ref"),
                       case((assignment.c.action == "agent_claim", assignment.c.previous), else_=None)
                       .label("agent_run_id"))
                .select_from(table.outerjoin(assignment, assignment.c.id == assignment_id))
                .where(table.c.requested_by == requested_by))

    @staticmethod
    def _requester(actor: Actor) -> str:
        if actor.type != "human":
            raise AccessDeniedError("Ändringsärenden kräver en mänsklig beställare.",
                                    operation="change_requests", actor_id=actor.id)
        return actor.id
