"""Kontrollerad schemamigration för Fas 5 F5-1: tabellen `cases` (02_system/databasschema.md §9g, §12).

Skapar bara `cases` med sina index – inga andra tabeller, även om modellerna har fler som
inte finns i databasen (t.ex. kapitalförvaltningens). `create_all` används därför inte.
Allt i en transaktion; DDL:en härleds ur modellen, så resultatet blir detsamma som
`create_all` på en tom databas. Inga befintliga rader ändras; radantalen kontrolleras
före och efter. Körs med scripts/migrations/migrate_cases.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, inspect, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import CreateIndex, CreateTable

from models import Base, Case

#: Tabellerna som ärendets främmande nycklar pekar på
REQUIRED_TABLES = ("insured_persons", "policies", "employers")


@dataclass
class MigrationResult:
    already_applied: bool
    applied: bool
    statements: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)


def compile_ddl(dialect) -> list[str]:
    """CREATE TABLE och index för `cases`, i körordning."""
    table = Case.__table__
    return [
        str(CreateTable(table).compile(dialect=dialect)).strip(),
        *(str(CreateIndex(i).compile(dialect=dialect)) for i in sorted(table.indexes, key=lambda i: i.name)),
    ]


def has_cases(conn: Connection) -> bool:
    tables = set(inspect(conn).get_table_names())
    missing = [t for t in REQUIRED_TABLES if t not in tables]
    if missing:
        raise RuntimeError(f"Tabellerna {', '.join(missing)} saknas – fel databas?")
    return "cases" in tables


def _row_counts(conn: Connection) -> dict[str, int]:
    names = set(inspect(conn).get_table_names())
    return {
        table.name: conn.execute(select(func.count()).select_from(table)).scalar_one()
        for table in Base.metadata.sorted_tables
        if table.name in names and table.name != "cases"
    }


def migrate_cases(engine: Engine, dry_run: bool = True) -> MigrationResult:
    """Skapar `cases` (eller visar SQL:en med dry_run, standard). Idempotent."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError(f"Migrationen är skriven för Postgres (Lakebase), inte {engine.dialect.name}")
    statements = compile_ddl(engine.dialect)
    with engine.begin() as conn:
        if has_cases(conn):
            return MigrationResult(already_applied=True, applied=False, statements=statements)
        before = _row_counts(conn)
        if dry_run:
            return MigrationResult(already_applied=False, applied=False, statements=statements, row_counts=before)
        for statement in statements:
            conn.exec_driver_sql(statement)
        if not has_cases(conn):
            raise RuntimeError("Migrationen gav inte väntat schema – allt rullas tillbaka")
        after = _row_counts(conn)
        if after != before:
            raise RuntimeError(f"Radantalen ändrades ({before} → {after}) – allt rullas tillbaka")
    return MigrationResult(already_applied=False, applied=True, statements=statements, row_counts=after)
