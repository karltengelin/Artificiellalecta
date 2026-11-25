"""Simulerad affärsdag för handläggar-UI:t i en lokal provkörning (paket B steg 8, B-056, Z13).

Paket C:s kalender kör operationerna med `services.operations.common.business_day`; webbsidan får samma
klocka per förfrågan så att en handläggare kan gå igenom ett scenario dag för dag. Middleware sätts bara
när `WebSettings.business_day` är satt, och inställningen godtas bara för den lokala demodatabasen.
"""

from __future__ import annotations

from datetime import date

from services.operations.common import business_day


class BusinessDayMiddleware:
    """ASGI-middleware: varje förfrågan körs med den simulerade affärsdagen."""

    def __init__(self, app, day: date):
        self.app = app
        self.day = day

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        with business_day(self.day):
            await self.app(scope, receive, send)
