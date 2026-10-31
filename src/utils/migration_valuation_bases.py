"""Kontrollerad schemamigration för antagandebiblioteket `valuation_bases` (databasschema.md §9j, §12, B-042).

Två lägen, båda i en transaktion och med torrkörning som standard:

- **Ny tabell (A4):** skapar bara `valuation_bases` med index och lägger in startgrunderna.
- **Uppgradering (A5):** finns tabellen redan uppdateras villkoren för familj och ändamål till
  modellen (t.ex. familjen `AVK-SIM`) och startgrunder som saknas läggs in. Befintliga grunder
  ändras inte.

Efteråt prövas varje grunds kontrollsumma, och radantalen i övriga tabeller kontrolleras före
och efter; minsta avvikelse rullar tillbaka allt. DDL:en härleds ur modellen, så resultatet blir
detsamma som `create_all`. Körs med scripts/migrations/migrate_valuation_bases.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session
from sqlalchemy.schema import AddConstraint, CreateIndex, CreateTable

from models import Base, ValuationBasis
from models.valuation_basis import BASIS_FAMILIES
from services.valuation_bases import BasisError, default_rows, verify_checksum

TABLE = ValuationBasis.__tablename__
#: Tabeller som visar att det är försäkringsdatabasen
REQUIRED_TABLES = ("insured_persons", "product_parameters")
#: Villkor som följer modellens familjer och ändamål och därför kan behöva uppgraderas
SYNCED_CHECKS = {
    "ck_valuation_bases_family": tuple(BASIS_FAMILIES),
    "ck_valuation_bases_purpose": tuple(sorted(set(BASIS_FAMILIES.values()))),
}


@dataclass
class MigrationResult:
    already_applied: bool
    applied: bool
    statements: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)
    seeded: list[str] = field(default_factory=list)
    upgrade: bool = False


def compile_ddl(dialect) -> list[str]:
    """CREATE TABLE och index för `valuation_bases`, i körordning."""
    table = ValuationBasis.__table__
    return [
        str(CreateTable(table).compile(dialect=dialect)).strip(),
        *(str(CreateIndex(i).compile(dialect=dialect)) for i in sorted(table.indexes, key=lambda i: i.name)),
    ]


def _constraint(name: str):
    return next(c for c in ValuationBasis.__table__.constraints if c.name == name)


def stale_checks(conn: Connection) -> list[str]:
    """Villkor för familj och ändamål som saknar något av modellens värden."""
    defs = dict(conn.execute(text(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = CAST(:t AS regclass)"
    ), {"t": TABLE}).all())
    return [name for name, values in SYNCED_CHECKS.items()
            if name not in defs or not all(f"'{v}'" in defs[name] for v in values)]


def compile_upgrade(dialect, stale: list[str]) -> list[str]:
    statements = []
    for name in stale:
        statements.append(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {name}")
        statements.append(str(AddConstraint(_constraint(name)).compile(dialect=dialect)).strip())
    return statements


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


def _seed_and_verify(conn: Connection, rows: list[ValuationBasis], expected: list[str]) -> None:
    session = Session(bind=conn)
    session.add_all(rows)
    session.flush()
    try:
        for row in session.scalars(select(ValuationBasis)):
            verify_checksum(row)
    except BasisError as exc:
        raise RuntimeError(f"{exc} – allt rullas tillbaka") from exc
    stored = set(session.scalars(select(ValuationBasis.code)))
    if not set(expected) <= stored:
        raise RuntimeError(f"Startgrunderna {sorted(set(expected) - stored)} saknas – allt rullas tillbaka")


def migrate_valuation_bases(engine: Engine, dry_run: bool = True) -> MigrationResult:
    """Skapar eller uppgraderar tabellen (eller visar SQL:en med dry_run, standard). Idempotent."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError(f"Migrationen är skriven för Postgres (Lakebase), inte {engine.dialect.name}")
    seeds = default_rows()
    with engine.begin() as conn:
        exists = TABLE in _tables(conn)
        if exists:
            stale = stale_checks(conn)
            present = set(conn.execute(select(ValuationBasis.code)).scalars())
            missing = [r for r in seeds if r.code not in present]
            if not stale and not missing:
                return MigrationResult(already_applied=True, applied=False, upgrade=True)
            statements = compile_upgrade(engine.dialect, stale)
        else:
            missing = seeds
            statements = compile_ddl(engine.dialect)
        codes = [r.code for r in missing]
        before = _row_counts(conn)
        if dry_run:
            return MigrationResult(already_applied=False, applied=False, statements=statements,
                                   row_counts=before, seeded=codes, upgrade=exists)
        for statement in statements:
            conn.exec_driver_sql(statement)
        _seed_and_verify(conn, missing, [r.code for r in seeds])
        if exists and stale_checks(conn):
            raise RuntimeError("Villkoren blev inte uppgraderade – allt rullas tillbaka")
        after = _row_counts(conn)
        if after != before:
            raise RuntimeError(f"Radantalen ändrades ({before} → {after}) – allt rullas tillbaka")
    return MigrationResult(already_applied=False, applied=True, statements=statements, row_counts=after,
                           seeded=codes, upgrade=exists)
