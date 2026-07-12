"""SQLAlchemy-modell för försäkringar.

Se 02_system/databasschema.md §5. En person kan ha flera försäkringar (B-022).
Ingen statuskolumn – försäkringens läge över tid ligger i policy_states,
dess innehåll i policy_benefits. Kapital härleds ur premium_transactions.
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
    from .policy_benefit import PolicyBenefit
    from .policy_state import PolicyState


class Policy(Base):
    """Försäkring – tecknad för en försäkrad, med förmåner och lägeshistorik."""

    __tablename__ = "policies"
    __table_args__ = (
        CheckConstraint(
            "start_date >= signed_date",
            name="ck_policies_start_after_signed",
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
        index=True,
    )

    product_code: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ITP1", server_default="ITP1"
    )
    signed_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)

    insured_person: Mapped["InsuredPerson"] = relationship(
        back_populates="policies"
    )
    states: Mapped[list["PolicyState"]] = relationship(
        back_populates="policy",
        order_by="PolicyState.valid_from",
    )
    benefits: Mapped[list["PolicyBenefit"]] = relationship(
        back_populates="policy",
        order_by="PolicyBenefit.start_date",
    )

    def __repr__(self) -> str:
        return f"<Policy {self.policy_number} ({self.product_code})>"
