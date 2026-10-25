"""Flödesmotorn (Fas 3c 3c-2, B-035, flaggskeppsflöde.md §6, databasschema.md §9i).

Ett testflöde i flaggskeppets form – tolkning, grind, insikt, grind, manuellt steg,
aktivering via godkännandekön och verifiering – körs mot demobeståndet i minnet med
FakeProvider. Därtill låsning på flödets version, grindar bundna till underlagets hash,
avslag, avbrott, avstämning efter avbrutna steg och tabellernas villkor.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from agents import (
    Ecosystem,
    HarnessError,
    SkillRegistry,
    mandate_from_interpretation,
    request_for_impact,
    request_for_interpretation,
)
from agents.flows import (
    AgentRuntime,
    AgentStep,
    FlowConflictError,
    FlowDefinition,
    FlowEngine,
    FlowError,
    GateStep,

    ManualStep,
    SystemOutcome,
    SystemStep,
)
from agents.flows.store import bump, load
from agents.gateways import DraftGateway, Gateways, RegulatoryGateway
from ai import AIClient, AIConfig
from ai.providers.fake import FakeProvider, text_result, tool_call_result
from ai.tracing import MemoryTraceSink
from models import Flow, FlowGateDecision, FlowStep
from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer, default_registry
from services.db import session_factory_for
from services.operations import common
from utils.demo_data import create_demo_database

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 11, 15)  # PR-ITP1 v1.0 gäller – compliance-agenten får föreslå parameterändringen
OPERATOR = Actor.human("karl")
SOURCE = "K-SIM-ITP-2027"


# --- testflödet ----------------------------------------------------------------------------------


class FlowInput(BaseModel):
    source_handle: str = Field(min_length=1)


class RuleTextDone(BaseModel):
    commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    note: str | None = None


def mandate(ctx):
    return mandate_from_interpretation(ctx.result("tolkning")["output"], ref=f"pc-{ctx.flow_id}")


def activate(ctx, trusted: ServiceLayer) -> SystemOutcome:
    """Förslaget läggs under compliance-agentens identitet, länkat till tolkningens körning (val C)."""
    change = ctx.result("tolkning")["output"]["result"]["parameter_changes"][0]
    data = {"key": change["key"], "value": change["new_value"], "valid_from": change["valid_from"],
            "rule_version": "1.1", "source_ref": ctx.input["source_handle"], "decision_ref": f"{ctx.flow_id} G2"}
    agent = OperationContext(actor=Actor.agent("compliance_agent", team="compliance"),
                             reason=f"Godkänd regeländring i {ctx.flow_id}", run_id=ctx.run_ids["tolkning"])
    result = trusted.execute("schedule_product_parameter_change", agent, data)
    return SystemOutcome(result={"operation": "schedule_product_parameter_change", "input": data},
                         approval_id=result.approval_id)


def verify(ctx, trusted: ServiceLayer) -> SystemOutcome:
    system = OperationContext(actor=Actor.system("flow_engine"))
    before = trusted.execute("get_product_parameters", system, {"on_date": "2026-12-01"}).output
    after = trusted.execute("get_product_parameters", system, {"on_date": "2027-01-01"}).output
    return SystemOutcome(result={"before": str(before.effective["premium_age_end"]),
                                 "after": str(after.effective["premium_age_end"])})


DEFINITION = FlowDefinition(
    flow_type="test_rule_change", version="1", title="Testflöde", input_model=FlowInput,
    steps=(
        AgentStep("tolkning", "Tolkning", "compliance", lambda ctx: request_for_interpretation(ctx.input["source_handle"])),
        GateStep("g1", "Godkänn tolkningen", binds=("tolkning",)),
        AgentStep("insikt", "Beståndsinsikt", "aktuarie", lambda ctx: request_for_impact(mandate(ctx)), mandate=mandate),
        GateStep("g2", "Anta regeländringen", binds=("tolkning", "insikt")),
        ManualStep("regeltext", "För in regeltexten", RuleTextDone),
        SystemStep("aktivering", "Schemalägg parametern", activate),
        SystemStep("verifiering", "Verifiera", verify),
    ),
)


def action(data: dict, reason: str | None = None) -> dict:
    return {"data": data, "reason": reason}


INTERPRETATION = json.dumps({
    "summary": "Premieåldern höjs från 66 till 67 år från 2027-01-01 (fiktiv källa).",
    "affected_rules": ["PR-ITP1-013", "PR-ITP1-016"],
    "parameter_changes": [{"key": "premium_age_end", "current_value": "66", "new_value": "67",
                           "valid_from": "2027-01-01", "rule_id": "PR-ITP1-013", "rationale": "Källan."}],
    "customer_impact": "Ett år till med premie.", "uncertainties": [], "source_handles": [SOURCE],
    "draft_names": ["konsekvensanalys.md"],
}, ensure_ascii=False)
COMPLIANCE = [
    tool_call_result("read_regulatory_document", action({"handle": SOURCE, "section": None, "offset": 0})),
    tool_call_result("write_draft", action({"name": "konsekvensanalys.md", "title": "Konsekvensanalys",
                                             "content": "# Konsekvensanalys"}, "Utkast"), call_id="call_2"),
    text_result(INTERPRETATION),
]
IMPACT = [
    tool_call_result("estimate_parameter_change_impact",
                     action({"key": "premium_age_end", "value": "67", "valid_from": "2027-01-01", "horizon_years": 10})),
    text_result(json.dumps({"insight": "Berörda redan 2027.", "key_findings": [], "uncertainties": [],
                            "source_handles": [], "draft_names": []})),
]


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


@pytest.fixture
def setup(tmp_path):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False)
    factory = session_factory_for(engine)
    service = ServiceLayer(session_factory=factory, rules=ProductRuleCatalog(today=TODAY))
    fake = FakeProvider()
    config = AIConfig.from_dict({
        "providers": {"alpha": {"type": "fake", "api_key_env": "ALPHA_KEY"}},
        "models": {"alpha:big": {"price": {"input": 10.0, "output": 20.0},
                                 "capabilities": {"tools": True, "structured_output": True}}},
        "roles": {"deep": {"model": "alpha:big"}, "standard": {"model": "alpha:big"}},
    })
    ai = AIClient(config, sink=MemoryTraceSink(), provider_overrides={"alpha": fake}, environ={})
    eco = Ecosystem.load()
    runtime = AgentRuntime(
        ai=ai, ecosystem=eco, skills=SkillRegistry.build(eco, default_registry), service=service,
        gateways=Gateways(regulatory=RegulatoryGateway(), drafts=DraftGateway(tmp_path / "utkast")),
        journal_dir=tmp_path / "runs",
    )
    flows = FlowEngine(factory, [DEFINITION], runtime=runtime, trusted=service)
    yield flows, fake, service, factory, tmp_path
    engine.dispose()


def through_g1(flows, fake):
    flow = flows.start("test_rule_change", {"source_handle": SOURCE}, actor=OPERATOR)
    fake.queue(*COMPLIANCE)
    flow = flows.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)
    return flows.decide_gate(flow.flow_id, expected_version=flow.version, actor=OPERATOR, decision="approved",
                             seen_hash=flow.gate_hashes["g1"])


# --- hela flödet ------------------------------------------------------------------------------------


class TestHelaFlodet:
    def test_fran_kalla_till_verifierad_parameter(self, setup):
        flows, fake, service, factory, tmp_path = setup
        flow = flows.start("test_rule_change", {"source_handle": SOURCE}, actor=OPERATOR)
        assert (flow.flow_id, flow.status, flow.current_step, flow.version) == ("FLOW-000001", "running", "tolkning", 1)

        fake.queue(*COMPLIANCE)
        flow = flows.run_next(flow.flow_id, expected_version=1, actor=OPERATOR)
        step = flow.step("tolkning")
        assert (flow.status, flow.current_step, step.status, step.agent) == (
            "waiting_gate", "g1", "completed", "compliance_agent")
        assert step.result["output"]["schema"] == "InterpretationProposal" and step.result_hash
        assert step.artifact_refs == (f"utkast:compliance/{step.run_id}/konsekvensanalys.md",)
        # körjournalen länkar flödet och steget
        journal = (tmp_path / "runs" / f"{step.run_id}.jsonl").read_text(encoding="utf-8").splitlines()
        started = json.loads(journal[0])
        assert (started["flow_id"], started["flow_step_id"]) == ("FLOW-000001", str(started["flow_step_id"]))

        flow = flows.decide_gate(flow.flow_id, expected_version=flow.version, actor=OPERATOR, decision="approved",
                                 seen_hash=flow.gate_hashes["g1"], note="Tolkningen stämmer")
        assert (flow.status, flow.current_step) == ("running", "insikt")

        fake.queue(*IMPACT)
        flow = flows.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)
        estimate = flow.step("insikt").result["output"]["evidence"]["estimate"]
        assert estimate["first_affected_year"] == 2027
        assert flow.status == "waiting_gate"

        flow = flows.decide_gate(flow.flow_id, expected_version=flow.version, actor=OPERATOR, decision="approved",
                                 seen_hash=flow.gate_hashes["g2"])
        assert flow.status == "waiting_manual"
        flow = flows.complete_manual(flow.flow_id, expected_version=flow.version, actor=OPERATOR,
                                     data={"commit": "a1b2c3d", "note": "PR-013 v1.1"})
        assert (flow.status, flow.step("regeltext").completed_by) == ("running", "karl")

        flow = flows.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)
        approval_id = flow.step("aktivering").approval_id
        assert (flow.status, flow.step("aktivering").status) == ("waiting_approval", "waiting") and approval_id
        with pytest.raises(FlowError, match="väntar på godkännande"):
            flows.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)
        # Grinden ersätter inte kön: operatören godkänner förslaget i tjänstelagret
        service.approve(approval_id, OperationContext(actor=OPERATOR))
        flow = flows.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)
        assert flow.step("aktivering").result["approval"]["status"] == "approved"
        assert flow.step("aktivering").completed_by == "karl"

        flow = flows.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)
        assert flow.status == "completed" and flow.finished
        assert flow.step("verifiering").result == {"before": "66", "after": "67"}
        assert [(d.step_key, d.decision, d.decided_by) for d in flow.decisions] == [
            ("g1", "approved", "karl"), ("g2", "approved", "karl")]
        assert flow.decisions[1].bound_steps == ("tolkning", "insikt")
        assert flow.stale_gates == ()

    def test_flodesnummer_i_foljd(self, setup):
        flows = setup[0]
        ids = [flows.start("test_rule_change", {"source_handle": SOURCE}, actor=OPERATOR).flow_id for _ in range(2)]
        assert ids == ["FLOW-000001", "FLOW-000002"]
        assert [f.flow_id for f in flows.list()] == ["FLOW-000002", "FLOW-000001"]


# --- låsning -------------------------------------------------------------------------------------


class TestLasning:
    def test_samma_steg_tas_inte_tva_ganger(self, setup):
        flows, fake = setup[0], setup[1]
        flow = flows.start("test_rule_change", {"source_handle": SOURCE}, actor=OPERATOR)
        fake.queue(*COMPLIANCE)
        flows.run_next(flow.flow_id, expected_version=1, actor=OPERATOR)
        with pytest.raises(FlowConflictError, match="version"):
            flows.run_next(flow.flow_id, expected_version=1, actor=OPERATOR)  # andra klicket
        assert len(fake.requests) == 3  # ingen ny modellkörning

    def test_villkorlig_uppdatering_ger_konflikt_vid_samtidig_andring(self, setup):
        factory = setup[3]
        flow = setup[0].start("test_rule_change", {"source_handle": SOURCE}, actor=OPERATOR)
        with factory() as first:
            row, _, _ = load(first, flow.flow_id)
            with factory() as second:
                bump(second, load(second, flow.flow_id)[0], 1)
            with pytest.raises(FlowConflictError):
                bump(first, row, 1)

    def test_agent_tar_inga_steg_och_startar_inga_floden(self, setup):
        flows = setup[0]
        agent = Actor.agent("compliance_agent", team="compliance")
        with pytest.raises(FlowError, match="inte av en agent"):
            flows.start("test_rule_change", {"source_handle": SOURCE}, actor=agent)
        flow = flows.start("test_rule_change", {"source_handle": SOURCE}, actor=OPERATOR)
        with pytest.raises(FlowError, match="inte av en agent"):
            flows.run_next(flow.flow_id, expected_version=1, actor=agent)


# --- grindar ---------------------------------------------------------------------------------------


class TestGrindar:
    def test_beslutet_binder_underlaget_operatoren_sag(self, setup):
        flows, fake = setup[0], setup[1]
        flow = flows.start("test_rule_change", {"source_handle": SOURCE}, actor=OPERATOR)
        fake.queue(*COMPLIANCE)
        flow = flows.run_next(flow.flow_id, expected_version=1, actor=OPERATOR)
        with pytest.raises(FlowConflictError, match="har ändrats sedan det visades"):
            flows.decide_gate(flow.flow_id, expected_version=flow.version, actor=OPERATOR, decision="approved",
                              seen_hash="0" * 64)
        with pytest.raises(FlowError, match="människa"):
            flows.decide_gate(flow.flow_id, expected_version=flow.version, actor=Actor.system("x"),
                              decision="approved", seen_hash=flow.gate_hashes["g1"])
        with pytest.raises(FlowError, match="anteckning"):
            flows.decide_gate(flow.flow_id, expected_version=flow.version, actor=OPERATOR, decision="rejected",
                              seen_hash=flow.gate_hashes["g1"])

    def test_avslag_stoppar_flodet(self, setup):
        flows, fake = setup[0], setup[1]
        flow = flows.start("test_rule_change", {"source_handle": SOURCE}, actor=OPERATOR)
        fake.queue(*COMPLIANCE)
        flow = flows.run_next(flow.flow_id, expected_version=1, actor=OPERATOR)
        flow = flows.decide_gate(flow.flow_id, expected_version=flow.version, actor=OPERATOR, decision="rejected",
                                 seen_hash=flow.gate_hashes["g1"], note="Fel tolkning av PR-016")
        assert (flow.status, flow.step("g1").status, flow.finished) == ("rejected", "rejected", True)
        assert flow.decisions[0].note == "Fel tolkning av PR-016"
        with pytest.raises(FlowError, match="rejected"):
            flows.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)

    def test_andrat_underlag_efter_beslutet_stoppar_flodet(self, setup):
        flows, fake, _, factory, _ = setup
        flow = through_g1(flows, fake)
        with factory() as s:
            s.execute(update(FlowStep).where(FlowStep.flow_id == flow.flow_id, FlowStep.step_key == "tolkning")
                      .values(result_hash="f" * 64))
        flow = flows.get(flow.flow_id)
        assert flow.stale_gates == ("g1",)
        with pytest.raises(FlowError, match="har ändrats efter beslutet"):
            flows.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)

    def test_grindbesluten_ar_bara_nya_rader(self, setup):
        flows, fake, _, factory, _ = setup
        flow = through_g1(flows, fake)
        with factory() as s:
            rows = s.scalars(select(FlowGateDecision).where(FlowGateDecision.flow_id == flow.flow_id)).all()
            assert [(r.step_key, r.bound_hash) for r in rows] == [("g1", flow.gate_hashes["g1"])]


# --- fel, avbrott och avstämning -----------------------------------------------------------------------


class TestFelOchAvstamning:
    def test_misslyckad_agentkorning_ger_failed(self, setup):
        flows, fake = setup[0], setup[1]
        flow = flows.start("test_rule_change", {"source_handle": SOURCE}, actor=OPERATOR)
        fake.queue(text_result("Inget strukturerat svar."))
        flow = flows.run_next(flow.flow_id, expected_version=1, actor=OPERATOR)
        assert (flow.status, flow.step("tolkning").status) == ("failed", "failed")
        assert "failed" in flow.step("tolkning").error and flow.finished

    def test_ovantat_avbrott_kraver_avstamning_och_kan_koras_om(self, setup):
        flows, fake = setup[0], setup[1]
        flow = flows.start("test_rule_change", {"source_handle": SOURCE}, actor=OPERATOR)
        flow = flows.run_next(flow.flow_id, expected_version=1, actor=OPERATOR)  # inga skriptade svar: undantag
        assert (flow.status, flow.step("tolkning").status) == ("reconciliation_required", "reconciliation_required")
        with pytest.raises(FlowError, match="reconciliation_required"):
            flows.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)
        with pytest.raises(FlowError, match="anteckning"):
            flows.resolve_reconciliation(flow.flow_id, expected_version=flow.version, actor=OPERATOR, retry=True, note=" ")
        flow = flows.resolve_reconciliation(flow.flow_id, expected_version=flow.version, actor=OPERATOR, retry=True,
                                            note="Journalen visar inga verktygsanrop")
        assert (flow.status, flow.step("tolkning").status) == ("running", "pending")
        fake.queue(*COMPLIANCE)
        flow = flows.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)
        assert flow.status == "waiting_gate"

    def test_steg_som_pagick_vid_omstart_avstams(self, setup):
        flows, _, _, factory, _ = setup
        flow = flows.start("test_rule_change", {"source_handle": SOURCE}, actor=OPERATOR)
        with factory() as s:
            s.execute(update(FlowStep).where(FlowStep.flow_id == flow.flow_id, FlowStep.step_key == "tolkning")
                      .values(status="running"))
        assert flows.mark_interrupted() == [flow.flow_id]
        flow = flows.get(flow.flow_id)
        assert flow.status == "reconciliation_required" and "startade om" in flow.step("tolkning").error
        flow = flows.resolve_reconciliation(flow.flow_id, expected_version=flow.version, actor=OPERATOR, retry=False,
                                            note="Körningen gav ett okänt utfall")
        assert (flow.status, flow.step("tolkning").status) == ("failed", "failed")

    def test_avslaget_forslag_i_kon_stoppar_flodet(self, setup):
        flows, fake, service, _, _ = setup
        flow = through_g1(flows, fake)
        fake.queue(*IMPACT)
        flow = flows.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)
        flow = flows.decide_gate(flow.flow_id, expected_version=flow.version, actor=OPERATOR, decision="approved",
                                 seen_hash=flow.gate_hashes["g2"])
        flow = flows.complete_manual(flow.flow_id, expected_version=flow.version, actor=OPERATOR, data={"commit": "abcdef1"})
        flow = flows.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)
        service.reject(flow.step("aktivering").approval_id, OperationContext(actor=OPERATOR), note="Inte nu")
        flow = flows.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)
        assert (flow.status, flow.step("aktivering").status) == ("rejected", "rejected")
        assert flow.step("aktivering").result["approval"]["note"] == "Inte nu"

    def test_manuellt_steg_kraver_giltiga_uppgifter(self, setup):
        flows, fake = setup[0], setup[1]
        flow = through_g1(flows, fake)
        fake.queue(*IMPACT)
        flow = flows.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)
        flow = flows.decide_gate(flow.flow_id, expected_version=flow.version, actor=OPERATOR, decision="approved",
                                 seen_hash=flow.gate_hashes["g2"])
        with pytest.raises(FlowError, match="Ogiltiga uppgifter"):
            flows.complete_manual(flow.flow_id, expected_version=flow.version, actor=OPERATOR, data={"commit": "main"})

    def test_avbrott_hoppar_over_aterstaende_steg(self, setup):
        flows, fake = setup[0], setup[1]
        flow = through_g1(flows, fake)
        flow = flows.cancel(flow.flow_id, expected_version=flow.version, actor=OPERATOR, note="Källan drogs tillbaka")
        assert flow.status == "cancelled" and flow.finished
        assert [s.status for s in flow.steps] == ["completed", "completed"] + ["skipped"] * 5


# --- definitioner och tabeller -----------------------------------------------------------------------


class TestDefinitionOchTabeller:
    @pytest.mark.parametrize("steps, message", [
        ((GateStep("g", "G", binds=("x",)),), "inte är ett tidigare steg"),
        ((ManualStep("a", "A", FlowInput), ManualStep("a", "B", FlowInput)), "två gånger"),
        ((ManualStep("a", "A", FlowInput), GateStep("g", "G", binds=())), "binder inget"),
        ((ManualStep("a", "A", FlowInput), GateStep("g", "G", binds=("a",)), GateStep("h", "H", binds=("g",))),
         "bind stegens resultat"),
        ((), "minst ett steg"),
    ])
    def test_ogiltig_definition_stoppas(self, steps, message):
        with pytest.raises(HarnessError, match=message):
            FlowDefinition(flow_type="x", version="1", title="X", input_model=FlowInput, steps=steps)

    def test_indata_valideras_vid_start(self, setup):
        with pytest.raises(FlowError, match="Ogiltig indata"):
            setup[0].start("test_rule_change", {}, actor=OPERATOR)
        with pytest.raises(FlowError, match="Okänd flödestyp"):
            setup[0].start("okand", {}, actor=OPERATOR)

    @pytest.mark.parametrize("values", [
        {"flow_id": "FLOW-1"},
        {"status": "okand"},
        {"status": "completed"},  # avslutat utan finished_at
    ])
    def test_tabellens_villkor(self, setup, values):
        factory = setup[3]
        row = {"flow_id": "FLOW-000099", "flow_type": "x", "definition_version": "1", "status": "running",
               "input": {}, "version": 1, "created_by": "karl", **values}
        with pytest.raises(IntegrityError), factory() as s:
            s.add(Flow(**row))
            s.flush()
