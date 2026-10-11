"""Gemensamma fixturer.

`insurance_db` – en testdatabas i minnet (SQLite) med samma modeller som Lakebase
(modellerna är portabla, se 02_system/databasschema.md) och ett litet bestånd:
en försäkrad med en försäkring som gått från premiebetalande till fribrev.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
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


@pytest.fixture
def insurance_db():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    session_factory = session_factory_for(engine)

    with session_factory() as s:
        s.add_all(
            [
                BaseAmount(year=2025, income_base_amount_sek=Decimal("80600")),
                BaseAmount(year=2026, income_base_amount_sek=Decimal("83400")),
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
        ids = SimpleNamespace(person=person.id, policy=policy.id, benefit=benefit.id)

    yield SimpleNamespace(engine=engine, session_factory=session_factory, ids=ids)
    engine.dispose()
