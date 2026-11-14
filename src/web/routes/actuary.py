# ruff: noqa: BLE001 -- Webbgränsen sanerar oväntade fel utan databasdetaljer.
"""Aktuariens teamyta (A3). Data och handlingar går bara genom befintliga adaptrar/tjänster."""

from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from services import OperationContext, ServiceError
from web.actuary_presenters import assumption_groups
from web.handler import read, render, service
from web.operator_auth import current_session, operator_action
from web.operator_forms import HEADERS
from web.presenters import describe_error
from web.routes.auth import auth_form

router = APIRouter()
ROOT = "/team/aktuarie"
BASES = ROOT + "/antaganden"


def page(request, template, context, *, status_code=200):
    response = render(request, template, {"operator_page": True, "actuary_page": True, **context}, status_code=status_code)
    response.headers.update(HEADERS)
    return response


def token(request, purpose):
    session = current_session(request)
    return request.app.state.actuary_submissions.issue(session.csrf_token + purpose) if session and session.operator_id else ""


def consume(request, form, purpose):
    request.app.state.actuary_submissions.take(form.get("request_token", ""), form["csrf_token"] + purpose)


@router.get(ROOT)
def overview(request: Request):
    context = {"basis_list": None, "valuations": None, "errors": []}
    try:
        context["valuations"] = read(request, "list_valuation_runs", {}).runs
    except Exception:
        context["errors"].append("Värderingskörningarna kunde inte läsas.")
    try:
        context["basis_list"] = read(request, "list_valuation_bases", {})
    except Exception:
        context["errors"].append("Antagandebiblioteket kunde inte läsas.")
    return page(request, "actuary_overview.html", context)


@router.get(BASES)
def basis_list(request: Request):
    try:
        data = read(request, "list_valuation_bases", {})
    except Exception:
        raise HTTPException(503, "Antagandebiblioteket kunde inte läsas.") from None
    return page(request, "actuary_bases.html", {"basis_list": data})


def basis_detail_page(request, code, *, error=None, status_code=200):
    try:
        basis = read(request, "get_valuation_basis", {"code": code})
    except ServiceError as exc:
        view = describe_error(exc, service(request).rules)
        raise HTTPException(view.status_code, view.message) from None
    except Exception:
        raise HTTPException(503, "Grunden kunde inte läsas.") from None
    return page(request, "actuary_basis.html", {"basis": basis, "error": error,
        "groups": assumption_groups(basis.assumptions),
        "request_token": token(request, f"basis:{code}:{basis.checksum}")}, status_code=status_code)


@router.get(BASES + "/{code}")
def basis_detail(request: Request, code: str):
    return basis_detail_page(request, code)


@router.post(BASES + "/{code}/{action}")
async def basis_action(request: Request, code: str, action: str):
    form = await auth_form(request, {"csrf_token", "request_token", "checksum", "valid_from", "decision_ref", "note"})
    actor = operator_action(request, form)
    if action not in {"anta", "avsla"}:
        raise HTTPException(404, "Åtgärden finns inte.")
    checksum = form.get("checksum", "")
    consume(request, form, f"basis:{code}:{checksum}")
    try:
        basis = await run_in_threadpool(read, request, "get_valuation_basis", {"code": code})
        if basis.checksum != checksum or basis.status != "proposed":
            raise HTTPException(409, "Förslaget har ändrats eller avgjorts. Läs grunden igen.")
        if action == "anta":
            data = {"code": code, "valid_from": date.fromisoformat(form.get("valid_from", "")),
                    "decision_ref": form.get("decision_ref", "").strip()}
            operation = "adopt_valuation_basis"
            reason = f"Antagande av {code}: {data['decision_ref']}"
        else:
            data = {"code": code, "note": form.get("note", "").strip()}
            operation, reason = "reject_valuation_basis", data["note"]
        await run_in_threadpool(service(request).execute, operation, OperationContext(actor=actor, reason=reason), data)
    except HTTPException:
        raise
    except ServiceError as exc:
        view = describe_error(exc, service(request).rules, write=True)
        return await run_in_threadpool(basis_detail_page, request, code, error=view.message, status_code=view.status_code)
    except ValueError:
        return await run_in_threadpool(basis_detail_page, request, code, error="Ange giltighetsdag och beslutsreferens.", status_code=422)
    except Exception:
        raise HTTPException(503, "Beslutets utfall behöver kontrolleras. Läs grunden innan du försöker igen.") from None
    return RedirectResponse(f"{BASES}/{code}", status_code=303, headers=HEADERS)
