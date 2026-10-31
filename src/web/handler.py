"""Gemensamt för sidorna: tjänstelagret, handläggarens kontext, CSRF och mallrendering.

Allt som rör data går genom `ServiceLayer`: läsoperationer med `read()`,
ändringar med `ServiceLayer.execute/approve/reject` i respektive sida. Aktören
är alltid handläggaren ur konfigurationen (`Actor.human(HANDLAGGARE_ID)`).
"""

from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from services import Actor, OperationContext, ServiceLayer
from web import presenters
from web.config import SWITCHABLE_DATABASES, WebSettings
from web.operator_auth import current_session

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.filters.update(
    sek=presenters.sek,
    number=presenters.number,
    iso_date=presenters.iso_date,
    month=presenters.month,
    pnr=presenters.personal_id,
    label=presenters.label,
    pretty_json=lambda value: json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
)
templates.env.globals["field_names"] = presenters.FIELD_NAMES


def static_version() -> str:
    """Kort innehållshash för CSS och JavaScript, så att ändringar hämtas direkt."""
    digest = hashlib.sha256()
    for path in sorted(p for p in STATIC_DIR.iterdir() if p.suffix in {".css", ".js", ".mjs"}):
        digest.update(path.name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()[:12]


templates.env.globals["static_version"] = static_version()


def service(request: Request) -> ServiceLayer:
    return request.app.state.service


def settings(request: Request) -> WebSettings:
    return request.app.state.settings


def handler_ctx(request: Request, reason: str | None = None, case_id: str | None = None) -> OperationContext:
    """Handläggaren som aktör – samma spår i händelseloggen som agenter och skript.

    case_id: ärendet ändringen görs i (Fas 5), så att den syns i ärendets historik.
    """
    return OperationContext(actor=Actor.human(settings(request).handler_id), reason=reason, case_id=case_id)


def read(request: Request, operation: str, data: dict[str, Any]) -> BaseModel:
    """En läsoperation (synkront – anropas från sidor som körs i trådpoolen)."""
    return service(request).execute(operation, handler_ctx(request), data).output


async def read_async(request: Request, operation: str, data: dict[str, Any]) -> BaseModel:
    return await run_in_threadpool(read, request, operation, data)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def check_csrf(request: Request, form: Any) -> None:
    """Skrivformulär bär processens token – en annan webbplats kan inte posta hit i handläggarens namn."""
    token = form.get("csrf_token", "")
    if not secrets.compare_digest(str(token), request.app.state.csrf_token):
        raise HTTPException(status_code=403, detail="Ogiltig eller saknad formulärtoken – ladda om sidan")


def render(
    request: Request, template: str, context: dict[str, Any] | None = None, status_code: int = 200,
    *, push_url: str | None = None,
):
    """push_url: adressen HTMX lägger i historiken – en sida som går att ladda om, inte formulärets POST-adress."""
    pending = pending_approvals(request)
    operator = current_session(request)
    base = {
        "settings": settings(request),
        "csrf_token": request.app.state.csrf_token,
        "rules": service(request).rules,
        "pending_approvals": pending,
        "database_available": pending is not None,
        "flows_available": getattr(request.app.state, "flow_console", None) is not None,
        "environment_choices": SWITCHABLE_DATABASES,
        "operator_auth_enabled": request.app.state.operator_auth.enabled,
        "operator_user": operator.operator_id if operator else None,
        "operator_csrf": operator.csrf_token if operator and operator.operator_id else None,
        "page_referrer_policy": "same-origin" if operator and operator.operator_id else "no-referrer",
    }
    response = templates.TemplateResponse(request, template, {**base, **(context or {})}, status_code=status_code)
    response.headers["Referrer-Policy"] = base["page_referrer_policy"]
    if push_url:
        response.headers["HX-Push-Url"] = push_url
    return response


def pending_approvals(request: Request) -> int | None:
    """Antal väntande förslag i menyn (count_approval_requests – inga personuppgifter, loggas inte)."""
    try:
        return service(request).execute("count_approval_requests", handler_ctx(request), {}).output.pending
    except Exception:  # noqa: BLE001 – menyn ska visas även om databasen inte svarar
        return None


def render_error(
    request: Request, exc: Exception, template: str = "error.html", context: dict | None = None, *, write: bool = False
):
    error = presenters.describe_error(exc, service(request).rules, write=write)
    return render(request, template, {"error": error, **(context or {})}, status_code=error.status_code)
