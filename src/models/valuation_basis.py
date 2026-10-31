"""SQLAlchemy-modell för antagandebiblioteket: aktuariella grunder som versionerad data (A4, B-042).

Se 02_system/databasschema.md §9j och projekt/06_avdelningsfunktioner/VARDERINGSKONTRAKT.md §4.
Varje rad är en grund med ett oföränderligt innehåll (`assumptions`) och dess kontrollsumma:
garantigrunderna SIM-G/SIM-HIST, utbetalningsgrunden SIM-B, riskgrunden SIM-R,
värderingsgrunden SIM-V, de syntetiska diskonteringskurvorna FI-SIM och den deklarerade
avkastningsserien AVK-SIM. En grund föreslås,
antas med giltighetsdag och beslutsreferens och avslutas när en nyare grund i samma familj
antas. Innehållet ändras aldrig efter att raden skapats (B-027: historiska grunder bevaras).

Inga personuppgifter.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

#: Familjer och deras ändamål. En ny familj kräver ändring här och i services/valuation_bases.py.
BASIS_FAMILIES = {
    "SIM-G": "guarantee",
    "SIM-HIST": "guarantee",
    "SIM-B": "payout",
    "SIM-R": "risk",
    "SIM-V": "valuation",
    "FI-SIM": "discount_curve",
    "AVK-SIM": "return_series",  # deklarerad avkastning för S-04 tills kapitalförvaltningen levererar
}
BASIS_STATUSES = ("proposed", "adopted", "rejected")
_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class ValuationBasis(Base):
    """En aktuariell grund eller diskonteringskurva med oföränderligt innehåll."""

    __tablename__ = "valuation_bases"
    __table_args__ = (
        CheckConstraint(_in("family", BASIS_FAMILIES), name="ck_valuation_bases_family"),
        CheckConstraint(_in("purpose", sorted(set(BASIS_FAMILIES.values()))), name="ck_valuation_bases_purpose"),
        CheckConstraint(_in("status", BASIS_STATUSES), name="ck_valuation_bases_status"),
        CheckConstraint("length(checksum) = 64", name="ck_valuation_bases_checksum"),
        CheckConstraint(
            "status <> 'adopted' OR (valid_from IS NOT NULL AND decision_ref IS NOT NULL AND adopted_by IS NOT NULL)",
            name="ck_valuation_bases_adopted",
        ),
        CheckConstraint("status = 'adopted' OR (valid_from IS NULL AND valid_to IS NULL)",
                        name="ck_valuation_bases_only_adopted_valid"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_valuation_bases_interval"),
        # Högst en gällande, inte avslutad grund per familj
        Index("uq_valuation_bases_one_open", "family", unique=True,
              postgresql_where=text("status = 'adopted' AND valid_to IS NULL"),
              sqlite_where=text("status = 'adopted' AND valid_to IS NULL")),
        Index("ix_valuation_bases_family", "family", "valid_from"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    family: Mapped[str] = mapped_column(String(20), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    assumptions: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    source_refs: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    decision_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supersedes_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    proposal_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    adopted_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    adopted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ValuationBasis {self.code} {self.status}>"
