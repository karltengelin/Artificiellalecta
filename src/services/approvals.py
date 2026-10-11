"""Godkännandekön (tjänstelager.md §6).

En agent som anropar en APPROVAL-operation får ett godkännandeärende i
stället för att operationen körs. I T1 ligger kön i minnet; databastabellen
`approval_requests` kommer i T3.
"""

from __future__ import annotations

import uuid
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
