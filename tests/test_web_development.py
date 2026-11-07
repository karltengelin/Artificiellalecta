"""U1 via den vanliga appfabriken, operatörsinloggningen och en lokal demofil."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from threading import Barrier
from uuid import UUID

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from services import Actor
from services.change_requests import ChangeRequest, ChangeRequestDraft, change_requests_table
from services.errors import AccessDeniedError
from web.app import create_app
from web.config import WebSettings
from web.database import demo_engine

BASE = "/central/utveckling"
ORIGIN = {"Origin": "https://testserver"}
PASSWORD = "en-fiktiv-losenfras-for-u1"


@pytest.fixture(scope="module")
def password_hash():
    return PasswordHasher().hash(PASSWORD)


@pytest.fixture
def settings(tmp_path, password_hash):
    return WebSettings(demo_path=tmp_path / "demo.db", allowed_hosts=("testserver",),
                       handler_id="legacy-handler", operator_id="karl", operator_password_hash=password_hash)


def client_for(app):
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def login(client, username="karl"):
    page = client.get("/logga-in")
    response = client.post("/logga-in", headers=ORIGIN, data={
        "username": username, "password": PASSWORD, "csrf_token": page.context["session_csrf"],
    })
    assert response.status_code == 303


def new_form(client, **fields):
    page = client.get(BASE + "/ny")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert 'name="request_id"' in page.text
    return {
        "request_id": str(page.context["request_id"]), "csrf_token": page.context["operator_csrf"],
        "kind": "defect", "title": "Fel vid export", "need": "Kolumnrubriken saknas.", **fields,
    }


def test_fel_och_regel_anvander_samma_kontrakt_efter_omstart(settings):
    # Återskapa schemaformen hos en äldre demofil med befintligt bestånd.
    engine = demo_engine(settings.demo_path)
    change_requests_table.drop(engine)
    engine.dispose()
    with client_for(create_app(settings=settings)) as client:
        assert f'href="{BASE}"' in client.get("/central").text
        login(client)
        assert "Du har inga ändringsärenden ännu" in client.get(BASE).text
        bug = new_form(client, need="Text med <script> och radbrytning.\nKolumnrubriken saknas.")
        rule = new_form(client, kind="rule_change", title="Visa giltighetsdatum", affected_system="Regelöversikt",
                        need="Tillämpa en fiktiv regel för en framtida period.", motivation="Spårbarhet",
                        acceptance="Gammal och ny period visas med rätt version.", source_refs="SIM-KÄLLA-01",
                        decision_ref="SIM-BESLUT-01", rule_version="SIM-REGEL v2", effective_on="2027-01-01")
        responses = [client.post(BASE, headers=ORIGIN, data=form) for form in (bug, rule)]
        assert all(r.status_code == 303 for r in responses)
        bug_url, rule_url = [r.headers["location"] for r in responses]
        assert bug_url == f"{BASE}/{bug['request_id']}"
        assert rule_url == f"{BASE}/{rule['request_id']}"

    with client_for(create_app(settings=settings)) as client:
        login(client)
        listing = client.get(BASE)
        assert listing.status_code == 200 and listing.headers["cache-control"] == "no-store"
        assert f'href="{bug_url}"' in listing.text and f'href="{rule_url}"' in listing.text
        assert "Felanmälan" in listing.text and "Regeländring" in listing.text
        bug_page, rule_page = client.get(bug_url), client.get(rule_url)
        assert bug_page.status_code == rule_page.status_code == 200
        assert "med &lt;script&gt; och radbrytning.\nKolumnrubriken" in bug_page.text
        assert "SIM-BESLUT-01" in rule_page.text and "SIM-REGEL v2" in rule_page.text
        for page in (bug_page, rule_page):
            item = page.context["item"]
            assert isinstance(item, ChangeRequest)
            assert item.requested_by == "karl" and item.status == "new"
        assert rule_page.context["item"].draft.effective_on == date(2027, 1, 1)


def test_atkomst_och_validering(settings):
    app = create_app(settings=settings)
    with client_for(app) as client:
        for url in (BASE, BASE + "/ny", BASE + "/11111111-1111-4111-8111-111111111111"):
            response = client.get(url)
            assert response.status_code == 401 and response.headers["cache-control"] == "no-store"
        assert client.post(BASE, headers=ORIGIN, data={"csrf_token": app.state.csrf_token}).status_code == 401
        login(client)
        form = new_form(client, title="   ", effective_on="2027-02-30")
        assert client.post(BASE, headers={"Origin": "https://example.test"}, data=form).status_code == 403
        assert client.post(BASE, headers=ORIGIN, data={**form, "csrf_token": app.state.csrf_token}).status_code == 403
        assert client.post(BASE, headers=ORIGIN, data={**form, "requested_by": "annat-id"}).status_code == 400
        invalid = client.post(BASE, headers=ORIGIN, data=form)
        assert invalid.status_code == 422 and invalid.headers["cache-control"] == "no-store"
        assert invalid.context["errors"].keys() == {"title", "effective_on"}
        assert str(invalid.context["request_id"]) == form["request_id"]
        assert invalid.context["values"]["need"] == form["need"]
        assert client.get(BASE).context["items"] == []
        response = client.post(BASE, headers=ORIGIN, data={**form, "title": "Eget ärende", "effective_on": ""})
        assert response.status_code == 303
        detail = response.headers["location"]

    with client_for(create_app(settings=replace(settings, operator_id="annan"))) as client:
        login(client, "annan")
        assert client.get(BASE).context["items"] == []
        hidden = client.get(detail)
        assert hidden.status_code == 404 and "Eget ärende" not in hidden.text

    for actor in (Actor.agent("karl"), Actor.system("karl")):
        with pytest.raises(AccessDeniedError):
            app.state.change_requests.list(actor)


def test_samtidigt_omforsok_ar_idempotent(settings):
    app = create_app(settings=settings)
    with client_for(app) as client:
        login(client)
        form = new_form(client)
        store = app.state.change_requests
        actor = Actor.human("karl")
        draft = ChangeRequestDraft(kind="defect", title=form["title"], need=form["need"])
        barrier = Barrier(2, timeout=10)

        def submit():
            barrier.wait()
            return store.create(actor, UUID(form["request_id"]), draft)

        with ThreadPoolExecutor(max_workers=2) as executor:
            attempts = [executor.submit(submit) for _ in range(2)]
            assert attempts[0].result() == attempts[1].result()
        replay = client.post(BASE, headers=ORIGIN, data=form)
        assert replay.status_code == 303 and replay.headers["location"] == f"{BASE}/{form['request_id']}"
        collision = client.post(BASE, headers=ORIGIN, data={**form, "title": "En annan titel"})
        assert collision.status_code == 409
        assert [item.draft.title for item in client.get(BASE).context["items"]] == [form["title"]]


@pytest.mark.parametrize("database", ["svc_test", "lakebase"])
def test_andra_miljoer_anropar_ingen_databas(web, settings, database, monkeypatch):
    service = web.app.state.service

    def fail(*args, **kwargs):
        pytest.fail("Utvecklingsytan får inte använda annan databas")

    monkeypatch.setattr(service, "execute", fail)
    monkeypatch.setattr(service, "_session_factory", fail)
    app = create_app(service=service, settings=replace(settings, database=database))
    assert app.state.change_requests is None
    with client_for(app) as client:
        login(client)
        page = client.get(BASE)
        assert page.status_code == 404 and "finns i demomiljön" in page.text
        response = client.post(BASE, headers=ORIGIN, data={"csrf_token": page.context["operator_csrf"]})
        assert response.status_code == 404
