"""Godkännandekön (tjänstelager.md §6).

En agent som anropar en APPROVAL-operation får ett godkännandeärende i
stället för att operationen körs. Med databas ligger kön i tabellen
`approval_requests` (DatabaseApprovalStore) och överlever omstarter; utan
databas i minnet.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

ApprovalStatus = Literal["pending", "approved", "rejected"]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = Field(default_factory=_now)
    operation: str
    input: dict[str, Any]
    reason: str | None = None
    proposed_by: str  # agentens id
    proposed_by_team: str | None = None
    run_id: str | None = None
    case_id: str | None = None
    status: ApprovalStatus = "pending"
    decided_by: str | None = None
    decided_at: str | None = None
    decision_note: str | None = None


class ApprovalStore(Protocol):
    def add(self, request: ApprovalRequest) -> None: ...
    def get(self, approval_id: str) -> ApprovalRequest | None: ...
    def update(self, request: ApprovalRequest) -> None: ...
    def list(self, status: ApprovalStatus | None = None) -> list[ApprovalRequest]: ...


class MemoryApprovalStore:
    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}

    def add(self, request: ApprovalRequest) -> None:
        self._requests[request.id] = request

    def get(self, approval_id: str) -> ApprovalRequest | None:
        return self._requests.get(approval_id)

    def update(self, request: ApprovalRequest) -> None:
        self._requests[request.id] = request

    def list(self, status: ApprovalStatus | None = None) -> list[ApprovalRequest]:
        return [r for r in self._requests.values() if status is None or r.status == status]


def decided(request: ApprovalRequest, status: ApprovalStatus, by: str, note: str | None) -> ApprovalRequest:
    return request.model_copy(
        update={"status": status, "decided_by": by, "decided_at": _now(), "decision_note": note}
    )


class DatabaseApprovalStore:
    """Tabellen approval_requests."""

    def __init__(self, session_factory: Callable[[], AbstractContextManager[Any]]) -> None:
        self._session_factory = session_factory

    def add(self, request: ApprovalRequest) -> None:
        from models import ApprovalRequestRecord

        with self._session_factory() as session:
            session.add(ApprovalRequestRecord(**_to_record(request)))

    def get(self, approval_id: str) -> ApprovalRequest | None:
        from models import ApprovalRequestRecord

        with self._session_factory() as session:
            record = session.get(ApprovalRequestRecord, approval_id)
            return _from_record(record) if record else None

    def update(self, request: ApprovalRequest) -> None:
        from models import ApprovalRequestRecord

        with self._session_factory() as session:
            record = session.get(ApprovalRequestRecord, request.id)
            for key, value in _to_record(request).items():
                setattr(record, key, value)

    def list(self, status: ApprovalStatus | None = None) -> list[ApprovalRequest]:
        from sqlalchemy import select

        from models import ApprovalRequestRecord

        query = select(ApprovalRequestRecord).order_by(ApprovalRequestRecord.created_at)
        if status is not None:
            query = query.where(ApprovalRequestRecord.status == status)
        with self._session_factory() as session:
            return [_from_record(r) for r in session.scalars(query).all()]


def _to_record(request: ApprovalRequest) -> dict[str, Any]:
    data = request.model_dump()
    data["created_at"] = datetime.fromisoformat(data["created_at"])
    data["decided_at"] = datetime.fromisoformat(data["decided_at"]) if data["decided_at"] else None
    return data


def _from_record(r: Any) -> ApprovalRequest:
    return ApprovalRequest(
        id=r.id, created_at=r.created_at.isoformat(timespec="milliseconds"), operation=r.operation,
        input=r.input, reason=r.reason, proposed_by=r.proposed_by, proposed_by_team=r.proposed_by_team,
        run_id=r.run_id, case_id=r.case_id, status=r.status, decided_by=r.decided_by,
        decided_at=r.decided_at.isoformat(timespec="milliseconds") if r.decided_at else None,
        decision_note=r.decision_note,
    )
