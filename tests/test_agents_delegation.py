"""Delegering mellan team (Fas 3c 3c-1, B-039, harness.md §10.1–10.2).

Första aktiva paret compliance → aktuarie med FakeProvider, utan nätverk, mot demobeståndet
i minnet: synlighet i profilen, barnets egen identitet och tjänstelager, gemensam rotbudget,
idempotens, nekanden, spridd status och journalen.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from agents import (
    CallStatus,
    Ecosystem,
    EcosystemConfigError,
    HarnessError,
    MemoryJournal,
    RunRequest,
    RunRequestError,
    RunStatus,
    SkillRegistry,
    compile_profile,
    run_agent,
)
from agents.delegation import DelegationRuntime
from agents.ecosystem import DEFAULT_ECOSYSTEM_PATH
from agents.gateways import DraftGateway, Gateways, RegulatoryGateway
from agents.profile import PII_DELEGATION_REASON
from ai import AIClient, AIConfig
from ai.providers.fake import FakeProvider, text_result, tool_call_result
from ai.tracing import MemoryTraceSink
from services import MemoryEventLog, ServiceLayer, default_registry
from services.db import session_factory_for
from services.operations import common
from services.rules import ProductRuleCatalog
from utils.demo_data import create_demo_database

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 10, 27)
DELEGATE = "delegate_to_team"


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


@pytest.fixture(scope="module")
def eco():
    return Ecosystem.load()


@pytest.fixture(scope="module")
def skills(eco):
    return SkillRegistry.build(eco, default_registry)


@pytest.fixture
def gateways(tmp_path):
    return Gateways(regulatory=RegulatoryGateway(), drafts=DraftGateway(tmp_path / "utkast"))


def policy_dict() -> dict:
    return yaml.safe_load(DEFAULT_ECOSYSTEM_PATH.read_text(encoding="utf-8"))


class Recording(ServiceLayer):
    """Tjänstelager som minns vilka operationer som kördes genom det."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls: list[tuple[str, str]] = []

    def execute(self, name, ctx, data):
        self.calls.append((name, ctx.actor.id))
        return super().execute(name, ctx, data)


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False)
    yield engine
    engine.dispose()


@pytest.fixture
def services(engine):
    db = session_factory_for(engine)
    rules = ProductRuleCatalog(today=TODAY)
    compliance = Recording(session_factory=db, validation_session_factory=db, events=MemoryEventLog(), rules=rules,
                            agent_role="agent_compliance")
    actuary = Recording(session_factory=db, validation_session_factory=db, events=MemoryEventLog(), rules=rules,
                        agent_role="agent_aktuarie")
    return compliance, actuary


def ai_client(fake) -> AIClient:
    config = AIConfig.from_dict({
        "providers": {"alpha": {"type": "fake", "api_key_env": "ALPHA_KEY"}},
        "models": {"alpha:big": {"price": {"input": 10.0, "output": 20.0},
                                 "capabilities": {"tools": True, "structured_output": True}}},
        "roles": {"deep": {"model": "alpha:big"}, "standard": {"model": "alpha:big"}},
    })
    return AIClient(config, sink=MemoryTraceSink(), provider_overrides={"alpha": fake}, environ={})


def order(**overrides) -> dict:
    data = {
        "target_team": "aktuarie",
        "goal": "Bedöm om en höjd premieålder stämmer med den aktuariella grunden",
        "background": "Compliance tolkar en fiktiv källa; ingen regel är ändrad",
        "constraints": ["Bara gällande parametrar"],
        "expected_output": "Kort aktuariellt utlåtande",
        "result_schema": None,
        "references": ["K-SIM-ITP-2027", "PR-ITP1-016"],
    }
    data.update(overrides)
    return {"data": data, "reason": "Behöver aktuariens bedömning"}


def delegate(call_id: str = "c1", **overrides):
    return tool_call_result(DELEGATE, order(**overrides), call_id=call_id)


def parent_request(**overrides) -> RunRequest:
    return RunRequest(**{"task_id": "task-1", "target_team": "compliance", "goal": "Tolka källan",
                         "delegation_targets": ("aktuarie",), **overrides})


