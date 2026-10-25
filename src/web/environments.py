"""Öppna en separat lokal UI-server med fast databasläge. Flyttar ingen data."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from http.client import HTTPConnection, HTTPException

from web.config import DEFAULT_PORTS, REPO_ROOT, SWITCHABLE_DATABASES

_startup_lock = threading.Lock()
_started: dict[str, subprocess.Popen] = {}


class EnvironmentUnavailable(Exception):
    """Målmiljön kunde inte startas eller verifieras."""


def _probe(database: str) -> bool:
    """Bara connection refused betyder ledig port; andra svar måste kunna verifieras."""
    # Windows kan behöva cirka två sekunder för att rapportera en ledig port
    # som connection refused. En sekund förväxlar det med en server som hängt.
    connection = HTTPConnection("127.0.0.1", DEFAULT_PORTS[database], timeout=3)
    try:
        connection.request("GET", "/_instance", headers={"Accept": "application/json"})
        if connection.sock is not None:
            connection.sock.settimeout(1)
        response = connection.getresponse()
        body = response.read(4097)
        if response.status != 200 or len(body) > 4096:
            raise EnvironmentUnavailable("Målporten används av en app vars miljö inte kan verifieras. Starta om den appen.")
        identity = json.loads(body)
        if not isinstance(identity, dict) or identity.get("application") != "artificiellalecta-handlaggare":
            raise EnvironmentUnavailable("Målporten används av en annan app. Ingen miljö har bytts.")
        if identity.get("database") != database:
            raise EnvironmentUnavailable("Appen på målporten använder fel databas. Stäng den gamla servern och försök igen.")
        if identity.get("environment_switching") is not True:
            raise EnvironmentUnavailable("Målmiljön kör en äldre version utan miljöväljare. Starta om den servern.")
        return True
    except ConnectionRefusedError:
        return False
    except (OSError, HTTPException, ValueError) as exc:
        raise EnvironmentUnavailable("Målmiljön svarar inte med en verifierbar miljö. Försök igen eller starta om den servern.") from exc
    finally:
        connection.close()


def ensure_environment(database: str) -> str:
    """Starta vid behov och verifiera före navigering. Inga godtyckliga URL:er eller kommandon."""
    if database not in SWITCHABLE_DATABASES:
        raise ValueError("Välj Lakebase eller Demo.")
    url = f"http://127.0.0.1:{DEFAULT_PORTS[database]}/"
    with _startup_lock:
        if _probe(database):
            return url
        process = _started.get(database)
        if process is None or process.poll() is not None:
            try:
                process = subprocess.Popen(
                    [sys.executable, str(REPO_ROOT / "scripts/web/start_ui.py"), "--db", database,
                     "--port", str(DEFAULT_PORTS[database])],
                    cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
            except OSError as exc:
                raise EnvironmentUnavailable("Målmiljön kunde inte startas. Kontrollera Pythonmiljön och försök igen.") from exc
            _started[database] = process
        deadline = time.monotonic() + 10
        while True:
            if _probe(database):
                return url
            if process.poll() is not None:
                raise EnvironmentUnavailable("Målmiljön kunde inte starta. Kontrollera databasinställningarna i .env.")
            if time.monotonic() >= deadline:
                raise EnvironmentUnavailable("Målmiljön har inte svarat inom tio sekunder. Du är kvar i din nuvarande miljö; försök igen.")
            time.sleep(0.2)
