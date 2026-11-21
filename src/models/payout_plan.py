"""SQLAlchemy-modeller för begäran, planversion och delning av uttagsdelar (paket B steg 4, B-047 punkt 3, Karls val V1–V11).

Se 02_system/databasschema.md §7d och designstoppet P1-PENSION-001 §5 (PB3, PB6). Raderna är
oföränderliga: en ny planversion ersätter den förra uttryckligen, och ett beslut genomförs i
ändringsmånadens stängning (Karls val V2 2026-11-21).

- `payout_requests`: kundens begäran med mottagningsdag, kanal, aktör, innehåll, frist och utfall
  (UTTAG_GEMENSAMT). En sen begäran får ett förslag på nästa möjliga månad; kundens bekräftelse
  registreras som en ny begäran som pekar på den förra.
- `payout_plans`: en planversion per uttagsdel med ändringsmånad, form, första rätt, N, pauser,
  härledd slutmånad, värderingsdag, grunder med kontrollsumma, faktorer, G, B och M. Ursprunget är en
  begäran eller standardstarten vid 66 (PR-ITP1-025).
- `payout_splits`: delningsbeslut (PR-ITP1-024) med del, andel, ändringsmånad och primär premiemottagare
  (PR-ITP1-015). Den nya delen skapas av ändringsmånadens stängning.

Agentrollerna har inga rättigheter på tabellerna (P1-PENSION-001 §12).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from .case import CASE_CHANNELS

#: Vad begäran gäller: första start eller ändrad framtida start (även uppskov), paus, förlängning och delning
REQUEST_KINDS = ("start", "pause", "extend", "split")
#: Fristprövningens utfall (UTTAG_GEMENSAMT, P1-PENSION-001 §5.1). `blocked`: utanför första versionen (PB1)
REQUEST_OUTCOMES = ("in_time", "late", "incomplete", "stopped", "blocked")
REQUESTERS = ("insured", "representative")
PLAN_ORIGINS = ("request", "standard_start")
PLAN_FORMS = ("lifelong", "fixed_term")
#: Vilken ändring planversionen gör; styr beloppsgolvet (PR-ITP1-009)
PLAN_CHANGES = ("start", "pause", "extend")

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
_MONEY = Numeric(14, 2)
_PRECISE = Numeric(24, 10)
_SHARE = Numeric(11, 10)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class PayoutRequest(Base):
    """Kundens begäran om start, uppskov, paus, förlängning eller delning, prövad mot fristen."""

    __tablename__ = "payout_requests"
    __table_args__ = (
        CheckConstraint(_in("kind", REQUEST_KINDS), name="ck_payout_requests_kind"),
        CheckConstraint(_in("outcome", REQUEST_OUTCOMES), name="ck_payout_requests_outcome"),
        CheckConstraint(_in("channel", CASE_CHANNELS), name="ck_payout_requests_channel"),
        CheckConstraint(_in("requester", REQUESTERS), name="ck_payout_requests_requester"),
        CheckConstraint("(outcome = 'late') = (proposed_month IS NOT NULL)", name="ck_payout_requests_proposal"),
        CheckConstraint("length(checksum) = 64", name="ck_payout_requests_checksum"),
        Index("ix_payout_requests_part", "payout_part_id"),
        Index("ix_payout_requests_person", "insured_person_id"),
    )

    #: Stabilt id ur innehållet (uuid5): samma begäran registrerad igen ger samma rad
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    insured_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insured_persons.id", ondelete="RESTRICT"), nullable=True)
    payout_part_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_parts.id", ondelete="RESTRICT"), nullable=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    #: Ändringsmånaden: första månad begäran ändrar; fristen räknas mot den
    change_month: Mapped[date] = mapped_column(Date, nullable=False)
    #: Kundens val: startmånad, form, N, pausintervall, nytt N, delningsandel och premiemottagare
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    requester: Mapped[str] = mapped_column(String(20), nullable=False)
    authority_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: Sista kalenderdagen i månaden före ändringsmånaden (Europe/Stockholm)
    deadline: Mapped[date] = mapped_column(Date, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    proposed_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: Konkreta uppgifter som saknas eller hindret, för komplettering
    missing: Mapped[list[Any]] = mapped_column(_JSON, nullable=False, default=list)
    confirms_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_requests.id", ondelete="RESTRICT"), nullable=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="RESTRICT"), nullable=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    registered_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<PayoutRequest {self.kind} {self.change_month} {self.outcome}>"


class PayoutPlan(Base):
    """En planversion för en uttagsdel, beslutad hashbundet mot en förhandsberäkning."""

    __tablename__ = "payout_plans"
    __table_args__ = (
        UniqueConstraint("payout_part_id", "version", name="uq_payout_plans_part_version"),
        CheckConstraint("version >= 1", name="ck_payout_plans_version"),
        CheckConstraint("(version = 1) = (supersedes_id IS NULL)", name="ck_payout_plans_supersedes"),
        CheckConstraint(_in("origin", PLAN_ORIGINS), name="ck_payout_plans_origin"),
        CheckConstraint("(origin = 'request') = (request_id IS NOT NULL)", name="ck_payout_plans_request"),
        CheckConstraint(_in("change", PLAN_CHANGES), name="ck_payout_plans_change"),
        CheckConstraint(_in("form", PLAN_FORMS), name="ck_payout_plans_form"),
        CheckConstraint("(form = 'lifelong' AND payments IS NULL AND end_month IS NULL)"
                        " OR (form = 'fixed_term' AND payments >= 60 AND end_month IS NOT NULL)",
                        name="ck_payout_plans_payments"),
        CheckConstraint("m_sek > 0", name="ck_payout_plans_amount"),
        CheckConstraint("length(checksum) = 64", name="ck_payout_plans_checksum"),
        Index("uq_payout_plans_supersedes", "supersedes_id", unique=True),
        Index("ix_payout_plans_effective", "effective_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payout_part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_parts.id", ondelete="RESTRICT"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_plans.id", ondelete="RESTRICT"), nullable=True)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_requests.id", ondelete="RESTRICT"), nullable=True)
    change: Mapped[str] = mapped_column(String(10), nullable=False)
    #: Ändringsmånaden: stängningen av denna månad genomför planen i steg 1
    effective_month: Mapped[date] = mapped_column(Date, nullable=False)
    #: Värderingen vid föregående månadsslut som G, B och M räknas på (aktuariell_grund.md §3)
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False)
    form: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Första rätt (originalstart); ändras inte efter start
    first_right: Mapped[date] = mapped_column(Date, nullable=False)
    payments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pauses: Mapped[list[Any]] = mapped_column(_JSON, nullable=False, default=list)
    end_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    consumed: Mapped[int] = mapped_column(Integer, nullable=False)
    capital_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    guarantee_sek_per_month: Mapped[Decimal] = mapped_column(_PRECISE, nullable=False)
    #: B = C / A_b(t, D_kvar) på utbetalningsgrunden
    capital_amount_sek: Mapped[Decimal] = mapped_column(_PRECISE, nullable=False)
    payout_basis_code: Mapped[str] = mapped_column(String(30), nullable=False)
    payout_basis_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    payout_factor: Mapped[Decimal] = mapped_column(_PRECISE, nullable=False)
    m_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    floor_sek: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    #: Hela beräkningen: garantidelarnas gamla och nya faktorer och belopp, regel- och villkorsversion
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    #: SHA-256 av `content`, granskningssumman som `decide_payout_plan` binder
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<PayoutPlan v{self.version} {self.form} från {self.first_right}>"


class PayoutSplit(Base):
    """Beslut om delning av en ej startad uttagsdel (PR-ITP1-024), genomfört i ändringsmånadens stängning."""

    __tablename__ = "payout_splits"
    __table_args__ = (
        CheckConstraint("new_part_number BETWEEN 2 AND 3", name="ck_payout_splits_number"),
        CheckConstraint("share >= 0.1 AND share <= 0.9", name="ck_payout_splits_share"),
        CheckConstraint("premium_receiver_number BETWEEN 1 AND 3", name="ck_payout_splits_receiver"),
        CheckConstraint("length(checksum) = 64", name="ck_payout_splits_checksum"),
        UniqueConstraint("from_part_id", "effective_month", name="uq_payout_splits_part_month"),
    )

    #: Stabilt id; den nya delens id härleds ur det
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_parts.id", ondelete="RESTRICT"), nullable=False, index=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_requests.id", ondelete="RESTRICT"), nullable=False)
    new_part_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Andel av den delade delens kapital och garanti som går till den nya delen
    share: Mapped[Decimal] = mapped_column(_SHARE, nullable=False)
    effective_month: Mapped[date] = mapped_column(Date, nullable=False)
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False)
    #: Primär premiemottagare med vikt 1 bland förmånens ej startade delar från ändringsmånaden (PR-ITP1-015)
    premium_receiver_number: Mapped[int] = mapped_column(Integer, nullable=False)
    capital_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<PayoutSplit {self.share} till del {self.new_part_number} från {self.effective_month}>"
