"""V-12 från Paket C:s riktiga export till versionsbundet beslut och mottagning."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from reporting.premium_deliveries import PremiumDeliveries, identity
from reporting.premium_statement import DAYS
from scripts.simulation.premium_calendar import publish
from services import Actor
from simulation.premium_calendar import advance, run_connection, start
from web.app import create_app
from web.operator_auth import OperatorAuth
from web.routes.premium_reports import BASE


def finish(root, scenario):
    run = start(root, scenario)
    pending = advance(root, run)
    state = advance(root, run, revision=pending["cursor"], decision=(
        Actor.human("testhandläggare"), "approve", pending["review"]["review_digest"], "Avstämda provrader"))
    publish(root / state["id"], state)
    return state["id"]


@pytest.mark.parametrize("scenario,open_sek,bank_events", [
    ("full", "0.00", 1), ("partial", "2733.13", 1), ("duplicate", "0.00", 1),
    ("twice", "0.00", 2), ("unknown", "6733.13", 1),
])
def test_delivery_facit(tmp_path, scenario, open_sek, bank_events):
    run = finish(tmp_path, scenario)
    registry = PremiumDeliveries(tmp_path)
    for day in DAYS:
        ident = identity(run, day)
        rev = registry.prepare(run, day, "ekonomi")
        doc = registry.get(ident, rev)
        packet = doc["packet"]
        assert not packet["failures"]
        assert packet["summary"]["operations"]["Unika bankhändelser"] == bank_events
        assert packet["summary"]["operations"]["Återlevererade bankhändelser"] == int(scenario == "duplicate")
        assert packet["summary"]["amounts"]["Därav förfallen fordran"] == (open_sek if day == DAYS[1] else "0.00")
        assert packet["summary"]["amounts"]["Öppen fordran"] == open_sek
        assert "AL-000001" not in json.dumps(packet)
        if day == DAYS[1]:
            assert packet["parent"] == registry.get(identity(run, DAYS[0]), 1)["digest"]
        registry.act(ident, rev, doc["digest"], "approve", "ekonomi", "Avstämd")


def test_delivery_control_failure_and_repair(tmp_path):
    run = finish(tmp_path, "partial")
    registry = PremiumDeliveries(tmp_path)
    day = DAYS[0]
    ident = identity(run, day)
    with pytest.raises(ValueError, match="novemberrapporten"):
        registry.prepare(run, DAYS[1], "producent")
    assert registry.listing() == []
    path = tmp_path / run / (day + ".json")
    saved = path.read_bytes()
    path.write_bytes((tmp_path / run / (DAYS[1] + ".json")).read_bytes())
    registry.prepare(run, day, "producent")
    bad = registry.get(ident, 1)
    assert "Källfil " + day + ".json" in bad["packet"]["failures"]
    with pytest.raises(ValueError, match="Kontrollfel"):
        registry.act(ident, 1, bad["digest"], "approve", "ekonomi", "Granskat")
    registry.act(ident, 1, bad["digest"], "return", "ekonomi", "Fel periodfil")
    path.write_bytes(saved)
    assert registry.prepare(run, day, "producent", previous=bad["digest"], reason="Novemberunderlaget återställt") == 2
    good = registry.get(ident, 2)
    assert good["packet"]["delta"]["Öppen fordran"] == "0.00" and good["status"] == "pending"
    assert not good["packet"]["failures"] and good["packet"]["parent"] == bad["digest"]
    with pytest.raises(ValueError, match="Leveranssumman"):
        registry.act(ident, 2, bad["digest"], "approve", "ekonomi", "Fel revision")
    assert registry.get(ident, 1)["decision"]["reason"] == "Fel periodfil"
    with run_connection(tmp_path, run, write=True) as (_, state):
        report = state["reports"][day]
        report["observed"]["rows"][0]["allocated"] = "1203.02"
        report["observed"]["rows"][1]["allocated"] = "2796.98"
        publish(tmp_path / run, state)
    registry.act(ident, 2, good["digest"], "approve", "ekonomi", "Fryst version")
    registry.prepare(run, day, "producent", previous=good["digest"], reason="Kontroll av radändring")
    assert "Radutfall och ärenden mot scenariefacit" in registry.get(ident, 3)["packet"]["failures"]
    assert registry.get(ident, 2, specialist=True)["evidence"]["report"]["observed"]["rows"][0]["allocated"] == "1203.01"
    with pytest.raises(ValueError, match="senare revision"):
        registry.act(ident, 2, good["digest"], "receive", "mottagare")


def test_delivery_web_decision_and_concurrent_receipt(tmp_path, request):
    run = finish(tmp_path, "partial")
    web = request.getfixturevalue("web")
    registry = PremiumDeliveries(tmp_path)
    web.app.state.premium_deliveries = registry
    ident = identity(run, DAYS[0])
    path = f"{BASE}/{ident}/1"
    password = "syntetiskt-lokalt-test"
    web.app.state.operator_auth = OperatorAuth("testoperator", PasswordHasher().hash(password))
    origin = {"Origin": "https://testserver"}
    with TestClient(web.app, base_url="https://testserver") as client:
        assert client.get(BASE).status_code == 401
        assert client.get(path + "/underlag").status_code == 401
        token = client.get("/logga-in").context["session_csrf"]
        client.post("/logga-in", data={"username": "testoperator", "password": password, "csrf_token": token},
                    headers=origin)
        inbox = client.get(BASE)
        assert run in inbox.text
        token = inbox.context["operator_csrf"]
        form = {"run": run, "day": DAYS[0], "csrf_token": token}
        assert client.post(BASE + "/bered", data=form).status_code == 403
        page = client.post(BASE + "/bered", data=form, headers=origin)
        assert page.status_code == 200 and "2733,13" in page.text
        assert "AL-000001" not in page.text and "AL-000001" in client.get(path + "/underlag").text
        digest = page.context["record"]["digest"]
        action = {"action": "receive", "csrf_token": token, "digest": digest}
        assert client.post(path, data=action, headers=origin).status_code == 409
        assert client.post(path, data={**action, "action": "approve", "reason": "Avstämd"}, headers=origin).status_code == 200
        assert "Godkänd, väntar på kvitto" in client.get(BASE).text
        def receive(_):
            PremiumDeliveries(tmp_path).act(ident, 1, digest, "receive", "testoperator")
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(receive, range(2)))
        receipt = registry.get(ident, 1)["receipt"]
        assert client.post(path, data=action, headers=origin).context["record"]["receipt"] == receipt
        assert receipt["actor"] == "testoperator" and receipt["digest"] == digest
        demo_settings = replace(web.app.state.settings, operator_id="testoperator",
                                operator_password_hash=PasswordHasher().hash(password))
        web.app.state.settings = replace(web.app.state.settings, database="lakebase")
        assert client.get(BASE).status_code == 401
        token = client.get("/logga-in").context["session_csrf"]
        client.post("/logga-in", data={"username": "testoperator", "password": password, "csrf_token": token},
                    headers=origin)
        assert client.get(BASE).status_code == 404
    restarted = create_app(service=web.service, settings=demo_settings)
    restarted.state.premium_deliveries = PremiumDeliveries(tmp_path)
    with TestClient(restarted, base_url="https://testserver") as client:
        token = client.get("/logga-in").context["session_csrf"]
        client.post("/logga-in", data={"username": "testoperator", "password": password, "csrf_token": token},
                    headers=origin)
        restored = client.get(path)
        assert restored.context["record"]["receipt"] == receipt and "Mottagen" in restored.text
