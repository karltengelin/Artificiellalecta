"""Kontrollerad migration av premieflödet, paket A steg 8 (B-046, P1-PREMIE-001 §11).

Inför i en transaktion:

- de fem tabellerna `salary_files`, `invoices`, `invoice_lines`, `bank_events` och
  `payment_allocations`, tomma och med index och villkor (databasschema.md §8c–8e);
- tre bytta CHECK-villkor på `cases` (§9g): ärendetyperna `salary_file_deviation`,
  `payment_overdue` och `payment_unmatched`, kanalen `system` och undantaget att ett
  `payment_unmatched`-ärende får sakna både försäkrad och arbetsgivare.

Villkoren vidgas bara, så befintliga ärenden uppfyller dem. Tabellerna och villkoren förs in
tillsammans: handläggarsidan slutar visa notisen om saknade tabeller när tabellerna finns, och
då måste ärendena kunna skapas.

**Torrkörning är standard** och körs i en `READ ONLY`-transaktion: den läser schema, villkor,
radantal och rättigheter och visar SQL:en, men kan inte skriva. En skarp körning kontrollerar
efteråt, i samma transaktion, att tabellerna är tomma och har modellens kolumner, att villkoren
har modellens värden, att radantalen i övriga tabeller är oförändrade och att ingen agentroll har
rättigheter på de nya tabellerna (P1-PREMIE-001 §11). Minsta avvikelse rullar tillbaka allt.
Idempotent: är allt infört görs ingenting; är bara en del infört stoppar migrationen.

DDL:en härleds ur modellerna, så resultatet blir detsamma som `create_all`. `premium_transactions`
ändras inte; kolumnerna i designstoppet §5 är ett separat förslag (steg 8).
Körs med scripts/migrations/migrate_premium_flow.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import AddConstraint, CheckConstraint, CreateIndex, CreateTable

from models import (
    BankEvent,
    Base,
    Case,
    Invoice,
    InvoiceLineRecord,
    PaymentAllocation,
    SalaryFile,
)
from models.case import CASE_CHANNELS, CASE_TYPES
from utils.agent_roles import ROLE_GRANTS

#: Refererade tabeller skapas före de tabeller som pekar på dem.
MODELS = (SalaryFile, Invoice, InvoiceLineRecord, BankEvent, PaymentAllocation)
TABLES = tuple(m.__tablename__ for m in MODELS)
#: Tabeller som de nya refererar eller som villkoren gäller – visar att det är försäkringsdatabasen
REQUIRED_TABLES = ("employers", "insured_persons", "policies", "policy_benefits", "premium_transactions",
                   "salary_reports", "cases")
CASES = Case.__tablename__
#: Villkoren på cases som paket A vidgar, med de värden som ska finnas i det införda villkoret
CASE_CHECKS: dict[str, tuple[str, ...]] = {
    "ck_cases_type": tuple(f"'{v}'" for v in CASE_TYPES),
    "ck_cases_channel": tuple(f"'{v}'" for v in CASE_CHANNELS),
    "ck_cases_subject": ("'payment_unmatched'",),
}
#: Villkoren som de infördes i Lakebase 2026-10-24 (F5-1, före paket A) – för prov av migrationen
CASE_CHECKS_BEFORE = {
    "ck_cases_type": "case_type IN ('salary_report')",
    "ck_cases_channel": "channel IN ('manual', 'employer_file', 'customer_portal', 'chatbot')",
    "ck_cases_subject": "insured_person_id IS NOT NULL OR employer_id IS NOT NULL",
}
PRIVILEGES = "SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER"
#: Typnamn som Postgres lagrar under ett annat namn än modellens
_TYPE_ALIASES = {"FLOAT": "DOUBLE PRECISION"}


@dataclass
class MigrationResult:
    already_applied: bool
    applied: bool
    statements: list[str] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)
    #: Villkorens definitioner före migrationen (pg_get_constraintdef)
    case_checks: dict[str, str | None] = field(default_factory=dict)
    #: Avvikelser mellan modellerna och databasens befintliga tabeller, utom det migrationen inför
    drift: dict[str, list[str]] = field(default_factory=dict)
    #: Hinder för en skarp körning, t.ex. standardrättigheter som skulle ge agentrollerna åtkomst
    problems: list[str] = field(default_factory=list)


def compile_tables(dialect) -> list[str]:
    """CREATE TABLE och index för de fem nya tabellerna, i körordning."""
    statements = []
    for model in MODELS:
        table = model.__table__
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip())
        statements += [str(CreateIndex(i).compile(dialect=dialect)) for i in sorted(table.indexes, key=lambda i: i.name)]
    return statements


def _case_check(name: str) -> CheckConstraint:
    return next(c for c in Case.__table__.constraints if isinstance(c, CheckConstraint) and c.name == name)


def compile_case_checks(dialect, names=tuple(CASE_CHECKS)) -> list[str]:
    """Byter villkoren på cases. isolate_from_table=False: annars tar SQLAlchemy bort dem ur CREATE TABLE."""
    statements = []
    for name in names:
        statements.append(f"ALTER TABLE {CASES} DROP CONSTRAINT IF EXISTS {name}")
        statements.append(str(AddConstraint(_case_check(name), isolate_from_table=False).compile(dialect=dialect)).strip())
    return statements


def compile_ddl(dialect) -> list[str]:
    """Hela migrationen i körordning: tabellerna först, sedan villkoren på cases."""
    return compile_tables(dialect) + compile_case_checks(dialect)


def case_check_definitions(conn: Connection) -> dict[str, str | None]:
    rows = dict(conn.execute(text(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = CAST(:t AS regclass) AND contype = 'c'"
    ), {"t": CASES}).all())
    return {name: rows.get(name) for name in CASE_CHECKS}


def stale_case_checks(definitions: dict[str, str | None]) -> list[str]:
    """Villkoren som saknas eller saknar något av modellens värden."""
    return [name for name, values in CASE_CHECKS.items()
            if definitions.get(name) is None or not all(v in definitions[name] for v in values)]


def _row_counts(conn: Connection, names: set[str]) -> dict[str, int]:
    return {
        table.name: conn.execute(select(func.count()).select_from(table)).scalar_one()
        for table in Base.metadata.sorted_tables
        if table.name in names
    }


def _type_name(type_, dialect) -> str:
    name = type_.compile(dialect=dialect)
    return _TYPE_ALIASES.get(name, name)


def _column_signature(conn: Connection, table_name: str) -> dict[str, tuple[str, bool]]:
    return {c["name"]: (_type_name(c["type"], conn.dialect), bool(c["nullable"]))
            for c in inspect(conn).get_columns(table_name)}


def _model_columns(table, dialect) -> dict[str, tuple[str, bool]]:
    return {c.name: (_type_name(c.type, dialect), bool(c.nullable)) for c in table.columns}


def schema_drift(conn: Connection, names: set[str]) -> dict[str, list[str]]:
    """Kolumner, villkor och index som skiljer modellerna från databasens befintliga tabeller.

    Gäller tabeller som finns i både modellerna och databasen, utom premieflödets nya. Villkoren
    på cases som migrationen byter räknas inte – deras innehåll prövas i stale_case_checks.
    """
    inspector = inspect(conn)
    drift: dict[str, list[str]] = {}
    for table in Base.metadata.sorted_tables:
        if table.name not in names or table.name in TABLES:
            continue
        issues = []
        model_cols = _model_columns(table, conn.dialect)
        db_cols = _column_signature(conn, table.name)
        for name in sorted(model_cols.keys() - db_cols.keys()):
            issues.append(f"kolumn {name} saknas i databasen")
        for name in sorted(db_cols.keys() - model_cols.keys()):
            issues.append(f"kolumn {name} finns bara i databasen")
        for name in sorted(model_cols.keys() & db_cols.keys()):
            if model_cols[name] != db_cols[name]:
                issues.append(f"kolumn {name}: modellen {model_cols[name]}, databasen {db_cols[name]}")
        model_checks = {c.name for c in table.constraints if isinstance(c, CheckConstraint) and c.name}
        db_checks = {c["name"] for c in inspector.get_check_constraints(table.name)}
        for name in sorted(model_checks - db_checks):
            issues.append(f"villkor {name} saknas i databasen")
        for name in sorted(db_checks - model_checks):
            issues.append(f"villkor {name} finns bara i databasen")
        model_indexes = {i.name for i in table.indexes}
        # Index bakom UNIQUE-villkor (unique=True på kolumnen) hör inte till modellens index
        db_indexes = {i["name"] for i in inspector.get_indexes(table.name) if not i.get("duplicates_constraint")}
        for name in sorted(model_indexes - db_indexes):
            issues.append(f"index {name} saknas i databasen")
        for name in sorted(db_indexes - model_indexes):
            issues.append(f"index {name} finns bara i databasen")
        if issues:
            drift[table.name] = issues
    return drift


def _agent_roles(conn: Connection) -> list[str]:
    wanted = [g.role for g in ROLE_GRANTS.values()]
    present = set(conn.execute(text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:r)"), {"r": wanted}).scalars())
    return [r for r in wanted if r in present]


def default_privilege_problems(conn: Connection, roles: list[str]) -> list[str]:
    """Standardrättigheter (ALTER DEFAULT PRIVILEGES) som skulle ge en agentroll åtkomst till nya tabeller."""
    if not roles:
        return []
    rows = conn.execute(text(
        "SELECT g.rolname, a.privilege_type FROM pg_default_acl d "
        "CROSS JOIN LATERAL aclexplode(d.defaclacl) a JOIN pg_roles g ON g.oid = a.grantee "
        "WHERE d.defaclobjtype = 'r' AND (d.defaclnamespace = 0 OR d.defaclnamespace = "
        "(SELECT oid FROM pg_namespace WHERE nspname = current_schema())) AND g.rolname = ANY(:r)"
    ), {"r": roles}).all()
    return [f"Standardrättighet {priv} för {role} på nya tabeller – agentrollerna ska inte få rättigheter (§11)"
            for role, priv in sorted(set(rows))]


def granted_to_agents(conn: Connection, roles: list[str]) -> list[str]:
    """Rättigheter som en agentroll har på någon av de nya tabellerna."""
    found = []
    for role in roles:
        for table in TABLES:
            if conn.execute(text("SELECT has_table_privilege(:r, CAST(:t AS regclass), :p)"),
                            {"r": role, "t": table, "p": PRIVILEGES}).scalar_one():
                found.append(f"{role} på {table}")
    return found


def migrate_premium_flow(engine: Engine, dry_run: bool = True) -> MigrationResult:
    """Inför premieflödets tabeller och villkor (eller visar SQL:en med dry_run, standard). Idempotent."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError(f"Migrationen är skriven för Postgres (Lakebase), inte {engine.dialect.name}")
    with engine.begin() as conn:
        if dry_run:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")  # torrkörningen kan inte skriva
        names = set(inspect(conn).get_table_names())
        missing = [t for t in REQUIRED_TABLES if t not in names]
        if missing:
            raise RuntimeError(f"Tabellerna {', '.join(missing)} saknas – fel databas eller tidigare migration "
                               "inte körd (migrate_t3_schema.py, migrate_cases.py)?")
        definitions = case_check_definitions(conn)
        stale = stale_case_checks(definitions)
        present = [t for t in TABLES if t in names]
        if len(present) == len(TABLES) and not stale:
            return MigrationResult(already_applied=True, applied=False, case_checks=definitions)
        if present or len(stale) != len(CASE_CHECKS):
            raise RuntimeError(
                f"Premieflödet är delvis infört (tabeller: {', '.join(present) or 'inga'}; villkor som saknar "
                f"modellens värden: {', '.join(stale) or 'inga'}) – stäm av innan något mer körs"
            )
        others = names - set(TABLES)
        before = _row_counts(conn, others)
        drift = schema_drift(conn, others)
        roles = _agent_roles(conn)
        problems = default_privilege_problems(conn, roles)
        statements = compile_ddl(engine.dialect)
        result = MigrationResult(already_applied=False, applied=False, statements=statements, row_counts=before,
                                 case_checks=definitions, drift=drift, problems=problems)
        if dry_run:
            return result
        if problems:
            raise RuntimeError("Hinder före migrationen: " + "; ".join(problems))
        for statement in statements:
            conn.exec_driver_sql(statement)
        created = set(inspect(conn).get_table_names())
        if not set(TABLES) <= created:
            raise RuntimeError("Tabellerna skapades inte – allt rullas tillbaka")
        for model in MODELS:
            if _column_signature(conn, model.__tablename__) != _model_columns(model.__table__, conn.dialect):
                raise RuntimeError(f"Tabellen {model.__tablename__} fick inte modellens kolumner – allt rullas tillbaka")
        if still := stale_case_checks(case_check_definitions(conn)):
            raise RuntimeError(f"Villkoren {', '.join(still)} byttes inte – allt rullas tillbaka")
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
