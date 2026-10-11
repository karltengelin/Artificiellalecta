"""Tester för tjänstelagrets första läsoperationer (Fas 1f, T2) mot testdatabasen i minnet."""

from datetime import date
from decimal import Decimal

import pytest

from ai import ToolSpec
from services import (
    Actor,
    AgentAccess,
    InvalidInputError,
    MemoryEventLog,
    NotFoundError,
    OperationContext,
    ServiceError,
    ServiceLayer,
)
from skills.calculation.calculate_itp1_premium import calculate_itp1_premium

# SQLite lagrar Numeric som flyttal; modellernas skala avrundar tillbaka till ören
pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

HUMAN = OperationContext(actor=Actor.human("karl"))
AGENT = OperationContext(actor=Actor.agent("case_handler", team="forsakring"), run_id="run-7")


@pytest.fixture
def service(insurance_db):
    return ServiceLayer(session_factory=insurance_db.session_factory, events=MemoryEventLog())


class TestForsakringsoversikt:
    def test_oversikt_via_personnummer(self, service):
        out = service.execute("get_insured_overview", HUMAN, {"personal_id_number": "199001011234"}).output
        assert (out.first_name, out.status, out.employer.name) == ("Test", "terminated", "Testbolaget AB")
        assert out.monthly_salary_sek == Decimal("80000")
        (policy,) = out.policies
        assert policy.policy_number == "AL-000001"
        assert (policy.current_state.state, policy.current_state.valid_from) == ("paid_up", date(2026, 1, 1))
        # Kapital = betalda transaktioner: 10 000 + 10 000 − 500 − 20 (den fakturerade räknas inte)
        assert policy.benefits[0].capital_sek == Decimal("19480.00")
        assert out.total_capital_sek == Decimal("19480.00")

    def test_oversikt_via_forsakringsnummer_ger_samma_person(self, service):
        out = service.execute("get_insured_overview", HUMAN, {"policy_number": "AL-000001"}).output
        assert out.personal_id_number == "199001011234"

    def test_okand_forsakrad(self, service):
        with pytest.raises(NotFoundError):
            service.execute("get_insured_overview", HUMAN, {"personal_id_number": "190001010000"})

    def test_exakt_ett_sokbegrepp(self, service):
        with pytest.raises(InvalidInputError):
            service.execute("get_insured_overview", HUMAN, {})
        with pytest.raises(InvalidInputError):
            service.execute(
                "get_insured_overview", HUMAN,
                {"personal_id_number": "199001011234", "policy_number": "AL-000001"},
            )

    def test_agent_far_lasa_och_atkomsten_loggas(self, service):
        service.execute("get_insured_overview", AGENT, {"policy_number": "AL-000001"})
        (event,) = service.events.events
        assert (event.outcome, event.actor_id, event.run_id, event.pii) == ("executed", "case_handler", "run-7", True)


class TestPremiehistorik:
    def test_hela_historiken_sorterad_med_betald_summa(self, service):
        out = service.execute("get_premium_history", HUMAN, {"policy_number": "AL-000001"}).output
        assert out.count == 5
        assert [r.period_month for r in out.transactions] == sorted(r.period_month for r in out.transactions)
        assert out.total_paid_sek == Decimal("19480.00")
        assert {r.benefit_type for r in out.transactions} == {"retirement_dc"}

    def test_urval_pa_manader(self, service):
        out = service.execute(
            "get_premium_history", HUMAN, {"policy_number": "AL-000001", "from_month": "2026-01-15"}
        ).output
        assert [(r.period_month, r.status) for r in out.transactions] == [(date(2026, 1, 1), "invoiced")]
        assert out.total_paid_sek == Decimal("0.00")

    def test_okand_forsakring(self, service):
        with pytest.raises(NotFoundError):
            service.execute("get_premium_history", HUMAN, {"policy_number": "AL-999999"})


class TestForhandsberakning:
    def test_premie_2026_enligt_premietrappan(self, service):
        out = service.execute(
            "calculate_premium_preview", AGENT, {"monthly_salary_sek": "80000", "period_month": "2026-03-01"}
        ).output
        assert out.income_base_amount_sek == Decimal("83400")
        assert out.total_premium_sek == Decimal("10708.13")  # 2 345,63 + 30 % × 27 875 (skillens exempel)
        assert out.in_age_window is None
        assert service.events.events == []  # beräkning utan personuppgifter loggas inte

    def test_ratt_basbelopp_per_ar(self, service):
        out = service.execute(
            "calculate_premium_preview", HUMAN, {"monthly_salary_sek": "80000", "period_month": "2025-06-20"}
        ).output
        assert out.period_month == date(2025, 6, 1)
        assert out.total_premium_sek == calculate_itp1_premium(Decimal("80000"), Decimal("80600")).total_premium_sek

    def test_aldersfonster_kontrolleras_med_fodelsedatum(self, service):
        out = service.execute(
            "calculate_premium_preview", HUMAN,
            {"monthly_salary_sek": "80000", "period_month": "2026-01-01", "birth_date": "1955-01-01"},
        ).output
        assert (out.in_age_window, out.total_premium_sek) == (False, Decimal("0.00"))

    def test_basbelopp_saknas(self, service):
        with pytest.raises(NotFoundError, match="2024"):
            service.execute(
                "calculate_premium_preview", HUMAN, {"monthly_salary_sek": "80000", "period_month": "2024-01-01"}
            )

    def test_negativ_lon_avvisas(self, service):
        with pytest.raises(InvalidInputError):
            service.execute(
                "calculate_premium_preview", HUMAN, {"monthly_salary_sek": "-1", "period_month": "2026-01-01"}
            )


class TestAgentredo:
    def test_lasoperationerna_ar_oppna_for_agenter_enligt_registret(self, service):
        for name in ("get_insured_overview", "get_premium_history", "calculate_premium_preview"):
            assert service.decision(name).effective == AgentAccess.AGENT

    def test_indatamodellerna_blir_strikta_verktyg(self, service):
        # Harness (Fas 3b) bygger verktyg ur operationerna – det ska fungera redan nu
        tools = [ToolSpec.from_model(op.name, op.description, op.input_model) for op in service.operations_for_agents()]
        assert {t.name for t in tools} >= {"get_insured_overview", "get_premium_history", "calculate_premium_preview"}
        assert all(t.strict and t.parameters["additionalProperties"] is False for t in tools)

    def test_utan_databasanslutning_ges_tydligt_fel(self):
        service = ServiceLayer(events=MemoryEventLog())
        with pytest.raises(ServiceError, match="databasanslutning"):
            service.execute("get_premium_history", HUMAN, {"policy_number": "AL-000001"})
