"""Tjänstelagret och T3-migrationen mot en riktig Postgres: radlås och omprövning i READ COMMITTED.

SQLite-testerna visar logiken när databasen serialiserar transaktionerna.
Lakebase är Postgres, där skyddet bygger på radlås:
- två samtidiga godkännanden: den villkorliga UPDATE:n (`… WHERE status =
  'pending'`) låser raden; den andra väntar, prövar villkoret på nytt efter
  commit och får ingen rad
- skrivoperationerna låser personen, försäkringen eller premieraden
  (SELECT … FOR UPDATE) så att samtidiga anrop prövas i tur och ordning

Här prövas också migrationen (scripts/migrations/migrate_t3_schema.py) från det gamla
schemat, och att resultatet blir identiskt med create_all.

Körs bara när SERVICES_TEST_POSTGRES_URL pekar på en ISOLERAD testdatabas –
aldrig mot Lakebase-beståndet (DATABASE_URL vägras). Varje test skapar egna
scheman och tar bort dem efteråt.

    SERVICES_TEST_POSTGRES_URL=postgresql://…/testdb pytest tests/test_services_postgres.py
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select

from models import Base, Policy, PremiumTransaction, SalaryReport
from services import ConflictError, OperationResult, ProductRuleCatalog
from services.db import session_factory_for
from tests.conftest import seed_insurance
from tests.test_services_transactions import (  # noqa: F401  (_reset_hooks är en autouse-fixtur)
    _reset_hooks,
    assert_concurrent_approvals_execute_once,
    assert_failed_status_save_rolls_back_everything,
    assert_second_approval_takes_over_after_failure,
)
from tests.test_services_write_ops import (  # noqa: F401  (fixed_today är en autouse-fixtur)
    ACTIVE,
    HUMAN,
    correction,
    fixed_today,
    make_service,
    report,
    seed_active,
)
from utils.backup import backup_database
from utils.migration_t3 import migrate_t3, schema_state

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

TEST_URL = os.environ.get("SERVICES_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres att testa mot"
)


@contextmanager
def isolated_schema() -> Iterator[SimpleNamespace]:
    """Ett eget schema i testdatabasen; motorn har det som search_path."""
    if TEST_URL == os.environ.get("DATABASE_URL"):
        pytest.fail("SERVICES_TEST_POSTGRES_URL får inte vara DATABASE_URL – testerna körs aldrig mot beståndet")
    name = f"svc_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(TEST_URL)
    with admin.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{name}"')
    engine = create_engine(TEST_URL, connect_args={"options": f"-csearch_path={name}"})
    try:
        yield SimpleNamespace(name=name, engine=engine, session_factory=session_factory_for(engine))
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA "{name}" CASCADE')
        admin.dispose()


@pytest.fixture
def postgres_db():
    with isolated_schema() as schema:
        Base.metadata.create_all(schema.engine)
        schema.ids = seed_insurance(schema.session_factory)
        yield schema


@pytest.fixture
def rules(tmp_path):
    (tmp_path / "PR-T-001-x.md").write_text("> **Granskningsstatus:** Godkänd\n", encoding="utf-8")
    return ProductRuleCatalog(tmp_path)


def run_concurrently(call: Callable[[], OperationResult], n: int = 2) -> list:
    barrier = threading.Barrier(n)
    results: list = []

    def worker():
        barrier.wait()
        try:
            results.append(call())
        except Exception as exc:  # noqa: BLE001 – utfallet kontrolleras av testet
            results.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def outcome_names(results: list) -> list[str]:
    return sorted(type(r).__name__ for r in results)


# --- godkännandets transaktionsgräns -------------------------------------------------------------


def test_fel_nar_status_sparas_rullar_tillbaka_allt(postgres_db, rules):
    assert_failed_status_save_rolls_back_everything(postgres_db, rules)


def test_samtidiga_godkannanden_verkstaller_en_gang(postgres_db, rules):
    assert_concurrent_approvals_execute_once(postgres_db, rules)


def test_andra_godkannandet_tar_over_om_det_forsta_fallerar(postgres_db, rules):
    assert_second_approval_takes_over_after_failure(postgres_db, rules)


# --- skrivoperationerna vid samtidiga anrop ----------------------------------------------------


def test_samtidiga_identiska_lonerapporter_ger_en_rad(postgres_db):
    db = seed_active(postgres_db)
    service = make_service(db)
    results = run_concurrently(lambda: service.execute("register_salary_report", HUMAN, report(source_reference=None)))
    assert outcome_names(results) == ["ConflictError", "OperationResult"]
    with db.session_factory() as s:
        assert len(s.scalars(select(SalaryReport)).all()) == 1


def test_samtidiga_premierattelser_ger_en_motpost(postgres_db):
    db = seed_active(postgres_db)
    service = make_service(db)
    june = db.tx[date(2026, 6, 1)]
    results = run_concurrently(lambda: service.execute("correct_premium_transaction", HUMAN, correction(june, "50000")))
    assert outcome_names(results) == ["ConflictError", "OperationResult"]
    with db.session_factory() as s:
        assert len(s.scalars(select(PremiumTransaction).where(PremiumTransaction.corrects_transaction_id == june)).all()) == 1


def test_samtidiga_fribrev_ger_ett_lagesbyte(postgres_db):
    db = seed_active(postgres_db)
    service = make_service(db)
    payload = {"policy_number": "AL-000002", "employment_end_date": "2026-09-30"}
    results = run_concurrently(lambda: service.execute("set_policy_paid_up", HUMAN, payload))
    assert outcome_names(results) == ["ConflictError", "OperationResult"]
    assert any(isinstance(r, ConflictError) and "redan fribrev" in str(r) for r in results)


# --- migrationen --------------------------------------------------------------------------------


def _signature(engine, schema: str) -> dict[str, set]:
    """Kolumner, constraints och index för de berörda tabellerna, utan schemanamn."""
    tables = ("premium_transactions", "salary_reports")
    with engine.connect() as conn:
        columns = conn.exec_driver_sql(
            "SELECT table_name, column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns WHERE table_schema = %(s)s AND table_name IN %(t)s",
            {"s": schema, "t": tables},
        ).all()
        constraints = conn.exec_driver_sql(
            "SELECT rel.relname, con.conname, pg_get_constraintdef(con.oid) FROM pg_constraint con "
            "JOIN pg_class rel ON rel.oid = con.conrelid JOIN pg_namespace n ON n.oid = rel.relnamespace "
            "WHERE n.nspname = %(s)s AND rel.relname IN %(t)s",
            {"s": schema, "t": tables},
        ).all()
        indexes = conn.exec_driver_sql(
            "SELECT tablename, indexname, replace(indexdef, %(p)s, '') FROM pg_indexes "
            "WHERE schemaname = %(s)s AND tablename IN %(t)s",
            {"s": schema, "t": tables, "p": f"{schema}."},
        ).all()
    return {"columns": set(columns), "constraints": set(constraints), "indexes": set(indexes)}


def test_migrering_fran_gammalt_schema_blir_identisk_med_create_all(tmp_path):
    with isolated_schema() as old, isolated_schema() as fresh:
        Base.metadata.create_all(fresh.engine)

        # Det gamla schemat: som Lakebase före T3, med data
        Base.metadata.create_all(old.engine)
        old.ids = seed_insurance(old.session_factory)
        with old.engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE salary_reports")
            conn.exec_driver_sql("ALTER TABLE premium_transactions DROP COLUMN corrects_transaction_id")
        with old.engine.connect() as conn:
            assert schema_state(conn) == (False, False)
            constraints = conn.exec_driver_sql(
                "SELECT con.conname FROM pg_constraint con JOIN pg_namespace n ON n.oid = con.connamespace "
                "WHERE n.nspname = %(s)s AND con.conname = 'ck_premium_transactions_correction_type'",
                {"s": old.name},
            ).all()
            assert constraints == []

        # Backup med den nya koden fungerar mot det gamla schemat (som inför migrationen av Lakebase)
        manifest = json.loads((backup_database(old.engine, tmp_path) / "manifest.json").read_text(encoding="utf-8"))
        assert "salary_reports" not in manifest["tables"] and manifest["row_counts"]["premium_transactions"] == 5

        dry = migrate_t3(old.engine, dry_run=True)
        assert (dry.applied, dry.row_counts["premium_transactions"]) == (False, 5)
        with old.engine.connect() as conn:
            assert schema_state(conn) == (False, False)

        done = migrate_t3(old.engine)
        assert done.applied and done.row_counts == dry.row_counts  # inga rader ändrade
        assert migrate_t3(old.engine).already_applied  # idempotent
        assert _signature(old.engine, old.name) == _signature(fresh.engine, fresh.name)

        # Operationerna fungerar på det migrerade schemat
        db = seed_active(old)
        out = make_service(db).execute(
            "correct_premium_transaction", HUMAN, correction(db.tx[date(2026, 6, 1)], "50000")
        ).output
        assert out.difference_sek == 225
        assert make_service(db).execute("register_salary_report", HUMAN, report()).output.version == 1
        assert make_service(db).execute("get_salary_reports", HUMAN, {"personal_id_number": ACTIVE}).output.reports


# --- handläggar-UI:ts läsoperationer: JSON-urval i Postgres (->>) ----------------------------------


def test_handelser_per_forsakrad_och_godkannandekon_i_postgres(postgres_db):
    """Händelseloggen per försäkrad väljer på indata/resultat i JSONB – annan SQL än i SQLite."""
    db = seed_active(postgres_db)
    service = make_service(db)
    service.execute("get_insured_overview", HUMAN, {"personal_id_number": ACTIVE})
    service.execute("get_premium_history", HUMAN, {"policy_number": "AL-000001"})  # den andra personens försäkring
    out = service.execute("correct_premium_transaction", HUMAN, correction(db.tx[date(2026, 6, 1)], "50000")).output

    active = service.execute(
        "get_operation_events", HUMAN, {"personal_id_number": ACTIVE, "include_reads": True}
    ).output
    assert [e.operation for e in active.events] == ["correct_premium_transaction", "get_insured_overview"]
    assert active.events[0].output["adjustment_transaction_id"] == out.adjustment_transaction_id
    changes_only = service.execute("get_operation_events", HUMAN, {"personal_id_number": ACTIVE}).output
    assert [e.operation for e in changes_only.events] == ["correct_premium_transaction"]

    queue = service.execute("list_approval_requests", HUMAN, {"status": None}).output
    counts = service.execute("count_approval_requests", HUMAN, {}).output
    assert (queue.count, counts.pending) == (0, 0)


def test_samtidiga_anslutningar_far_aldrig_samma_forsakringsnummer(postgres_db):
    """Nästa AL-nummer räknas fram ur det högsta – en krock stoppas av unikhetsregeln (ConflictError)."""
    from tests.test_services_enrollment import enrollment

    service = make_service(postgres_db)
    people = iter(["199204171236", "198811112229"])
    lock = threading.Lock()

    def enroll():
        with lock:
            pnr = next(people)
        return service.execute("enroll_insured_person", HUMAN, enrollment(personal_id_number=pnr))

    results = run_concurrently(enroll)
    done = [r.output.policy_number for r in results if isinstance(r, OperationResult)]
    assert len(done) >= 1 and len(set(done)) == len(done)
    assert all(isinstance(r, (OperationResult, ConflictError)) for r in results), results
    with postgres_db.session_factory() as s:
        numbers = [p.policy_number for p in s.scalars(select(Policy))]
    assert len(numbers) == len(set(numbers)) == 1 + len(done)
