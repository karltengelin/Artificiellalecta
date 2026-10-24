"""Tester för dispatchern och resursmandatet (Fas 3b-3, harness.md §3.1, §5.1, §6.2, §11.1).

Fejkade modellsvar anropar verktyg direkt – även dolda, påhittade och sådana som
pekar på fel person. Beviset är att tjänstelagret aldrig nåddes: inga händelser,
inga förslag i kön och inga anrop till testoperationerna.

PII-verktyg visas bara när tjänstelagret ansluter med teamets begränsade databasroll
(`agent_role`). SQLite har inga roller, så här anges rollen som i drift men med samma
anslutning för båda – databasrättigheterna prövas i tests/test_agents_postgres_role.py.
"""

import json
from datetime import date

import pytest
from pydantic import BaseModel

from agents import (
    CallStatus,
    Dispatcher,
    Ecosystem,
    ExecutionScope,
    HarnessError,
    RunRequest,
    SkillRegistry,
    compile_profile,
    scope_for_person,
)
from ai import ToolCall
from services import (
    AccessRegister,
    MemoryEventLog,
    OperationContext,
    OperationKind,
    OperationRegistry,
    ProductRuleCatalog,
    ServiceLayer,
    default_registry,
    operation,
)
from services.db import AGENT_ROLES

PERSON = "199001011234"  # testbeståndet i conftest
OTHER = "198505055678"
POLICY = "AL-000001"
EMPLOYER = "5560000001"
AFTER_RULES = date(2026, 11, 1)  # PR-ITP1 v1.0 gäller – löneunderlag blir APPROVAL för agenter


def call(name, arguments, call_id=None):
    return ToolCall(id=call_id or f"call-{name}", name=name, arguments=arguments)


def overview(pid=PERSON, call_id=None):
    return call("get_insured_overview", {"data": {"personal_id_number": pid, "policy_number": None},
                                          "reason": None}, call_id)


def salary_report(period="2025-10-01", employer=EMPLOYER):  # 2025-11 och -12 har redan premie
    return call("register_salary_report", {
        "data": {
            "personal_id_number": PERSON, "employer_org_number": employer, "period_month": period,
            "pensionable_salary_sek": "81000", "kind": "new", "corrects_version": None,
            "source": "employer", "source_reference": "lönefil", "received_date": "2025-11-05",
        },
        "reason": "Arbetsgivarens lönefil",
    })


def payload(outcome):
    return json.loads(outcome.result.content)


@pytest.fixture
def harness(insurance_db):
    """Handläggaragenten mot testbeståndet, med ett resursmandat för den försäkrade."""
    events = MemoryEventLog()
    service = ServiceLayer(
        session_factory=insurance_db.session_factory, validation_session_factory=insurance_db.session_factory,
        agent_role="agent_forsakring", events=events, rules=ProductRuleCatalog(today=AFTER_RULES),
    )
    scope = scope_for_person(
        service, ref="scope-1", personal_id_number=PERSON,
        from_month=date(2025, 1, 1), to_month=date(2026, 10, 1), assigned_by="karl",
    )
    events.events.clear()  # scopets egen läsning (systemaktör) räknas inte i testerna
    eco = Ecosystem.load()
    request = RunRequest(task_id="task-1", target_team="forsakring", goal="Kontrollera löneunderlag",
                         execution_scope_ref="scope-1")
    profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), service, request=request)
    dispatcher = Dispatcher(profile, service, run_id="run-1", scope=scope)
    return dispatcher, service, events


