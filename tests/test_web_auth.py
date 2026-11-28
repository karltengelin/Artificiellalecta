"""OC-3a H–I: verifierad operatör, sessionslivslängd, CSRF och försöksgräns."""

import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from argon2 import PasswordHasher
from dotenv import dotenv_values
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import select

from models import OperationEventRecord
from services.approvals import ApprovalRequest
from web.app import create_app
from web.config import WebConfigError, WebSettings
from web.operator_auth import LoginRejected, OperatorAuth, operator_action
from web.provision_operator import configure_handler, configure_operator

PASSWORD = "endast-en-syntetisk-testlosenfras"
COOKIE = "__Host-al-operator-demo"
ORIGIN = {"Origin": "https://testserver"}
HANDLER = "provhandlaggare"
HANDLER_PASSWORD = "separat-syntetisk-losenfras"


@pytest.fixture(scope="module")
def password_hash():
    return PasswordHasher().hash(PASSWORD)


@pytest.fixture
def auth_web(web, password_hash):
    clock = [1000.0]
    web.app.state.settings = replace(web.app.state.settings, handler_id="legacy-handler",
                                     operator_id="karl", operator_password_hash=password_hash)
    store = OperatorAuth("karl", password_hash, clock=lambda: clock[0])
    web.app.state.operator_auth = store
    actions = []

    @web.app.api_route("/_test/action", methods=["POST", "PUT", "PATCH", "DELETE"])
    async def protected(request: Request):
        actor = operator_action(request, dict(await request.form()))
        actions.append(actor.id)
        return {"actor_id": actor.id, "is_agent": actor.is_agent}

    with TestClient(web.app, base_url="https://testserver") as client:
        yield SimpleNamespace(app=web.app, client=client, store=store, clock=clock, actions=actions, process_csrf=web.csrf)


def login_form(client):
    page = client.get("/logga-in", follow_redirects=False)
    assert page.status_code == 200
    return page.context["session_csrf"]


def login(client, *, username="karl", password=PASSWORD, token=None, headers=None):
    token = token if token is not None else login_form(client)
    return client.post("/logga-in", data={"username": username, "password": password, "csrf_token": token},
                       headers=ORIGIN if headers is None else headers, follow_redirects=False)


def session_csrf(client):
    return client.get("/central").context["operator_csrf"]


@pytest.fixture
def portal(web, password_hash):
    config = replace(
        web.app.state.settings, portal_login=True, handler_id="legacy-handler",
        operator_password_hash=password_hash, handler_login_id=HANDLER,
        handler_password_hash=PasswordHasher().hash(HANDLER_PASSWORD),
    )
    app = create_app(service=web.service, settings=config)
    with TestClient(app, base_url="https://testserver") as client:
        yield SimpleNamespace(app=app, client=client, service=web.service, session_factory=web.session_factory)


