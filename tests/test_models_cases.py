"""Tabellen cases (Fas 5 F5-1, databasschema.md §9g) – databasens egna villkor, mot SQLite.

Tjänstelagrets ärendeoperationer (F5-2) validerar mer, men de här villkoren gäller även
om någon skriver förbi tjänstelagret.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models import Case, InsuredPerson


def person_id(db):
    with db.session_factory() as s:
        return s.scalar(select(InsuredPerson.id))


def add(db, **overrides):
    values = {
        "case_number": "CASE-000001",
        "case_type": "salary_report",
        "status": "open",
        "insured_person_id": person_id(db),
        "period_month": date(2026, 10, 1),
        "channel": "manual",
        "received_date": date(2026, 10, 24),
        "details": {"pensionable_salary_sek": "60000.00", "source": "employer", "kind": "new"},
        "created_by": "karl",
        **overrides,
    }
    with db.session_factory() as s:
        s.add(Case(**values))
    with db.session_factory() as s:
        return s.scalar(select(Case).where(Case.case_number == values["case_number"]))


CLOSED = {"status": "closed", "outcome": "approved", "closed_by": "karl", "closed_at": datetime(2026, 10, 24, tzinfo=UTC)}


def test_oppet_arende_med_uppgifter(insurance_db):
    case = add(insurance_db)
    assert (case.status, case.outcome, case.details["kind"]) == ("open", None, "new")


def test_stangt_arende_med_utfall(insurance_db):
    assert add(insurance_db, **CLOSED).outcome == "approved"


@pytest.mark.parametrize(
    "overrides",
    [
        {"case_number": "ÄR-1"},
        {"case_number": "CASE-1"},
        {"case_type": "complaint"},  # inte i v1 (B-033 val C)
        {"status": "done"},
        {"channel": "email"},
        {"outcome": "approved"},  # utfall på öppet ärende
        {"status": "closed"},  # stängt utan utfall
        {**CLOSED, "closed_by": None},
        {**CLOSED, "outcome": "rejected"},  # avslag kräver anteckning
        {**CLOSED, "outcome": "manual_review"},
        {"insured_person_id": None},  # ingen försäkrad och ingen arbetsgivare
        {"period_month": date(2026, 10, 15)},
        {"details": None},
    ],
)
def test_databasen_stoppar_ogiltiga_arenden(insurance_db, overrides):
    with pytest.raises(IntegrityError):
        add(insurance_db, **overrides)


def test_avslag_med_anteckning_godtas(insurance_db):
    case = add(insurance_db, **{**CLOSED, "outcome": "rejected", "closing_note": "Fel månad enligt arbetsgivaren"})
    assert case.closing_note.startswith("Fel månad")


def test_arendenumret_ar_unikt(insurance_db):
    add(insurance_db)
    with pytest.raises(IntegrityError):
        add(insurance_db)
