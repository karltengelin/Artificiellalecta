"""Agentens begränsade databasroll mot en riktig Postgres (harness.md §5.1, §11.2).

SQLite har inga roller – här prövas att rollen `agent_forsakring` med rättigheterna i
src/utils/agent_roles.py räcker för agentens läsningar, förslag och loggrader, och att
den inte kan något mer: inte ändra affärsdata, inte avgöra förslag, inte ändra loggen,
inte låsa rader och inte läsa andra områdens tabeller.

Körs bara när både SERVICES_TEST_POSTGRES_URL (app_backend) och
SERVICES_TEST_AGENT_POSTGRES_URL (agent_forsakring) pekar på den ISOLERADE
testdatabasen. Ett eget schema skapas och tas bort efteråt; beståndet rörs aldrig.
"""

from __future__ import annotations

import os
from datetime import date

import pytest
from sqlalchemy import create_engine, func, select

from agents import (
    CallStatus,
    Dispatcher,
    Ecosystem,
    RunRequest,
    RunStatus,
    SkillRegistry,
    compile_profile,
    scope_for_person,
)
from ai import ToolCall
from models import ApprovalRequestRecord, OperationEventRecord, SalaryReport
from services import (
    Actor,
    OperationContext,
    ProductRuleCatalog,
    ServiceLayer,
    default_registry,
)
from services.db import session_factory_for
from tests.test_services_postgres import TEST_URL, isolated_schema
from utils.agent_roles import (
    FORSAKRING,
    RETURNING_COLUMNS,
    current_column_privileges,
    current_privileges,
    inspect_role,
)

AGENT_URL = os.environ.get("SERVICES_TEST_AGENT_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not (TEST_URL and AGENT_URL),
    reason="SERVICES_TEST_POSTGRES_URL och SERVICES_TEST_AGENT_POSTGRES_URL behövs för rollproven",
)

PERSON = "199001011234"  # testbeståndet i conftest
AFTER_RULES = date(2026, 11, 1)
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Granskat")
AGENT = OperationContext(actor=Actor.agent("case_handler", team="forsakring"), run_id="run-pg")
AGENT_WRITE = OperationContext(
    actor=Actor.agent("case_handler", team="forsakring"), run_id="run-pg", reason="Arbetsgivarens lönefil"
)

SALARY = {
    "personal_id_number": PERSON, "employer_org_number": "5560000001", "period_month": "2025-10-01",
    "pensionable_salary_sek": "81000", "kind": "new", "source": "employer",
    "source_reference": "lönefil", "received_date": "2025-11-05",
}


@pytest.fixture(scope="module")
def db():
    if AGENT_URL == os.environ.get("AGENT_FORSAKRING_DATABASE_URL"):
        pytest.fail("SERVICES_TEST_AGENT_POSTGRES_URL får inte peka på beståndet")
    from models import Base
    from tests.conftest import seed_insurance

    with isolated_schema() as schema:
        Base.metadata.create_all(schema.engine)
        seed_insurance(schema.session_factory)
        with schema.engine.begin() as conn:
            for statement in FORSAKRING.statements(schema.name):
                conn.exec_driver_sql(statement)
        agent_engine = create_engine(AGENT_URL, connect_args={"options": f"-csearch_path={schema.name}"})
        schema.agent_engine = agent_engine
        schema.agent_factory = session_factory_for(agent_engine)
        try:
            yield schema
        finally:
            agent_engine.dispose()


def agent_service(db) -> ServiceLayer:
    """Som services.db.agent_service_layer, men mot testschemat."""
    return ServiceLayer(
        session_factory=db.agent_factory, validation_session_factory=db.session_factory,
        agent_role="agent_forsakring", rules=ProductRuleCatalog(today=AFTER_RULES),
    )


def count(db, model) -> int:
    with db.session_factory() as s:
        return s.scalar(select(func.count()).select_from(model))


def test_forkontrollen_godkanner_rollen_och_rattigheterna_ar_exakta(db):
    with db.engine.connect() as conn:
        assert inspect_role(conn, FORSAKRING, db.name) == []
        privileges = current_privileges(conn, "agent_forsakring", db.name)
        columns = current_column_privileges(conn, "agent_forsakring", db.name)
    assert privileges == {
        **{t: ["SELECT"] for t in FORSAKRING.select},
        **{t: ["INSERT"] for t in FORSAKRING.insert},
    }
    assert columns == {f"{t}.{c}": ["SELECT"] for t in FORSAKRING.insert for c in RETURNING_COLUMNS}


def test_agenten_laser_och_loggraden_skrivs(db):
    before = count(db, OperationEventRecord)
    out = agent_service(db).execute("get_insured_overview", AGENT, {"personal_id_number": PERSON}).output
    assert out.personal_id_number == PERSON
    assert count(db, OperationEventRecord) == before + 1


def test_forslag_provkors_med_betrodd_anslutning_och_hamnar_i_kon(db):
    reports, approvals = count(db, SalaryReport), count(db, ApprovalRequestRecord)
    result = agent_service(db).execute("register_salary_report", AGENT_WRITE, {**SALARY})
    assert result.pending
    assert count(db, ApprovalRequestRecord) == approvals + 1
    assert count(db, SalaryReport) == reports  # provkörningen rullades tillbaka

    # Handläggaren godkänner via den vanliga anslutningen
    human = ServiceLayer(session_factory=db.session_factory, rules=ProductRuleCatalog(today=AFTER_RULES))
    assert not human.approve(result.approval_id, HUMAN).pending
    assert count(db, SalaryReport) == reports + 1


