"""P2-FRAGA-001 through HTTP → QuestionConsole → real report export; no external calls."""

import json
import shutil
import subprocess
from dataclasses import replace
from datetime import date
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select

from agents.flows.questions import QuestionConsole
from ai import AIClient, AIConfig
from ai.providers.fake import FakeProvider, text_result, tool_call_result
from ai.tracing import MemoryTraceSink
from models import Flow, FlowStep, PremiumTransaction
from reporting import render_report
from reporting.template import Fonts
from services import AccessDeniedError, ServiceLayer
from services.operations import common
from web.operator_auth import OperatorAuth

ORIGIN = {"Origin": "https://testserver"}
TODAY = date(2026, 10, 27)
BASE = "/central/fragor"
TEAM = "/team/aktuarie/uppdrag"


def script(month="2025-11-01", status="answered", conclusion="Registrerat bestånd och betalmarkerade premier.", read=True):
    responses = [tool_call_result("get_company_metrics", {"data": {"month": month}, "reason": None})] if read else []
    return [*responses, text_result(json.dumps({"status": status, "month": month, "conclusion": conclusion,
            "limitations": ["Ingen bankavstämning."], "assumptions": [], "next_steps": []}))]


@pytest.fixture(scope="module")
def password_hash():
    return PasswordHasher().hash("syntetisk-testlosenfras")


@pytest.fixture
def questions(web, tmp_path, monkeypatch, password_hash):
    monkeypatch.setattr(common, "today", lambda: TODAY)
    web.app.state.settings = replace(web.app.state.settings, handler_id="legacy-user", operator_password_hash=password_hash)
    web.app.state.operator_auth = OperatorAuth("karl", password_hash)
    config = AIConfig.from_dict({
        "providers": {"test": {"type": "fake"}},
        "models": {"test:questions": {"price": {"input": 0.0, "output": 0.0},
                                      "capabilities": {"tools": True, "structured_output": True}}},
        "roles": {"deep": {"model": "test:questions"}, "standard": {"model": "test:questions"}},
    })
    def connect(responses=None, *, service=None, renderer=None):
        ai = AIClient(config, sink=MemoryTraceSink(), provider_overrides={"test": FakeProvider(responses or script())}, environ={})
        console = QuestionConsole.build(web.session_factory, trusted=web.service, actuary_service=service or web.service,
            ai=ai, renderer=renderer or partial(render_report, fonts=Fonts.helvetica()),
            environment_id="demo", dataset_ref="demo:current", deliveries_dir=tmp_path / "deliveries", journal_dir=tmp_path / "runs")
        web.app.state.question_console = console
        return console
    c = connect()
    with TestClient(web.app, base_url="https://testserver") as client:
        login_page = client.get("/logga-in")
        login = client.post("/logga-in", data={"username": "karl", "password": "syntetisk-testlosenfras",
                            "csrf_token": login_page.context["session_csrf"]}, headers=ORIGIN, follow_redirects=False)
        assert login.status_code == 303
        yield SimpleNamespace(client=client, c=c, connect=connect, db=web.session_factory, app=web.app, tmp=tmp_path)


def form(q, base=BASE, month="2025-11", **overrides):
    page = q.client.get(base)
    assert page.status_code == 200
    return {"csrf_token": page.context["operator_csrf"], "request_token": page.context["request_token"],
            "team": "aktuarie", "question_type": "portfolio_overview", "month": month, "note": "", **overrides}


def start(q, base=BASE, **overrides):
    response = q.client.post(base, data=form(q, base, **overrides), headers=ORIGIN, follow_redirects=False)
    assert response.status_code == 303, response.text
    page = q.client.get(response.headers["location"])
    assert page.status_code == 200, page.text
    return page


def decision(q, page, decision="approved", **overrides):
    return q.client.post(f"{BASE}/{page.context['assignment'].flow_id}/granska", headers=ORIGIN,
        data={"csrf_token": page.context["operator_csrf"], "version": page.context["flow"].version,
              "seen_hash": page.context["flow"].gate_hashes.get("review", ""), "decision": decision,
              "note": "Granskat", **overrides}, follow_redirects=False)


