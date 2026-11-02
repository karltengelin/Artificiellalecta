"""Aktuariens riktiga analysmotor, dataväg, dialog, behörigheter och HTTP-kontrakt."""

import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from agents.actuarial_dialogue import ActuarialDialogue
from agents.actuarial_workbench import Workbench, WorkbenchInput
from agents.gateways import GatewayError
from ai import AIClient, AIConfig
from ai.providers.fake import FakeProvider, text_result, tool_call_result
from ai.tracing import MemoryTraceSink
from analytics.actuarial_experience import (
    fit_mortality,
    poisson_interval,
)
from models import (
    ActuarialConversation,
    ActuarialDataset,
    ActuarialTurn,
    Base,
    ValuationRun,
)
from reporting.analysis_chart import render_analysis_chart
from services import Actor, OperationContext, ServiceLayer
from services.errors import AccessDeniedError, BlockedError, ConflictError
from services.operations.actuarial_analysis import DatasetInput, validated_dataset
from skills.calculation import actuarial_annuity as aa
from utils.migration_actuarial_workspace import (
    TABLES,
    migrate_actuarial_workspace,
)
from web.operator_auth import OperatorAuth

HUMAN = Actor.human("karl")
SYSTEM = OperationContext(actor=Actor.system("actuarial-worker"))


def client(script):
    fake = FakeProvider(script)
    config = AIConfig.from_dict({"providers": {"alpha": {"type": "fake", "api_key_env": "TEST_KEY"}},
        "models": {"alpha:test": {"price": {"input": 1, "output": 2}}},
        "roles": {"deep": {"model": "alpha:test"}, "standard": {"model": "alpha:test"}}})
    return AIClient(config, provider_overrides={"alpha": fake}, sink=MemoryTraceSink(), environ={}), fake


def answer(summary="Vilket värderingsdatum vill du utgå från?", refs=()):
    return text_result(json.dumps({"status": "needs_information", "summary": summary,
        "questions": ["Vilken period gäller uppdraget?"], "limitations": [], "analysis_refs": list(refs)}, ensure_ascii=False))


def tool(action, name="", args=None, ident="tool-1"):
    return tool_call_result("actuarial_workbench", {"data": {"action": action, "name": name,
        "arguments_json": json.dumps(args or {})}, "reason": "Utför operatörens aktuariella uppdrag"}, call_id=ident)


def analyze(service, name, **params):
    return service.execute("perform_actuarial_analysis", SYSTEM,
        {"analysis": name, "parameters_json": json.dumps(params)}).output.payload


def register(service, ident="experience-v1", rows=None, kind="mortality"):
    rows = rows or [{"year": 2025, "age": 70, "lives": 10000, "exposure_years": 10000, "deaths": 100}]
    return service.execute("register_actuarial_dataset", OperationContext(actor=HUMAN, reason="Avstämt testunderlag"),
        {"id": ident, "kind": kind, "title": "Syntetiskt erfarenhetsunderlag", "source_ref": "TEST-EXPERIENCE",
         "definition": "Syntetisk kohort. Central exponering i personår; en cell per år och uppnådd ålder.",
         "synthetic": True, "rows_json": json.dumps(rows)})


def saved_run(web):
    result = web.service.execute("run_valuation", OperationContext(actor=HUMAN, reason="Syntetiskt analysscenario"),
        {"valuation_date": "2026-09-30", "purpose": "scenario", "basis_code": "SIM-V-2026-01", "curve_code": "FI-SIM-2026-10"})
    return str(result.output.run_id)


def test_garwood_independent_known_cases_and_large_count():
    lo, hi = poisson_interval(0)
    assert lo == 0 and hi == pytest.approx(-math.log(.025), rel=1e-10)
    lo, hi = poisson_interval(10)
    assert lo == pytest.approx(4.7953887, rel=1e-7)
    assert hi == pytest.approx(18.390356, rel=1e-7)
    lo, hi = poisson_interval(10000000)
    assert 0 < lo < 10000000 < hi


