"""Appfabriken för handläggar-UI:t.

    app = create_app()                                  # inställningar ur miljön, databas enligt HANDLAGGARE_DB
    app = create_app(service=ServiceLayer(...), settings=WebSettings(...))   # t.ex. i tester

Bara lokalt: servern binds till 127.0.0.1 (`python -m web`), Host-huvudet
måste vara en lokal adress (skydd mot DNS-rebinding) och varje skrivformulär
bär en token per process (skydd mot att en annan webbplats postar hit).
Bolagsfrågornas operatörssession är separat från v1-handläggarens konfigurerade aktör.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from agents.case_workspace import CaseWorkspace
from agents.mission_archive import MissionArchive
from ai import AIClient
from services import ServiceLayer
from services.change_releases import ChangeReleases
from services.change_requests import ChangeRequests
from services.development_demo import DemoDelivery
from web.agent import CaseAgent
from web.config import WebConfigError, WebSettings
from web.development_github import GitHubReader
from web.handler import STATIC_DIR, new_csrf_token, render
from web.operator_auth import OperatorAuth
from web.operator_forms import HEADERS, Submissions
from web.presenters import ErrorView
from web.routes import (
    actuarial_dialogue,
    actuary,
    actuary_valuations,
    auth,
    case_workspace,
    cases,
    changes,
    company_missions,
    development,
    enrollment,
    environments,
    insured,
    journal,
    mission_archive,
    operator,
    parameters,
    premium_payments,
)

log = logging.getLogger("web")


def create_app(
    service: ServiceLayer | None = None, settings: WebSettings | None = None, case_agent: CaseAgent | None = None,
    case_workspace_console: CaseWorkspace | None = None,
    actuarial_dialogue_console=None,
    company_ai: AIClient | None = None,
) -> FastAPI:
    """case_agent: handläggaragenten för ärenden. Byggs med tjänstelagret om inget anges;
    med ett givet tjänstelager utan agent visas ärendena utan knappen *Starta agent*.

    """
    settings = settings or WebSettings.from_env()
    if company_ai is not None and (settings.database != "demo" or settings.operator_password_hash is None):
        raise WebConfigError("Bolagspiloten kräver demo och operatörsinloggning")
    if service is None:
        from web.database import build_services

        service, built_agent = build_services(settings)
        case_agent = case_agent or built_agent
    change_requests = (
        ChangeRequests(service._session_factory) if settings.database == "demo" and service._session_factory else None
    )
    app = FastAPI(title="Artificiellalecta – handläggare", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service
    app.state.change_requests = change_requests
    app.state.change_releases = (
        ChangeReleases(change_requests, DemoDelivery(settings.demo_path)) if change_requests is not None else None
    )
    app.state.company_missions = None
    if change_requests is not None and settings.operator_password_hash is not None:
        from web.database import build_company_missions

        app.state.company_missions = build_company_missions(
            settings, service, change_requests, app.state.change_releases, ai=company_ai,
        )
    app.state.development_github = GitHubReader(
        settings.development_github_repository, settings.development_github_token,
    ) if app.state.change_requests is not None else None
    app.state.case_agent = case_agent
    app.state.case_workspace = case_workspace_console or (
        CaseWorkspace.build(service, case_agent) if case_agent is not None and service._session_factory else None
    )
    app.state.actuarial_dialogue = actuarial_dialogue_console
    app.state.actuary_submissions = Submissions()
    app.state.mission_archive = MissionArchive(service._session_factory) if service._session_factory else None
    app.state.settings = settings
    app.state.csrf_token = new_csrf_token()
    app.state.operator_auth = OperatorAuth(settings.operator_id, settings.operator_password_hash)

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(auth.router)
    app.include_router(enrollment.router)  # före insured: /forsakrade/ny är inget personnummer
    app.include_router(insured.router)
    app.include_router(changes.router)
    app.include_router(journal.router)
    app.include_router(cases.router)
    app.include_router(premium_payments.router)
    app.include_router(case_workspace.router)
    app.include_router(parameters.router)
    app.include_router(environments.router)
    app.include_router(operator.router)
    app.include_router(mission_archive.router)
    app.include_router(company_missions.router)
    app.include_router(development.router)
    app.include_router(actuary.router)
    app.include_router(actuarial_dialogue.router)
    app.include_router(actuary_valuations.router)

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
        if request.url.path in {"/logga-in", "/logga-ut"}:
            # Ingen databasläsning eller återgivning av formulärvärden på autentiseringsfel.
            return auth.login_page(request, message="Förfrågan kunde inte genomföras. Ladda om inloggningssidan.",
                                   status_code=exc.status_code)
        title = {403: "Ej tillåtet", 404: "Sidan finns inte"}.get(exc.status_code, "Fel")
        detail = exc.detail if isinstance(exc.detail, str) else "Förfrågan kunde inte hanteras."
        if exc.status_code == 404 and detail == "Not Found":
            detail = "Adressen finns inte i handläggar-UI:t."
        error = ErrorView("error", title, detail, exc.status_code, nothing_changed=False)
        if request.url.path.startswith(development.BASE):
            return development.respond(request, "error.html", {"error": error}, status_code=exc.status_code)
        response = render(request, "error.html", {"error": error}, status_code=exc.status_code)
        if request.url.path.startswith((company_missions.BASE, company_missions.OLD_BASE, mission_archive.BASE, "/floden", "/team/aktuarie")):
            response.headers.update(HEADERS)
        return response

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        if request.url.path.startswith(development.BASE):
            error = ErrorView("error", "Utvecklingsytan är tillfälligt otillgänglig",
                              "Kontrollera ärendelistan innan du registrerar ärendet igen.", 503, nothing_changed=False)
            return development.respond(request, "error.html", {"error": error}, status_code=503)
        if request.url.path.startswith(("/arenden", "/godkannanden")):
            error = ErrorView("error", "Arbetsytan kunde inte läsas",
                              "Kontrollera anslutning och uppdragens status innan du försöker igen.",
                              503, nothing_changed=False)
            response = render(request, "error.html", {"error": error}, status_code=503)
            response.headers["Cache-Control"] = "no-store"
            return response
        if request.url.path.startswith((company_missions.BASE, company_missions.OLD_BASE, mission_archive.BASE, "/floden", "/team/aktuarie")):
            error = ErrorView("error", "Uppdraget kunde inte läsas", "Kontrollera uppdragslistan innan du försöker igen.",
                              503, nothing_changed=False)
            response = render(request, "error.html", {"error": error}, status_code=503)
            response.headers.update(HEADERS)
            return response
        if request.url.path in {"/logga-in", "/logga-ut"}:
            log.error("operator_auth_unavailable")
            return auth.login_page(request, message="Inloggningen är tillfälligt otillgänglig.", status_code=503)
        log.exception("Oväntat fel i handläggar-UI:t")
        error = ErrorView("error", "Oväntat fel", f"{type(exc).__name__}: {exc}", 500, nothing_changed=False)
        return render(request, "error.html", {"error": error}, status_code=500)

    return app
