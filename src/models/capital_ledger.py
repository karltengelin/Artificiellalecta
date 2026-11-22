"""SQLAlchemy-modeller för den operativa kapital- och garantijournalen (paket B steg 2, B-047 punkt 4).

Se 02_system/databasschema.md §7c och designstoppet P1-PENSION-001 §6 (PB4). Journalen är
bolagets enda källa för pensionskapitalet C och garantin G efter övergången från S-04. Posterna
är oföränderliga; en rättelse är en ny länkad post, aldrig en ändring.

- `ledger_batches`: en verifikation per bokning – det ingående läget från S-04 per 2026-10-31
  (`opening_s04`, steg 2), en månadsstängning per månad (`month_close`) och rättelser av en stängd
  månad (`month_correction`, steg 3). En rättelse pekar på verifikationen den ersätter
  (`supersedes_id`), och varje verifikation ersätts högst en gång, så versionerna bildar en rak kedja.
  Varje kapitalpost, garantidel och kontrollpost pekar på sin verifikation.
- `ledger_guarantee_parts`: en garantidel per ursprung och uttagsdel, med premien P_j, mottagning,
  värdedag, premieperiod, referensplan, grund med kontrollsumma, A_g och G_j i hög precision.
  Ursprunget är antingen en S-04-premierad (`s04_premium`) eller en allokering i paket A
  (`payment_allocation`). Delning och omräkning (steg 4) ger nya versioner med länk; den
  historiska grunden byts aldrig.
- `ledger_capital_entries`: kapitalposter per konto, uttagsdel och kapitalspår med belopp i ören,
  in- och utgående spårsaldo och orsak. Ett kapitalspår är (uttagsdel, ursprungets garantidel).
  Kontona hålls isär: kundkapital, betalningsskuld, skatteskuld, arvsvinstpool, bolagskonto och
  avstämningskonto – kapital, skuld och pool blandas aldrig i samma saldo.
- `ledger_controls`: kontrollposter för avstämningens led, utan ekonomisk effekt.

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

#: Verifikationens slag: ingående läge (steg 2), månadsstängning och rättelse av en stängd månad (steg 3) och
#: bolagets kapitalinsättning (steg 5, PR-ITP1-028, Karls val W7)
BATCH_KINDS = ("opening_s04", "month_close", "month_correction", "company_capital")
#: Märkning av posternas ursprung, samma värden som värderingsmotorns källor (`valuation_runs.source`)
SOURCES = ("reconstructed_s04", "ledger")
#: Journalens konton (P1-PENSION-001 §6.1). Steg 2 använder bara kundkapitalet
ACCOUNTS = ("customer_capital", "payment_liability", "tax_liability", "inheritance_pool", "company", "suspense")
#: Kapitalpostens orsak (§6.1). `opening` är det ingående saldot från S-04 (beslutat av Karl 2026-11-14);
#: `company_capital` är ägarens dokumenterade insättning på bolagskontot (steg 5, Karls val W7)
ENTRY_REASONS = ("opening", "premium", "return", "fee", "tax", "pension_debit", "company_support",
                 "pool_in", "pool_out", "split", "company_capital")
#: Konton som aldrig får bli negativa utöver kundkapitalet (steg 5): betalningsskulden och bolagskontot
NON_NEGATIVE_ACCOUNTS = ("payment_liability", "company")
#: Garantidelens ursprung: en premierad i S-04 eller en allokering i paket A (PA6)
GUARANTEE_ORIGINS = ("s04_premium", "payment_allocation")
#: Varför en garantidelsversion finns: premien själv (version 1), delning eller omräkning (steg 4)
GUARANTEE_REASONS = ("premium", "split", "recalculation")
#: Planen som A_g räknas på: referensplanen (aktuariell_grund.md §3) eller en beslutad uttagsplan
#: (`plan`, paket B steg 4, V1) – då pekar `plan_id` på planversionen
PLAN_KINDS = ("reference_lifelong", "plan")

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")
_MONEY = Numeric(14, 2)
_PRECISE = Numeric(24, 10)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class LedgerBatch(Base):
    """En verifikation: en bokning i journalen med källor, sammanställning och kontrollsumma."""

    __tablename__ = "ledger_batches"
    __table_args__ = (
        CheckConstraint(_in("kind", BATCH_KINDS), name="ck_ledger_batches_kind"),
        CheckConstraint(_in("source", SOURCES), name="ck_ledger_batches_source"),
        CheckConstraint("length(checksum) = 64", name="ck_ledger_batches_checksum"),
        # Det ingående läget bygger på ett sparat S-04-utdrag med kontrollsumma
        CheckConstraint("kind <> 'opening_s04' OR (extract_id IS NOT NULL AND length(extract_checksum) = 64)",
                        name="ck_ledger_batches_opening_extract"),
        # Högst ett ingående läge: övergången görs en gång
        Index("uq_ledger_batches_one_opening", "kind", unique=True,
              postgresql_where=text("kind = 'opening_s04'"), sqlite_where=text("kind = 'opening_s04'")),
        # En rättelse och bara en rättelse pekar på verifikationen den ersätter (steg 3, Karls val S1)
        CheckConstraint("(kind = 'month_correction') = (supersedes_id IS NOT NULL)",
                        name="ck_ledger_batches_supersedes"),
        # En stängning per månadsslut; senare versioner är rättelser
        Index("uq_ledger_batches_one_close", "period_end", unique=True,
              postgresql_where=text("kind = 'month_close'"), sqlite_where=text("kind = 'month_close'")),
        # Varje verifikation ersätts högst en gång: versionerna bildar en rak kedja
        Index("uq_ledger_batches_supersedes", "supersedes_id", unique=True,
              postgresql_where=text("supersedes_id IS NOT NULL"), sqlite_where=text("supersedes_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Dagen saldona gäller: månadens sista dag
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    extract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("valuation_extracts.id", ondelete="RESTRICT"), nullable=True,
    )
    extract_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Sammanställningen som granskades: metod, källor, totaler, kontroller och ej överförda försäkringar
    content: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    #: SHA-256 av `content`; samma som granskningssumman operationen binder
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    #: Verifikationen som en rättelse ersätter (steg 3); NULL för ingående läge och stängning. Läses bara när
    #: den behövs, så att journalens läsningar fungerar i en databas där steg 3:s migration inte är körd
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_batches.id", ondelete="RESTRICT"), nullable=True, deferred=True,
    )

    def __repr__(self) -> str:
        return f"<LedgerBatch {self.kind} {self.period_end}>"


class LedgerGuaranteePart(Base):
    """En garantidel G_j på exakt en uttagsdel, med ursprung, grund och referensplan."""

    __tablename__ = "ledger_guarantee_parts"
    __table_args__ = (
        CheckConstraint(_in("origin_kind", GUARANTEE_ORIGINS), name="ck_ledger_guarantee_parts_origin_kind"),
        CheckConstraint(
            "(origin_kind = 's04_premium' AND premium_transaction_id IS NOT NULL AND payment_allocation_id IS NULL)"
            " OR (origin_kind = 'payment_allocation' AND payment_allocation_id IS NOT NULL)",
            name="ck_ledger_guarantee_parts_origin",
        ),
        CheckConstraint(_in("reason", GUARANTEE_REASONS), name="ck_ledger_guarantee_parts_reason"),
        CheckConstraint(
            "(version = 1 AND supersedes_id IS NULL AND reason = 'premium')"
            " OR (version > 1 AND supersedes_id IS NOT NULL AND reason <> 'premium')",
            name="ck_ledger_guarantee_parts_version",
        ),
        CheckConstraint(_in("plan_kind", PLAN_KINDS), name="ck_ledger_guarantee_parts_plan"),
        CheckConstraint("(plan_kind = 'plan') = (plan_id IS NOT NULL)", name="ck_ledger_guarantee_parts_plan_id"),
        CheckConstraint(_in("source", SOURCES), name="ck_ledger_guarantee_parts_source"),
        CheckConstraint("premium_sek > 0", name="ck_ledger_guarantee_parts_premium"),
        CheckConstraint("factor > 0 AND guarantee_sek_per_month >= 0", name="ck_ledger_guarantee_parts_amounts"),
        CheckConstraint("length(basis_checksum) = 64", name="ck_ledger_guarantee_parts_basis_checksum"),
        # En premie bildar ett ursprung: en S-04-premierad eller en allokering ger högst en version 1
        Index("uq_ledger_guarantee_parts_premium", "premium_transaction_id", unique=True,
              postgresql_where=text("origin_kind = 's04_premium' AND version = 1"),
              sqlite_where=text("origin_kind = 's04_premium' AND version = 1")),
        Index("uq_ledger_guarantee_parts_allocation", "payment_allocation_id", unique=True,
              postgresql_where=text("version = 1"), sqlite_where=text("version = 1")),
        Index("ix_ledger_guarantee_parts_supersedes", "supersedes_id"),
        Index("ix_ledger_guarantee_parts_plan", "plan_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_batches.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    payout_part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_parts.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    origin_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Premieraden: ursprunget för S-04, och den fakturerade premieraden för en allokering
    premium_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("premium_transactions.id", ondelete="RESTRICT"), nullable=True,
    )
    payment_allocation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_allocations.id", ondelete="RESTRICT"), nullable=True,
    )
    #: P_j: mottagen nettopremie som garantigrund (PR-ITP1-008)
    premium_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    #: Mottagningsmånadens första dag; premien tillförs vid månadsslut (PR-ITP1-020 steg 4)
    received_month: Mapped[date] = mapped_column(Date, nullable=False)
    value_date: Mapped[date] = mapped_column(Date, nullable=False)
    plan_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    plan_start: Mapped[date] = mapped_column(Date, nullable=False)
    #: Planversionen A_g räknas på när `plan_kind = 'plan'` (steg 4). Läses bara när den behövs och sätts
    #: bara för planbaserade versioner, så att journalen fungerar där steg 4:s migration inte är körd
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_plans.id", ondelete="RESTRICT"), nullable=True, deferred=True,
    )
    basis_code: Mapped[str] = mapped_column(String(30), nullable=False)
    basis_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    #: A_g vid värdedagen på referensplanen
    factor: Mapped[Decimal] = mapped_column(_PRECISE, nullable=False)
    #: G_j i kronor per månad, hög precision; avrundas först i rapporteringen
    guarantee_sek_per_month: Mapped[Decimal] = mapped_column(_PRECISE, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reason: Mapped[str] = mapped_column(String(20), nullable=False, default="premium")
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_guarantee_parts.id", ondelete="RESTRICT"), nullable=True,
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<LedgerGuaranteePart {self.origin_kind} v{self.version} {self.guarantee_sek_per_month}>"


class LedgerCapitalEntry(Base):
    """En kapitalpost: konto, uttagsdel och kapitalspår, belopp och spårsaldo före och efter."""

    __tablename__ = "ledger_capital_entries"
    __table_args__ = (
        CheckConstraint(_in("account", ACCOUNTS), name="ck_ledger_capital_entries_account"),
        CheckConstraint(_in("reason", ENTRY_REASONS), name="ck_ledger_capital_entries_reason"),
        CheckConstraint(_in("source", SOURCES), name="ck_ledger_capital_entries_source"),
        # Kundkapitalet förs per uttagsdel och kapitalspår (ursprungets garantidel)
        CheckConstraint("account <> 'customer_capital' OR (payout_part_id IS NOT NULL AND origin_id IS NOT NULL)",
                        name="ck_ledger_capital_entries_track"),
        CheckConstraint("balance_after_sek = balance_before_sek + amount_sek",
                        name="ck_ledger_capital_entries_balance").ddl_if(dialect="postgresql"),
        # Samma regel i testdatabasen; SQLite räknar NUMERIC som flyttal, så likheten prövas på halva ören
        CheckConstraint("abs(balance_after_sek - balance_before_sek - amount_sek) < 0.005",
                        name="ck_ledger_capital_entries_balance").ddl_if(dialect="sqlite"),
        # Ingen del har negativt C (P1-PENSION-001 §11, acceptans)
        CheckConstraint("account <> 'customer_capital' OR (balance_before_sek >= 0 AND balance_after_sek >= 0)",
                        name="ck_ledger_capital_entries_non_negative"),
        CheckConstraint("reason <> 'opening' OR balance_before_sek = 0", name="ck_ledger_capital_entries_opening"),
        # Betalningsskuld och bolagskonto blir aldrig negativa; ett ej finansierat anspråk står på anspråket (W8)
        CheckConstraint(f"account NOT IN {NON_NEGATIVE_ACCOUNTS!r} OR (balance_before_sek >= 0 AND balance_after_sek >= 0)",
                        name="ck_ledger_capital_entries_accounts"),
        CheckConstraint("EXTRACT(DAY FROM month) = 1", name="ck_ledger_capital_entries_month").ddl_if(
            dialect="postgresql"),
        # Samma regel i testdatabasen (SQLite saknar EXTRACT)
        CheckConstraint("CAST(strftime('%d', month) AS INTEGER) = 1", name="ck_ledger_capital_entries_month").ddl_if(
            dialect="sqlite"),
        UniqueConstraint("batch_id", "account", "payout_part_id", "origin_id", "reason",
                         name="uq_ledger_capital_entries_posting"),
        Index("ix_ledger_capital_entries_track", "payout_part_id", "origin_id", "month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_batches.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    account: Mapped[str] = mapped_column(String(30), nullable=False)
    payout_part_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payout_parts.id", ondelete="RESTRICT"), nullable=True,
    )
    #: Kapitalspårets ursprung: garantidelen (version 1) som premien gav
    origin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_guarantee_parts.id", ondelete="RESTRICT"), nullable=True, index=True,
    )
    #: Månaden posten hör till (första dagen)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    balance_before_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    balance_after_sek: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<LedgerCapitalEntry {self.account} {self.reason} {self.amount_sek}>"


class LedgerControl(Base):
    """En kontrollpost: avstämningens led med väntat och faktiskt värde, skillnad, källor och utfall."""

    __tablename__ = "ledger_controls"
    __table_args__ = (UniqueConstraint("batch_id", "step", name="uq_ledger_controls_step"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger_batches.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    step: Mapped[str] = mapped_column(String(60), nullable=False)
    expected: Mapped[str | None] = mapped_column(String(100), nullable=True)
    actual: Mapped[str | None] = mapped_column(String(100), nullable=True)
    difference: Mapped[Decimal | None] = mapped_column(_PRECISE, nullable=True)
    sources: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<LedgerControl {self.step} {'ok' if self.passed else 'AVVIKER'}>"