def test_complementary_suppression_protects_single_hidden_year(web):
    register(web.service, rows=[{"year": 2024, "age": 70, "lives": 1000, "exposure_years": 1000, "deaths": 20},
                                {"year": 2025, "age": 70, "lives": 1000, "exposure_years": 1000, "deaths": 3}])
    out = analyze(web.service, "experience", dataset_id="experience-v1", basis_code="SIM-R-2026-01")
    assert out["observed"] == 23
    assert all(r["observed"] is None and r["ae_ratio"] is None for r in out["rows"])
    assert out["synthetic"] and out["code_checksum"]


def test_source_import_permissions_immutability_validation_and_tampering(web):
    register(web.service)
    with pytest.raises(ConflictError):
        register(web.service)
    inp = {"id": "bad", "kind": "mortality", "title": "Testunderlag", "source_ref": "TEST",
        "definition": "Syntetiskt kontrollunderlag", "synthetic": True,
        "rows_json": json.dumps([{"year": 2025, "age": 70, "lives": 10, "exposure_years": 100, "deaths": 11}])}
    with pytest.raises(ValueError):
        validated_dataset(DatasetInput(**inp))
    with pytest.raises(AccessDeniedError):
        web.service.execute("register_actuarial_dataset", OperationContext(actor=Actor.agent("actuary_agent", "aktuarie"),
            reason="Försök skapa utfall"), inp)
    with web.session_factory() as s:
        row = s.get(ActuarialDataset, "experience-v1")
        row.content = {**row.content, "source_ref": "CHANGED"}
    with pytest.raises(BlockedError):
        analyze(web.service, "experience", dataset_id="experience-v1", basis_code="SIM-R-2026-01")


def test_scenario_cashflows_and_input_integrity(web):
    ident = saved_run(web)
    base = analyze(web.service, "scenario", run_id=ident)
    assert base["delta_fta_sek"] == 0
    rates = analyze(web.service, "scenario", run_id=ident, rate_shift_bp=100)
    longer = analyze(web.service, "scenario", run_id=ident, mortality_intensity_factor=.8)
    costs = analyze(web.service, "scenario", run_id=ident, expense_factor=1.1)
    assert rates["delta_fta_sek"] < 0 and longer["delta_fta_sek"] > 0 and costs["delta_fta_sek"] > 0
    cf = analyze(web.service, "cashflows", run_id=ident)
    assert abs(cf["reconciliation_difference_sek"]) < .01
    assert len(cf["rows"]) > 30
    with web.session_factory() as s:
        run = s.get(ValuationRun, uuid4())
        assert run is None
        run = s.scalar(select(ValuationRun))
        assert run.status == "draft" and run.purpose == "scenario"
        run.fta_sek += 1
    with pytest.raises(BlockedError):
        analyze(web.service, "cashflows", run_id=ident)


def test_mortality_model_temporal_holdout_and_curve(web):
    rows = [{"year": y, "age": age, "lives": 10000, "exposure_years": 10000, "deaths": 80}
            for y in range(2020, 2026) for age in (65, 75)]
    register(web.service, rows=rows)
    out = analyze(web.service, "fit_mortality", dataset_id="experience-v1", basis_code="SIM-V-2026-01")
    assert out["training_through"] == 2024 and out["validation_year"] == 2025
    mutated = [dict(r, deaths=150) if r["year"] == 2025 else r for r in rows]
    with web.session_factory() as s:
        from models import ValuationBasis
        mortality = aa.MortalityBasis.from_assumptions(s.scalar(select(ValuationBasis).where(
            ValuationBasis.code == "SIM-V-2026-01")).assumptions["mortality"])
    second = fit_mortality(mutated, mortality)
    assert second["candidate"]["improvement"] == out["candidate"]["improvement"]
    assert second["candidate"]["intensity_factor"] == out["candidate"]["intensity_factor"]
    assert second["candidate"]["validation_deviance"] != out["candidate"]["validation_deviance"]
    curve = analyze(web.service, "mortality_curve", basis_code="SIM-R-2026-01", birth_year=1960)
    assert curve["rows"][0]["survival"] == 1 and curve["rows"][-1]["survival"] < .2


