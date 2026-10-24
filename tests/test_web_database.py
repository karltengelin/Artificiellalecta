"""Databasvalet för handläggar-UI:t och demobeståndet (src/web/database.py, src/utils/demo_data.py)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from models import ApprovalRequestRecord, InsuredPerson, PremiumTransaction
from services import ProductRuleCatalog
from services.db import session_factory_for
from services.operations import common
from utils.demo_data import PERSONS, create_demo_database
from web.config import WebConfigError
from web.database import demo_engine, svc_test_engine

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 10, 12)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


def memory_engine():
    return create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})


def counts(engine):
    with session_factory_for(engine)() as s:
        return (
            s.scalar(select(func.count()).select_from(InsuredPerson)),
            s.scalar(select(func.count()).select_from(PremiumTransaction)),
            s.scalar(select(func.count()).select_from(ApprovalRequestRecord)),
        )


def test_demobestandet_har_personer_premier_och_tva_forslag():
    engine = memory_engine()
    create_demo_database(engine, today=TODAY)
    persons, premiums, proposals = counts(engine)
    assert persons == len(PERSONS) == 4
    assert premiums == 21 + 21 + 12 + 4
    assert proposals == 2


def test_demobestandet_skapas_bara_i_en_tom_databas():
    engine = memory_engine()
    create_demo_database(engine, today=TODAY, with_proposals=False)
    with pytest.raises(RuntimeError, match="redan tabeller"):
        create_demo_database(engine, today=TODAY)


def test_demofilen_skapas_en_gang_och_ateranvands(tmp_path):
    path = tmp_path / "demo.db"
    first = demo_engine(path)
    assert path.exists()
    with session_factory_for(first)() as s:
        s.add(ApprovalRequestRecord(id="x" * 32, operation="get_insured_overview", input={},
                                    proposed_by="test", status="rejected"))
    first.dispose()
    second = demo_engine(path)  # befintlig fil: inget nytt bestånd, inga tabeller skapas om
    assert counts(second)[0] == 4
    with session_factory_for(second)() as s:
        assert s.get(ApprovalRequestRecord, "x" * 32) is not None
    second.dispose()


def test_ny_tabell_laggs_till_i_befintlig_demofil(tmp_path):
    """En demofil från före Fas 5 får tabellen cases; beståndet och kön är kvar."""
    from sqlalchemy import inspect

    path = tmp_path / "demo.db"
    first = demo_engine(path)
    with first.begin() as conn:
        conn.exec_driver_sql("DROP TABLE cases")
    first.dispose()
    second = demo_engine(path)
    assert "cases" in inspect(second).get_table_names()
    assert counts(second)[0] == 4
    second.dispose()


def test_svc_test_kraver_isolerad_databas(monkeypatch):
    monkeypatch.delenv("SERVICES_TEST_POSTGRES_URL", raising=False)
    with pytest.raises(WebConfigError, match="saknas"):
        svc_test_engine()
    monkeypatch.setenv("SERVICES_TEST_POSTGRES_URL", "postgresql://samma")
    monkeypatch.setenv("DATABASE_URL", "postgresql://samma")
    with pytest.raises(WebConfigError, match="beståndet"):
        svc_test_engine()


def test_regelns_rubrik_lases_ur_regelfilen():
    rules = ProductRuleCatalog(today=TODAY)
    assert rules.title("PR-ITP1-013") == "premieperioder, anställning och fribrev"
    assert rules.title("PR-ITP1-999") is None
