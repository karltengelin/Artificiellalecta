"""Migrationen som inför premieflödet i Lakebase (paket A steg 8, B-046, P1-PREMIE-001 §11).

Mot en isolerad Postgres (svc_test, eget schema per test) som Lakebase ser ut i dag: alla
befintliga tabeller med data, `cases` med villkoren från F5-1 och inga av premieflödets tabeller.
Migrationen ska skapa exakt de fem tabellerna och byta exakt tre villkor på cases – samma
resultat som create_all – och torrkörningen ska inte kunna skriva.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from models import Base, Case
from tests.conftest import seed_insurance
from tests.test_services_postgres import TEST_URL, isolated_schema
from utils.migration_premium_flow import (
    CASE_CHECKS,
    CASE_CHECKS_BEFORE,
    TABLES,
    compile_case_checks,
    compile_ddl,
    compile_tables,
    migrate_premium_flow,
    stale_case_checks,
)

#: Tabeller som finns i modellerna men inte i Lakebase före migrationen
NOT_IN_LAKEBASE = {*TABLES, "portfolios", "portfolio_holdings", "trades"}
#: Villkoren på cases som de infördes i Lakebase 2026-10-24 (F5-1, före paket A)
OLD_CASE_CHECKS = CASE_CHECKS_BEFORE


def _signature(engine, schema: str, table: str) -> dict[str, set]:
    """Kolumner, villkor och index för en tabell – för jämförelse med create_all."""
    params = {"s": schema, "t": table, "p": f"{schema}."}
    with engine.connect() as conn:
        columns = conn.exec_driver_sql(
            "SELECT column_name, data_type, character_maximum_length, numeric_precision, numeric_scale, "
            "is_nullable, column_default FROM information_schema.columns "
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


def _lakebase_like(schema) -> None:
    """Dagens Lakebase: befintliga tabeller med data och cases med villkoren före paket A."""
    tables = [t for t in Base.metadata.sorted_tables if t.name not in NOT_IN_LAKEBASE]
    Base.metadata.create_all(schema.engine, tables=tables)
    with schema.engine.begin() as conn:
        for name, definition in OLD_CASE_CHECKS.items():
            conn.exec_driver_sql(f"ALTER TABLE cases DROP CONSTRAINT {name}")
            conn.exec_driver_sql(f"ALTER TABLE cases ADD CONSTRAINT {name} CHECK ({definition})")


def _case(number: str, case_type: str, employer=None, channel="manual") -> Case:
    return Case(case_number=number, case_type=case_type, status="open", employer_id=employer, channel=channel,
                received_date=date(2026, 11, 2), details={}, created_by="test")


def test_migrationen_kraver_postgres():
    with pytest.raises(RuntimeError, match="Postgres"):
        migrate_premium_flow(create_engine("sqlite://"))


def test_ddl_skapar_de_fem_tabellerna_och_byter_tre_villkor_pa_cases():
    statements = compile_ddl(postgresql.dialect())
    created = [s.split()[2] for s in statements if s.startswith("CREATE TABLE")]
    assert created == ["salary_files", "invoices", "invoice_lines", "bank_events", "payment_allocations"]
    altered = [s for s in statements if s.startswith("ALTER TABLE")]
    assert altered == compile_case_checks(postgresql.dialect())
    assert all(s.startswith("ALTER TABLE cases ") for s in altered)
    assert [s.split()[-1] for s in altered if "DROP CONSTRAINT" in s] == list(CASE_CHECKS)
    # Inget rör premium_transactions eller andra befintliga tabeller
    assert not any("premium_transactions ADD" in s or s.startswith("ALTER TABLE premium") for s in statements)
    assert statements == compile_tables(postgresql.dialect()) + altered
    assert "%%" not in " ".join(statements)
    added = " ".join(s for s in altered if "ADD CONSTRAINT" in s)
    for value in ("'salary_file_deviation'", "'payment_overdue'", "'payment_unmatched'", "'system'"):
        assert value in added


def test_villkor_som_saknar_modellens_varden_raknas_som_gamla():
    old = {name: f"CHECK ({definition})" for name, definition in OLD_CASE_CHECKS.items()}
    assert stale_case_checks(old) == list(CASE_CHECKS)
    assert stale_case_checks({}) == list(CASE_CHECKS)
    new = {
        "ck_cases_type": "CHECK (case_type IN ('salary_report', 'salary_file_deviation', 'payment_overdue', "
                         "'payment_unmatched'))",
        "ck_cases_channel": "CHECK (channel IN ('manual', 'employer_file', 'customer_portal', 'chatbot', 'system'))",
        "ck_cases_subject": "CHECK (... OR case_type = 'payment_unmatched')",
    }
    assert stale_case_checks(new) == []
    assert stale_case_checks({**new, "ck_cases_channel": old["ck_cases_channel"]}) == ["ck_cases_channel"]


@pytest.mark.skipif(not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")
def test_migrationen_infor_premieflodet_och_blir_identisk_med_create_all():
    with isolated_schema() as lakebase_like, isolated_schema() as fresh:
        Base.metadata.create_all(fresh.engine)
        _lakebase_like(lakebase_like)
        ids = seed_insurance(lakebase_like.session_factory)
        with lakebase_like.session_factory() as s:
            s.add(_case("CASE-000001", "salary_report", employer=ids.employer))
        with pytest.raises(IntegrityError), lakebase_like.session_factory() as s:
            s.add(_case("CASE-000002", "payment_unmatched", channel="system"))  # före: villkoren stoppar

        dry = migrate_premium_flow(lakebase_like.engine)  # torrkörning är standard
        assert not dry.applied and not dry.already_applied
        assert dry.row_counts["premium_transactions"] == 5 and dry.row_counts["cases"] == 1
        assert set(dry.case_checks) == set(CASE_CHECKS) and all(dry.case_checks.values())
        assert dry.drift == {} and dry.problems == []
        assert not set(TABLES) & set(inspect(lakebase_like.engine).get_table_names())

        done = migrate_premium_flow(lakebase_like.engine, dry_run=False)
        assert done.applied and done.row_counts == dry.row_counts  # inga rader ändrade
        assert migrate_premium_flow(lakebase_like.engine, dry_run=False).already_applied  # idempotent
        assert migrate_premium_flow(lakebase_like.engine).already_applied

        names = set(inspect(lakebase_like.engine).get_table_names())
        assert set(TABLES) <= names
        assert not names & {"portfolios", "portfolio_holdings", "trades"}  # inget annat skapades
        for table in (*TABLES, "cases"):
            assert _signature(lakebase_like.engine, lakebase_like.name, table) == \
                _signature(fresh.engine, fresh.name, table), table

        # Det lättade villkoret: en oallokerad inbetalning från okänd betalare kan bli ärende
        with lakebase_like.session_factory() as s:
            s.add(_case("CASE-000002", "payment_unmatched", channel="system"))
        with pytest.raises(IntegrityError), lakebase_like.session_factory() as s:
            s.add(_case("CASE-000003", "payment_overdue", channel="system"))  # gäller fortfarande någon


@pytest.mark.skipif(not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")
def test_torrkorningen_ar_skrivskyddad_och_delvis_inforande_stoppar():
    with isolated_schema() as lakebase_like:
        _lakebase_like(lakebase_like)
        dry = migrate_premium_flow(lakebase_like.engine)
        assert dry.statements and not dry.applied
        # Torrkörningen kör i en READ ONLY-transaktion; det går inte att skriva i samma läge
        with lakebase_like.engine.connect() as conn:
            tx = conn.begin()
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            with pytest.raises(Exception, match="read-only"):
                conn.exec_driver_sql(compile_tables(lakebase_like.engine.dialect)[0])
            tx.rollback()

        # Ett villkor bytt för hand men inga tabeller: delvis infört
        with lakebase_like.engine.begin() as conn:
            for statement in compile_case_checks(lakebase_like.engine.dialect, ["ck_cases_channel"]):
                conn.exec_driver_sql(statement)
        with pytest.raises(RuntimeError, match="delvis"):
            migrate_premium_flow(lakebase_like.engine)
        with pytest.raises(RuntimeError, match="delvis"):
            migrate_premium_flow(lakebase_like.engine, dry_run=False)
        assert not set(TABLES) & set(inspect(lakebase_like.engine).get_table_names())


@pytest.mark.skipif(not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")
def test_saknad_forutsattning_stoppar():
    with isolated_schema() as empty:
        with pytest.raises(RuntimeError, match="saknas"):
            migrate_premium_flow(empty.engine)