def test_agent_can_investigate_before_first_saved_base_and_pin_source(web):
    args = {"valuation_date": "2026-09-30", "basis_code": "SIM-V-2026-01", "curve_code": "FI-SIM-2026-10"}
    base = analyze(web.service, "scenario", **args)
    changed = analyze(web.service, "scenario", **args, mortality_intensity_factor=.8,
                      source_checksum=base["extract_checksum"])
    assert base["base_status"] == "unsaved" and changed["delta_fta_sek"] > 0
    cf = analyze(web.service, "cashflows", **args)
    assert abs(cf["reconciliation_difference_sek"]) < .01
    with pytest.raises(BlockedError, match="ändrats"):
        analyze(web.service, "scenario", **args, source_checksum="0"*64)
    with web.session_factory() as session:
        assert session.scalar(select(ValuationRun)) is None


def test_behavior_wilson_and_expense_data(web):
    register(web.service, ident="behavior", kind="behavior", rows=[{"year": 2025, "event": "retirement",
        "eligible": 100, "events": 40, "expected_rate": .3}])
    behavior = analyze(web.service, "experience", dataset_id="behavior")
    row = behavior["rows"][0]
    assert row["lower_95"] < .4 < row["upper_95"]
    register(web.service, ident="costs", kind="expenses", rows=[{"year": 2025, "state": "deferred",
        "lives": 100, "exposure_years": 100, "actual_sek": 20000, "expected_sek": 18000}])
    cost = analyze(web.service, "experience", dataset_id="costs")
    assert cost["rows"][0]["difference_sek"] == 2000


def test_chart_escapes_text_keeps_missing_gaps_and_rejects_nonfinite():
    rows = [{"age": 60, "value": .1}, {"age": 61, "value": None}, {"age": 62, "value": .2}]
    svg = render_analysis_chart(rows, title="<script>bad</script>", x="age", y="value")
    assert "<script>" not in svg and "&lt;script&gt;" in svg
    assert "DM Sans" in svg and "#6951CF" in svg
    assert svg.count("<circle") == 2 and 'fill="none"' not in svg
    with pytest.raises(ValueError):
        render_analysis_chart([{"x": 1, "y": float("nan")}], title="Test", x="x", y="y")


def test_dialogue_persistence_idempotency_scope_and_cancel(web, tmp_path):
    ai, _fake = client([answer(), answer("Vilken grund vill du jämföra med?")])
    dialogue = ActuarialDialogue(web.service, web.service, ai, journal_dir=tmp_path)
    ident, key = uuid4().hex, uuid4().hex
    turn = dialogue.submit(ident, "Undersök dödligheten", actor=HUMAN, key=key)
    assert dialogue.submit(ident, "Undersök dödligheten", actor=HUMAN, key=key) == turn
    with pytest.raises(ConflictError):
        dialogue.submit(ident, "Nytt uppdrag", actor=HUMAN, key=uuid4().hex)
    assert dialogue.process(turn) and not dialogue.process(turn)
    reloaded = ActuarialDialogue(web.service, web.service, ai, journal_dir=tmp_path)
    assert reloaded.view(ident, HUMAN)["turns"][0]["status"] == "completed"
    with pytest.raises(Exception, match="saknas"):
        reloaded.view(ident, Actor.human("other"))
    follow = reloaded.submit(ident, "Visa också osäkerheten", actor=HUMAN, key=uuid4().hex)
    reloaded.interrupt(ident, follow, HUMAN)
    assert not reloaded.process(follow)


