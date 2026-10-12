"""Gemensamt för sidorna: tjänstelagret, handläggarens kontext, CSRF och mallrendering.

Allt som rör data går genom `ServiceLayer`: läsoperationer med `read()`,
ändringar med `ServiceLayer.execute/approve/reject` i respektive sida. Aktören
är alltid handläggaren ur konfigurationen (`Actor.human(HANDLAGGARE_ID)`).
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from services import Actor, OperationContext, ServiceLayer
from web import presenters
from web.config import WebSettings

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
)
templates.env.globals["field_names"] = presenters.FIELD_NAMES


def service(request: Request) -> ServiceLayer:
    return request.app.state.service


def settings(request: Request) -> WebSettings:
    return request.app.state.settings


def handler_ctx(request: Request, reason: str | None = None) -> OperationContext:
    """Handläggaren som aktör – samma spår i händelseloggen som agenter och skript."""
    return OperationContext(actor=Actor.human(settings(request).handler_id), reason=reason)


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


def render(request: Request, template: str, context: dict[str, Any] | None = None, status_code: int = 200):
    base = {
        "settings": settings(request),
        "csrf_token": request.app.state.csrf_token,
        "rules": service(request).rules,
    }
    return templates.TemplateResponse(request, template, {**base, **(context or {})}, status_code=status_code)


def render_error(
    request: Request, exc: Exception, template: str = "error.html", context: dict | None = None, *, write: bool = False
):
    error = presenters.describe_error(exc, service(request).rules, write=write)
    return render(request, template, {"error": error, **(context or {})}, status_code=error.status_code)
