"""SQLAlchemy-modeller för fakturor och fakturarader (paket A steg 3, B-046, P1-PREMIE-001 §4.4–4.5).

Se 02_system/databasschema.md §8d. En faktura per arbetsgivare, premieperiod och
fakturering: debetfaktura för ordinarie premie, omdebitering och tillägg, och
kreditfaktura som avräknas separat mot den krediterade fakturan (PR-ITP1-017, -018).
Fakturor ändras aldrig efter skapandet; omfakturering sker med kredit och ny debet.

Varje rad hör till en premiekedja: den ordinarie premieraden (`premium_transaction_id`)
och dess länkade rättelser. `covers` är premieraderna som raden fakturerar. Förmånen
identifierar personen; personnumret står inte på fakturan.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")

INVOICE_TYPES = ("debit", "credit")
#: ordinary = ordinarie premie; rebill = ny debet efter kredit; additional = tillägg på mottagen premie
INVOICE_LINE_TYPES = ("ordinary", "rebill", "additional", "credit")


class Invoice(Base):
    """En faktura till en arbetsgivare för en premieperiod."""

    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("invoice_type IN ('debit', 'credit')", name="ck_invoices_type"),
        CheckConstraint(
            "(invoice_type = 'debit' AND credited_invoice_id IS NULL AND total_sek > 0)"
            " OR (invoice_type = 'credit' AND credited_invoice_id IS NOT NULL AND total_sek < 0)",
            name="ck_invoices_credit",
        ),
        CheckConstraint("due_date >= invoice_date", name="ck_invoices_due"),
        CheckConstraint("length(checksum) = 64", name="ck_invoices_hash"),
        CheckConstraint(
            "EXTRACT(DAY FROM period_month) = 1", name="ck_invoices_period_first_of_month"
        ).ddl_if(dialect="postgresql"),
        # Samma regel i testdatabasen (SQLite saknar EXTRACT)
        CheckConstraint(
            "CAST(strftime('%d', period_month) AS INTEGER) = 1", name="ck_invoices_period_first_of_month"
        ).ddl_if(dialect="sqlite"),
        Index("ix_invoices_employer_period", "employer_id", "period_month"),
        Index("ix_invoices_credited", "credited_invoice_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    employer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employers.id", ondelete="RESTRICT"), nullable=False
    )
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    invoice_type: Mapped[str] = mapped_column(String(10), nullable=False)
    ocr_reference: Mapped[str] = mapped_column(String(25), nullable=False, unique=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_sek: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    credited_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=True
    )
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Invoice {self.invoice_number} {self.invoice_type} {self.total_sek}>"


class InvoiceLineRecord(Base):
    """En fakturarad: ett belopp för en förmån och premieperiod, kopplat till premiekedjan."""

    __tablename__ = "invoice_lines"
    __table_args__ = (
        CheckConstraint(
            "line_type IN ('ordinary', 'rebill', 'additional', 'credit')", name="ck_invoice_lines_type"
        ),
        CheckConstraint(
            "(line_type = 'credit' AND amount_sek < 0 AND credits_line_id IS NOT NULL)"
            " OR (line_type <> 'credit' AND amount_sek > 0 AND credits_line_id IS NULL)",
            name="ck_invoice_lines_credit",
        ),
        CheckConstraint("line_number >= 1", name="ck_invoice_lines_number"),
        Index("uq_invoice_lines_number", "invoice_id", "line_number", unique=True),
        # En rad krediteras högst en gång
        Index("uq_invoice_lines_credits", "credits_line_id", unique=True),
        Index("ix_invoice_lines_premium", "premium_transaction_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    line_type: Mapped[str] = mapped_column(String(20), nullable=False)
    premium_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("premium_transactions.id", ondelete="RESTRICT"), nullable=False
    )
    covers: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    benefit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_benefits.id", ondelete="RESTRICT"), nullable=False
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policies.id", ondelete="RESTRICT"), nullable=False
    )
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    amount_sek: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    credits_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoice_lines.id", ondelete="RESTRICT"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<InvoiceLine {self.line_type} {self.amount_sek}>"