def test_real_harness_selects_analysis_and_fabricated_reference_is_rejected(web, tmp_path):
    ai, fake = client([tool("catalog"), tool("analyze", "mortality_curve", {
        "basis_code": "SIM-R-2026-01", "birth_year": 1960}, ident="tool-2"), answer(refs=("fabricated",))])
    dialog = ActuarialDialogue(web.service, web.service, ai, journal_dir=tmp_path)
    ident = uuid4().hex
    turn = dialog.submit(ident, "Visa dödlighetskurvan", actor=HUMAN, key=uuid4().hex)
    dialog.process(turn)
    view = dialog.view(ident, HUMAN)
    assert view["turns"][0]["status"] == "needs_human"
    assert any(d["kind"] == "analysis" for d in view["deliveries"])
    assert {t.name for t in fake.requests[0].tools} == {"actuarial_workbench", "list_regulatory_documents", "read_regulatory_document", "write_draft"}
    with pytest.raises(ValueError, match="inte aktivt"):
        Workbench(web.service, web.service, ident).invoke("aktuarie", view["turns"][0]["run_id"],
            WorkbenchInput(action="catalog", name="", arguments_json="{}"))
    with pytest.raises(GatewayError):
        Workbench(web.service, web.service, ident).invoke("compliance", "fake", WorkbenchInput(
            action="catalog", name="", arguments_json="{}"))


def test_quantitative_claim_without_any_tool_is_not_a_completed_delivery(web, tmp_path):
    ai, _ = client([answer("FTA är 1234567 kronor.")])
    dialog = ActuarialDialogue(web.service, web.service, ai, journal_dir=tmp_path)
    ident = uuid4().hex
    turn = dialog.submit(ident, "Vad är vår FTA?", actor=HUMAN, key=uuid4().hex)
    dialog.process(turn)
    assert dialog.view(ident, HUMAN)["turns"][0]["status"] == "needs_human"


def test_web_dialogue_authenticated_submission_and_followup(web, tmp_path):
    ai, _ = client([answer(), answer()])
    console = ActuarialDialogue(web.service, web.service, ai, journal_dir=tmp_path)
    web.app.state.actuarial_dialogue = console
    web.app.state.operator_auth = OperatorAuth("karl", PasswordHasher().hash("syntetisk-dialoglosenfras"))
    origin = {"Origin": "https://testserver"}
    with TestClient(web.app, base_url="https://testserver") as http:
        assert "Logga in" in http.get("/team/aktuarie/dialog").text
        login = http.get("/logga-in")
        assert http.post("/logga-in", data={"username": "karl", "password": "syntetisk-dialoglosenfras",
            "csrf_token": login.context["session_csrf"]}, headers=origin, follow_redirects=False).status_code == 303
        page = http.get("/team/aktuarie/dialog")
        ident = page.context["conversation_id"]
        form = {"message": "Hjälp mig undersöka våra antaganden", "submission_key": page.context["submission_key"],
                "csrf_token": page.context["operator_csrf"]}
        assert http.post("/team/aktuarie/dialog/"+ident, data=form, headers={"Origin":"https://evil.test"}).status_code == 403
        assert http.post("/team/aktuarie/dialog/"+ident, data={**form,"actor":"other"}, headers=origin).status_code == 400
        posted = http.post("/team/aktuarie/dialog/"+ident, data=form, headers=origin)
        assert posted.status_code == 200 and "Vilket värderingsdatum" in posted.text
        assert "Fortsätt samtalet" in posted.text and posted.headers["cache-control"] == "no-store"


