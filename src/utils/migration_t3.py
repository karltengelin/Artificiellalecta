"""Kontrollerad schemamigration för Fas 1f T3 (02_system/databasschema.md §8, §8b, §12).

Skapar tabellen `salary_reports` och lägger till
`premium_transactions.corrects_transaction_id` med främmande nyckel, CHECK och
index – i en transaktion (Postgres-DDL är transaktionell: allt eller inget).
DDL:en härleds ur modellerna, så resultatet blir detsamma som `create_all` på
en tom databas. Inga befintliga rader ändras; radantalen kontrolleras före och
efter. Körs med scripts/migrate_t3_schema.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, inspect, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import CreateIndex, CreateTable

from models import Base, PremiumTransaction, SalaryReport

NEW_COLUMN = "corrects_transaction_id"


@dataclass
class MigrationResult:
    already_applied: bool
    applied: bool
    statements: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)


def schema_state(conn: Connection) -> tuple[bool, bool]:
    """(salary_reports finns, premium_transactions har den nya kolumnen)."""
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    if "premium_transactions" not in tables:
        raise RuntimeError("Tabellen premium_transactions saknas – fel databas?")
    columns = {c["name"] for c in inspector.get_columns("premium_transactions")}
    return "salary_reports" in tables, NEW_COLUMN in columns


def compile_ddl(dialect) -> list[str]:
    """DDL i körordning, härledd ur modellerna.

    Constraints kompileras direkt i stället för med AddConstraint – den markerar
    constraint-objektet så att CREATE TABLE sedan hoppar över det, vilket skulle
    ändra modellernas metadata för resten av processen.
    """
    reports = SalaryReport.__table__
    premiums = PremiumTransaction.__table__
    column = premiums.c[NEW_COLUMN]
    foreign_key = next(iter(column.foreign_keys)).constraint
    check = next(c for c in premiums.constraints if c.name == "ck_premium_transactions_correction_type")
    index = next(i for i in premiums.indexes if NEW_COLUMN in i.columns)
    clauses = dialect.ddl_compiler(dialect, None)
    alter = f"ALTER TABLE {premiums.name}"
    return [
        str(CreateTable(reports).compile(dialect=dialect)).strip(),
        *(str(CreateIndex(i).compile(dialect=dialect)) for i in sorted(reports.indexes, key=lambda i: i.name)),
        f"{alter} ADD COLUMN {column.name} {column.type.compile(dialect=dialect)}",
        f"{alter} ADD {clauses.process(foreign_key)}",
        f"{alter} ADD {clauses.process(check)}",
        str(CreateIndex(index).compile(dialect=dialect)),
    ]


def _row_counts(conn: Connection) -> dict[str, int]:
    names = set(inspect(conn).get_table_names())
    return {
        table.name: conn.execute(select(func.count()).select_from(table)).scalar_one()
        for table in Base.metadata.sorted_tables
        if table.name in names and table.name != "salary_reports"
    }


def migrate_t3(engine: Engine, dry_run: bool = False) -> MigrationResult:
    """Kör migrationen (eller visar den med dry_run). Idempotent: redan migrerad databas lämnas orörd."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError(f"Migrationen är skriven för Postgres (Lakebase), inte {engine.dialect.name}")
    statements = compile_ddl(engine.dialect)
    with engine.begin() as conn:
        has_table, has_column = schema_state(conn)
        if has_table and has_column:
            return MigrationResult(already_applied=True, applied=False, statements=statements)
        if has_table != has_column:
            raise RuntimeError(
                "Databasen är delvis migrerad (salary_reports och corrects_transaction_id finns inte båda) – "
                "stoppa och undersök innan något mer körs"
            )
        before = _row_counts(conn)
        if dry_run:
            return MigrationResult(already_applied=False, applied=False, statements=statements, row_counts=before)
        for statement in statements:
            conn.exec_driver_sql(statement)
        if schema_state(conn) != (True, True):
            raise RuntimeError("Migrationen gav inte väntat schema – allt rullas tillbaka")
        after = _row_counts(conn)
        if after != before:
            raise RuntimeError(f"Radantalen ändrades ({before} → {after}) – allt rullas tillbaka")
    return MigrationResult(already_applied=False, applied=True, statements=statements, row_counts=after)
