"""Migrationen för månadsrätt och bolagskonto (paket B steg 5, P1-PENSION-001 §12, Karls val W12).

Mot en isolerad Postgres (svc_test, eget schema per test) som Lakebase ser ut efter steg 4: journalen med
stängningen och planerna, men inga tabeller för belopp, anspråk och finansiering och villkoren utan
`company_capital`. Steg 5:s kod ska då stänga november som steg 4. Migrationen ska ge exakt samma schema som
create_all utan att röra några rader eller ge agentrollerna rättigheter, och torrkörningen ska inte kunna
skriva. Därefter bokas en standardstart med månadsrätt mot Postgres (fall 1), med villkoren för anspråkets
fördelning och de icke-negativa kontona.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.dialects import postgresql

from models import Base, InsuredPerson, PensionClaim, ValuationBasis
from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer
from services import capital_ledger as cl
from services import month_close as mc
from services import pension_claims as pc
from services import valuation_bases as vb
from services.errors import BlockedError
from services.ledger_extract import build_ledger_extract
from services.operations import common
from tests import test_premium_month_export as export_tests
from tests.conftest import seed_insurance
from tests.test_migration_payout_parts import _signature
from tests.test_services_postgres import TEST_URL, isolated_schema
from utils.migration_pension_claims import (
    CHECKS,
    CHECKS_BEFORE,
    TABLES,
    compile_ddl,
    migrate_pension_claims,
)
from utils.migration_payout_orders import TABLES as STEP6_TABLES

NOT_IN_LAKEBASE = {*STEP6_TABLES, "portfolios", "portfolio_holdings", "trades"}
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Månadsrätter (prov)")
needs_postgres = pytest.mark.skipif(not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")
ACCOUNTS_CHECK = "ck_ledger_capital_entries_accounts"


def _as_after_step4(engine) -> None:
    """Tar bort steg 5:s delar så att schemat ser ut som i Lakebase efter steg 4."""
    with engine.begin() as conn:
        for table in reversed(TABLES):
            conn.exec_driver_sql(f"DROP TABLE {table}")
        conn.exec_driver_sql(f"ALTER TABLE ledger_capital_entries DROP CONSTRAINT {ACCOUNTS_CHECK}")
        tables = {name: table for table, _, name, _ in CHECKS}
        for name, definition in CHECKS_BEFORE.items():
            conn.exec_driver_sql(f"ALTER TABLE {tables[name]} DROP CONSTRAINT {name}")
            conn.exec_driver_sql(f"ALTER TABLE {tables[name]} ADD CONSTRAINT {name} CHECK ({definition})")


def _service(schema) -> ServiceLayer:
    return ServiceLayer(session_factory=schema.session_factory, rules=ProductRuleCatalog())


def _lakebase_like(schema) -> ServiceLayer:
    Base.metadata.create_all(schema.engine, tables=[t for t in Base.metadata.sorted_tables
                                                    if t.name not in NOT_IN_LAKEBASE])
    seed_insurance(schema.session_factory)
    with schema.session_factory() as s:
        vb.add_missing_defaults(s)
        s.commit()
    service = _service(schema)
    review = service.execute("preview_ledger_opening", HUMAN, {}).output.payload
    assert review["passed"], review["problems"]
    service.execute("open_capital_ledger", HUMAN, {"reviewed_checksum": review["review_checksum"]})
    _as_after_step4(schema.engine)
    return service


def _adopt_avk(service, schema, code: str, rates: dict[str, str], valid_from: str, supersedes: str) -> None:
    with schema.session_factory() as s:
        base = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "AVK-SIM-2026-01")).assumptions
    months = [*vb.normalize("return_series", base)["months"], *({"month": m, "rate": r} for m, r in rates.items())]
    service.execute("propose_valuation_basis", HUMAN, {
        "code": code, "title": "Syntetisk avkastning", "assumptions": vb.normalize("return_series", {**base, "months": months}),
        "source_refs": "prov", "supersedes_code": supersedes})
    service.execute("adopt_valuation_basis", HUMAN, {"code": code, "valid_from": valid_from, "decision_ref": "prov"})


def _close(service, month: str) -> dict:
    review = service.execute("prepare_month_close", HUMAN, {"month": month}).output.payload
    assert review["passed"], review["problems"]
    return service.execute("close_policy_month", HUMAN, {"month": month,
                                                         "reviewed_checksum": review["review_checksum"]}).output.payload


def test_migrationen_kraver_postgres():
    with pytest.raises(RuntimeError, match="Postgres"):
        migrate_pension_claims(create_engine("sqlite://"))


def test_ddl_ror_bara_steg_5_journalens_villkor_och_arendena():
    statements = compile_ddl(postgresql.dialect())
    touched = {*TABLES, "ledger_batches", "ledger_capital_entries", "cases"}
    assert all(any(t in s for t in touched) for s in statements)
    assert sum(s.startswith("CREATE TABLE") for s in statements) == 3
    # Inga rättigheter, borttagna tabeller eller radändringar (ON DELETE RESTRICT i en FK räknas inte)
    assert not any(s.lstrip().upper().startswith(("GRANT", "DROP TABLE", "DELETE", "UPDATE", "INSERT"))
                   for s in statements)
    assert sum("'company_capital'" in s for s in statements) == 4 and any(ACCOUNTS_CHECK in s for s in statements)


@needs_postgres
def test_migrationen_infor_manadsratterna_och_blir_identisk_med_create_all(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: date(2026, 12, 1))
    with isolated_schema() as lakebase_like, isolated_schema() as fresh:
        Base.metadata.create_all(fresh.engine)
        service = _lakebase_like(lakebase_like)
        with lakebase_like.session_factory() as s:
            assert not pc.claims_present(s)
        # Steg 5:s kod stänger november som steg 4 när migrationen inte är körd
        _adopt_avk(service, lakebase_like, "AVK-SIM-2026-02", {"2026-11-01": "0.002"}, "2026-11-01",
                   "AVK-SIM-2026-01")
        closed = _close(service, "2026-11-01")
        assert closed["created"] and "pension" not in closed and "claims" not in closed["totals"]
        with pytest.raises(BlockedError, match="migrate_pension_claims"):
            service.execute("register_company_capital", HUMAN, {"amount_sek": "100.00", "decided_on": "2026-11-20",
                                                                "document_ref": "prov"})

        dry = migrate_pension_claims(lakebase_like.engine)  # torrkörning är standard
        assert not dry.applied and not dry.already_applied and dry.problems == []
        assert not set(TABLES) & set(inspect(lakebase_like.engine).get_table_names())

        done = migrate_pension_claims(lakebase_like.engine, dry_run=False)
        assert done.applied and done.row_counts == dry.row_counts and all(done.state.values())
        assert migrate_pension_claims(lakebase_like.engine, dry_run=False).already_applied  # idempotent
        assert migrate_pension_claims(lakebase_like.engine).already_applied
        for table in (*TABLES, "ledger_batches", "ledger_capital_entries", "cases"):
            assert _signature(lakebase_like.engine, lakebase_like.name, table) == \
                _signature(fresh.engine, fresh.name, table), table
        with lakebase_like.session_factory() as s:
            cl.verify_opening(s, cl.opening_batch(s))  # det ingående läget och novembers stängning är orörda
            mc.verify_month(s, cl.effective_batch(s, date(2026, 11, 30)))
            assert build_ledger_extract(s, date(2026, 11, 30)).approved
        made = service.execute("register_company_capital", HUMAN, {
            "amount_sek": "100.00", "decided_on": "2026-12-02", "document_ref": "prov"}).output.payload
        assert made["created"] and made["month"] == "2026-12-01"


@needs_postgres
def test_delvis_inford_migration_och_saknat_steg_4_stoppar():
    with isolated_schema() as schema:
        Base.metadata.create_all(schema.engine, tables=[t for t in Base.metadata.sorted_tables
                                                        if t.name not in NOT_IN_LAKEBASE])
        _as_after_step4(schema.engine)
        Base.metadata.create_all(schema.engine, tables=[Base.metadata.tables["payout_amounts"]])
        with pytest.raises(RuntimeError, match="delvis"):
            migrate_pension_claims(schema.engine, dry_run=False)
    with isolated_schema() as schema:
        Base.metadata.create_all(schema.engine, tables=[t for t in Base.metadata.sorted_tables
                                                        if t.name not in {*NOT_IN_LAKEBASE, *TABLES, "payout_splits",
                                                                          "payout_plans", "payout_requests"}
                                                        and not t.name.startswith("ledger_")])
        with pytest.raises(RuntimeError, match="steg 1–4"):
            migrate_pension_claims(schema.engine)


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


def test_standardstart_med_manadsratt_mot_postgres(chain_on_postgres, chain, clock):
    """Fall 1 och 14 mot Postgres: standardplan, beslutat M, anspråk, debitering per spår och betalningsskuld."""
    db = chain
    assert db.engine is chain_on_postgres.engine
    with db.factory() as s:  # B fyller 66 i november 2026 (som at_66 i test_payout_plans.py)
        person = s.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == export_tests.PERSONS["B"]))
        person.personal_id_number = "19601103" + export_tests.PERSONS["B"][-4:]
        s.commit()
    review = export_tests.run(db, "preview_ledger_opening", {}).payload
    export_tests.run(db, "open_capital_ledger", {"reviewed_checksum": review["review_checksum"]})
    with db.factory() as s:
        base = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "AVK-SIM-2026-01")).assumptions
    months = [*vb.normalize("return_series", base)["months"], {"month": "2026-11-01", "rate": "0.002"}]
    export_tests.run(db, "propose_valuation_basis", {
        "code": "AVK-SIM-2026-02", "title": "Syntetisk avkastning", "source_refs": "prov",
        "assumptions": vb.normalize("return_series", {**base, "months": months}), "supersedes_code": "AVK-SIM-2026-01"})
    export_tests.run(db, "adopt_valuation_basis", {"code": "AVK-SIM-2026-02", "valid_from": "2026-11-01",
                                                   "decision_ref": "prov"})
    export_tests.run(db, "register_company_capital", {"amount_sek": "50000.00", "decided_on": "2026-11-20",
                                                      "document_ref": "Ägarbeslut (prov)"})

    clock.today = date(2026, 12, 1)
    closing = export_tests.run(db, "prepare_month_close", {"month": "2026-11-01"}).payload
    assert closing["passed"], closing["problems"]
    [claim] = closing["pension"]["claims"]
    assert claim["payment_day"] == "2026-12-01" and claim["right_number"] == 1
    export_tests.run(db, "close_policy_month", {"month": "2026-11-01", "reviewed_checksum": closing["review_checksum"]})
    nov_end = date(2026, 11, 30)
    with db.factory() as s:
        mc.verify_month(s, cl.effective_batch(s, nov_end))
        row = s.scalar(select(PensionClaim))
        assert row.gross_sek == row.from_capital_sek + row.company_support_sek + row.unfunded_sek
        assert pc.account_balance(s, pc.LIABILITY, date(2026, 11, 1)) == row.gross_sek
        assert pc.account_balance(s, pc.COMPANY, date(2026, 11, 1)) == Decimal("50000.00")
        assert all(t.balance >= 0 for t in cl.tracks(s, nov_end))
        assert build_ledger_extract(s, nov_end).approved
    again = export_tests.run(db, "close_policy_month", {"month": "2026-11-01",
                                                        "reviewed_checksum": closing["review_checksum"]}).payload
    assert not again["created"]