class TestResursmandat:
    def test_scopet_byggs_ur_tjanstelagret(self, harness):
        dispatcher, _, _ = harness
        assert dispatcher.scope.persons == {PERSON}
        assert dispatcher.scope.policies == {POLICY}
        assert dispatcher.scope.employers == {EMPLOYER}

    @pytest.mark.parametrize(
        "kwargs, message",
        [
            ({"persons": frozenset({PERSON, OTHER})}, "exakt 1 försäkrad"),
            ({"from_month": date(2024, 1, 1), "to_month": date(2026, 1, 1)}, "högst 24 månader"),
            ({"from_month": date(2025, 1, 15)}, "första dagen i månaden"),
            ({"from_month": date(2026, 2, 1), "to_month": date(2026, 1, 1)}, "före from_month"),
        ],
    )
    def test_ogiltigt_scope(self, kwargs, message):
        base = {"ref": "s", "persons": frozenset({PERSON}), "from_month": date(2025, 1, 1),
                "to_month": date(2025, 12, 1)}
        with pytest.raises(ValueError, match=message):
            ExecutionScope(**{**base, **kwargs})

    def test_scope_maste_vara_uppdragets(self, harness):
        dispatcher, service, _ = harness
        other = dispatcher.scope.model_copy(update={"ref": "scope-2"})
        with pytest.raises(HarnessError, match="stämmer inte med uppdraget"):
            Dispatcher(dispatcher.profile, service, run_id="run-1", scope=other)
        with pytest.raises(HarnessError, match="stämmer inte med uppdraget"):
            Dispatcher(dispatcher.profile, service, run_id="run-1", scope=None)


class TestLasning:
    def test_lasning_inom_scopet_gar_som_agent(self, harness):
        dispatcher, _, events = harness
        (outcome,) = dispatcher.dispatch([overview()]).calls
        assert outcome.status == CallStatus.DONE
        assert payload(outcome)["output"]["personal_id_number"] == PERSON
        (event,) = events.events
        assert (event.actor_type, event.actor_id, event.run_id) == ("agent", "case_handler", "run-1")

    def test_premiehistorik_med_period_inom_scopet(self, harness):
        dispatcher, _, _ = harness
        (outcome,) = dispatcher.dispatch([call("get_premium_history", {
            "data": {"policy_number": POLICY, "from_month": "2025-11-01", "to_month": "2026-01-01"},
            "reason": None,
        })]).calls
        assert outcome.status == CallStatus.DONE

    @pytest.mark.parametrize(
        "arguments, message",
        [
            ({"policy_number": POLICY, "from_month": None, "to_month": None}, "from_month måste anges"),
            ({"policy_number": POLICY, "from_month": "2024-12-01", "to_month": "2025-06-01"},
             "utanför uppdragets period"),
            ({"policy_number": "AL-000002", "from_month": "2025-11-01", "to_month": "2025-12-01"},
             "försäkringen ingår inte"),
        ],
    )
    def test_premiehistorik_utanfor_scopet_nekas(self, harness, arguments, message):
        dispatcher, _, events = harness
        (outcome,) = dispatcher.dispatch([call("get_premium_history", {"data": arguments, "reason": None})]).calls
        assert outcome.status == CallStatus.DENIED and outcome.result.is_error
        assert message in payload(outcome)["message"]
        assert events.events == []

    def test_annan_person_nekas_och_stoppar_hela_gruppen(self, harness):
        dispatcher, _, events = harness
        outcome = dispatcher.dispatch([overview(call_id="c1"), overview(OTHER, call_id="c2")])
        assert [c.status for c in outcome.calls] == [CallStatus.NOT_EXECUTED, CallStatus.DENIED]
        assert "personen ingår inte i uppdraget" in payload(outcome.calls[1])["message"]
        assert [r.call_id for r in outcome.results] == ["c1", "c2"]  # ett svar per call-id
        assert events.events == []  # ingen läsning alls – inte ens den tillåtna