def test_full_dialogue_chart_report_and_followup_reference(web, tmp_path):
    references = {}

    def chart(request):
        receipt = json.loads(request.messages[-1].tool_results[0].content)["output"]["payload"]
        references["analysis"] = receipt["id"]
        return tool("chart", args={"analysis_id": receipt["id"], "title": "Kohortens överlevnad",
            "x": "age", "y": "survival", "unit": "Andel kvar i livet"}, ident="chart-call")

    def report(_request):
        receipt = json.loads(_request.messages[-1].tool_results[0].content)["output"]["payload"]
        references["chart"] = receipt["id"]
        return tool("report", args={"title": "Dödlighetsanalys", "conclusion": "Kurvan beskriver grundens antaganden.",
            "analysis_ids": [references["analysis"]], "chart_ids": [references["chart"]]}, ident="report-call")

    def finish(_request):
        return answer("Underlaget och diagrammet visar grundens antaganden.", [references["analysis"]])

    ai, _fake = client([tool("analyze", "mortality_curve", {"basis_code": "SIM-R-2026-01", "birth_year": 1960}),
                       chart, report, finish])
    dialog = ActuarialDialogue(web.service, web.service, ai, journal_dir=tmp_path)
    ident = uuid4().hex
    turn = dialog.submit(ident, "Visa överlevnaden och gör en rapport", actor=HUMAN, key=uuid4().hex)
    assert dialog.process(turn)
    view = dialog.view(ident, HUMAN)
    assert view["turns"][0]["status"] == "completed"
    assert {d["kind"] for d in view["deliveries"]} == {"analysis", "chart", "report"}
    chart_ref = next(d for d in view["deliveries"] if d["kind"] == "chart")
    report_ref = next(d for d in view["deliveries"] if d["kind"] == "report")
    assert "<svg" in dialog.delivery(ident, chart_ref["id"], HUMAN)["content"]["svg"]
    md = dialog.delivery(ident, report_ref["id"], HUMAN)["content"]["markdown"]
    from reporting import ReportMetadata, render_report
    from reporting.analysis_chart import analysis_drawing
    from reporting.template import Fonts

    drawing = analysis_drawing(dialog.delivery(ident, chart_ref["id"], HUMAN)["content"]["svg"], font_name="Helvetica")
    assert render_report(md, ReportMetadata(title="Dödlighetsanalys"), fonts=Fonts.helvetica(),
                         charts={chart_ref["id"]:drawing}).startswith(b"%PDF")
    with pytest.raises(Exception, match="Dialog"):
        dialog.delivery(uuid4().hex, chart_ref["id"], HUMAN)


def test_basis_proposal_uses_existing_approval_and_is_not_replayed(web, tmp_path):
    from services import ProductRuleCatalog

    web.service.rules = ProductRuleCatalog(today=date(2026, 11, 2))
    ai, _ = client([])
    dialog = ActuarialDialogue(web.service, web.service, ai, journal_dir=tmp_path)
    ident = uuid4().hex
    turn_id = dialog.submit(ident, "Pröva antagandena", actor=HUMAN, key=uuid4().hex)
    with web.session_factory() as s:
        t = s.get(ActuarialTurn, turn_id)
        t.status = "running"
        run_id = t.run_id
        from models import ValuationBasis
        basis = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "SIM-V-2026-01"))
        assumptions = basis.assumptions
    bench = Workbench(web.service, web.service, ident)
    receipt = bench.invoke("aktuarie", run_id, WorkbenchInput(action="analyze", name="mortality_curve",
        arguments_json=json.dumps({"basis_code":"SIM-V-2026-01", "birth_year":1960}))).payload
    proposal = {"code":"SIM-V-2027-01", "title":"Testförslag", "assumptions":assumptions,
                "supersedes_code":"SIM-V-2026-01", "source_refs":"Ersätts av källbundna referenser"}
    args = WorkbenchInput(action="propose_basis", name="", arguments_json=json.dumps({
        "reason":"Syntetiskt test av förslagsvägen", "analysis_ids":[receipt["id"]], "proposal_json":json.dumps(proposal)}))
    first = bench.invoke("aktuarie", run_id, args).payload
    second = bench.invoke("aktuarie", run_id, args).payload
    assert first["id"] == second["id"]
    assert first["content"]["pending_approval"] and not first["content"]["executed"]
    with web.session_factory() as s:
        assert s.scalar(select(ValuationBasis).where(ValuationBasis.code == "SIM-V-2027-01")) is None


