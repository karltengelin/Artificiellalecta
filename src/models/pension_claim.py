"""SQLAlchemy-modeller för beloppsbeslut och månadsrätter (paket B steg 5, B-047 punkt 6 och 8, Karls val W1–W12).

Se 02_system/databasschema.md §7e och designstoppet P1-PENSION-001 §5.5 (PB6, PB11). Raderna skrivs av
månadsstängningen i samma transaktion som verifikationen och ändras aldrig (Karls val W1–W2 2026-11-22).

- `payout_amounts`: beslutat månadsbelopp M per uttagsdel, giltigt från en månad. Orsaken är start,
  återstart, planändring eller januariomräkning (PR-ITP1-009). Beslutet räknas på värderingen vid
  föregående månadsslut och bär G, B, faktor, golv och grund med kontrollsumma.
- `pension_claims`: ett bruttoanspråk per uttagsdel och rättighetsmånad (PR-ITP1-026), med fördelningen
  på kundkapital, bolagsstöd och ej finansierat belopp (PR-ITP1-028) och betalningsdagen. Steg 6 bygger
  betalningsförloppet som egna rader som pekar på anspråket, så anspråket självt ändras aldrig.
- `pension_claim_fundings`: senare finansiering av ett ej finansierat anspråk från bolagskontot, bokad i
  en senare stängning efter en ny insättning (Karls val W8). Kvar att finansiera är anspråkets
  `unfunded_sek` minus summan av dess finansieringar.

Agentrollerna har inga rättigheter på tabellerna (P1-PENSION-001 §12).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

#: Varför ett nytt belopp beslutas (PR-ITP1-009): start, återstart, planändring och varje januari
AMOUNT_REASONS = ("start", "restart", "plan_change", "january")
#: Vad som bestämde beloppet (`pension_amount`): kandidaten max(G, B), garantigolvet eller tidigare golv
AMOUNT_BINDINGS = ("candidate", "guarantee", "floor")

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
_MONEY = Numeric(14, 2)
_PRECISE = Numeric(24, 10)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PayoutAmount(Base):
    """Ett beslutat månadsbelopp M för en uttagsdel från en månad, räknat av månadsstängningen."""

    __tablename__ = "payout_amounts"
    __table_args__ = (
        UniqueConstraint("payout_part_id", "effective_month", name="uq_payout_amounts_part_month"),
        CheckConstraint(_in("reason", AMOUNT_REASONS), name="ck_payout_amounts_reason"),
        CheckConstraint(_in("binding", AMOUNT_BINDINGS), name="ck_payout_amounts_binding"),
        CheckConstraint("m_sek > 0 AND capital_sek >= 0 AND guarantee_sek_per_month >= 0 AND payout_factor > 0",
                        name="ck_payout_amounts_amounts"),
        CheckConstraint("length(payout_basis_checksum) = 64", name="ck_payout_amounts_basis_checksum"),
    )

    #: Stabilt id ur del och månad
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payout_part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_parts.id", ondelete="RESTRICT"), nullable=False, index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_plans.id", ondelete="RESTRICT"), nullable=False)
    #: Första rättighetsmånad beloppet gäller för; det ligger fast till nästa beslut
    effective_month: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Föregående månadsslut, som G, B och M räknas på (aktuariell_grund.md §3)
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False)
    capital_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    guarantee_sek_per_month: Mapped[Decimal] = mapped_column(_PRECISE, nullable=False)
    capital_amount_sek: Mapped[Decimal] = mapped_column(_PRECISE, nullable=False)
    payout_basis_code: Mapped[str] = mapped_column(String(30), nullable=False)
    payout_basis_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    payout_factor: Mapped[Decimal] = mapped_column(_PRECISE, nullable=False)
    m_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    floor_sek: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    binding: Mapped[str] = mapped_column(String(20), nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    #: Hela beräkningen, som i stängningens sammanställning
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<PayoutAmount {self.reason} {self.effective_month} {self.m_sek}>"


class PensionClaim(Base):
    """Ett bruttoanspråk per uttagsdel och rättighetsmånad: skuldfört en gång (PR-ITP1-026)."""

    __tablename__ = "pension_claims"
    __table_args__ = (
        UniqueConstraint("payout_part_id", "right_month", name="uq_pension_claims_part_month"),
        CheckConstraint("right_number >= 1", name="ck_pension_claims_number"),
        CheckConstraint("gross_sek > 0 AND from_capital_sek >= 0 AND company_support_sek >= 0 AND unfunded_sek >= 0",
                        name="ck_pension_claims_amounts"),
        # Brutto = kundkapital + bolagsstöd + ej finansierat (PR-ITP1-028)
        CheckConstraint("gross_sek = from_capital_sek + company_support_sek + unfunded_sek",
                        name="ck_pension_claims_funding").ddl_if(dialect="postgresql"),
        # Samma regel i testdatabasen; SQLite räknar NUMERIC som flyttal, så likheten prövas på halva ören
        CheckConstraint("abs(gross_sek - from_capital_sek - company_support_sek - unfunded_sek) < 0.005",
                        name="ck_pension_claims_funding").ddl_if(dialect="sqlite"),
        Index("ix_pension_claims_month", "right_month"),
    )

    #: Stabilt id ur del och månad; steg 6:s bankförsök pekar hit
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payout_part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_parts.id", ondelete="RESTRICT"), nullable=False, index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_plans.id", ondelete="RESTRICT"), nullable=False)
    amount_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_amounts.id", ondelete="RESTRICT"), nullable=False)
    #: Rättighetsmånaden (första dagen) och rättens löpnummer i planen
    right_month: Mapped[date] = mapped_column(Date, nullable=False)
    right_number: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    from_capital_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    company_support_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    #: Ej finansierat när anspråket uppkom; en senare finansiering står i `pension_claim_fundings`
    unfunded_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    #: Sista rätten i en tidsbegränsad plan, slutavräknad (PR-ITP1-027)
    final_settlement: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Första svenska bankdagen efter rättighetsmånaden (PR-ITP1-026)
    payment_day: Mapped[date] = mapped_column(Date, nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<PensionClaim {self.right_month} {self.gross_sek}>"


class PensionClaimFunding(Base):
    """Bolagsstöd som i en senare stängning finansierar ett tidigare ej finansierat anspråk (PR-ITP1-028)."""

    __tablename__ = "pension_claim_fundings"
    __table_args__ = (
        UniqueConstraint("claim_id", "batch_id", name="uq_pension_claim_fundings_claim_batch"),
        CheckConstraint("amount_sek > 0", name="ck_pension_claim_fundings_amount"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pension_claims.id", ondelete="RESTRICT"), nullable=False, index=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<PensionClaimFunding {self.amount_sek}>"
