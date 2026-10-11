"""Transaktionsgränsen mot en riktig Postgres: radlås och omprövning i READ COMMITTED.

SQLite-testerna (test_services_transactions.py) visar logiken när databasen
serialiserar transaktionerna. Lakebase är Postgres, där två samtidiga
godkännanden skyddas av att den villkorliga UPDATE:n (`… WHERE status =
'pending'`) tar radlås: den andra väntar, och när den första har gjort commit
prövas villkoret på nytt och ingen rad matchar.

Körs bara när SERVICES_TEST_POSTGRES_URL pekar på en ISOLERAD testdatabas –
aldrig mot Lakebase-beståndet (DATABASE_URL vägras). Testet skapar ett eget
schema, bygger tabellerna och samma lilla bestånd som insurance_db där, och
tar bort schemat efteråt.

    SERVICES_TEST_POSTGRES_URL=postgresql://…/testdb pytest tests/test_services_postgres.py
"""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

from models import Base
from services.db import session_factory_for
from tests.conftest import seed_insurance
from services import ProductRuleCatalog
from tests.test_services_transactions import (  # noqa: F401  (_reset_hooks är en autouse-fixtur)
    _reset_hooks,
    assert_concurrent_approvals_execute_once,
    assert_failed_status_save_rolls_back_everything,
    assert_second_approval_takes_over_after_failure,
)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

TEST_URL = os.environ.get("SERVICES_TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres att testa mot"
)


@pytest.fixture
def rules(tmp_path):
    (tmp_path / "PR-T-001-x.md").write_text("> **Granskningsstatus:** Godkänd\n", encoding="utf-8")
    return ProductRuleCatalog(tmp_path)


@pytest.fixture
def postgres_db():
    if TEST_URL == os.environ.get("DATABASE_URL"):
        pytest.fail("SERVICES_TEST_POSTGRES_URL får inte vara DATABASE_URL – testerna körs aldrig mot beståndet")
    schema = f"svc_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(TEST_URL)
    with admin.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(TEST_URL, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        session_factory = session_factory_for(engine)
        ids = seed_insurance(session_factory)
        yield SimpleNamespace(engine=engine, session_factory=session_factory, ids=ids)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()


def test_fel_nar_status_sparas_rullar_tillbaka_allt(postgres_db, rules):
    assert_failed_status_save_rolls_back_everything(postgres_db, rules)


def test_samtidiga_godkannanden_verkstaller_en_gang(postgres_db, rules):
    assert_concurrent_approvals_execute_once(postgres_db, rules)


def test_andra_godkannandet_tar_over_om_det_forsta_fallerar(postgres_db, rules):
    assert_second_approval_takes_over_after_failure(postgres_db, rules)
