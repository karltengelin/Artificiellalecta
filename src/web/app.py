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
from agents.flows.console import FlowConsole
from agents.flows.product_reports import ProductReportConsole
from agents.flows.questions import QuestionConsole
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
from web.presenters import ErrorView
from web.routes import (
    actuarial_dialogue,
    actuary,
    actuary_valuations,
    auth,
    case_workspace,
    cases,
    changes,
    development,
    enrollment,
    environments,
    flows,
    insured,
    journal,
    operator,
    parameters,
    premium_payments,
    questions,
)

log = logging.getLogger("web")


def create_app(
    service: ServiceLayer | None = None, settings: WebSettings | None = None, case_agent: CaseAgent | None = None,
    flow_console: FlowConsole | None = None,
    question_console: QuestionConsole | None = None,
    case_workspace_console: CaseWorkspace | None = None,
    product_report_console: ProductReportConsole | None = None,
    actuarial_dialogue_console=None,
    rule_flow_ai: AIClient | None = None,
) -> FastAPI:
    """case_agent: handläggaragenten för ärenden. Byggs med tjänstelagret om inget anges;
    med ett givet tjänstelager utan agent visas ärendena utan knappen *Starta agent*.

    question_console: explicit ansluten OC-3a-adapter, gemensam för centralen och aktuariens teamyta.
    flow_console: flödena (`/floden`, Fas 3c 3c-3) på samma sätt. Steg som stod som pågående
    när UI:t senast stoppades blir `reconciliation_required` här och avgörs av handläggaren.
    rule_flow_ai: anslut demo med de två regeländringsflödena och operatörens utvecklingsyta."""
    settings = settings or WebSettings.from_env()
    if rule_flow_ai is not None and (
        settings.database != "demo" or settings.operator_password_hash is None or flow_console is not None
    ):
        raise WebConfigError("Regeländringsflöden med utvecklingsöverlämning kräver demo och operatörsinloggning")
    if service is None:
        from web.database import build_services

        service, built_agent, built_flows = build_services(settings)
        case_agent = case_agent or built_agent
        flow_console = flow_console or built_flows
    change_requests = (
        ChangeRequests(service._session_factory) if settings.database == "demo" and service._session_factory else None
    )
    if rule_flow_ai is not None:
        from web.database import build_demo_rule_flows

        if change_requests is None:
            raise WebConfigError("Utvecklingsöverlämning kräver en demodatabas")
        flow_console = build_demo_rule_flows(service, change_requests, ai=rule_flow_ai)
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
    app.state.change_requests = change_requests
    app.state.change_releases = (
        ChangeReleases(change_requests, DemoDelivery(settings.demo_path)) if change_requests is not None else None
    )
    app.state.development_github = GitHubReader(
        settings.development_github_repository, settings.development_github_token,
    ) if app.state.change_requests is not None else None
    app.state.case_agent = case_agent
    app.state.case_workspace = case_workspace_console or (
        CaseWorkspace.build(service, case_agent) if case_agent is not None and service._session_factory else None
    )
    app.state.flow_console = flow_console
    app.state.question_console = question_console
    app.state.product_report_console = product_report_console
    app.state.actuarial_dialogue = actuarial_dialogue_console
    app.state.question_submissions = questions.Submissions()
    app.state.actuary_submissions = questions.Submissions()
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
    app.include_router(flows.router)
    app.include_router(environments.router)
    app.include_router(operator.router)
    app.include_router(development.router)
    app.include_router(actuary.router)
    app.include_router(actuarial_dialogue.router)
    app.include_router(actuary_valuations.router)
    app.include_router(questions.router)

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
        if request.url.path.startswith(("/central/fragor", "/team/aktuarie")):
            response.headers.update(questions.HEADERS)
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
        if request.url.path.startswith(("/central/fragor", "/team/aktuarie")):
            error = ErrorView("error", "Uppdraget kunde inte läsas", "Kontrollera uppdragslistan innan du försöker igen.",
                              503, nothing_changed=False)
            response = render(request, "error.html", {"error": error}, status_code=503)
            response.headers.update(questions.HEADERS)
            return response
        if request.url.path in {"/logga-in", "/logga-ut"}:
            log.error("operator_auth_unavailable")
            return auth.login_page(request, message="Inloggningen är tillfälligt otillgänglig.", status_code=503)
        log.exception("Oväntat fel i handläggar-UI:t")
        error = ErrorView("error", "Oväntat fel", f"{type(exc).__name__}: {exc}", 500, nothing_changed=False)
        return render(request, "error.html", {"error": error}, status_code=500)

    return app
