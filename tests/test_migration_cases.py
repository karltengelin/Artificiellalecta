"""Migrationen som skapar tabellen cases (Fas 5 F5-1, databasschema.md §12).

Mot en isolerad Postgres (svc_test, eget schema per test) som Lakebase ser ut i dag:
alla försäkringstabeller med data, men varken cases eller kapitalförvaltningens tabeller.
Migrationen ska skapa exakt cases – samma som create_all – och inget annat.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect

from models import Base
from tests.conftest import seed_insurance
from tests.test_services_postgres import TEST_URL, isolated_schema
from utils.migration_cases import compile_ddl, migrate_cases

#: Tabeller som finns i modellerna men inte i Lakebase före migrationen
NOT_IN_LAKEBASE = {"cases", "portfolios", "portfolio_holdings", "trades"}


def test_migrationen_kraver_postgres():
    with pytest.raises(RuntimeError, match="Postgres"):
        migrate_cases(create_engine("sqlite://"))


def test_ddl_galler_bara_cases():
    from sqlalchemy.dialects import postgresql

    statements = compile_ddl(postgresql.dialect())
    assert statements[0].startswith("CREATE TABLE cases")
    assert all(" cases " in s or s.startswith("CREATE TABLE cases") for s in statements)
    assert "%%" not in " ".join(statements)


def _signature(engine, schema: str) -> dict[str, set]:
    with engine.connect() as conn:
        columns = conn.exec_driver_sql(
            "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema = %(s)s AND table_name = 'cases'", {"s": schema},
        ).all()
        constraints = conn.exec_driver_sql(
            "SELECT con.conname, pg_get_constraintdef(con.oid) FROM pg_constraint con "
            "JOIN pg_class rel ON rel.oid = con.conrelid JOIN pg_namespace n ON n.oid = rel.relnamespace "
            "WHERE n.nspname = %(s)s AND rel.relname = 'cases'", {"s": schema},
        ).all()
        indexes = conn.exec_driver_sql(
            "SELECT indexname, replace(indexdef, %(p)s, '') FROM pg_indexes "
            "WHERE schemaname = %(s)s AND tablename = 'cases'", {"s": schema, "p": f"{schema}."},
        ).all()
    return {"columns": set(columns), "constraints": set(constraints), "indexes": set(indexes)}


@pytest.mark.skipif(not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")
def test_migrationen_skapar_bara_cases_och_blir_identisk_med_create_all():
    with isolated_schema() as lakebase_like, isolated_schema() as fresh:
        Base.metadata.create_all(fresh.engine)

        tables = [t for t in Base.metadata.sorted_tables if t.name not in NOT_IN_LAKEBASE]
        Base.metadata.create_all(lakebase_like.engine, tables=tables)
        seed_insurance(lakebase_like.session_factory)

        dry = migrate_cases(lakebase_like.engine)  # torrkörning är standard
        assert not dry.applied and dry.row_counts["premium_transactions"] == 5
        assert "cases" not in inspect(lakebase_like.engine).get_table_names()

        done = migrate_cases(lakebase_like.engine, dry_run=False)
        assert done.applied and done.row_counts == dry.row_counts  # inga rader ändrade
        assert migrate_cases(lakebase_like.engine, dry_run=False).already_applied  # idempotent

        names = set(inspect(lakebase_like.engine).get_table_names())
        assert "cases" in names
        assert not names & (NOT_IN_LAKEBASE - {"cases"})  # kapitaltabellerna skapades inte
        assert _signature(lakebase_like.engine, lakebase_like.name) == _signature(fresh.engine, fresh.name)
