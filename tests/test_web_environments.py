"""Miljöbyte: rätt server, separat datakälla och bevarade osparade formulär."""

import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from web import environments
from web.config import WebSettings
from web.environments import EnvironmentUnavailable
from web.routes import environments as routes

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")


def test_valjaren_visar_sqlite_och_postgres_med_aktiv_miljo(web):
    page = web.client.get("/").text
    assert 'value="demo" selected' in page
    assert "(SQLite)" in page and "(Postgres)" in page
    assert 'action="/miljo" hx-boost="false"' in page
    assert '<meta name="referrer" content="no-referrer">' in page


@pytest.mark.parametrize("accept", ["application/json", "text/html"])
def test_byte_gar_till_malets_startsida_utan_att_andra_appens_databas(web, monkeypatch, accept):
    ensure = Mock(return_value="http://127.0.0.1:8765/")
    monkeypatch.setattr(routes, "ensure_environment", ensure)
    response = web.client.post("/miljo", data={"database": "lakebase", "csrf_token": web.csrf,
                                             "return_url": "/forsakrade/198505151236"},
                               headers={"Accept": accept}, follow_redirects=False)
    ensure.assert_called_once_with("lakebase")
    assert response.headers["referrer-policy"] == "no-referrer"
    if accept == "application/json":
        assert response.status_code == 200
        assert response.json() == {"url": "http://127.0.0.1:8765/"}
    else:
        assert response.status_code == 303
        assert response.headers["location"] == "http://127.0.0.1:8765/"
    assert web.app.state.settings.database == "demo"
    assert 'value="demo" selected' in web.client.get("/").text


def test_samma_miljo_startar_ingen_server(web, monkeypatch):
    ensure = Mock()
    monkeypatch.setattr(routes, "ensure_environment", ensure)
    response = web.client.post("/miljo", data={"database": "demo", "csrf_token": web.csrf},
                               headers={"Accept": "application/json"})
    assert response.json() == {"url": "/"}
    ensure.assert_not_called()


@pytest.mark.parametrize("database,token,status", [
    ("lakebase", "fel", 403), ("http://example.com", None, 422), ("svc_test", None, 422),
])
def test_miljoval_kraver_token_och_tillatet_databaslage(web, monkeypatch, database, token, status):
    ensure = Mock()
    monkeypatch.setattr(routes, "ensure_environment", ensure)
    response = web.client.post("/miljo", data={"database": database, "csrf_token": token or web.csrf})
    assert response.status_code == status
    ensure.assert_not_called()


def test_otillganglig_miljo_lamnar_datakallan_oforandrad(web, monkeypatch):
    web.app.state.settings = WebSettings(database="lakebase", allowed_hosts=("testserver",))
    monkeypatch.setattr(routes, "ensure_environment", Mock(side_effect=EnvironmentUnavailable("Fel databas på målporten")))
    response = web.client.post("/miljo", data={"database": "demo", "csrf_token": web.csrf},
                               headers={"Accept": "application/json"})
    assert response.status_code == 503
    assert response.json() == {"message": "Fel databas på målporten"}
    assert web.app.state.settings.database == "lakebase"


@pytest.mark.parametrize("identity,status,expected", [
    ({"application": "artificiellalecta-handlaggare", "database": "demo", "environment_switching": True}, 200, None),
    ({"application": "artificiellalecta-handlaggare", "database": "lakebase", "environment_switching": True}, 200, "fel databas"),
    ({"application": "artificiellalecta-handlaggare", "database": "demo"}, 200, "äldre version"),
    ({"application": "another-app"}, 200, "annan app"),
    ({}, 302, "inte kan verifieras"),
    ([], 200, "annan app"),
])
def test_malserverns_identitet_och_lage_kontrolleras(monkeypatch, identity, status, expected):
    connection = Mock()
    connection.getresponse.return_value = SimpleNamespace(status=status, read=lambda size: json.dumps(identity).encode())
    factory = Mock(return_value=connection)
    monkeypatch.setattr(environments, "HTTPConnection", factory)
    if expected:
        with pytest.raises(EnvironmentUnavailable, match=expected):
            environments._probe("demo")
    else:
        assert environments._probe("demo")
    factory.assert_called_once_with("127.0.0.1", 8767, timeout=3)
    connection.sock.settimeout.assert_called_once_with(1)
    connection.request.assert_called_once_with("GET", "/_instance", headers={"Accept": "application/json"})
    connection.close.assert_called_once()


