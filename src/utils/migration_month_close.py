"""Kontrollerad migration för månadsstängningen, paket B steg 3 (B-047, P1-PENSION-001 §7 och §12).

Vidgar i **en** transaktion `ledger_batches` (databasschema.md §7c) så att journalen kan bära
månadsstängningar och rättelser (Karls val S1 2026-11-19):

- villkoret `ck_ledger_batches_kind` får slagen `month_close` och `month_correction`;
- kolumnen `supersedes_id` (FK till `ledger_batches`) pekar på verifikationen en rättelse ersätter;
- villkoret `ck_ledger_batches_supersedes`: en rättelse och bara en rättelse har `supersedes_id`;
- unika index `uq_ledger_batches_one_close` (en stängning per månadsslut) och
  `uq_ledger_batches_supersedes` (varje verifikation ersätts högst en gång).

Inga rader ändras och inga nya tabeller skapas. Det ingående läget från steg 2 uppfyller de nya
villkoren (slaget `opening_s04`, ingen `supersedes_id`).

**Torrkörning är standard** och körs i en `READ ONLY`-transaktion. En skarp körning kontrollerar i
samma transaktion att tabellen fått modellens kolumner, villkor och index, att radantalen i alla
tabeller är oförändrade och att ingen agentroll har rättigheter på journalens tabeller. Minsta
avvikelse rullar tillbaka allt. Idempotent: är allt infört görs ingenting; är bara en del infört
stoppar migrationen. DDL:en härleds ur modellen, så resultatet blir detsamma som `create_all`.
Körs med scripts/migrations/migrate_month_close.py. Inget ingrepp i Lakebase utan Karls separata OK.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import CheckConstraint, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import AddConstraint, CreateIndex

from models import LedgerBatch
from utils.migration_capital_ledger import TABLES as LEDGER_TABLES
from utils.migration_capital_ledger import granted_to_agents
from utils.migration_premium_flow import (
    _agent_roles,
    _column_signature,
    _model_columns,
    _row_counts,
)

TABLE = LedgerBatch.__tablename__
COLUMN = "supersedes_id"
KIND_CHECK = "ck_ledger_batches_kind"
SUPERSEDES_CHECK = "ck_ledger_batches_supersedes"
INDEXES = ("uq_ledger_batches_one_close", "uq_ledger_batches_supersedes")
#: Villkoret som det ser ut i Lakebase efter steg 2 – för prov
KIND_CHECK_BEFORE = "kind IN ('opening_s04')"


@dataclass
class MigrationResult:
    already_applied: bool
    applied: bool
    statements: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)
    state: dict[str, bool] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def _check(name: str) -> CheckConstraint:
    return next(c for c in LedgerBatch.__table__.constraints if isinstance(c, CheckConstraint) and c.name == name)


def compile_ddl(dialect) -> list[str]:
    table = LedgerBatch.__table__
    column = table.c[COLUMN]
    statements = [
        (f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} {column.type.compile(dialect=dialect)} "
        f"REFERENCES {TABLE} (id) ON DELETE RESTRICT"),
        f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {KIND_CHECK}",
        str(AddConstraint(_check(KIND_CHECK), isolate_from_table=False).compile(dialect=dialect)).strip(),
        str(AddConstraint(_check(SUPERSEDES_CHECK), isolate_from_table=False).compile(dialect=dialect)).strip(),
    ]
    statements += [str(CreateIndex(i).compile(dialect=dialect)).strip()
                   for i in sorted(table.indexes, key=lambda i: i.name) if i.name in INDEXES]
    return statements


def _checks(conn: Connection) -> dict[str, str | None]:
    return {name: conn.execute(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = CAST(:t AS regclass) AND contype = 'c' AND conname = :n"), {"t": TABLE, "n": name}
    ).scalar_one_or_none() for name in (KIND_CHECK, SUPERSEDES_CHECK)}


def applied_state(conn: Connection) -> dict[str, bool]:
    """Vilka av migrationens delar som finns i databasen."""
    inspector = inspect(conn)
    checks = _checks(conn)
    indexes = {i["name"] for i in inspector.get_indexes(TABLE)}
    return {
        "column": COLUMN in {c["name"] for c in inspector.get_columns(TABLE)},
        "kind_check": bool(checks[KIND_CHECK]) and "month_close" in checks[KIND_CHECK]
        and "month_correction" in checks[KIND_CHECK],
        "supersedes_check": checks[SUPERSEDES_CHECK] is not None,
        **{name: name in indexes for name in INDEXES},
    }


def migrate_month_close(engine: Engine, dry_run: bool = True) -> MigrationResult:
    """Vidgar journalens verifikationer för stängning och rättelse (eller visar SQL:en med dry_run). Idempotent."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError(f"Migrationen är skriven för Postgres (Lakebase), inte {engine.dialect.name}")
    with engine.begin() as conn:
        if dry_run:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")  # torrkörningen kan inte skriva
        names = set(inspect(conn).get_table_names())
        missing = [t for t in LEDGER_TABLES if t not in names]
        if missing:
            raise RuntimeError(f"Kapitaljournalen saknas ({', '.join(missing)}) – migrate_capital_ledger.py först")
        state = applied_state(conn)
        if all(state.values()):
            if _column_signature(conn, TABLE) != _model_columns(LedgerBatch.__table__, conn.dialect):
                raise RuntimeError(f"Månadsstängningen är införd men {TABLE} har inte modellens kolumner")
            return MigrationResult(already_applied=True, applied=False, state=state)
        if any(state.values()):
            done = ", ".join(k for k, v in state.items() if v)
            raise RuntimeError(f"Migrationen är delvis införd ({done}) – stäm av innan något mer körs")
        before = _row_counts(conn, names)
        roles = _agent_roles(conn)
        problems = [f"Agentroller har redan rättigheter på journalen ({', '.join(g)})"
                    for g in [granted_to_agents(conn, roles)] if g]
        statements = compile_ddl(engine.dialect)
        result = MigrationResult(already_applied=False, applied=False, statements=statements, row_counts=before,
                                 state=state, problems=problems)
        if dry_run:
            return result
        if problems:
            raise RuntimeError("Hinder före migrationen: " + "; ".join(problems))
        for statement in statements:
            conn.exec_driver_sql(statement)
        after_state = applied_state(conn)
        if not all(after_state.values()):
            raise RuntimeError(f"Migrationen fick inte alla delar ({after_state}) – allt rullas tillbaka")
        if _column_signature(conn, TABLE) != _model_columns(LedgerBatch.__table__, conn.dialect):
            raise RuntimeError(f"{TABLE} fick inte modellens kolumner – allt rullas tillbaka")
        if granted := granted_to_agents(conn, roles):
            raise RuntimeError(f"Agentroller har rättigheter på journalen ({', '.join(granted)}) – allt rullas tillbaka")
        after = _row_counts(conn, names)
        if after != before:
            raise RuntimeError(f"Radantalen ändrades ({before} → {after}) – allt rullas tillbaka")
    result.applied = True
    result.state = after_state
    result.row_counts = after
    return result