def test_normal_case_same_assignment_both_surfaces_pdf_and_verified_actor(questions):
    q = questions
    page = start(q, note="Visa underlaget")
    view = page.context["assignment"]
    assert view.requested_by == "karl" and view.requested_by != "legacy-user"
    assert view.status == "waiting_gate" and not view.accepted
    team = q.client.get(f"{TEAM}/{view.flow_id}")
    assert team.context["assignment"] == view
    assert "145 971,41" in page.text.replace("\u00a0", " ") and "35 personer" in page.text
    assert 'data-pdf-preview' in page.text and '<iframe' not in page.text
    assert f'data-pdf-url="{BASE}/{view.flow_id}/leverans/1/rapport.pdf"' in page.text
    assert "Svar och underlag" in page.text
    assert "raw_messages" not in page.text
    url = f"{BASE}/{view.flow_id}/leverans/1/rapport.pdf"
    pdf = q.client.get(url)
    assert pdf.content.startswith(b"%PDF-") and pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["cache-control"] == "no-store" and pdf.headers["x-frame-options"] == "SAMEORIGIN"
    md = q.client.get(url.replace("rapport.pdf", "rapport.md")).text
    for text in ("145 971,41 SEK", "P2-FRAGA-001 v1.0", "35 personer", "inte bankavstämt", "insured_registered_count"):
        assert text in md
    approved = decision(q, page)
    assert approved.status_code == 303
    done = q.client.get(approved.headers["location"])
    assert done.context["assignment"].accepted and "godkänd av karl" in done.text
    assert q.client.get(url).content == pdf.content
    assert q.client.get(BASE).context["items"] == q.client.get(TEAM).context["items"]


def test_trace_uses_same_journal_on_both_surfaces_and_escapes_text(questions):
    q = questions
    page = start(q)
    view = page.context["assignment"]
    path = q.tmp / "runs" / f"{view.run_id}.jsonl"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    started = next(event for event in events if event["type"] == "run_started")
    started["agent"] = '<script>alert("agent")</script>'
    started["raw_messages"] = "PRIVATE-CONVERSATION-MARKER"
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    traces = []
    for base in (BASE, TEAM, "/team/aktuarie"):
        detail = q.client.get(f"{base}/{view.flow_id}")
        assert detail.status_code == 200 and detail.headers["cache-control"] == "no-store"
        trace = detail.context["trace"]
        traces.append(trace)
        assert trace.complete and trace.models == ("test:questions",)
        assert trace.tools[0].skill == "get_company_metrics"
        assert "Avancerat körspår" in detail.text and "Direkt inom mandat" in detail.text
        assert "0.0000 USD" in detail.text and "Utfört" in detail.text
        assert '&lt;script&gt;' in detail.text and '<script>alert(' not in detail.text
        assert "PRIVATE-CONVERSATION-MARKER" not in detail.text
    assert traces[0] == traces[1] == traces[2]


@pytest.mark.parametrize("journal", ["missing", "incomplete", "unreadable"])
def test_trace_gaps_do_not_hide_report_or_review_and_do_not_invent_usage(questions, monkeypatch, journal):
    q = questions
    page = start(q)
    view = page.context["assignment"]
    path = q.tmp / "runs" / f"{view.run_id}.jsonl"
    if journal == "missing":
        path.unlink()
    elif journal == "incomplete":
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        events = [event for event in events if event["type"] != "run_ended"]
        path.write_text("\n".join(json.dumps(event) for event in events) + '\n{"broken":', encoding="utf-8")
    else:
        def unreadable(_):
            raise OSError("PRIVATE-DATABASE-ERROR")
        monkeypatch.setattr(q.c, "trace", unreadable)
    for base in (BASE, TEAM):
        detail = q.client.get(f"{base}/{view.flow_id}")
        assert detail.status_code == 200
        assert "Godkänn leveransen" in detail.text and "data-pdf-preview" in detail.text
        if journal == "missing":
            assert "Körjournalen saknas" in detail.text and detail.context["trace"] is None
        elif journal == "incomplete":
            assert "Journalen är ofullständig" in detail.text
            assert not detail.context["trace"].complete
            assert "Slutstatus saknas" in detail.text and "Okänt antal" in detail.text
            assert "<dt>Registrerad kostnad</dt><dd>Okänd</dd>" in detail.text
        else:
            assert "Körspåret kunde inte läsas" in detail.text and detail.context["trace_error"]
        assert "PRIVATE-DATABASE-ERROR" not in detail.text


