"""Kontrollerad migration av den operativa kapital- och garantijournalen, paket B steg 2 (B-047, P1-PENSION-001 §6 och §12).

Inför i **en** transaktion de fyra tabellerna `ledger_batches`, `ledger_guarantee_parts`,
`ledger_capital_entries` och `ledger_controls`, tomma och med index och villkor
(databasschema.md §7c). Inga befintliga tabeller, villkor eller rader ändras. Övergången från S-04
(det ingående läget) är ett eget ingrepp efter migrationen, med operationen `open_capital_ledger`
och Karls separata OK (§12 punkt 3).

**Torrkörning är standard** och körs i en `READ ONLY`-transaktion: den visar SQL, schemaskillnader i
befintliga tabeller, hinder och radantal, men kan inte skriva. En skarp körning kontrollerar i samma
transaktion att tabellerna har modellens kolumner och är tomma, att radantalen i övriga tabeller är
oförändrade och att ingen agentroll har rättigheter på de nya tabellerna (§12: inga rättigheter i
första versionen). Minsta avvikelse rullar tillbaka allt. Idempotent: är allt infört görs ingenting;
är bara en del infört stoppar migrationen.

DDL:en härleds ur modellerna, så resultatet blir detsamma som `create_all`. Körs med
scripts/migrations/migrate_capital_ledger.py. Inget ingrepp i Lakebase utan Karls separata OK.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import CreateIndex, CreateTable

from models import LedgerBatch, LedgerCapitalEntry, LedgerControl, LedgerGuaranteePart
from utils.migration_premium_flow import (
    PRIVILEGES,
    _agent_roles,
    _column_signature,
    _model_columns,
    _row_counts,
    default_privilege_problems,
    schema_drift,
)

MODELS = (LedgerBatch, LedgerGuaranteePart, LedgerCapitalEntry, LedgerControl)
TABLES = tuple(m.__tablename__ for m in MODELS)
#: Tabellerna journalen pekar på: uttagsdelarna (steg 1), premier, allokeringar (paket A) och utdragen (A6)
REQUIRED_TABLES = ("policies", "policy_benefits", "payout_parts", "payout_part_states", "premium_transactions",
                   "bank_events", "payment_allocations", "valuation_extracts")


@dataclass
class MigrationResult:
    already_applied: bool
    applied: bool
    statements: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)
    drift: dict[str, list[str]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def compile_ddl(dialect) -> list[str]:
    statements = []
    for model in MODELS:
        table = model.__table__
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip())
        statements += [str(CreateIndex(i).compile(dialect=dialect)) for i in sorted(table.indexes, key=lambda i: i.name)]
    return statements


def granted_to_agents(conn: Connection, roles: list[str]) -> list[str]:
    return [f"{role} på {table}" for role in roles for table in TABLES
            if conn.execute(text("SELECT has_table_privilege(:r, CAST(:t AS regclass), :p)"),
                            {"r": role, "t": table, "p": PRIVILEGES}).scalar_one()]


def migrate_capital_ledger(engine: Engine, dry_run: bool = True) -> MigrationResult:
    """Inför journalens tabeller tomma (eller visar SQL:en med dry_run, standard). Idempotent."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError(f"Migrationen är skriven för Postgres (Lakebase), inte {engine.dialect.name}")
    with engine.begin() as conn:
        if dry_run:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")  # torrkörningen kan inte skriva
        names = set(inspect(conn).get_table_names())
        missing = [t for t in REQUIRED_TABLES if t not in names]
        if missing:
            raise RuntimeError(f"Tabellerna {', '.join(missing)} saknas – fel databas eller tidigare migration "
                               "inte körd (migrate_premium_flow.py, migrate_payout_parts.py, migrate_valuation_runs.py)?")
        present = [t for t in TABLES if t in names]
        if len(present) == len(TABLES):
            for model in MODELS:
                if _column_signature(conn, model.__tablename__) != _model_columns(model.__table__, conn.dialect):
                    raise RuntimeError(f"Journalen är införd men {model.__tablename__} har inte modellens kolumner")
            return MigrationResult(already_applied=True, applied=False)
        if present:
            raise RuntimeError(f"Journalen är delvis införd (tabeller: {', '.join(present)}) – stäm av innan något "
                               "mer körs")
        others = names - set(TABLES)
        before = _row_counts(conn, others)
        drift = schema_drift(conn, others)
        roles = _agent_roles(conn)
        problems = default_privilege_problems(conn, roles)
        statements = compile_ddl(engine.dialect)
        result = MigrationResult(already_applied=False, applied=False, statements=statements, row_counts=before,
                                 drift=drift, problems=problems)
        if dry_run:
            return result
        if problems:
            raise RuntimeError("Hinder före migrationen: " + "; ".join(problems))
        for statement in statements:
            conn.exec_driver_sql(statement)
        if not set(TABLES) <= set(inspect(conn).get_table_names()):
            raise RuntimeError("Tabellerna skapades inte – allt rullas tillbaka")
        for model in MODELS:
            if _column_signature(conn, model.__tablename__) != _model_columns(model.__table__, conn.dialect):
                raise RuntimeError(f"Tabellen {model.__tablename__} fick inte modellens kolumner – allt rullas tillbaka")
        empty = _row_counts(conn, set(TABLES))
        if any(empty.values()):
            raise RuntimeError(f"De nya tabellerna är inte tomma ({empty}) – allt rullas tillbaka")
        if granted := granted_to_agents(conn, roles):
            raise RuntimeError(f"Agentroller har rättigheter på nya tabeller ({', '.join(granted)}) – allt rullas tillbaka")
        after = _row_counts(conn, others)
        if after != before:
            raise RuntimeError(f"Radantalen ändrades ({before} → {after}) – allt rullas tillbaka")
    result.applied = True
    result.row_counts = after
    return result
