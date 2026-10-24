"""Ärendeoperationerna i tjänstelagret (Fas 5 F5-2, B-033).

Mot testdatabasen i minnet med händelselogg och godkännandekö i databasen, så att
ärendets historik (händelser med case_id) och kopplingen till kön går att pröva.
"""

from datetime import date

import pytest
from sqlalchemy import select

from models import OperationEventRecord
from services import (
    AccessDeniedError,
    Actor,
    BlockedError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
    OperationContext,
    ProductRuleCatalog,
    ServiceLayer,
)

PERSON = "199001011234"  # testbeståndet i conftest
EMPLOYER = "5560000001"
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Lönefil från arbetsgivaren")
AGENT = OperationContext(actor=Actor.agent("case_handler", team="forsakring"), run_id="run-1",
                         reason="Arbetsgivarens lönefil")

CASE = {
    "case_type": "salary_report", "personal_id_number": PERSON, "employer_org_number": EMPLOYER,
    "period_month": "2025-10-15", "received_date": "2025-11-05", "source_reference": "LON-2025-10",
    "details": {"pensionable_salary_sek": "81000", "kind": "new", "corrects_version": None, "source": "employer"},
}


@pytest.fixture
def service(insurance_db):
    # Regelpaketet gäller – så att agenten får föreslå löneunderlag
    return ServiceLayer(session_factory=insurance_db.session_factory, rules=ProductRuleCatalog(today=date(2026, 11, 1)))


def create(service, **overrides):
    return service.execute("create_case", HUMAN, {**CASE, **overrides}).output.case_number


def events(insurance_db, case_number):
    with insurance_db.session_factory() as s:
        rows = s.scalars(
            select(OperationEventRecord).where(OperationEventRecord.case_id == case_number)
            .order_by(OperationEventRecord.occurred_at)
        ).all()
        return [(e.operation, e.outcome, e.actor_id) for e in rows]


class TestRegistrering:
    def test_arendenummer_och_historik(self, service, insurance_db):
        first = create(service)
        second = create(service, source_reference="LON-2025-11", period_month="2025-11-01")
        assert (first, second) == ("CASE-000001", "CASE-000002")
        case = service.execute("get_case", HUMAN, {"case_number": first}).output
        assert (case.status, case.period_month, case.channel, case.created_by) == (
            "open", date(2025, 10, 1), "manual", "karl"
        )
        assert (case.personal_id_number, case.employer_org_number) == (PERSON, EMPLOYER)
        assert case.details["pensionable_salary_sek"] == "81000"
        # Skapandet hamnar i loggen med ärendenumret, trots att numret inte fanns i anropet
        assert events(insurance_db, first) == [("create_case", "executed", "karl"), ("get_case", "executed", "karl")]

    @pytest.mark.parametrize(
        "overrides, error, message",
        [
            ({"personal_id_number": "198001010000"}, NotFoundError, "anslut personen"),
            ({"employer_org_number": "5569999999"}, NotFoundError, "arbetsgivare"),
            ({"policy_number": "AL-999999"}, NotFoundError, "hör inte till"),
            ({"received_date": "2099-01-01"}, BlockedError, "framtiden"),
            ({"details": {**CASE["details"], "kind": "correction"}}, InvalidInputError, "corrects_version"),
            ({"case_type": "complaint"}, InvalidInputError, "case_type"),
        ],
    )
    def test_ogiltig_registrering(self, service, overrides, error, message):
        with pytest.raises(error, match=message):
            create(service, **overrides)

    def test_samma_underlag_registreras_inte_tva_ganger(self, service):
        number = create(service)
        with pytest.raises(ConflictError, match=f"redan registrerat som ärende {number}"):
            create(service, period_month="2025-11-01")

    def test_forsakring_som_hor_till_personen(self, service):
        number = create(service, policy_number="AL-000001")
        assert service.execute("get_case", HUMAN, {"case_number": number}).output.policy_number == "AL-000001"


class TestListaOchStatus:
    def test_lista_aktiva_och_stangda(self, service):
        a = create(service)
        b = create(service, source_reference="LON-2025-11", period_month="2025-11-01")
        service.execute("close_case", HUMAN, {"case_number": b, "outcome": "no_action"})
        active = service.execute("list_cases", HUMAN, {}).output
        assert [c.case_number for c in active.cases] == [a]
        assert active.cases[0].name == "Test Testsson"
        closed = service.execute("list_cases", HUMAN, {"status": "closed"}).output
        assert [(c.case_number, c.outcome) for c in closed.cases] == [(b, "no_action")]
        everything = service.execute("list_cases", HUMAN, {"status": None, "personal_id_number": PERSON}).output
        assert everything.count == 2

    def test_statusbyte_och_tilldelning(self, service, insurance_db):
        number = create(service)
        out = service.execute(
            "update_case_status", HUMAN,
            {"case_number": number, "status": "in_progress", "assigned_to": "eva", "last_run_id": "run-9"},
        ).output
        assert (out.previous_status, out.status, out.assigned_to) == ("open", "in_progress", "eva")
        assert service.execute("get_case", HUMAN, {"case_number": number}).output.last_run_id == "run-9"
        assert ("update_case_status", "executed", "karl") in events(insurance_db, number)

    def test_stangning_gors_inte_via_statusbyte(self, service):
        number = create(service)
        with pytest.raises(InvalidInputError):
            service.execute("update_case_status", HUMAN, {"case_number": number, "status": "closed"})


