"""Riktad tom migration av P6-MANAD-001:s tre journaltabeller. Ej körd i Lakebase."""

from sqlalchemy import inspect
from sqlalchemy.schema import CreateIndex, CreateTable

from models import PremiumMonthClose, PremiumMonthJournal, PremiumReceipt
from utils.migration_actuarial_workspace import MigrationResult, _row_counts

MODELS = (PremiumMonthJournal, PremiumReceipt, PremiumMonthClose)
TABLES = tuple(m.__tablename__ for m in MODELS)
REQUIRED = {"insured_persons", "valuation_bases", "valuation_runs", "product_parameters"}


def compile_ddl(dialect):
    out = []
    for model in MODELS:
        table = model.__table__
        out.append(str(CreateTable(table).compile(dialect=dialect)).strip())
        out += [str(CreateIndex(i).compile(dialect=dialect)) for i in sorted(table.indexes, key=lambda i: i.name)]
    return out


def migrate_premium_journal(engine, dry_run=True):
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Den riktade journalmigrationen kräver PostgreSQL")
    with engine.begin() as conn:
        names = set(inspect(conn).get_table_names())
        if REQUIRED - names:
            raise RuntimeError("Försäkringssystemets värderings-/parametertabeller saknas")
        present = set(TABLES) & names
        if present == set(TABLES):
            return MigrationResult(already_applied=True, applied=False)
        if present:
            raise RuntimeError("Journalens schema är delvis infört; stäm av innan nästa försök")
        before = _row_counts(conn, names)
        statements = compile_ddl(engine.dialect)
        if dry_run:
            return MigrationResult(already_applied=False, applied=False, statements=statements, row_counts=before)
        for sql in statements:
            conn.exec_driver_sql(sql)
        after = _row_counts(conn, names)
        if before != after or any(_row_counts(conn, set(TABLES)).values()):
            raise RuntimeError("Radantal eller tomhetskontroll avviker; migrationen rullas tillbaka")
    return MigrationResult(already_applied=False, applied=True, statements=statements, row_counts=after)
