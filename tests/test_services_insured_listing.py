"""Beståndsurval räknar personer, använder nuvarande läge och håller PII-gränsen."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import event

from models import Employer, InsuredPerson, Policy, PolicyState
from services import (
    AccessDeniedError,
    Actor,
    InvalidInputError,
    MemoryEventLog,
    OperationContext,
    ServiceLayer,
)

HUMAN = OperationContext(actor=Actor.human("karl"))


@pytest.fixture
def bestand(insurance_db):
    with insurance_db.session_factory() as session:
        employer = Employer(org_number="5560000002", name="Andra bolaget", affiliation_date=date(2020, 1, 1))
        session.add(employer)
        session.flush()
        for pnr, first, last, employer_id in [
            ("199002021234", "Åsa", "Öst Äng", insurance_db.ids.employer),
            ("199003031234", "Åsa", "Öst Äng", employer.id),
            ("199004041234", "Utan", "Försäkring", employer.id),
        ]:
            session.add(InsuredPerson(
                personal_id_number=pnr, first_name=first, last_name=last, employer_id=employer_id,
                employment_start_date=date(2020, 1, 1), monthly_salary_sek=Decimal(30000),
                employment_rate=Decimal(100), itp1_start_date=date(2020, 1, 1), status="active",
            ))
        session.flush()
        for number, pnr, state in [
            ("AL-000002", "199002021234", "premium_paying"),
            ("AL-000003", "199002021234", "paid_up"),
            ("AL-000004", "199003031234", "in_payout"),
        ]:
            person = session.query(InsuredPerson).filter_by(personal_id_number=pnr).one()
            policy = Policy(policy_number=number, insured_person_id=person.id,
                            signed_date=date(2020, 1, 1), start_date=date(2020, 1, 1))
            session.add(policy)
            session.flush()
            session.add(PolicyState(policy_id=policy.id, state=state, valid_from=date(2020, 1, 1)))
    return ServiceLayer(session_factory=insurance_db.session_factory, events=MemoryEventLog())


def listing(service, **query):
    return service.execute("list_insured_persons", HUMAN, query).output


@pytest.mark.parametrize(("query", "pnrs"), [
    ("  öST   ÅSA ÄNG ", {"199002021234", "199003031234"}),
    ("test TESTSSON", {"199001011234"}),
    ("19900202-1234", {"199002021234"}),
    ("199002", {"199002021234"}),
    ("al000003", {"199002021234"}),
    ("al-000003", {"199002021234"}),
    ("%", set()), ("_", set()), ("--", set()), ("' OR 1=1 --", set()),
])
def test_soker_namndelar_och_nummer_som_bokstavlig_text(bestand, query, pnrs):
    result = listing(bestand, q=query)
    assert {p.personal_id_number for p in result.persons} == pnrs
    assert result.total == len(pnrs)
    assert result.total_in_database == 4


def test_filter_matchar_nuvarande_lage_inte_historiskt(bestand):
    result = listing(bestand, policy_state="premium_paying")
    assert [p.personal_id_number for p in result.persons] == ["199002021234"]
    assert {p.policy_number for p in result.persons[0].policies} == {"AL-000002", "AL-000003"}
    assert listing(bestand, policy_state="paid_up").total == 2
    assert listing(bestand, q="Test", policy_state="premium_paying").total == 0
    assert listing(bestand, policy_state="in_payout", employer_org_number="5560000002").total == 1
    assert listing(bestand, policy_state="in_payout", employer_org_number="5560000001").total == 0


def test_flera_forsakringar_blir_en_person_och_utan_forsakring_ar_med(bestand):
    result = listing(bestand)
    assert result.total == len(result.persons) == 4
    without = listing(bestand, policy_state="no_policy")
    assert [(p.personal_id_number, p.policies) for p in without.persons] == [("199004041234", [])]


def test_sidindelning_ar_stabil_aven_med_lika_namn(bestand):
    first = listing(bestand, page_size=1, q="Åsa", page=1)
    second = listing(bestand, page_size=1, q="Åsa", page=2)
    assert (first.total, first.page_count) == (2, 2)
    assert first.persons[0].personal_id_number == "199002021234"
    assert second.persons[0].personal_id_number == "199003031234"
    assert listing(bestand, page_size=1, q="Åsa", page=99) == second
    empty = listing(bestand, q="finns inte", page=99)
    assert (empty.total, empty.persons, empty.page, empty.page_count) == (0, [], 1, 1)


@pytest.mark.parametrize("query", [
    {"page": 0}, {"page": 100001}, {"page_size": 0}, {"page_size": 101},
    {"q": "a" * 201}, {"policy_state": "historical"}, {"employer_org_number": "x"},
])
def test_ogiltiga_urval_stoppas(bestand, query):
    with pytest.raises(InvalidInputError):
        listing(bestand, **query)


def test_bred_personlista_ar_bara_for_mansklig_handlaggare(bestand):
    agent = OperationContext(actor=Actor.agent("case_handler", team="forsakring"), run_id="run-list")
    with pytest.raises(AccessDeniedError):
        bestand.execute("list_insured_persons", agent, {})


def test_loggar_sokningen_men_inte_personlistans_innehall(bestand):
    listing(bestand, q="Åsa", policy_state="paid_up", page_size=25)
    (entry,) = bestand.events.events
    assert (entry.operation, entry.actor_type, entry.actor_id, entry.pii) == ("list_insured_persons", "human", "karl", True)
    assert entry.input["q"] == "Åsa"
    assert entry.input["policy_state"] == "paid_up"
    assert entry.output is None


def test_antal_databasfragor_vaxer_inte_med_raderna(bestand, insurance_db):
    queries = []

    def record(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(insurance_db.engine, "before_cursor_execute", record)
    try:
        listing(bestand, page_size=1)
        first_count = len(queries)
        queries.clear()
        listing(bestand, page_size=100)
        assert len(queries) == first_count == 4
    finally:
        event.remove(insurance_db.engine, "before_cursor_execute", record)
