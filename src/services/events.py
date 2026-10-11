"""Händelseloggen (tjänstelager.md §7) – append-only.

Loggas: utförda write/external-operationer, läsningar av personuppgifter,
agentförslag som väntar på godkännande, avslag och nekade agentförsök.
Med databas skrivs loggen till tabellen `operation_events` i samma
transaktion som operationen (DatabaseEventLog). Utan databas – i minnet
eller till en JSONL-fil.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

EventOutcome = Literal["executed", "proposed", "rejected", "denied"]


class OperationEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="milliseconds")
    )
    operation: str
    kind: str
    outcome: EventOutcome
    actor_type: str
    actor_id: str
    actor_team: str | None = None
    proposed_by: str | None = None  # agent som föreslog (vid godkänt förslag)
    approval_id: str | None = None
    run_id: str | None = None
    case_id: str | None = None
    reason: str | None = None
    rules: list[str] = Field(default_factory=list)
    pii: bool = False
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    detail: str | None = None  # t.ex. skäl till nekad åtkomst


class EventLog(Protocol):
    def record(self, event: OperationEvent, session: Any = None) -> None:
        """session: operationens databassession, när händelsen hör till en körning."""


class MemoryEventLog:
    def __init__(self) -> None:
        self.events: list[OperationEvent] = []

    def record(self, event: OperationEvent, session: Any = None) -> None:
        self.events.append(event)


class JsonlEventLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def record(self, event: OperationEvent, session: Any = None) -> None:
        line = event.model_dump_json(exclude_none=True)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


class DatabaseEventLog:
    """Tabellen operation_events. Använder operationens session när den finns –
    då kan en ändring aldrig sparas utan sin loggrad."""

    def __init__(self, session_factory: Callable[[], AbstractContextManager[Any]]) -> None:
        self._session_factory = session_factory

    def record(self, event: OperationEvent, session: Any = None) -> None:
        from models import OperationEventRecord

        data = event.model_dump()
        data["occurred_at"] = datetime.fromisoformat(data.pop("timestamp"))
        if session is not None:
            session.add(OperationEventRecord(**data))
            return
        with self._session_factory() as own:
            own.add(OperationEventRecord(**data))

    def list(self) -> list[OperationEvent]:
        from sqlalchemy import select

        from models import OperationEventRecord

        with self._session_factory() as session:
            rows = session.scalars(select(OperationEventRecord).order_by(OperationEventRecord.occurred_at)).all()
            return [_event_from_record(r) for r in rows]


def _event_from_record(r: Any) -> OperationEvent:
    return OperationEvent(
        id=r.id, timestamp=r.occurred_at.isoformat(timespec="milliseconds"), operation=r.operation,
        kind=r.kind, outcome=r.outcome, actor_type=r.actor_type, actor_id=r.actor_id,
        actor_team=r.actor_team, proposed_by=r.proposed_by, approval_id=r.approval_id,
        run_id=r.run_id, case_id=r.case_id, reason=r.reason, rules=r.rules or [], pii=r.pii,
        input=r.input, output=r.output, detail=r.detail,
    )


def default_event_log() -> JsonlEventLog:
    return JsonlEventLog(Path(__file__).resolve().parents[2] / "logs" / "operation_events.jsonl")
