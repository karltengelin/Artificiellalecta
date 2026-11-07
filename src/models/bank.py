"""SQLAlchemy-modeller för bankhändelser och betalningsallokeringar (paket A steg 4, B-046, P1-PREMIE-001 §4.6).

Se 02_system/databasschema.md §8e. En bankhändelse är en inbetalning som banken
rapporterat, sparad en gång per källsystem och bankens händelse-ID. En allokering
fördelar en del av händelsen till en fakturarad eller till avstämningskontot
(`suspense`). Summan av en händelses allokeringar är alltid händelsens belopp.
Allokeringar ändras aldrig: en manuell fördelning från avstämningskontot är en
negativ avstämningspost och nya radallokeringar (PR-ITP1-018).

Mottagningsallokeringarna är sanningskällan för vad som är betalt (PA6).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

ALLOCATION_KINDS = ("invoice_line", "suspense")
#: Fördelningsgrund: OCR-matchning, manuell fördelning eller skäl till avstämningskontot
ALLOCATION_BASES = ("ocr_match", "manual", "overpayment", "unknown_reference", "wrong_payer", "manual_release")


class BankEvent(Base):
    """En inbetalning enligt banken."""

    __tablename__ = "bank_events"
    __table_args__ = (
        CheckConstraint("amount_sek > 0", name="ck_bank_events_amount"),
        CheckConstraint("length(file_checksum) = 64 AND length(content_checksum) = 64", name="ck_bank_events_hash"),
        # Samma händelse sparas en gång per källsystem (P1-PREMIE-001 §4.6)
        Index("uq_bank_events_source", "source_system", "event_id", unique=True),
        Index("ix_bank_events_received", "received_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    file_reference: Mapped[str] = mapped_column(String(60), nullable=False)
    file_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount_sek: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payer_org_number: Mapped[str] = mapped_column(String(10), nullable=False)
    reference: Mapped[str] = mapped_column(String(35), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<BankEvent {self.source_system}:{self.event_id} {self.amount_sek}>"


class PaymentAllocation(Base):
    """En del av en bankhändelse: till en fakturarad eller avstämningskontot."""

    __tablename__ = "payment_allocations"
    __table_args__ = (
        CheckConstraint("kind IN ('invoice_line', 'suspense')", name="ck_payment_allocations_kind"),
        CheckConstraint(
            "basis IN ('ocr_match', 'manual', 'overpayment', 'unknown_reference', 'wrong_payer', 'manual_release')",
            name="ck_payment_allocations_basis",
        ),
        CheckConstraint(
            "(kind = 'invoice_line' AND invoice_line_id IS NOT NULL AND invoice_id IS NOT NULL AND amount_sek > 0)"
            " OR (kind = 'suspense' AND invoice_line_id IS NULL AND amount_sek <> 0)",
            name="ck_payment_allocations_target",
        ),
        Index("uq_payment_allocations_key", "allocation_key", unique=True),
        Index("ix_payment_allocations_event", "bank_event_id"),
        Index("ix_payment_allocations_line", "invoice_line_id"),
        Index("ix_payment_allocations_invoice", "invoice_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bank_events.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=True
    )
    invoice_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoice_lines.id", ondelete="RESTRICT"), nullable=True
    )
    amount_sek: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    basis: Mapped[str] = mapped_column(String(30), nullable=False)
    basis_version: Mapped[str] = mapped_column(String(40), nullable=False)
    allocation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<PaymentAllocation {self.kind} {self.amount_sek}>"
