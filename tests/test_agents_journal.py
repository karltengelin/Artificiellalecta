"""Tester för körjournalen (3b-6) och fortsättningen efter godkännande (3b-5).

Journalen ska visa vad agenten gjorde, i ordning, utan råa personuppgifter. En
fortsättning ska bara starta när förslagen är avgjorda, inte anropa den avgjorda
operationen igen och inte få mer budget än rotkörningen hade kvar.
"""

import json
from datetime import date
from types import SimpleNamespace

import pytest

from agents import (
    ContinuationNotReady,
    Ecosystem,
    FileJournal,
    HarnessError,
    JournalError,
    MemoryJournal,
    RunRequest,
    RunRequestError,
    RunStatus,
    SkillRegistry,
    compile_profile,
    prepare_continuation,
    read_journal,
    run_agent,
    scope_for_person,
)
from agents.journal import mask
from ai.providers.fake import FakeProvider, text_result, tool_call_result
from services import (
    Actor,
    MemoryEventLog,
    OperationContext,
    ProductRuleCatalog,
    ServiceLayer,
    default_registry,
)
from tests.test_agents_loop import AFTER_RULES, PERSON, PREVIEW, ai_client

HUMAN = OperationContext(actor=Actor.human("karl"))
OVERVIEW = {"data": {"personal_id_number": PERSON, "policy_number": None}, "reason": None}
SALARY = {
    "data": {"personal_id_number": PERSON, "employer_org_number": "5560000001", "period_month": "2025-10-01",
             "pensionable_salary_sek": "81000", "kind": "new", "corrects_version": None, "source": "employer",
             "source_reference": "lönefil", "received_date": "2025-11-05"},
    "reason": "Arbetsgivarens lönefil för oktober (199001011234)",
}


class TestJournalen:
    def test_en_skrivare_per_korning(self, tmp_path):
        FileJournal(tmp_path, run_id="run-x", team="forsakring", agent="case_handler")
        with pytest.raises(JournalError, match="finns redan"):
            FileJournal(tmp_path, run_id="run-x", team="forsakring", agent="case_handler")

    def test_skadad_sista_rad_rapporteras_men_skrivs_inte_om(self, tmp_path):
        path = tmp_path / "run.jsonl"
        path.write_text('{"seq": 1}\n{"seq": 2', encoding="utf-8")
        events, corrupt = read_journal(path)
        assert events == [{"seq": 1}] and corrupt
        path.write_text('{"seq": 1}\n{"seq"\n{"seq": 3}\n', encoding="utf-8")
        with pytest.raises(JournalError, match="rad 2"):
            read_journal(path)

    def test_maskering(self):
        assert mask("Lön för 199001011234 hos 5560000001, AL-000123, test@exempel.se") == (
            "Lön för [maskerat] hos [maskerat], AL-[maskerat], [e-post]"
        )


@pytest.fixture
def calc(insurance_db):
    service = ServiceLayer(session_factory=insurance_db.session_factory, events=MemoryEventLog())
    eco = Ecosystem.load()
    request = RunRequest(task_id="task-1", target_team="forsakring", goal="Förhandsberäkna premien")
    profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), service, request=request)
    return profile, service, request


def test_journalen_foljer_korningen_i_ordning(calc):
    profile, service, request = calc
    journal = MemoryJournal(run_id="run-1", team="forsakring", agent="case_handler")
    fake = FakeProvider([tool_call_result("calculate_premium_preview", PREVIEW), text_result("Klart.")])
    run_agent(ai_client(fake), profile, service, request, run_id="run-1", journal=journal)
    events = journal.events
    assert [e["type"] for e in events] == [
        "run_started", "policy_resolved", "model_returned", "tool_intent", "tool_completed",
        "model_returned", "run_ended",
    ]
    assert [e["seq"] for e in events] == list(range(1, 8))
    assert {(e["run_id"], e["root_run_id"], e["team"], e["agent"]) for e in events} == {
        ("run-1", "run-1", "forsakring", "case_handler")
    }
    started, policy, model, intent, done, _, ended = events
    assert started["versions"]["policy_id"] == "harness-v1" and started["root_limits"]["max_steps"] == 12
    assert [t["skill"] for t in policy["tools"]] == ["calculate_premium_preview"]
    assert "text" not in model and model["text_length"] == 0 and model["tool_calls"][0]["skill"] == (
        "calculate_premium_preview"
    )
    assert intent["step"] == 1 and len(intent["input_hash"]) == 64 and "input" not in intent
    assert done["status"] == "done" and "output" not in done
    assert ended["status"] == "completed" and ended["usage"]["steps"] == 2
    assert ended["root_usage"] == ended["usage"]