def test_certa_is_the_logged_out_landing_and_guards_all_workspaces(portal, monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("En oinloggad besökare får inte läsa verksamhetsdata")

    monkeypatch.setattr(portal.service, "execute", fail)
    client = portal.client
    landing = client.get("/")
    assert landing.status_code == 200
    assert landing.template.name == "portal_login.html"
    assert "Certa · Tjänstepension" in landing.text and " open data-open" not in landing.text
    assert landing.headers["cache-control"] == "no-store"
    assert "script-src 'self'" in landing.headers["content-security-policy"]
    assert client.get("/static/portal_login.js").status_code == 200
    assert client.get("/logga-in").context["open_dialog"] is True
    for path in ("/central", "/sok", "/forsakrade", "/team/aktuarie", "/central/uppdragsarkiv"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/logga-in"
    assert client.get("/arenden", headers={"HX-Request": "true"}).headers["HX-Redirect"] == "/logga-in"
    assert client.post("/arenden", headers=ORIGIN).status_code == 401
    assert client.get("/_instance").json()["portal_login"] is True


def test_portal_roles_control_landing_navigation_and_direct_addresses(portal):
    handler = portal.client
    assert login(handler, username=HANDLER, password=HANDLER_PASSWORD).headers["location"] == "/sok"
    page = handler.get("/")
    assert page.url.path == "/sok" and page.context["web_user"] == HANDLER
    assert page.headers["cache-control"] == "no-store"
    assert page.context["operator_user"] is None and page.context["csrf_token"] == page.context["web_csrf"]
    assert 'href="/arenden"' in page.text and 'href="/central"' not in page.text
    for path in ("/central", "/team/aktuarie", "/central/fragor", "/central/bolagsuppdrag",
                 "/central/utveckling", "/handelselogg", "/parametrar", "/floden"):
        assert handler.get(path).status_code == 403
    with TestClient(portal.app, base_url="https://testserver") as operator:
        assert login(operator).headers["location"] == "/central"
        central = operator.get("/")
        assert central.url.path == "/central" and central.context["operator_user"] == "karl"
        assert "Arbetsytor" in central.text and 'href="/team/aktuarie"' in central.text
        assert operator.get("/sok").status_code == 200
    csrf = page.context["web_csrf"]
    assert handler.post("/logga-ut", data={"csrf_token": csrf}, headers=ORIGIN,
                        follow_redirects=False).headers["location"] == "/"
    assert handler.get("/sok", follow_redirects=False).status_code == 303


def test_portal_handler_writes_use_verified_actor_and_sessions_csrf(portal):
    client = portal.client
    assert login(client, username=HANDLER, password=HANDLER_PASSWORD).status_code == 303
    csrf = client.get("/arenden/ny").context["web_csrf"]
    form = {
        "personal_id_number": "198505151236", "employer_org_number": "5560000001",
        "kind": "new", "period_month": "2026-10", "pensionable_salary_sek": "47000",
        "source": "employer", "received_date": "2026-10-10", "reason": "Syntetiskt underlag",
        "actor_id": "karl", "csrf_token": csrf,
    }
    assert client.post("/arenden", data=form, headers={"Origin": "https://elsewhere.invalid"}).status_code == 403
    assert client.post("/arenden", data={**form, "csrf_token": portal.app.state.csrf_token},
                       headers=ORIGIN).status_code == 403
    response = client.post("/arenden", data=form, headers=ORIGIN)
    assert response.status_code == 200 and "CASE-000002" in response.text
    with portal.session_factory() as db:
        assert db.scalars(select(OperationEventRecord.actor_id).where(
            OperationEventRecord.operation == "create_case"
        )).all() == [HANDLER]
    assert client.post("/pensioner/bankfiler/godkann", data={"csrf_token": csrf}, headers=ORIGIN).status_code == 403


def test_portal_handler_cannot_see_or_decide_company_proposals(portal):
    request = ApprovalRequest(operation="schedule_product_parameter_change", input={},
                              proposed_by="compliance-test", reason="Prov för bolagsbeslutet")
    portal.service.approvals.add(request)
    client = portal.client
    assert login(client, username=HANDLER, password=HANDLER_PASSWORD).status_code == 303
    queue = client.get("/godkannanden")
    assert "register_salary_report" in queue.text and request.id not in queue.text
    assert queue.context["counts"].pending == 2
    response = client.post(f"/godkannanden/{request.id}/avsla",
                           data={"note": "Ska nekas", "csrf_token": queue.context["web_csrf"]}, headers=ORIGIN)
    assert response.status_code == 403 and portal.service.approvals.get(request.id).status == "pending"


def test_handler_provisioning_preserves_operator_and_rejects_duplicate_username(tmp_path):
    path = tmp_path / ".env"
    configure_operator(path, "karl", PASSWORD)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Användarnamnet"):
        configure_handler(path, "", HANDLER_PASSWORD)
    with pytest.raises(WebConfigError, match="olika inloggningsnamn"):
        configure_handler(path, "karl", HANDLER_PASSWORD)
    assert path.read_bytes() == before
    configure_handler(path, HANDLER, HANDLER_PASSWORD)
    values = dotenv_values(path)
    assert values["OPERATOR_ID"] == "karl"
    assert values["HANDLAGGARE_LOGIN_ID"] == HANDLER
    assert PasswordHasher().verify(values["HANDLAGGARE_PASSWORD_HASH"], HANDLER_PASSWORD)
    assert HANDLER_PASSWORD not in path.read_text(encoding="utf-8")


def test_unconfigured_login_is_closed_but_legacy_views_remain_available(web):
    page = web.client.get("/logga-in")
    assert page.status_code == 503 and "inte konfigurerad" in page.text
    assert "Set-Cookie" not in page.headers and 'name="password"' not in page.text
    assert web.client.get("/central").status_code == 200
    assert web.client.get("/floden").status_code != 401
    assert web.client.get("/parametrar").status_code == 200


def test_login_rotates_cookie_and_csrf_and_only_uses_verified_identity(auth_web):
    client = auth_web.client
    csrf = login_form(client)
    anonymous = client.cookies.get(COOKIE)
    response = login(client, token=csrf)
    assert response.status_code == 303 and response.headers["location"] == "/central"
    authenticated = client.cookies.get(COOKIE)
    assert authenticated != anonymous and auth_web.store.resolve(anonymous) is None
    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/" in cookie
    assert "Domain=" not in cookie
    new_csrf = session_csrf(client)
    assert new_csrf != csrf and new_csrf != auth_web.process_csrf
    page = client.get("/central")
    assert page.headers["referrer-policy"] == "same-origin"
    assert '<meta name="referrer" content="same-origin">' in page.text
    response = client.post("/_test/action", data={"csrf_token": new_csrf, "actor_id": "forged"}, headers=ORIGIN)
    assert response.json() == {"actor_id": "karl", "is_agent": False}
    assert auth_web.actions == ["karl"]
    assert client.get("/logga-in", follow_redirects=False).status_code == 303


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_new_write_guard_rejects_anonymous_and_process_token(auth_web, method):
    response = auth_web.client.request(method, "/_test/action", data={"csrf_token": auth_web.process_csrf, "actor_id": "karl"},
                                       headers=ORIGIN)
    assert response.status_code == 401 and not auth_web.actions


@pytest.mark.parametrize("token", ["", "forged", "åäö"])
def test_login_requires_its_own_csrf_and_does_not_echo_password(auth_web, token):
    login_form(auth_web.client)
    response = login(auth_web.client, token=token)
    assert response.status_code == 403 and PASSWORD not in response.text
    assert not auth_web.actions


@pytest.mark.parametrize("headers", [
    {}, {"Origin": "null"}, {"Origin": "https://evil.invalid"},
    {"Origin": "https://testserver:9999"}, {"Origin": "https://testserver", "Sec-Fetch-Site": "cross-site"},
    {"Origin": "https://evil.invalid", "X-Forwarded-Host": "testserver", "X-Forwarded-Proto": "https"},
])
def test_login_rejects_missing_or_foreign_origin(auth_web, headers):
    assert login(auth_web.client, headers=headers).status_code == 403


def test_same_origin_referer_is_accepted_when_origin_is_absent(auth_web):
    assert login(auth_web.client, headers={"Referer": "https://testserver/logga-in"}).status_code == 303


def test_host_and_non_loopback_http_are_rejected(auth_web):
    assert auth_web.client.get("/logga-in", headers={"Host": "evil.invalid"}).status_code == 400
    with TestClient(auth_web.app, base_url="http://testserver") as client:
        assert client.get("/logga-in").status_code == 403


def test_login_page_is_independent_of_database_and_never_cached(auth_web, monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Inloggningen får inte läsa verksamhetsdata")
    monkeypatch.setattr(auth_web.app.state.service, "execute", fail)
    page = auth_web.client.get("/logga-in")
    assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
    assert page.headers["referrer-policy"] == "same-origin" and page.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert '<meta name="referrer" content="same-origin">' in page.text


def test_failures_are_generic_and_credentials_never_enter_output_or_logs(auth_web, caplog, password_hash):
    caplog.set_level(logging.INFO, logger="web.auth")
    first = login(auth_web.client, username="unknown", password="wrong-passphrase")
    second = login(auth_web.client, username="karl", password="wrong-passphrase")
    assert first.status_code == second.status_code == 401
    assert first.context["message"] == second.context["message"]
    assert "wrong-passphrase" not in first.text + second.text + caplog.text
    assert password_hash not in first.text + second.text + caplog.text
    assert auth_web.client.cookies.get(COOKIE) not in caplog.text
    assert password_hash not in repr(auth_web.app.state.settings)


def test_attempt_limit_cannot_be_bypassed_by_username_ip_or_new_session(auth_web):
    for i in range(5):
        result = login(auth_web.client, username=f"different{i}", password="wrong",
                       headers={**ORIGIN, "X-Forwarded-For": f"192.0.2.{i}"})
        assert result.status_code == (429 if i == 4 else 401)
    assert result.headers["retry-after"] == "300"
    with TestClient(auth_web.app, base_url="https://testserver") as other:
        assert login(other).status_code == 429
    auth_web.clock[0] += 300
    assert login(auth_web.client).status_code == 303


def test_simultaneous_failures_share_attempt_limit(password_hash):
    store = OperatorAuth("karl", password_hash)
    token, _ = store.anonymous()

    def attempt(_):
        try:
            store.authenticate(token, "karl", "wrong")
        except LoginRejected as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(attempt, range(5)))
    assert sorted(results) == [401, 401, 401, 401, 429]
    with pytest.raises(LoginRejected) as blocked:
        store.authenticate(token, "karl", PASSWORD)
    assert blocked.value.status_code == 429


def test_logout_revokes_cookie_and_replayed_session(auth_web):
    assert login(auth_web.client).status_code == 303
    old_cookie = auth_web.client.cookies.get(COOKIE)
    csrf = session_csrf(auth_web.client)
    assert auth_web.client.get("/logga-ut").status_code == 405
    assert auth_web.client.post("/logga-ut", data={"csrf_token": auth_web.process_csrf}, headers=ORIGIN).status_code == 403
    assert auth_web.client.post("/logga-ut", data={"csrf_token": csrf}, headers=ORIGIN, follow_redirects=False).status_code == 303
    assert auth_web.store.resolve(old_cookie) is None and auth_web.client.cookies.get(COOKIE) is None
    assert auth_web.client.get("/central").headers["referrer-policy"] == "no-referrer"
    response = auth_web.client.post("/_test/action", data={"csrf_token": csrf},
                                    headers={**ORIGIN, "Cookie": f"{COOKIE}={old_cookie}"})
    assert response.status_code == 401 and not auth_web.actions


@pytest.mark.parametrize("kind", ["idle", "absolute"])
def test_idle_and_absolute_session_expiry(auth_web, kind):
    assert login(auth_web.client).status_code == 303
    csrf = session_csrf(auth_web.client)
    if kind == "idle":
        auth_web.clock[0] += 900
    else:
        for _ in range(35):
            auth_web.clock[0] += 800
            assert session_csrf(auth_web.client) == csrf
        auth_web.clock[0] += 800
    response = auth_web.client.post("/_test/action", data={"csrf_token": csrf}, headers=ORIGIN)
    assert response.status_code == 401 and not auth_web.actions


def test_other_browser_restart_and_environment_do_not_inherit_session(auth_web, password_hash):
    assert login(auth_web.client).status_code == 303
    csrf = session_csrf(auth_web.client)
    with TestClient(auth_web.app, base_url="https://testserver") as other:
        assert other.post("/_test/action", data={"csrf_token": csrf}, headers=ORIGIN).status_code == 401
    auth_web.app.state.settings = replace(auth_web.app.state.settings, database="lakebase")
    assert auth_web.client.post("/_test/action", data={"csrf_token": csrf}, headers=ORIGIN).status_code == 401
    auth_web.app.state.settings = replace(auth_web.app.state.settings, database="demo")
    auth_web.app.state.operator_auth = OperatorAuth("karl", password_hash)
    assert auth_web.client.post("/_test/action", data={"csrf_token": csrf}, headers=ORIGIN).status_code == 401


def test_old_login_csrf_and_legacy_csrf_cannot_authorize_new_actions(auth_web):
    old_csrf = login_form(auth_web.client)
    assert login(auth_web.client, token=old_csrf).status_code == 303
    for token in (old_csrf, auth_web.process_csrf, "åäö"):
        assert auth_web.client.post("/_test/action", data={"csrf_token": token}, headers=ORIGIN).status_code == 403
    assert not auth_web.actions


@pytest.mark.parametrize("body", ["username=a&username=b", "actor_id=karl", "password=" + "a" * 17000])
def test_duplicate_extra_and_oversized_forms_are_rejected(auth_web, body):
    login_form(auth_web.client)
    response = auth_web.client.post("/logga-in", content=body,
                                    headers={**ORIGIN, "Content-Type": "application/x-www-form-urlencoded"})
    assert response.status_code in {400, 413}


def test_invalid_password_hash_fails_without_disclosing_it():
    with pytest.raises(WebConfigError) as exc:
        WebSettings(operator_password_hash="not-a-password-hash")
    assert "not-a-password-hash" not in str(exc.value)


def test_provisioning_writes_only_hash_to_env_and_preserves_other_configuration(tmp_path):
    path = tmp_path / ".env"
    path.write_text("DATABASE_URL=fixture-not-a-database\n", encoding="utf-8")
    configure_operator(path, "karl", PASSWORD)
    values = dotenv_values(path)
    assert values["OPERATOR_ID"] == "karl" and values["DATABASE_URL"] == "fixture-not-a-database"
    assert values["OPERATOR_PASSWORD_HASH"].startswith("$argon2id$")
    assert PasswordHasher().verify(values["OPERATOR_PASSWORD_HASH"], PASSWORD)
    assert PASSWORD not in path.read_text(encoding="utf-8")
    for target, password in [(tmp_path / ".env.example", PASSWORD), (tmp_path / "other.env", PASSWORD), (path, "short")]:
        with pytest.raises(ValueError):
            configure_operator(target, "karl", password)


def test_password_script_prompts_privately_and_prints_no_credentials(tmp_path, monkeypatch, capsys):
    from web import provision_operator
    path = tmp_path / ".env"
    passwords = iter([PASSWORD, PASSWORD])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(provision_operator.getpass, "getpass", lambda prompt: next(passwords))
    monkeypatch.setattr(sys, "argv", ["set_operator_password.py", "--env-file", str(path)])
    provision_operator.main()
    output = capsys.readouterr()
    assert PASSWORD not in output.out + output.err and "$argon2id$" not in output.out + output.err
    assert "konfigurerad" in output.out


def test_mismatched_password_confirmation_does_not_write_a_file(tmp_path, monkeypatch):
    from web import provision_operator
    path = tmp_path / ".env"
    passwords = iter([PASSWORD, PASSWORD + "-different"])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(provision_operator.getpass, "getpass", lambda prompt: next(passwords))
    monkeypatch.setattr(sys, "argv", ["set_operator_password.py", "--env-file", str(path)])
    with pytest.raises(SystemExit) as exc:
        provision_operator.main()
    assert exc.value.code == 2 and not path.exists()


def test_password_script_refuses_input_without_a_terminal(tmp_path, monkeypatch):
    from web import provision_operator
    path = tmp_path / ".env"
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(sys, "argv", ["set_operator_password.py", "--env-file", str(path)])
    monkeypatch.setattr(provision_operator.getpass, "getpass", lambda prompt: pytest.fail("Får inte läsa lösenfrasen"))
    with pytest.raises(SystemExit) as exc:
        provision_operator.main()
    assert exc.value.code == 2 and not path.exists()


def test_login_links_leave_boosted_navigation():
    # htmx-navigering byter inte sidans referrer-policy. En boostad väg till inloggningen
    # behåller no-referrer, och nästa formulär skickas då med Origin: null.
    templates = Path(__file__).resolve().parents[1] / "src" / "web" / "templates"
    boosted = [
        f"{path.relative_to(templates)}: {link}"
        for path in templates.rglob("*.html") if path.name != "login.html"
        for link in re.findall(r'<a [^>]*href="/logga-in"[^>]*>', path.read_text(encoding="utf-8"))
        if 'hx-boost="false"' not in link
    ]
    assert not boosted
