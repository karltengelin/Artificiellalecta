"""Värderingsarbete via HTTP och verkliga tjänsteoperationer, med uttryckliga testgrunder."""

from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import select

from models import ValuationBasis, ValuationExtractRecord, ValuationRun
from services import Actor, OperationContext
from web.operator_auth import OperatorAuth

ROOT = "/team/aktuarie/varderingar"
ORIGIN = {"Origin": "https://testserver"}


@pytest.fixture(scope="module")
def valuation_password():
    return PasswordHasher().hash("syntetisk-testlosenfras")


@pytest.fixture
def valuations(web, valuation_password):
    web.app.state.settings = replace(web.app.state.settings, handler_id="legacy-user")
    web.app.state.operator_auth = OperatorAuth("karl", valuation_password)
    with TestClient(web.app, base_url="https://testserver") as client:
        login = client.get("/logga-in")
        assert client.post("/logga-in", data={"username": "karl", "password": "syntetisk-testlosenfras",
            "csrf_token": login.context["session_csrf"]}, headers=ORIGIN, follow_redirects=False).status_code == 303
        yield SimpleNamespace(client=client, db=web.session_factory, service=web.service, app=web.app)


def earlier_bases(q):
    # Isolerad testdata: produktionsregistrets giltighetsdag ändras aldrig.
    with q.db() as s:
        for row in s.scalars(select(ValuationBasis).where(ValuationBasis.family.in_(("SIM-V", "FI-SIM")))):
            row.valid_from = date(2026, 3, 31)
        s.commit()


def start_form(q, **changes):
    p = q.client.get(ROOT)
    assert p.status_code == 200, p.text
    return {"csrf_token": p.context["operator_csrf"], "request_token": p.context["request_token"],
        "valuation_date": "2026-09-30", "purpose": "base", "basis_code": "", "curve_code": "",
        "note": "Kvartalsgranskning med syntetiskt underlag", **changes}


def start(q, **changes):
    response = q.client.post(ROOT, data=start_form(q, **changes), headers=ORIGIN, follow_redirects=False)
    assert response.status_code == 303, response.text
    return q.client.get(response.headers["location"])


def lock_form(page, **changes):
    return {"csrf_token": page.context["operator_csrf"], "request_token": page.context["request_token"],
        "reviewed_checksum": page.context["run"].review_checksum, "reviewed": "yes",
        "note": "Belopp, kontroller och begränsningar granskade", **changes}


def lock_url(page):
    return f"{ROOT}/{page.context['run'].run_id}/faststall"


def test_base_workflow_list_detail_lock_overview_and_verified_actor(valuations):
    q = valuations
    earlier_bases(q)
    p = start(q)
    run = p.context["run"]
    assert run.created_by == "karl" and run.created_by != "legacy-user"
    assert p.headers["cache-control"] == "no-store"
    for text in ("Pensionskapital", "Villkorad återbäring", "Underskott", "FTA", "Kontroller",
                 "Ej beräknade", "Spårbarhet", "SIM-V-2026-01", "FI-SIM-2026-10"):
        assert text.lower() in p.text.lower()
    assert run.extract_checksum in p.text and run.result_checksum in p.text
    assert "Fastställ basvärderingen" in p.text
    assert str(run.run_id) in q.client.get(ROOT).text
    assert str(run.run_id) in q.client.get("/team/aktuarie").text
    response = q.client.post(lock_url(p), data=lock_form(p), headers=ORIGIN)
    locked = response.context["run"]
    assert response.status_code == 200 and locked.status == "locked" and locked.locked_by == "karl"
    assert "Fastställ basvärderingen" not in response.text
    assert "Senaste fastställda bas" in q.client.get("/team/aktuarie").text
    assert "guarantee_parts" not in p.text and "policy_id" not in p.text


def test_actual_registry_blocks_base_and_allows_explicit_scenario(valuations):
    q = valuations
    p = q.client.get(ROOT)
    assert "2026-12-31" in p.text
    blocked = q.client.post(ROOT, data=start_form(q), headers=ORIGIN)
    assert blocked.status_code == 422 and "Ingen antagen grund i SIM-V" in blocked.text
    scenario = start(q, purpose="scenario", basis_code="SIM-V-2026-01", curve_code="FI-SIM-2026-10")
    assert scenario.context["run"].purpose == "scenario"
    assert "Scenario – kan aldrig fastställas som bas" in scenario.text
    assert "Fastställ basvärderingen" not in scenario.text
    attempted = q.client.post(lock_url(scenario), data=lock_form(scenario), headers=ORIGIN)
    assert attempted.status_code == 422 and "aldrig bas" in attempted.text


@pytest.mark.parametrize("changes, message", [
    ({"valuation_date": "2026-09-29"}, "månadsslut"),
    ({"valuation_date": "2026-08-31"}, "kvartalsslut"),
    ({"basis_code": "SIM-V-2026-01"}, "ange ingen kod"),
    ({"valuation_date": "2026-12-31"}, "avkastning"),
    ({"note": ""}, "motivering"),
    ({"purpose": "other"}, "Kontrollera"),
])
def test_blocked_dates_inputs_and_incomplete_returns(valuations, changes, message):
    q = valuations
    earlier_bases(q)
    result = q.client.post(ROOT, data=start_form(q, **changes), headers=ORIGIN)
    assert result.status_code == 422 and message.lower() in result.text.lower(), result.text
    assert not q.service.execute("list_valuation_runs", OperationContext(actor=Actor.human("test")), {}).output.runs