class TestSkrivning:
    def test_forslag_vantar_och_stoppar_resten_av_gruppen(self, harness):
        dispatcher, service, events = harness
        outcome = dispatcher.dispatch([salary_report(), overview()])
        assert [c.status for c in outcome.calls] == [CallStatus.PENDING_APPROVAL, CallStatus.NOT_EXECUTED], (
            outcome.calls[0].result.content
        )
        assert outcome.waiting_approval and outcome.pending_approvals == (outcome.calls[0].approval_id,)
        assert "väntar på handläggarens godkännande" in payload(outcome.calls[1])["message"]
        (pending,) = service.approvals.list("pending")
        assert (pending.operation, pending.proposed_by, pending.run_id) == (
            "register_salary_report", "case_handler", "run-1"
        )
        assert [e.outcome for e in events.events] == ["proposed"]

    def test_annan_arbetsgivare_nekas(self, harness):
        dispatcher, service, _ = harness
        (outcome,) = dispatcher.dispatch([salary_report(employer="5560000099")]).calls
        assert outcome.status == CallStatus.DENIED
        assert "arbetsgivaren ingår inte" in payload(outcome)["message"]
        assert service.approvals.list("pending") == []

    def test_tjanstelagrets_stopp_blir_fel_utan_andring(self, harness):
        dispatcher, service, _ = harness
        # Anställningen slutade 2025-12-31 – löneunderlag för en senare månad stoppas av tjänstelagret
        (outcome,) = dispatcher.dispatch([salary_report(period="2026-03-01")]).calls
        assert outcome.status == CallStatus.ERROR and outcome.result.is_error
        assert service.approvals.list("pending") == []


class TestNekadeAnrop:
    @pytest.mark.parametrize(
        "tool_call, message",
        [
            (call("correct_premium_transaction", {"data": {}, "reason": "x"}), "inte öppen"),
            (call("set_policy_paid_up", {"data": {}, "reason": "x"}), "nekad för agenten"),
            (call("delete_everything", {}), "Okänd skill"),
            (call("get_insured_overview", {"data": {"personal_id_number": PERSON, "policy_number": None},
                                           "reason": None, "actor": "human"}), "okända fält actor"),
        ],
    )
    def test_dolt_paahittat_eller_falsk_identitet_nar_aldrig_tjanstelagret(self, harness, tool_call, message):
        dispatcher, service, events = harness
        (outcome,) = dispatcher.dispatch([tool_call]).calls
        assert outcome.status == CallStatus.DENIED
        assert message in payload(outcome)["message"]
        assert events.events == [] and service.approvals.list("pending") == []

    def test_dubbelt_call_id_nekas(self, harness):
        dispatcher, _, events = harness
        outcome = dispatcher.dispatch([overview(call_id="same"), overview(call_id="same")])
        assert outcome.denied and events.events == []


class TestUtanPersonuppgifter:
    def test_premieforhandsberakning_utan_uppdrag_och_scope(self, insurance_db):
        eco = Ecosystem.load()
        service = ServiceLayer(session_factory=insurance_db.session_factory, events=MemoryEventLog())
        profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), service, agent_id="case_handler")
        dispatcher = Dispatcher(profile, service, run_id="run-3")
        (outcome,) = dispatcher.dispatch([call("calculate_premium_preview", {
            "data": {"monthly_salary_sek": "80000", "period_month": "2026-03-01", "birth_date": None},
            "reason": None,
        })]).calls
        assert outcome.status == CallStatus.DONE
        assert payload(outcome)["output"]["total_premium_sek"] == "10708.13"

    def test_pii_verktyg_ar_dolda_utan_databasroll(self, insurance_db):
        eco = Ecosystem.load()
        service = ServiceLayer(session_factory=insurance_db.session_factory, events=MemoryEventLog())
        request = RunRequest(task_id="t", target_team="forsakring", goal="g", execution_scope_ref="scope-1")
        profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), service, request=request)
        scope = ExecutionScope(ref="scope-1", persons=frozenset({PERSON}), policies=frozenset({POLICY}),
                               from_month=date(2025, 1, 1), to_month=date(2025, 12, 1))
        (outcome,) = Dispatcher(profile, service, run_id="r", scope=scope).dispatch([overview()]).calls
        assert outcome.status == CallStatus.DENIED
        assert "databasroll" in payload(outcome)["message"]


