"""Agentkörning i ett ärende (Fas 5 F5-3, B-033) – mot testdatabasen och FakeProvider.

Ärendet ger mandatet: agenten når ärendets försäkrade, arbetsgivare och period, och bara
ärendet självt. Efter körningen skriver harness ärendets status – aldrig modellen.
"""

from datetime import date

import pytest

from agents import (
    CallStatus,
    Dispatcher,
    Ecosystem,
    HarnessError,
    MemoryJournal,
    RunStatus,
    SkillRegistry,
    case_and_scope,
    compile_profile,
    request_for_case,
    run_case,
    scope_for_case,
)
from ai import ToolCall
from ai.providers.fake import FakeProvider, text_result, tool_call_result
from services import (
    Actor,
    MemoryEventLog,
    OperationContext,
    ProductRuleCatalog,
    ServiceLayer,
    default_registry,
)
from tests.test_agents_loop import ai_client

PERSON = "199001011234"  # testbeståndet i conftest
EMPLOYER = "5560000001"
AFTER_RULES = date(2026, 11, 1)
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Lönefil från arbetsgivaren")

CASE = {
    "case_type": "salary_report", "personal_id_number": PERSON, "employer_org_number": EMPLOYER,
    "period_month": "2025-10-01", "received_date": "2025-11-05", "source_reference": "LON-2025-10",
    "details": {"pensionable_salary_sek": "81000", "kind": "new", "corrects_version": None, "source": "employer"},
}
SALARY = {
    "data": {"personal_id_number": PERSON, "employer_org_number": EMPLOYER, "period_month": "2025-10-01",
             "pensionable_salary_sek": "81000", "kind": "new", "corrects_version": None, "source": "employer",
             "source_reference": "LON-2025-10", "received_date": "2025-11-05"},
    "reason": "Enligt ärendets löneunderlag",
}


@pytest.fixture
def env(insurance_db):
    rules = ProductRuleCatalog(today=AFTER_RULES)
    trusted = ServiceLayer(session_factory=insurance_db.session_factory, rules=rules)
    agent = ServiceLayer(
        session_factory=insurance_db.session_factory, validation_session_factory=insurance_db.session_factory,
        agent_role="agent_forsakring", rules=rules, events=trusted.events, approvals=trusted.approvals,
    )
    eco = Ecosystem.load()
    return trusted, agent, eco, SkillRegistry.build(eco, default_registry)


def create(trusted, **overrides):
    return trusted.execute("create_case", HUMAN, {**CASE, **overrides}).output.case_number


def journal(run_id="run-1"):
    return MemoryJournal(run_id=run_id, team="forsakring", agent="case_handler")


class TestMandat:
    def test_mandatet_byggs_ur_arendet(self, env):
        trusted, *_ = env
        number = create(trusted)
        scope = scope_for_case(trusted, number, assigned_by="karl")
        assert (scope.persons, scope.policies, scope.employers) == ({PERSON}, {"AL-000001"}, {EMPLOYER})
        assert (scope.from_month, scope.to_month) == (date(2023, 11, 1), date(2025, 10, 1))  # 24 månader
        assert (scope.case_id, scope.ref) == (number, f"scope-{number}")

    def test_stangt_arende_ger_inget_mandat(self, env):
        trusted, *_ = env
        number = create(trusted)
        trusted.execute("close_case", HUMAN, {"case_number": number, "outcome": "no_action"})
        with pytest.raises(HarnessError, match="stängt"):
            scope_for_case(trusted, number, assigned_by="karl")

    def test_uppdraget_har_arendenumret_men_inga_personuppgifter(self, env):
        trusted, *_ = env
        number = create(trusted)
        case, scope = case_and_scope(trusted, number, assigned_by="karl")
        request = request_for_case(case, scope)
        assert (request.case_id, request.execution_scope_ref, request.references) == (number, scope.ref, (number,))
        assert number in request.goal and "get_case" in request.goal
        for secret in (PERSON, EMPLOYER, "81000", "Testsson"):
            assert secret not in request.goal + " ".join(request.constraints)

    def test_agenten_nar_bara_korningens_arende(self, env):
        trusted, agent, eco, skills = env
        own = create(trusted)
        other = create(trusted, source_reference="LON-2025-11", period_month="2025-11-01")
        case, scope = case_and_scope(trusted, own, assigned_by="karl")
        request = request_for_case(case, scope)
        profile = compile_profile(eco, skills, agent, request=request)
        assert profile.decision("get_case").outcome.value == "execute"
        dispatcher = Dispatcher(profile, agent, run_id="run-1", case_id=own, scope=scope)

        def get(number, call_id):
            return ToolCall(id=call_id, name="get_case", arguments={"data": {"case_number": number}, "reason": None})

        (mine,) = dispatcher.dispatch([get(own, "c1")]).calls
        assert mine.status == CallStatus.DONE
        (theirs,) = dispatcher.dispatch([get(other, "c2")]).calls
        assert theirs.status == CallStatus.DENIED
        assert "inte körningens ärende" in theirs.result.content


