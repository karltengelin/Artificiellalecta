"""SQLAlchemy-modell för försäkringsförmåner.

Se 02_system/databasschema.md §7. En förmån inom en försäkring – i nuläget
bara premiebestämd ITP1 ålderspension (retirement_dc) i beslutat produktscope.
TGL och familjeskydd är tekniskt förberedda som typer enligt B-022; användning
som produkter kräver ett nytt uttryckligt scopebeslut och uppdaterade villkor.
Förmånens premier ligger i premium_transactions.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, Date, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .policy import Policy
    from .premium_transaction import PremiumTransaction

#: Tekniskt tillåtna typer; bara retirement_dc ingår i beslutat produktscope.
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
            sqlite_where=text("end_date IS NULL"),  # testdatabasen (tjänstelagrets tester)
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
    parameters: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True  # JSONB i Lakebase, JSON i tester
    )

    policy: Mapped["Policy"] = relationship(back_populates="benefits")
    premium_transactions: Mapped[list["PremiumTransaction"]] = relationship(
        back_populates="benefit",
        order_by="PremiumTransaction.period_month",
    )

    def __repr__(self) -> str:
        return f"<PolicyBenefit {self.benefit_type} från {self.start_date}>"
