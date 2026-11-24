"""Migrationen för dödsfallsbesked, avräkning och dödsbo (paket B steg 7, P1-PENSION-001 §12, Karls val Y12).

Mot en isolerad Postgres (svc_test, eget schema per test) som Lakebase ser ut efter steg 6: journalen med
stängningen, planerna, anspråken och bankuppdragen, men inga tabeller för besked, avräkningar, återföringar och
dödsbo, och villkoren utan `death_reversal`, arvsvinstpoolen, garantiorsaken `death` och de nya ärendetyperna.
Steg 7:s kod ska då blockera dödsfallsoperationerna och stänga som steg 6. Migrationen ska ge exakt samma
schema som create_all utan att röra några rader eller ge agentrollerna rättigheter, och torrkörningen ska inte
kunna skriva. Därefter avräknas ett dödsfall med arvsvinst mot Postgres (fall 26) med villkoret att poolen
aldrig blir negativ, och utan antagen SIM-R står poolen kvar med ett ärende utan person (fall 29).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.dialects import postgresql

from models import Base, Case, DeathSettlement
from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer
from services import capital_ledger as cl
from services import death_reports as dr
from services import valuation_bases as vb
from services.errors import BlockedError
from tests import test_death_reports as deaths
from tests import test_premium_month_export as export_tests
from tests.conftest import seed_insurance
from tests.test_migration_payout_parts import _signature
from tests.test_services_postgres import TEST_URL, isolated_schema
from utils.migration_death_reports import (
    CHECKS,
    CHECKS_BEFORE,
    TABLES,
    compile_ddl,
    migrate_death_reports,
)

NOT_IN_LAKEBASE = {"portfolios", "portfolio_holdings", "trades"}
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Dödsfallsavräkning (prov)")
needs_postgres = pytest.mark.skipif(not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")


def _as_after_step6(engine) -> None:
    """Tar bort steg 7:s delar så att schemat ser ut som i Lakebase efter steg 6."""
    with engine.begin() as conn:
        for table in reversed(TABLES):
            conn.exec_driver_sql(f"DROP TABLE {table}")
        tables = {name: table for table, _, name, _ in CHECKS}
        for name, definition in CHECKS_BEFORE.items():
            conn.exec_driver_sql(f"ALTER TABLE {tables[name]} DROP CONSTRAINT {name}")
            conn.exec_driver_sql(f"ALTER TABLE {tables[name]} ADD CONSTRAINT {name} CHECK ({definition})")


def _lakebase_like(schema) -> ServiceLayer:
    Base.metadata.create_all(schema.engine, tables=[t for t in Base.metadata.sorted_tables
                                                    if t.name not in NOT_IN_LAKEBASE])
    seed_insurance(schema.session_factory)
    with schema.session_factory() as s:
        vb.add_missing_defaults(s)
        s.commit()
    service = ServiceLayer(session_factory=schema.session_factory, rules=ProductRuleCatalog())
    review = service.execute("preview_ledger_opening", HUMAN, {}).output.payload
    assert review["passed"], review["problems"]
    service.execute("open_capital_ledger", HUMAN, {"reviewed_checksum": review["review_checksum"]})
    _as_after_step6(schema.engine)
    return service


def test_migrationen_kraver_postgres():
    with pytest.raises(RuntimeError, match="Postgres"):
        migrate_death_reports(create_engine("sqlite://"))


def test_ddl_ror_bara_steg_7_journalens_villkor_och_arendena():
    statements = compile_ddl(postgresql.dialect())
    touched = {*TABLES, "ledger_capital_entries", "ledger_guarantee_parts", "cases"}
    assert all(any(t in s for t in touched) for s in statements)
    assert sum(s.startswith("CREATE TABLE") for s in statements) == 4
    # Inga rättigheter, borttagna tabeller eller radändringar (ON DELETE RESTRICT i en FK räknas inte)
    assert not any(s.lstrip().upper().startswith(("GRANT", "DROP TABLE", "DELETE", "UPDATE", "INSERT"))
                   for s in statements)
    joined = "\n".join(statements)
    for value in ("'death_reversal'", "'inheritance_pool'", "'death'", "'death_report'", "'death_recovery'"):
        assert value in joined, value
    assert "uq_death_reports_notice" in joined


def test_villkoren_fore_ar_steg_6_utan_steg_7():
    for name, definition in CHECKS_BEFORE.items():
        assert "death" not in definition and "inheritance_pool" not in definition, name
    assert "'tax_liability'" in CHECKS_BEFORE["ck_ledger_capital_entries_accounts"]


@needs_postgres
def test_migrationen_infor_dodsfallstabellerna_och_blir_identisk_med_create_all():
    with isolated_schema() as lakebase_like, isolated_schema() as fresh:
        Base.metadata.create_all(fresh.engine)
        service = _lakebase_like(lakebase_like)
        with lakebase_like.session_factory() as s:
            assert not dr.deaths_present(s)
        with pytest.raises(BlockedError, match="migrate_death_reports"):
            service.execute("get_death_settlement", HUMAN, {"personal_id_number": "198505151234"})

        dry = migrate_death_reports(lakebase_like.engine)  # torrkörning är standard
        assert not dry.applied and not dry.already_applied and dry.problems == []
        assert not set(TABLES) & set(inspect(lakebase_like.engine).get_table_names())

        done = migrate_death_reports(lakebase_like.engine, dry_run=False)
        assert done.applied and done.row_counts == dry.row_counts and all(done.state.values())
        assert migrate_death_reports(lakebase_like.engine, dry_run=False).already_applied  # idempotent
        assert migrate_death_reports(lakebase_like.engine).already_applied
        for table in (*TABLES, "ledger_capital_entries", "ledger_guarantee_parts", "cases"):
            assert _signature(lakebase_like.engine, lakebase_like.name, table) == \
                _signature(fresh.engine, fresh.name, table), table
        with lakebase_like.session_factory() as s:
            cl.verify_opening(s, cl.opening_batch(s))  # det ingående läget är orört
            assert dr.deaths_present(s)


@needs_postgres
def test_delvis_inford_migration_och_saknat_steg_6_stoppar():
    with isolated_schema() as schema:
        Base.metadata.create_all(schema.engine, tables=[t for t in Base.metadata.sorted_tables
                                                        if t.name not in NOT_IN_LAKEBASE])
        _as_after_step6(schema.engine)
        Base.metadata.create_all(schema.engine, tables=[Base.metadata.tables["death_reports"]])
        with pytest.raises(RuntimeError, match="delvis"):
            migrate_death_reports(schema.engine, dry_run=False)
    with isolated_schema() as schema:
        Base.metadata.create_all(schema.engine, tables=[t for t in Base.metadata.sorted_tables
                                                        if t.name not in {*NOT_IN_LAKEBASE, *TABLES, "payout_receipts",
                                                                          "payout_order_lines", "payout_orders",
                                                                          "payout_files", "payout_accounts",
                                                                          "tax_statuses"}])
        with pytest.raises(RuntimeError, match="steg 1–6"):
            migrate_death_reports(schema.engine)


@pytest.fixture
def chain_on_postgres(monkeypatch):
    """Paket A:s testbestånd (export_tests.chain) i ett isolerat Postgres-schema i stället för SQLite."""
    if not TEST_URL:
        pytest.skip("SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")
    with isolated_schema() as schema:
        monkeypatch.setattr(export_tests, "create_engine", lambda *args, **kwargs: schema.engine)
        yield schema


chain = export_tests.chain
clock = export_tests.clock
at_66 = deaths.at_66


def test_dodsfall_och_arvsvinst_mot_postgres(chain_on_postgres, at_66, clock):
    """Fall 26 mot Postgres: avräkning, poolen och fördelningen; poolen kan aldrig bli negativ."""
    db = at_66
    assert db.engine is chain_on_postgres.engine
    deaths.report(db, deaths.A_PNR)
    review = deaths.close_month(db, clock, deaths.NOVEMBER)
    assert deaths.steps(review)["dödsfall"] and deaths.steps(review)["arvsvinstpool"]
    pool = review["death"]["pool"]
    assert Decimal(pool["inflow_sek"]) > 0 and pool["closing_sek"] == "0.00"
    with db.factory() as s:
        assert s.scalar(select(DeathSettlement.death_month)) == deaths.NOVEMBER
    with db.engine.begin() as conn, pytest.raises(Exception, match="ck_ledger_capital_entries_accounts"):
        conn.execute(text(  # arvsvinstpoolen blir aldrig negativ
            "UPDATE ledger_capital_entries SET balance_after_sek = -1, amount_sek = -1 - balance_before_sek "
            "WHERE account = 'inheritance_pool'"))


def test_kvarstaende_pool_mot_postgres(chain_on_postgres, at_66, clock):
    """Fall 29 mot Postgres: utan antagen SIM-R står poolen kvar med ärendet `inheritance_pool` utan person."""
    db = at_66
    with db.engine.begin() as conn:
        conn.execute(text("DELETE FROM valuation_bases WHERE family = 'SIM-R'"))
    deaths.report(db, deaths.A_PNR)
    review = deaths.close_month(db, clock, deaths.NOVEMBER)
    pool = review["death"]["pool"]
    assert pool["distributed_sek"] == "0.00" and pool["closing_sek"] == pool["inflow_sek"]
    with db.factory() as s:
        [case] = s.scalars(select(Case).where(Case.case_type == "inheritance_pool")).all()
        assert case.insured_person_id is None and case.employer_id is None
