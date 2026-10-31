"""Gemensamma fixturer.

`insurance_db` – en testdatabas i minnet (SQLite) med samma modeller som Lakebase
(modellerna är portabla, se 02_system/databasschema.md) och ett litet bestånd:
en försäkrad med en försäkring som gått från premiebetalande till fribrev.

`insurance_file_db` – samma bestånd i en SQLite-fil där varje session får en egen
anslutning och varje transaktion börjar med BEGIN IMMEDIATE. Används för tester
med samtidiga anrop: databasen serialiserar transaktionerna i stället för att
alla trådar delar en anslutning. Bevisar inte Postgres radlås – se
tests/test_services_postgres.py.

`web` – handläggar-UI:t (src/web/) med en TestClient mot demobeståndet
(src/utils/demo_data.py) i en SQLite-databas i minnet.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from models import (
    Base,
    BaseAmount,
    Employer,
    InsuredPerson,
    Policy,
    PolicyBenefit,
    PolicyState,
    PremiumTransaction,
)
from services.db import session_factory_for
from services.parameters import default_rows as default_parameter_rows

pytest_plugins = ["testing.pytest_plugin"]


def seed_insurance(session_factory) -> SimpleNamespace:
    with session_factory() as s:
        s.add_all(
            [
                BaseAmount(year=2025, income_base_amount_sek=Decimal("80600")),
                BaseAmount(year=2026, income_base_amount_sek=Decimal("83400")),
                *default_parameter_rows(),
            ]
        )
        employer = Employer(org_number="5560000001", name="Testbolaget AB", affiliation_date=date(2010, 1, 1))
        s.add(employer)
        s.flush()
        person = InsuredPerson(
            personal_id_number="199001011234",
            first_name="Test",
            last_name="Testsson",
            employer_id=employer.id,
            employment_start_date=date(2015, 1, 1),
            employment_end_date=date(2025, 12, 31),
            monthly_salary_sek=Decimal("80000"),
            employment_rate=Decimal("100"),
            itp1_start_date=date(2015, 1, 1),
            status="terminated",
        )
        s.add(person)
        s.flush()
        policy = Policy(
            policy_number="AL-000001",
            insured_person_id=person.id,
            signed_date=date(2015, 1, 1),
            start_date=date(2015, 1, 1),
        )
        s.add(policy)
        s.flush()
        benefit = PolicyBenefit(policy_id=policy.id, benefit_type="retirement_dc", start_date=date(2015, 1, 1))
        s.add(benefit)
        s.flush()
        s.add_all(
            [
                PolicyState(policy_id=policy.id, state="premium_paying",
                            valid_from=date(2015, 1, 1), valid_to=date(2025, 12, 31)),
                PolicyState(policy_id=policy.id, state="paid_up", valid_from=date(2026, 1, 1)),
            ]
        )
        transactions = [
            (date(2025, 11, 1), "premium", "10000.00", "paid"),
            (date(2025, 12, 1), "premium", "10000.00", "paid"),
            (date(2025, 12, 1), "adjustment", "-500.00", "paid"),
            (date(2025, 12, 1), "fee", "-20.00", "paid"),
            (date(2026, 1, 1), "premium", "10708.13", "invoiced"),
        ]
        for period, tx_type, amount, status in transactions:
            s.add(
                PremiumTransaction(
                    benefit_id=benefit.id,
                    period_month=period,
                    transaction_type=tx_type,
                    pensionable_salary_sek=Decimal("80000") if tx_type == "premium" else None,
                    amount_sek=Decimal(amount),
                    status=status,
                    paid_date=period if status == "paid" else None,
                )
            )
        return SimpleNamespace(person=person.id, policy=policy.id, benefit=benefit.id, employer=employer.id)


@pytest.fixture
def insurance_db():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    session_factory = session_factory_for(engine)
    ids = seed_insurance(session_factory)
    yield SimpleNamespace(engine=engine, session_factory=session_factory, ids=ids)
    engine.dispose()


#: Dagen handläggar-UI:ts tester körs (före PR-ITP1 v1.0:s giltighetsdag 2026-11-01)
WEB_TODAY = date(2026, 10, 12)


@pytest.fixture
def web(monkeypatch):
    """Handläggar-UI:t mot demobeståndet i en SQLite-databas i minnet (utils/demo_data.py).

    Två agentförslag ligger i godkännandekön. `client` är en FastAPI TestClient;
    `csrf` är formulärtoken; `session_factory` används bara av testerna för att
    kontrollera databasen – UI:t själv går genom tjänstelagret.
    """
    from fastapi.testclient import TestClient

    from services import ProductRuleCatalog, ServiceLayer
    from services.operations import common
    from utils.demo_data import create_demo_database
    from web import create_app
    from web.config import WebSettings

    monkeypatch.setattr(common, "today", lambda: WEB_TODAY)
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, today=WEB_TODAY)
    session_factory = session_factory_for(engine)
    service = ServiceLayer(session_factory=session_factory, rules=ProductRuleCatalog(today=WEB_TODAY))
    app = create_app(service=service, settings=WebSettings(allowed_hosts=("testserver",)))
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client, service=service, session_factory=session_factory, engine=engine,
            csrf=app.state.csrf_token, app=app,
        )
    engine.dispose()


@pytest.fixture
def insurance_file_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'insurance.db'}", connect_args={"check_same_thread": False, "timeout": 15}
    )

    # pysqlite: låt SQLAlchemy styra transaktionerna och ta skrivlåset direkt vid start,
    # så att samtidiga transaktioner köas i stället för att fastna i ett låsläge.
    @event.listens_for(engine, "connect")
    def _autocommit_driver(dbapi_connection, _record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _begin_immediate(connection):
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    Base.metadata.create_all(engine)
    session_factory = session_factory_for(engine)
    ids = seed_insurance(session_factory)
    yield SimpleNamespace(engine=engine, session_factory=session_factory, ids=ids)
    engine.dispose()
