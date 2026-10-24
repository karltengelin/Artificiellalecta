"""Fristående paper trading-scenario (B-003/B-019), databasschema §9d.

Startkassan är ett finansieringsfaktum; aktuella saldon härleds senare.
Modellen ger ingen rätt att boka affärer eller koppla försäkringsbeståndet.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .portfolio_holding import PortfolioHolding


class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        CheckConstraint("mode = 'paper'", name="ck_portfolios_mode"),
        CheckConstraint(
            "scenario_type = 'standalone'", name="ck_portfolios_scenario_type"
        ),
        CheckConstraint("base_currency = 'SEK'", name="ck_portfolios_currency"),
        CheckConstraint(
            "settlement_model = 'instant_simulated'", name="ck_portfolios_settlement"
        ),
        CheckConstraint("opening_cash_sek >= 0", name="ck_portfolios_opening_cash"),
        CheckConstraint(
            "length(trim(scenario_code)) > 0 AND length(trim(name)) > 0 "
            "AND length(trim(scenario_description)) > 0 "
            "AND length(trim(guideline_reference)) > 0 "
            "AND length(trim(guideline_version)) > 0",
            name="ck_portfolios_required_text",
        ),
        CheckConstraint(
            "length(guideline_hash) = 64", name="ck_portfolios_guideline_hash"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    scenario_description: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="paper", server_default="paper"
    )
    scenario_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="standalone", server_default="standalone"
    )
    base_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="SEK", server_default="SEK"
    )
    settlement_model: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="instant_simulated",
        server_default="instant_simulated",
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    opening_cash_sek: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    funding_basis: Mapped[dict[str, Any]] = mapped_column(
        JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql"),
        nullable=False,
    )
    guideline_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    guideline_version: Mapped[str] = mapped_column(String(40), nullable=False)
    guideline_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario_basis: Mapped[dict[str, Any]] = mapped_column(
        JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql"),
        nullable=False,
    )

    holdings: Mapped[list[PortfolioHolding]] = relationship(
        back_populates="portfolio", passive_deletes="all"
    )
