"""Skapar endast ärendeuppdragens tre tabeller; inga ändringar i befintliga rader."""

from sqlalchemy import func, inspect, select
from sqlalchemy.schema import CreateIndex, CreateTable

from models import Base, CaseMessage, CaseWork, CaseWorkDay
from utils.migration_cases import MigrationResult

TABLES = (CaseWork.__table__, CaseMessage.__table__, CaseWorkDay.__table__)
NAMES = {t.name for t in TABLES}


def migrate_case_work(engine, dry_run=True):
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Migrationen är avsedd för Postgres")
    with engine.begin() as conn:
        names = set(inspect(conn).get_table_names())
        if "cases" not in names:
            raise RuntimeError("Tabellen cases saknas – kontrollera databas och tidigare migration")
        for table in TABLES:
            if table.name in names:
                columns = {c["name"] for c in inspect(conn).get_columns(table.name)}
                if columns != set(table.columns.keys()):
                    raise RuntimeError(f"Tabellen {table.name} har oväntat schema; avbryter")
        statements = []
        for table in TABLES:
            if table.name not in names:
                statements.append(str(CreateTable(table).compile(dialect=engine.dialect)))
                statements.extend(str(CreateIndex(i).compile(dialect=engine.dialect))
                                  for i in sorted(table.indexes, key=lambda i: i.name))
        counts = {t.name: conn.scalar(select(func.count()).select_from(t))
                  for t in Base.metadata.sorted_tables if t.name in names and t.name not in NAMES}
        if dry_run or not statements:
            return MigrationResult(not statements, False, statements, counts)
        for statement in statements:
            conn.exec_driver_sql(statement)
        after = {t.name: conn.scalar(select(func.count()).select_from(t))
                 for t in Base.metadata.sorted_tables if t.name in counts}
        if counts != after:
            raise RuntimeError("Radantalen ändrades; migrationen rullas tillbaka")
        return MigrationResult(False, True, statements, after)
