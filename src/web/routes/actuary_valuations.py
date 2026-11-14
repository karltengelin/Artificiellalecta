# ruff: noqa: BLE001 -- Sanerade fel vid webbgränsen.
"""Människans värderingsväg. Beräkning, urval och beslut ägs av tjänstelagret."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from services import OperationContext, ServiceError
from web.handler import read, service
from web.operator_auth import operator_action
from web.operator_forms import HEADERS
from web.presenters import describe_error
from web.routes.actuary import consume, page, token
from web.routes.auth import auth_form

router = APIRouter()
ROOT = "/team/aktuarie/varderingar"
STATUS = {"draft": "Utkast", "locked": "Fastställd", "superseded": "Ersatt"}
PURPOSE = {"base": "Bas", "scenario": "Scenario"}


def listing(request, *, error=None, values=None, status_code=200):
    try:
        runs = read(request, "list_valuation_runs", {}).runs
        bases = read(request, "list_valuation_bases", {}).bases
    except Exception:
        raise HTTPException(503, "Värderingarna eller grundregistret kunde inte läsas. Kontrollera anslutningen.") from None
    return page(request, "actuary_valuations.html", {"runs": runs, "bases": bases,
        "valuation_status": STATUS, "valuation_purpose": PURPOSE, "error": error,
        "values": values or {}, "request_token": token(request, "valuation:start")}, status_code=status_code)


@router.get(ROOT)
def valuation_list(request: Request):
    return listing(request)


@router.post(ROOT)
async def valuation_start(request: Request):
    form = await auth_form(request, {"csrf_token", "request_token", "valuation_date", "purpose",
                                    "basis_code", "curve_code", "note"})
    actor = operator_action(request, form)
    note = form.get("note", "").strip()
    if not note or len(note) > 1000:
        return await run_in_threadpool(listing, request, error="Ange en motivering på 1–1 000 tecken.",
                                       values=form, status_code=422)
    consume(request, form, "valuation:start")
    data = {key: form.get(key, "") for key in ("valuation_date", "purpose")}
    data.update({key: form.get(key) or None for key in ("basis_code", "curve_code")})
    try:
        result = await run_in_threadpool(service(request).execute, "run_valuation",
                                        OperationContext(actor=actor, reason=note), data)
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        return await run_in_threadpool(listing, request, error=error.message + " Ingenting har ändrats.",
                                       values=form, status_code=error.status_code)
    except Exception:
        raise HTTPException(503, "Körningens utfall behöver kontrolleras. Läs värderingslistan innan du försöker igen.") from None
    return RedirectResponse(f"{ROOT}/{result.output.run_id}", status_code=303, headers=HEADERS)


def detail(request, run_id, *, error=None, status_code=200):
    try:
        run = read(request, "get_valuation_run", {"run_id": run_id})
    except ServiceError as exc:
        view = describe_error(exc, service(request).rules)
        raise HTTPException(view.status_code, view.message) from None
    except Exception:
        raise HTTPException(503, "Värderingskörningen kunde inte läsas.") from None
    return page(request, "actuary_valuation.html", {"run": run, "error": error,
        "valuation_status": STATUS, "valuation_purpose": PURPOSE,
        "request_token": token(request, f"valuation:lock:{run.run_id}:{run.review_checksum}")}, status_code=status_code)


@router.get(ROOT + "/{run_id}")
def valuation_detail(request: Request, run_id: UUID):
    return detail(request, run_id)


@router.post(ROOT + "/{run_id}/faststall")
async def valuation_lock(request: Request, run_id: UUID):
    form = await auth_form(request, {"csrf_token", "request_token", "reviewed_checksum", "reviewed", "note"})
    actor = operator_action(request, form)
    note = form.get("note", "").strip()
    if form.get("reviewed") != "yes" or not note or len(note) > 1000:
        return await run_in_threadpool(detail, request, run_id,
            error="Bekräfta granskningen och ange en beslutsmotivering på 1–1 000 tecken.", status_code=422)
    checksum = form.get("reviewed_checksum", "")
    consume(request, form, f"valuation:lock:{run_id}:{checksum}")
    try:
        await run_in_threadpool(service(request).execute, "lock_valuation", OperationContext(actor=actor, reason=note),
                               {"run_id": run_id, "reviewed_checksum": checksum})
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        return await run_in_threadpool(detail, request, run_id, error=error.message + " Ingenting har ändrats.",
                                       status_code=error.status_code)
    except Exception:
        raise HTTPException(503, "Beslutets utfall behöver kontrolleras. Läs körningen innan du försöker igen.") from None
    return RedirectResponse(f"{ROOT}/{run_id}", status_code=303, headers=HEADERS)
