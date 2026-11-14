"""Kontrollerad migration av uttagsdelar och tre förlopp, paket B steg 1 (B-047, P1-PENSION-001 §4 och §12).

Inför i **en** transaktion:

1. tabellerna `payout_parts` och `payout_part_states`, med index och villkor (databasschema.md §7b);
2. ärendetypen `payout_reconstruction` i villkoret `ck_cases_type` (vidgas bara);
3. övergången (`services/payout_transition.py`): uttagsdel 1 i `not_started` för varje
   ålderspensionsförmån, gamla uttagslägen flyttade till delen och ett rekonstruktionsärende per
   flyttat uttag. I Lakebase finns inga uttagslägen, så där skapas bara delarna;
4. villkoret `ck_policy_states_state` smalnas till premieförloppets två lägen (`premium_paying`,
   `paid_up`) – sist, när inga gamla lägen finns kvar.

**Torrkörning är standard** och körs i en `READ ONLY`-transaktion: den visar SQL, villkorens
nuvarande definitioner, övergångens plan (antal delar, flyttade uttag, ärenden), schemaskillnader,
hinder och radantal, men kan inte skriva. En skarp körning kontrollerar i samma transaktion att
tabellerna har modellens kolumner, att villkoren har modellens värden, att varje förmån har exakt
del 1 med ett öppet läge, att radantalen i övriga tabeller är oförändrade (utom `policy_states` och
`cases` med exakt övergångens rörelser) och att ingen agentroll har rättigheter på de nya
tabellerna (§12). Minsta avvikelse rullar tillbaka allt. Idempotent: är allt infört görs ingenting;
är bara en del infört stoppar migrationen.

Körs med scripts/migrations/migrate_payout_parts.py. Inget ingrepp i Lakebase utan Karls separata OK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session
from sqlalchemy.schema import AddConstraint, CheckConstraint, CreateIndex, CreateTable

from models import Case, PayoutPart, PayoutPartState, PolicyBenefit, PolicyState
from models.policy_state import LEGACY_PAYOUT_STATES
from services.payout_transition import (
    CASE_TYPE,
    TransitionResult,
    apply_transition,
    plan_transition,
)
from utils.migration_premium_flow import (
    PRIVILEGES,
    _agent_roles,
    _column_signature,
    _model_columns,
    _row_counts,
    default_privilege_problems,
    schema_drift,
)

MODELS = (PayoutPart, PayoutPartState)
TABLES = tuple(m.__tablename__ for m in MODELS)
REQUIRED_TABLES = ("employers", "insured_persons", "policies", "policy_benefits", "policy_states",
                   "premium_transactions", "cases")
#: Villkoren som byts: tabell, namn, ett värde som ska finnas efteråt och ett som inte får finnas kvar
CASE_TYPE_CHECK = ("cases", "ck_cases_type", f"'{CASE_TYPE}'", None)
STATE_CHECK = ("policy_states", "ck_policy_states_state", "'paid_up'", "'in_payout'")
CHECKS = (CASE_TYPE_CHECK, STATE_CHECK)
#: Villkoren som de finns i Lakebase före steg 1 (paket A:s ärendetyper, B-022:s fem lägen) – för prov
CHECKS_BEFORE = {
    "ck_cases_type": "case_type IN ('salary_report', 'salary_file_deviation', 'payment_overdue', "
                     "'payment_unmatched')",
    "ck_policy_states_state": "state IN ('premium_paying', 'paid_up', 'in_payout', 'payout_paused', 'terminated')",
}
_MODEL_FOR = {"cases": Case, "policy_states": PolicyState}


@dataclass
class MigrationResult:
    already_applied: bool
    applied: bool
    statements: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)
    checks: dict[str, str | None] = field(default_factory=dict)
    transition: TransitionResult | None = None
    drift: dict[str, list[str]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def compile_tables(dialect) -> list[str]:
    statements = []
    for model in MODELS:
        table = model.__table__
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip())
        statements += [str(CreateIndex(i).compile(dialect=dialect)) for i in sorted(table.indexes, key=lambda i: i.name)]
    return statements


def compile_check(dialect, table: str, name: str) -> list[str]:
    constraint = next(c for c in _MODEL_FOR[table].__table__.constraints
                      if isinstance(c, CheckConstraint) and c.name == name)
    return [f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}",
            str(AddConstraint(constraint, isolate_from_table=False).compile(dialect=dialect)).strip()]


def compile_ddl(dialect) -> tuple[list[str], list[str]]:
    """(före övergången, efter övergången): tabellerna och ärendetypen först, lägesvillkoret sist."""
    return (compile_tables(dialect) + compile_check(dialect, *CASE_TYPE_CHECK[:2]),
            compile_check(dialect, *STATE_CHECK[:2]))


def check_definitions(conn: Connection) -> dict[str, str | None]:
    out = {}
    for table, name, _, _ in CHECKS:
        out[name] = conn.execute(text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = CAST(:t AS regclass) AND contype = 'c' AND conname = :n"
        ), {"t": table, "n": name}).scalar_one_or_none()
    return out


def stale_checks(definitions: dict[str, str | None]) -> list[str]:
    return [name for _, name, wanted, unwanted in CHECKS
            if definitions.get(name) is None or wanted not in definitions[name]
            or (unwanted is not None and unwanted in definitions[name])]


def granted_to_agents(conn: Connection, roles: list[str]) -> list[str]:
    return [f"{role} på {table}" for role in roles for table in TABLES
            if conn.execute(text("SELECT has_table_privilege(:r, CAST(:t AS regclass), :p)"),
                            {"r": role, "t": table, "p": PRIVILEGES}).scalar_one()]


def _structure_problems(conn: Connection) -> list[str]:
    """Efter övergången: exakt del 1 per ålderspensionsförmån, ett öppet läge per del, inga gamla lägen."""
    problems = []
    benefits = conn.execute(select(func.count()).select_from(PolicyBenefit)
                            .where(PolicyBenefit.benefit_type == "retirement_dc")).scalar_one()
    parts = conn.execute(select(func.count()).select_from(PayoutPart).where(PayoutPart.part_number == 1)).scalar_one()
    all_parts = conn.execute(select(func.count()).select_from(PayoutPart)).scalar_one()
    if not benefits == parts == all_parts:
        problems.append(f"{benefits} ålderspensionsförmåner men {parts} delar nr 1 och {all_parts} delar totalt")
    missing = conn.execute(select(func.count()).select_from(PolicyBenefit).where(
        PolicyBenefit.benefit_type == "retirement_dc",
        ~select(PayoutPart.id).where(PayoutPart.benefit_id == PolicyBenefit.id).exists())).scalar_one()
    if missing:
        problems.append(f"{missing} förmåner saknar uttagsdel")
    open_states = conn.execute(select(func.count()).select_from(PayoutPartState)
                               .where(PayoutPartState.valid_to.is_(None))).scalar_one()
    if open_states != all_parts:
        problems.append(f"{all_parts} delar men {open_states} öppna lägen")
    legacy = conn.execute(select(func.count()).select_from(PolicyState)
                          .where(PolicyState.state.in_(LEGACY_PAYOUT_STATES))).scalar_one()
    if legacy:
        problems.append(f"{legacy} gamla uttagslägen kvar i policy_states")
    return problems


def migrate_payout_parts(engine: Engine, dry_run: bool = True, today: date | None = None) -> MigrationResult:
    """Inför uttagsdelarna och övergången (eller visar planen med dry_run, standard). Idempotent."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError(f"Migrationen är skriven för Postgres (Lakebase), inte {engine.dialect.name}")
    today = today or date.today()
    with engine.begin() as conn:
        if dry_run:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")  # torrkörningen kan inte skriva
        names = set(inspect(conn).get_table_names())
        missing = [t for t in REQUIRED_TABLES if t not in names]
        if missing:
            raise RuntimeError(f"Tabellerna {', '.join(missing)} saknas – fel databas eller tidigare migration "
                               "inte körd (migrate_cases.py, migrate_premium_flow.py)?")
        definitions = check_definitions(conn)
        stale = stale_checks(definitions)
        present = [t for t in TABLES if t in names]
        if len(present) == len(TABLES) and not stale:
            if problems := _structure_problems(conn):
                raise RuntimeError("Uttagsdelarna är införda men stämmer inte: " + "; ".join(problems))
            return MigrationResult(already_applied=True, applied=False, checks=definitions)
        if present or len(stale) != len(CHECKS):
            raise RuntimeError(
                f"Uttagsdelarna är delvis införda (tabeller: {', '.join(present) or 'inga'}; villkor som saknar "
                f"modellens värden: {', '.join(stale) or 'inga'}) – stäm av innan något mer körs"
            )
        others = names - set(TABLES)
        before = _row_counts(conn, others)
        drift = schema_drift(conn, others)
        roles = _agent_roles(conn)
        problems = default_privilege_problems(conn, roles)
        with Session(bind=conn) as session:
            plan = plan_transition(session, parts_table=False)
        problems += plan.problems
        first, last = compile_ddl(engine.dialect)
        result = MigrationResult(already_applied=False, applied=False, statements=first + last, row_counts=before,
                                 checks=definitions, transition=plan, drift=drift, problems=problems)
        if dry_run:
            return result
        if problems:
            raise RuntimeError("Hinder före migrationen: " + "; ".join(problems))
        for statement in first:
            conn.exec_driver_sql(statement)
        with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
            done = apply_transition(session, today)
            session.commit()  # släpper sparpunkten; den yttre transaktionen styr allt
        for statement in last:
            conn.exec_driver_sql(statement)
        for model in MODELS:
            if _column_signature(conn, model.__tablename__) != _model_columns(model.__table__, conn.dialect):
                raise RuntimeError(f"Tabellen {model.__tablename__} fick inte modellens kolumner – allt rullas tillbaka")
        if still := stale_checks(check_definitions(conn)):
            raise RuntimeError(f"Villkoren {', '.join(still)} byttes inte – allt rullas tillbaka")
        if structure := _structure_problems(conn):
            raise RuntimeError("Övergången stämmer inte: " + "; ".join(structure) + " – allt rullas tillbaka")
        if granted := granted_to_agents(conn, roles):
            raise RuntimeError(f"Agentroller har rättigheter på nya tabeller ({', '.join(granted)}) – allt rullas tillbaka")
        after = _row_counts(conn, others)
        added_paid_up = sum(m.premium_action == "paid_up" for m in done.moved)
        moved_rows = sum(len(m.rows) for m in done.moved)
        expected = dict(before)
        expected["policy_states"] = before["policy_states"] - moved_rows + added_paid_up
        expected["cases"] = before["cases"] + len(done.moved)
        if after != expected:
            raise RuntimeError(f"Radantalen stämmer inte ({expected} → {after}) – allt rullas tillbaka")
    result.applied = True
    result.transition = done
    result.row_counts = after
    return result
