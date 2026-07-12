"""SQLAlchemy-modell för försäkringsförmåner.

Se 02_system/databasschema.md §7. En förmån inom en försäkring – i nuläget
bara premiebestämd ålderspension (retirement_dc); TGL och familjeskydd är
förberedda som typer. Förmånens premier ligger i premium_transactions.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .policy import Policy
    from .premium_transaction import PremiumTransaction

#: Förmånstyper. Nya typer läggs till i CHECK-constrainten vid behov.
BENEFIT_TYPES = ("retirement_dc", "tgl", "family_protection")


class PolicyBenefit(Base):
    """Försäkringsförmån – t.ex. premiebestämd ålderspension."""

    __tablename__ = "policy_benefits"
    __table_args__ = (
        CheckConstraint(
            "benefit_type IN ('retirement_dc', 'tgl', 'family_protection')",
            name="ck_policy_benefits_type",
        ),
        CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_policy_benefits_dates",
        ),
        # Max en pågående förmån av varje typ per försäkring
        Index(
            "uq_policy_benefits_one_active_per_type",
            "policy_id",
            "benefit_type",
            unique=True,
            postgresql_where="end_date IS NULL",
        ),
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
        index=True,
    )
    benefit_type: Mapped[str] = mapped_column(String(30), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    policy: Mapped["Policy"] = relationship(back_populates="benefits")
    premium_transactions: Mapped[list["PremiumTransaction"]] = relationship(
        back_populates="benefit",
        order_by="PremiumTransaction.period_month",
    )

    def __repr__(self) -> str:
        return f"<PolicyBenefit {self.benefit_type} från {self.start_date}>"
