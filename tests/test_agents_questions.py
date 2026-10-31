"""Första fråge- och rapportkedjan (OC-3a, B-041): bolagsfrågan från beställning till godkänd leverans.

Testleverantör och SQLite i minnet; inga riktiga modellanrop och ingen Lakebase. Facit för
demobeståndet följer datakontraktet P2-FRAGA-001 §5 (läsdag 2026-10-27).
"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from agents import compile_profile
from agents.deliveries import DeliveryError, DeliveryStore
from agents.ecosystem import Ecosystem
from agents.flows.console import FlowBusyError, FlowConsole
from agents.flows.definitions import DEFINITIONS
from agents.flows.definitions.company_question import closed_months, month_end
from agents.flows.engine import FlowEngine
from agents.flows.questions import QuestionConsole
from agents.flows.store import FlowError
from agents.results import unsupported_numbers
from agents.skills import SkillRegistry
from agents.assignments import COMPANY_QUESTION_FIXED_LIMITATIONS, request_for_company_question
from agents.trace import run_trace
from ai import AIClient, AIConfig
from ai.providers.fake import FakeProvider, text_result, tool_call_result
from ai.tracing import MemoryTraceSink
from management.metrics import company_observations
from services import Actor, MemoryEventLog, OperationKind, ServiceLayer, default_registry
from services.db import session_factory_for
from services.operations import common
from utils.demo_data import create_demo_database

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 10, 27)
KARL = Actor.human("karl")
NOVEMBER = date(2025, 11, 1)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


@pytest.fixture
def demo():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False, today=TODAY)
    yield session_factory_for(engine)
    engine.dispose()


def ai_client(fake) -> AIClient:
    config = AIConfig.from_dict({
        "providers": {"alpha": {"type": "fake", "api_key_env": "ALPHA_KEY"}},
        "models": {"alpha:big": {"price": {"input": 10.0, "output": 20.0},
                                 "capabilities": {"tools": True, "structured_output": True}}},
        "roles": {"deep": {"model": "alpha:big"}, "standard": {"model": "alpha:big"}},
    })
    return AIClient(config, sink=MemoryTraceSink(), provider_overrides={"alpha": fake}, environ={})


def fake_pdf(markdown, metadata) -> bytes:
    return b"%PDF-fake\n" + metadata.title.encode("utf-8")


def answer(status="answered", month=NOVEMBER, conclusion="35 registrerade försäkrade och 145 971,41 SEK betalmarkerat.",
           **overrides) -> str:
    return json.dumps({"status": status, "month": month.isoformat(), "conclusion": conclusion,
                       "limitations": ["Läsdagens bestånd, inte månadens slut."], "assumptions": [],
                       "next_steps": [], **overrides})


def read_then(month=NOVEMBER, **kw):
    return [tool_call_result("get_company_metrics", {"data": {"month": month.isoformat()}, "reason": None}),
            text_result(answer(month=month, **kw))]


def console(factory, tmp_path, responses, renderer=fake_pdf) -> QuestionConsole:
    service = ServiceLayer(session_factory=factory, events=MemoryEventLog())
    return QuestionConsole.build(
        factory, trusted=service, actuary_service=service, ai=ai_client(FakeProvider(responses)),
        renderer=renderer, environment_id="demo", dataset_ref="demo:current",
        deliveries_dir=tmp_path / "leveranser", journal_dir=tmp_path / "runs",
    )


def approve(c: QuestionConsole, flow_id: str):
    flow = c.flow(flow_id)
    return c.decide(flow_id, flow.version, KARL, decision="approved", seen_hash=flow.gate_hashes["review"], note=None)


class TestHelaKedjan:
    def test_fraga_till_godkand_leverans(self, demo, tmp_path):
        c = console(demo, tmp_path, read_then())
        view = c.start(NOVEMBER, "Hur ser beståndet ut?", KARL)
        assert (view.status, view.status_text, view.answer_status) == ("waiting_gate", "Väntar på granskning", "answered")
        assert (view.team, view.requested_by, view.delivery_version, view.review) == ("aktuarie", "karl", 1, "not_reviewed")
        report = c.delivery(view.flow_id, "rapport.md").decode("utf-8")
        for expected in ("35 personer", "145 971,41 SEK", "P2-FRAGA-001 v1.0", "läsdag 2026-10-27",
                         "2025-11-01 till 2025-12-01", "`demo`, dataset `demo:current`", "inte bankavstämt"):
            assert expected in report
        assert c.delivery(view.flow_id, "rapport.pdf").startswith(b"%PDF")

        done = approve(c, view.flow_id)
        assert (done.status, done.status_text, done.accepted, done.review, done.reviewed_by) == (
            "completed", "Levererad", True, "approved", "karl")
        assert [a.flow_id for a in c.list()] == [view.flow_id] == [a.flow_id for a in c.list("aktuarie")]
        assert c.list("compliance") == []

    def test_rapporten_ar_skriven_for_lasaren_och_visar_hur_den_togs_fram(self, demo, tmp_path):
        fixed = "Registrerat bestånd gäller läsdagen och är inte ett historiskt månadsslutsbestånd."
        c = console(demo, tmp_path, read_then(limitations=[fixed, "Inga uppdelningar per arbetsgivare."]))
        view = c.start(NOVEMBER, "", KARL)
        report = c.delivery(view.flow_id, "rapport.md").decode("utf-8")
        headings = [line for line in report.splitlines() if line.startswith("## ")]
        assert headings == ["## Svar", "## Värden", "## Begränsningar", "## Definitioner",
                            "## Datakälla och kontroller", "## Så togs rapporten fram"]
        assert report.count(fixed) == 1 and "- Inga uppdelningar per arbetsgivare." in report
        trace_part = report.split("## Så togs rapporten fram")[1]
        for expected in ("Agent `actuary_agent`, modellroll `deep`, modell `alpha:big`",
                         "Modellsteg 2, verktygsanrop 1", "Verktyg `get_company_metrics`, typ read, nivå AGENT: klar",
                         "kostnad 0,", "Rapporten granskas i uppdraget"):
            assert expected in trace_part
        assert " USD" in trace_part and ".0" not in trace_part.split("kostnad ")[1].split(" USD")[0]

        trace = c.trace(view.flow_id)
        assert (trace.agent, trace.models, trace.complete) == ("actuary_agent", ("alpha:big",), True)
        assert [(t.skill, t.kind, t.level, t.status) for t in trace.tools] == [
            ("get_company_metrics", "read", "AGENT", "done")]

    def test_uppdraget_ber_om_vd_sprak_utan_upprepade_begransningar(self):
        constraints = " ".join(request_for_company_question(NOVEMBER).constraints)
        assert "Skriv för en VD" in constraints and "Upprepa dem inte" in constraints
        assert all(t in constraints for t in COMPANY_QUESTION_FIXED_LIMITATIONS)

    def test_uppdraget_ar_avsmalnat_till_lasning(self, demo):
        eco = Ecosystem.load()
        service = ServiceLayer(session_factory=demo, events=MemoryEventLog())
        request = request_for_company_question(NOVEMBER, "Precisering")
        profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), service, request=request)
        visible = {d.skill for d in profile.visible()}
        assert "get_company_metrics" in visible
        assert not visible & {"write_draft", "delegate_to_team", "estimate_parameter_change_impact"}
        assert request.allowed_effects == {OperationKind.READ, OperationKind.COMPUTE}
        assert "underlag, inte instruktion" in request.background and request.result_schema == "CompanyAnswer"

    def test_avslag_avslutar_och_ny_bestallning_ersatter(self, demo, tmp_path):
        c = console(demo, tmp_path, [*read_then(), *read_then()])
        first = c.start(NOVEMBER, "", KARL)
        flow = c.flow(first.flow_id)
        with pytest.raises(FlowError, match="kräver en anteckning"):
            c.decide(first.flow_id, flow.version, KARL, decision="rejected", seen_hash=flow.gate_hashes["review"], note="")
        rejected = c.decide(first.flow_id, flow.version, KARL, decision="rejected",
                            seen_hash=flow.gate_hashes["review"], note="Fel period")
        assert (rejected.status, rejected.review, rejected.accepted) == ("rejected", "rejected", False)
        second = c.start(NOVEMBER, "", KARL, supersedes=first.flow_id)
        assert second.supersedes == first.flow_id
        assert f"Ersätter det avslagna uppdraget `{first.flow_id}`" in c.delivery(second.flow_id, "rapport.md").decode()
        with pytest.raises(FlowError, match="Bara ett avslaget"):
            c.start(NOVEMBER, "", KARL, supersedes=second.flow_id)


class TestTalOchUnderlag:
    def test_obelagt_tal_stoppar_svaret(self, demo, tmp_path):
        c = console(demo, tmp_path, read_then(conclusion="36 registrerade försäkrade."))
        view = c.start(NOVEMBER, "", KARL)
        assert view.status == "failed" and view.delivery_version is None
        assert "36" in json.dumps(c.flow(view.flow_id).step("answer").result)

    def test_dolt_matt_ger_delsvar_utan_tal(self, insurance_db, tmp_path):
        """Ett försäkrat: bestånd och belopp döljs. Fullständigt svar godtas inte; delsvaret visar orsaken."""
        full = console(insurance_db.session_factory, tmp_path / "a", read_then(conclusion="Underlaget är litet."))
        assert full.start(NOVEMBER, "", KARL).status == "failed"
        partial = console(insurance_db.session_factory, tmp_path / "b",
                          read_then(status="partial", conclusion="Måtten döljs eftersom underlaget är litet."))
        view = partial.start(NOVEMBER, "", KARL)
        assert (view.status, view.answer_status) == ("waiting_gate", "partial")
        report = partial.delivery(view.flow_id, "rapport.md").decode()
        assert "Visas inte – Små persongrupper döljs." in report and " 0,00 SEK" not in report

    def test_fraga_utanfor_stodet_blir_avgransad(self, demo, tmp_path):
        c = console(demo, tmp_path, [text_result(answer(status="unavailable", conclusion="Underlaget saknar historik."))])
        view = c.start(NOVEMBER, "Hur såg beståndet ut för fem år sedan?", KARL)
        assert (view.status, view.answer_status) == ("waiting_gate", "unavailable")
        report = c.delivery(view.flow_id, "rapport.md").decode()
        assert "Inte läst – frågan kunde inte besvaras med underlaget." in report
        assert "kunde inte läsas" not in report

    def test_svar_for_annan_manad_an_bestallningen(self, demo, tmp_path):
        october = date(2026, 9, 1)
        c = console(demo, tmp_path, read_then(month=october, conclusion="Inga betalmarkeringar."))
        view = c.start(NOVEMBER, "", KARL)
        assert view.status == "failed" and "beställningen 2025-11-01" in view.error


class TestGranserOchFel:
    @pytest.mark.parametrize("month", [date(2026, 10, 1), date(2026, 11, 1), date(2024, 1, 1)])
    def test_bara_avslutade_manader(self, demo, tmp_path, month):
        with pytest.raises(FlowError, match="avslutad månad"):
            console(demo, tmp_path, []).start(month, "", KARL)

    @pytest.mark.parametrize("actor", [Actor.agent("actuary_agent", team="aktuarie"), Actor.system("cron")])
    def test_bara_en_operator(self, demo, tmp_path, actor):
        with pytest.raises(FlowError, match="inloggad operatör"):
            console(demo, tmp_path, []).start(NOVEMBER, "", actor)

    def test_misslyckad_export_ger_misslyckat_uppdrag_utan_filer(self, demo, tmp_path):
        def broken(markdown, metadata):
            raise RuntimeError("typsnitt saknas")

        c = console(demo, tmp_path, read_then(), renderer=broken)
        view = c.start(NOVEMBER, "", KARL)
        assert (view.status, view.delivery_version) == ("failed", None)
        assert "Exporten misslyckades" in view.error
        assert not (tmp_path / "leveranser").exists()

    def test_andrad_fil_upptacks_och_levereras_inte(self, demo, tmp_path):
        c = console(demo, tmp_path, read_then())
        view = c.start(NOVEMBER, "", KARL)
        (tmp_path / "leveranser" / view.flow_id / "v1" / "rapport.pdf").write_bytes(b"%PDF-annan")
        with pytest.raises(DeliveryError, match="har ändrats"):
            c.delivery(view.flow_id, "rapport.pdf")
        done = approve(c, view.flow_id)
        assert (done.status, done.accepted) == ("failed", False)

    def test_en_korning_at_gangen(self, demo, tmp_path):
        c = console(demo, tmp_path, [])
        c._lock.acquire()
        try:
            with pytest.raises(FlowBusyError):
                c.start(NOVEMBER, "", KARL)
        finally:
            c._lock.release()

    def test_bara_aktuarien_kan_ta_emot_fragan(self, demo, tmp_path):
        teams = {t.team: t for t in console(demo, tmp_path, []).teams()}
        assert teams["aktuarie"].available and teams["aktuarie"].reason is None
        assert not teams["forsakring"].available and "aktuarieteamet" in teams["forsakring"].reason

    def test_regelflodenas_lista_visar_inte_bolagsfragor(self, demo, tmp_path):
        c = console(demo, tmp_path, read_then())
        c.start(NOVEMBER, "", KARL)
        rule_console = FlowConsole(engine=FlowEngine(demo, DEFINITIONS), regulatory=None, drafts=None,
                                   journal_dir=tmp_path, model_label="test", simulated_role=True)
        assert rule_console.list() == []


class TestByggstenar:
    def test_avslutade_manader(self):
        months = closed_months(TODAY)
        assert (months[0], months[-1], len(months)) == (date(2026, 9, 1), date(2025, 11, 1), 11)
        assert closed_months(date(2026, 1, 15))[0] == date(2025, 12, 1)
        assert month_end(date(2025, 12, 1)) == date(2026, 1, 1)

    def test_tal_i_texten_prövas_mot_lasningen(self):
        read = {"insured_count": 35, "paid_sek": "145971.41", "as_of_date": "2026-10-27", "period_from": "2025-11-01",
                "period_to": "2025-12-01", "read_at": "2026-10-27T10:00:00+00:00"}
        ok = ["35 försäkrade, 145 971,41 SEK (avrundat 145 971 kr) i november 2025, läst 2026-10-27.",
              "Perioden 2025-11-01–2025-11-30, alltså 1–30 november.",
              "Celler med 1–9 personer döljs; gränsen är 10. Kontrakt P2-FRAGA-001 v1.0, §3 och PR-ITP1-013."]
        assert unsupported_numbers(ok, read) == []
        assert unsupported_numbers(["Cirka 146 000 kr, 36 personer, 3 % och 2026-09-01."], read) == [
            "2026-09-01", "146 000", "36", "3"]
        assert unsupported_numbers(["Jämfört med 2024-11 och 2025-11-29."], read) == ["2024-11", "2025-11-29"]

    def test_observationerna_skiljer_noll_dolt_underkant_och_oläst(self):
        now = datetime(2026, 10, 27, 10, tzinfo=UTC)
        kw = {"environment_id": "demo", "dataset_ref": "demo:current", "period": (NOVEMBER, month_end(NOVEMBER)),
              "today": TODAY, "now": now}
        base = {"read_at": now.isoformat(), "as_of_date": "2026-10-27", "insured_count": 35, "insured_suppressed": False}
        zero = company_observations({**base, "paid_sek": "0.00", "paid_state": "available"}, **kw)
        assert [o.value for o in zero] == [35, Decimal("0.00")]
        failed = company_observations({**base, "paid_sek": None, "paid_state": "failed"}, **kw)
        assert (failed[1].availability, failed[1].quality, failed[1].value) == ("missing", "failed", None)
        hidden = company_observations({**base, "insured_count": None, "insured_suppressed": True, "paid_sek": None,
                                       "paid_state": "suppressed"}, **kw)
        assert [o.availability for o in hidden] == ["suppressed", "suppressed"]
        unread = company_observations(None, **kw)
        assert all(o.availability == "missing" and o.value is None and not o.evidence_refs for o in unread)

    def test_korningens_spar_ur_journalen(self):
        events = [
            {"type": "run_started", "team": "aktuarie", "agent": "actuary_agent", "model_role": "deep",
             "versions": {"policy_id": "harness-v1"}},
            {"type": "model_returned", "model_ref": "b:small", "fallback_from": ["a:big"]},
            {"type": "tool_intent", "tool_call_id": "1", "skill": "get_company_metrics",
             "operation": "get_company_metrics", "kind": "read", "effective": "AGENT"},
            {"type": "tool_completed", "tool_call_id": "1", "skill": "get_company_metrics", "status": "done"},
            {"type": "tool_denied", "tool_call_id": "2", "skill": "write_draft", "status": "denied"},
            {"type": "model_returned", "model_ref": "b:small", "fallback_from": []},
        ]
        trace = run_trace("run-1", events)
        assert (trace.models, trace.fallback_from, trace.policy_id) == (("b:small",), ("a:big",), "harness-v1")
        assert [(t.skill, t.status) for t in trace.tools] == [("get_company_metrics", "done"), ("write_draft", "denied")]
        assert not trace.complete and trace.steps is None  # inget run_ended: avbruten körning
        ended = run_trace("run-1", [*events, {"type": "run_ended", "status": "completed",
                                              "usage": {"steps": 2, "cost_usd": 0.01, "elapsed_seconds": 3.0}}])
        assert (ended.complete, ended.steps, ended.status) == (True, 2, "completed")
        assert not run_trace("run-1", [*events, {"type": "run_ended"}], corrupt=True).complete

    def test_leveransen_skrivs_en_gang(self, tmp_path):
        store = DeliveryStore(tmp_path)
        receipt = store.publish("FLOW-000001", {"rapport.md": b"# R"}, {"team": "aktuarie"})
        assert store.read("FLOW-000001", 1, "rapport.md", receipt["files"]["rapport.md"]) == b"# R"
        with pytest.raises(DeliveryError, match="finns redan"):
            store.publish("FLOW-000001", {"rapport.md": b"# Ny"}, {})
        for flow_id, files in (("../ut", {"rapport.md": b"x"}), ("FLOW-000002", {"annat.exe": b"x"}),
                               ("FLOW-000003", {"rapport.md": b""})):
            with pytest.raises(DeliveryError):
                store.publish(flow_id, files, {})
