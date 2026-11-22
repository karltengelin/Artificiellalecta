"""Granska och kvittera Paket C:s lokala rapporter i operatörscentralen."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from reporting.premium_deliveries import STATUSES, identity
from reporting.premium_statement import DAYS
from web.handler import render
from web.operator_auth import operator_action, operator_actor
from web.operator_forms import HEADERS
from web.routes.auth import auth_form

BASE = "/central/premierapporter"
router = APIRouter()


def store(request):
    if request.app.state.settings.database != "demo":
        raise HTTPException(404, "Premierapporterna hör till den lokala demomiljön")
    return request.app.state.premium_deliveries


def page(request, template, **context):
    response = render(request, template, {"base": BASE, "statuses": STATUSES, "days": DAYS,
                      "operator_page": True, **context}, check_database=False)
    response.headers.update(HEADERS)
    return response


@router.get(BASE)
def inbox(request: Request):
    operator_actor(request)
    registry = store(request)
    return page(request, "premium_reports.html", records=registry.listing(), runs=registry.sources())


@router.post(BASE + "/bered")
async def prepare(request: Request):
    form = await auth_form(request, {"csrf_token", "run", "day", "source_run", "previous", "reason"})
    actor = operator_action(request, form)
    registry = store(request)
    run, day = form.get("run", ""), form.get("day", "")
    try:
        rev = await run_in_threadpool(registry.prepare, run, day, actor.id, previous=form.get("previous", ""),
                                      reason=form.get("reason", ""), source_run=form.get("source_run", ""))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return RedirectResponse(f"{BASE}/{identity(run, day)}/{rev}", 303, headers=HEADERS)


@router.get(BASE + "/{ident}/{rev}")
def detail(request: Request, ident: str, rev: int):
    operator_actor(request)
    try:
        record = store(request).get(ident, rev)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    return page(request, "premium_report.html", record=record, p=record["packet"])


@router.get(BASE + "/{ident}/{rev}/underlag")
def evidence(request: Request, ident: str, rev: int):
    operator_actor(request)
    try:
        record = store(request).get(ident, rev, specialist=True)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    return page(request, "premium_evidence.html", record=record)


@router.post(BASE + "/{ident}/{rev}")
async def submit(request: Request, ident: str, rev: int):
    form = await auth_form(request, {"csrf_token", "digest", "action", "reason"})
    actor = operator_action(request, form)
    try:
        await run_in_threadpool(store(request).act, ident, rev, form.get("digest", ""),
                                form.get("action", ""), actor.id, form.get("reason", ""))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return RedirectResponse(f"{BASE}/{ident}/{rev}", 303, headers=HEADERS)
