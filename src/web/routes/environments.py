"""Miljöval navigerar mellan separata servrar och ändrar aldrig appens databas."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from web.config import SWITCHABLE_DATABASES
from web.environments import EnvironmentUnavailable, ensure_environment
from web.handler import check_csrf, render, settings
from web.presenters import ErrorView

router = APIRouter()


@router.post("/miljo")
async def switch_environment(request: Request):
    form = await request.form()
    check_csrf(request, form)
    database = str(form.get("database", ""))
    status = 200
    message = None
    url = "/"
    if database not in SWITCHABLE_DATABASES:
        status, message = 422, "Välj Lakebase eller Demo."
    elif database != settings(request).database:
        try:
            url = await run_in_threadpool(ensure_environment, database)
        except EnvironmentUnavailable as exc:
            status, message = 503, str(exc)
    headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    if "application/json" in request.headers.get("Accept", ""):
        return JSONResponse({"message": message} if message else {"url": url}, status_code=status, headers=headers)
    if message:
        return render(request, "search.html", {
            "query": "", "error": ErrorView("error", "Miljön kunde inte öppnas", message, status, nothing_changed=True),
        }, status_code=status)
    return RedirectResponse(url, status_code=303, headers=headers)
