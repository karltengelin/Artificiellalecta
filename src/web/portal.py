"""Behörighet vid plattformens webbgräns."""

from fastapi import HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response

from web.operator_auth import Role, signed_in_session

PUBLIC_PATHS = {"/", "/logga-in", "/logga-ut", "/_instance"}
HANDLER_AREAS = (
    "/sok", "/forsakrade", "/forsakringar", "/arbetsgivare", "/arenden",
    "/premier", "/pensioner", "/godkannanden", "/berakna", "/miljo",
)
HANDLER_APPROVALS = (
    "enroll_insured_person", "receive_premium_payment", "register_salary_report", "set_policy_paid_up",
)
PRIVATE = {"Cache-Control": "no-store", "Referrer-Policy": "same-origin"}


def home_for(role: Role | None) -> str:
    return "/sok" if role == Role.HANDLER else "/central"


async def authorize(request: Request, call_next):
    path = request.url.path
    if not request.app.state.settings.portal_login or path in PUBLIC_PATHS or path.startswith("/static/"):
        return await call_next(request)

    try:
        session = signed_in_session(request)
    except HTTPException as exc:
        if exc.status_code == 401 and request.method in {"GET", "HEAD"}:
            if request.headers.get("HX-Request"):
                return Response(headers={**PRIVATE, "HX-Redirect": "/logga-in"})
            return RedirectResponse("/logga-in", status_code=303, headers=PRIVATE)
        return PlainTextResponse(exc.detail, status_code=exc.status_code, headers=PRIVATE)

    if session.role != Role.OPERATOR and not any(
        path == prefix or path.startswith(prefix + "/") for prefix in HANDLER_AREAS
    ):
        return PlainTextResponse("Sidan kräver operatörens behörighet.", status_code=403, headers=PRIVATE)

    response = await call_next(request)
    response.headers.update(PRIVATE)
    return response