class TestStangning:
    def test_avslag_kraver_motivering(self, service):
        number = create(service)
        with pytest.raises(InvalidInputError, match="motivering"):
            service.execute("close_case", HUMAN, {"case_number": number, "outcome": "rejected"})
        out = service.execute(
            "close_case", HUMAN, {"case_number": number, "outcome": "rejected", "closing_note": "Fel månad"}
        ).output
        assert (out.outcome, out.closed_by) == ("rejected", "karl")

    def test_stangt_arende_andras_inte(self, service):
        number = create(service)
        service.execute("close_case", HUMAN, {"case_number": number, "outcome": "no_action"})
        with pytest.raises(ConflictError, match="redan stängt"):
            service.execute("close_case", HUMAN, {"case_number": number, "outcome": "no_action"})
        with pytest.raises(ConflictError, match="stängt och ändras inte"):
            service.execute("update_case_status", HUMAN, {"case_number": number, "status": "in_progress"})

    def test_approved_kraver_genomford_andring(self, service, insurance_db):
        number = create(service)
        with pytest.raises(BlockedError, match="genomförd ändring"):
            service.execute("close_case", HUMAN, {"case_number": number, "outcome": "approved"})
        # Handläggaren registrerar själv, i ärendet
        in_case = OperationContext(actor=Actor.human("karl"), reason="Enligt ärendet", case_id=number)
        service.execute("register_salary_report", in_case, {
            "personal_id_number": PERSON, "employer_org_number": EMPLOYER, "period_month": "2025-10-01",
            "pensionable_salary_sek": "81000", "kind": "new", "source": "employer",
            "source_reference": "LON-2025-10", "received_date": "2025-11-05",
        })
        out = service.execute("close_case", HUMAN, {"case_number": number, "outcome": "approved"}).output
        assert out.outcome == "approved"
        assert [op for op, _, _ in events(insurance_db, number)] == [
            "create_case", "register_salary_report", "close_case"
        ]

    def test_vantande_forslag_maste_avgoras_forst(self, service):
        number = create(service)
        agent_in_case = OperationContext(actor=AGENT.actor, run_id="run-1", reason=AGENT.reason, case_id=number)
        proposal = service.execute("register_salary_report", agent_in_case, {
            "personal_id_number": PERSON, "employer_org_number": EMPLOYER, "period_month": "2025-10-01",
            "pensionable_salary_sek": "81000", "kind": "new", "source": "employer",
            "source_reference": "LON-2025-10", "received_date": "2025-11-05",
        })
        assert proposal.pending
        assert service.approvals.get(proposal.approval_id).case_id == number
        with pytest.raises(BlockedError, match="väntar i godkännandekön"):
            service.execute("close_case", HUMAN, {"case_number": number, "outcome": "no_action"})
        service.approve(proposal.approval_id, OperationContext(actor=Actor.human("karl")))
        assert service.execute("close_case", HUMAN, {"case_number": number, "outcome": "approved"}).output


class TestAgenten:
    def test_agenten_far_lasa_men_inte_skapa_andra_eller_stanga(self, service, insurance_db):
        number = create(service)
        assert service.execute("get_case", AGENT, {"case_number": number}).output.case_number == number
        for name, data in (
            ("create_case", {**CASE, "source_reference": "LON-X"}),
            ("list_cases", {}),
            ("update_case_status", {"case_number": number, "status": "in_progress"}),
            ("close_case", {"case_number": number, "outcome": "no_action"}),
        ):
            with pytest.raises(AccessDeniedError):
                service.execute(name, AGENT, data)
        assert ("get_case", "executed", "case_handler") in events(insurance_db, number)

    def test_annat_arende_an_kontextens_nekas(self, service):
        first = create(service)
        second = create(service, source_reference="LON-2025-11", period_month="2025-11-01")
        in_first = OperationContext(actor=AGENT.actor, run_id="run-1", case_id=first)
        with pytest.raises(InvalidInputError, match=f"körs i ärendet {first}"):
            service.execute("get_case", in_first, {"case_number": second})
