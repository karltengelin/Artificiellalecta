"""Syntetiska arbetsuppdrag; används av lokala och isolerade Postgres-prov."""

import json
from datetime import date
from types import SimpleNamespace

import yaml

from agents.case_policy import DEFAULT_POLICY
from agents.case_workspace import CaseWorkspace
from ai.providers.fake import FakeProvider, text_result, tool_call_result
from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer
from tests.test_agents_loop import ai_client
from web.agent import CaseAgent

HUMAN = Actor.human("karl")
PERSON = "199001011234"
EMPLOYER = "5560000001"
CASE = {
    "case_type": "salary_report", "personal_id_number": PERSON, "employer_org_number": EMPLOYER,
    "period_month": "2025-10-01", "received_date": "2025-11-05", "source_reference": "LON-2025-10",
    "details": {"pensionable_salary_sek": "81000", "kind": "new", "corrects_version": None, "source": "employer"},
}


def make_workspace(session_factory, tmp_path, *, automatic=False, scheduled=False):
    policy = yaml.safe_load(DEFAULT_POLICY.read_text(encoding="utf-8"))
    policy["case_types"]["salary_report"]["review_required"] = not automatic
    policy["case_types"]["salary_report"]["schedule"]["enabled"] = scheduled
    path = tmp_path / "case_policy.yaml"
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    rules = ProductRuleCatalog(today=date(2026, 11, 1))
    trusted = ServiceLayer(session_factory=session_factory, rules=rules)
    fake = FakeProvider()
    agent = CaseAgent(agent_service_factory=lambda: ServiceLayer(
        session_factory=session_factory, validation_session_factory=session_factory,
        agent_role="agent_forsakring", rules=rules), simulated_role=True,
        ai_factory=lambda: ai_client(fake), journal_dir=tmp_path / "runs")
    workspace = CaseWorkspace.build(trusted, agent, policy_path=path)
    return SimpleNamespace(workspace=workspace, trusted=trusted, fake=fake, agent=agent, policy_path=path,
                           session_factory=session_factory)


def create(env, **overrides):
    return env.trusted.execute("create_case", OperationContext(actor=HUMAN, reason="Syntetiskt löneunderlag"),
                               {**CASE, **overrides}).output.case_number


def answer(status="answered", summary="Underlaget är läst.", questions=None):
    return text_result(json.dumps({"status": status, "summary": summary, "questions": questions or [],
                                   "limitations": []}))


def read_case(number, call_id="read-case"):
    return tool_call_result("get_case", {"data": {"case_number": number}, "reason": None}, call_id=call_id)


def proposal(*, salary="81000", source_reference="LON-2025-10", person=PERSON):
    return tool_call_result("register_salary_report", {"data": {
        "personal_id_number": person, "employer_org_number": EMPLOYER,
        "period_month": "2025-10-01", "pensionable_salary_sek": salary,
        "kind": "new", "corrects_version": None, "source": "employer",
        "source_reference": source_reference, "received_date": "2025-11-05",
    }, "reason": "Kontrollerat mot ärendets löneunderlag"}, call_id="proposal")


def work(env, ident):
    from models import CaseWork

    with env.session_factory() as session:
        return session.get(CaseWork, ident)