# --- fejkade operationer: läckande resultat och policyändring mitt i körningen ------------


class Ref(BaseModel):
    personal_id_number: str


class Leaky(BaseModel):
    personal_id_number: str
    related: list[dict]


fake_registry = OperationRegistry()


@operation(name="leaky_lookup", description="Läser och råkar ta med en annan person",
           kind=OperationKind.READ, pii=True, registry=fake_registry)
def leaky_lookup(ctx: OperationContext, data: Ref) -> Leaky:
    return Leaky(personal_id_number=data.personal_id_number, related=[{"personal_id_number": OTHER}])


@operation(name="plain_lookup", description="Läser", kind=OperationKind.READ, pii=True, registry=fake_registry)
def plain_lookup(ctx: OperationContext, data: Ref) -> Leaky:
    return Leaky(personal_id_number=data.personal_id_number, related=[])


FAKE_POLICY = {
    "schema_version": 1, "policy_id": "test", "team_ids": ["t1"],
    "defaults": {"allowed_effects": ["read"], "limits": {
        "max_steps": 5, "max_tool_calls": 5, "max_cost_usd": 1.0, "max_output_tokens": 100,
        "max_context_bytes": 1000, "max_wall_seconds": 10}},
    "pods": {"p": {"owner_team": "t1", "mountable_by": ["t1"], "pii": True, "allowed_effects": ["read"],
                   "skills": {"leaky_lookup": {"service_operation": "leaky_lookup"},
                              "plain_lookup": {"service_operation": "plain_lookup"}}}},
    "teams": {"t1": {"lead": "a", "mandate": "m", "pods": ["p"], "allowed_effects": ["read"]}},
    "agents": {"a": {"name": "A", "team": "t1", "instruction": "02_system/agenter/handlaggaragent.md",
                     "model_role": "standard", "pods": ["p"], "allowed_effects": ["read"]}},
    "delegation": {"max_depth": 1, "max_children": 0, "root_limits": {
        "max_steps": 5, "max_tool_calls": 5, "max_cost_usd": 1.0, "max_wall_seconds": 10}},
}


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setitem(AGENT_ROLES, "t1", ("agent_t1", "AGENT_T1_DATABASE_URL"))
    eco = Ecosystem.from_dict(FAKE_POLICY)
    service = ServiceLayer(registry=fake_registry, events=MemoryEventLog(),
                           register=AccessRegister.from_dict({"leaky_lookup": "AGENT", "plain_lookup": "AGENT"}))
    service.agent_role = "agent_t1"  # ingen databas här; i drift sätts rollen av agent_service_layer
    request = RunRequest(task_id="t", target_team="t1", goal="g", execution_scope_ref="s")
    profile = compile_profile(eco, SkillRegistry.build(eco, fake_registry), service, request=request)
    scope = ExecutionScope(ref="s", persons=frozenset({PERSON}), from_month=date(2025, 1, 1),
                           to_month=date(2025, 12, 1))
    return Dispatcher(profile, service, run_id="r", scope=scope), service


def test_resultat_med_annan_person_lamnas_inte_ut(fake):
    dispatcher, _ = fake
    (outcome,) = dispatcher.dispatch([call("leaky_lookup", {"data": {"personal_id_number": PERSON},
                                                            "reason": None})]).calls
    assert outcome.status == CallStatus.WITHHELD and outcome.result.is_error
    assert OTHER not in outcome.result.content


def test_indragen_atkomst_galler_direkt_aven_for_visat_verktyg(fake):
    dispatcher, service = fake
    service.register = AccessRegister.from_dict({"leaky_lookup": "AGENT", "plain_lookup": "HUMAN_ONLY"})
    (outcome,) = dispatcher.dispatch([call("plain_lookup", {"data": {"personal_id_number": PERSON},
                                                            "reason": None})]).calls
    assert outcome.status == CallStatus.DENIED
    assert "ändrats under körningen" in payload(outcome)["message"]
    assert service.events.events == []
