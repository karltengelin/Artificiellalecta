"""Händelseloggen (tjänstelager.md §7) – append-only.

Loggas: utförda write/external-operationer, läsningar av personuppgifter,
agentförslag som väntar på godkännande, avslag och nekade agentförsök.
I T1 skrivs loggen till minnet eller en JSONL-fil; databastabellen
`operation_events` kommer i T3.
"""

from __future__ import annotations

import threading
import uuid
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
    def record(self, event: OperationEvent) -> None: ...


class MemoryEventLog:
    def __init__(self) -> None:
        self.events: list[OperationEvent] = []

    def record(self, event: OperationEvent) -> None:
        self.events.append(event)


class JsonlEventLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def record(self, event: OperationEvent) -> None:
        line = event.model_dump_json(exclude_none=True)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


def default_event_log() -> JsonlEventLog:
    return JsonlEventLog(Path(__file__).resolve().parents[2] / "logs" / "operation_events.jsonl")