class Run:
    """En föräldrakörning med journaler i minnet för föräldern och varje barn."""

    def __init__(self, ai, eco, skills, services, gateways, *, request=None, eco_for_runtime=None,
                 child_journal=None):
        compliance, actuary = services
        self.children: dict[str, MemoryJournal] = {}

        def factory(**kwargs):
            journal = MemoryJournal(**kwargs)
            self.children[kwargs["run_id"]] = journal
            return journal

        runtime_eco = eco_for_runtime or eco
        runtime_skills = skills if eco_for_runtime is None else SkillRegistry.build(runtime_eco, default_registry)
        self.runtime = DelegationRuntime(
            ai, runtime_eco, runtime_skills, compliance, team_services={"aktuarie": actuary},
            gateways=gateways, journal_factory=child_journal or factory,
        )
        self.request = request or parent_request()
        self.profile = compile_profile(runtime_eco, runtime_skills, compliance, request=self.request)
        self.journal = MemoryJournal(run_id="run-1", team="compliance", agent="compliance_agent")
        self.outcome = run_agent(ai, self.profile, compliance, self.request, gateways=gateways, run_id="run-1",
                                 journal=self.journal, delegation=self.runtime)

    def events(self, type: str) -> list[dict]:
        return [e for e in self.journal.events if e["type"] == type]

    def call(self, index: int = 0):
        return [c for d in self.outcome.dispatches for c in d.calls][index]


def modified(change) -> Ecosystem:
    data = policy_dict()
    change(data)
    return Ecosystem.from_dict(data)


# --- körpolicy och profil -----------------------------------------------------------------------


class TestProfil:
    def test_verktyget_visas_bara_med_delegeringsmal_i_uppdraget(self, eco, skills, services):
        compliance, _ = services
        without = compile_profile(eco, skills, compliance, request=parent_request(delegation_targets=()))
        assert not without.decision(DELEGATE).visible
        assert "delegation_targets" in " ".join(without.decision(DELEGATE).reasons)
        with_targets = compile_profile(eco, skills, compliance, request=parent_request())
        assert with_targets.decision(DELEGATE).visible
        assert with_targets.delegation_targets == ("aktuarie",)
        assert DELEGATE in {t.name for t in with_targets.tool_specs()}

    def test_profil_utan_uppdrag_visar_inte_verktyget(self, eco, skills, services):
        profile = compile_profile(eco, skills, services[0], agent_id="compliance_agent")
        assert not profile.decision(DELEGATE).visible and profile.delegation_targets == ()

    def test_aktuarien_och_handlaggaren_har_inte_verktyget(self, eco, skills, services):
        for team in ("aktuarie", "forsakring"):
            profile = compile_profile(eco, skills, services[1], request=RunRequest(task_id="t", target_team=team, goal="x"))
            assert not profile.decision(DELEGATE).visible

    def test_mal_utanfor_agentens_delegates_to_ar_ett_fel_i_betrodd_kod(self, eco, skills, services):
        with pytest.raises(RunRequestError, match="delegeringsmål"):
            compile_profile(eco, skills, services[0], request=parent_request(delegation_targets=("forsakring",)))

    def test_avstangd_delegering_doljer_verktyget(self, skills, services):
        eco = modified(lambda d: d["delegation"].update(enabled=False))
        profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), services[0], request=parent_request())
        assert not profile.decision(DELEGATE).visible
        assert "avstängd" in " ".join(profile.decision(DELEGATE).reasons)

    def test_mal_utan_aktiv_profil_ger_inget_verktyg(self, services):
        def change(d):
            d["pods"]["delegering"]["mountable_by"] = ["compliance", "forsakring"]
            d["teams"]["forsakring"]["pods"].append("delegering")
            d["agents"]["case_handler"]["pods"].append("delegering")

        eco = modified(change)
        profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), services[0], request=RunRequest(
            task_id="t", target_team="forsakring", goal="x", delegation_targets=("kommunikation",)))
        assert not profile.decision(DELEGATE).visible and profile.delegation_targets == ()

    def test_korning_med_personuppgifter_far_inte_delegera(self, engine):
        def change(d):
            d["pods"]["delegering"]["mountable_by"] = ["compliance", "forsakring"]
            d["teams"]["forsakring"]["pods"].append("delegering")
            d["teams"]["forsakring"]["delegates_to"] = ["kommunikation", "compliance"]
            d["agents"]["case_handler"]["pods"].append("delegering")
            d["agents"]["case_handler"]["delegates_to"] = ["kommunikation", "compliance"]

        eco = modified(change)
        db = session_factory_for(engine)
        service = ServiceLayer(session_factory=db, validation_session_factory=db, events=MemoryEventLog(),
                               rules=ProductRuleCatalog(today=TODAY), agent_role="agent_forsakring")
        profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), service, request=RunRequest(
            task_id="t", target_team="forsakring", goal="x", execution_scope_ref="scope-1",
            delegation_targets=("compliance",)))
        assert any(d.visible and d.pii for d in profile.decisions)
        assert PII_DELEGATION_REASON in profile.decision(DELEGATE).reasons
        assert profile.delegation_targets == ()

    def test_okant_harnessverktyg_och_pii_podd_stoppar_policyn(self):
        with pytest.raises(EcosystemConfigError, match="harnessverktyget 'hoppa' finns inte"):
            modified(lambda d: d["pods"]["delegering"]["skills"]["delegate_to_team"].update(harness_tool="hoppa"))
        with pytest.raises(EcosystemConfigError, match="podd utan PII"):
            modified(lambda d: d["pods"]["delegering"].update(pii=True))

    def test_uppdrag_med_mal_kraver_delegationruntime(self, eco, skills, services):
        compliance, _ = services
        profile = compile_profile(eco, skills, compliance, request=parent_request())
        with pytest.raises(HarnessError, match="DelegationRuntime"):
            run_agent(ai_client(FakeProvider([])), profile, compliance, parent_request())


