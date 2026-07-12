"""SQLAlchemy-modell för premietransaktioner.

Se 02_system/databasschema.md §6 för fullständig dokumentation av tabellen.

Spårbarhetens kärna: varje krona i pensionskapitalet ska kunna följas hit,
och varje `premium`-rad ska kunna räknas om ur pensionable_salary_sek +
calculation_basis (jfr 01_domän/ITP1_regelverk.md §8).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .policy import Policy

#: Transaktionstyper. 'fee' (kapitalavgift, B-021) införs med kapitalberäkningen.
TRANSACTION_TYPES = ("premium", "adjustment", "fee")

#: Faktureringsflöde enligt försäkringsvillkor §4. Kapital tillgodoförs vid 'paid'.
TRANSACTION_STATUSES = ("pending", "invoiced", "paid", "cancelled")


class PremiumTransaction(Base):
    """Premietransaktion – en rad per policy, månad och transaktionstyp."""

    __tablename__ = "premium_transactions"
    __table_args__ = (
        CheckConstraint(
            "transaction_type IN ('premium', 'adjustment', 'fee')",
            name="ck_premium_transactions_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'invoiced', 'paid', 'cancelled')",
            name="ck_premium_transactions_status",
        ),
        CheckConstraint(
            "EXTRACT(DAY FROM period_month) = 1",
            name="ck_premium_transactions_period_first_of_month",
        ),
        CheckConstraint(
            "pensionable_salary_sek IS NULL OR pensionable_salary_sek >= 0",
            name="ck_premium_transactions_salary",
        ),
        # Max en ordinarie premie per avtal och månad (partiellt unikt index).
        Index(
            "uq_premium_transactions_policy_period_premium",
            "policy_id",
            "period_month",
            unique=True,
            postgresql_where="transaction_type = 'premium'",
        ),
        Index("ix_premium_transactions_policy_period", "policy_id", "period_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policies.id", ondelete="RESTRICT"),
        nullable=False,
    )

    period_month: Mapped[date] = mapped_column(Date, nullable=False)

    transaction_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="premium",
        server_default="premium",
    )

    pensionable_salary_sek: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    amount_sek: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    calculation_basis: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    policy: Mapped["Policy"] = relationship(back_populates="premium_transactions")

    def __repr__(self) -> str:
        return (
            f"<PremiumTransaction {self.transaction_type} "
            f"{self.period_month:%Y-%m} {self.amount_sek} kr [{self.status}]>"
        )
