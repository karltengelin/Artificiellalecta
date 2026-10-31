"""SQLAlchemy-modeller för värderingsmotorn: datautdrag, körningar och resultat (A6, B-042).

Se 02_system/databasschema.md §9k och projekt/06_avdelningsfunktioner/VARDERINGSKONTRAKT.md §5–6.

- `valuation_extracts`: det oföränderliga datautdraget (S-04) som en körning räknar på, med
  SHA-256-kontrollsumma. Innehåller individrader utan personuppgifter (försäkringens id,
  födelsemånad, garantidelar och kapital) och läses bara i betrodd kod – ingen agentroll får
  SELECT på tabellen.
- `valuation_runs`: en värderingskörning med datum, grund, kurva, skatteavdrag, utdragets och
  resultatets kontrollsummor, kodversion och totalerna FTA, villkorad återbäring och underskott.
  Status `draft` → `locked` (av människa) → `superseded` (när en rättad version låses).
  Scenarier låses aldrig.
- `valuation_results`: resultatet per segment (läge × födelsekohort) med småcellsskydd: en
  dold cell har bara skälet, inga belopp.

Belopp lagras med sex decimaler och avrundas till öre först i rapporteringen.
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
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

RUN_STATUSES = ("draft", "locked", "superseded")
RUN_PURPOSES = ("base", "scenario")
SOURCES = ("reconstructed_s04", "ledger")
_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
_AMOUNT = Numeric(20, 6)


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class ValuationExtractRecord(Base):
    """Ett sparat datautdrag; samma innehåll sparas en gång (unik kontrollsumma)."""

    __tablename__ = "valuation_extracts"
    __table_args__ = (
        CheckConstraint(_in("source", SOURCES), name="ck_valuation_extracts_source"),
        CheckConstraint("length(checksum) = 64", name="ck_valuation_extracts_checksum"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policies: Mapped[int] = mapped_column(Integer, nullable=False)
    guarantee_parts: Mapped[int] = mapped_column(Integer, nullable=False)
    capital_sek: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return f"<ValuationExtractRecord {self.valuation_date} {self.checksum[:12]}>"


class ValuationRun(Base):
    """En värderingskörning: indata med kontrollsummor, totaler, kontroller och status."""

    __tablename__ = "valuation_runs"
    __table_args__ = (
        CheckConstraint(_in("status", RUN_STATUSES), name="ck_valuation_runs_status"),
        CheckConstraint(_in("purpose", RUN_PURPOSES), name="ck_valuation_runs_purpose"),
        CheckConstraint(_in("source", SOURCES), name="ck_valuation_runs_source"),
        CheckConstraint("purpose = 'base' OR status = 'draft'", name="ck_valuation_runs_scenario_never_locked"),
        CheckConstraint("status = 'draft' OR (locked_by IS NOT NULL AND locked_at IS NOT NULL)",
                        name="ck_valuation_runs_locked"),
        CheckConstraint("length(extract_checksum) = 64 AND length(result_checksum) = 64",
                        name="ck_valuation_runs_checksums"),
        UniqueConstraint("valuation_date", "purpose", "version", name="uq_valuation_runs_version"),
        # Högst en låst basvärdering per datum; en rättelse ersätter den (status superseded)
        Index("uq_valuation_runs_one_locked", "valuation_date", unique=True,
              postgresql_where=text("status = 'locked'"), sqlite_where=text("status = 'locked'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    basis_code: Mapped[str] = mapped_column(String(30), nullable=False)
    basis_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    curve_code: Mapped[str] = mapped_column(String(30), nullable=False)
    curve_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    tax_reduction: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    tax_parameter: Mapped[str] = mapped_column(String(100), nullable=False)
    extract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("valuation_extracts.id"),
                                                  nullable=False)
    extract_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    code_version: Mapped[str] = mapped_column(String(60), nullable=False)
    result_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    policies: Mapped[int] = mapped_column(Integer, nullable=False)
    capital_sek: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    guarantee_sek_per_month: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    fta_sek: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    expenses_sek: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    surplus_sek: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    deficit_sek: Mapped[Decimal] = mapped_column(_AMOUNT, nullable=False)
    not_calculated: Mapped[list[dict[str, Any]]] = mapped_column(_JSON, nullable=False)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(_JSON, nullable=False)
    checks_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("valuation_runs.id"),
                                                            nullable=True)

    def __repr__(self) -> str:
        return f"<ValuationRun {self.valuation_date} {self.purpose} v{self.version} {self.status}>"


class ValuationResult(Base):
    """Resultatet för ett segment (läge × födelsekohort); dolda celler saknar belopp."""

    __tablename__ = "valuation_results"
    __table_args__ = (
        UniqueConstraint("run_id", "state", "cohort", name="uq_valuation_results_segment"),
        CheckConstraint(
            "(hidden_reason IS NULL AND policies IS NOT NULL AND fta_sek IS NOT NULL) OR "
            "(hidden_reason IS NOT NULL AND policies IS NULL AND capital_sek IS NULL AND fta_sek IS NULL "
            "AND expenses_sek IS NULL AND surplus_sek IS NULL AND deficit_sek IS NULL)",
            name="ck_valuation_results_hidden",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("valuation_runs.id"), nullable=False,
                                              index=True)
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    cohort: Mapped[str] = mapped_column(String(20), nullable=False)
    policies: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capital_sek: Mapped[Decimal | None] = mapped_column(_AMOUNT, nullable=True)
    fta_sek: Mapped[Decimal | None] = mapped_column(_AMOUNT, nullable=True)
    expenses_sek: Mapped[Decimal | None] = mapped_column(_AMOUNT, nullable=True)
    surplus_sek: Mapped[Decimal | None] = mapped_column(_AMOUNT, nullable=True)
    deficit_sek: Mapped[Decimal | None] = mapped_column(_AMOUNT, nullable=True)
    hidden_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    def __repr__(self) -> str:
        return f"<ValuationResult {self.state} {self.cohort}>"
