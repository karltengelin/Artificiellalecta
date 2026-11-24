"""Migrationen för skatt, konto, bankuppdrag och kvitton (paket B steg 6, P1-PENSION-001 §12, Karls val X13).

Mot en isolerad Postgres (svc_test, eget schema per test) som Lakebase ser ut efter steg 5: journalen med
stängningen, planerna och anspråken, men inga tabeller för skattestatus, konto, bankfil, uppdrag, rader och
kvitton, och villkoren utan `payout_settlement`, skatteskulden och de nya ärendetyperna. Steg 6:s kod ska då
blockera bankuppdragen. Migrationen ska ge exakt samma schema som create_all utan att röra några rader eller
ge agentrollerna rättigheter, och torrkörningen ska inte kunna skriva. Därefter betalas en månadsrätt mot
Postgres (fall 22) med villkoren för den förberedda filen och den icke-negativa skatteskulden.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.dialects import postgresql

from models import Base, PayoutFile
from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer
from services import capital_ledger as cl
from services import payout_orders as po
from services import valuation_bases as vb
from services.errors import BlockedError
from tests import test_payout_orders as orders
from tests import test_premium_month_export as export_tests
from tests.conftest import seed_insurance
from tests.test_migration_payout_parts import _signature
from tests.test_services_postgres import TEST_URL, isolated_schema
from utils.migration_payout_orders import (
    CHECKS,
    CHECKS_BEFORE,
    TABLES,
    compile_ddl,
    migrate_payout_orders,
)

NOT_IN_LAKEBASE = {"portfolios", "portfolio_holdings", "trades"}
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Bankuppdrag (prov)")
needs_postgres = pytest.mark.skipif(not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")


def _as_after_step5(engine) -> None:
    """Tar bort steg 6:s delar så att schemat ser ut som i Lakebase efter steg 5."""
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
    _as_after_step5(schema.engine)
    return service


def test_migrationen_kraver_postgres():
    with pytest.raises(RuntimeError, match="Postgres"):
        migrate_payout_orders(create_engine("sqlite://"))


def test_ddl_ror_bara_steg_6_journalens_villkor_och_arendena():
    statements = compile_ddl(postgresql.dialect())
    touched = {*TABLES, "ledger_batches", "ledger_capital_entries", "cases"}
    assert all(any(t in s for t in touched) for s in statements)
    assert sum(s.startswith("CREATE TABLE") for s in statements) == 6
    # Inga rättigheter, borttagna tabeller eller radändringar (ON DELETE RESTRICT i en FK räknas inte)
    assert not any(s.lstrip().upper().startswith(("GRANT", "DROP TABLE", "DELETE", "UPDATE", "INSERT"))
                   for s in statements)
    joined = "\n".join(statements)
    for value in ("'payout_settlement'", "'withholding'", "'payout_returned'", "'tax_liability'",
                  "'payout_hindrance'", "'tax_status'"):
        assert value in joined, value
    assert "CREATE UNIQUE INDEX uq_payout_files_prepared ON payout_files (status) WHERE status = 'prepared'" in joined


def test_villkoren_fore_ar_steg_5_utan_steg_6():
    for name, definition in CHECKS_BEFORE.items():
        assert "payout_settlement" not in definition and "tax_liability" not in definition
        assert "payout_hindrance" not in definition, name


@needs_postgres
def test_migrationen_infor_bankuppdragen_och_blir_identisk_med_create_all():
    with isolated_schema() as lakebase_like, isolated_schema() as fresh:
        Base.metadata.create_all(fresh.engine)
        service = _lakebase_like(lakebase_like)
        with lakebase_like.session_factory() as s:
            assert not po.orders_present(s)
        with pytest.raises(BlockedError, match="migrate_payout_orders"):
            service.execute("list_payout_orders", HUMAN, {})

        dry = migrate_payout_orders(lakebase_like.engine)  # torrkörning är standard
        assert not dry.applied and not dry.already_applied and dry.problems == []
        assert not set(TABLES) & set(inspect(lakebase_like.engine).get_table_names())

        done = migrate_payout_orders(lakebase_like.engine, dry_run=False)
        assert done.applied and done.row_counts == dry.row_counts and all(done.state.values())
        assert migrate_payout_orders(lakebase_like.engine, dry_run=False).already_applied  # idempotent
        assert migrate_payout_orders(lakebase_like.engine).already_applied
        for table in (*TABLES, "ledger_batches", "ledger_capital_entries", "cases"):
            assert _signature(lakebase_like.engine, lakebase_like.name, table) == \
                _signature(fresh.engine, fresh.name, table), table
        with lakebase_like.session_factory() as s:
            cl.verify_opening(s, cl.opening_batch(s))  # det ingående läget är orört
        listed = service.execute("list_payout_orders", HUMAN, {}).output.payload
        assert listed["count"] == 0 and listed["claims"] == []


@needs_postgres
def test_delvis_inford_migration_och_saknat_steg_5_stoppar():
    with isolated_schema() as schema:
        Base.metadata.create_all(schema.engine, tables=[t for t in Base.metadata.sorted_tables
                                                        if t.name not in NOT_IN_LAKEBASE])
        _as_after_step5(schema.engine)
        Base.metadata.create_all(schema.engine, tables=[Base.metadata.tables["tax_statuses"]])
        with pytest.raises(RuntimeError, match="delvis"):
            migrate_payout_orders(schema.engine, dry_run=False)
    with isolated_schema() as schema:
        Base.metadata.create_all(schema.engine, tables=[t for t in Base.metadata.sorted_tables
                                                        if t.name not in {*NOT_IN_LAKEBASE, *TABLES, "payout_amounts",
                                                                          "pension_claims", "pension_claim_fundings"}])
        with pytest.raises(RuntimeError, match="steg 1–5"):
            migrate_payout_orders(schema.engine)


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
claimed = orders.claimed
ready = orders.ready


def test_utbetalning_med_kvitto_mot_postgres(chain_on_postgres, ready):
    """Fall 22 mot Postgres: bankfil, godkännande, utfört kvitto och verifikationen `payout_settlement`."""
    db = ready
    assert db.engine is chain_on_postgres.engine
    made = orders.create(db)
    with db.engine.begin() as conn, pytest.raises(Exception, match="uq_payout_files_prepared"):
        conn.execute(text("UPDATE payout_files SET status = 'prepared' WHERE status = 'superseded'"))
        conn.execute(text(
            "INSERT INTO payout_files (id, file_reference, payment_day, execution_date, status, content, checksum, "
            "created_by) SELECT gen_random_uuid(), 'X', payment_day, execution_date, 'prepared', content, "
            "repeat('a', 64), 'prov' FROM payout_files"))
    approved = orders.approve(db, made)
    result = orders.receipts(db, approved)
    assert Decimal(result["settlement"]["withholding_sek"]) == orders.TAX
    assert orders.liability(db) == 0 and orders.tax_liability(db) == orders.TAX
    assert orders.receipts(db, approved)["new"] == 0
    with db.factory() as s:
        assert s.scalar(select(PayoutFile.status)) == "approved"
    with db.engine.begin() as conn, pytest.raises(Exception, match="ck_ledger_capital_entries_accounts"):
        conn.execute(text(  # skatteskulden blir aldrig negativ
            "UPDATE ledger_capital_entries SET balance_after_sek = -1, amount_sek = -1 - balance_before_sek "
            "WHERE account = 'tax_liability'"))