@pytest.mark.postgres
def test_actuarial_migration_and_concurrent_submission_postgres():
    import os
    from dataclasses import replace

    from sqlalchemy import create_engine
    from sqlalchemy.exc import DBAPIError

    from services.db import session_factory_for
    from tests.test_services_postgres import TEST_URL, isolated_schema
    from utils.agent_roles import AKTUARIE
    from utils.demo_data import create_demo_database

    if not TEST_URL:
        pytest.skip("Isolerad Postgres saknas")
    with isolated_schema() as db:
        Base.metadata.create_all(db.engine, tables=[t for t in Base.metadata.sorted_tables if t.name not in TABLES])
        assert not migrate_actuarial_workspace(db.engine).applied
        assert not set(TABLES) & set(inspect(db.engine).get_table_names())
        assert migrate_actuarial_workspace(db.engine, dry_run=False).applied
        assert migrate_actuarial_workspace(db.engine, dry_run=False).already_applied
        service = ServiceLayer(session_factory=db.session_factory)
        ai, _ = client([])
        dialog = ActuarialDialogue(service, service, ai)
        ident = uuid4().hex
        with db.session_factory() as session:
            session.add(ActuarialConversation(id=ident, title="Samtidighet", created_by="karl"))
        def submit_once(_):
            try:
                return dialog.submit(ident, "Analysera", actor=HUMAN, key=uuid4().hex)
            except ConflictError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit_once, (1, 2)))
        assert sum(r is not None for r in results) == 1
        # Serverns domänarbetare kan räkna, medan den faktiska agentrollen
        # fortfarande saknar rätt till individutdrag, dialog och observationsdata.
        role_url = os.environ.get("SERVICES_TEST_AKTUARIE_POSTGRES_URL") or os.environ.get("SERVICES_TEST_AGENT_POSTGRES_URL")
        assert role_url and role_url != os.environ.get("AGENT_AKTUARIE_DATABASE_URL")
        create_demo_database(db.engine, with_proposals=False)
        role_engine = create_engine(role_url, connect_args={"options": f"-csearch_path={db.name}"})
        try:
            with role_engine.connect() as conn:
                login = conn.exec_driver_sql("SELECT current_user").scalar_one()
            with db.engine.begin() as conn:
                for statement in replace(AKTUARIE, role=login).statements(db.name):
                    conn.exec_driver_sql(statement)
            for table in ("valuation_extracts", "actuarial_datasets", "actuarial_conversations", "actuarial_analyses"):
                with pytest.raises(DBAPIError), role_engine.begin() as conn:
                    conn.exec_driver_sql(f"SELECT * FROM {table}")
            restricted = ServiceLayer(session_factory=session_factory_for(role_engine),
                validation_session_factory=db.session_factory, agent_role="agent_aktuarie")
            turn_id = next(r for r in results if r is not None)
            with db.session_factory() as session:
                turn = session.get(ActuarialTurn, turn_id)
                turn.status = "running"
                run_id = turn.run_id
            bench = Workbench(service, restricted, ident)
            read = bench.invoke("aktuarie", run_id, WorkbenchInput(action="read", name="list_valuation_bases", arguments_json="{}"))
            assert read.payload["kind"] == "data"
            computed = bench.invoke("aktuarie", run_id, WorkbenchInput(action="analyze", name="scenario",
                arguments_json=json.dumps({"valuation_date":"2026-09-30", "basis_code":"SIM-V-2026-01", "curve_code":"FI-SIM-2026-10"})))
            assert computed.payload["content"]["base_status"] == "unsaved"
            assert "policy_id" not in json.dumps(computed.model_dump())
        finally:
            role_engine.dispose()
