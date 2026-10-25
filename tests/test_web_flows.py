"""Handläggar-UI:t, Fas 3c 3c-3: sidorna `/floden` för flödet `rule_change_parameter`.

Mot demobeståndet i minnet med den skriptade demomodellen – inga modellanrop. Flödets
tjänstelager prövar regelpaketet som om det gällde (2026-11-01), så att compliance-agenten
får föreslå aktiveringen; handläggarens UI har dagens regelstatus. Formulären bär flödets
version och hashen av underlaget som visades, och gamla värden ger en konflikt.
"""

from __future__ import annotations

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from agents.flows.console import FlowConsole
from models import FlowStep
from services import Actor, ProductRuleCatalog, ServiceLayer
from web import create_app
from web.config import WebSettings

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

SOURCE = "K-SIM-ITP-2027"


def build_console(web, tmp_path) -> FlowConsole:
    service = ServiceLayer(session_factory=web.session_factory, rules=ProductRuleCatalog(today=date(2026, 11, 1)))
    return FlowConsole.build(web.session_factory, trusted=service, agent_service=service,
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
        assert f'<option value="{SOURCE}">' in page.text and "skriptad demomodell" in page.text

    def test_utan_flodesmotor_visas_varfor(self, web):
        page = web.client.get("/floden")
        assert page.status_code == 409 and "migrate_flows.py är inte körd" in page.text
        assert post(web, "/floden", {"source_handle": SOURCE}).status_code == 409

    def test_starta_och_lista(self, flow_web):
        page = start(flow_web)
        assert "Flödet FLOW-000001 är startat." in page.text and "Kör nästa steg" in page.text
        assert page.headers["HX-Push-Url"] == "/floden/FLOW-000001"
        listing = flow_web.client.get("/floden")
        assert 'href="/floden/FLOW-000001"' in listing.text and "Tolkning och konsekvens" in listing.text

    def test_annan_kalla_stoppas(self, flow_web):
        page = post(flow_web, "/floden", {"source_handle": "kallandringar"})
        assert page.status_code == 422 and "bara köra den fiktiva källan" in page.text

    def test_formularet_kraver_token(self, flow_web):
        assert post(flow_web, "/floden", {"source_handle": SOURCE}, csrf=False).status_code == 403


class TestHelaFlodet:
    def test_fran_kalla_till_verifierad_parameter(self, flow_web):
        page = act(flow_web, start(flow_web), "kor")
        assert "Premieåldern i ITP1 höjs från 66 till 67 år" in page.text
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
        assert "inom åldersfönstret" in page.text and "utanför åldersfönstret" in page.text
        assert "IBB 2026 antaget" in page.text and "Kör nästa steg" not in page.text

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
