"""SQLAlchemy-modell för arbetsgivarens löneunderlagsfil (paket A steg 2, B-046, P1-PREMIE-001 §4.1–4.2).

Se 02_system/databasschema.md §8c. En rad per mottagen fil: arbetsgivare, period,
arbetsgivarens referens, mottagningsdag, innehåll och kontrollsumma samt betrodd
kods valideringsresultat. Innehållet ändras aldrig. Granskningen binder
`review_digest` (kontrollsumman plus valideringen). Godkännande eller avslag sätter
status, beslutsfattare, tidpunkt och – vid godkännande – vad som registrerades.
Skrivs bara av tjänstelagrets import_salary_file, approve_salary_file och
reject_salary_file.

⚠️  Innehållet har personnummer och lön – personuppgifter (B-006).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")

SALARY_FILE_STATUSES = ("received", "approved", "rejected")


class SalaryFile(Base):
    """En löneunderlagsfil från en arbetsgivare för en period."""

    __tablename__ = "salary_files"
    __table_args__ = (
        CheckConstraint("status IN ('received', 'approved', 'rejected')", name="ck_salary_files_status"),
        CheckConstraint("length(checksum) = 64 AND length(review_digest) = 64", name="ck_salary_files_hash"),
        CheckConstraint(
            "(status = 'received' AND decided_by IS NULL AND decided_at IS NULL)"
            " OR (status <> 'received' AND decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_salary_files_decision",
        ),
        CheckConstraint("status <> 'rejected' OR decision_note IS NOT NULL", name="ck_salary_files_reject_note"),
        CheckConstraint(
            "EXTRACT(DAY FROM period_month) = 1", name="ck_salary_files_period_first_of_month"
        ).ddl_if(dialect="postgresql"),
        # Samma regel i testdatabasen (SQLite saknar EXTRACT)
        CheckConstraint(
            "CAST(strftime('%d', period_month) AS INTEGER) = 1", name="ck_salary_files_period_first_of_month"
        ).ddl_if(dialect="sqlite"),
        # Samma referens tas emot en gång per arbetsgivare (P1-PREMIE-001 §4.1)
        Index("uq_salary_files_reference", "employer_id", "file_reference", unique=True),
        Index("ix_salary_files_employer_period", "employer_id", "period_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employers.id", ondelete="RESTRICT"), nullable=False
    )
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    file_reference: Mapped[str] = mapped_column(String(60), nullable=False)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    validation: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    review_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received")
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<SalaryFile {self.file_reference} {self.period_month:%Y-%m} {self.status}>"