def test_utan_betrodd_anslutning_kan_agentrollen_inte_provkora(db):
    """Därför två anslutningar: provkörningen skriver och låser rader."""
    alone = ServiceLayer(session_factory=db.agent_factory, rules=ProductRuleCatalog(today=AFTER_RULES))
    with pytest.raises(Exception, match="permission denied"):
        alone.execute("register_salary_report", AGENT_WRITE, {**SALARY, "period_month": "2025-09-01", "source_reference": "lönefil 2025-09-01"})


def test_agentrollen_kan_inte_avgora_forslag(db):
    agent = agent_service(db)
    pending = agent.execute("register_salary_report", AGENT_WRITE, {**SALARY, "period_month": "2025-08-01", "source_reference": "lönefil 2025-08-01"})
    with pytest.raises(Exception, match="permission denied"):
        agent.approve(pending.approval_id, HUMAN)  # även med människa som aktör
    with db.session_factory() as s:
        assert s.get(ApprovalRequestRecord, pending.approval_id).status == "pending"


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE operation_events SET reason = 'ändrad'",
        "DELETE FROM operation_events",
        "UPDATE approval_requests SET status = 'approved'",
        "DELETE FROM approval_requests",
        "UPDATE insured_persons SET monthly_salary_sek = 1",
        "UPDATE cases SET status = 'closed'",
        "DELETE FROM cases",
        "DELETE FROM premium_transactions",
        "INSERT INTO base_amounts (year, income_base_amount_sek) VALUES (2099, 1)",
        "SELECT * FROM insured_persons FOR UPDATE",
        "SELECT * FROM operation_events",
        "SELECT * FROM approval_requests",
        "SELECT reason, input FROM operation_events",
        "SELECT * FROM portfolios",
        "TRUNCATE salary_reports",
        "CREATE TABLE agent_egen (id int)",
    ],
)
def test_agentrollen_nekas_allt_annat(db, sql):
    with db.agent_engine.connect() as conn, pytest.raises(Exception, match="permission denied"):
        conn.exec_driver_sql(sql)


def test_dispatchern_hela_vagen_med_agentrollen(db):
    service = agent_service(db)
    scope = scope_for_person(
        service, ref="scope-pg", personal_id_number=PERSON,
        from_month=date(2025, 1, 1), to_month=date(2026, 10, 1), assigned_by="karl",
    )
    eco = Ecosystem.load()
    request = RunRequest(task_id="t-pg", target_team="forsakring", goal="Kontrollera löneunderlag",
                         execution_scope_ref="scope-pg")
    profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), service, request=request)
    assert {d.skill for d in profile.visible()} == {
        "get_case", "get_insured_overview", "get_premium_history", "get_salary_reports",
        "register_salary_report", "calculate_premium_preview",
    }
    outcome = Dispatcher(profile, service, run_id="run-pg", scope=scope).dispatch([
        ToolCall(id="c1", name="get_insured_overview",
                 arguments={"data": {"personal_id_number": PERSON, "policy_number": None}, "reason": None}),
        ToolCall(id="c2", name="register_salary_report",
                 arguments={"data": {**SALARY, "period_month": "2025-07-01", "source_reference": "lönefil 2025-07-01", "corrects_version": None},
                            "reason": "Arbetsgivarens lönefil"}),
    ])
    assert [c.status for c in outcome.calls] == [CallStatus.DONE, CallStatus.PENDING_APPROVAL]


def test_arendekorning_med_agentrollen(db, tmp_path):
    """Hela Fas 5-kedjan med den begränsade rollen: ärende → mandat → läsning → förslag → status."""
    from agents import run_case
    from ai.providers.fake import FakeProvider, tool_call_result
    from tests.test_agents_loop import ai_client

    trusted = ServiceLayer(session_factory=db.session_factory, rules=ProductRuleCatalog(today=AFTER_RULES))
    number = trusted.execute("create_case", HUMAN, {
        "case_type": "salary_report", "personal_id_number": PERSON, "employer_org_number": "5560000001",
        "period_month": "2025-06-01", "received_date": "2025-07-05", "source_reference": "lönefil 2025-06",
        "details": {"pensionable_salary_sek": "81000", "kind": "new", "corrects_version": None, "source": "employer"},
    }).output.case_number
    salary = {**SALARY, "period_month": "2025-06-01", "source_reference": "lönefil 2025-06",
              "received_date": "2025-07-05", "corrects_version": None}
    fake = FakeProvider([
        tool_call_result("get_case", {"data": {"case_number": number}, "reason": None}),
        tool_call_result("register_salary_report", {"data": salary, "reason": "Enligt ärendet"}, call_id="c2"),
    ])
    eco = Ecosystem.load()
    run = run_case(ai_client(fake), eco, SkillRegistry.build(eco, default_registry), agent_service(db), trusted,
                   number, assigned_by="karl", run_id="run-case-pg", journal_dir=tmp_path)
    assert run.outcome.result.status == RunStatus.WAITING_APPROVAL
    assert trusted.execute("get_case", HUMAN, {"case_number": number}).output.status == "waiting_approval"
