"""Flödet `rule_change_parameter` (Fas 3c 3c-3, B-035, flaggskeppsflöde.md §2 och §7).

Hela flödet körs mot demobeståndet i minnet genom adaptern för UI:t (`FlowConsole`) med den
skriptade demomodellen: tolkning, grind 1, insikt, grind 2 med version, giltighet och B-nummer,
regeltexten, aktiveringen i godkännandekön under compliance-agentens identitet (val C) och
verifieringen med `ReleaseEvidence`. Därtill grindarnas kontroller, regelgolvet före
2026-11-01, verifiering av en återkallad version och adapterns gränser.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from agents.flows import FlowDefinition, FlowError, GateStep, ManualStep
from agents.flows.console import FlowBusyError, FlowConsole
from agents.flows.definitions import DEFINITIONS, RULE_CHANGE_PARAMETER, RuleTextCommit
from agents.flows.definitions.rule_change_parameter import synthetic_profile
from agents.flows.demo_model import interpretation_script
from ai.providers.fake import text_result
from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer
from services.db import session_factory_for
from services.operations import common
from utils.demo_data import create_demo_database

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 11, 15)  # PR-ITP1 v1.0 gäller – compliance-agenten får föreslå parameterändringen
OPERATOR = Actor.human("karl")
SOURCE = "K-SIM-ITP-2027"
ADOPTION = {"rule_version": "1.1", "valid_from": "2027-01-01", "decision_number": "B-036"}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False)
    yield session_factory_for(engine)
    engine.dispose()


def build(factory, tmp_path, *, today: date = TODAY) -> tuple[FlowConsole, ServiceLayer]:
    service = ServiceLayer(session_factory=factory, rules=ProductRuleCatalog(today=today))
    console = FlowConsole.build(factory, trusted=service, agent_service=service, journal_dir=tmp_path / "runs",
                                drafts_dir=tmp_path / "utkast")
    return console, service


@pytest.fixture
def setup(db, tmp_path):
    console, service = build(db, tmp_path)
    return console, service


def step(console, flow):
    return console.run_next(flow.flow_id, flow.version, OPERATOR)


def approve(console, flow, gate, details=None, note=None):
    return console.decide(flow.flow_id, flow.version, OPERATOR, decision="approved",
                          seen_hash=flow.gate_hashes[gate], note=note, details=details)


def to_g2(console):
    flow = console.start(SOURCE, OPERATOR)
    flow = approve(console, step(console, flow), "g1", note="Tolkningen stämmer")
    return step(console, flow)


def to_activation(console, details=ADOPTION):
    flow = approve(console, to_g2(console), "g2", details=details)
    flow = console.complete_manual(flow.flow_id, flow.version, OPERATOR, {"commit": "a1b2c3d", "note": "PR-013 v1.1"})
    return step(console, flow)


# --- hela flödet ------------------------------------------------------------------------------------


class TestHelaFlodet:
    def test_definitionen_foljer_paragraf_7(self):
        assert DEFINITIONS == (RULE_CHANGE_PARAMETER,)
        assert [(s.key, s.kind) for s in RULE_CHANGE_PARAMETER.steps] == [
            ("tolkning", "agent"), ("g1", "gate"), ("insikt", "agent"), ("g2", "gate"),
            ("regeltext", "manual"), ("aktivering", "system"), ("verifiering", "system")]
        assert RULE_CHANGE_PARAMETER.step("g2").binds == ("tolkning", "insikt")

    def test_fran_kalla_till_verifierad_parameter(self, setup, tmp_path):
        console, service = setup
        flow = console.start(SOURCE, OPERATOR)
        assert (flow.flow_type, flow.status, flow.current_step) == ("rule_change_parameter", "running", "tolkning")

        flow = step(console, flow)
        tolkning = flow.step("tolkning")
        assert (flow.status, tolkning.status, tolkning.agent) == ("waiting_gate", "completed", "compliance_agent")
        output = tolkning.result["output"]
        assert output["schema"] == "InterpretationProposal"
        assert [s["handle"] for s in output["evidence"]["sources"]] == [SOURCE, "PR-ITP1-013", "PR-ITP1-016"]
        assert output["evidence"]["sources"][0]["fictional"] is True
        assert tolkning.artifact_refs == (
            f"utkast:compliance/{tolkning.run_id}/konsekvensanalys.md",
            f"utkast:compliance/{tolkning.run_id}/regeldiff-pr-itp1-013.md")
        assert (tmp_path / "utkast" / "compliance" / tolkning.run_id / "konsekvensanalys.md").exists()
        assert tolkning.result["run"]["cost_usd"] == 0.0  # skriptad modell

        flow = step(console, approve(console, flow, "g1", note="Tolkningen stämmer"))
        insikt = flow.step("insikt")
        assert insikt.agent == "actuary_agent" and flow.status == "waiting_gate"
        assert insikt.result["output"]["evidence"]["estimate"]["first_affected_year"] == 2027

        flow = approve(console, flow, "g2", details=ADOPTION)
        assert flow.step("g2").result["details"] == ADOPTION and flow.status == "waiting_manual"
        flow = console.complete_manual(flow.flow_id, flow.version, OPERATOR, {"commit": "a1b2c3d"})

        flow = step(console, flow)
        aktivering = flow.step("aktivering")
        assert (flow.status, aktivering.status) == ("waiting_approval", "waiting")
        request = service.approvals.get(aktivering.approval_id)
        assert (request.operation, request.proposed_by, request.proposed_by_team, request.run_id) == (
            "schedule_product_parameter_change", "compliance_agent", "compliance", tolkning.run_id)
        assert request.input == {"key": "premium_age_end", "value": "67", "valid_from": "2027-01-01",
                                 "rule_version": "1.1", "source_ref": SOURCE, "decision_ref": "FLOW-000001 G2 B-036"}
        assert "a1b2c3d" in request.reason

        service.approve(aktivering.approval_id, OperationContext(actor=OPERATOR), note="Antagen i grind 2")
        flow = step(console, flow)
        assert flow.step("aktivering").completed_by == "karl" and flow.current_step == "verifiering"

        flow = step(console, flow)
        assert flow.status == "completed"
        result = flow.step("verifiering").result
        assert result["schema"] == "ReleaseEvidence"
        evidence = result["evidence"]
        assert evidence["verified"] is True and evidence["problems"] == []
        assert evidence["approval_id"] == aktivering.approval_id
        assert (evidence["before"]["value"], evidence["before"]["valid_to"]) == ("66", "2026-12-31")
        assert (evidence["after"]["value"], evidence["after"]["rule_version"]) == ("67", "1.1")
        assert evidence["after"]["decision_ref"] == "FLOW-000001 G2 B-036"
        before, after = evidence["preview_before"], evidence["preview_after"]
        assert (before["period_month"], before["in_age_window"], Decimal(before["total_premium_sek"])) == (
            "2026-12-01", False, Decimal("0.00"))
        assert (after["period_month"], after["in_age_window"]) == ("2027-01-01", True)
        assert Decimal(after["total_premium_sek"]) > 0
        assert after["parameter_version"] == "PR-ITP1-013 v1.1 från 2027-01-01"
        assert after["base_amount_assumed_from"] == 2026  # demobeståndet saknar IBB 2027
        assert evidence["profile"]["birth_date"] == "1960-07-15"

    def test_utan_b_nummer_ar_beslutet_grinden(self, setup):
        console, service = setup
        flow = to_activation(console, details={"rule_version": "1.1", "valid_from": "2027-01-01"})
        request = service.approvals.get(flow.step("aktivering").approval_id)
        assert request.input["decision_ref"] == "FLOW-000001 G2"


# --- grindarna -------------------------------------------------------------------------------------


class TestGrindarna:
    def test_grind_1_kraver_exakt_en_parameterandring(self, setup):
        console, _ = setup
        flow = console.start(SOURCE, OPERATOR)
        script = interpretation_script(SOURCE)
        answer = json.loads(script[-1].text)
        answer["parameter_changes"].append({**answer["parameter_changes"][0], "key": "premium_age_start",
                                            "current_value": "25", "new_value": "24"})
        console.demo_model.load([*script[:-1], text_result(json.dumps(answer, ensure_ascii=False))])
        flow = console.engine.run_next(flow.flow_id, expected_version=flow.version, actor=OPERATOR)
        with pytest.raises(FlowError, match="föreslår 2 parameterändringar"):
            approve(console, flow, "g1")
        with pytest.raises(FlowError, match="tar inga uppgifter"):
            approve(console, flow, "g1", details={"x": 1})
        flow = console.decide(flow.flow_id, flow.version, OPERATOR, decision="rejected",
                              seen_hash=flow.gate_hashes["g1"], note="Ett flöde per ändring")
        assert flow.status == "rejected"

    @pytest.mark.parametrize("details, message", [
        (None, "Ogiltiga uppgifter"),
        ({"rule_version": "1.1"}, "Ogiltiga uppgifter"),
        ({"rule_version": "v1.1", "valid_from": "2027-01-01"}, "Ogiltiga uppgifter"),
        ({"rule_version": "1.1", "valid_from": "2027-01-01", "decision_number": "36"}, "Ogiltiga uppgifter"),
        ({"rule_version": "1.1", "valid_from": "2027-02-01"}, "inte den godkända tolkningens 2027-01-01"),
    ])
    def test_grind_2_provar_uppgifterna(self, setup, details, message):
        console, _ = setup
        flow = to_g2(console)
        with pytest.raises(FlowError, match=message):
            approve(console, flow, "g2", details=details)
        assert console.get(flow.flow_id).status == "waiting_gate"  # ingenting sparat

    def test_avslag_i_grind_2_bar_inga_uppgifter(self, setup):
        console, _ = setup
        flow = to_g2(console)
        flow = console.decide(flow.flow_id, flow.version, OPERATOR, decision="rejected",
                              seen_hash=flow.gate_hashes["g2"], note="Vänta på parternas besked om PR-016")
        assert flow.status == "rejected" and "details" not in flow.step("g2").result

    def test_kontroll_utan_beslutsmodell_ar_tillaten(self):
        gate = GateStep("g", "G", binds=("a",), check=lambda ctx, details: None)
        assert gate.decision_model is None
        FlowDefinition(flow_type="x", version="1", title="X", input_model=RuleTextCommit,
                       steps=(ManualStep("a", "A", RuleTextCommit), gate))


# --- aktivering och verifiering -------------------------------------------------------------------


class TestAktiveringOchVerifiering:
    def test_regelgolvet_stoppar_forslaget_fore_regelpaketet(self, db, tmp_path):
        console, _ = build(db, tmp_path, today=date(2026, 10, 25))
        flow = to_activation(console)
        assert flow.status == "reconciliation_required"
        error = flow.step("aktivering").error
        assert "AccessDeniedError" in error and "2026-11-01" in error
        assert flow.step("aktivering").approval_id is None

    def test_kon_lases_utan_att_vanta_pa_flodets_las_i_en_sqlite_fil(self, tmp_path):
        """Demodatabasen tar skrivlåset vid BEGIN (web.database.demo_engine) – kön läses utanför flödets transaktion."""
        from web.database import demo_engine

        engine = demo_engine(tmp_path / "demo.db")
        try:
            console, service = build(session_factory_for(engine), tmp_path)
            flow = to_activation(console)
            service.approve(flow.step("aktivering").approval_id, OperationContext(actor=OPERATOR))
            flow = step(console, flow)
            assert flow.current_step == "verifiering"
        finally:
            engine.dispose()

    def test_avslaget_forslag_stoppar_flodet(self, setup):
        console, service = setup
        flow = to_activation(console)
        service.reject(flow.step("aktivering").approval_id, OperationContext(actor=OPERATOR), note="Inte nu")
        flow = step(console, flow)
        assert (flow.status, flow.step("verifiering").status) == ("rejected", "pending")

    def test_verifieringen_upptacker_en_aterkallad_version(self, setup):
        console, service = setup
        flow = to_activation(console)
        service.approve(flow.step("aktivering").approval_id, OperationContext(actor=OPERATOR))
        flow = step(console, flow)
        service.execute("withdraw_product_parameter_change", OperationContext(actor=OPERATOR, reason="Prov"),
                        {"key": "premium_age_end", "valid_from": "2027-01-01"})
        flow = step(console, flow)
        evidence = flow.step("verifiering").result["evidence"]
        assert flow.status == "completed" and evidence["verified"] is False
        assert any("66" in p for p in evidence["problems"])
        assert any("ändras inte" in p for p in evidence["problems"])

    @pytest.mark.parametrize("key, current, new, birth", [
        ("premium_age_end", "66", "67", date(1960, 7, 15)),
        ("premium_age_end", "66", "65", date(1961, 7, 15)),
        ("premium_age_start", "25", "24", date(2002, 7, 15)),
        ("premium_rate_low", "0.045", "0.05", date(1985, 5, 15)),
    ])
    def test_syntetisk_profil(self, key, current, new, birth):
        profile = synthetic_profile(key, Decimal(current), Decimal(new), date(2027, 1, 1))
        assert profile.birth_date == birth and profile.monthly_salary_sek > 0
        assert "Syntetisk profil" in profile.description


# --- adaptern för UI:t ------------------------------------------------------------------------------


class TestAdaptern:
    def test_demomodellen_kor_bara_demokallan(self, setup):
        console, _ = setup
        assert [d.handle for d in console.sources()] == [SOURCE]
        with pytest.raises(FlowError, match="bara köra den fiktiva källan"):
            console.start("kallandringar", OPERATOR)

    def test_en_korning_at_gangen(self, setup):
        console, _ = setup
        flow = console.start(SOURCE, OPERATOR)
        console._lock.acquire()
        try:
            assert console.busy
            with pytest.raises(FlowBusyError, match="körs redan"):
                step(console, flow)
        finally:
            console._lock.release()
        assert console.get(flow.flow_id).version == flow.version  # inget steg taget

    def test_skriptet_toms_efter_korningen(self, setup):
        console, _ = setup
        flow = step(console, console.start(SOURCE, OPERATOR))
        assert flow.status == "waiting_gate"
        assert console.demo_model._script == []

    def test_avbrutna_steg_markeras_vid_start(self, setup):
        console, _ = setup
        assert console.mark_interrupted() == []