def test_preview_assets_are_served_locally_with_browser_module_mime_type(questions):
    client = questions.client
    for name in ("pdf-preview.mjs", "pdfjs-6.4.299.min.mjs", "pdfjs-worker-6.4.299.min.mjs"):
        asset = client.get(f"/static/{name}")
        assert asset.status_code == 200
        assert "javascript" in asset.headers["content-type"]
    assert client.get("/static/PDFJS_LICENSE.txt").status_code == 200


def test_preview_cleanup_accepts_htmx_text_nodes():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node behövs för klientens livscykelprov")
    # Run the actual module; only the external PDF engine is replaced.
    script = r"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { pathToFileURL } from 'node:url';
const events = {};
const context = vm.createContext({URL, document: {
  addEventListener: (name, callback) => { events[name] = callback; },
}});
const filename = process.argv[1];
const source = new vm.SourceTextModule(fs.readFileSync(filename, 'utf8'), {
  context, initializeImportMeta: meta => { meta.url = pathToFileURL(filename).href; },
});
await source.link(() => new vm.SyntheticModule(['getDocument', 'GlobalWorkerOptions'], function () {
  this.setExport('getDocument', () => { throw Error('Unexpected PDF read'); });
  this.setExport('GlobalWorkerOptions', {});
}, {context}));
await source.evaluate();
const cleanup = events['htmx:beforeCleanupElement'];
assert.equal(typeof cleanup, 'function');
for (const elt of [null, {nodeType: 3}, {nodeType: 8}, {nodeType: 11},
                  {nodeType: 1, matches: () => false, querySelectorAll: () => []}]) {
  assert.doesNotThrow(() => cleanup({detail: {elt}}));
}
"""
    module = Path(__file__).resolve().parents[1] / "src/web/static/pdf-preview.mjs"
    result = subprocess.run([node, "--experimental-vm-modules", "--input-type=module", "-e", script, str(module)],
                            capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr


def test_repeated_form_only_starts_once_and_new_form_gets_new_assignment(questions):
    q = questions
    q.connect([*script(), *script()])
    data = form(q)
    first = q.client.post(BASE, data=data, headers=ORIGIN, follow_redirects=False)
    second = q.client.post(BASE, data=data, headers=ORIGIN, follow_redirects=False)
    assert first.status_code == second.status_code == 303
    assert first.headers["location"] == second.headers["location"]
    new = start(q)
    assert new.context["assignment"].flow_id not in first.headers["location"]
    assert len(q.app.state.question_console.list()) == 2


@pytest.mark.parametrize("base", [BASE, TEAM])
def test_reads_allowed_but_start_and_actions_need_session(questions, base):
    q = questions
    page = start(q)
    q.client.cookies.clear()
    assert q.client.get(base).status_code == 200
    assert q.client.post(base, data={"csrf_token": q.app.state.csrf_token}, headers=ORIGIN).status_code == 401
    for action in ("granska", "avbryt", "avstam"):
        response = q.client.post(f"{base}/{page.context['assignment'].flow_id}/{action}",
                                 data={"csrf_token": q.app.state.csrf_token}, headers=ORIGIN)
        assert response.status_code == 401


@pytest.mark.parametrize("change,status", [({"team":"compliance"},422), ({"question_type":"fta"},422),
    ({"month":"2026-10"},422), ({"month":"2025-10"},422), ({"month":"2026-99"},422),
    ({"note":"x"*501},422), ({"csrf_token":"forged"},403), ({"actor_id":"forged"},400),
    ({"environment_id":"lakebase"},400), ({"request_token":"forged"},409)])
def test_invalid_form_never_calls_model_or_creates_flow(questions, change, status):
    q = questions
    response = q.client.post(BASE, data=form(q, **change), headers=ORIGIN)
    assert response.status_code == status and not q.c.list()


def test_session_origin_and_session_bound_form_required(questions):
    q = questions
    data = form(q)
    assert q.client.post(BASE, data=data, headers={"Origin":"https://evil.invalid"}).status_code == 403
    assert not q.c.list()


def test_stale_hash_and_version_reject_and_rejection_links_new_assignment(questions):
    q = questions
    q.connect([*script(), *script()])
    page = start(q)
    assert decision(q, page, seen_hash="changed").status_code == 409
    assert decision(q, page, version=0).status_code == 409
    rejected = decision(q, page, decision="rejected")
    assert rejected.status_code == 303
    assert decision(q, page).status_code == 409
    view = q.client.get(rejected.headers["location"]).context["assignment"]
    assert view.status == "rejected" and not view.accepted
    replacement = start(q, supersedes=view.flow_id)
    assert replacement.context["assignment"].supersedes == view.flow_id


def test_tampered_report_is_not_displayed_downloaded_or_delivered(questions):
    q = questions
    page = start(q)
    flow_id = page.context["assignment"].flow_id
    path = q.tmp / "deliveries" / flow_id / "v1" / "rapport.pdf"
    path.write_bytes(b"altered")
    detail = q.client.get(f"{BASE}/{flow_id}")
    assert detail.status_code == 409 and "Granskning är spärrad" in detail.text
    assert "data-pdf-preview" not in detail.text and "Godkänn leveransen" not in detail.text
    assert q.client.get(f"{BASE}/{flow_id}/leverans/1/rapport.pdf").status_code == 409
    decision(q, page)
    assert not q.c.get(flow_id).accepted


def test_zero_is_value_and_small_cells_are_hidden(questions, insurance_db):
    q = questions
    q.connect(script(month="2026-09-01"))
    zero = start(q, month="2026-09")
    assert zero.context["observations"][1]["value"] == "0.00"
    q.connect(script(status="partial", conclusion="Underlaget är dolt."),
              service=ServiceLayer(session_factory=insurance_db.session_factory))
    hidden = start(q)
    assert all(obs["value"] is None for obs in hidden.context["observations"])
    assert "Dolt – småcellsskydd" in hidden.text and "10 000" not in hidden.text


def test_invalid_paid_date_is_missing_not_zero(questions):
    q = questions
    with q.db() as session:
        row = session.scalar(select(PremiumTransaction).where(PremiumTransaction.status == "paid"))
        row.paid_date = None
    q.connect(script(status="partial"))
    page = start(q)
    obs = page.context["observations"][1]
    assert obs["value"] is None and obs["availability"] == "missing" and obs["quality"] == "failed"
    assert "utan giltigt betaldatum" in page.text


def test_unsupported_question_is_valid_unavailable_result_without_fake_values(questions):
    q = questions
    q.connect(script(status="unavailable", conclusion="Historiskt månadsslutsbestånd saknas.", read=False))
    page = start(q, note="Vad var månadsslutsbeståndet?")
    assert page.context["assignment"].answer_status == "unavailable"
    assert all(obs["value"] is None for obs in page.context["observations"])
    assert "Saknas – inget värde visas" in page.text


def test_export_failure_stays_failed_without_delivery(questions):
    q = questions
    def fail(*_):
        raise ValueError("secret-export-detail")
    q.connect(renderer=fail)
    page = start(q)
    assert page.context["assignment"].status == "failed"
    assert page.context["assignment"].delivery_version is None
    assert "secret-export-detail" not in page.text and "Godkänn leveransen" not in page.text


def test_reconciliation_and_cancel_use_verified_actor(questions):
    q = questions
    page = start(q)
    fid = page.context["assignment"].flow_id
    with q.db() as session:
        flow = session.get(Flow, fid)
        flow.status = "reconciliation_required"
        row = session.scalar(select(FlowStep).where(FlowStep.flow_id == fid, FlowStep.step_key == "review"))
        row.status = "reconciliation_required"
    page = q.client.get(f"{TEAM}/{fid}")
    assert "Stäm av avbruten körning" in page.text
    result = q.client.post(f"{TEAM}/{fid}/avbryt", headers=ORIGIN, follow_redirects=False,
        data={"csrf_token":page.context["operator_csrf"], "version":page.context["flow"].version, "note":"Kontrollerat avbrott"})
    assert result.status_code == 303 and q.c.get(fid).status == "cancelled"


def test_unconnected_or_wrong_environment_is_unavailable(questions):
    q = questions
    q.c.environment_id = "lakebase"
    assert q.client.get(BASE).status_code == 503
    q.app.state.question_console = None
    page = q.client.get(TEAM)
    assert page.status_code == 503 and "inte anslutna" in page.text


@pytest.mark.parametrize("denied", [False, True], ids=["source-failure", "access-denied"])
def test_data_failure_never_uses_replacement_values_or_exposes_details(questions, monkeypatch, denied):
    q = questions
    service = ServiceLayer(session_factory=q.db)
    original = service.execute
    def fail(operation, *args, **kwargs):
        if operation == "get_company_metrics":
            if denied:
                raise AccessDeniedError("secret-source-address", operation=operation, actor_id="actuary_agent")
            raise RuntimeError("secret-source-address")
        return original(operation, *args, **kwargs)
    monkeypatch.setattr(service, "execute", fail)
    q.connect(script(status="unavailable", conclusion="Källan kunde inte läsas."), service=service)
    page = start(q)
    view = page.context["assignment"]
    assert not view.accepted
    assert not page.context["observations"] or all(obs["value"] is None for obs in page.context["observations"])
    assert "secret-source-address" not in page.text and "145\u00a0971,41" not in page.text


@pytest.mark.parametrize("builder_name", ["build_question_services", "build_actuary_services"])
def test_explicit_workspace_connection_binds_environment_and_real_lakebase_role(questions, monkeypatch, builder_name):
    import services.db
    from web import database
    q = questions
    with q.db() as session:
        engine = session.get_bind()
    monkeypatch.setattr(database, "build_engine", lambda _: engine)
    calls = []
    restricted = ServiceLayer(session_factory=q.db, validation_session_factory=q.db, agent_role="agent_aktuarie")
    def role(team):
        calls.append(team)
        return restricted
    monkeypatch.setattr(services.db, "agent_service_layer", role)
    ai = q.c.engine.runtime.ai
    for mode in ("demo", "svc_test", "lakebase"):
        settings = replace(q.app.state.settings, database=mode)
        built = getattr(database, builder_name)(settings, ai=ai, renderer=render_report)
        _, _, c = built[:3]
        assert c.environment_id == mode and c.dataset_ref == f"{mode}:current"
        assert c.engine.runtime.service.agent_role == "agent_aktuarie"
        if mode == "lakebase":
            assert c.engine.runtime.service is restricted
        if len(built) == 4:
            assert built[3].engine.runtime.service is c.engine.runtime.service
            assert built[3].environment_id == c.environment_id
    assert calls == ["aktuarie"]


# A3 bygger vidare på samma webbfixtur och inloggning; inga nya testdatabasroller.
REPORTS = "/team/aktuarie/rapporter"
BASES = "/team/aktuarie/antaganden"


def product_answers():
    return [
        tool_call_result("get_portfolio_snapshot", {"data": {"year": 2025}, "reason": None}, call_id="snapshot"),
        tool_call_result("get_premium_flows", {"data": {"year": 2025}, "reason": None}, call_id="premiums"),
        text_result(json.dumps({"year": 2025, "conclusion": "Rapporten beskriver bestånd och premieflöden.",
            "key_findings": ["Små grupper döljs."], "recommendations": ["Följ upp premieflödet."], "limitations": []})),
    ]


@pytest.fixture
def actuary(questions, monkeypatch):
    from agents.flows.product_reports import ProductReportConsole
    from services import ProductRuleCatalog

    q = questions
    monkeypatch.setattr(common, "today", lambda: date(2026, 11, 2))
    q.app.state.service = ServiceLayer(session_factory=q.db, rules=ProductRuleCatalog(today=date(2026, 11, 2)))
    question_console = q.connect(product_answers())
    q.reports = ProductReportConsole.build(q.db, trusted=q.app.state.service,
        actuary_service=ServiceLayer(session_factory=q.db, validation_session_factory=q.db, agent_role="agent_aktuarie"),
        ai=question_console.engine.runtime.ai, renderer=partial(render_report, fonts=Fonts.helvetica()),
        environment_id="demo", dataset_ref="demo:current", deliveries_dir=q.tmp / "products", journal_dir=q.tmp / "runs")
    q.app.state.product_report_console = q.reports
    return q


def product_form(q, **changes):
    p = q.client.get(REPORTS)
    assert p.status_code == 200
    return {"csrf_token": p.context["operator_csrf"], "request_token": p.context["request_token"],
            "year": "2025", "note": "", **changes}


def product_start(q):
    response = q.client.post(REPORTS, data=product_form(q), headers=ORIGIN, follow_redirects=False)
    assert response.status_code == 303, response.text
    return q.client.get(response.headers["location"])


def product_decision_form(page, **changes):
    return {"csrf_token": page.context["operator_csrf"], "request_token": page.context["request_token"],
        "version": page.context["flow"].version, "seen_hash": page.context["flow"].gate_hashes.get("review", ""),
        "decision": "approved", "note": "Kontrollerat", **changes}


def propose_basis(q, code="SIM-V-2027-01", original="SIM-V-2026-01"):
    from services import Actor, OperationContext
    ctx = OperationContext(actor=Actor.human("test_preparation"), reason="Syntetiskt grundförslag")
    s = q.app.state.service
    old = s.execute("get_valuation_basis", ctx, {"code": original}).output
    return s.execute("propose_valuation_basis", ctx, {"code": code, "title": "Ny testgrund",
        "assumptions": old.assumptions, "source_refs": "Testets erfarenhetsanalys", "supersedes_code": original}).output


def basis_form(q, code, **changes):
    p = q.client.get(f"{BASES}/{code}")
    assert p.status_code == 200
    return {"csrf_token": p.context["operator_csrf"], "request_token": p.context["request_token"],
        "checksum": p.context["basis"].checksum, "valid_from": "2027-03-31", "decision_ref": "Styrelse 2027-02",
        "note": "Otillräckligt underlag", **changes}


def test_a3_report_order_review_pdf_trace_and_actor(actuary):
    q = actuary
    p = product_start(q)
    assert p.status_code == 200, p.text
    a = p.context["assignment"]
    assert a.status == "waiting_gate" and a.requested_by == "karl"
    assert "Så togs rapporten fram" in p.text and "test:questions" in p.text
    assert p.context["trace"].complete and "get_portfolio_snapshot" in p.text
    assert q.client.get("/team/aktuarie").context["reports"][0].flow_id == a.flow_id
    assert "Väntande granskningar" in q.client.get("/team/aktuarie").text
    result = q.client.post(f"{REPORTS}/{a.flow_id}/granska", data=product_decision_form(p), headers=ORIGIN)
    assert result.context["assignment"].accepted
    assert result.context["assignment"].reviewed_by == "karl"
    pdf = q.client.get(f"{REPORTS}/{a.flow_id}/leverans/1/rapport.pdf")
    assert pdf.content.startswith(b"%PDF-") and pdf.headers["cache-control"] == "no-store"
    md = q.client.get(f"{REPORTS}/{a.flow_id}/leverans/1/rapport.md")
    assert "ej beräknat" in md.text.lower()
    assert "personal_id_number" not in result.text and "raw_messages" not in result.text


def test_a3_start_and_review_tokens_are_single_use(actuary):
    q = actuary
    data = product_form(q)
    first = q.client.post(REPORTS, data=data, headers=ORIGIN, follow_redirects=False)
    assert first.status_code == 303
    assert q.client.post(REPORTS, data=data, headers=ORIGIN).status_code == 409
    p = q.client.get(first.headers["location"])
    url = f"{REPORTS}/{p.context['assignment'].flow_id}/granska"
    decision = product_decision_form(p)
    assert q.client.post(url, data=decision, headers=ORIGIN).status_code == 200
    assert q.client.post(url, data=decision, headers=ORIGIN).status_code == 409
    assert len(q.reports.list()) == 1


@pytest.mark.parametrize("change,expected", [({"csrf_token":"fake"},403), ({"year":"2999"},422),
    ({"actor_id":"forged"},400), ({"environment_id":"lakebase"},400), ({"request_token":"fake"},409)])
def test_a3_invalid_report_form_does_not_start(actuary, change, expected):
    q = actuary
    assert q.client.post(REPORTS, data=product_form(q, **change), headers=ORIGIN).status_code == expected
    assert not q.reports.list()


def test_a3_report_forms_require_session_origin_and_environment(actuary):
    q = actuary
    data = product_form(q)
    assert q.client.post(REPORTS, data=data, headers={"Origin":"https://elsewhere"}).status_code == 403
    q.client.cookies.clear()
    assert q.client.post(REPORTS, data=data, headers=ORIGIN).status_code == 401
    q.reports.environment_id = "lakebase"
    assert q.client.get(REPORTS).status_code == 503


def test_a3_modified_delivery_cannot_be_reviewed_or_downloaded(actuary):
    q = actuary
    p = product_start(q)
    ident = p.context["assignment"].flow_id
    data = product_decision_form(p)
    (q.reports.store.root / ident / "v1/rapport.pdf").write_bytes(b"changed")
    detail = q.client.get(f"{REPORTS}/{ident}")
    assert detail.status_code == 409 and "Godkänn leveransen" not in detail.text
    assert q.client.get(f"{REPORTS}/{ident}/leverans/1/rapport.pdf").status_code == 409
    q.client.post(f"{REPORTS}/{ident}/granska", data=data, headers=ORIGIN)
    assert not q.reports.get(ident).accepted


def test_a3_report_can_be_rejected_and_foreign_flow_cannot_be_downloaded(actuary):
    q = actuary
    p = product_start(q)
    ident = p.context["assignment"].flow_id
    result = q.client.post(f"{REPORTS}/{ident}/granska",
        data=product_decision_form(p, decision="rejected"), headers=ORIGIN)
    assert result.context["assignment"].status == "rejected"
    assert q.client.get(f"{REPORTS}/{ident}/leverans/1/manifest.json").status_code == 404
    assert q.client.get(f"{REPORTS}/{ident}/leverans/2/rapport.pdf").status_code == 409
    assert q.client.get(f"{REPORTS}/FLOW-999999").status_code == 404


def test_a3_all_current_start_bases_and_readable_assumptions(actuary):
    q = actuary
    from services.valuation_bases import default_rows
    p = q.client.get(BASES)
    assert p.status_code == 200
    for b in default_rows():
        assert b.code in p.text
        detail = q.client.get(f"{BASES}/{b.code}")
        assert detail.status_code == 200, detail.text
        assert "Kontrollsumma · verifierad" in detail.text
    curve = q.client.get(f"{BASES}/FI-SIM-2026-10")
    assert "Löptid, år" in curve.text and "Spotränta" in curve.text
    assert "Deklarerad månadsavkastning" in q.client.get(f"{BASES}/AVK-SIM-2026-01").text


@pytest.mark.parametrize("action,state", [("anta","adopted"), ("avsla","rejected")])
def test_a3_human_can_adopt_or_reject_proposed_basis(actuary, action, state):
    q = actuary
    b = propose_basis(q)
    data = basis_form(q, b.code)
    result = q.client.post(f"{BASES}/{b.code}/{action}", data=data, headers=ORIGIN)
    assert result.status_code == 200 and result.context["basis"].status == state
    if action == "anta":
        assert result.context["basis"].adopted_by == "karl"
    assert q.client.post(f"{BASES}/{b.code}/{action}", data=data, headers=ORIGIN).status_code == 409


@pytest.mark.parametrize("change,status", [({"csrf_token":"fake"},403), ({"request_token":"fake"},409),
    ({"checksum":"fake"},409), ({"decision_ref":""},422), ({"valid_from":"invalid"},422),
    ({"actor":"forged"},400)])
def test_a3_basis_decision_form_controls(actuary, change, status):
    q = actuary
    b = propose_basis(q)
    r = q.client.post(f"{BASES}/{b.code}/anta", data=basis_form(q,b.code,**change), headers=ORIGIN)
    assert r.status_code == status, r.text
    assert q.client.get(f"{BASES}/{b.code}").context["basis"].status == "proposed"


def test_a3_guarantee_date_rule_is_shown_and_basis_remains_proposed(actuary):
    q = actuary
    b = propose_basis(q, "SIM-G-2027-01", "SIM-G-2026-01")
    r = q.client.post(f"{BASES}/{b.code}/anta", data=basis_form(q,b.code,valid_from="2026-11-01"), headers=ORIGIN)
    assert r.status_code == 422 and "tidigast nästa månadsförsta" in r.text
    assert r.context["basis"].status == "proposed"


def test_a3_basis_nonce_is_bound_to_code_and_session(actuary):
    q = actuary
    a = propose_basis(q)
    b = propose_basis(q, "SIM-V-2028-01")
    data = basis_form(q, a.code)
    assert q.client.post(f"{BASES}/{b.code}/anta", data=data, headers=ORIGIN).status_code == 409
    q.client.cookies.clear()
    assert q.client.post(f"{BASES}/{a.code}/anta", data=data, headers=ORIGIN).status_code == 401


def test_a3_overview_unavailable_modules_and_legacy_assignment_address(actuary):
    q = actuary
    p = q.client.get("/team/aktuarie")
    assert p.status_code == 200 and "Rapporteringsrytm" in p.text
    assert "Kommande registervyer" in p.text
    assert 'href="/team/aktuarie/varderingar"' in p.text
    assert 'aria-disabled="true"' in p.text  # Återstående arbetsvägar är fortfarande inaktiva.
    q.app.state.product_report_console = None
    p = q.client.get("/team/aktuarie")
    assert p.context["reports"] is None and "Antagandebiblioteket" in p.text
    q.connect(script(month="2026-01-01"))
    assignment = start(q, TEAM, month="2026-01")
    old = q.client.get(f"/team/aktuarie/{assignment.context['assignment'].flow_id}")
    assert old.status_code == 200 and old.context["assignment"] == assignment.context["assignment"]


def test_a3_internal_failure_is_sanitized_and_not_retried(actuary, monkeypatch):
    q = actuary
    def unavailable(*args, **kwargs):
        raise RuntimeError("SYNTHETIC_PRIVATE_DATABASE_DETAIL")
    monkeypatch.setattr(q.reports, "start", unavailable)
    data = product_form(q)
    r = q.client.post(REPORTS, data=data, headers=ORIGIN)
    assert r.status_code == 503 and "SYNTHETIC_PRIVATE_DATABASE_DETAIL" not in r.text
    assert q.client.post(REPORTS, data=data, headers=ORIGIN).status_code == 409


def test_a3_pdf_preview_accepts_new_routes_but_rejects_foreign_paths():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node behövs för klientens URL-prov")
    script = r"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {pathToFileURL} from 'node:url';
const filename = process.argv[1];
for (const [path, allowed] of [
  ['/team/aktuarie/rapporter/FLOW-000001/leverans/1/rapport.pdf', true],
  ['/team/aktuarie/uppdrag/FLOW-000001/leverans/1/rapport.pdf', true],
  ['/team/aktuarie/FLOW-000001/leverans/1/rapport.pdf', true],
  ['/central/fragor/FLOW-000001/leverans/1/rapport.pdf', true],
  ['/arenden/FLOW-000001/leverans/1/rapport.pdf', false],
  ['/team/aktuarie/rapporter/FLOW-000001/leverans/1/manifest.json', false],
  ['https://foreign.example/team/aktuarie/FLOW-000001/leverans/1/rapport.pdf', false],
]) {
  const fetched=[];
  const root = {dataset:{pdfUrl:path},querySelector:()=>({})};
  const context = vm.createContext({URL, AbortController, Uint8Array,
    window:{location:{href:'https://local.example/team/aktuarie/rapporter/FLOW-000001',origin:'https://local.example'}},
    document:{addEventListener:()=>{},querySelectorAll:()=>[root]},
    fetch:async url=>{fetched.push(String(url));return {ok:false};},
  });
  const module = new vm.SourceTextModule(fs.readFileSync(filename,'utf8'),{
    context,initializeImportMeta:meta=>{meta.url=pathToFileURL(filename).href;},
  });
  await module.link(()=>new vm.SyntheticModule(['getDocument','GlobalWorkerOptions'],function(){
    this.setExport('getDocument',()=>{throw Error('Unexpected PDF decode');});
    this.setExport('GlobalWorkerOptions',{});
  },{context}));
  await module.evaluate();
  module.namespace.mountPreviews();
  assert.equal(fetched.length,allowed?1:0,path);
}
"""
    module = Path(__file__).resolve().parents[1] / "src/web/static/pdf-preview.mjs"
    result = subprocess.run([node, "--experimental-vm-modules", "--input-type=module", "-e", script, str(module)],
                            capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr
