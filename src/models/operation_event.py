"""SQLAlchemy-modell för tjänstelagrets händelselogg (B-028).

Se 02_system/databasschema.md §9b. Append-only – rader uppdateras eller tas
aldrig bort. Skrivs av services.events.DatabaseEventLog.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")


class OperationEventRecord(Base):
    __tablename__ = "operation_events"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('executed', 'proposed', 'rejected', 'denied')",
            name="ck_operation_events_outcome",
        ),
        CheckConstraint(
            "actor_type IN ('human', 'agent', 'system')",
            name="ck_operation_events_actor_type",
        ),
        Index("ix_operation_events_operation_time", "operation", "occurred_at"),
        Index("ix_operation_events_actor_time", "actor_id", "occurred_at"),
        Index("ix_operation_events_run", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(10), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_team: Mapped[str | None] = mapped_column(String(50), nullable=True)
    proposed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    case_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules: Mapped[list[str] | None] = mapped_column(_JSON, nullable=True)
    pii: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    input: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)
    output: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
