"""Appfabriken för handläggar-UI:t.

    app = create_app()                                  # inställningar ur miljön, databas enligt HANDLAGGARE_DB
    app = create_app(service=ServiceLayer(...), settings=WebSettings(...))   # t.ex. i tester

Bara lokalt: servern binds till 127.0.0.1 (`python -m web`), Host-huvudet
måste vara en lokal adress (skydd mot DNS-rebinding) och varje skrivformulär
bär en token per process (skydd mot att en annan webbplats postar hit).
Ingen inloggning i v1 – aktören är handläggaren ur konfigurationen.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from agents.flows.console import FlowConsole
from services import ServiceLayer
from web.agent import CaseAgent
from web.config import WebSettings
from web.handler import STATIC_DIR, new_csrf_token, render
from web.presenters import ErrorView
from web.routes import (
    cases,
    changes,
    enrollment,
    environments,
    flows,
    insured,
    journal,
    parameters,
)

log = logging.getLogger("web")


def create_app(
    service: ServiceLayer | None = None, settings: WebSettings | None = None, case_agent: CaseAgent | None = None,
    flow_console: FlowConsole | None = None,
) -> FastAPI:
    """case_agent: handläggaragenten för ärenden. Byggs med tjänstelagret om inget anges;
    med ett givet tjänstelager utan agent visas ärendena utan knappen *Starta agent*.

    flow_console: flödena (`/floden`, Fas 3c 3c-3) på samma sätt. Steg som stod som pågående
    när UI:t senast stoppades blir `reconciliation_required` här och avgörs av handläggaren."""
    settings = settings or WebSettings.from_env()
    if service is None:
        from web.database import build_services

        service, built_agent, built_flows = build_services(settings)
        case_agent = case_agent or built_agent
        flow_console = flow_console or built_flows
    if flow_console is not None:
        try:
            interrupted = flow_console.mark_interrupted()
        except Exception:  # UI:t startar även om databasen inte svarar; sidan visar felet
            log.exception("Avbrutna flödessteg kunde inte markeras")
        else:
            if interrupted:
                log.warning("Flödessteg som pågick vid omstart kräver avstämning: %s", ", ".join(interrupted))

    app = FastAPI(title="Artificiellalecta – handläggare", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service
    app.state.case_agent = case_agent
    app.state.flow_console = flow_console
    app.state.settings = settings
    app.state.csrf_token = new_csrf_token()

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(enrollment.router)  # före insured: /forsakrade/ny är inget personnummer
    app.include_router(insured.router)
    app.include_router(changes.router)
    app.include_router(journal.router)
    app.include_router(cases.router)
    app.include_router(parameters.router)
    app.include_router(flows.router)
    app.include_router(environments.router)

    @app.get("/_instance")
    def instance(request: Request):
        """Startskriptets miljökontroll; inga databasfrågor eller anslutningsuppgifter."""
        return JSONResponse(
            {"application": "artificiellalecta-handlaggare", "database": request.app.state.settings.database,
             "environment_switching": True},
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        title = {403: "Ej tillåtet", 404: "Sidan finns inte"}.get(exc.status_code, "Fel")
        detail = exc.detail if isinstance(exc.detail, str) else "Förfrågan kunde inte hanteras."
        if exc.status_code == 404 and detail == "Not Found":
            detail = "Adressen finns inte i handläggar-UI:t."
        error = ErrorView("error", title, detail, exc.status_code, nothing_changed=False)
        return render(request, "error.html", {"error": error}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        log.exception("Oväntat fel i handläggar-UI:t")
        error = ErrorView("error", "Oväntat fel", f"{type(exc).__name__}: {exc}", 500, nothing_changed=False)
        return render(request, "error.html", {"error": error}, status_code=500)

    return app
