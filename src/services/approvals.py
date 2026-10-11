"""Godkännandekön (tjänstelager.md §6).

En agent som anropar en APPROVAL-operation får ett godkännandeärende i
stället för att operationen körs. Med databas ligger kön i tabellen
`approval_requests` (DatabaseApprovalStore) och överlever omstarter; utan
databas i minnet.

Ett ärende avgörs med `decide()`: ett atomiskt byte från `pending` till
`approved`/`rejected`. I databasen är det en villkorlig UPDATE (`… WHERE
status = 'pending'`) i anropets transaktion – av två samtidiga beslut kan
bara ett lyckas, och fallerar operationen efteråt rullas beslutet tillbaka
tillsammans med ändringen och loggraden.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from services.errors import ApprovalError
from services.transaction import Transaction

ApprovalStatus = Literal["pending", "approved", "rejected"]
Decision = Literal["approved", "rejected"]


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
    def add(self, request: ApprovalRequest, tx: Transaction | None = None) -> None: ...
    def decide(
        self, approval_id: str, status: Decision, decided_by: str, note: str | None,
        tx: Transaction | None = None,
    ) -> ApprovalRequest: ...
    def get(self, approval_id: str) -> ApprovalRequest | None: ...
    def list(self, status: ApprovalStatus | None = None) -> list[ApprovalRequest]: ...


def _not_pending(approval_id: str, current: ApprovalRequest | None) -> ApprovalError:
    if current is None:
        return ApprovalError(f"Okänt godkännandeärende: {approval_id}")
    return ApprovalError(f"Ärendet {approval_id} är redan {current.status}")


class MemoryApprovalStore:
    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}
        self._lock = threading.Lock()

    def add(self, request: ApprovalRequest, tx: Transaction | None = None) -> None:
        with self._lock:
            self._requests[request.id] = request
        if tx is not None:
            tx.on_rollback(lambda: self._requests.pop(request.id, None))

    def decide(
        self, approval_id: str, status: Decision, decided_by: str, note: str | None,
        tx: Transaction | None = None,
    ) -> ApprovalRequest:
        with self._lock:
            current = self._requests.get(approval_id)
            if current is None or current.status != "pending":
                raise _not_pending(approval_id, current)
            decided = current.model_copy(
                update={"status": status, "decided_by": decided_by, "decided_at": _now(), "decision_note": note}
            )
            self._requests[approval_id] = decided
        if tx is not None:
            tx.on_rollback(lambda: self._requests.__setitem__(approval_id, current))
        return decided

    def get(self, approval_id: str) -> ApprovalRequest | None:
        return self._requests.get(approval_id)

    def list(self, status: ApprovalStatus | None = None) -> list[ApprovalRequest]:
        return [r for r in self._requests.values() if status is None or r.status == status]


class DatabaseApprovalStore:
    """Tabellen approval_requests. Skriver i anropets transaktion när en sådan ges."""

    def __init__(self, session_factory: Callable[[], AbstractContextManager[Any]]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session(self, tx: Transaction | None) -> Iterator[Any]:
        if tx is not None and tx.session is not None:
            yield tx.session
        else:
            with self._session_factory() as session:
                yield session

    def add(self, request: ApprovalRequest, tx: Transaction | None = None) -> None:
        from models import ApprovalRequestRecord

        with self._session(tx) as session:
            session.add(ApprovalRequestRecord(**_to_record(request)))
            session.flush()

    def decide(
        self, approval_id: str, status: Decision, decided_by: str, note: str | None,
        tx: Transaction | None = None,
    ) -> ApprovalRequest:
        from sqlalchemy import select, update

        from models import ApprovalRequestRecord

        with self._session(tx) as session:
            claimed = session.execute(
                update(ApprovalRequestRecord)
                .where(ApprovalRequestRecord.id == approval_id, ApprovalRequestRecord.status == "pending")
                .values(status=status, decided_by=decided_by, decided_at=datetime.now(UTC), decision_note=note)
                .execution_options(synchronize_session=False)
            ).rowcount
            record = session.scalars(
                select(ApprovalRequestRecord)
                .where(ApprovalRequestRecord.id == approval_id)
                .execution_options(populate_existing=True)
            ).first()
            if claimed != 1:
                raise _not_pending(approval_id, _from_record(record) if record else None)
            return _from_record(record)

    def get(self, approval_id: str) -> ApprovalRequest | None:
        from models import ApprovalRequestRecord

        with self._session_factory() as session:
            record = session.get(ApprovalRequestRecord, approval_id)
            return _from_record(record) if record else None

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
