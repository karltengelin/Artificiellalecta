"""Varaktiga ärendeuppdrag och skyddad dialog. Endast betrodd harness når tabellerna."""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CaseWork(Base):
    __tablename__ = "case_work"
    __table_args__ = (
        CheckConstraint("mode IN ('assist', 'handle')", name="ck_case_work_mode"),
        CheckConstraint("status IN ('queued','running','waiting_approval','waiting_info','needs_human',"
                        "'completed','cancelled','reconciliation_required')", name="ck_case_work_status"),
        Index("ix_case_work_case_status", "case_number", "status"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    case_number: Mapped[str] = mapped_column(ForeignKey("cases.case_number", ondelete="RESTRICT"), nullable=False)
    submission_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="queued")
    allow_proposals: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    case_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    run_id: Mapped[str | None] = mapped_column(String(100))


class CaseMessage(Base):
    __tablename__ = "case_messages"
    __table_args__ = (
        CheckConstraint("role IN ('human','agent','system')", name="ck_case_messages_role"),
        Index("ix_case_messages_case", "case_number", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    case_number: Mapped[str] = mapped_column(ForeignKey("cases.case_number", ondelete="RESTRICT"), nullable=False)
    work_id: Mapped[str] = mapped_column(ForeignKey("case_work.id", ondelete="RESTRICT"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)


class CaseWorkDay(Base):
    """Reservationsbok per verksamhetsdag i policyns tidszon; ingen återbetalning."""

    __tablename__ = "case_work_days"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0)
