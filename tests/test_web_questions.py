"""P2-FRAGA-001 through HTTP → QuestionConsole → real report export; no external calls."""

import json
from dataclasses import replace
from datetime import date
from functools import partial
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
TEAM = "/team/aktuarie"


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


def test_preview_assets_are_served_locally_with_browser_module_mime_type(questions):
    client = questions.client
    for name in ("pdf-preview.mjs", "pdfjs-6.4.299.min.mjs", "pdfjs-worker-6.4.299.min.mjs"):
        asset = client.get(f"/static/{name}")
        assert asset.status_code == 200
        assert "javascript" in asset.headers["content-type"]
    assert client.get("/static/PDFJS_LICENSE.txt").status_code == 200


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


def test_explicit_workspace_connection_binds_environment_and_real_lakebase_role(questions, monkeypatch):
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
        _, _, c = database.build_question_services(settings, ai=ai, renderer=render_report)
        assert c.environment_id == mode and c.dataset_ref == f"{mode}:current"
        assert c.engine.runtime.service.agent_role == "agent_aktuarie"
        if mode == "lakebase":
            assert c.engine.runtime.service is restricted
    assert calls == ["aktuarie"]
