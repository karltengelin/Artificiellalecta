"""Produktrapporten v0 (A2, B-042): beståndets och premiernas aggregat och flödet till godkänd leverans.

Testleverantör och SQLite i minnet; inga riktiga modellanrop och ingen Lakebase. Läsdag 2026-10-27,
samma demobestånd som bolagsfrågan (tests/test_agents_questions.py).
"""

import json
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from agents import compile_profile
from agents.assignments import PRODUCT_REPORT_FIXED_LIMITATIONS, request_for_product_report
from agents.ecosystem import Ecosystem
from agents.flows.product_reports import ProductReportConsole
from agents.flows.store import FlowError
from agents.skills import SkillRegistry
from ai import AIClient, AIConfig
from ai.providers.fake import FakeProvider, text_result, tool_call_result
from ai.tracing import MemoryTraceSink
from analytics.portfolio_snapshot import COMPLEMENTARY, PRIMARY, birth_year, cohort_of, suppress_counts, suppress_sets
from reporting import ReportMetadata, render_report
from reporting.template import Fonts
from services import Actor, MemoryEventLog, OperationContext, OperationKind, ServiceLayer, default_registry
from services.db import session_factory_for
from services.errors import InvalidInputError
from services.operations import common
from utils.demo_data import create_demo_database

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 10, 27)
KARL = Actor.human("karl")
AGENT = OperationContext(actor=Actor.agent("actuary_agent", team="aktuarie"))


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


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


@pytest.fixture
def demo():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False, today=TODAY)
    yield session_factory_for(engine)
    engine.dispose()


@pytest.fixture
def service(demo):
    return ServiceLayer(session_factory=demo, events=MemoryEventLog())


def read(service, op, year=2025, ctx=AGENT):
    return service.execute(op, ctx, {"year": year}).output


class TestAggregat:
    def test_bestandet_summerar_och_saknar_personuppgifter(self, service):
        s = read(service, "get_portfolio_snapshot", 2026)
        shown = sum(c.policies or 0 for c in s.by_state)
        hidden = [c for c in s.by_state if c.policies is None]
        # De dolda lägena omfattar tillsammans minst tio försäkringar, så ingen kan räknas fram ur totalen
        assert s.policies_total == 35 and (not hidden or s.policies_total - shown >= 10)
        assert {c.hidden_reason for c in hidden} <= {PRIMARY, COMPLEMENTARY}
        assert s.as_of_date == TODAY and s.min_cell_size == 10
        raw = s.model_dump_json()
        assert not any(ch.isdigit() and len(ch) == 12 for ch in raw.split('"'))  # inga personnummer
        assert "first_name" not in raw and "salary" not in raw

    def test_kohorter_doljs_med_kompletterande_doljning(self, service):
        cells = {c.key: c for c in read(service, "get_portfolio_snapshot", 2026).by_cohort}
        hidden = [c for c in cells.values() if c.policies is None]
        assert hidden and {c.hidden_reason for c in hidden} <= {PRIMARY, COMPLEMENTARY}
        in_force = read(service, "get_portfolio_snapshot", 2026).policies_in_force
        assert in_force - sum(c.policies or 0 for c in cells.values()) >= 10

    def test_premier_per_manad_stammer_med_ledningsmattet(self, service):
        flows = read(service, "get_premium_flows", 2025)
        assert [m.month.month for m in flows.months] == list(range(1, 13)) and flows.period_to == date(2026, 1, 1)
        november = next(m for m in flows.months if m.month == date(2025, 11, 1))
        metrics = service.execute("get_company_metrics", AGENT, {"month": "2025-11-01"}).output
        assert november.paid_sek == metrics.paid_sek
        assert flows.total_paid_sek == sum(m.paid_sek for m in flows.months)
        assert flows.transfers_in_sek is None and "Flytt" in flows.transfers_note

    def test_innevarande_manad_ingar_inte(self, service):
        flows = read(service, "get_premium_flows", 2026)
        assert flows.months[-1].month == date(2026, 9, 1) and flows.period_to == date(2026, 10, 1)

    def test_litet_bestand_doljs(self, insurance_db):
        small = ServiceLayer(session_factory=insurance_db.session_factory, events=MemoryEventLog())
        s = read(small, "get_portfolio_snapshot", 2026)
        assert s.policies_total is None and s.insured_in_force is None
        flows = read(small, "get_premium_flows", 2025)
        assert flows.total_state == "suppressed" and flows.total_paid_sek is None
        assert all(m.paid_sek is None or m.persons == 0 for m in flows.months)

    @pytest.mark.parametrize("year", [2027, 2022])
    def test_bara_ar_med_historik(self, service, year):
        with pytest.raises(InvalidInputError):
            read(service, "get_portfolio_snapshot", year)

    def test_agenten_far_inte_bredda_urvalet(self, service):
        with pytest.raises(InvalidInputError):
            service.execute("get_premium_flows", AGENT, {"year": 2025, "employer": "all"})

    def test_doljning_och_fodelsear(self):
        assert suppress_counts({"a": 0, "b": 5, "c": 12, "d": 30}) == {"b": PRIMARY, "c": COMPLEMENTARY}
        assert suppress_counts({"a": 15, "b": 20}) == {}
        months = {date(2025, 1, 1): {1, 2, 3}, date(2025, 2, 1): set(range(1, 12))}
        assert suppress_sets(months) == {date(2025, 1, 1): PRIMARY, date(2025, 2, 1): COMPLEMENTARY}
        assert (birth_year("196203150123"), birth_year("19620375012x"), birth_year("196213150123")) == (1962, None, None)
        assert birth_year("196203750123") == 1962  # samordningsnummer
        assert (cohort_of(1962), cohort_of(None)) == ("1960–1969", "okänt")


def summary(service, year=2025, conclusion=None, **overrides) -> str:
    persons = read(service, "get_premium_flows", year).total_persons
    return json.dumps({
        "year": year,
        "conclusion": conclusion or f"Under {year} betalade {persons} personer premier till produkten.",
        "key_findings": ["Beståndet är litet och flera grupper döljs."],
        "recommendations": ["Följ premieflödet månadsvis."],
        "limitations": [], **overrides,
    })


def responses(service, year=2025, **kw):
    return [
        tool_call_result("get_portfolio_snapshot", {"data": {"year": year}, "reason": None}, call_id="c1"),
        tool_call_result("get_premium_flows", {"data": {"year": year}, "reason": None}, call_id="c2"),
        text_result(summary(service, year, **kw)),
    ]


def console(demo, tmp_path, answers, renderer=fake_pdf) -> ProductReportConsole:
    service = ServiceLayer(session_factory=demo, events=MemoryEventLog())
    return ProductReportConsole.build(
        demo, trusted=service, actuary_service=service, ai=ai_client(FakeProvider(answers)), renderer=renderer,
        environment_id="demo", dataset_ref="demo:current", deliveries_dir=tmp_path / "leveranser",
        journal_dir=tmp_path / "runs",
    )


class TestFlodet:
    def test_rapport_till_godkand_leverans(self, demo, service, tmp_path):
        c = console(demo, tmp_path, responses(service))
        view = c.start(2025, "Inför styrelsemötet", KARL)
        assert (view.status, view.summarized, view.delivery_version) == ("waiting_gate", True, 1)
        report = c.delivery(view.flow_id, "rapport.md").decode("utf-8")
        headings = [line for line in report.splitlines() if line.startswith("## ")]
        assert headings == ["## 1. Sammanfattning", "## 2. Bestånd och rörelser", "## 3. Premier",
                            "## 4. Kapital och avkastning", "## 5. Avgifter och kostnader",
                            "## 6. Garanti och återbäring", "## 7. Risk- och dödlighetsutfall",
                            "## 8. Känslighet för produktparametrar", "## 9. Kundutfall och värde",
                            "## 10. Avvikelser och åtgärder", "## Begränsningar", "## Så togs rapporten fram"]
        assert report.count("Ej beräknat – ") == 4 and "| 2025-11 |" in report
        assert all(t in report for t in PRODUCT_REPORT_FIXED_LIMITATIONS)
        assert "från 4,5 % till 5,0 %" in report and "| 45 000,00 kr |" in report
        assert "Operatörens precisering: Inför styrelsemötet" in report
        flow = c.flow(view.flow_id)
        done = c.decide(view.flow_id, flow.version, KARL, decision="approved",
                        seen_hash=flow.gate_hashes["review"], note=None)
        assert (done.status, done.accepted, done.reviewed_by) == ("completed", True, "karl")
        assert [v.flow_id for v in c.list()] == [view.flow_id]

    def test_obelagt_tal_stoppar_sammanfattningen(self, demo, service, tmp_path):
        c = console(demo, tmp_path, responses(service, conclusion="Premierna ökade med 17 procent."))
        view = c.start(2025, "", KARL)
        assert view.status == "failed" and view.delivery_version is None

    def test_utan_lasning_godtas_ingen_sammanfattning(self, demo, service, tmp_path):
        c = console(demo, tmp_path, [text_result(summary(service, conclusion="Produkten fungerar."))])
        assert c.start(2025, "", KARL).status == "failed"

    def test_sammanfattning_for_annat_ar(self, demo, service, tmp_path):
        answers = responses(service, 2024)
        c = console(demo, tmp_path, answers)
        view = c.start(2025, "", KARL)
        assert view.status == "failed"

    def test_bara_operator_och_giltigt_ar(self, demo, tmp_path):
        c = console(demo, tmp_path, [])
        with pytest.raises(FlowError, match="inloggad operatör"):
            c.start(2025, "", Actor.agent("actuary_agent", team="aktuarie"))
        with pytest.raises(FlowError, match="Välj ett år"):
            c.start(2027, "", KARL)

    def test_uppdraget_ar_avsmalnat_till_lasning(self, service):
        eco = Ecosystem.load()
        request = request_for_product_report(2025, "Precisering")
        profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), service, request=request)
        visible = {d.skill for d in profile.visible()}
        assert {"get_portfolio_snapshot", "get_premium_flows"} <= visible
        assert not visible & {"write_draft", "delegate_to_team", "estimate_parameter_change_impact"}
        assert request.allowed_effects == {OperationKind.READ, OperationKind.COMPUTE}
        assert request.result_schema == "ProductReportSummary" and "underlag, inte instruktion" in request.background

    def test_riktig_export_klarar_rapporten(self, demo, service, tmp_path):
        def helvetica(markdown, metadata: ReportMetadata) -> bytes:
            return render_report(markdown, metadata, fonts=Fonts.helvetica())

        c = console(demo, tmp_path, responses(service), renderer=helvetica)
        view = c.start(2025, "", KARL)
        assert view.status == "waiting_gate"
        assert c.delivery(view.flow_id, "rapport.pdf").startswith(b"%PDF-")

    def test_ordningen_kraver_giltig_bestallning(self):
        from agents.flows.definitions.product_report import ProductReportOrder
        with pytest.raises(ValidationError):
            ProductReportOrder(year=2025, environment_id="demo", dataset_ref="d", policy_ref="p", extra=1)