# --- lyckad delegering -------------------------------------------------------------------------------


class TestLyckadDelegering:
    def test_barnet_kor_som_aktuarien_med_eget_tjanstelager(self, eco, skills, services, gateways):
        fake = FakeProvider([
            delegate(),
            tool_call_result("get_product_parameters", {"data": {"on_date": "2026-10-27"}, "reason": None},
                             call_id="a1"),
            text_result("Tolkningen stämmer med den aktuariella grunden."),
            text_result("Klart, med aktuariens bedömning."),
        ])
        run = Run(ai_client(fake), eco, skills, services, gateways)
        compliance, actuary = services

        assert run.outcome.result.status == RunStatus.COMPLETED
        assert actuary.calls == [("get_product_parameters", "actuary_agent")]
        assert compliance.calls == []
        # Barnet fick aktuariens instruktion och verktyg – utan delegering och utan beståndsinsikt
        child_request = fake.requests[1]
        tools = {t.name for t in child_request.tools}
        assert "Aktuarieagent" in child_request.system and DELEGATE not in tools
        assert "estimate_parameter_change_impact" not in tools
        assert "Uppdraget är beställt av teamet compliance" in child_request.messages[0].text

        result = run.call().result
        assert run.call().status == CallStatus.DONE and not result.is_error
        assert "Tolkningen stämmer" in result.content and '"team": "aktuarie"' in result.content

    def test_journalen_binder_barn_och_forlader(self, eco, skills, services, gateways):
        fake = FakeProvider([delegate(), text_result("Bedömning."), text_result("Klart.")])
        run = Run(ai_client(fake), eco, skills, services, gateways)

        assert [e["type"] for e in run.journal.events if e["type"].startswith("delegation")] == [
            "delegation_requested", "delegation_started", "delegation_returned"]
        started = run.events("delegation_started")[0]
        (child_id, child), = run.children.items()
        assert started["child_run_id"] == child_id and started["depth"] == 1
        first = child.events[0]
        assert first["type"] == "run_started" and first["parent_run_id"] == "run-1" and first["root_run_id"] == "run-1"
        assert first["depth"] == 1 and first["task_id"] == "del-run-1-c1"
        # Barnets tak är aktuariens, inom rotbudgeten
        assert first["limits"]["max_cost_usd"] == eco.agent_limits("actuary_agent").max_cost_usd
        assert run.events("run_started")[0]["delegation_targets"] == ["aktuarie"]
        # Fri text bara som hash
        assert "goal" in run.events("delegation_requested")[0]
        assert "Bedöm" not in str(run.events("delegation_requested")[0])
        ended = run.events("run_ended")[0]
        assert ended["delegation"]["children"] == 1
        assert ended["delegation"]["root_usage"]["steps"] == 3

    def test_samma_bestallning_igen_ger_samma_svar_utan_ny_korning(self, eco, skills, services, gateways):
        fake = FakeProvider([delegate("c1"), text_result("Bedömning."), delegate("c2"), text_result("Klart.")])
        run = Run(ai_client(fake), eco, skills, services, gateways)

        assert run.outcome.result.status == RunStatus.COMPLETED
        assert len(run.children) == 1 and len(fake.requests) == 4
        returned = run.events("delegation_returned")
        assert [e["reused"] for e in returned] == [False, True]
        assert run.call(0).result.content == run.call(1).result.content


# --- nekanden och gränser -----------------------------------------------------------------------------


