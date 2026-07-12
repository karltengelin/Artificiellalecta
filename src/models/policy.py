"""SQLAlchemy-modell för försäkringsavtal (ålderspension ITP1).

Se 02_system/databasschema.md §5 för fullständig dokumentation av tabellen.
Enligt B-021 har varje försäkrad exakt ett avtal (UNIQUE på insured_person_id).
Pensionskapital lagras inte här – det härleds ur premium_transactions.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .insured_person import InsuredPerson
    from .premium_transaction import PremiumTransaction

#: Tillåtna livscykelstatusar, speglar villkoren i 01_domän/försäkringsvillkor.md
POLICY_STATUSES = ("active", "paid_up", "in_payout", "payout_paused", "terminated")


class Policy(Base):
    """Försäkringsavtal – ålderspension ITP1 för en försäkrad."""

    __tablename__ = "policies"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'paid_up', 'in_payout', 'payout_paused', 'terminated')",
            name="ck_policies_status",
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_policies_dates",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    policy_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)

    insured_person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("insured_persons.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,  # Ett avtal per försäkrad (B-021)
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
        index=True,
    )

    insured_person: Mapped["InsuredPerson"] = relationship(back_populates="policy")
    premium_transactions: Mapped[list["PremiumTransaction"]] = relationship(
        back_populates="policy",
        order_by="PremiumTransaction.period_month",
    )

    def __repr__(self) -> str:
        return f"<Policy {self.policy_number} [{self.status}]>"