def test_journal_som_inte_kan_skrivas_stoppar_fore_verktyget(calc):
    profile, service, request = calc

    class Failing(MemoryJournal):
        def append(self, type, **fields):
            if type == "tool_intent":
                raise JournalError("disken är full")
            return super().append(type, **fields)

    journal = Failing(run_id="run-1", team="forsakring", agent="case_handler")
    fake = FakeProvider([tool_call_result("calculate_premium_preview", PREVIEW), text_result("x")])
    outcome = run_agent(ai_client(fake), profile, service, request, run_id="run-1", journal=journal)
    assert outcome.result.status == RunStatus.FAILED
    assert outcome.dispatches == () and len(fake.requests) == 1


def test_journal_som_inte_kan_startas_ger_inget_modellanrop(calc):
    profile, service, request = calc

    class Broken(MemoryJournal):
        def append(self, type, **fields):
            raise JournalError("skrivskyddad")

    fake = FakeProvider([text_result("x")])
    with pytest.raises(JournalError):
        run_agent(ai_client(fake), profile, service, request,
                  journal=Broken(run_id="r", team="forsakring", agent="case_handler"))
    assert fake.requests == []


# --- med personuppgifter: journal utan råa uppgifter och fortsättning --------------------------


@pytest.fixture
def pii(insurance_db, tmp_path):
    service = ServiceLayer(
        session_factory=insurance_db.session_factory, validation_session_factory=insurance_db.session_factory,
        agent_role="agent_forsakring", events=MemoryEventLog(), rules=ProductRuleCatalog(today=AFTER_RULES),
    )
    trusted = ServiceLayer(session_factory=insurance_db.session_factory, events=MemoryEventLog(),
                           rules=ProductRuleCatalog(today=AFTER_RULES))
    scope = scope_for_person(trusted, ref="scope-1", personal_id_number=PERSON,
                             from_month=date(2025, 1, 1), to_month=date(2026, 10, 1), assigned_by="karl")
    request = RunRequest(task_id="task-2", target_team="forsakring",
                         goal=f"Förbered oktoberlön för Test Testsson ({PERSON}), född 1990-01-01",
                         execution_scope_ref="scope-1")
    eco = Ecosystem.load()
    skills = SkillRegistry.build(eco, default_registry)

    def start(script, *, req=request, continuation=None, run_id="run-a"):
        profile = compile_profile(eco, skills, service, request=req)
        return run_agent(ai_client(FakeProvider(script)), profile, service, req, scope=scope, run_id=run_id,
                         journal_dir=tmp_path, continuation=continuation), profile

    return SimpleNamespace(start=start, request=request, trusted=trusted, skills=skills, dir=tmp_path)


def waiting_run(pii):
    outcome, _ = pii.start([tool_call_result("get_insured_overview", OVERVIEW),
                            tool_call_result("register_salary_report", SALARY, call_id="call_2")])
    assert outcome.result.status == RunStatus.WAITING_APPROVAL
    return outcome, read_journal(pii.dir / "run-a.jsonl")


def test_journalen_har_inga_raa_personuppgifter(pii):
    outcome, (events, corrupt) = waiting_run(pii)
    raw = (pii.dir / "run-a.jsonl").read_text(encoding="utf-8")
    assert not corrupt
    for secret in (PERSON, "5560000001", "Testsson", "81000", "1990-01-01"):
        assert secret not in raw
    wait = next(e for e in events if e["type"] == "approval_wait")
    assert wait["approval_id"] == outcome.result.pending_approvals[0]
    assert wait["business_change_executed"] is False
    intent = next(e for e in events if e["type"] == "tool_intent" and e["skill"] == "register_salary_report")
    assert set(intent["reason"]) == {"sha256", "length"}  # fri text från modellen: bara hash och längd
    started = events[0]
    assert set(started["goal"]) == {"sha256", "length"}


