"""Ärendedialogens identitet, arbetsvy och åtgärder genom HTTP."""

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from tests.case_work_helpers import (
    HUMAN,
    answer,
    create,
    make_workspace,
    proposal,
    read_case,
    work,
)
from web.app import create_app
from web.config import WebSettings

ORIGIN = {"Origin": "https://testserver"}


@pytest.fixture
def desk(insurance_db, tmp_path):
    env = make_workspace(insurance_db.session_factory, tmp_path)
    settings = WebSettings(allowed_hosts=("testserver",), operator_id="karl",
                           operator_password_hash=PasswordHasher().hash("syntetisk-testlosenfras"))
    app = create_app(service=env.trusted, settings=settings, case_agent=env.agent,
                     case_workspace_console=env.workspace)
    with TestClient(app, base_url="https://testserver") as client:
        env.client, env.app = client, app
        yield env


def login(desk):
    token = desk.client.get("/logga-in").context["session_csrf"]
    response = desk.client.post("/logga-in", data={"username": "karl", "password": "syntetisk-testlosenfras",
        "csrf_token": token}, headers=ORIGIN, follow_redirects=False)
    assert response.status_code in {302, 303}
    return desk.client.get("/central").context["operator_csrf"]


def post(desk, path, csrf, **data):
    return desk.client.post(path, data={"csrf_token": csrf, **data}, headers=ORIGIN)


def test_dialogen_kraver_inloggning_och_sparad_text_html_escapas(desk):
    number = create(desk)
    ident = desk.workspace.submit(number, "<script>privat-text</script>", actor=HUMAN, key="privat")
    page = desk.client.get(f"/arenden/{number}")
    assert "privat-text" not in page.text
    assert post(desk, f"/arenden/{number}/uppdrag", "falsk", instruction="Hej", submission_key="x").status_code == 401
    csrf = login(desk)
    page = desk.client.get(f"/arenden/{number}")
    assert "&lt;script&gt;privat-text&lt;/script&gt;" in page.text
    assert page.headers["cache-control"] == "no-store"
    assert "Pausa agenten och ta över" in page.text
    assert post(desk, f"/arenden/{number}/uppdrag/{ident}/takeover", csrf, revision="0").status_code == 200


def test_fritt_deluppdrag_syns_efter_omladdning(desk):
    number = create(desk)
    csrf = login(desk)
    desk.fake.queue(read_case(number), answer(summary="Underlaget behöver kontrolleras mot arbetsgivarens besked."))
    response = post(desk, f"/arenden/{number}/uppdrag", csrf, instruction="Vad behöver vi kontrollera?",
                    submission_key="dialog-1", mode="assist")
    assert response.status_code == 200
    page = desk.client.get(f"/arenden/{number}")
    assert "Vad behöver vi kontrollera?" in page.text
    assert "arbetsgivarens besked" in page.text


def test_aktor_miljo_och_csrf_kan_inte_forgas(desk):
    number = create(desk)
    csrf = login(desk)
    data = {"instruction": "Undersök", "submission_key": "spoof", "mode": "assist"}
    assert post(desk, f"/arenden/{number}/uppdrag", csrf, **data, actor="annan").status_code == 422
    assert post(desk, f"/arenden/{number}/uppdrag", "falsk", **data).status_code == 403
    assert desk.client.post(f"/arenden/{number}/uppdrag", data={"csrf_token": csrf, **data},
                           headers={"Origin": "https://annan"}).status_code == 403
    assert not desk.fake.requests


def test_handlaggarens_beslut_avslutar_overlamnat_arende(desk):
    number = create(desk)
    csrf = login(desk)
    desk.fake.queue(read_case(number), proposal())
    response = post(desk, f"/arenden/{number}/uppdrag", csrf, instruction="Handlägg detta ärende",
                    submission_key="handle", mode="handle")
    assert response.status_code == 200
    pending = desk.trusted.approvals.list("pending")[0]
    # Den gamla processtoken får inte godkänna ett nytt ärendeuppdrag.
    denied = post(desk, f"/godkannanden/{pending.id}/godkann", desk.app.state.csrf_token)
    assert denied.status_code == 403
    response = post(desk, f"/godkannanden/{pending.id}/godkann", csrf)
    assert response.status_code == 200
    view = desk.workspace.view(number, HUMAN)
    assert view["works"][0]["status"] == "completed"
    page = desk.client.get(f"/arenden/{number}")
    assert "Ärendet är avslutat" in page.text


def test_kopplat_uppdrag_kan_inte_styras_fran_annat_arende(desk):
    number = create(desk)
    other = create(desk, source_reference="annan")
    ident = desk.workspace.submit(number, "Kontrollera", actor=HUMAN, key="bundet")
    csrf = login(desk)
    assert post(desk, f"/arenden/{other}/uppdrag/{ident}/takeover", csrf, revision="0").status_code == 409
    assert work(desk, ident).status == "queued"


def test_komplettering_andrar_inte_underlaget_utan_versionskontroll(desk):
    number = create(desk)
    csrf = login(desk)
    digest = desk.workspace.view(number, HUMAN)["case_digest"]
    data = {"salary": "82000", "kind": "new", "source": "employer", "reason": "Nytt verifierat besked"}
    assert post(desk, f"/arenden/{number}/komplettera", csrf, expected_digest="0" * 64, **data).status_code == 409
    assert post(desk, f"/arenden/{number}/komplettera", csrf, expected_digest=digest, **data).status_code == 200
    assert post(desk, f"/arenden/{number}/komplettera", csrf, expected_digest=digest, **data).status_code == 409
