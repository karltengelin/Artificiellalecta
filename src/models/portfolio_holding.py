"""Instrument per paper trading-portfölj; antal härleds ur avslut (§9e)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .portfolio import Portfolio
    from .trade import Trade


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id", "instrument_key", name="uq_portfolio_holdings_instrument"
        ),
        CheckConstraint(
            "allocation_bucket IN ('sek_fixed_income', 'global_equity', 'swedish_equity')",
            name="ck_portfolio_holdings_allocation",
        ),
        CheckConstraint(
            "length(trim(instrument_key)) > 0 AND length(trim(name)) > 0 "
            "AND length(trim(instrument_basis_reference)) > 0",
            name="ck_portfolio_holdings_required_text",
        ),
        CheckConstraint(
            "length(price_currency) = 3", name="ck_portfolio_holdings_currency"
        ),
        CheckConstraint(
            "length(instrument_basis_hash) = 64",
            name="ck_portfolio_holdings_basis_hash",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    instrument_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    market_symbol: Mapped[str | None] = mapped_column(String(100), nullable=True)
    market_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    allocation_bucket: Mapped[str] = mapped_column(String(30), nullable=False)
    price_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    instrument_basis_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    instrument_basis_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_basis: Mapped[dict[str, Any]] = mapped_column(
        JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql"),
        nullable=False,
    )

    portfolio: Mapped[Portfolio] = relationship(back_populates="holdings")
    trades: Mapped[list[Trade]] = relationship(
        back_populates="holding", passive_deletes="all"
    )
