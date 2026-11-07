"""Skrivskyddad GitHub-status för utvecklingsytans konfigurerade repo."""

import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from http.client import HTTPException, HTTPSConnection
from threading import Lock

DEFAULT_REPOSITORY = "karltengelin/Artificiellalecta"
REPOSITORY_PATTERN = r"[a-zA-Z0-9][a-zA-Z0-9-]{0,38}/[a-zA-Z0-9_.-]{1,100}"
_LINK = re.compile(
    rf"https://github\.com/({REPOSITORY_PATTERN})/(issues|pull)/([1-9][0-9]{{0,18}})/?",
    re.ASCII | re.IGNORECASE,
)
_FRESH_FOR = timedelta(minutes=1)
_RETRY_AFTER = timedelta(seconds=15)
_MAX_RESPONSE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class GitHubStatus:
    label: str | None = None
    checked_at: datetime | None = None
    error: str | None = None
    stale: bool = False


class GitHubReader:
    def __init__(self, repository: str, token: str | None):
        self.repository = repository
        self._token = token
        self._statuses: dict[str, GitHubStatus] = {}
        self._retry_at: dict[str, datetime] = {}
        self._in_flight: set[str] = set()
        self._lock = Lock()

    def normalize(self, url: str) -> str:
        match = _LINK.fullmatch(url.strip())
        if match is None or match[1].lower() != self.repository.lower():
            raise ValueError("Ange en direkt HTTPS-länk till ett issue eller en pull request i det angivna repot.")
        return f"https://github.com/{self.repository}/{match[2].lower()}/{match[3]}"

    def status(self, url: str, *, refresh: bool = False) -> GitHubStatus:
        try:
            canonical = self.normalize(url)
        except ValueError:
            return GitHubStatus(error="Den sparade länken hör till ett annat repo än det konfigurerade.")
        if not self._token:
            return GitHubStatus(error="GitHub-läsning är inte aktiverad i den här demon.")
        now = datetime.now(UTC)
        with self._lock:
            cached = self._statuses.get(canonical, GitHubStatus())
            expired = cached.checked_at is not None and now - cached.checked_at >= _FRESH_FOR
            stale = cached.label is not None and (expired or cached.error is not None)
            can_retry = canonical not in self._retry_at or now >= self._retry_at[canonical]
            if not refresh or not can_retry or canonical in self._in_flight:
                return replace(cached, stale=stale)
            self._in_flight.add(canonical)
        result = None
        try:
            match = _LINK.fullmatch(canonical)
            label = self._read_label(match[2], match[3])
            result = GitHubStatus(label=label, checked_at=datetime.now(UTC))
            delay = _FRESH_FOR
        except (OSError, HTTPException, ValueError, RecursionError):
            result = replace(cached, error="GitHub-status kunde inte hämtas.", stale=cached.label is not None)
            delay = _RETRY_AFTER
        finally:
            with self._lock:
                self._in_flight.remove(canonical)
                # Uppdatera cachen innan någon annan tråd får påbörja nästa hämtning.
                if result is not None:
                    self._statuses[canonical] = result
                    self._retry_at[canonical] = datetime.now(UTC) + delay
        return result

    def _read_label(self, kind: str, number: str) -> str:
        collection = "pulls" if kind == "pull" else "issues"
        connection = HTTPSConnection("api.github.com", timeout=2)
        try:
            # Fast API-värd och inga omdirigeringar. Länken styr endast typ och nummer.
            connection.request("GET", f"/repos/{self.repository}/{collection}/{number}", headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "Artificiellalecta-Development",
                "X-GitHub-Api-Version": "2026-03-10",
            })
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError("GitHub returned a non-success status")
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                raise ValueError("GitHub response exceeded the size limit")
        finally:
            connection.close()
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("number") != int(number) or data.get("state") not in ("open", "closed"):
            raise ValueError("Unexpected GitHub response")
        if kind == "pull":
            if type(data.get("merged")) is not bool or type(data.get("draft")) is not bool:
                raise ValueError("Unexpected pull request state")
            if data["merged"]:
                return "Mergad"
            if data["state"] == "open" and data["draft"]:
                return "Utkast"
        elif "pull_request" in data:
            raise ValueError("The issue link points to a pull request")
        return "Öppen" if data["state"] == "open" else "Stängd"
