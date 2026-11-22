"""Kontrollerad migration för uttagsplaner, paket B steg 4 (B-047 punkt 3, P1-PENSION-001 §5 och §12).

Inför i **en** transaktion (databasschema.md §7d, Karls val V1 2026-11-21):

1. tabellerna `payout_requests`, `payout_plans` och `payout_splits` med index och villkor;
2. ärendetyperna `payout_request` och `payout_review` i villkoret `ck_cases_type` (vidgas bara);
3. i `ledger_guarantee_parts`: kolumnen `plan_id` (FK till `payout_plans`), planslaget `plan` i
   `ck_ledger_guarantee_parts_plan`, villkoret `ck_ledger_guarantee_parts_plan_id` (planslaget `plan`
   exakt när `plan_id` är satt) och indexet `ix_ledger_guarantee_parts_plan`.

Inga rader ändras. Befintliga garantidelar har `reference_lifelong` och ingen `plan_id` och uppfyller de nya
villkoren.

**Torrkörning är standard** och körs i en `READ ONLY`-transaktion. En skarp körning kontrollerar i samma
transaktion att tabellerna har modellens kolumner, att villkoren har modellens värden, att radantalen i alla
tabeller är oförändrade och att ingen agentroll har rättigheter på de nya tabellerna eller journalen. Minsta
avvikelse rullar tillbaka allt. Idempotent: är allt infört görs ingenting; är bara en del infört stoppar
migrationen. DDL:en härleds ur modellerna, så resultatet blir detsamma som `create_all`.

Körs med scripts/migrations/migrate_payout_plans.py. Inget ingrepp i Lakebase utan Karls separata OK, och
tidigast efter novembers stängning (2026-12-01).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import CheckConstraint, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import AddConstraint, CreateIndex, CreateTable

from models import Case, LedgerGuaranteePart, PayoutPlan, PayoutRequest, PayoutSplit
from utils.migration_capital_ledger import granted_to_agents as granted_on_ledger
from utils.migration_premium_flow import (
    PRIVILEGES,
    _agent_roles,
    _column_signature,
    _model_columns,
    _row_counts,
    default_privilege_problems,
)

MODELS = (PayoutRequest, PayoutPlan, PayoutSplit)
TABLES = tuple(m.__tablename__ for m in MODELS)
GUARANTEES = LedgerGuaranteePart.__tablename__
COLUMN = "plan_id"
PLAN_CHECK = "ck_ledger_guarantee_parts_plan"
PLAN_ID_CHECK = "ck_ledger_guarantee_parts_plan_id"
PLAN_INDEX = "ix_ledger_guarantee_parts_plan"
CASE_CHECK = "ck_cases_type"
NEW_CASE_TYPES = ("payout_request", "payout_review")
#: Tabellerna steg 4 bygger på: uttagsdelarna (steg 1), journalen (steg 2) med stängningen (steg 3) och ärendena
REQUIRED_TABLES = ("insured_persons", "payout_parts", "payout_part_states", "cases", "ledger_batches",
                   "ledger_guarantee_parts", "ledger_capital_entries", "ledger_controls")
#: Villkoren som de ser ut i Lakebase efter steg 3 – för prov
CHECKS_BEFORE = {
    CASE_CHECK: "case_type IN ('salary_report', 'salary_file_deviation', 'payment_overdue', "
                "'payment_unmatched', 'payout_reconstruction')",
    PLAN_CHECK: "plan_kind IN ('reference_lifelong')",
}


@dataclass
class MigrationResult:
    already_applied: bool
    applied: bool
    statements: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)
    state: dict[str, bool] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def _check(model, name: str) -> CheckConstraint:
    return next(c for c in model.__table__.constraints if isinstance(c, CheckConstraint) and c.name == name)


def _add(model, name: str, dialect) -> str:
    return str(AddConstraint(_check(model, name), isolate_from_table=False).compile(dialect=dialect)).strip()


def compile_ddl(dialect) -> list[str]:
    """Tabellerna i beroendeordning, ärendetypen och garantidelarnas plankoppling."""
    statements = []
    for model in MODELS:
        table = model.__table__
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip())
        statements += [str(CreateIndex(i).compile(dialect=dialect)).strip()
                       for i in sorted(table.indexes, key=lambda i: i.name)]
    statements += [f"ALTER TABLE cases DROP CONSTRAINT IF EXISTS {CASE_CHECK}", _add(Case, CASE_CHECK, dialect)]
    column = LedgerGuaranteePart.__table__.c[COLUMN]
    index = next(i for i in LedgerGuaranteePart.__table__.indexes if i.name == PLAN_INDEX)
    statements += [
        (f"ALTER TABLE {GUARANTEES} ADD COLUMN {COLUMN} {column.type.compile(dialect=dialect)} "
         f"REFERENCES {PayoutPlan.__tablename__} (id) ON DELETE RESTRICT"),
        f"ALTER TABLE {GUARANTEES} DROP CONSTRAINT IF EXISTS {PLAN_CHECK}",
        _add(LedgerGuaranteePart, PLAN_CHECK, dialect),
        _add(LedgerGuaranteePart, PLAN_ID_CHECK, dialect),
        str(CreateIndex(index).compile(dialect=dialect)).strip(),
    ]
    return statements


def _definition(conn: Connection, table: str, name: str) -> str | None:
    return conn.execute(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = CAST(:t AS regclass) AND contype = 'c' AND conname = :n"), {"t": table, "n": name}
    ).scalar_one_or_none()


def applied_state(conn: Connection) -> dict[str, bool]:
    """Vilka av migrationens delar som finns i databasen."""
    inspector = inspect(conn)
    names = set(inspector.get_table_names())
    case_check = _definition(conn, "cases", CASE_CHECK) or ""
    plan_check = _definition(conn, GUARANTEES, PLAN_CHECK) or ""
    return {
        **{table: table in names for table in TABLES},
        "case_types": all(f"'{t}'" in case_check for t in NEW_CASE_TYPES),
        "column": COLUMN in {c["name"] for c in inspector.get_columns(GUARANTEES)},
        "plan_check": "'plan'" in plan_check,
        "plan_id_check": _definition(conn, GUARANTEES, PLAN_ID_CHECK) is not None,
        "plan_index": PLAN_INDEX in {i["name"] for i in inspector.get_indexes(GUARANTEES)},
    }


def granted_to_agents(conn: Connection, roles: list[str]) -> list[str]:
    """Rättigheter som en agentroll har på de nya tabellerna eller journalen (P1-PENSION-001 §12)."""
    return [f"{role} på {table}" for role in roles for table in TABLES
            if conn.execute(text("SELECT has_table_privilege(:r, CAST(:t AS regclass), :p)"),
                            {"r": role, "t": table, "p": PRIVILEGES}).scalar_one()] + granted_on_ledger(conn, roles)


def _signature_problems(conn: Connection) -> list[str]:
    return [f"{model.__tablename__} har inte modellens kolumner" for model in (*MODELS, LedgerGuaranteePart)
            if _column_signature(conn, model.__tablename__) != _model_columns(model.__table__, conn.dialect)]


def migrate_payout_plans(engine: Engine, dry_run: bool = True) -> MigrationResult:
    """Inför begäran, planer och delning (eller visar SQL:en med dry_run, standard). Idempotent."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError(f"Migrationen är skriven för Postgres (Lakebase), inte {engine.dialect.name}")
    with engine.begin() as conn:
        if dry_run:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")  # torrkörningen kan inte skriva
        names = set(inspect(conn).get_table_names())
        missing = [t for t in REQUIRED_TABLES if t not in names]
        if missing:
            raise RuntimeError(f"Tabellerna {', '.join(missing)} saknas – steg 1–3 inte införda "
                               "(migrate_payout_parts.py, migrate_capital_ledger.py, migrate_month_close.py)?")
        if "supersedes_id" not in {c["name"] for c in inspect(conn).get_columns("ledger_batches")}:
            raise RuntimeError("Månadsstängningen (steg 3) är inte införd – migrate_month_close.py först")
        state = applied_state(conn)
        if all(state.values()):
            if problems := _signature_problems(conn):
                raise RuntimeError("Uttagsplanerna är införda men " + "; ".join(problems))
            return MigrationResult(already_applied=True, applied=False, state=state)
        if any(state.values()):
            done = ", ".join(k for k, v in state.items() if v)
            raise RuntimeError(f"Migrationen är delvis införd ({done}) – stäm av innan något mer körs")
        before = _row_counts(conn, names)
        roles = _agent_roles(conn)
        problems = default_privilege_problems(conn, roles)
        problems += [f"Agentroller har redan rättigheter på journalen ({', '.join(g)})"
                     for g in [granted_on_ledger(conn, roles)] if g]
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
        if problems := _signature_problems(conn):
            raise RuntimeError("; ".join(problems) + " – allt rullas tillbaka")
        if granted := granted_to_agents(conn, roles):
            raise RuntimeError(f"Agentroller har rättigheter ({', '.join(granted)}) – allt rullas tillbaka")
        after = _row_counts(conn, names)
        if after != before:
            raise RuntimeError(f"Radantalen ändrades ({before} → {after}) – allt rullas tillbaka")
    result.applied = True
    result.state = after_state
    result.row_counts = after
    return result