class TestNekanden:
    @pytest.mark.parametrize("overrides, text", [
        ({"target_team": "forsakring"}, "inte ett tillåtet delegeringsmål"),
        ({"goal": "Kolla kunden 19920417-1236"}, "personnummer"),
        ({"references": ["../hemligt"]}, "Ogiltiga referenser"),
    ])
    def test_sakerhetsnej_blockerar_foraldern_utan_barn(self, eco, skills, services, gateways, overrides, text):
        fake = FakeProvider([delegate(**overrides)])
        run = Run(ai_client(fake), eco, skills, services, gateways)

        assert run.outcome.result.status == RunStatus.BLOCKED
        assert run.call().status == CallStatus.DENIED and text in run.call().result.content
        assert run.children == {} and len(fake.requests) == 1
        assert run.events("delegation_denied")[0]["security"] is True

    def test_okant_resultatschema_ar_ett_vanligt_fel(self, eco, skills, services, gateways):
        fake = FakeProvider([delegate(result_schema="Hittepa"), text_result("Klart utan aktuarien.")])
        run = Run(ai_client(fake), eco, skills, services, gateways)

        assert run.outcome.result.status == RunStatus.COMPLETED
        assert run.call().status == CallStatus.ERROR and "Okänt resultatschema" in run.call().result.content
        assert run.children == {}

    def test_djupgransen(self, eco, skills, services, gateways):
        fake = FakeProvider([delegate()])
        run = Run(ai_client(fake), eco, skills, services, gateways, request=parent_request(depth=2))
        assert run.outcome.result.status == RunStatus.BLOCKED and "Djupgränsen" in run.call().result.content

    def test_hogst_antal_barn_per_rot(self, eco, skills, services, gateways):
        limited = modified(lambda d: d["delegation"].update(max_children=1))
        fake = FakeProvider([delegate("c1"), text_result("Första."),
                             delegate("c2", goal="Ett annat uppdrag"), text_result("Klart.")])
        run = Run(ai_client(fake), eco, skills, services, gateways, eco_for_runtime=limited)

        assert run.outcome.result.status == RunStatus.COMPLETED
        assert run.call(1).status == CallStatus.ERROR and "Högst 1" in run.call(1).result.content
        assert len(run.children) == 1

    def test_rotbudgeten_begransar_barnet_och_stoppar_foraldern(self, eco, skills, services, gateways):
        small = modified(lambda d: d["delegation"]["root_limits"].update(max_steps=2))
        fake = FakeProvider([delegate(), text_result("Bedömning."), text_result("Kommer aldrig.")])
        run = Run(ai_client(fake), eco, skills, services, gateways, eco_for_runtime=small)

        (child,) = run.children.values()
        assert child.events[0]["limits"]["max_steps"] == 1
        assert run.outcome.result.status == RunStatus.LIMIT_REACHED
        assert "rotbudgeten" in run.outcome.result.summary
        assert len(fake.requests) == 2


# --- barnets status --------------------------------------------------------------------------------------


class TestBarnetsStatus:
    def test_barn_som_behover_manniska_stoppar_foraldern(self, eco, skills, services, gateways):
        refusal = replace(text_result("Jag kan inte"), stop_reason="refusal")
        fake = FakeProvider([delegate(), refusal])
        run = Run(ai_client(fake), eco, skills, services, gateways)

        assert run.outcome.result.status == RunStatus.NEEDS_HUMAN
        assert "delegerat uppdrag" in run.outcome.result.summary
        assert run.call().status == CallStatus.DELEGATION_STOPPED
        assert len(fake.requests) == 2  # inget fler modellanrop i föräldern

    def test_barn_som_misslyckas_blir_ett_fel_foraldern_kan_hantera(self, eco, skills, services, gateways):
        cut = replace(text_result("halvt"), stop_reason="max_tokens")
        fake = FakeProvider([delegate(), cut, text_result("Klart utan aktuarien.")])
        run = Run(ai_client(fake), eco, skills, services, gateways)

        assert run.outcome.result.status == RunStatus.COMPLETED
        assert run.call().status == CallStatus.ERROR and run.call().error_type == "Delegation:failed"

    def test_ovantat_fel_i_barnet_kraver_avstamning(self, eco, skills, services, gateways):
        def broken(**kwargs):
            raise RuntimeError("journalen gick sönder")

        fake = FakeProvider([delegate()])
        run = Run(ai_client(fake), eco, skills, services, gateways, child_journal=broken)

        assert run.outcome.result.status == RunStatus.RECONCILIATION_REQUIRED
        returned = run.events("delegation_returned")[0]
        assert returned["status"] == "reconciliation_required"
        # Okänd förbrukning räknas inte som noll – hela reservationen står kvar
        assert returned["usage"]["cost_usd"] == eco.agent_limits("actuary_agent").max_cost_usd
