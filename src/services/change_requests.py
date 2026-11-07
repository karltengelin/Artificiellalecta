"""Manuella ändringsärenden i demo. Ägaren är den autentiserade beställaren."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from sqlalchemy import JSON, Column, MetaData, String, Table, select
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


class ChangeRequest(BaseModel):
    id: UUID
    requested_by: str
    status: Literal["new"]
    created_at: datetime
    draft: ChangeRequestDraft


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
        statement = self._owned(self._requester(actor)).where(change_requests_table.c.id == str(request_id))
        with self._session_factory() as session:
            row = session.execute(statement).mappings().one_or_none()
            return ChangeRequest.model_validate(row) if row is not None else None

    @staticmethod
    def _owned(requested_by: str):
        return select(change_requests_table).where(change_requests_table.c.requested_by == requested_by)

    @staticmethod
    def _requester(actor: Actor) -> str:
        if actor.type != "human":
            raise AccessDeniedError("Ändringsärenden kräver en mänsklig beställare.",
                                    operation="change_requests", actor_id=actor.id)
        return actor.id