def test_ai_log_content_far_inte_vara_pa_med_pii_verktyg(pii, insurance_db):
    service = ServiceLayer(
        session_factory=insurance_db.session_factory, validation_session_factory=insurance_db.session_factory,
        agent_role="agent_forsakring", events=MemoryEventLog(), rules=ProductRuleCatalog(today=AFTER_RULES),
    )
    profile = compile_profile(Ecosystem.load(), pii.skills, service, request=pii.request)
    ai = ai_client(FakeProvider([text_result("x")]))
    ai._log_content = True  # som AI_LOG_CONTENT=true
    with pytest.raises(HarnessError, match="AI_LOG_CONTENT"):
        run_agent(ai, profile, service, pii.request, journal_dir=pii.dir)


class TestFortsattning:
    def test_vantande_forslag_ger_ingen_fortsattning(self, pii):
        _, (events, _) = waiting_run(pii)
        with pytest.raises(ContinuationNotReady, match="väntar fortfarande"):
            prepare_continuation(pii.request, events, pii.trusted, pii.skills)

    def test_godkant_forslag_gors_inte_om_och_budgeten_ar_rotens(self, pii):
        first, (events, _) = waiting_run(pii)
        (approval_id,) = first.result.pending_approvals
        pii.trusted.approve(approval_id, HUMAN)

        cont = prepare_continuation(pii.request, events, pii.trusted, pii.skills)
        assert cont.continuation_of == "run-a" and cont.root_run_id == "run-a"
        assert "register_salary_report" in cont.request.deny_skills
        assert cont.request.limits.max_steps == 12 - 2  # två modellsteg förbrukade i första segmentet
        assert cont.request.limits.max_cost_usd == pytest.approx(0.5 - first.result.cost_usd)

        outcome, profile = pii.start([text_result("Löneunderlaget för oktober är registrerat.")],
                                     req=cont.request, continuation=cont, run_id="run-b")
        assert outcome.result.status == RunStatus.COMPLETED
        assert "nekad i uppdraget" in profile.decision("register_salary_report").reasons
        first_message = outcome.history[0].text
        assert f"{approval_id} (register_salary_report): godkänt av karl" in first_message

        events_b, _ = read_journal(pii.dir / "run-b.jsonl")
        assert {(e["root_run_id"], e["continuation_of"]) for e in events_b} == {("run-a", "run-a")}
        observed = [e for e in events_b if e["type"] == "approval_observed"]
        assert [(o["approval_id"], o["decision"], o["decided_by"]) for o in observed] == [
            (approval_id, "approved", "karl")
        ]
        ended = events_b[-1]
        assert ended["usage"]["steps"] == 1 and ended["root_usage"]["steps"] == 3

    def test_avslag_med_motivering_i_kontexten(self, pii):
        first, (events, _) = waiting_run(pii)
        pii.trusted.reject(first.result.pending_approvals[0], HUMAN, note="Fel månad enligt arbetsgivaren")
        cont = prepare_continuation(pii.request, events, pii.trusted, pii.skills)
        assert "avslaget av karl: Fel månad enligt arbetsgivaren" in cont.note()
        assert "Föreslå inte samma sak igen" in cont.note()

    def test_fortsattning_far_inte_koras_med_annat_uppdrag(self, pii):
        first, (events, _) = waiting_run(pii)
        pii.trusted.approve(first.result.pending_approvals[0], HUMAN)
        cont = prepare_continuation(pii.request, events, pii.trusted, pii.skills)
        with pytest.raises(HarnessError, match="fortsättningens uppdrag"):
            pii.start([text_result("x")], req=pii.request, continuation=cont, run_id="run-c")

    @pytest.mark.parametrize(
        "change, error, message",
        [
            ({"task": "annan"}, RunRequestError, "samma uppdrag"),
            ({"status": "completed"}, RunRequestError, "inte waiting_approval"),
            ({"steps": 12}, RunRequestError, "budget är förbrukad"),
            ({"corrupt": True}, JournalError, "skadad"),
        ],
    )
    def test_fortsattning_provas_mot_forra_journalen(self, pii, change, error, message):
        first, (events, _) = waiting_run(pii)
        pii.trusted.approve(first.result.pending_approvals[0], HUMAN)
        events = json.loads(json.dumps(events))
        if "task" in change:
            events[0]["task_id"] = change["task"]
        if "status" in change:
            events[-1]["status"] = change["status"]
        if "steps" in change:
            events[-1]["root_usage"]["steps"] = change["steps"]
        with pytest.raises(error, match=message):
            prepare_continuation(pii.request, events, pii.trusted, pii.skills, corrupt=change.get("corrupt", False))
