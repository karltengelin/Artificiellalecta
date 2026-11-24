"""Migrationen för uttagsplaner (paket B steg 4, P1-PENSION-001 §5 och §12).

Mot en isolerad Postgres (svc_test, eget schema per test) som Lakebase ser ut efter steg 3: journalen med
stängningen, ärendetyperna till och med `payout_reconstruction`, inga tabeller för begäran, planer eller
delning och ingen `plan_id` på garantidelarna. Steg 4:s kod ska då stänga november som steg 3. Migrationen ska
ge exakt samma schema som create_all utan att röra några rader eller ge agentrollerna rättigheter, och
torrkörningen ska inte kunna skriva. Därefter beslutas och bokas en delning mot Postgres.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.dialects import postgresql

from models import Base, InsuredPerson, LedgerGuaranteePart, PayoutPart, ValuationBasis
from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer
from services import capital_ledger as cl
from services import month_close as mc
from services import payout_plans as pl
from services import valuation_bases as vb
from services.errors import BlockedError
from services.ledger_extract import build_ledger_extract
from services.operations import common
from tests import test_premium_month_export as export_tests
from tests.conftest import seed_insurance
from tests.test_migration_payout_parts import _signature
from tests.test_services_postgres import TEST_URL, isolated_schema
from utils.migration_payout_plans import (
    CHECKS_BEFORE,
    PLAN_ID_CHECK,
    PLAN_INDEX,
    TABLES,
    compile_ddl,
    migrate_payout_plans,
)
from utils.migration_pension_claims import TABLES as STEP5_TABLES
from utils.migration_death_reports import TABLES as STEP7_TABLES
from utils.migration_payout_orders import TABLES as STEP6_TABLES

NOT_IN_LAKEBASE = {*STEP7_TABLES, *STEP6_TABLES, *STEP5_TABLES, "portfolios", "portfolio_holdings", "trades"}
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Uttagsplaner (prov)")
needs_postgres = pytest.mark.skipif(not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")


def _as_after_step3(engine) -> None:
    """Tar bort steg 4:s delar så att schemat ser ut som i Lakebase efter steg 3."""
    with engine.begin() as conn:
        conn.exec_driver_sql(f"DROP INDEX {PLAN_INDEX}")
        conn.exec_driver_sql(f"ALTER TABLE ledger_guarantee_parts DROP CONSTRAINT {PLAN_ID_CHECK}")
        conn.exec_driver_sql("ALTER TABLE ledger_guarantee_parts DROP COLUMN plan_id")
        for table in reversed(TABLES):
            conn.exec_driver_sql(f"DROP TABLE {table}")
        for name, definition in CHECKS_BEFORE.items():
            table = "cases" if name.startswith("ck_cases") else "ledger_guarantee_parts"
            conn.exec_driver_sql(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({definition})")


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
    _as_after_step3(schema.engine)
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
        migrate_payout_plans(create_engine("sqlite://"))


def test_ddl_ror_bara_steg_4_och_garantidelarna():
    statements = compile_ddl(postgresql.dialect())
    touched = {"payout_requests", "payout_plans", "payout_splits", "cases", "ledger_guarantee_parts"}
    assert all(any(t in s for t in touched) for s in statements)
    assert sum(s.startswith("CREATE TABLE") for s in statements) == 3
    # Inga rättigheter, borttagna tabeller eller radändringar (ON DELETE RESTRICT i en FK räknas inte)
    assert not any(s.lstrip().upper().startswith(("GRANT", "DROP TABLE", "DELETE", "UPDATE", "INSERT"))
                   for s in statements)
    assert any("'payout_review'" in s for s in statements) and any("'plan'" in s for s in statements)


@needs_postgres
def test_migrationen_infor_uttagsplanerna_och_blir_identisk_med_create_all(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: date(2026, 12, 1))
    with isolated_schema() as lakebase_like, isolated_schema() as fresh:
        Base.metadata.create_all(fresh.engine)
        service = _lakebase_like(lakebase_like)
        with lakebase_like.session_factory() as s:
            assert not pl.plans_present(s)
        # Steg 4:s kod stänger november som steg 3 när migrationen inte är körd
        _adopt_avk(service, lakebase_like, "AVK-SIM-2026-02", {"2026-11-01": "0.002"}, "2026-11-01",
                   "AVK-SIM-2026-01")
        closed = _close(service, "2026-11-01")
        assert closed["created"] and "payout" not in closed
        with pytest.raises(BlockedError, match="migrate_payout_plans"):
            service.execute("register_payout_request", HUMAN, {
                "policy_number": "AL-000001", "kind": "split", "received_date": "2026-11-20", "channel": "manual",
                "content": {"month": "2026-12-01", "share": "0.3", "premium_receiver": 1}})

        dry = migrate_payout_plans(lakebase_like.engine)  # torrkörning är standard
        assert not dry.applied and not dry.already_applied and dry.problems == []
        assert not set(TABLES) & set(inspect(lakebase_like.engine).get_table_names())

        done = migrate_payout_plans(lakebase_like.engine, dry_run=False)
        assert done.applied and done.row_counts == dry.row_counts and all(done.state.values())
        assert migrate_payout_plans(lakebase_like.engine, dry_run=False).already_applied  # idempotent
        assert migrate_payout_plans(lakebase_like.engine).already_applied
        for table in (*TABLES, "ledger_guarantee_parts", "cases"):
            assert _signature(lakebase_like.engine, lakebase_like.name, table) == \
                _signature(fresh.engine, fresh.name, table), table
        with lakebase_like.session_factory() as s:
            cl.verify_opening(s, cl.opening_batch(s))  # det ingående läget är orört
            mc.verify_month(s, cl.effective_batch(s, date(2026, 11, 30)))
            assert build_ledger_extract(s, date(2026, 11, 30)).approved


@needs_postgres
def test_delvis_inford_migration_stoppar():
    with isolated_schema() as schema:
        Base.metadata.create_all(schema.engine, tables=[t for t in Base.metadata.sorted_tables
                                                        if t.name not in NOT_IN_LAKEBASE])
        _as_after_step3(schema.engine)
        with schema.engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE ledger_guarantee_parts ADD COLUMN plan_id UUID")
        with pytest.raises(RuntimeError, match="delvis"):
            migrate_payout_plans(schema.engine, dry_run=False)
    with isolated_schema() as schema:
        Base.metadata.create_all(schema.engine, tables=[t for t in Base.metadata.sorted_tables
                                                        if not t.name.startswith("ledger_") and t.name not in {*STEP5_TABLES, *STEP6_TABLES, *STEP7_TABLES}])
        with pytest.raises(RuntimeError, match="steg 1–3"):
            migrate_payout_plans(schema.engine)


@needs_postgres
def test_delningen_mot_postgres(monkeypatch):
    today = {"day": date(2026, 12, 1)}
    monkeypatch.setattr(common, "today", lambda: today["day"])
    with isolated_schema() as schema:
        service = _lakebase_like(schema)
        _adopt_avk(service, schema, "AVK-SIM-2026-02", {"2026-11-01": "0.002"}, "2026-11-01", "AVK-SIM-2026-01")
        _close(service, "2026-11-01")
        migrate_payout_plans(schema.engine, dry_run=False)

        made = service.execute("register_payout_request", HUMAN, {
            "policy_number": "AL-000001", "kind": "split", "received_date": "2026-11-20", "channel": "manual",
            "content": {"month": "2026-12-01", "share": "0.3", "premium_receiver": 1}}).output.payload
        assert made["outcome"] == "in_time"
        review = service.execute("preview_payout_plan", HUMAN, {"request_id": made["request_id"]}).output.payload
        assert review["bindable"] and review["valuation_date"] == "2026-11-30"
        service.execute("split_payout_part", HUMAN, {"request_id": made["request_id"],
                                                     "reviewed_checksum": review["review_checksum"],
                                                     "reason": "Prov mot Postgres"})
        today["day"] = date(2027, 1, 4)
        _adopt_avk(service, schema, "AVK-SIM-2026-03", {"2026-11-01": "0.002", "2026-12-01": "0.001"},
                   "2026-12-01", "AVK-SIM-2026-02")
        closed = _close(service, "2026-12-01")
        assert closed["totals"]["splits"] == 1
        with schema.session_factory() as s:
            batch = cl.effective_batch(s, date(2026, 12, 31))
            mc.verify_month(s, batch)
            assert s.scalar(select(func.count()).select_from(PayoutPart)) == 2
            assert s.scalar(select(func.count()).select_from(LedgerGuaranteePart)
                            .where(LedgerGuaranteePart.reason == "split")) == 2 * len(review["guarantees"])
            moved = s.scalar(select(func.sum(cl.LedgerCapitalEntry.amount_sek)).where(
                cl.LedgerCapitalEntry.reason == "split", cl.LedgerCapitalEntry.amount_sek > 0))
            # Testbeståndets försäkring kan ha C = 0 men garanti; då finns inga positiva kapitalposter
            assert (moved or Decimal("0.00")) == Decimal(review["new_capital_sek"])
            split_g = s.scalar(select(func.sum(LedgerGuaranteePart.guarantee_sek_per_month))
                               .where(LedgerGuaranteePart.reason == "split"))
            assert (split_g or 0) == sum(Decimal(g["g"]) for g in review["guarantees"])  # G bevaras i delningen
            # Beloppen med kapital och garanti provas mot Postgres i test_plan_och_delning_med_kapital_mot_postgres
            assert build_ledger_extract(s, date(2026, 12, 31)).approved
        # Samma stängning igen ger ingen ny effekt (fall 16)
        again = service.execute("close_policy_month", HUMAN, {"month": "2026-12-01",
                                                              "reviewed_checksum": closed["review_checksum"]})
        assert not again.output.payload["created"]


@pytest.fixture
def chain_on_postgres(monkeypatch):
    """Paket A:s testbestånd (export_tests.chain) i ett isolerat Postgres-schema i stället för SQLite."""
    if not TEST_URL:
        pytest.skip("SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")
    with isolated_schema() as schema:
        monkeypatch.setattr(export_tests, "create_engine", lambda *args, **kwargs: schema.engine)
        yield schema


def test_plan_och_delning_med_kapital_mot_postgres(chain_on_postgres, chain, clock):
    """Fall 2 och 7 i samma novemberstängning mot Postgres: planbaserade garantidelar med plan_id och delning av C."""
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

    def decide(policy, kind, content, name):
        made = export_tests.run(db, "register_payout_request", {
            "policy_number": policy, "part_number": 1, "kind": kind, "content": content,
            "received_date": "2026-10-20", "channel": "customer_portal"}).payload
        assert made["outcome"] == "in_time", made
        preview = export_tests.run(db, "preview_payout_plan", {"request_id": made["request_id"]}).payload
        assert preview["bindable"]
        export_tests.run(db, name, {"request_id": made["request_id"], "reviewed_checksum": preview["review_checksum"],
                                    "reason": "Prov mot Postgres"})
        return preview

    deferral = decide("AL-000102", "start", {"first_right": "2032-11-01", "form": "lifelong"}, "decide_payout_plan")
    split = decide("AL-000101", "split", {"month": "2026-11-01", "share": "0.3", "premium_receiver": 1},
                   "split_payout_part")
    assert deferral["guarantees"] and split["guarantees"] and Decimal(split["new_capital_sek"]) > 0

    clock.today = date(2026, 12, 1)
    closing = export_tests.run(db, "prepare_month_close", {"month": "2026-11-01"}).payload
    assert closing["passed"], closing["problems"]
    closed = export_tests.run(db, "close_policy_month", {"month": "2026-11-01",
                                                         "reviewed_checksum": closing["review_checksum"]}).payload
    nov_end = date(2026, 11, 30)
    with db.factory() as s:
        mc.verify_month(s, cl.effective_batch(s, nov_end))
        b = pl.find_part(s, "AL-000102", 1).part.id
        planned = [g for g in cl.guarantee_parts(s, nov_end) if g.payout_part_id == b]
        assert {g.plan_kind for g in planned} == {"plan"} and all(g.plan_id is not None for g in planned)
        two = pl.find_part(s, "AL-000101", 2).part.id
        moved = s.scalar(select(func.sum(cl.LedgerCapitalEntry.amount_sek)).where(
            cl.LedgerCapitalEntry.reason == "split", cl.LedgerCapitalEntry.payout_part_id == two))
        assert moved == Decimal(split["new_capital_sek"])
        extract = build_ledger_extract(s, nov_end)
        assert extract.approved, [c for c in extract.checks if not c.passed]
        assert any(n.reason.startswith("Beslutad uttagsplan") for n in extract.not_calculated)  # V7
    again = export_tests.run(db, "close_policy_month", {"month": "2026-11-01",
                                                        "reviewed_checksum": closed["review_checksum"]}).payload
    assert not again["created"]


chain = export_tests.chain
clock = export_tests.clock
