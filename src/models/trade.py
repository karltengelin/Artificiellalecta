"""Låst affärsförslag med separata kvittenser för paper trading (§9f).

CHECK skyddar radens form. Betrodd identitet, oföränderlighet, övergångar,
reservationer och portföljkontroller kräver den framtida kapitalgatewayen.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .portfolio_holding import PortfolioHolding

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


def _complete_receipt(name: str, *columns: str) -> CheckConstraint:
    """SQL CHECK får inte släppa igenom en halv kvittens via NULL-semantik."""
    empty = " AND ".join(f"{column} IS NULL" for column in columns)
    complete = " AND ".join(f"{column} IS NOT NULL" for column in columns)
    return CheckConstraint(
        f"({empty}) OR ({complete})", name=f"ck_trades_{name}_complete"
    )


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("side IN ('buy', 'sell')", name="ck_trades_side"),
        CheckConstraint(
            "status IN ('proposed', 'approved', 'executed', 'rejected')",
            name="ck_trades_status",
        ),
        CheckConstraint(
            "proposer_type IN ('human', 'agent')", name="ck_trades_proposer_type"
        ),
        CheckConstraint(
            "quantity > 0 AND limit_price > 0", name="ck_trades_quantity_price"
        ),
        CheckConstraint("max_cost_sek >= 0", name="ck_trades_max_cost"),
        CheckConstraint("valid_until > proposed_at", name="ck_trades_validity"),
        CheckConstraint(
            "length(trim(proposed_by)) > 0 AND length(trim(reason)) > 0",
            name="ck_trades_required_text",
        ),
        CheckConstraint("length(proposal_hash) = 64", name="ck_trades_proposal_hash"),
        CheckConstraint(
            "(side = 'buy' AND max_cash_sek IS NOT NULL AND max_cash_sek > 0 "
            "AND min_proceeds_sek IS NULL) OR "
            "(side = 'sell' AND min_proceeds_sek IS NOT NULL AND min_proceeds_sek >= 0 "
            "AND max_cash_sek IS NULL)",
            name="ck_trades_side_limits",
        ),
        _complete_receipt(
            "approval",
            "approved_at",
            "approved_by",
            "approval_role",
            "approved_proposal_hash",
            "approval_basis",
        ),
        _complete_receipt(
            "execution",
            "executed_at",
            "execution_price",
            "execution_fx_rate",
            "gross_sek",
            "cost_sek",
            "execution_price_basis",
            "execution_basis",
        ),
        _complete_receipt(
            "rejection", "rejected_at", "rejected_by", "rejection_reason"
        ),
        CheckConstraint(
            "(status = 'proposed' AND approved_at IS NULL AND executed_at IS NULL AND rejected_at IS NULL) OR "
            "(status = 'approved' AND approved_at IS NOT NULL AND executed_at IS NULL AND rejected_at IS NULL) OR "
            "(status = 'executed' AND approved_at IS NOT NULL AND executed_at IS NOT NULL AND rejected_at IS NULL) OR "
            "(status = 'rejected' AND executed_at IS NULL AND rejected_at IS NOT NULL)",
            name="ck_trades_status_receipts",
        ),
        CheckConstraint(
            "approved_at IS NULL OR (approved_at >= proposed_at AND approved_at <= valid_until "
            "AND approved_proposal_hash = proposal_hash "
            "AND length(trim(approved_by)) > 0 AND length(trim(approval_role)) > 0)",
            name="ck_trades_approval_terms",
        ),
        CheckConstraint(
            "executed_at IS NULL OR (executed_at >= approved_at AND executed_at <= valid_until "
            "AND execution_price > 0 AND execution_fx_rate > 0 AND gross_sek > 0 "
            "AND cost_sek >= 0 AND cost_sek <= max_cost_sek)",
            name="ck_trades_execution_terms",
        ),
        CheckConstraint(
            "executed_at IS NULL OR "
            "(side = 'buy' AND execution_price <= limit_price AND gross_sek + cost_sek <= max_cash_sek) OR "
            "(side = 'sell' AND execution_price >= limit_price AND gross_sek - cost_sek >= min_proceeds_sek)",
            name="ck_trades_execution_limits",
        ),
        CheckConstraint(
            "rejected_at IS NULL OR (rejected_at >= proposed_at "
            "AND (approved_at IS NULL OR rejected_at >= approved_at) "
            "AND length(trim(rejected_by)) > 0 AND length(trim(rejection_reason)) > 0)",
            name="ck_trades_rejection_terms",
        ),
        CheckConstraint(
            "supersedes_trade_id IS NULL OR supersedes_trade_id <> id",
            name="ck_trades_not_superself",
        ),
        CheckConstraint(
            "corrects_trade_id IS NULL OR corrects_trade_id <> id",
            name="ck_trades_not_correctself",
        ),
        Index("ix_trades_holding_execution", "portfolio_holding_id", "executed_at"),
        Index("ix_trades_status_proposed", "status", "proposed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    portfolio_holding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio_holdings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="proposed", server_default="proposed"
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    limit_price: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    max_cost_sek: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    max_cash_sek: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    min_proceeds_sek: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    proposed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    proposed_by: Mapped[str] = mapped_column(String(100), nullable=False)
    proposer_type: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    run_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    order_group_reference: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    proposal_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_price_basis: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    proposal_basis: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approval_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_proposal_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    approval_basis: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)

    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    execution_price: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 10), nullable=True
    )
    execution_fx_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 10), nullable=True
    )
    gross_sek: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    cost_sek: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    execution_price_basis: Mapped[dict[str, Any] | None] = mapped_column(
        _JSON, nullable=True
    )
    execution_basis: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)

    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    supersedes_trade_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trades.id", ondelete="RESTRICT"), nullable=True
    )
    corrects_trade_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trades.id", ondelete="RESTRICT"), nullable=True
    )

    holding: Mapped[PortfolioHolding] = relationship(back_populates="trades")
