"""Kontrollerad schemamigration för värderingsmotorns tabeller (databasschema.md §9k, §12, A6, B-042).

Skapar `valuation_extracts`, `valuation_runs` och `valuation_results` med index och villkor, tomma, i
en transaktion och med torrkörning som standard. Antagandebiblioteket (`valuation_bases`) ska finnas
först. Radantalen i övriga tabeller kontrolleras före och efter, och de nya tabellerna ska vara
tomma; minsta avvikelse rullar tillbaka allt. DDL:en härleds ur modellerna, så resultatet blir
detsamma som `create_all`. Idempotent: finns alla tre görs ingenting, finns bara några stoppar
migrationen. Körs med scripts/migrations/migrate_valuation_runs.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, inspect, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import CreateIndex, CreateTable

from models import Base, ValuationExtractRecord, ValuationResult, ValuationRun

#: I körordning: körningen pekar på utdraget, resultatet på körningen
MODELS = (ValuationExtractRecord, ValuationRun, ValuationResult)
TABLES = tuple(m.__tablename__ for m in MODELS)
#: Tabeller som visar att det är försäkringsdatabasen med antagandebiblioteket
REQUIRED_TABLES = ("insured_persons", "product_parameters", "valuation_bases")


@dataclass
class MigrationResult:
    already_applied: bool
    applied: bool
    statements: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)


def compile_ddl(dialect) -> list[str]:
    """CREATE TABLE och index för de tre tabellerna, i körordning."""
    statements = []
    for model in MODELS:
        table = model.__table__
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip())
        statements += [str(CreateIndex(i).compile(dialect=dialect)) for i in sorted(table.indexes, key=lambda i: i.name)]
    return statements


def _row_counts(conn: Connection, names: set[str]) -> dict[str, int]:
    return {
        table.name: conn.execute(select(func.count()).select_from(table)).scalar_one()
        for table in Base.metadata.sorted_tables
        if table.name in names
    }


def migrate_valuation_runs(engine: Engine, dry_run: bool = True) -> MigrationResult:
    """Skapar tabellerna (eller visar SQL:en med dry_run, standard). Idempotent."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError(f"Migrationen är skriven för Postgres (Lakebase), inte {engine.dialect.name}")
    with engine.begin() as conn:
        names = set(inspect(conn).get_table_names())
        missing = [t for t in REQUIRED_TABLES if t not in names]
        if missing:
            raise RuntimeError(f"Tabellerna {', '.join(missing)} saknas – fel databas eller antagandebiblioteket "
                               "inte infört (migrate_valuation_bases.py)?")
        present = [t for t in TABLES if t in names]
        if len(present) == len(TABLES):
            return MigrationResult(already_applied=True, applied=False)
        if present:
            raise RuntimeError(f"Bara {', '.join(present)} finns – ett tidigare försök? Stäm av innan något görs")
        others = names - set(TABLES)
        before = _row_counts(conn, others)
        statements = compile_ddl(engine.dialect)
        if dry_run:
            return MigrationResult(already_applied=False, applied=False, statements=statements, row_counts=before)
        for statement in statements:
            conn.exec_driver_sql(statement)
        created = set(inspect(conn).get_table_names())
        if not set(TABLES) <= created:
            raise RuntimeError("Tabellerna skapades inte – allt rullas tillbaka")
        empty = _row_counts(conn, set(TABLES))
        if any(empty.values()):
            raise RuntimeError(f"De nya tabellerna är inte tomma ({empty}) – allt rullas tillbaka")
        after = _row_counts(conn, others)
        if after != before:
            raise RuntimeError(f"Radantalen ändrades ({before} → {after}) – allt rullas tillbaka")
    return MigrationResult(already_applied=False, applied=True, statements=statements, row_counts=after)
