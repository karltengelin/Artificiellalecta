"""Teamen compliance och aktuarie i harness (Fas 3c 3c-T, B-035, flaggskeppsflöde.md §5 och §7).

Gatewayverktyg som skills (körpolicy, profil, dispatcher), parametermandatet för
beståndsinsikten, resultatscheman som prövas mot körningen och uppdragsmallarna – med
FakeProvider, utan nätverk, mot demobeståndet i minnet.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from agents import (
    CallStatus,
    Dispatcher,
    Ecosystem,
    EcosystemConfigError,
    Gateways,
    HarnessError,
    MemoryJournal,
    ParameterChangeMandate,
    RunRequest,
    RunStatus,
    SkillRegistry,
    compile_profile,
    mandate_from_interpretation,
    request_for_impact,
    request_for_interpretation,
    run_agent,
    run_assignment,
)
from agents.ecosystem import DEFAULT_ECOSYSTEM_PATH
from agents.gateways import DraftGateway, GatewayError, RegulatoryGateway
from ai import AIClient, AIConfig, ToolCall
from ai.providers.fake import FakeProvider, text_result, tool_call_result
from ai.tracing import MemoryTraceSink
from services import MemoryEventLog, ServiceLayer, default_registry
from services.db import session_factory_for
from services.operations import common
from utils.agent_roles import AKTUARIE
from utils.demo_data import create_demo_database

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 10, 25)
SOURCE = "K-SIM-ITP-2027"
MANDATE = ParameterChangeMandate(ref="pc-test", key="premium_age_end", value=Decimal("67"),
                                 valid_from=date(2027, 1, 1), horizon_years=10)
ESTIMATE = {"key": "premium_age_end", "value": "67", "valid_from": "2027-01-01", "horizon_years": 10}


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
def service():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False)
    yield ServiceLayer(session_factory=session_factory_for(engine), events=MemoryEventLog())
    engine.dispose()


@pytest.fixture
def gateways(tmp_path):
    return Gateways(regulatory=RegulatoryGateway(), drafts=DraftGateway(tmp_path / "utkast"))


def ai_client(fake) -> AIClient:
    config = AIConfig.from_dict({
        "providers": {"alpha": {"type": "fake", "api_key_env": "ALPHA_KEY"}},
        "models": {"alpha:big": {"price": {"input": 10.0, "output": 20.0},
                                 "capabilities": {"tools": True, "structured_output": True}}},
        "roles": {"deep": {"model": "alpha:big"}, "standard": {"model": "alpha:big"}},
    })
    return AIClient(config, sink=MemoryTraceSink(), provider_overrides={"alpha": fake}, environ={})


def action(data: dict, reason: str | None = None) -> dict:
    return {"data": data, "reason": reason}


def call(name: str, data: dict, call_id: str = "c1", reason: str | None = None) -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=action(data, reason))


def request(team: str, **overrides) -> RunRequest:
    return RunRequest(**{"task_id": "task-1", "target_team": team, "goal": "Test", **overrides})


def journal(team: str, agent: str) -> MemoryJournal:
    return MemoryJournal(run_id="run-1", team=team, agent=agent)


# --- körpolicyn ------------------------------------------------------------------------------------


def policy_dict() -> dict:
    return yaml.safe_load(DEFAULT_ECOSYSTEM_PATH.read_text(encoding="utf-8"))


class TestKorpolicyn:
    def test_teamen_och_deras_verktyg(self, eco, skills, service):
        visible = {
            agent: {d.skill for d in compile_profile(eco, skills, service, agent_id=agent).visible()}
            for agent in ("compliance_agent", "actuary_agent")
        }
        common_tools = {"list_regulatory_documents", "read_regulatory_document", "get_product_parameters",
                        "write_draft", "calculate_premium_preview"}
        assert visible == {"compliance_agent": common_tools, "actuary_agent": common_tools | {
            "get_company_metrics", "get_portfolio_snapshot", "get_premium_flows", "list_valuation_bases",
            "get_valuation_basis"}}
        assert eco.teams["compliance"].lead == "compliance_agent" and eco.agents["actuary_agent"].model_role == "deep"

    def test_inga_personuppgifter_for_teamen(self, eco, skills, service):
        for agent in ("compliance_agent", "actuary_agent"):
            profile = compile_profile(eco, skills, service, agent_id=agent)
            assert not any(d.pii for d in profile.visible())

    def test_beståndsinsikten_kraver_godkant_parameterforslag(self, eco, skills, service):
        without = compile_profile(eco, skills, service, request=request("aktuarie"))
        assert "kräver ett godkänt parameterförslag" in " ".join(without.decision("estimate_parameter_change_impact").reasons)
        with_ref = compile_profile(eco, skills, service, request=request("aktuarie", parameter_change_ref="pc-test"))
        assert with_ref.decision("estimate_parameter_change_impact").visible
        # compliance har inte podden bestand, ens med ett förslag
        compliance = compile_profile(eco, skills, service, request=request("compliance", parameter_change_ref="pc-test"))
        assert not compliance.decision("estimate_parameter_change_impact").visible

    def test_gatewayverktyg_ar_skills_utan_niva_i_tjanstelagret(self, eco, skills, service):
        profile = compile_profile(eco, skills, service, agent_id="compliance_agent")
        decision = profile.decision("write_draft")
        assert (decision.source, decision.kind.value, decision.pod) == ("gateway", "write", "dokument")
        assert skills.get("write_draft").action_model.model_json_schema()["required"] == ["data", "reason"]
        assert "write_draft" not in eco.unmapped_operations(default_registry)
        assert "estimate_parameter_change_impact" not in eco.unmapped_operations(default_registry)

    @pytest.mark.parametrize("change, message", [
        (lambda d: d["pods"]["regelverk"]["skills"].update({"x": {"gateway_tool": "okant"}}), "finns inte"),
        (lambda d: d["pods"]["regelverk"]["skills"].update({"x": {"gateway_tool": "write_draft"}}),
         "hör till podden 'dokument'"),
        (lambda d: d["pods"]["dokument"].update({"allowed_effects": ["read"]}), "verktyget är write"),
        (lambda d: d["pods"]["regelverk"]["skills"].update(
            {"x": {"gateway_tool": "read_regulatory_document", "service_operation": "get_case"}}), "exakt en av"),
        (lambda d: d["pods"]["regelverk"]["skills"].update({"x": {}}), "exakt en av"),
        (lambda d: d["pods"]["regelverk"]["skills"].update(
            {"x": {"gateway_tool": "list_regulatory_documents", "parameter_mandate": True}}), "bara tjänsteoperationer"),
    ])
    def test_ogiltig_montering_stoppas(self, change, message):
        data = copy.deepcopy(policy_dict())
        change(data)
        with pytest.raises(EcosystemConfigError, match=message):
            Ecosystem.from_dict(data)

    def test_parametermandat_kraver_parameterfalten(self):
        data = copy.deepcopy(policy_dict())
        data["pods"]["regelverk"]["skills"]["get_product_parameters"]["parameter_mandate"] = True
        with pytest.raises(EcosystemConfigError, match="parameter_mandate kräver fälten"):
            Ecosystem.from_dict(data).validate_against_registry(default_registry)


# --- dispatchern -----------------------------------------------------------------------------------


def dispatcher(eco, skills, service, team, *, parameter_change=None, gateways=None, **overrides):
    req = request(team, **overrides)
    profile = compile_profile(eco, skills, service, request=req)
    return Dispatcher(profile, service, run_id="run-1", parameter_change=parameter_change, gateways=gateways)


class TestGatewayverktyg:
    def test_lasa_kallan_ger_version_och_kontrollsumma(self, eco, skills, service, gateways):
        outcome = dispatcher(eco, skills, service, "compliance", gateways=gateways).dispatch(
            [call("read_regulatory_document", {"handle": SOURCE, "section": None, "offset": 0})])
        (c,) = outcome.calls
        assert c.status == CallStatus.DONE
        doc = json.loads(c.result.content)["output"]["document"]
        assert (doc["handle"], doc["fictional"]) == (SOURCE, True) and len(doc["sha256"]) == 16

    def test_utkast_hamnar_i_korningens_arbetsyta(self, eco, skills, service, gateways, tmp_path):
        outcome = dispatcher(eco, skills, service, "compliance", gateways=gateways).dispatch(
            [call("write_draft", {"name": "konsekvensanalys.md", "title": "Konsekvensanalys", "content": "# Test"},
                  reason="Utkast")])
        assert outcome.calls[0].status == CallStatus.DONE
        assert (tmp_path / "utkast" / "compliance" / "run-1" / "konsekvensanalys.md").read_text(encoding="utf-8") == "# Test\n"

    def test_utkast_kraver_motivering(self, eco, skills, service, gateways):
        outcome = dispatcher(eco, skills, service, "compliance", gateways=gateways).dispatch(
            [call("write_draft", {"name": "a.md", "title": "A", "content": "x"})])
        assert outcome.calls[0].status == CallStatus.INVALID

    def test_gatewayens_nej_blir_fel_och_sakerhetsnej_nekas(self, eco, skills, service, gateways):
        d = dispatcher(eco, skills, service, "compliance", gateways=gateways)
        missing = d.dispatch([call("read_regulatory_document", {"handle": "PR-ITP1-999", "section": None, "offset": 0})])
        assert missing.calls[0].status == CallStatus.ERROR
        assert missing.calls[0].error_type.startswith("GatewayError:")
        pnr = d.dispatch([call("write_draft", {"name": "b.md", "title": "B", "content": "Anna 19850515-1236"},
                               reason="Utkast")])
        assert pnr.calls[0].status == CallStatus.ERROR and "personnummer" in pnr.calls[0].result.content

        class Breaking(DraftGateway):
            def write_draft(self, team, run_id, data):
                raise GatewayError("security", "Länkar är inte tillåtna", security=True)

        breaking = Gateways(regulatory=gateways.regulatory, drafts=Breaking(gateways.drafts.root))
        denied = dispatcher(eco, skills, service, "compliance", gateways=breaking).dispatch(
            [call("write_draft", {"name": "c.md", "title": "C", "content": "x"}, reason="Utkast")])
        assert denied.calls[0].status == CallStatus.DENIED

    def test_okanda_falt_i_gatewayanrop_ar_sakerhetsbrott(self, eco, skills, service, gateways):
        outcome = dispatcher(eco, skills, service, "compliance", gateways=gateways).dispatch(
            [call("read_regulatory_document", {"handle": SOURCE, "section": None, "offset": 0, "path": "../.env"})])
        assert outcome.calls[0].status == CallStatus.DENIED


class TestParametermandatet:
    def test_godkand_andring_raknas(self, eco, skills, service):
        d = dispatcher(eco, skills, service, "aktuarie", parameter_change=MANDATE, parameter_change_ref="pc-test")
        (c,) = d.dispatch([call("estimate_parameter_change_impact", ESTIMATE)]).calls
        assert c.status == CallStatus.DONE
        assert json.loads(c.result.content)["output"]["first_affected_year"] == 2027

    def test_utelamnad_horisont_ar_standard_tio_ar(self, eco, skills, service):
        d = dispatcher(eco, skills, service, "aktuarie", parameter_change=MANDATE, parameter_change_ref="pc-test")
        data = {k: v for k, v in ESTIMATE.items() if k != "horizon_years"}
        assert d.dispatch([call("estimate_parameter_change_impact", data)]).calls[0].status == CallStatus.DONE

    @pytest.mark.parametrize("change", [
        {"value": "68"}, {"valid_from": "2027-02-01"}, {"horizon_years": 11}, {"key": "premium_rate_low", "value": "0.05"},
    ])
    def test_annan_andring_eller_horisont_nekas(self, eco, skills, service, change):
        d = dispatcher(eco, skills, service, "aktuarie", parameter_change=MANDATE, parameter_change_ref="pc-test")
        (c,) = d.dispatch([call("estimate_parameter_change_impact", {**ESTIMATE, **change})]).calls
        assert c.status == CallStatus.DENIED and "godkända parameterförslaget pc-test" in c.result.content

    def test_samma_varde_med_annan_skrivning_godtas(self, eco, skills, service):
        d = dispatcher(eco, skills, service, "aktuarie", parameter_change=MANDATE, parameter_change_ref="pc-test")
        assert d.dispatch([call("estimate_parameter_change_impact", {**ESTIMATE, "value": "67.0"})]).calls[0].status == CallStatus.DONE

    def test_mandatet_maste_vara_uppdragets(self, eco, skills, service):
        with pytest.raises(HarnessError, match="Parameterförslaget stämmer inte"):
            dispatcher(eco, skills, service, "aktuarie", parameter_change=MANDATE, parameter_change_ref="pc-annat")
        with pytest.raises(HarnessError, match="Parameterförslaget stämmer inte"):
            dispatcher(eco, skills, service, "aktuarie", parameter_change_ref="pc-test")

    def test_utan_mandat_ar_verktyget_dolt_och_nekas(self, eco, skills, service):
        (c,) = dispatcher(eco, skills, service, "aktuarie").dispatch(
            [call("estimate_parameter_change_impact", ESTIMATE)]).calls
        assert c.status == CallStatus.DENIED


class TestLedningsaggregat:
    """OC-3a val C–D: aktuarien läser ledningsaggregatet utan mandat; databasrollen får bara kolumnerna."""

    def test_aktuarien_laser_aggregatet_utan_mandat(self, eco, skills, service):
        (c,) = dispatcher(eco, skills, service, "aktuarie").dispatch(
            [call("get_company_metrics", {"month": "2026-09-01"})]).calls
        assert c.status == CallStatus.DONE
        out = json.loads(c.result.content)["output"]
        assert out["period_from"] == "2026-09-01" and out["paid_state"] in {"available", "suppressed", "failed"}
        assert out["insured_count"] is None or out["insured_count"] >= 10

    def test_compliance_har_inte_aggregatet(self, eco, skills, service):
        profile = compile_profile(eco, skills, service, request=request("compliance"))
        assert not profile.decision("get_company_metrics").visible

    def test_rollen_far_bara_aggregatets_kolumner(self):
        statements = " ; ".join(AKTUARIE.statements())
        assert 'GRANT SELECT ON "public"."premium_transactions"' not in statements
        assert ('GRANT SELECT ("benefit_id", "transaction_type", "status", "paid_date", "amount_sek") '
                'ON "public"."premium_transactions"') in statements
        assert "pensionable_salary_sek" not in statements and "calculation_basis" not in statements

    @pytest.mark.parametrize("columns", [(("policies", ("id",)),), (("premium_transactions", ()),),
                                         (("premium_transactions", ("amount; DROP",)),)])
    def test_ogiltig_kolumnrattighet_stoppas(self, columns):
        with pytest.raises(ValueError):
            replace(AKTUARIE, columns=columns).statements()


# --- resultatscheman och uppdragsmallar ---------------------------------------------------------------


def interpretation(**overrides) -> str:
    data = {
        "summary": "Premieåldern höjs från 66 till 67 år från 2027-01-01 (fiktiv källa).",
        "affected_rules": ["PR-ITP1-013", "PR-ITP1-016"],
        "parameter_changes": [{"key": "premium_age_end", "current_value": "66", "new_value": "67",
                               "valid_from": "2027-01-01", "rule_id": "PR-ITP1-013",
                               "rationale": "Källan anger premie till månaden före 67 år."}],
        "customer_impact": "Försäkrade som fyller 66 från 2027 får premie ett år till.",
        "uncertainties": ["PR-ITP1-016:s frivilliga premie 66–67 blir överflödig"],
        "source_handles": [SOURCE],
        "draft_names": ["konsekvensanalys.md"],
        **overrides,
    }
    return json.dumps(data, ensure_ascii=False)


def impact(**overrides) -> str:
    data = {"insight": "Premieåldern 67 berör 16 aktiva redan 2027.", "key_findings": ["2027–2029 berörs"],
            "uncertainties": ["Dagens lön utan lönetillväxt"], "source_handles": [], "draft_names": ["insikt.md"],
            **overrides}
    return json.dumps(data, ensure_ascii=False)


COMPLIANCE_SCRIPT = [
    tool_call_result("read_regulatory_document", action({"handle": SOURCE, "section": None, "offset": 0})),
    tool_call_result("get_product_parameters", action({"on_date": "2027-01-01"}), call_id="call_2"),
    tool_call_result("write_draft", action({"name": "konsekvensanalys.md", "title": "Konsekvensanalys",
                                             "content": "# Konsekvensanalys\n\nPR-ITP1-013 och PR-ITP1-016."},
                                            "Utkast till grind 1"), call_id="call_3"),
]


class TestTolkning:
    def test_mallen_ger_uppdrag_med_schema_och_kalla(self):
        req = request_for_interpretation(SOURCE, flow_id="FLOW-000001")
        assert (req.target_team, req.result_schema, req.references, req.flow_id) == (
            "compliance", "InterpretationProposal", (SOURCE,), "FLOW-000001")
        assert req.parameter_change_ref is None and req.execution_scope_ref is None

    def test_tolkningen_far_bevis_ur_korningen(self, eco, skills, service, gateways):
        fake = FakeProvider([*COMPLIANCE_SCRIPT, text_result(interpretation())])
        outcome = run_assignment(ai_client(fake), eco, skills, service, request_for_interpretation(SOURCE),
                                 gateways=gateways, run_id="run-1", journal=journal("compliance", "compliance_agent"))
        result = outcome.result
        assert result.status == RunStatus.COMPLETED, result.uncertainties
        assert result.summary.startswith("Premieåldern höjs")
        assert result.output["schema"] == "InterpretationProposal"
        (source,) = result.output["evidence"]["sources"]
        assert (source["handle"], source["fictional"]) == (SOURCE, True)
        assert result.output["evidence"]["drafts"][0]["reference"] == "utkast:compliance/run-1/konsekvensanalys.md"
        # AI-lagret fick schemat, och modellen såg bara teamets verktyg
        assert fake.requests[0].output_schema is not None
        assert {t.name for t in fake.requests[0].tools} == {
            "list_regulatory_documents", "read_regulatory_document", "get_product_parameters", "write_draft",
            "calculate_premium_preview"}
        assert "InterpretationProposal" in fake.requests[0].messages[0].text

    @pytest.mark.parametrize("overrides, problem", [
        ({"source_handles": ["PR-ITP1-013"]}, "källan PR-ITP1-013 är inte läst"),
        ({"draft_names": ["annat.md"]}, "utkastet annat.md är inte skrivet"),
        ({"source_handles": []}, "ingen läst källa"),
    ])
    def test_resultat_som_inte_stammer_lamnas_till_manniskan(self, eco, skills, service, gateways, overrides, problem):
        fake = FakeProvider([*COMPLIANCE_SCRIPT, text_result(interpretation(**overrides))])
        outcome = run_assignment(ai_client(fake), eco, skills, service, request_for_interpretation(SOURCE),
                                 gateways=gateways, run_id="run-1", journal=journal("compliance", "compliance_agent"))
        assert outcome.result.status == RunStatus.NEEDS_HUMAN and outcome.result.output is None
        assert any(problem in u for u in outcome.result.uncertainties)

    def test_svar_utanfor_schemat_godtas_inte(self, eco, skills, service, gateways):
        fake = FakeProvider([text_result("Premieåldern höjs till 67 år.")])
        outcome = run_assignment(ai_client(fake), eco, skills, service, request_for_interpretation(SOURCE),
                                 gateways=gateways, run_id="run-1", journal=journal("compliance", "compliance_agent"))
        assert outcome.result.status == RunStatus.FAILED and outcome.result.output is None

    def test_avklippt_svar_vid_utdatataket_sags_tydligt(self, eco, skills, service, gateways):
        """Röktestet 3c-V: tolkningen klipptes vid teamets utdatatak och validerade inte."""
        cut = replace(text_result('{"summary": "Premieåldern höjs till 67 år och '), stop_reason="max_tokens")
        outcome = run_assignment(ai_client(FakeProvider([cut])), eco, skills, service,
                                 request_for_interpretation(SOURCE), gateways=gateways, run_id="run-1",
                                 journal=journal("compliance", "compliance_agent"))
        assert outcome.result.status == RunStatus.FAILED and outcome.result.output is None
        assert "utdatataket" in outcome.result.summary


class TestBestandsinsikt:
    def approved(self, eco, skills, service, gateways):
        fake = FakeProvider([*COMPLIANCE_SCRIPT, text_result(interpretation())])
        outcome = run_assignment(ai_client(fake), eco, skills, service, request_for_interpretation(SOURCE),
                                 gateways=gateways, run_id="run-1", journal=journal("compliance", "compliance_agent"))
        return mandate_from_interpretation(outcome.result.output, ref="pc-FLOW-000001")

    def test_mandatet_ur_den_godkanda_tolkningen(self, eco, skills, service, gateways):
        mandate = self.approved(eco, skills, service, gateways)
        assert (mandate.key, mandate.value, mandate.valid_from, mandate.horizon_years) == (
            "premium_age_end", Decimal("67"), date(2027, 1, 1), 10)
        req = request_for_impact(mandate)
        assert (req.target_team, req.result_schema, req.parameter_change_ref) == (
            "aktuarie", "PortfolioImpactResult", "pc-FLOW-000001")
        assert "premium_age_end = 67 från 2027-01-01" in req.goal

    def test_insikten_bar_beräkningen_ur_betrodd_kod(self, eco, skills, service, gateways):
        mandate = self.approved(eco, skills, service, gateways)
        fake = FakeProvider([
            tool_call_result("estimate_parameter_change_impact", action(ESTIMATE)),
            tool_call_result("write_draft", action({"name": "insikt.md", "title": "Beståndsinsikt",
                                                     "content": "# Insikt\n\nFörsta berörda år 2027."}, "Rapportutkast"),
                             call_id="call_2"),
            text_result(impact()),
        ])
        outcome = run_assignment(ai_client(fake), eco, skills, service, request_for_impact(mandate),
                                 parameter_change=mandate, gateways=gateways, run_id="run-2",
                                 journal=journal("aktuarie", "actuary_agent"))
        result = outcome.result
        assert result.status == RunStatus.COMPLETED, result.uncertainties
        estimate = result.output["evidence"]["estimate"]
        assert (estimate["first_affected_year"], estimate["key"], estimate["value"]) == (2027, "premium_age_end", "67")
        assert estimate["years"][0]["affected_persons"] >= 10
        assert "estimate_parameter_change_impact" in {t.name for t in fake.requests[0].tools}

    def test_utan_beräkning_ingen_insikt(self, eco, skills, service, gateways):
        fake = FakeProvider([text_result(impact(draft_names=[]))])
        outcome = run_assignment(ai_client(fake), eco, skills, service, request_for_impact(MANDATE),
                                 parameter_change=MANDATE, gateways=gateways, run_id="run-2",
                                 journal=journal("aktuarie", "actuary_agent"))
        assert outcome.result.status == RunStatus.NEEDS_HUMAN
        assert "ingen beräkning" in outcome.result.uncertainties[0]

    def test_annat_varde_an_det_godkanda_blockerar(self, eco, skills, service, gateways):
        fake = FakeProvider([tool_call_result("estimate_parameter_change_impact", action({**ESTIMATE, "value": "68"}))])
        outcome = run_assignment(ai_client(fake), eco, skills, service, request_for_impact(MANDATE),
                                 parameter_change=MANDATE, gateways=gateways, run_id="run-2",
                                 journal=journal("aktuarie", "actuary_agent"))
        assert outcome.result.status == RunStatus.BLOCKED and len(fake.requests) == 1

    def test_mandat_bara_ur_en_tolkning_med_parameterandring(self):
        with pytest.raises(HarnessError, match="bara ur en tolkning"):
            mandate_from_interpretation({"schema": "PortfolioImpactResult"}, ref="x")
        empty = {"schema": "InterpretationProposal", "result": {"parameter_changes": []}}
        with pytest.raises(HarnessError, match="ingen parameterändring"):
            mandate_from_interpretation(empty, ref="x")


def test_okant_resultatschema_stoppas(eco, skills, service):
    req = request("compliance", result_schema="Okänt")
    profile = compile_profile(eco, skills, service, request=req)
    with pytest.raises(HarnessError, match="Okänt resultatschema"):
        run_agent(ai_client(FakeProvider()), profile, service, req, journal=journal("compliance", "compliance_agent"))