def test_ledig_port_skils_fran_en_server_som_inte_svarar(monkeypatch):
    connection = Mock()
    monkeypatch.setattr(environments, "HTTPConnection", Mock(return_value=connection))
    connection.request.side_effect = ConnectionRefusedError()
    assert not environments._probe("demo")
    connection.request.side_effect = TimeoutError()
    with pytest.raises(EnvironmentUnavailable):
        environments._probe("demo")


def test_ledig_loopbackport_upptacks_aven_med_windows_fordrojning(monkeypatch):
    """Riktig lokal TCP: Windows rapporterar connection refused först efter cirka 2 s."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        unused_port = listener.getsockname()[1]
    monkeypatch.setattr(environments, "DEFAULT_PORTS", {"demo": unused_port})
    assert not environments._probe("demo")


def test_befintlig_miljo_ateranvands_och_ny_startas_med_fast_databas(monkeypatch):
    monkeypatch.setattr(environments, "_started", {})
    probe = Mock(side_effect=[True, False, False, True])
    monkeypatch.setattr(environments, "_probe", probe)
    process = Mock()
    process.poll.return_value = None
    popen = Mock(return_value=process)
    monkeypatch.setattr(environments.subprocess, "Popen", popen)
    monkeypatch.setattr(environments.time, "sleep", lambda _: None)
    assert environments.ensure_environment("demo") == "http://127.0.0.1:8767/"
    popen.assert_not_called()
    assert environments.ensure_environment("demo") == "http://127.0.0.1:8767/"
    command = popen.call_args.args[0]
    assert command == [sys.executable, str(environments.REPO_ROOT / "scripts/web/start_ui.py"),
                       "--db", "demo", "--port", "8767"]
    if sys.platform == "win32":
        assert popen.call_args.kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW


def test_ovantad_server_stoppar_byten_utan_att_starta_fler_processer(monkeypatch):
    monkeypatch.setattr(environments, "_probe", Mock(side_effect=EnvironmentUnavailable("fel databas")))
    popen = Mock()
    monkeypatch.setattr(environments.subprocess, "Popen", popen)
    with pytest.raises(EnvironmentUnavailable, match="fel databas"):
        environments.ensure_environment("lakebase")
    with pytest.raises(ValueError):
        environments.ensure_environment("svc_test")
    popen.assert_not_called()


def test_tidsgrans_ateranvander_den_redan_startade_processen(monkeypatch):
    process = Mock()
    process.poll.return_value = None
    monkeypatch.setattr(environments, "_started", {"demo": process})
    monkeypatch.setattr(environments, "_probe", Mock(return_value=False))
    monkeypatch.setattr(environments.time, "monotonic", Mock(side_effect=[0, 11]))
    popen = Mock()
    monkeypatch.setattr(environments.subprocess, "Popen", popen)
    with pytest.raises(EnvironmentUnavailable, match="tio sekunder"):
        environments.ensure_environment("demo")
    popen.assert_not_called()


@pytest.mark.skipif(shutil.which("node") is None, reason="Node används bara för JavaScript-provet")
def test_javascript_bevarar_utkast_och_byter_bara_efter_verifierat_svar():
    result = subprocess.run([shutil.which("node"), str(Path(__file__).with_name("web_environment_client.cjs"))],
                            check=False, capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
