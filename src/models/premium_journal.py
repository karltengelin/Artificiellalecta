"""Syntetiskt mottagnings-/journalförsök P6-MANAD-001.

Oföränderliga källpaket, mottagningskvitton och månadsleverans. Inga referenser
till kapitalförvaltning eller utökade agenträttigheter. Individunderlag stannar
i betrodd kod; godkännandet avser analysens hash och kan aldrig låsa en bas.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")


class PremiumMonthJournal(Base):
    __tablename__ = "premium_month_journals"
    __table_args__ = (CheckConstraint("length(checksum) = 64", name="ck_premium_month_journal_hash"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[dict] = mapped_column(_JSON)
    checksum: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PremiumReceipt(Base):
    __tablename__ = "premium_receipts"
    __table_args__ = (
        UniqueConstraint("journal_id", "source_system", "source_event_id", name="uq_premium_receipt_original"),
        CheckConstraint("length(checksum) = 64", name="ck_premium_receipt_hash"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    journal_id: Mapped[str] = mapped_column(ForeignKey("premium_month_journals.id"), index=True)
    source_system: Mapped[str] = mapped_column(String(64))
    source_event_id: Mapped[str] = mapped_column(String(64))
    received_date: Mapped[date] = mapped_column(Date)
    content: Mapped[dict] = mapped_column(_JSON)
    checksum: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PremiumMonthClose(Base):
    __tablename__ = "premium_month_closes"
    __table_args__ = (
        UniqueConstraint("journal_id", "period_end", name="uq_premium_month_close_period"),
        CheckConstraint("length(checksum) = 64", name="ck_premium_month_close_hash"),
        CheckConstraint("approved_by IS NULL OR approved_at IS NOT NULL", name="ck_premium_month_close_review"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    journal_id: Mapped[str] = mapped_column(ForeignKey("premium_month_journals.id"), index=True)
    period_end: Mapped[date] = mapped_column(Date)
    content: Mapped[dict] = mapped_column(_JSON)
    checksum: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