class TestKorning:
    def test_forslag_i_arendet_ger_vantan_och_status(self, env):
        trusted, agent, eco, skills = env
        number = create(trusted)
        fake = FakeProvider([
            tool_call_result("get_case", {"data": {"case_number": number}, "reason": None}),
            tool_call_result("calculate_premium_preview", {
                "data": {"monthly_salary_sek": "81000", "period_month": "2025-10-01", "birth_date": None},
                "reason": None,
            }, call_id="call_2"),
            tool_call_result("register_salary_report", SALARY, call_id="call_3"),
        ])
        run = run_case(ai_client(fake), eco, skills, agent, trusted, number, assigned_by="karl",
                       run_id="run-1", journal=journal())
        assert run.outcome.result.status == RunStatus.WAITING_APPROVAL
        assert run.case_status == "waiting_approval"
        case = trusted.execute("get_case", HUMAN, {"case_number": number}).output
        assert (case.status, case.last_run_id) == ("waiting_approval", "run-1")
        (pending,) = trusted.approvals.list("pending")
        assert (pending.case_id, pending.run_id, pending.proposed_by) == (number, "run-1", "case_handler")

        # Handläggaren godkänner och stänger ärendet
        trusted.approve(pending.id, OperationContext(actor=Actor.human("karl")))
        closed = trusted.execute("close_case", HUMAN, {"case_number": number, "outcome": "approved"}).output
        assert closed.outcome == "approved"

    def test_korning_utan_forslag_ger_in_progress(self, env):
        trusted, agent, eco, skills = env
        number = create(trusted)
        fake = FakeProvider([
            tool_call_result("get_case", {"data": {"case_number": number}, "reason": None}),
            text_result("Underlaget saknar uppgift om källa – komplettering behövs."),
        ])
        run = run_case(ai_client(fake), eco, skills, agent, trusted, number, assigned_by="karl",
                       run_id="run-2", journal=journal("run-2"))
        assert (run.outcome.result.status, run.case_status) == (RunStatus.COMPLETED, "in_progress")

    def test_harness_skriver_status_som_systemaktor(self, env, insurance_db):
        from sqlalchemy import select

        from models import OperationEventRecord

        trusted, agent, eco, skills = env
        number = create(trusted)
        fake = FakeProvider([text_result("Inget att göra.")])
        run_case(ai_client(fake), eco, skills, agent, trusted, number, assigned_by="karl",
                 run_id="run-3", journal=journal("run-3"))
        with insurance_db.session_factory() as s:
            status_events = s.scalars(select(OperationEventRecord).where(
                OperationEventRecord.case_id == number, OperationEventRecord.operation == "update_case_status",
            )).all()
        assert [(e.actor_type, e.actor_id, e.run_id) for e in status_events] == [("system", "harness", "run-3")]


def test_utan_databasroll_ser_agenten_inte_arendet(insurance_db):
    trusted = ServiceLayer(session_factory=insurance_db.session_factory, events=MemoryEventLog())
    eco = Ecosystem.load()
    number = create(trusted)
    case, scope = case_and_scope(trusted, number, assigned_by="karl")
    profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), trusted,
                              request=request_for_case(case, scope))
    assert not profile.decision("get_case").visible
