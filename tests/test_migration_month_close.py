"""Migrationen som vidgar kapitaljournalen för månadsstängning (paket B steg 3, B-047, P1-PENSION-001 §7 och §12).

Mot en isolerad Postgres (svc_test, eget schema per test) som Lakebase ser ut efter steg 2: journalens fyra
tabeller med `ledger_batches` utan `supersedes_id` och med slaget `opening_s04` som enda värde, och det ingående
läget bokat. Migrationen ska ge exakt samma schema som create_all utan att röra några rader eller ge
agentrollerna rättigheter; torrkörningen ska inte kunna skriva. Därefter stängs november mot Postgres.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.dialects import postgresql

from models import Base, LedgerBatch, LedgerCapitalEntry, ValuationBasis
from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer
from services import capital_ledger as cl
from services import month_close as mc
from services import valuation_bases as vb
from services.errors import BlockedError
from services.ledger_extract import build_ledger_extract
from services.operations import common
from tests.conftest import seed_insurance
from tests.test_migration_payout_parts import _signature
from tests.test_services_postgres import TEST_URL, isolated_schema
from utils.migration_month_close import (
    INDEXES,
    KIND_CHECK_BEFORE,
    compile_ddl,
    migrate_month_close,
)

NOT_IN_LAKEBASE = {"portfolios", "portfolio_holdings", "trades"}
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Månadsstängning (prov)")
needs_postgres = pytest.mark.skipif(not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")


def _as_after_step2(engine) -> None:
    """Tar bort steg 3:s delar så att ledger_batches ser ut som i Lakebase efter steg 2."""
    with engine.begin() as conn:
        for name in INDEXES:
            conn.exec_driver_sql(f"DROP INDEX {name}")
        conn.exec_driver_sql("ALTER TABLE ledger_batches DROP CONSTRAINT ck_ledger_batches_supersedes")
        conn.exec_driver_sql("ALTER TABLE ledger_batches DROP COLUMN supersedes_id")
        conn.exec_driver_sql("ALTER TABLE ledger_batches DROP CONSTRAINT ck_ledger_batches_kind")
        conn.exec_driver_sql(f"ALTER TABLE ledger_batches ADD CONSTRAINT ck_ledger_batches_kind CHECK ({KIND_CHECK_BEFORE})")


def _lakebase_like(schema) -> ServiceLayer:
    Base.metadata.create_all(schema.engine, tables=[t for t in Base.metadata.sorted_tables
                                                    if t.name not in NOT_IN_LAKEBASE])
    seed_insurance(schema.session_factory)
    with schema.session_factory() as s:
        vb.add_missing_defaults(s)
        s.commit()
    service = ServiceLayer(session_factory=schema.session_factory, rules=ProductRuleCatalog())
    # Som i Lakebase: det ingående läget bokades i steg 2, och därefter tas steg 3:s delar bort. Raden har
    # supersedes_id NULL och uppfyller steg 2:s villkor.
    review = service.execute("preview_ledger_opening", HUMAN, {}).output.payload
    assert review["passed"], review["problems"]
    service.execute("open_capital_ledger", HUMAN, {"reviewed_checksum": review["review_checksum"]})
    _as_after_step2(schema.engine)
    return service


def test_migrationen_kraver_postgres():
    with pytest.raises(RuntimeError, match="Postgres"):
        migrate_month_close(create_engine("sqlite://"))


def test_ddl_vidgar_bara_ledger_batches():
    statements = compile_ddl(postgresql.dialect())
    assert all("ledger_batches" in s for s in statements)
    assert not any("GRANT" in s or "CREATE TABLE" in s or "DROP TABLE" in s for s in statements)
    assert any("month_correction" in s for s in statements)
    assert sum(s.startswith("CREATE UNIQUE INDEX") for s in statements) == 2


@needs_postgres
def test_migrationen_vidgar_verifikationerna_och_blir_identisk_med_create_all(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: date(2026, 12, 1))
    with isolated_schema() as lakebase_like, isolated_schema() as fresh:
        Base.metadata.create_all(fresh.engine)
        _lakebase_like(lakebase_like)
        with lakebase_like.session_factory() as s:
            with pytest.raises(mc.CloseError, match="migrate_month_close"):
                mc.plan_month(s, date(2026, 11, 1), date(2026, 12, 1))
            assert build_ledger_extract(s, date(2026, 10, 31)).approved  # steg 2:s läsningar fungerar

        dry = migrate_month_close(lakebase_like.engine)  # torrkörning är standard
        assert not dry.applied and not dry.already_applied and dry.problems == []
        assert "supersedes_id" not in {c["name"] for c in inspect(lakebase_like.engine).get_columns("ledger_batches")}

        done = migrate_month_close(lakebase_like.engine, dry_run=False)
        assert done.applied and done.row_counts == dry.row_counts and all(done.state.values())
        assert migrate_month_close(lakebase_like.engine, dry_run=False).already_applied  # idempotent
        assert migrate_month_close(lakebase_like.engine).already_applied
        assert _signature(lakebase_like.engine, lakebase_like.name, "ledger_batches") == \
            _signature(fresh.engine, fresh.name, "ledger_batches")
        with lakebase_like.session_factory() as s:
            cl.verify_opening(s, cl.opening_batch(s))  # det ingående läget är orört


@needs_postgres
def test_delvis_inford_migration_stoppar():
    with isolated_schema() as schema:
        Base.metadata.create_all(schema.engine, tables=[t for t in Base.metadata.sorted_tables
                                                        if t.name not in NOT_IN_LAKEBASE])
        _as_after_step2(schema.engine)
        with schema.engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE ledger_batches ADD COLUMN supersedes_id UUID")
        with pytest.raises(RuntimeError, match="delvis"):
            migrate_month_close(schema.engine, dry_run=False)
    with isolated_schema() as schema:
        Base.metadata.create_all(schema.engine, tables=[t for t in Base.metadata.sorted_tables
                                                        if not t.name.startswith("ledger_")])
        with pytest.raises(RuntimeError, match="migrate_capital_ledger"):
            migrate_month_close(schema.engine)


@needs_postgres
def test_novemberstangningen_mot_postgres(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: date(2026, 12, 1))
    with isolated_schema() as schema:
        service = _lakebase_like(schema)
        migrate_month_close(schema.engine, dry_run=False)
        with schema.session_factory() as s:
            base = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "AVK-SIM-2026-01")).assumptions
        months = [*vb.normalize("return_series", base)["months"], {"month": "2026-11-01", "rate": "0.002"}]
        with pytest.raises(BlockedError):  # fall 17 mot Postgres
            service.execute("prepare_month_close", HUMAN, {"month": "2026-11-01"})
        service.execute("propose_valuation_basis", HUMAN, {
            "code": "AVK-SIM-2026-02", "title": "Syntetisk avkastning för november",
            "assumptions": vb.normalize("return_series", {**base, "months": months}), "source_refs": "prov",
            "supersedes_code": "AVK-SIM-2026-01"})
        service.execute("adopt_valuation_basis", HUMAN, {"code": "AVK-SIM-2026-02", "valid_from": "2026-11-01",
                                                         "decision_ref": "prov S5"})
        review = service.execute("prepare_month_close", HUMAN, {"month": "2026-11-01"}).output.payload
        assert review["passed"], review["problems"]
        data = {"month": "2026-11-01", "reviewed_checksum": review["review_checksum"]}
        assert service.execute("close_policy_month", HUMAN, data).output.payload["created"]
        assert not service.execute("close_policy_month", HUMAN, data).output.payload["created"]  # fall 16
        with schema.session_factory() as s:
            batch = cl.effective_batch(s, date(2026, 11, 30))
            mc.verify_month(s, batch)
            assert s.scalar(select(func.count()).select_from(LedgerBatch)) == 2
            assert s.scalar(select(func.count()).select_from(LedgerCapitalEntry)
                            .where(LedgerCapitalEntry.batch_id == batch.id)) == batch.content["totals"]["entries"]
            assert build_ledger_extract(s, date(2026, 11, 30)).approved
