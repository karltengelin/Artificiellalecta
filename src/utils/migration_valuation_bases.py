"""Kontrollerad schemamigration för A4: antagandebiblioteket `valuation_bases` (databasschema.md §9j, §12, B-042).

Skapar bara `valuation_bases` med index och lägger in startgrunderna (SIM-HIST/G/B/R, SIM-V-2026-01
och kurvan FI-SIM-2026-10, `services/valuation_bases.py`). Varje startgrunds kontrollsumma prövas
efter inläsningen; minsta avvikelse rullar tillbaka allt. Inga befintliga rader ändras och radantalen
kontrolleras före och efter. Allt i en transaktion; DDL:en härleds ur modellen, så resultatet blir
detsamma som `create_all` på en tom databas. Körs med scripts/migrations/migrate_valuation_bases.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, inspect, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable

from models import Base, ValuationBasis
from services.valuation_bases import BasisError, default_rows, verify_checksum

TABLE = ValuationBasis.__tablename__
#: Tabeller som visar att det är försäkringsdatabasen
REQUIRED_TABLES = ("insured_persons", "product_parameters")


@dataclass
class MigrationResult:
    already_applied: bool
    applied: bool
    statements: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)
    seeded: list[str] = field(default_factory=list)


def compile_ddl(dialect) -> list[str]:
    """CREATE TABLE och index för `valuation_bases`, i körordning."""
    table = ValuationBasis.__table__
    return [
        str(CreateTable(table).compile(dialect=dialect)).strip(),
        *(str(CreateIndex(i).compile(dialect=dialect)) for i in sorted(table.indexes, key=lambda i: i.name)),
    ]


def _tables(conn: Connection) -> set[str]:
    tables = set(inspect(conn).get_table_names())
    missing = [t for t in REQUIRED_TABLES if t not in tables]
    if missing:
        raise RuntimeError(f"Tabellerna {', '.join(missing)} saknas – fel databas?")
    return tables


def _row_counts(conn: Connection) -> dict[str, int]:
    names = set(inspect(conn).get_table_names())
    return {
        table.name: conn.execute(select(func.count()).select_from(table)).scalar_one()
        for table in Base.metadata.sorted_tables
        if table.name in names and table.name != TABLE
    }


def migrate_valuation_bases(engine: Engine, dry_run: bool = True) -> MigrationResult:
    """Skapar tabellen och startgrunderna (eller visar SQL:en med dry_run, standard). Idempotent."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError(f"Migrationen är skriven för Postgres (Lakebase), inte {engine.dialect.name}")
    statements = compile_ddl(engine.dialect)
    seeds = [r.code for r in default_rows()]
    with engine.begin() as conn:
        if TABLE in _tables(conn):
            return MigrationResult(already_applied=True, applied=False, statements=statements)
        before = _row_counts(conn)
        if dry_run:
            return MigrationResult(already_applied=False, applied=False, statements=statements,
                                   row_counts=before, seeded=seeds)
        for statement in statements:
            conn.exec_driver_sql(statement)
        session = Session(bind=conn)
        session.add_all(default_rows())
        session.flush()
        try:
            for row in session.scalars(select(ValuationBasis)):
                verify_checksum(row)
        except BasisError as exc:
            raise RuntimeError(f"{exc} – allt rullas tillbaka") from exc
        stored = sorted(session.scalars(select(ValuationBasis.code)))
        if stored != sorted(seeds):
            raise RuntimeError(f"Startgrunderna blev {stored}, väntat {sorted(seeds)} – allt rullas tillbaka")
        after = _row_counts(conn)
        if after != before:
            raise RuntimeError(f"Radantalen ändrades ({before} → {after}) – allt rullas tillbaka")
    return MigrationResult(already_applied=False, applied=True, statements=statements, row_counts=after,
                           seeded=seeds)
