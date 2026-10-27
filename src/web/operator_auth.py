"""Lokal operatörssession för bolagsfrågor, OC-3a val H–I.

Inga databasrättigheter eller policy_admin följer av sessionen. Äldre
handläggarvägar använder fortsatt sin befintliga kontext och processtoken.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from threading import Lock
from urllib.parse import urlsplit

from argon2 import PasswordHasher, Type, extract_parameters
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request

from services import Actor

IDLE_SECONDS = 15 * 60
LIFETIME_SECONDS = 8 * 60 * 60
ATTEMPT_WINDOW_SECONDS = 5 * 60
MAX_FAILURES = 5
MAX_SESSIONS = 256
MAX_PASSWORD_LENGTH = 1024


def validate_password_hash(encoded: str | None) -> None:
    if encoded is None:
        return
    try:
        if extract_parameters(encoded).type != Type.ID:
            raise ValueError
    except (InvalidHashError, ValueError, TypeError):
        raise ValueError("OPERATOR_PASSWORD_HASH måste vara en giltig Argon2id-hash från provisioneringsskriptet") from None


@dataclass(frozen=True)
class OperatorSession:
    operator_id: str | None
    csrf_token: str = field(repr=False)
    created_at: float
    last_seen: float


class LoginRejected(Exception):
    def __init__(self, status_code: int, retry_after: int | None = None):
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__("Inloggningen kunde inte genomföras")


class OperatorAuth:
    def __init__(self, operator_id: str, password_hash: str | None, *, clock: Callable[[], float] = time.monotonic):
        validate_password_hash(password_hash)
        self.operator_id = operator_id
        self._password_hash = password_hash
        self._clock = clock
        self._hasher = PasswordHasher()
        self._sessions: dict[str, OperatorSession] = {}
        self._failures: deque[float] = deque()
        self._blocked_until = 0.0
        self._lock = Lock()

    @property
    def enabled(self) -> bool:
        return self._password_hash is not None

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _prune(self, now: float) -> None:
        for key, item in list(self._sessions.items()):
            if now - item.last_seen >= IDLE_SECONDS or now - item.created_at >= LIFETIME_SECONDS:
                del self._sessions[key]

    def _create(self, operator_id: str | None, now: float) -> tuple[str, OperatorSession]:
        self._prune(now)
        if len(self._sessions) >= MAX_SESSIONS:
            anonymous = next((key for key, item in self._sessions.items() if item.operator_id is None), None)
            if anonymous is None:
                raise LoginRejected(503)
            del self._sessions[anonymous]
        token = secrets.token_urlsafe(32)
        item = OperatorSession(operator_id, secrets.token_urlsafe(32), now, now)
        self._sessions[self._key(token)] = item
        return token, item

    def anonymous(self) -> tuple[str, OperatorSession]:
        with self._lock:
            return self._create(None, self._clock())

    def resolve(self, token: str | None) -> OperatorSession | None:
        if not token or len(token) > 128:
            return None
        with self._lock:
            now = self._clock()
            self._prune(now)
            key = self._key(token)
            item = self._sessions.get(key)
            if item is not None:
                item = replace(item, last_seen=now)
                self._sessions[key] = item
            return item

    def revoke(self, token: str | None) -> None:
        if token and len(token) <= 128:
            with self._lock:
                self._sessions.pop(self._key(token), None)

    def authenticate(self, token: str, username: str, password: str) -> tuple[str, OperatorSession]:
        # En gemensam gräns för den enda operatören; namn, IP och X-Forwarded-For
        # kan inte kringgå den. Låset omfattar verifieringen även vid samtidiga anrop.
        with self._lock:
            now = self._clock()
            self._prune(now)
            if not self.enabled:
                raise LoginRejected(503)
            if now < self._blocked_until:
                raise LoginRejected(429, max(1, int(self._blocked_until - now) + 1))
            if len(token) > 128 or self._key(token) not in self._sessions:
                raise LoginRejected(403)
            while self._failures and self._failures[0] <= now - ATTEMPT_WINDOW_SECONDS:
                self._failures.popleft()
            valid = False
            if 0 < len(password) <= MAX_PASSWORD_LENGTH and len(username) <= 100:
                try:
                    # Samma lösenordsarbete även för ett felaktigt operatörsnamn.
                    valid = self._hasher.verify(self._password_hash, password)
                except (VerificationError, InvalidHashError):
                    pass
                valid = secrets.compare_digest(username.encode(), self.operator_id.encode()) and valid
            if not valid:
                self._failures.append(now)
                if len(self._failures) >= MAX_FAILURES:
                    self._blocked_until = now + ATTEMPT_WINDOW_SECONDS
                    self._failures.clear()
                    raise LoginRejected(429, ATTEMPT_WINDOW_SECONDS)
                raise LoginRejected(401)
            self._failures.clear()
            self._sessions.pop(self._key(token), None)
            return self._create(self.operator_id, self._clock())


def cookie_name(request: Request) -> str:
    # Miljöernas servrar delar värdnamn: cookies har ingen portavgränsning.
    return "__Host-al-operator-" + request.app.state.settings.database


def current_session(request: Request) -> OperatorSession | None:
    if not hasattr(request.state, "operator_session"):
        auth = request.app.state.operator_auth
        request.state.operator_session = auth.resolve(request.cookies.get(cookie_name(request))) if auth.enabled else None
    return request.state.operator_session


def check_transport(request: Request) -> None:
    if request.url.scheme != "https" and not (
        request.url.scheme == "http" and request.url.hostname in {"127.0.0.1", "localhost", "::1"}
    ):
        raise HTTPException(403, "Operatörsinloggningen kräver lokal loopback eller HTTPS")


def check_origin(request: Request) -> None:
    """Exakt ursprung, inklusive port; ingen tillit till proxyhuvuden."""
    check_transport(request)
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Förfrågan måste komma från samma ursprung")
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    expected = (request.url.scheme, request.url.netloc)
    try:
        supplied = urlsplit(origin if origin is not None else referer or "")
        valid = (supplied.scheme, supplied.netloc) == expected and not supplied.username and not supplied.password
        if origin is not None:
            valid = valid and not supplied.path and not supplied.query and not supplied.fragment
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(403, "Förfrågan måste komma från samma ursprung")


def check_session_csrf(request: Request, form: dict) -> OperatorSession:
    check_origin(request)
    item = current_session(request)
    token = form.get("csrf_token", "")
    if item is None or not isinstance(token, str) or len(token) > 128 or not secrets.compare_digest(
        token.encode(), item.csrf_token.encode(),
    ):
        raise HTTPException(403, "Ogiltig eller utgången formulärtoken – ladda om sidan")
    return item


def operator_actor(request: Request) -> Actor:
    """Identitet för nya bolagsfrågor, aldrig ur formulär eller HANDLAGGARE_ID."""
    check_transport(request)
    item = current_session(request)
    if item is None or item.operator_id is None:
        raise HTTPException(401, "Logga in som operatör för att fortsätta")
    return Actor.human(item.operator_id)


def operator_action(request: Request, form: dict) -> Actor:
    """Starta/kör/granska/avbryt: anropa före uppdragsadaptern i varje skrivväg."""
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        raise HTTPException(405, "Åtgärden kräver en skrivförfrågan")
    actor = operator_actor(request)
    check_session_csrf(request, form)
    return actor
