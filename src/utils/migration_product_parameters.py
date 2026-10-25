"""Kontrollerad schemamigration för Fas 3c 3c-P1: tabellen `product_parameters` (databasschema §9h, §12, B-035).

Skapar bara `product_parameters` med index och lägger in startvärdena från 2023-01-01
(premieålder 25–66, satserna 4,5 och 30 %, brytpunkterna 7,5 och 30 IBB). Därefter
räknas varje ordinarie premierad om med de lästa parametrarna; minsta avvikelse
rullar tillbaka allt. Inga befintliga rader ändras och radantalen kontrolleras före
och efter. Allt i en transaktion; DDL:en härleds ur modellen. Körs med
scripts/migrations/migrate_product_parameters.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, inspect, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable

from models import (
    Base,
    BaseAmount,
    InsuredPerson,
    Policy,
    PolicyBenefit,
    PremiumTransaction,
    ProductParameter,
)
from services.errors import BlockedError
from services.operations.common import birth_date
from services.parameters import default_rows, premium_parameters
from skills.calculation.calculate_itp1_premium import calculate_itp1_premium

TABLE = ProductParameter.__tablename__
#: Tabellerna kontrollen av premierna läser
REQUIRED_TABLES = ("base_amounts", "premium_transactions", "policy_benefits", "policies", "insured_persons")


@dataclass
class PremiumCheck:
    checked: int = 0
    skipped: int = 0
    mismatches: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches


@dataclass
class MigrationResult:
    already_applied: bool
    applied: bool
    statements: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)
    seeded: int = 0
    check: PremiumCheck | None = None


def compile_ddl(dialect) -> list[str]:
    """CREATE TABLE och index för `product_parameters`, i körordning."""
    table = ProductParameter.__table__
    return [
        str(CreateTable(table).compile(dialect=dialect)).strip(),
        *(str(CreateIndex(i).compile(dialect=dialect)) for i in sorted(table.indexes, key=lambda i: i.name)),
    ]


def verify_premiums(session: Session) -> PremiumCheck:
    """Räknar om varje ordinarie premierad (ej makulerad, med lön) med parametrarna för dess månad.

    Rader som inte går att räkna om (saknat IBB-år eller oläsligt personnummer) räknas som
    överhoppade – de kunde inte heller räknas om före migrationen.
    """
    check = PremiumCheck()
    ibb = {row.year: row.income_base_amount_sek for row in session.scalars(select(BaseAmount))}
    params_by_month: dict = {}
    rows = session.execute(
        select(PremiumTransaction, InsuredPerson.personal_id_number)
        .join(PolicyBenefit, PremiumTransaction.benefit_id == PolicyBenefit.id)
        .join(Policy, PolicyBenefit.policy_id == Policy.id)
        .join(InsuredPerson, Policy.insured_person_id == InsuredPerson.id)
        .where(
            PremiumTransaction.transaction_type == "premium",
            PremiumTransaction.status != "cancelled",
            PremiumTransaction.pensionable_salary_sek.is_not(None),
        )
    ).all()
    for tx, pnr in rows:
        month = tx.period_month
        if month.year not in ibb:
            check.skipped += 1
            continue
        try:
            born = birth_date(pnr)
        except BlockedError:  # oläsligt personnummer
            check.skipped += 1
            continue
        if month not in params_by_month:
            params_by_month[month] = premium_parameters(session, month)
        calc = calculate_itp1_premium(
            tx.pensionable_salary_sek, ibb[month.year], birth_date=born, period_month=month,
            parameters=params_by_month[month],
        )
        check.checked += 1
        if calc.total_premium_sek != Decimal(tx.amount_sek):
            check.mismatches.append(f"{tx.id} {month:%Y-%m}: {tx.amount_sek} kr ≠ {calc.total_premium_sek} kr")
    return check


def has_table(conn: Connection) -> bool:
    tables = set(inspect(conn).get_table_names())
    missing = [t for t in REQUIRED_TABLES if t not in tables]
    if missing:
        raise RuntimeError(f"Tabellerna {', '.join(missing)} saknas – fel databas?")
    return TABLE in tables


def _row_counts(conn: Connection) -> dict[str, int]:
    names = set(inspect(conn).get_table_names())
    return {
        table.name: conn.execute(select(func.count()).select_from(table)).scalar_one()
        for table in Base.metadata.sorted_tables
        if table.name in names and table.name != TABLE
    }


def migrate_product_parameters(engine: Engine, dry_run: bool = True) -> MigrationResult:
    """Skapar och fyller `product_parameters` (eller visar SQL:en med dry_run, standard). Idempotent.

    Även torrkörningen räknar om premierna – inuti en transaktion som rullas tillbaka.
    """
    if engine.dialect.name != "postgresql":
        raise RuntimeError(f"Migrationen är skriven för Postgres (Lakebase), inte {engine.dialect.name}")
    statements = compile_ddl(engine.dialect)
    conn = engine.connect()
    tx = conn.begin()
    try:
        if has_table(conn):
            tx.rollback()
            return MigrationResult(already_applied=True, applied=False, statements=statements)
        before = _row_counts(conn)
        for statement in statements:
            conn.exec_driver_sql(statement)
        session = Session(bind=conn, autoflush=True)
        rows = default_rows()
        session.add_all(rows)
        session.flush()
        check = verify_premiums(session)
        after = _row_counts(conn)
        if after != before:
            raise RuntimeError(f"Radantalen ändrades ({before} → {after}) – allt rullas tillbaka")
        if not check.ok:
            raise RuntimeError(
                f"{len(check.mismatches)} av {check.checked} premier räknas inte om identiskt – allt rullas tillbaka: "
                + "; ".join(check.mismatches[:5])
            )
        result = MigrationResult(
            already_applied=False, applied=not dry_run, statements=statements,
            row_counts=after, seeded=len(rows), check=check,
        )
        if dry_run:
            tx.rollback()
        else:
            tx.commit()
        return result
    except Exception:
        if tx.is_active:
            tx.rollback()
        raise
    finally:
        conn.close()
