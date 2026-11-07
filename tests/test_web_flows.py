"""Handläggar-UI:t, Fas 3c 3c-3: sidorna `/floden` för flödet `rule_change_parameter`.

Mot demobeståndet i minnet med en uttryckligen injicerad FakeProvider för tester – inga modellanrop. Flödets
tjänstelager prövar regelpaketet som om det gällde (2026-11-01), så att compliance-agenten
får föreslå aktiveringen; handläggarens UI har dagens regelstatus. Formulären bär flödets
version och hashen av underlaget som visades, och gamla värden ger en konflikt.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import date
from uuid import UUID, uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import delete, update

from agents.development import EditProposal, TestEvidence as CodingEvidence, run_development_case
from agents.flows import console as flow_adapter
from agents.flows.console import FlowConsole
from agents.flows.definitions.rule_change_code import FLOW_TYPE as CODE_FLOW_TYPE, HANDOFF
from agents.gateways import DraftGateway, RegulatoryGateway
from ai.providers.fake import text_result
from models import FlowGateDecision, FlowStep
from scripts.demo.run_development_case import request_merge, stage_candidate
from services import Actor, ProductRuleCatalog, ServiceLayer
from services.change_requests import DEVELOPER, ChangeQueueRun
from services.errors import AccessDeniedError
from tests.flow_helpers import CHANGE, call, flow_client
from web import create_app
from web.config import WebSettings

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

SOURCE = "K-SIM-ITP-2027"
CODE_SOURCE = "K-SIM-KOD-2027"
ORIGIN = {"Origin": "https://testserver"}
BOARD = "/central/utveckling"
FLOW = "/floden/FLOW-000001"
ADOPTION = {
    "decision": "approved", "has_details": "1", "rule_id": "PR-ITP1-013", "rule_version": "1.2",
    "valid_from": "2027-02-01", "decision_number": "B-999", "affected_system": "Premieberäkning",
    "code_reason": "Rättelser behöver bedömas per ursprungsmånad och övergångsvillkor.",
    "expected_effect": "Rättelser efter februari använder den nya regeln bara för berörda ursprungsmånader.",
}


def build_console(web, tmp_path) -> FlowConsole:
    service = ServiceLayer(session_factory=web.session_factory, rules=ProductRuleCatalog(today=date(2026, 11, 1)))
    return FlowConsole.build(web.session_factory, trusted=service, agent_service=service, ai=flow_client(),
                             journal_dir=tmp_path / "runs", drafts_dir=tmp_path / "utkast")


@pytest.fixture
def flow_web(web, tmp_path):
    web.app.state.flow_console = build_console(web, tmp_path)
    return web


def post(web, url, data=None, *, csrf=True):
    return web.client.post(url, data={**(data or {}), **({"csrf_token": web.csrf} if csrf else {})})


def hidden(page, name) -> str:
    match = re.search(rf'name="{name}" value="([^"]*)"', page.text)
    assert match, f"{name} saknas på sidan"
    return match.group(1)


def act(web, page, path, data=None):
    """Postar ett formulär på flödessidan med den version (och hash) sidan visade."""
    flow_id = re.search(r"/floden/(FLOW-\d{6})/", page.text).group(1)
    data = {"version": hidden(page, "version"), **(data or {})}
    if path == "grind":
        data["seen_hash"] = hidden(page, "seen_hash")
    response = post(web, f"/floden/{flow_id}/{path}", data)
    assert response.status_code == 200, response.text
    return response


def start(web):
    response = post(web, "/floden", {"source_handle": SOURCE})
    assert response.status_code == 200, response.text
    return response


def to_activation(web):
    page = act(web, start(web), "kor")
    page = act(web, page, "grind", {"decision": "approved", "note": "Tolkningen stämmer"})
    page = act(web, page, "kor")
    page = act(web, page, "grind", {"decision": "approved", "has_details": "1", "rule_version": "1.1",
                                    "valid_from": "2027-01-01", "decision_number": "B-036"})
    page = act(web, page, "klart", {"commit": "a1b2c3d", "note": "PR-013 v1.1"})
    return act(web, page, "kor")


class TestListaOchStart:
    def test_meny_och_tom_lista(self, flow_web):
        page = flow_web.client.get("/floden")
        assert page.status_code == 200
        assert 'href="/floden"' in page.text and "Inga flöden ännu" in page.text
        assert f'<option value="{SOURCE}">' in page.text and "konfigurerad AI-klient" in page.text

    def test_utan_flodesmotor_visas_varfor(self, web):
        assert 'href="/floden"' not in web.client.get("/").text
        page = web.client.get("/floden")
        assert page.status_code == 409 and "ännu inte anslutna" in page.text
        assert post(web, "/floden", {"source_handle": SOURCE}).status_code == 409

    def test_starta_och_lista(self, flow_web):
        page = start(flow_web)
        assert "Flödet FLOW-000001 är startat." in page.text and "Kör nästa steg" in page.text
        assert page.headers["HX-Push-Url"] == "/floden/FLOW-000001"
        listing = flow_web.client.get("/floden")
        assert 'href="/floden/FLOW-000001"' in listing.text and "Tolkning och konsekvens" in listing.text

    def test_annan_kalla_kan_startas(self, flow_web):
        page = post(flow_web, "/floden", {"source_handle": "kallandringar"})
        assert page.status_code == 200 and "kallandringar" in page.text

    def test_formularet_kraver_token(self, flow_web):
        assert post(flow_web, "/floden", {"source_handle": SOURCE}, csrf=False).status_code == 403


class TestHelaFlodet:
    def test_fran_kalla_till_verifierad_parameter(self, flow_web):
        page = act(flow_web, start(flow_web), "kor")
        assert "Teständring: premium_age_end från 66 till 67" in page.text
        assert "Godkänn tolkningen" in page.text and "/steg/tolkning/utkast/konsekvensanalys.md" in page.text
        assert "0.0000 USD" in page.text and "körjournal" in page.text

        page = act(flow_web, page, "grind", {"decision": "approved", "note": "Tolkningen stämmer"})
        assert "Grinden är godkänd." in page.text
        page = act(flow_web, page, "kor")
        assert "Första berörda år: <strong>2027</strong>" in page.text
        assert 'name="rule_version"' in page.text and 'value="2027-01-01"' in page.text

        page = act(flow_web, page, "grind", {"decision": "approved", "has_details": "1", "rule_version": "1.1",
                                             "valid_from": "2027-01-01", "decision_number": "B-036"})
        assert "Regelversion 1.1 från 2027-01-01 · beslut B-036" in page.text and 'name="commit"' in page.text
        page = act(flow_web, page, "klart", {"commit": "a1b2c3d"})
        page = act(flow_web, page, "kor")
        approval_id = re.search(r'#arende-([^"]+)"', page.text).group(1)
        assert "Väntar på godkännande" in page.text and "compliance_agent" in page.text

        queue = flow_web.client.get("/godkannanden")
        assert approval_id in queue.text and "schedule_product_parameter_change" in queue.text
        assert post(flow_web, f"/godkannanden/{approval_id}/godkann", {"note": "Antagen"}).status_code == 200

        page = act(flow_web, flow_web.client.get("/floden/FLOW-000001"), "kor")
        assert "Verifiera i systemet" in page.text
        page = act(flow_web, page, "kor")
        assert "Klart" in page.text and "Verifierat" in page.text
        assert "Parameterversion" in page.text and "premium_age_end" in page.text
        assert "Syntetisk profil" not in page.text and "Kör nästa steg" not in page.text

    def test_grind_2_med_annan_giltighet_stoppas(self, flow_web):
        page = act(flow_web, start(flow_web), "kor")
        page = act(flow_web, page, "grind", {"decision": "approved"})
        page = act(flow_web, page, "kor")
        flow_id = "FLOW-000001"
        response = post(flow_web, f"/floden/{flow_id}/grind", {
            "version": hidden(page, "version"), "seen_hash": hidden(page, "seen_hash"), "decision": "approved",
            "has_details": "1", "rule_version": "1.1", "valid_from": "2027-02-01"})
        assert response.status_code == 422 and "inte den godkända tolkningens" in response.text
        assert "Ingenting har ändrats." in response.text


class TestKonflikter:
    def test_gammal_version_ger_konflikt(self, flow_web):
        page = start(flow_web)
        act(flow_web, page, "kor")
        again = post(flow_web, "/floden/FLOW-000001/kor", {"version": hidden(page, "version")})
        assert again.status_code == 409 and "Flödet har ändrats" in again.text

    def test_annat_underlag_an_det_som_visades(self, flow_web):
        page = act(flow_web, start(flow_web), "kor")
        response = post(flow_web, "/floden/FLOW-000001/grind", {
            "version": hidden(page, "version"), "seen_hash": "0" * 64, "decision": "approved"})
        assert response.status_code == 409 and "har ändrats sedan det visades" in response.text

    def test_avslag_kraver_skal_och_stoppar_flodet(self, flow_web):
        page = act(flow_web, start(flow_web), "kor")
        response = post(flow_web, "/floden/FLOW-000001/grind", {
            "version": hidden(page, "version"), "seen_hash": hidden(page, "seen_hash"), "decision": "rejected"})
        assert response.status_code == 422 and "anteckning" in response.text
        page = act(flow_web, page, "grind", {"decision": "rejected", "note": "Fel tolkning av PR-016"})
        assert "Avslaget" in page.text and "Fel tolkning av PR-016" in page.text

    def test_ogiltig_commit(self, flow_web):
        page = act(flow_web, start(flow_web), "kor")
        page = act(flow_web, page, "grind", {"decision": "approved"})
        page = act(flow_web, page, "kor")
        page = act(flow_web, page, "grind", {"decision": "approved", "has_details": "1", "rule_version": "1.1",
                                             "valid_from": "2027-01-01"})
        response = post(flow_web, "/floden/FLOW-000001/klart", {"version": hidden(page, "version"), "commit": "main"})
        assert response.status_code == 422 and "Ogiltiga uppgifter" in response.text


class TestUtkastOchJournal:
    def test_utkast_och_korjournal(self, flow_web):
        act(flow_web, start(flow_web), "kor")
        draft = flow_web.client.get("/floden/FLOW-000001/steg/tolkning/utkast/konsekvensanalys.md")
        assert draft.status_code == 200 and "Konsekvensanalys – K-SIM-ITP-2027" in draft.text
        assert flow_web.client.get("/floden/FLOW-000001/steg/tolkning/utkast/annat.md").status_code == 404
        assert flow_web.client.get("/floden/FLOW-000001/steg/g1/utkast/konsekvensanalys.md").status_code == 404
        journal = flow_web.client.get("/floden/FLOW-000001/steg/tolkning/journal")
        assert journal.status_code == 200 and "run_started" in journal.text and "run_ended" in journal.text

    def test_okant_flode(self, flow_web):
        assert flow_web.client.get("/floden/FLOW-000099").status_code == 404


class TestAvbrottOchAvstamning:
    def test_steg_som_pagick_markeras_nar_ui_t_startar(self, web, tmp_path):
        console = build_console(web, tmp_path)
        flow = console.start(SOURCE, Actor.human("karl"))
        with web.session_factory() as s:
            s.execute(update(FlowStep).where(FlowStep.flow_id == flow.flow_id, FlowStep.step_key == "tolkning")
                      .values(status="running"))
        app = create_app(service=web.service, settings=WebSettings(allowed_hosts=("testserver",)),
                         flow_console=console)
        with TestClient(app) as client:
            page = client.get(f"/floden/{flow.flow_id}")
            assert "Kräver avstämning" in page.text and "startade om" in page.text
            data = {"csrf_token": app.state.csrf_token, "version": hidden(page, "version"),
                    "note": "Journalen visar inga verktygsanrop", "retry": "1"}
            page = client.post(f"/floden/{flow.flow_id}/avstam", data=data)
            assert page.status_code == 200 and "Steget körs om vid nästa klick." in page.text

    def test_avbryt_flodet(self, flow_web):
        page = start(flow_web)
        page = act(flow_web, page, "avbryt", {"note": "Källan drogs tillbaka"})
        assert "Flödet är avbrutet." in page.text and "Hoppades över" in page.text
        assert "Avbryt flödet" not in page.text

    def test_aktiveringen_lanker_till_kon(self, flow_web):
        page = to_activation(flow_web)
        assert "/godkannanden?status=vantar#arende-" in page.text
        stopped = post(flow_web, "/floden/FLOW-000001/kor", {"version": hidden(page, "version")})
        assert stopped.status_code == 422 and "väntar på godkännande" in stopped.text


@pytest.fixture
def code_app(tmp_path, monkeypatch):
    sources = tmp_path / "04_regulatoriskt" / "03_bevakning"
    sources.mkdir(parents=True)
    (sources / f"{CODE_SOURCE}.md").write_text(
        "# Fiktiv regel för rättelser\n\n**Version:** 1.0\n\n"
        "Rättelser ska följa ett övergångsvillkor för den ursprungliga premiemånaden.",
        encoding="utf-8",
    )
    (sources / f"{SOURCE}.md").write_text("# Annat bevakningsunderlag", encoding="utf-8")
    monkeypatch.setattr(flow_adapter, "RegulatoryGateway", lambda: RegulatoryGateway(tmp_path))
    monkeypatch.setattr(flow_adapter, "DraftGateway", lambda: DraftGateway(tmp_path / "utkast"))
    monkeypatch.setattr(flow_adapter, "DEFAULT_JOURNAL_DIR", tmp_path / "runs")
    settings = WebSettings(demo_path=tmp_path / "demo.db", allowed_hosts=("testserver",),
                           handler_id="legacy-handler", operator_id="karl",
                           operator_password_hash=PasswordHasher().hash("fiktiv-losenfras-u4"))

    def build(*, source_read=CODE_SOURCE, parameter_change=False, operator_id="karl"):
        answer = {
            "summary": "Inför övergångsvillkor för rättelser av tidigare perioder.",
            "affected_rules": ["PR-ITP1-013"], "parameter_changes": [CHANGE] if parameter_change else [],
            "customer_impact": "Historiska perioder behandlas enligt övergångsvillkoret.",
            "uncertainties": [], "source_handles": [source_read], "draft_names": [],
        }
        ai = flow_client(interpretation_responses=[
            call("read_regulatory_document", {"handle": source_read, "section": None, "offset": 0}, 1),
            text_result(json.dumps(answer, ensure_ascii=False)),
        ])
        return create_app(settings=replace(settings, operator_id=operator_id), rule_flow_ai=ai)

    return build


def code_client(app):
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def login_operator(client, username="karl"):
    page = client.get("/logga-in")
    response = client.post("/logga-in", headers=ORIGIN, data={
        "username": username, "password": "fiktiv-losenfras-u4", "csrf_token": page.context["session_csrf"],
    })
    assert response.status_code == 303


def code_post(client, page, path, data=None):
    payload = {"csrf_token": page.context["operator_csrf"], **(data or {})}
    if path != "/floden":
        payload["version"] = hidden(page, "version")
    if path.endswith("/grind"):
        payload["seen_hash"] = hidden(page, "seen_hash")
    return client.post(path, headers=ORIGIN, data=payload)


def interpret_code_rule(client):
    login_operator(client)
    listing = client.get("/floden")
    page = code_post(client, listing, "/floden", {"flow_type": CODE_FLOW_TYPE, "source_handle": CODE_SOURCE})
    assert page.status_code == 200, page.text
    page = code_post(client, page, FLOW + "/kor")
    assert page.status_code == 200 and "Anta regeln för utveckling" in page.text
    return page


def adopt_code_rule(client):
    page = code_post(client, interpret_code_rule(client), FLOW + "/grind", ADOPTION)
    assert page.status_code == 200 and "Lämna till utveckling" in page.text
    return page


def test_u4_bestallningen_syns_i_flodet_boarden_och_den_behoriga_agentkon(code_app):
    app = code_app()
    store = app.state.change_requests
    operator = Actor.human("karl")
    with code_client(app) as client:
        page = adopt_code_rule(client)
        assert not store.list(operator)
        page = code_post(client, page, FLOW + "/kor")
        assert page.status_code == 200 and page.context["flow"].status == "completed"
        assert "Överlämnat till utveckling" in page.text
        request_id = UUID(page.context["flow"].step(HANDOFF).result["change_request_id"])
        detail_url = f"{BOARD}/{request_id}"
        assert f'href="{detail_url}"' in page.text
        assert f'href="{detail_url}"' in client.get(BOARD).text
        detail = client.get(detail_url)
        assert f'href="{FLOW}#steg-{HANDOFF}"' in detail.text
        item = detail.context["item"]
        source = page.context["flow"].step("tolkning").result["output"]["evidence"]["sources"][0]
        assert item.status == "new" and item.requested_by == "karl"
        assert item.origin.reference == f"FLOW-000001/{HANDOFF}"
        assert item.draft.source_refs == f"{CODE_SOURCE} v1.0 · sha {source['sha256']}"
        assert item.draft.decision_ref == "FLOW-000001 G2 B-999"
        assert item.draft.rule_version == "1.2" and item.draft.effective_on == date(2027, 2, 1)
        assert item.draft.acceptance == ADOPTION["expected_effect"]
        run = ChangeQueueRun(actor=DEVELOPER, run_id=uuid4(), requested_by="karl",
                             allowed_requests=frozenset({request_id}))
        assert store.list_new(run.model_copy(update={"allowed_requests": frozenset()})) == []
        with pytest.raises(AccessDeniedError):
            store.claim(run.model_copy(update={"requested_by": "annan"}), request_id)
        assert [item.id for item in store.list_new(run)] == [request_id]
        assert store.claim(run, request_id).agent_run_id == run.run_id
        assert client.get(detail_url).context["item"].status == "in_progress"
        assert f'href="{detail_url}"' in client.get(FLOW).text


def test_u5_ursprungsflodet_visar_inforandebevis(code_app, tmp_path):
    app = code_app()
    store = app.state.change_requests
    releases = app.state.change_releases
    operator = Actor.human("karl")

    class RuleCoder:
        def propose(self, *_):
            return EditProposal(path="correction.sql", before=":receipt_month", after=":origin_month",
                                plan="Kontrollera övergången mot rättelsens ursprungsmånad.")

    def verify(workspace):
        source = (workspace / "correction.sql").read_text(encoding="utf-8")
        with closing(sqlite3.connect(":memory:")) as db:
            observed = [db.execute(source, {"receipt_month": "2027-03", "origin_month": origin}).fetchone()[0]
                        for origin in ("2027-01", "2027-02")]
        return CodingEvidence(passed=observed == [0, 1], summary="Kontroll före och efter giltighetsgränsen")

    with code_client(app) as client:
        page = code_post(client, adopt_code_rule(client), FLOW + "/kor")
        case_id = UUID(page.context["flow"].step(HANDOFF).result["change_request_id"])
        run = ChangeQueueRun(actor=DEVELOPER, run_id=uuid4(), requested_by=operator.id, allowed_requests={case_id})
        result = run_development_case(store, run, case_id, coder=RuleCoder(), verify=verify,
                                      files={"correction.sql": "SELECT :receipt_month >= '2027-02';\n"},
                                      directory=tmp_path / "development")
        assert result.head_commit and result.head_commit != result.base_commit
        stage_candidate(releases.delivery, result)
        detail_url = f"{BOARD}/{case_id}"
        detail = client.get(detail_url)
        token = detail.context["operator_csrf"]
        assert result.head_commit in detail.text
        approved = client.post(detail_url + "/inforande/approve", headers=ORIGIN, data={
            "csrf_token": token, "review": hidden(detail, "review"),
        })
        assert approved.status_code == 303
        request_merge(store, releases.delivery, operator, case_id)
        assert client.get(FLOW).context["development_status"] == "Mergat"
        approval = client.get(detail_url).context["release"].approval.id
        for action, status in (("deploy", "Infört"), ("verify", "Verifierat")):
            response = client.post(f"{detail_url}/inforande/{action}", headers=ORIGIN, data={
                "csrf_token": token, "approval_id": approval,
            })
            assert response.status_code == 303
            assert client.get(FLOW).context["development_status"] == status
        outcome = client.get(FLOW)
        view = outcome.context["development_release"]
        assert outcome.context["flow"].status == "completed"
        assert view.deployment.version == view.merge.version == view.check.version
        assert view.check.passed and view.check.summary in outcome.text
        assert f'href="{detail_url}#development-release"' in outcome.text
        assert f'href="{FLOW}#steg-{HANDOFF}"' in client.get(detail_url).text


def test_u4_omstart_efter_sparat_arende_bevarar_id_och_ansvar(code_app, monkeypatch):
    app = code_app()
    operator = Actor.human("karl")
    engine = app.state.flow_console.engine

    def interrupt(*args, **kwargs):
        raise RuntimeError("Testavbrott före flödeskvittot")

    with code_client(app) as client:
        page = adopt_code_rule(client)
        monkeypatch.setattr(engine, "_record_system", interrupt)
        with pytest.raises(RuntimeError, match="Testavbrott"):
            code_post(client, page, FLOW + "/kor")
        case, = app.state.change_requests.list(operator)
        assert app.state.change_requests.move(operator, case.id, "new", "in_progress")

    restarted = code_app()
    with code_client(restarted) as client:
        login_operator(client)
        page = client.get(FLOW)
        assert page.context["flow"].status == "reconciliation_required"
        page = code_post(client, page, FLOW + "/avstam", {"retry": "1", "note": "Ärendet finns på boarden."})
        page = code_post(client, page, FLOW + "/kor")
        assert page.context["flow"].step(HANDOFF).result["change_request_id"] == str(case.id)
        saved, = restarted.state.change_requests.list(operator)
        assert saved.id == case.id and saved.status == "in_progress" and saved.assignee_id == "karl"
        history = restarted.state.change_requests.get(operator, case.id).history
        assert sum(event.action == "ordered" for event in history) == 1


@pytest.mark.parametrize(("setup", "details", "message"), [
    ({}, {"expected_effect": ""}, "Ogiltiga uppgifter"),
    ({}, {"rule_id": "PR-ITP1-016"}, "måste finnas bland tolkningens berörda regler"),
    ({"source_read": SOURCE}, {}, "saknar verifierat källunderlag"),
    ({"parameter_change": True}, {}, "Hantera den i parameterflödet"),
])
def test_u4_grinden_stoppar_otillrackligt_underlag(code_app, setup, details, message):
    app = code_app(**setup)
    with code_client(app) as client:
        page = interpret_code_rule(client)
        page = code_post(client, page, FLOW + "/grind", {**ADOPTION, **details})
        assert page.status_code == 422 and message in page.text
        assert page.context["flow"].status == "waiting_gate"
        assert code_post(client, page, FLOW + "/kor").status_code == 422
        assert app.state.change_requests.list(Actor.human("karl")) == []


@pytest.mark.parametrize("tamper", ["bound_input", "missing_decision"])
def test_u4_kraver_bestandigt_beslut_och_oforandrat_underlag(code_app, tamper):
    app = code_app()
    with code_client(app) as client:
        page = adopt_code_rule(client)
        flow = page.context["flow"]
        with app.state.service._session_factory() as session:
            if tamper == "missing_decision":
                session.execute(delete(FlowGateDecision).where(FlowGateDecision.flow_id == flow.flow_id))
            else:
                result = {**flow.step("tolkning").result, "run": {"status": "failed"}}
                session.execute(update(FlowStep).where(FlowStep.flow_id == flow.flow_id, FlowStep.step_key == "tolkning")
                                .values(result=result))
        response = code_post(client, page, FLOW + "/kor")
        assert response.context["flow"].status == "failed" and "verifierat beslut" in response.text
        assert app.state.change_requests.list(Actor.human("karl")) == []


def test_u4_skrivning_och_underlag_kraver_ratt_operator(code_app):
    app = code_app()
    with code_client(app) as client:
        data = {"flow_type": CODE_FLOW_TYPE, "source_handle": CODE_SOURCE, "csrf_token": app.state.csrf_token}
        assert client.post("/floden", headers=ORIGIN, data=data).status_code == 401
        page = adopt_code_rule(client)
        assert client.post(FLOW + "/kor", headers=ORIGIN, data={**data, "version": hidden(page, "version")}).status_code == 403
        assert client.post(FLOW + "/kor", data={
            "csrf_token": page.context["operator_csrf"], "version": hidden(page, "version"),
        }).status_code == 403

    with code_client(code_app(operator_id="annan")) as client:
        login_operator(client, "annan")
        listing = client.get("/floden")
        assert FLOW not in listing.text
        assert client.get(FLOW).status_code == 404
        assert client.get(FLOW + "/steg/tolkning/journal").status_code == 404
        assert client.post(FLOW + "/kor", headers=ORIGIN, data={
            "csrf_token": listing.context["operator_csrf"], "version": hidden(page, "version"),
        }).status_code == 404
    assert app.state.change_requests.list(Actor.human("karl")) == []
