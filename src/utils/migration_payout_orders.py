"""Kontrollerad migration för skatt, konto, bankuppdrag och kvitton, paket B steg 6 (B-054, P1-PENSION-001 §12).

Inför i **en** transaktion (databasschema.md §7f, Karls val X1, X6, X9 och X13 2026-11-24):

1. tabellerna `tax_statuses`, `payout_accounts`, `payout_files`, `payout_orders`, `payout_order_lines` och
   `payout_receipts` med index och villkor;
2. verifikationsslaget `payout_settlement` i `ck_ledger_batches_kind` och postorsakerna `payout`,
   `withholding` och `payout_returned` i `ck_ledger_capital_entries_reason` (vidgas bara);
3. villkoret `ck_ledger_capital_entries_accounts` vidgat med skatteskulden: betalningsskuld, bolagskonto och
   skatteskuld blir aldrig negativa;
4. ärendetyperna `payout_hindrance` och `tax_status` i `ck_cases_type` (vidgas bara).

Inga rader ändras. Skatteskulden har inga poster före migrationen och uppfyller det nya villkoret.

**Förutsätter steg 5:s migration** (anspråken och bolagskontots villkor). Villkoren i punkt 2–4 läggs om ur
modellerna, så bara tabellerna avgör om migrationen är delvis införd.

**Torrkörning är standard** och körs i en `READ ONLY`-transaktion. En skarp körning kontrollerar i samma
transaktion att tabellerna har modellens kolumner, att villkoren har modellens värden, att radantalen är
oförändrade och att ingen agentroll har rättigheter på de nya tabellerna eller journalen. Minsta avvikelse
rullar tillbaka allt. Idempotent: är allt infört görs ingenting.

Körs med scripts/migrations/migrate_payout_orders.py. Inget ingrepp i Lakebase utan Karls separata OK, och
först efter steg 5:s migration.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import CheckConstraint, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import AddConstraint, CreateIndex, CreateTable

from models import (
    Case,
    LedgerBatch,
    LedgerCapitalEntry,
    PayoutAccount,
    PayoutFile,
    PayoutOrder,
    PayoutOrderLine,
    PayoutReceipt,
    TaxStatus,
)
from utils.migration_capital_ledger import granted_to_agents as granted_on_ledger
from utils.migration_premium_flow import (
    PRIVILEGES,
    _agent_roles,
    _column_signature,
    _model_columns,
    _row_counts,
    default_privilege_problems,
)

MODELS = (TaxStatus, PayoutAccount, PayoutFile, PayoutOrder, PayoutOrderLine, PayoutReceipt)
TABLES = tuple(m.__tablename__ for m in MODELS)
BATCHES = LedgerBatch.__tablename__
ENTRIES = LedgerCapitalEntry.__tablename__
#: (tabell, modell, villkor, värde som ska finnas i definitionen efter migrationen)
CHECKS = (
    (BATCHES, LedgerBatch, "ck_ledger_batches_kind", "'payout_settlement'"),
    (ENTRIES, LedgerCapitalEntry, "ck_ledger_capital_entries_reason", "'payout_returned'"),
    (ENTRIES, LedgerCapitalEntry, "ck_ledger_capital_entries_accounts", "'tax_liability'"),
    ("cases", Case, "ck_cases_type", "'payout_hindrance'"),
)
#: Tabellerna steg 6 bygger på: journalen med stängningen (steg 2–3), planerna (steg 4) och anspråken (steg 5)
REQUIRED_TABLES = ("insured_persons", "payout_parts", "payout_part_states", "cases", "ledger_batches",
                   "ledger_guarantee_parts", "ledger_capital_entries", "ledger_controls", "payout_requests",
                   "payout_plans", "payout_splits", "payout_amounts", "pension_claims", "pension_claim_fundings")
#: Villkoren som de ser ut i Lakebase efter steg 5 – för prov
CHECKS_BEFORE = {
    "ck_ledger_batches_kind": "kind IN ('opening_s04', 'month_close', 'month_correction', 'company_capital')",
    "ck_ledger_capital_entries_reason": "reason IN ('opening', 'premium', 'return', 'fee', 'tax', 'pension_debit', "
                                        "'company_support', 'pool_in', 'pool_out', 'split', 'company_capital')",
    "ck_ledger_capital_entries_accounts": "account NOT IN ('payment_liability', 'company') OR "
                                          "(balance_before_sek >= 0 AND balance_after_sek >= 0)",
    "ck_cases_type": "case_type IN ('salary_report', 'salary_file_deviation', 'payment_overdue', "
                     "'payment_unmatched', 'payout_reconstruction', 'payout_request', 'payout_review', "
                     "'company_capital')",
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
    """Tabellerna i beroendeordning och de vidgade villkoren, lagda om ur modellerna."""
    statements = []
    for model in MODELS:
        table = model.__table__
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip())
        statements += [str(CreateIndex(i).compile(dialect=dialect)).strip()
                       for i in sorted(table.indexes, key=lambda i: i.name)]
    for table, model, name, _ in CHECKS:
        statements += [f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}", _add(model, name, dialect)]
    return statements


def _definition(conn: Connection, table: str, name: str) -> str | None:
    return conn.execute(text(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = CAST(:t AS regclass) AND contype = 'c' AND conname = :n"), {"t": table, "n": name}
    ).scalar_one_or_none()


def applied_state(conn: Connection) -> dict[str, bool]:
    """Vilka av migrationens delar som finns i databasen."""
    names = set(inspect(conn).get_table_names())
    return {**{table: table in names for table in TABLES},
            **{name: value in (_definition(conn, table, name) or "") for table, _, name, value in CHECKS}}


def granted_to_agents(conn: Connection, roles: list[str]) -> list[str]:
    """Rättigheter som en agentroll har på de nya tabellerna eller journalen (P1-PENSION-001 §12)."""
    return [f"{role} på {table}" for role in roles for table in TABLES
            if conn.execute(text("SELECT has_table_privilege(:r, CAST(:t AS regclass), :p)"),
                            {"r": role, "t": table, "p": PRIVILEGES}).scalar_one()] + granted_on_ledger(conn, roles)


def _signature_problems(conn: Connection) -> list[str]:
    return [f"{model.__tablename__} har inte modellens kolumner" for model in MODELS
            if _column_signature(conn, model.__tablename__) != _model_columns(model.__table__, conn.dialect)]


def migrate_payout_orders(engine: Engine, dry_run: bool = True) -> MigrationResult:
    """Inför skatt, konto, bankuppdrag och kvitton (eller visar SQL:en med dry_run, standard). Idempotent."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError(f"Migrationen är skriven för Postgres (Lakebase), inte {engine.dialect.name}")
    with engine.begin() as conn:
        if dry_run:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")  # torrkörningen kan inte skriva
        inspector = inspect(conn)
        names = set(inspector.get_table_names())
        missing = [t for t in REQUIRED_TABLES if t not in names]
        if missing:
            raise RuntimeError(f"Tabellerna {', '.join(missing)} saknas – steg 1–5 inte införda "
                               "(migrate_payout_parts.py … migrate_pension_claims.py)?")
        if "'company'" not in (_definition(conn, ENTRIES, "ck_ledger_capital_entries_accounts") or ""):
            raise RuntimeError("Bolagskontots villkor (steg 5) saknas – migrate_pension_claims.py först")
        state = applied_state(conn)
        if all(state.values()):
            if problems := _signature_problems(conn):
                raise RuntimeError("Bankuppdragen är införda men " + "; ".join(problems))
            return MigrationResult(already_applied=True, applied=False, state=state)
        if any(state[t] for t in TABLES):
            done = ", ".join(t for t in TABLES if state[t])
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
