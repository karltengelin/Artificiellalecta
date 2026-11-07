"""Manuella ändringsärenden i demo. Ägaren är den autentiserade beställaren."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

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


class ChangeRequestEvent(BaseModel):
    actor_id: str
    occurred_at: datetime
    action: Literal["status", "github"]
    previous: str | None
    current: str | None


class ChangeRequest(BaseModel):
    id: UUID
    requested_by: str
    status: ChangeStatus
    created_at: datetime
    draft: ChangeRequestDraft
    github_url: str | None = None
    history: tuple[ChangeRequestEvent, ...] = ()


class ChangeRequests:
    def __init__(self, session_factory: SessionFactory):
        self._session_factory = session_factory

    def create(self, actor: Actor, request_id: UUID, draft: ChangeRequestDraft) -> ChangeRequest:
        requested_by = self._requester(actor)
        values = {
            "id": str(request_id), "requested_by": requested_by, "status": "new",
            "created_at": datetime.now(UTC).isoformat(), "draft": draft.model_dump(mode="json"),
        }
        table = change_requests_table
        with self._session_factory() as session:
            session.execute(insert(table).values(values).on_conflict_do_nothing(index_elements=[table.c.id]))
            row = session.execute(self._owned(requested_by).where(table.c.id == str(request_id))).mappings().one_or_none()
            if row is None or row["draft"] != values["draft"]:
                raise ConflictError("Registreringen har redan använts. Öppna ett nytt formulär.")
            return ChangeRequest.model_validate(row)

    def list(self, actor: Actor) -> list[ChangeRequest]:
        table = change_requests_table
        statement = self._owned(self._requester(actor)).order_by(table.c.created_at.desc(), table.c.id.desc())
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

    def move(self, actor: Actor, request_id: UUID, previous: str, status: str) -> bool:
        requested_by = self._requester(actor)
        with self._session_factory() as session:
            row = self._find(session, requested_by, request_id)
            if row is None:
                return False
            if status not in STATUS_MOVES.get(previous, ()):
                raise ValueError("Välj ett angränsande steg i ärendets arbetsflöde.")
            if row["status"] == status:
                return True
            if row["status"] != previous:
                raise ConflictError("Ärendet har flyttats. Öppna ärendet igen och kontrollera status.")
            table = change_requests_table
            session.execute(table.update().where(table.c.id == str(request_id)).values(status=status))
            self._record(session, request_id, requested_by, "status", previous, status)
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

    @staticmethod
    def _owned(requested_by: str):
        table = change_requests_table
        events = change_request_events
        github_url = (select(events.c.current)
                      .where(events.c.request_id == table.c.id, events.c.action == "github")
                      .order_by(events.c.id.desc()).limit(1).scalar_subquery())
        return select(table, github_url.label("github_url")).where(table.c.requested_by == requested_by)

    @staticmethod
    def _requester(actor: Actor) -> str:
        if actor.type != "human":
            raise AccessDeniedError("Ändringsärenden kräver en mänsklig beställare.",
                                    operation="change_requests", actor_id=actor.id)
        return actor.id
