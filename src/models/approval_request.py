"""SQLAlchemy-modell för tjänstelagrets godkännandekö (B-028).

Se 02_system/databasschema.md §9c. Skrivs av services.approvals.DatabaseApprovalStore.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ApprovalRequestRecord(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_approval_requests_status",
        ),
        Index("ix_approval_requests_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_by: Mapped[str] = mapped_column(String(100), nullable=False)
    proposed_by_team: Mapped[str | None] = mapped_column(String(50), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    case_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
