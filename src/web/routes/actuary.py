# ruff: noqa: BLE001 -- Webbgränsen sanerar oväntade fel utan databasdetaljer.
"""Aktuariens teamyta (A3). Data och handlingar går bara genom befintliga adaptrar/tjänster."""

from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from agents.flows.product_reports import report_view
from agents.flows.store import FlowError
from services import OperationContext, ServiceError
from web.actuary_presenters import assumption_groups
from web.handler import read, service
from web.operator_auth import current_session, operator_action
from web.presenters import describe_error
from web.routes.auth import auth_form
from web.routes.questions import HEADERS, known_error, respond

router = APIRouter()
ROOT = "/team/aktuarie"
REPORTS = ROOT + "/rapporter"
BASES = ROOT + "/antaganden"


def reports(request):
    console = request.app.state.product_report_console
    if console is None:
        raise HTTPException(503, "Produktrapporterna är inte anslutna i denna miljö. Starta med aktuariens arbetsyta ansluten.")
    settings = request.app.state.settings
    if (console.environment_id, console.dataset_ref) != (settings.database, settings.dataset_ref):
        raise HTTPException(503, "Rapportadaptern stämmer inte med vald miljö och dataset")
    return console


def page(request, template, context, *, status_code=200):
    return respond(request, template, {"actuary_page": True, **context}, status_code=status_code)


def token(request, purpose):
    session = current_session(request)
    return request.app.state.actuary_submissions.issue(session.csrf_token + purpose) if session and session.operator_id else ""


def consume(request, form, purpose):
    previous = request.app.state.actuary_submissions.take(form.get("request_token", ""), form["csrf_token"] + purpose)
    if previous:
        raise HTTPException(409, "Formuläret har redan använts. Ladda om sidan före nästa åtgärd.")


def finish(request, form, result):
    request.app.state.actuary_submissions.finish(form["request_token"], result)


@router.get(ROOT)
def overview(request: Request):
    context = {"basis_list": None, "reports": None, "assignments": None, "valuations": None, "errors": []}
    try:
        context["valuations"] = read(request, "list_valuation_runs", {}).runs
    except Exception:
        context["errors"].append("Värderingskörningarna kunde inte läsas.")
    try:
        context["basis_list"] = read(request, "list_valuation_bases", {})
    except Exception:
        context["errors"].append("Antagandebiblioteket kunde inte läsas.")
    try:
        context["reports"] = reports(request).list()
    except Exception:
        context["errors"].append("Produktrapporterna är inte anslutna eller kunde inte läsas.")
    try:
        from web.routes.questions import console
        context["assignments"] = console(request).list(team="aktuarie")
    except Exception:
        context["errors"].append("Agentuppdragen är inte anslutna eller kunde inte läsas.")
    return page(request, "actuary_overview.html", context)


@router.get(REPORTS)
def report_list(request: Request):
    try:
        c = reports(request)
        return page(request, "actuary_reports.html", {"items": c.list(), "years": c.years(),
                    "request_token": token(request, "report:start")})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Produktrapporterna kunde inte läsas.") from None


@router.post(REPORTS)
async def report_start(request: Request):
    form = await auth_form(request, {"csrf_token", "request_token", "year", "note"})
    actor = operator_action(request, form)
    c = reports(request)
    try:
        year = int(form.get("year", ""))
        if year not in c.years() or len(form.get("note", "")) > 500:
            raise ValueError
    except ValueError:
        raise HTTPException(422, "Välj ett tillgängligt år och högst 500 tecken precisering.") from None
    consume(request, form, "report:start")
    try:
        view = await run_in_threadpool(c.start, year, form.get("note", ""), actor)
    except Exception as exc:
        status, detail = known_error(exc)
        raise HTTPException(status, detail) from None
    finish(request, form, view.flow_id)
    return RedirectResponse(f"{REPORTS}/{view.flow_id}", status_code=303, headers=HEADERS)


def report_detail_page(request, flow_id, *, error=None, status_code=200):
    c = reports(request)
    try:
        flow = c.flow(flow_id)
        view = report_view(flow)
    except FlowError:
        raise HTTPException(404, "Produktrapporten finns inte i denna miljö.") from None
    except Exception:
        raise HTTPException(503, "Produktrapporten kunde inte läsas.") from None
    integrity = False
    if view.delivery_version:
        try:
            c.delivery(flow_id, "rapport.pdf")
            c.delivery(flow_id, "rapport.md")
        except Exception:
            integrity = True
    try:
        trace = c.trace(flow_id)
    except Exception:
        trace = None
    summary = (flow.step("summary").result or {}).get("output") or {}
    purpose = f"report:{flow_id}:{flow.version}:{flow.gate_hashes.get('review', '')}"
    return page(request, "actuary_report.html", {"assignment": view, "flow": flow,
        "answer": summary.get("result"), "trace": trace, "integrity_error": integrity,
        "request_token": token(request, purpose), "error": error}, status_code=409 if integrity else status_code)


@router.get(REPORTS + "/{flow_id}")
def report_detail(request: Request, flow_id: str):
    return report_detail_page(request, flow_id)


@router.post(REPORTS + "/{flow_id}/{action}")
async def report_action(request: Request, flow_id: str, action: str):
    form = await auth_form(request, {"csrf_token", "request_token", "version", "seen_hash", "decision", "note"})
    actor = operator_action(request, form)
    c = reports(request)
    try:
        version = int(form.get("version", ""))
    except ValueError:
        raise HTTPException(422, "Ogiltig uppdragsversion.") from None
    if action not in {"granska", "avbryt"}:
        raise HTTPException(404, "Åtgärden finns inte.")
    purpose = f"report:{flow_id}:{version}:{form.get('seen_hash', '')}"
    consume(request, form, purpose)
    try:
        if action == "granska":
            view = await run_in_threadpool(c.decide, flow_id, version, actor, decision=form.get("decision", ""),
                                          seen_hash=form.get("seen_hash", ""), note=form.get("note") or None)
        else:
            view = await run_in_threadpool(c.cancel, flow_id, version, actor, form.get("note", ""))
    except Exception as exc:
        status, error = known_error(exc)
        return await run_in_threadpool(report_detail_page, request, flow_id, error=error, status_code=status)
    finish(request, form, view.flow_id)
    return RedirectResponse(f"{REPORTS}/{flow_id}", status_code=303, headers=HEADERS)


@router.get(REPORTS + "/{flow_id}/leverans/{version}/{name}")
def report_delivery(request: Request, flow_id: str, version: int, name: str):
    # Samma integritetskontroll och begränsade filnamn som befintlig rapportyta.
    if name not in {"rapport.pdf", "rapport.md"}:
        raise HTTPException(404, "Leveransfilen finns inte.")
    c = reports(request)
    from fastapi.responses import Response
    try:
        if c.get(flow_id).delivery_version != version:
            raise ValueError
        files = {filename: c.delivery(flow_id, filename) for filename in ("rapport.pdf", "rapport.md")}
        data = files[name]
    except Exception:
        raise HTTPException(409, "Leveransfilen saknas eller stämmer inte med rapportens kontrollsumma.") from None
    return Response(data, media_type="application/pdf" if name.endswith("pdf") else "text/markdown; charset=utf-8",
        headers={**HEADERS, "Content-Disposition": f'attachment; filename="{name}"'})


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
    finish(request, form, code)
    return RedirectResponse(f"{BASES}/{code}", status_code=303, headers=HEADERS)
