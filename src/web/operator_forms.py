"""Gemensamma svarshuvuden och engångsformulär för operatören."""

import secrets
import threading
import time

from fastapi import HTTPException

HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
           "Content-Security-Policy": "frame-ancestors 'none'; form-action 'self'; base-uri 'none'"}


class Submissions:
    """Korta, sessionsbundna engångsnycklar för beslut i webbformulär."""

    def __init__(self):
        self._items = {}
        self._lock = threading.Lock()

    def issue(self, session_key):
        with self._lock:
            now = time.monotonic()
            self._items = {k: v for k, v in self._items.items() if now - v[0] < 8 * 3600}
            if len(self._items) >= 4096:
                raise HTTPException(503, "För många öppna formulär")
            token = secrets.token_urlsafe(32)
            self._items[token] = (now, session_key)
            return token

    def take(self, token, session_key):
        with self._lock:
            item = self._items.get(token)
            if item is None or item[1] != session_key or time.monotonic() - item[0] >= 8 * 3600:
                raise HTTPException(409, "Formuläret har använts eller gått ut. Ladda om sidan.")
            del self._items[token]
