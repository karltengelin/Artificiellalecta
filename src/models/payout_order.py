"""SQLAlchemy-modeller för skattestatus, utbetalningskonto, bankuppdrag och bankkvitton (paket B steg 6, B-054).

Se 02_system/databasschema.md §7f och designstoppet P1-PENSION-001 §8 (PB7, PB8), Karls val X1–X13
2026-11-24. Raderna läggs bara till. Anspråket i `pension_claims` ändras aldrig (W1): betalningsförloppet
står i egna rader som pekar på det, och anspråkets betalningsläge härleds ur dem.

- `tax_statuses`: skattestatus per person och skatteår i en versionskedja (X5). Individuellt beslut,
  sidoinkomst, huvudinkomst eller SINK (PR-ITP1-026).
- `payout_accounts`: utbetalningskonto per person i en versionskedja, med verifiering (X6).
- `payout_files`: bankfilen för en utförandedag, med kontrollsumma och godkännande (X7). Läget går bara
  framåt: förberedd → godkänd, eller förberedd → ersatt.
- `payout_orders`: ett bankuppdrag per mottagare i filen, med kontoversion, skattestatusversion, skatteår,
  brutto, skatt och netto (X3).
- `payout_order_lines`: en rad per anspråk och försök (X1, X8). Ett nytt försök är en ny rad med samma
  anspråk och nästa försöksnummer, aldrig ett nytt anspråk.
- `payout_receipts`: bankens kvitton per uppdrag, en gång per källsystem och kvitto-id (X8).

Agentrollerna har inga rättigheter på tabellerna (P1-PENSION-001 §12, X12).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

#: Skattestatusens slag (PR-ITP1-026 p. 1–4, X5)
TAX_KINDS = ("individual_decision", "side_income", "main_income", "sink")
#: Bankfilens läge (X7)
FILE_STATUSES = ("prepared", "approved", "superseded")
#: Bankens utfall för ett uppdrag (X8)
RECEIPT_OUTCOMES = ("executed", "rejected", "returned", "unknown")
#: Hur skatten bestämdes på uppdraget (X3)
TAX_METHODS = ("percent", "fixed", "below_100", "below_1000")

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
_MONEY = Numeric(14, 2)
_RATE = Numeric(7, 4)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class TaxStatus(Base):
    """En version av en persons skattestatus för ett skatteår (PR-ITP1-026, X5)."""

    __tablename__ = "tax_statuses"
    __table_args__ = (
        UniqueConstraint("insured_person_id", "tax_year", "version", name="uq_tax_statuses_version"),
        UniqueConstraint("supersedes_id", name="uq_tax_statuses_supersedes"),
        CheckConstraint(_in("kind", TAX_KINDS), name="ck_tax_statuses_kind"),
        CheckConstraint("version >= 1 AND tax_year >= 2000", name="ck_tax_statuses_version"),
        CheckConstraint("(version = 1) = (supersedes_id IS NULL)", name="ck_tax_statuses_chain"),
        CheckConstraint("rate IS NULL OR (rate >= 0 AND rate <= 1)", name="ck_tax_statuses_rate"),
        CheckConstraint("fixed_amount_sek IS NULL OR fixed_amount_sek >= 0", name="ck_tax_statuses_fixed"),
        # Sidoinkomst minst 30 %; SINK och individuellt beslut kräver beslutsreferens; huvudinkomst kräver tabell
        CheckConstraint("kind <> 'side_income' OR (rate IS NOT NULL AND rate >= 0.30)", name="ck_tax_statuses_side"),
        CheckConstraint("kind NOT IN ('sink', 'individual_decision') OR decision_ref IS NOT NULL",
                        name="ck_tax_statuses_decision"),
        CheckConstraint("kind <> 'sink' OR rate IS NOT NULL", name="ck_tax_statuses_sink"),
        CheckConstraint("kind <> 'individual_decision' OR (rate IS NULL) <> (fixed_amount_sek IS NULL)",
                        name="ck_tax_statuses_individual"),
        CheckConstraint("kind <> 'main_income' OR (table_number IS NOT NULL AND table_column IS NOT NULL)",
                        name="ck_tax_statuses_main"),
        CheckConstraint("length(checksum) = 64", name="ck_tax_statuses_checksum"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    insured_person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insured_persons.id", ondelete="RESTRICT"), nullable=False, index=True)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tax_statuses.id", ondelete="RESTRICT"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    #: Procentsatsen: sidoinkomstens avdrag (minst 30 %), SINK-beslutets sats eller beslutets procent
    rate: Mapped[Decimal | None] = mapped_column(_RATE, nullable=True)
    #: Individuellt beslut med fast belopp per utbetalning
    fixed_amount_sek: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    #: Huvudinkomst: skattetabell och pensionskolumn, och förhöjt avdrag enligt SFL 11 kap. 21 §
    table_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    table_column: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raised_deduction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decision_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Första utbetalningsdag versionen gäller för (frivilligt högre avdrag: två veckor efter begäran)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<TaxStatus {self.tax_year} v{self.version} {self.kind}>"


class PayoutAccount(Base):
    """En version av en persons utbetalningskonto, verifierat eller inte (PR-ITP1-026, X6)."""

    __tablename__ = "payout_accounts"
    __table_args__ = (
        UniqueConstraint("insured_person_id", "version", name="uq_payout_accounts_version"),
        UniqueConstraint("supersedes_id", name="uq_payout_accounts_supersedes"),
        CheckConstraint("version >= 1", name="ck_payout_accounts_version"),
        CheckConstraint("(version = 1) = (supersedes_id IS NULL)", name="ck_payout_accounts_chain"),
        CheckConstraint("NOT verified OR (verification_method IS NOT NULL AND verification_ref IS NOT NULL)",
                        name="ck_payout_accounts_verified"),
        CheckConstraint("length(checksum) = 64", name="ck_payout_accounts_checksum"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    insured_person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insured_persons.id", ondelete="RESTRICT"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_accounts.id", ondelete="RESTRICT"), nullable=True)
    clearing_number: Mapped[str] = mapped_column(String(5), nullable=False)
    account_number: Mapped[str] = mapped_column(String(20), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(60), nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verification_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verification_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<PayoutAccount v{self.version} {'verifierat' if self.verified else 'overifierat'}>"


class PayoutFile(Base):
    """Bankfilen för en utförandedag: uppdragen per mottagare, kontrollsumma och godkännande (X7)."""

    __tablename__ = "payout_files"
    __table_args__ = (
        UniqueConstraint("checksum", name="uq_payout_files_checksum"),
        UniqueConstraint("file_reference", name="uq_payout_files_reference"),
        # En fil ersätts av högst en nyare fil, och högst en fil är förberedd åt gången (X7)
        UniqueConstraint("supersedes_id", name="uq_payout_files_supersedes"),
        Index("uq_payout_files_prepared", "status", unique=True, postgresql_where=text("status = 'prepared'"),
              sqlite_where=text("status = 'prepared'")),
        CheckConstraint(_in("status", FILE_STATUSES), name="ck_payout_files_status"),
        CheckConstraint("length(checksum) = 64", name="ck_payout_files_checksum"),
        CheckConstraint("(status = 'approved') = (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
                        name="ck_payout_files_approved"),
        CheckConstraint("execution_date >= payment_day", name="ck_payout_files_dates"),
        Index("ix_payout_files_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_reference: Mapped[str] = mapped_column(String(60), nullable=False)
    #: Betalningsdagen filen gäller: anspråk med betalningsdag senast denna dag
    payment_day: Mapped[date] = mapped_column(Date, nullable=False)
    #: Dagen banken ska utföra betalningarna: betalningsdagen eller nästa bankdag från skapandet
    execution_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Filen som denna ersätter (en ej godkänd fil med äldre underlag)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_files.id", ondelete="RESTRICT"), nullable=True)
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<PayoutFile {self.execution_date} {self.status}>"


class PayoutOrder(Base):
    """Ett bankuppdrag per mottagare i bankfilen, med skatten räknad på summan av personens rader (X3)."""

    __tablename__ = "payout_orders"
    __table_args__ = (
        UniqueConstraint("file_id", "insured_person_id", name="uq_payout_orders_person"),
        UniqueConstraint("reference", name="uq_payout_orders_reference"),
        CheckConstraint(_in("tax_method", TAX_METHODS), name="ck_payout_orders_tax_method"),
        CheckConstraint("gross_sek > 0 AND tax_sek >= 0 AND net_sek >= 0", name="ck_payout_orders_amounts"),
        CheckConstraint("gross_sek = tax_sek + net_sek", name="ck_payout_orders_net").ddl_if(dialect="postgresql"),
        # Samma regel i testdatabasen; SQLite räknar NUMERIC som flyttal, så likheten prövas på halva ören
        CheckConstraint("abs(gross_sek - tax_sek - net_sek) < 0.005", name="ck_payout_orders_net").ddl_if(
            dialect="sqlite"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_files.id", ondelete="RESTRICT"), nullable=False, index=True)
    insured_person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insured_persons.id", ondelete="RESTRICT"), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_accounts.id", ondelete="RESTRICT"), nullable=False)
    tax_status_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tax_statuses.id", ondelete="RESTRICT"), nullable=False)
    #: Utbetalningsdagens år styr skatten (PR-ITP1-026)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Bankens referens (end-to-end) för uppdraget
    reference: Mapped[str] = mapped_column(String(35), nullable=False)
    gross_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    tax_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    net_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    tax_method: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Skatteberäkningen: sats, förväntad årssumma, gränser och engångsbelopp
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<PayoutOrder {self.reference} {self.net_sek}>"


class PayoutOrderLine(Base):
    """Ett försök att betala ett anspråk: hela bruttot, en gång per anspråk och försöksnummer (X1, X2, X8)."""

    __tablename__ = "payout_order_lines"
    __table_args__ = (
        UniqueConstraint("claim_id", "attempt", name="uq_payout_order_lines_attempt"),
        UniqueConstraint("order_id", "claim_id", name="uq_payout_order_lines_order_claim"),
        CheckConstraint("attempt >= 1 AND gross_sek > 0", name="ck_payout_order_lines_amounts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pension_claims.id", ondelete="RESTRICT"), nullable=False, index=True)
    payout_part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_parts.id", ondelete="RESTRICT"), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    #: Engångsbelopp: rätten gäller en tidigare månad än månaden före utförandet (PR-ITP1-026 p. 6)
    lump_sum: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<PayoutOrderLine försök {self.attempt} {self.gross_sek}>"


class PayoutReceipt(Base):
    """Ett bankkvitto för ett uppdrag: utförd, avvisad, återkommen eller okänt utfall (X8)."""

    __tablename__ = "payout_receipts"
    __table_args__ = (
        UniqueConstraint("source_system", "receipt_id", name="uq_payout_receipts_source"),
        UniqueConstraint("order_id", "sequence", name="uq_payout_receipts_sequence"),
        CheckConstraint(_in("outcome", RECEIPT_OUTCOMES), name="ck_payout_receipts_outcome"),
        CheckConstraint("length(file_checksum) = 64 AND length(content_checksum) = 64",
                        name="ck_payout_receipts_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    receipt_id: Mapped[str] = mapped_column(String(64), nullable=False)
    file_reference: Mapped[str] = mapped_column(String(60), nullable=False)
    file_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    bank_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    #: Kvittots plats i ordningen för uppdraget (1, 2, …), så att senaste utfall är entydigt
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Verifikationen `payout_settlement` som bokade en utförd eller återkommen betalning
    settlement_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_batches.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<PayoutReceipt {self.receipt_id} {self.outcome}>"