@pytest.mark.parametrize("changes,status", [({"csrf_token": "forged"},403), ({"actor_id":"forged"},400),
    ({"environment_id":"lakebase"},400), ({"request_token":"forged"},409)])
def test_start_rejects_forgery_before_write(valuations, changes, status):
    q = valuations
    assert q.client.post(ROOT, data=start_form(q, **changes), headers=ORIGIN).status_code == status


def test_start_and_lock_require_session_origin_and_session_csrf(valuations):
    q = valuations
    earlier_bases(q)
    p = start(q)
    data, decision = start_form(q), lock_form(p)
    assert q.client.post(ROOT, data=data, headers={"Origin": "https://elsewhere"}).status_code == 403
    assert q.client.post(lock_url(p), data=decision, headers={"Origin":"https://elsewhere"}).status_code == 403
    assert q.client.post(lock_url(p), data={**decision,"csrf_token":q.app.state.csrf_token}, headers=ORIGIN).status_code == 403
    q.client.cookies.clear()
    assert q.client.post(ROOT, data=data, headers=ORIGIN).status_code == 401
    assert q.client.post(lock_url(p), data=decision, headers=ORIGIN).status_code == 401


def test_replayed_forms_do_not_create_or_lock_twice(valuations):
    q = valuations
    earlier_bases(q)
    data = start_form(q)
    result = q.client.post(ROOT, data=data, headers=ORIGIN, follow_redirects=False)
    assert result.status_code == 303
    assert q.client.post(ROOT, data=data, headers=ORIGIN).status_code == 409
    p = q.client.get(result.headers["location"])
    decision = lock_form(p)
    assert q.client.post(lock_url(p), data=decision, headers=ORIGIN).status_code == 200
    assert q.client.post(lock_url(p), data=decision, headers=ORIGIN).status_code == 409
    assert len(q.client.get(ROOT).context["runs"]) == 1


def test_decision_is_bound_to_run_checksum_and_current_base(valuations):
    q = valuations
    earlier_bases(q)
    first, second = start(q), start(q)
    assert q.client.post(lock_url(second), data=lock_form(first), headers=ORIGIN).status_code == 409
    assert q.client.post(lock_url(first), data=lock_form(first, reviewed_checksum="0"*64), headers=ORIGIN).status_code == 409
    assert q.client.post(lock_url(first), data=lock_form(first), headers=ORIGIN).status_code == 200
    stale = q.client.post(lock_url(second), data=lock_form(second), headers=ORIGIN)
    assert stale.status_code == 409 and "bas har ändrats" in stale.text
    fresh = q.client.get(f"{ROOT}/{second.context['run'].run_id}")
    assert "periodens nuvarande bas" in fresh.text
    done = q.client.post(lock_url(fresh), data=lock_form(fresh), headers=ORIGIN)
    assert done.context["run"].supersedes_run_id == first.context["run"].run_id


@pytest.mark.parametrize("reviewed,note", [("", "Granskat"), ("yes", "")])
def test_lock_requires_explicit_review_and_reason(valuations, reviewed, note):
    q = valuations
    earlier_bases(q)
    p = start(q)
    response = q.client.post(lock_url(p), data=lock_form(p, reviewed=reviewed, note=note), headers=ORIGIN)
    assert response.status_code == 422 and response.context["run"].status == "draft"


def test_failed_controls_and_changed_extract_cannot_be_locked(valuations):
    q = valuations
    earlier_bases(q)
    p = start(q)
    with q.db() as s:
        row = s.get(ValuationRun, p.context["run"].run_id)
        row.checks_passed = False
        s.commit()
    fresh = q.client.get(f"{ROOT}/{p.context['run'].run_id}")
    assert "Fastställ basvärderingen" not in fresh.text
    assert q.client.post(lock_url(fresh), data=lock_form(fresh), headers=ORIGIN).status_code == 422
    with q.db() as s:
        s.get(ValuationRun, p.context["run"].run_id).checks_passed = True
        s.scalar(select(ValuationExtractRecord)).approved = False
        s.commit()
    fresh = q.client.get(f"{ROOT}/{p.context['run'].run_id}")
    blocked = q.client.post(lock_url(fresh), data=lock_form(fresh), headers=ORIGIN)
    assert blocked.status_code == 422 and "Datautdragets kontrollsumma" in blocked.text


def test_total_small_cell_protection_includes_check_details(valuations):
    q = valuations
    earlier_bases(q)
    p = start(q)
    with q.db() as s:
        s.get(ValuationRun, p.context["run"].run_id).policies = 3
        s.commit()
    p = q.client.get(f"{ROOT}/{p.context['run'].run_id}")
    run = p.context["run"]
    assert run.capital_sek is None and run.fta_sek is None
    assert all(c.detail == "Detaljer dolda – småcellsskydd" for c in run.checks)
    assert "Dolt – småcellsskydd" in p.text


def test_missing_run_and_sanitized_unavailable_data(valuations, monkeypatch):
    q = valuations
    assert q.client.get(f"{ROOT}/{uuid4()}").status_code == 404
    def unavailable(*args, **kwargs):
        raise RuntimeError("secret-connection-string")
    monkeypatch.setattr(q.service, "execute", unavailable)
    response = q.client.get(ROOT)
    assert response.status_code == 503 and "secret-connection-string" not in response.text
