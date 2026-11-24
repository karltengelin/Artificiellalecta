"""SQLAlchemy-modeller för dödsfallsbesked, dödsfallsavräkning, återförda anspråk och dödsboets behörighet
(paket B steg 7, B-055).

Se 02_system/databasschema.md §7g och designstoppet P1-PENSION-001 §9.1 (PB9, PB10), Karls val Y1–Y14
2026-11-24. Raderna läggs bara till. Anspråket i `pension_claims` ändras aldrig (W1): ett anspråk efter
dödsmånaden återförs med en egen rad, och delens slut står i `payout_part_states` (`ended`, `death`).

- `death_reports`: dödsfallsbesked per person i en versionskedja (Y1, Y2). Läget är misstänkt, verifierat
  eller tillbakadraget. Varje version har dödsdag, rapportdag, mottagningsdag, källa med referens, kanal,
  aktör och – när den är verifierad – verifieringssätt med dokumentreferens. Ett besked ur en fil är unikt
  på (källsystem, besked-id).
- `death_settlements`: en rad per avräknad uttagsdel (Y6), unik på delen: beskedets version, dödsmånaden,
  stängningens verifikation, dödsmånadens anspråk, återförda anspråk, kapital till poolen och kvarstående
  skuld till dödsboet.
- `pension_claim_reversals`: ett återfört anspråk efter dödsmånaden (Y5), unikt på anspråket, med beloppen
  tillbaka till skulden, kundkapitalet och bolagskontot och den strukna ej finansierade resten.
- `estate_authorities`: dödsboets företrädare per avliden person i en versionskedja (Y10), med roll,
  behörighetshandling, verifiering, beslutsfattare och en kontoversion i `payout_accounts`.

Agentrollerna har inga rättigheter på tabellerna (P1-PENSION-001 §12, Y11).
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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

#: Beskedets läge (Y1)
REPORT_STATUSES = ("suspected", "verified", "withdrawn")
#: Varifrån beskedet kom: folkbokföringens avisering, anhörig, arbetsgivare, handläggare eller annan källa
REPORT_SOURCES = ("population_register", "relative", "employer", "case_handler", "other")
#: Hur dödsfallet verifierades (Y2): folkbokföringen, dödsbevis eller annan handling med referens
VERIFICATION_METHODS = ("population_register", "death_certificate", "other_document")
#: Dödsboets företrädare (Y10): dödsbodelägare med fullmakt, boutredningsman eller ombud
ESTATE_ROLES = ("estate_member", "estate_administrator", "representative")
#: Behörighetshandlingen (Y10): dödsfallsintyg med släktutredning, bouppteckning eller fullmakt
ESTATE_DOCUMENTS = ("death_certificate_with_family", "estate_inventory", "power_of_attorney")

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
_MONEY = Numeric(14, 2)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class DeathReport(Base):
    """En version av ett dödsfallsbesked för en person (PR-ITP1-010, Y1–Y2)."""

    __tablename__ = "death_reports"
    __table_args__ = (
        UniqueConstraint("insured_person_id", "version", name="uq_death_reports_version"),
        UniqueConstraint("supersedes_id", name="uq_death_reports_supersedes"),
        CheckConstraint(_in("status", REPORT_STATUSES), name="ck_death_reports_status"),
        CheckConstraint(_in("source", REPORT_SOURCES), name="ck_death_reports_source"),
        CheckConstraint("version >= 1", name="ck_death_reports_version"),
        CheckConstraint("(version = 1) = (supersedes_id IS NULL)", name="ck_death_reports_chain"),
        # Ett verifierat besked har dödsdag, verifieringssätt och dokumentreferens (PR-ITP1-010)
        CheckConstraint("status <> 'verified' OR (death_date IS NOT NULL AND verification_method IS NOT NULL "
                        "AND document_ref IS NOT NULL)", name="ck_death_reports_verified"),
        CheckConstraint(f"verification_method IS NULL OR {_in('verification_method', VERIFICATION_METHODS)}",
                        name="ck_death_reports_method"),
        CheckConstraint("death_date IS NULL OR death_date <= reported_on", name="ck_death_reports_dates"),
        CheckConstraint("reported_on <= received_date", name="ck_death_reports_received"),
        CheckConstraint("(source_system IS NULL) = (notice_id IS NULL)", name="ck_death_reports_notice"),
        CheckConstraint("length(checksum) = 64", name="ck_death_reports_checksum"),
        # Ett besked ur en fil registreras en gång per källsystem och besked-id (Y14)
        Index("uq_death_reports_notice", "source_system", "notice_id", unique=True,
              postgresql_where=text("notice_id IS NOT NULL"), sqlite_where=text("notice_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    insured_person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insured_persons.id", ondelete="RESTRICT"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("death_reports.id", ondelete="RESTRICT"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Dödsdagen; kan saknas i ett misstänkt besked
    death_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: Rapportdagen: dagen beskedet lämnades av källan (T-ITP1-005)
    reported_on: Mapped[date] = mapped_column(Date, nullable=False)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Källsystem och besked-id när beskedet kom i en fil (`import_death_notices`)
    source_system: Mapped[str | None] = mapped_column(String(60), nullable=True)
    notice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    verification_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    document_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: Personens status före verifieringen; återställs om beskedet dras tillbaka före avräkningen (Y2)
    previous_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<DeathReport v{self.version} {self.status} {self.death_date}>"


class DeathSettlement(Base):
    """Dödsfallsavräkningen av en uttagsdel i månadsstängningen (PR-ITP1-020 steg 6, Y6)."""

    __tablename__ = "death_settlements"
    __table_args__ = (
        UniqueConstraint("payout_part_id", name="uq_death_settlements_part"),
        CheckConstraint("EXTRACT(DAY FROM death_month) = 1", name="ck_death_settlements_month").ddl_if(
            dialect="postgresql"),
        CheckConstraint("CAST(strftime('%d', death_month) AS INTEGER) = 1", name="ck_death_settlements_month").ddl_if(
            dialect="sqlite"),
        CheckConstraint("capital_to_pool_sek >= 0 AND reversed_claims >= 0 AND estate_liability_sek >= 0",
                        name="ck_death_settlements_amounts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payout_part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_parts.id", ondelete="RESTRICT"), nullable=False)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("death_reports.id", ondelete="RESTRICT"), nullable=False, index=True)
    death_month: Mapped[date] = mapped_column(Date, nullable=False)
    #: Stängningens verifikation (`month_close`) där delen avräknades
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    #: Dödsmånadens anspråk, om delen hade rätt i dödsmånaden
    death_month_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pension_claims.id", ondelete="RESTRICT"), nullable=True)
    reversed_claims: Mapped[int] = mapped_column(Integer, nullable=False)
    capital_to_pool_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    #: Skulden till dödsboet efter avräkningen: anspråk med rätt senast dödsmånaden som inte är betalda
    estate_liability_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<DeathSettlement {self.death_month} {self.capital_to_pool_sek}>"


class PensionClaimReversal(Base):
    """Ett återfört anspråk efter dödsmånaden (Y5). Anspråket själv ändras aldrig (W1)."""

    __tablename__ = "pension_claim_reversals"
    __table_args__ = (
        UniqueConstraint("claim_id", name="uq_pension_claim_reversals_claim"),
        CheckConstraint("liability_sek >= 0 AND capital_sek >= 0 AND company_sek >= 0 AND unfunded_dropped_sek >= 0",
                        name="ck_pension_claim_reversals_amounts"),
        CheckConstraint("liability_sek = capital_sek + company_sek",
                        name="ck_pension_claim_reversals_sum").ddl_if(dialect="postgresql"),
        CheckConstraint("abs(liability_sek - capital_sek - company_sek) < 0.005",
                        name="ck_pension_claim_reversals_sum").ddl_if(dialect="sqlite"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pension_claims.id", ondelete="RESTRICT"), nullable=False)
    payout_part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_parts.id", ondelete="RESTRICT"), nullable=False, index=True)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("death_reports.id", ondelete="RESTRICT"), nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_batches.id", ondelete="RESTRICT"), nullable=False, index=True)
    #: Betalningsläget när anspråket återfördes: finansierat, ej finansierat, avvisat, återkommet eller förberett
    payment_state: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Skuldfört belopp som återförs: kundkapitalets debitering + bolagsstöd + senare finansiering
    liability_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    capital_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    company_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    unfunded_dropped_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<PensionClaimReversal {self.liability_sek}>"


class EstateAuthority(Base):
    """En version av dödsboets behörighet och konto för en avliden person (PR-ITP1-010, -026, Y10)."""

    __tablename__ = "estate_authorities"
    __table_args__ = (
        UniqueConstraint("insured_person_id", "version", name="uq_estate_authorities_version"),
        UniqueConstraint("supersedes_id", name="uq_estate_authorities_supersedes"),
        CheckConstraint(_in("role", ESTATE_ROLES), name="ck_estate_authorities_role"),
        CheckConstraint(_in("document_kind", ESTATE_DOCUMENTS), name="ck_estate_authorities_document"),
        CheckConstraint("version >= 1", name="ck_estate_authorities_version"),
        CheckConstraint("(version = 1) = (supersedes_id IS NULL)", name="ck_estate_authorities_chain"),
        CheckConstraint("NOT verified OR (verification_method IS NOT NULL AND verification_ref IS NOT NULL)",
                        name="ck_estate_authorities_verified"),
        CheckConstraint("length(checksum) = 64", name="ck_estate_authorities_checksum"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    insured_person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insured_persons.id", ondelete="RESTRICT"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("estate_authorities.id", ondelete="RESTRICT"), nullable=True)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("death_reports.id", ondelete="RESTRICT"), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    #: Företrädarens namn eller beteckning – personuppgift (B-006)
    representative: Mapped[str] = mapped_column(String(200), nullable=False)
    document_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    document_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verification_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verification_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_accounts.id", ondelete="RESTRICT"), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(100), nullable=False)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<EstateAuthority v{self.version} {self.role} {'verifierad' if self.verified else 'overifierad'}>"
