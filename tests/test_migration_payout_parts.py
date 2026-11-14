"""Migrationen som inför uttagsdelarna i Lakebase (paket B steg 1, B-047, P1-PENSION-001 §4 och §12).

Mot en isolerad Postgres (svc_test, eget schema per test) som Lakebase ser ut före steg 1: alla
tabeller utom uttagsdelarna, `ck_cases_type` med paket A:s fyra typer och `ck_policy_states_state`
med B-022:s fem lägen. Migrationen ska skapa exakt de två tabellerna, byta exakt två villkor och
ge varje förmån del 1 – samma schema som create_all – och torrkörningen ska inte kunna skriva.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from models import Base, Case, PayoutPart, PayoutPartState, PolicyState
from tests.conftest import seed_insurance
from tests.test_services_postgres import TEST_URL, isolated_schema
from utils.migration_payout_parts import (
    CHECKS,
    CHECKS_BEFORE,
    TABLES,
    compile_ddl,
    compile_tables,
    migrate_payout_parts,
    stale_checks,
)

#: Tabeller som finns i modellerna men inte i Lakebase före steg 1
NOT_IN_LAKEBASE = {*TABLES, "portfolios", "portfolio_holdings", "trades"}
TODAY = date(2026, 11, 14)
needs_postgres = pytest.mark.skipif(not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")


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


def _lakebase_like(schema, *, with_payout: bool = False):
    """Lakebase före steg 1, med testbeståndet; `with_payout` ger försäkringen ett gammalt uttagsläge."""
    tables = [t for t in Base.metadata.sorted_tables if t.name not in NOT_IN_LAKEBASE - set(TABLES)]
    Base.metadata.create_all(schema.engine, tables=tables)
    ids = seed_insurance(schema.session_factory)  # skapar del 1 – tas bort nedan som före steg 1
    with schema.engine.begin() as conn:
        for table, name, _, _ in CHECKS:
            conn.exec_driver_sql(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({CHECKS_BEFORE[name]})")
        conn.exec_driver_sql("DROP TABLE payout_part_states")
        conn.exec_driver_sql("DROP TABLE payout_parts")
    if with_payout:
        with schema.session_factory() as s:
            paid_up = s.scalar(select(PolicyState).where(PolicyState.state == "paid_up"))
            paid_up.valid_to = date(2026, 5, 31)
            s.flush()
            s.add(PolicyState(policy_id=ids.policy, state="in_payout", valid_from=date(2026, 6, 1)))
            s.commit()
    return ids


def test_migrationen_kraver_postgres():
    with pytest.raises(RuntimeError, match="Postgres"):
        migrate_payout_parts(create_engine("sqlite://"))


def test_ddl_skapar_tva_tabeller_och_byter_tva_villkor():
    first, last = compile_ddl(postgresql.dialect())
    created = [s.split()[2] for s in first if s.startswith("CREATE TABLE")]
    assert created == ["payout_parts", "payout_part_states"]
    assert first[:len(compile_tables(postgresql.dialect()))] == compile_tables(postgresql.dialect())
    altered = [s for s in first + last if s.startswith("ALTER TABLE")]
    assert [s.split()[2] for s in altered] == ["cases", "cases", "policy_states", "policy_states"]
    assert "'payout_reconstruction'" in altered[1] and "'in_payout'" not in last[1]
    assert not any("GRANT" in s for s in first + last)  # inga rättigheter till agentrollerna (§12)


def test_villkor_som_saknar_modellens_varden_raknas_som_gamla():
    old = {name: f"CHECK ({definition})" for name, definition in CHECKS_BEFORE.items()}
    assert stale_checks(old) == [name for _, name, _, _ in CHECKS]
    new = {"ck_cases_type": "CHECK (case_type IN ('salary_report', 'payout_reconstruction'))",
           "ck_policy_states_state": "CHECK (state IN ('premium_paying', 'paid_up'))"}
    assert stale_checks(new) == []
    assert stale_checks({**new, "ck_policy_states_state": old["ck_policy_states_state"]}) == ["ck_policy_states_state"]


@needs_postgres
def test_migrationen_infor_uttagsdelarna_och_blir_identisk_med_create_all():
    with isolated_schema() as lakebase_like, isolated_schema() as fresh:
        Base.metadata.create_all(fresh.engine)
        ids = _lakebase_like(lakebase_like)

        dry = migrate_payout_parts(lakebase_like.engine, today=TODAY)  # torrkörning är standard
        assert not dry.applied and not dry.already_applied
        assert (dry.transition.benefits, dry.transition.parts_to_create, dry.transition.moved) == (1, 1, [])
        assert dry.drift == {} and dry.problems == []
        assert not set(TABLES) & set(inspect(lakebase_like.engine).get_table_names())

        done = migrate_payout_parts(lakebase_like.engine, dry_run=False, today=TODAY)
        assert done.applied and done.row_counts == dry.row_counts  # inga rader i befintliga tabeller ändrade
        assert migrate_payout_parts(lakebase_like.engine, dry_run=False).already_applied  # idempotent
        assert migrate_payout_parts(lakebase_like.engine).already_applied

        for table in (*TABLES, "cases", "policy_states"):
            assert _signature(lakebase_like.engine, lakebase_like.name, table) == \
                _signature(fresh.engine, fresh.name, table), table
        with lakebase_like.session_factory() as s:
            (part,) = s.scalars(select(PayoutPart)).all()
            (state,) = s.scalars(select(PayoutPartState)).all()
            assert (part.benefit_id, part.part_number, state.state, state.valid_to) == (ids.benefit, 1, "not_started", None)
        with pytest.raises(IntegrityError), lakebase_like.session_factory() as s:
            s.add(PolicyState(policy_id=ids.policy, state="payout_paused", valid_from=date(2027, 1, 1)))
            s.flush()


@needs_postgres
def test_gammalt_uttagslage_flyttas_med_rekonstruktionsarende():
    with isolated_schema() as lakebase_like:
        ids = _lakebase_like(lakebase_like, with_payout=True)
        dry = migrate_payout_parts(lakebase_like.engine, today=TODAY)
        (moved,) = dry.transition.moved
        assert moved.premium_action == "reopen" and moved.case_number is None
        done = migrate_payout_parts(lakebase_like.engine, dry_run=False, today=TODAY)
        assert done.row_counts["policy_states"] == dry.row_counts["policy_states"] - 1
        assert done.row_counts["cases"] == dry.row_counts["cases"] + 1
        with lakebase_like.session_factory() as s:
            case = s.scalar(select(Case))
            assert (case.case_type, case.policy_id, case.received_date) == ("payout_reconstruction", ids.policy, TODAY)
            current = s.scalar(select(PolicyState).where(PolicyState.valid_to.is_(None)))
            assert (current.state, current.valid_from) == ("paid_up", date(2026, 1, 1))
            assert sorted(s.state for s in s.scalars(select(PayoutPartState))) == ["in_payout", "not_started"]


@needs_postgres
def test_torrkorningen_ar_skrivskyddad_och_hinder_stoppar():
    with isolated_schema() as lakebase_like:
        ids = _lakebase_like(lakebase_like)
        with lakebase_like.session_factory() as s:
            current = s.scalar(select(PolicyState).where(PolicyState.valid_to.is_(None)))
            current.valid_to = date(2026, 5, 31)
            s.flush()
            s.add(PolicyState(policy_id=ids.policy, state="terminated", valid_from=date(2026, 6, 1)))
            s.commit()
        dry = migrate_payout_parts(lakebase_like.engine)
        assert any("PB10" in p for p in dry.problems)
        with pytest.raises(RuntimeError, match="Hinder"):
            migrate_payout_parts(lakebase_like.engine, dry_run=False)
        assert not set(TABLES) & set(inspect(lakebase_like.engine).get_table_names())


@needs_postgres
def test_delvis_inforande_och_saknad_forutsattning_stoppar():
    with isolated_schema() as lakebase_like:
        _lakebase_like(lakebase_like)
        with lakebase_like.engine.begin() as conn:
            for statement in compile_tables(lakebase_like.engine.dialect):
                conn.exec_driver_sql(statement)
        with pytest.raises(RuntimeError, match="delvis"):
            migrate_payout_parts(lakebase_like.engine)
    with isolated_schema() as empty, pytest.raises(RuntimeError, match="saknas"):
        migrate_payout_parts(empty.engine)
