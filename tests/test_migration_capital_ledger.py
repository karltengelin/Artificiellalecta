"""Migrationen som inför kapitaljournalen i Lakebase (paket B steg 2, B-047, P1-PENSION-001 §6 och §12).

Mot en isolerad Postgres (svc_test, eget schema per test) som Lakebase ser ut efter steg 1: alla
tabeller utom journalens fyra. Migrationen ska skapa exakt de fyra tabellerna tomma – samma schema som
create_all – utan att röra befintliga rader eller ge agentrollerna rättigheter, och torrkörningen ska inte
kunna skriva. Övergången från S-04 provas också mot Postgres, med det transaktionsbundna låset.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.dialects import postgresql

from models import Base, LedgerBatch, LedgerCapitalEntry, LedgerGuaranteePart
from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer
from services import capital_ledger as cl
from services.ledger_extract import build_ledger_extract
from services.valuation_extract import build_extract
from tests.conftest import seed_insurance
from tests.test_migration_payout_parts import _signature
from tests.test_services_postgres import TEST_URL, isolated_schema
from utils.migration_capital_ledger import TABLES, compile_ddl, migrate_capital_ledger

#: Tabeller som finns i modellerna men inte i Lakebase efter steg 1
NOT_IN_LAKEBASE = {*TABLES, "portfolios", "portfolio_holdings", "trades"}
OPENING = date(2026, 10, 31)
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Kapitaljournalens ingående läge (prov)")
needs_postgres = pytest.mark.skipif(not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")


def _lakebase_like(schema):
    tables = [t for t in Base.metadata.sorted_tables if t.name not in NOT_IN_LAKEBASE]
    Base.metadata.create_all(schema.engine, tables=tables)
    return seed_insurance(schema.session_factory)


def test_migrationen_kraver_postgres():
    with pytest.raises(RuntimeError, match="Postgres"):
        migrate_capital_ledger(create_engine("sqlite://"))


def test_ddl_skapar_fyra_tabeller_utan_rattigheter():
    statements = compile_ddl(postgresql.dialect())
    created = [s.split()[2] for s in statements if s.startswith("CREATE TABLE")]
    assert created == list(TABLES)
    assert all(s.startswith(("CREATE TABLE", "CREATE INDEX", "CREATE UNIQUE INDEX")) for s in statements)
    assert not any("GRANT" in s or "ALTER" in s or "DROP" in s for s in statements)  # inga agenträttigheter (§12)
    assert any("uq_ledger_batches_one_opening" in s and "WHERE" in s for s in statements)


@needs_postgres
def test_migrationen_infor_journalen_och_blir_identisk_med_create_all():
    with isolated_schema() as lakebase_like, isolated_schema() as fresh:
        Base.metadata.create_all(fresh.engine)
        _lakebase_like(lakebase_like)

        dry = migrate_capital_ledger(lakebase_like.engine)  # torrkörning är standard
        assert not dry.applied and not dry.already_applied
        assert dry.drift == {} and dry.problems == []
        assert not set(TABLES) & set(inspect(lakebase_like.engine).get_table_names())

        done = migrate_capital_ledger(lakebase_like.engine, dry_run=False)
        assert done.applied and done.row_counts == dry.row_counts  # inga rader i befintliga tabeller ändrade
        assert migrate_capital_ledger(lakebase_like.engine, dry_run=False).already_applied  # idempotent
        assert migrate_capital_ledger(lakebase_like.engine).already_applied

        for table in TABLES:
            assert _signature(lakebase_like.engine, lakebase_like.name, table) == \
                _signature(fresh.engine, fresh.name, table), table


@needs_postgres
def test_delvis_inford_journal_och_saknad_forutsattning_stoppar():
    with isolated_schema() as schema:
        _lakebase_like(schema)
        Base.metadata.tables["ledger_batches"].create(schema.engine)
        with pytest.raises(RuntimeError, match="delvis införd"):
            migrate_capital_ledger(schema.engine, dry_run=False)
    with isolated_schema() as schema:
        tables = [t for t in Base.metadata.sorted_tables
                  if t.name not in NOT_IN_LAKEBASE | {"valuation_extracts", "valuation_runs", "valuation_decisions"}]
        Base.metadata.create_all(schema.engine, tables=tables)
        with pytest.raises(RuntimeError, match="valuation_extracts"):
            migrate_capital_ledger(schema.engine)


@needs_postgres
def test_overgangen_fran_s04_mot_postgres():
    with isolated_schema() as schema:
        _lakebase_like(schema)
        migrate_capital_ledger(schema.engine, dry_run=False)
        service = ServiceLayer(session_factory=schema.session_factory, rules=ProductRuleCatalog())
        review = service.execute("preview_ledger_opening", HUMAN, {}).output.payload
        assert review["passed"], review["problems"] or review["controls"]
        opened = service.execute("open_capital_ledger", HUMAN,
                                 {"reviewed_checksum": review["review_checksum"]}).output.payload
        assert opened["created"]
        again = service.execute("open_capital_ledger", HUMAN,
                                {"reviewed_checksum": review["review_checksum"]}).output.payload
        assert not again["created"]
        with schema.session_factory() as s:
            s04 = build_extract(s, OPENING)
            ledger = build_ledger_extract(s, OPENING)
            assert ledger.approved
            assert [(p.policy_id, p.capital) for p in ledger.policies] == [(p.policy_id, p.capital) for p in s04.policies]
            assert s.scalar(select(func.count()).select_from(LedgerBatch)) == 1
            assert s.scalar(select(func.count()).select_from(LedgerGuaranteePart)) == \
                s.scalar(select(func.count()).select_from(LedgerCapitalEntry)) == \
                sum(len(p.guarantee_parts) for p in s04.policies)
            cl.verify_opening(s, cl.opening_batch(s))
