"""Operatörens granskning av aktuariella grundförslag."""
from datetime import date
from types import SimpleNamespace

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from services import ProductRuleCatalog, ServiceLayer
from services.operations import common
from web.operator_auth import OperatorAuth

BASES = "/team/aktuarie/antaganden"
ORIGIN = {"Origin": "https://testserver"}
PASSWORD = "syntetisk-testlosenfras"


@pytest.fixture
def actuary(web, monkeypatch):
    monkeypatch.setattr(common, "today", lambda: date(2026, 11, 2))
    web.app.state.service = ServiceLayer(session_factory=web.session_factory,
                                        rules=ProductRuleCatalog(today=date(2026, 11, 2)))
    web.app.state.operator_auth = OperatorAuth("karl", PasswordHasher().hash(PASSWORD))
    with TestClient(web.app, base_url="https://testserver") as client:
        form = client.get("/logga-in")
        logged = client.post("/logga-in", headers=ORIGIN, follow_redirects=False,
                             data={"username": "karl", "password": PASSWORD,
                                   "csrf_token": form.context["session_csrf"]})
        assert logged.status_code == 303
        yield SimpleNamespace(app=web.app, client=client)


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
