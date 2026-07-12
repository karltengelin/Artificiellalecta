"""SQLAlchemy-modell för försäkringslägen (tillståndsperioder).

Se 02_system/databasschema.md §6. Varje rad = "försäkringen var i läge X
från valid_from till valid_to". Öppen rad (valid_to IS NULL) = nuläget.
Max ett öppet läge per försäkring (partiellt unikt index). Att perioder
inte överlappar valideras på applikationsnivå.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .policy import Policy

#: Lägen, mappade mot 01_domän/försäkringsvillkor.md (databasschema §6)
POLICY_STATES = (
    "premium_paying",
    "paid_up",
    "in_payout",
    "payout_paused",
    "terminated",
)


class PolicyState(Base):
    """Försäkringsläge – ett tillstånd med giltighetsperiod."""

    __tablename__ = "policy_states"
    __table_args__ = (
        CheckConstraint(
            "state IN ('premium_paying', 'paid_up', 'in_payout', "
            "'payout_paused', 'terminated')",
            name="ck_policy_states_state",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_policy_states_dates",
        ),
        # Max ett öppet (pågående) läge per försäkring
        Index(
            "uq_policy_states_one_open",
            "policy_id",
            unique=True,
            postgresql_where="valid_to IS NULL",
        ),
        Index("ix_policy_states_policy_from", "policy_id", "valid_from"),
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
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    policy: Mapped["Policy"] = relationship(back_populates="states")

    def __repr__(self) -> str:
        until = self.valid_to.isoformat() if self.valid_to else "pågående"
        return f"<PolicyState {self.state} {self.valid_from} → {until}>"
