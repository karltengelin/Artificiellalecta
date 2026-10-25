"""Migrationen som skapar flödesmotorns tabeller (Fas 3c 3c-2, databasschema.md §9i och §12).

Mot en isolerad Postgres (svc_test, eget schema per test) som Lakebase ser ut i dag:
försäkringstabellerna med data, men varken flödestabellerna eller kapitalförvaltningens.
Migrationen ska skapa exakt flows, flow_steps och flow_gate_decisions – samma som create_all.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect

from models import Base
from tests.conftest import seed_insurance
from tests.test_services_postgres import TEST_URL, isolated_schema
from utils.migration_flows import FLOW_TABLE_NAMES, compile_ddl, migrate_flows

NOT_IN_LAKEBASE = {*FLOW_TABLE_NAMES, "portfolios", "portfolio_holdings", "trades"}


def _signature(engine, schema: str, table: str) -> dict[str, set]:
    """Kolumner, villkor och index för en tabell – för jämförelse med create_all."""
    params = {"s": schema, "t": table, "p": f"{schema}."}
    with engine.connect() as conn:
        columns = conn.exec_driver_sql(
            "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema = %(s)s AND table_name = %(t)s", params,
        ).all()
        constraints = conn.exec_driver_sql(
            "SELECT con.conname, replace(pg_get_constraintdef(con.oid), %(p)s, '') FROM pg_constraint con "
            "JOIN pg_class rel ON rel.oid = con.conrelid JOIN pg_namespace n ON n.oid = rel.relnamespace "
            "WHERE n.nspname = %(s)s AND rel.relname = %(t)s", params,
        ).all()
        indexes = conn.exec_driver_sql(
            "SELECT indexname, replace(indexdef, %(p)s, '') FROM pg_indexes "
            "WHERE schemaname = %(s)s AND tablename = %(t)s", params,
        ).all()
    return {"columns": set(columns), "constraints": set(constraints), "indexes": set(indexes)}


def test_migrationen_kraver_postgres():
    with pytest.raises(RuntimeError, match="Postgres"):
        migrate_flows(create_engine("sqlite://"))


def test_ddl_galler_bara_flodestabellerna():
    from sqlalchemy.dialects import postgresql

    statements = compile_ddl(postgresql.dialect())
    created = [s.split()[2] for s in statements if s.startswith("CREATE TABLE")]
    assert created == ["flows", "flow_steps", "flow_gate_decisions"]
    assert all(any(f" {t} " in s or s.startswith(f"CREATE TABLE {t}") for t in FLOW_TABLE_NAMES) for s in statements)
    assert "%%" not in " ".join(statements)


@pytest.mark.skipif(not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")
def test_migrationen_skapar_bara_flodestabellerna_och_blir_identisk_med_create_all():
    with isolated_schema() as lakebase_like, isolated_schema() as fresh:
        Base.metadata.create_all(fresh.engine)

        tables = [t for t in Base.metadata.sorted_tables if t.name not in NOT_IN_LAKEBASE]
        Base.metadata.create_all(lakebase_like.engine, tables=tables)
        seed_insurance(lakebase_like.session_factory)

        dry = migrate_flows(lakebase_like.engine)  # torrkörning är standard
        assert not dry.applied and dry.row_counts["premium_transactions"] == 5
        assert not set(FLOW_TABLE_NAMES) & set(inspect(lakebase_like.engine).get_table_names())

        done = migrate_flows(lakebase_like.engine, dry_run=False)
        assert done.applied and done.row_counts == dry.row_counts  # inga rader ändrade
        assert migrate_flows(lakebase_like.engine, dry_run=False).already_applied  # idempotent

        names = set(inspect(lakebase_like.engine).get_table_names())
        assert set(FLOW_TABLE_NAMES) <= names
        assert not names & (NOT_IN_LAKEBASE - set(FLOW_TABLE_NAMES))
        for table in FLOW_TABLE_NAMES:
            assert _signature(lakebase_like.engine, lakebase_like.name, table) == _signature(fresh.engine, fresh.name, table)
