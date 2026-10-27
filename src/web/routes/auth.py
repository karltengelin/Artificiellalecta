"""Inloggning och utloggning för operatören; inget databas- eller modellanrop."""

import logging
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from web.handler import templates
from web.operator_auth import (
    LIFETIME_SECONDS,
    LoginRejected,
    check_origin,
    check_session_csrf,
    check_transport,
    cookie_name,
    current_session,
    operator_action,
)

router = APIRouter()
log = logging.getLogger("web.auth")
HEADERS = {
    "Cache-Control": "no-store",
    # no-referrer gör Origin=null för vanliga POST-formulär i Chromium.
    # same-origin behåller ursprungsbeviset utan referer till andra webbplatser.
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'; form-action 'self'; base-uri 'none'",
}


def set_session_cookie(request: Request, response, token: str) -> None:
    response.set_cookie(cookie_name(request), token, max_age=LIFETIME_SECONDS, path="/",
                        secure=True, httponly=True, samesite="strict")


async def auth_form(request: Request, allowed: set[str]) -> dict[str, str]:
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Använd inloggningsformuläret")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16384:
            raise HTTPException(413, "Formuläret är för stort")
    try:
        fields = parse_qs(body.decode("utf-8"), keep_blank_values=True, max_num_fields=8, strict_parsing=True)
        if fields.keys() - allowed or any(len(values) != 1 for values in fields.values()):
            raise ValueError
    except (UnicodeError, ValueError):
        raise HTTPException(400, "Ogiltigt formulär") from None
    return {key: values[0] for key, values in fields.items()}


def login_page(request: Request, *, session=None, message=None, status_code=200, retry_after=None):
    auth = request.app.state.operator_auth
    response = templates.TemplateResponse(request, "login.html", {
        "operator_id": auth.operator_id, "auth_enabled": auth.enabled,
        "session_csrf": session.csrf_token if session else "", "message": message,
        "database_label": request.app.state.settings.database_label,
    }, status_code=status_code, headers=HEADERS)
    if retry_after is not None:
        response.headers["Retry-After"] = str(retry_after)
    return response


@router.get("/logga-in")
def login(request: Request):
    auth = request.app.state.operator_auth
    if not auth.enabled:
        return login_page(request, message="Operatörsinloggningen är inte konfigurerad. Kontakta operatören.", status_code=503)
    check_transport(request)
    item = current_session(request)
    if item is not None and item.operator_id is not None:
        return RedirectResponse("/central", status_code=303, headers=HEADERS)
    if item is not None:
        return login_page(request, session=item)
    try:
        token, item = auth.anonymous()
    except LoginRejected:
        return login_page(request, message="Inloggningen är tillfälligt otillgänglig. Försök igen senare.", status_code=503)
    response = login_page(request, session=item)
    set_session_cookie(request, response, token)
    return response


@router.post("/logga-in")
async def submit_login(request: Request):
    auth = request.app.state.operator_auth
    if not auth.enabled:
        return login_page(request, message="Operatörsinloggningen är inte konfigurerad. Kontakta operatören.", status_code=503)
    check_origin(request)
    form = await auth_form(request, {"username", "password", "csrf_token"})
    item = check_session_csrf(request, form)
    try:
        token, _ = await run_in_threadpool(
            auth.authenticate, request.cookies.get(cookie_name(request), ""),
            form.get("username", ""), form.get("password", ""),
        )
    except LoginRejected as exc:
        log.warning("operator_login_rejected")
        message = "Inloggningen kunde inte genomföras. Kontrollera uppgifterna."
        if exc.status_code == 429:
            message = "För många misslyckade försök. Vänta fem minuter innan du försöker igen."
        return login_page(request, session=item, message=message, status_code=exc.status_code, retry_after=exc.retry_after)
    log.info("operator_login_succeeded")
    response = RedirectResponse("/central", status_code=303, headers=HEADERS)
    set_session_cookie(request, response, token)
    return response


@router.post("/logga-ut")
async def logout(request: Request):
    form = await auth_form(request, {"csrf_token"})
    operator_action(request, form)
    request.app.state.operator_auth.revoke(request.cookies.get(cookie_name(request)))
    log.info("operator_logged_out")
    response = RedirectResponse("/central", status_code=303, headers=HEADERS)
    response.delete_cookie(cookie_name(request), path="/", secure=True, httponly=True, samesite="strict")
    return response
