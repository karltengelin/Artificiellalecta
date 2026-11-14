"""SQLAlchemy-modeller för uttagsdelar och deras pensionsförlopp (paket B steg 1, B-047 punkt 2).

Se 02_system/databasschema.md §7b och designstoppet P1-PENSION-001 §4 (PB2). En uttagsdel
ligger under en förmån. Varje ålderspensionsförmån har minst del 1; en delning (PR-ITP1-024,
byggs i steg 4) ger högst tre delar per ursprunglig förmån. Varje garantidel, kapitalpost och
månadsrätt ska tillhöra exakt en del (steg 2 och 5).

Delens pensionsförlopp är en tidslinje i `payout_part_states`, på samma sätt som
`policy_states` bär premieförloppet: `not_started`, `in_payout`, `paused` och `ended` (med
orsak `final_settlement` eller `death`). En framtida plan är en planversion (steg 4), inte ett
läge. Öppen rad (`valid_to IS NULL`) = delens läge i dag; `ended` är slutligt och alltid öppet.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .policy_benefit import PolicyBenefit

#: Pensionsförloppets lägen per uttagsdel (P1-PENSION-001 §4)
PAYOUT_PART_STATES = ("not_started", "in_payout", "paused", "ended")
#: Lägen där delen har startat och inte längre tar emot premie (PR-ITP1-015, -025)
STARTED_PART_STATES = ("in_payout", "paused")
#: Orsak till att en del är avslutad i rättighetshänseende (PB10): slutavräkning eller dödsfall
END_REASONS = ("final_settlement", "death")
#: Högst tre uttagsdelar per ursprunglig försäkring (PR-ITP1-024)
MAX_PARTS = 3
#: Minsta andel för ny och kvarvarande del vid delning (PR-ITP1-024)
MIN_SPLIT_SHARE = Decimal("0.1")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PayoutPart(Base):
    """Uttagsdel – den enhet som får egen start, form, plan, garantidelar och månadsrätter."""

    __tablename__ = "payout_parts"
    __table_args__ = (
        UniqueConstraint("benefit_id", "part_number", name="uq_payout_parts_benefit_number"),
        CheckConstraint(f"part_number BETWEEN 1 AND {MAX_PARTS}", name="ck_payout_parts_number"),
        CheckConstraint("share_of_origin > 0 AND share_of_origin <= 1", name="ck_payout_parts_share"),
        # Del 1 är ursprunget; senare delar uppstår bara genom delning med länk, dag och andel
        CheckConstraint(
            "(part_number = 1 AND split_from_part_id IS NULL AND split_date IS NULL AND split_share IS NULL)"
            " OR (part_number > 1 AND split_from_part_id IS NOT NULL AND split_date IS NOT NULL"
            " AND split_share IS NOT NULL)",
            name="ck_payout_parts_split",
        ),
        CheckConstraint(
            f"split_share IS NULL OR (split_share >= {MIN_SPLIT_SHARE} AND split_share <= {1 - MIN_SPLIT_SHARE})",
            name="ck_payout_parts_split_share",
        ),
        Index("ix_payout_parts_split_from", "split_from_part_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    benefit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_benefits.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    part_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Delens andel av den ursprungliga rätten, fastställd vid delningen; marknadsutveckling ändrar
    #: den inte (PR-ITP1-024). Del 1 före delning: 1.
    share_of_origin: Mapped[Decimal] = mapped_column(Numeric(11, 10), nullable=False, default=Decimal(1))
    split_from_part_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_parts.id", ondelete="RESTRICT"), nullable=True,
    )
    split_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: Vald andel av den delade delens kapital vid delningen (minst 10 %, och minst 10 % kvar)
    split_share: Mapped[Decimal | None] = mapped_column(Numeric(11, 10), nullable=True)

    benefit: Mapped[PolicyBenefit] = relationship(back_populates="payout_parts")
    states: Mapped[list[PayoutPartState]] = relationship(
        back_populates="part", order_by="PayoutPartState.valid_from",
    )

    def __repr__(self) -> str:
        return f"<PayoutPart {self.part_number} av förmån {self.benefit_id}>"


class PayoutPartState(Base):
    """Uttagsdelens pensionsläge med giltighetsperiod (pensionsförloppet)."""

    __tablename__ = "payout_part_states"
    __table_args__ = (
        CheckConstraint(_in("state", PAYOUT_PART_STATES), name="ck_payout_part_states_state"),
        CheckConstraint(
            f"(state = 'ended' AND end_reason IS NOT NULL AND {_in('end_reason', END_REASONS)}) "
            "OR (state <> 'ended' AND end_reason IS NULL)",
            name="ck_payout_part_states_end_reason",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_payout_part_states_dates"),
        CheckConstraint("state <> 'ended' OR valid_to IS NULL", name="ck_payout_part_states_ended_open"),
        # Max ett öppet läge per uttagsdel
        Index(
            "uq_payout_part_states_one_open", "payout_part_id", unique=True,
            postgresql_where=text("valid_to IS NULL"), sqlite_where=text("valid_to IS NULL"),
        ),
        Index("ix_payout_part_states_part_from", "payout_part_id", "valid_from"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payout_part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_parts.id", ondelete="RESTRICT"), nullable=False,
    )
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    end_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    part: Mapped[PayoutPart] = relationship(back_populates="states")

    def __repr__(self) -> str:
        until = self.valid_to.isoformat() if self.valid_to else "pågående"
        return f"<PayoutPartState {self.state} {self.valid_from} → {until}>"
