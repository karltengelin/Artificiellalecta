"""Kontrollerad schemamigration för Fas 3c 3c-2: flödesmotorns tabeller (databasschema.md §9i, §12).

Skapar `flows`, `flow_steps` och `flow_gate_decisions` med sina index – inga andra tabeller,
även om modellerna har fler som inte finns i databasen (t.ex. kapitalförvaltningens).
`create_all` används därför inte. Allt i en transaktion; DDL:en härleds ur modellerna, så
resultatet blir detsamma som `create_all` på en tom databas. Inga befintliga rader ändras;
radantalen kontrolleras före och efter. Körs med scripts/migrations/migrate_flows.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, inspect, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import CreateIndex, CreateTable

from models import Base, Flow, FlowGateDecision, FlowStep

#: I beroendeordning: stegen och besluten pekar på flödet
FLOW_TABLES = (Flow.__table__, FlowStep.__table__, FlowGateDecision.__table__)
FLOW_TABLE_NAMES = tuple(t.name for t in FLOW_TABLES)
#: Tabeller som visar att det är försäkringsdatabasen (flödena länkar till godkännandekön)
REQUIRED_TABLES = ("insured_persons", "approval_requests")


@dataclass
class MigrationResult:
    already_applied: bool
    applied: bool
    statements: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)


def compile_ddl(dialect) -> list[str]:
    """CREATE TABLE och index för flödestabellerna, i körordning."""
    statements = []
    for table in FLOW_TABLES:
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip())
        statements += [str(CreateIndex(i).compile(dialect=dialect)) for i in sorted(table.indexes, key=lambda i: i.name)]
    return statements


def existing_flow_tables(conn: Connection) -> set[str]:
    tables = set(inspect(conn).get_table_names())
    missing = [t for t in REQUIRED_TABLES if t not in tables]
    if missing:
        raise RuntimeError(f"Tabellerna {', '.join(missing)} saknas – fel databas?")
    return tables & set(FLOW_TABLE_NAMES)


def _row_counts(conn: Connection) -> dict[str, int]:
    names = set(inspect(conn).get_table_names())
    return {
        table.name: conn.execute(select(func.count()).select_from(table)).scalar_one()
        for table in Base.metadata.sorted_tables
        if table.name in names and table.name not in FLOW_TABLE_NAMES
    }


def migrate_flows(engine: Engine, dry_run: bool = True) -> MigrationResult:
    """Skapar flödestabellerna (eller visar SQL:en med dry_run, standard). Idempotent."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError(f"Migrationen är skriven för Postgres (Lakebase), inte {engine.dialect.name}")
    statements = compile_ddl(engine.dialect)
    with engine.begin() as conn:
        existing = existing_flow_tables(conn)
        if existing == set(FLOW_TABLE_NAMES):
            return MigrationResult(already_applied=True, applied=False, statements=statements)
        if existing:
            raise RuntimeError(
                f"Bara en del av flödestabellerna finns ({', '.join(sorted(existing))}) – rättas manuellt"
            )
        before = _row_counts(conn)
        if dry_run:
            return MigrationResult(already_applied=False, applied=False, statements=statements, row_counts=before)
        for statement in statements:
            conn.exec_driver_sql(statement)
        if existing_flow_tables(conn) != set(FLOW_TABLE_NAMES):
            raise RuntimeError("Migrationen gav inte väntat schema – allt rullas tillbaka")
        after = _row_counts(conn)
        if after != before:
            raise RuntimeError(f"Radantalen ändrades ({before} → {after}) – allt rullas tillbaka")
    return MigrationResult(already_applied=False, applied=True, statements=statements, row_counts=after)
