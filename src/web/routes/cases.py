"""Ärenden och handläggaragenten (Fas 5 F5-4, B-033).

- `/arenden` – handläggarens lista (`list_cases`): aktiva, stängda eller alla.
- `/arenden/ny` – registrera ett ärende om inrapporterat löneunderlag (`create_case`).
- `/arenden/{nummer}` – ärendet med uppgifter, förslag i kön, historik och agentens senaste körning.
- *Starta agent* kör handläggaragenten i ärendet (`run_case`) – synkront, en körning åt gången.
  Mandatet byggs ur ärendet; harness skriver ärendets status efteråt.
- Statusbyte (`update_case_status`) och stängning (`close_case`) görs av handläggaren.

Handläggarens egen registrering av löneunderlaget görs i det vanliga formuläret, med
ärendenumret medskickat, så att den syns i ärendets historik och ärendet kan stängas som
godkänt.
"""

from __future__ import annotations

import threading
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from agents import HarnessError
from services import ServiceError
from web.handler import (
    check_csrf,
    handler_ctx,
    read,
    render,
    render_error,
    service,
    settings,
)
from web.presenters import (
    ErrorView,
    clean_decimal,
    clean_month,
    clean_text,
    describe_error,
)
from web.routes.insured import redirect

router = APIRouter()

#: Urvalen i listan: adressens värde → list_cases status
LIST_FILTERS = {"aktiva": "active", "stangda": "closed", "alla": None}
OPEN_STATUSES = ("open", "in_progress", "waiting_approval", "waiting_info")

#: En agentkörning åt gången i processen (lokalt, en handläggare – B-033 val D)
_agent_lock = threading.Lock()


def case_agent(request: Request):
    return getattr(request.app.state, "case_agent", None)


# --- lista och registrering ----------------------------------------------------------------------


@router.get("/arenden")
def case_list(request: Request, status: str = "aktiva"):
    key = status if status in LIST_FILTERS else "aktiva"
    try:
        cases = read(request, "list_cases", {"status": LIST_FILTERS[key]})
    except ServiceError as exc:
        return render_error(request, exc)
    return render(request, "cases.html", {"cases": cases, "filter": key}, push_url=f"/arenden?status={key}")


@router.get("/arenden/ny")
def case_form(request: Request, pnr: str = ""):
    values: dict[str, Any] = {"received_date": date.today().isoformat(), "source": "employer", "kind": "new"}
    overview = None
    if pnr:
        try:
            overview = read(request, "get_insured_overview", {"personal_id_number": pnr})
        except ServiceError as exc:
            return render_error(request, exc)
        values.update(personal_id_number=pnr, employer_org_number=overview.employer.org_number)
    return render(request, "form_case.html", {"values": values, "o": overview})


@router.post("/arenden")
async def case_submit(request: Request):
    form = await request.form()
    check_csrf(request, form)
    values = {key: str(value) for key, value in form.items() if key != "csrf_token"}
    kind = values.get("kind") or None
    data = {
        "case_type": "salary_report",
        "personal_id_number": clean_text((values.get("personal_id_number") or "").replace("-", "")),
        "employer_org_number": clean_text((values.get("employer_org_number") or "").replace("-", "")),
        "policy_number": clean_text(values.get("policy_number")),
        "period_month": clean_month(values.get("period_month")),
        "received_date": clean_text(values.get("received_date")),
        "source_reference": clean_text(values.get("source_reference")),
        "due_date": clean_text(values.get("due_date")),
        "assigned_to": clean_text(values.get("assigned_to")),
        "details": {
            "pensionable_salary_sek": clean_decimal(values.get("pensionable_salary_sek")),
            "kind": kind,
            "corrects_version": clean_text(values.get("corrects_version")) if kind == "correction" else None,
            "source": values.get("source") or None,
        },
    }
    ctx = handler_ctx(request, reason=clean_text(values.get("reason")))
    try:
        result = await run_in_threadpool(service(request).execute, "create_case", ctx, data)
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        return render(request, "form_case.html", {"values": values, "o": None, "error": error},
                      status_code=error.status_code)
    return await run_in_threadpool(
        _case_page, request, result.output.case_number,
        message=f"Ärendet {result.output.case_number} är registrerat.",
    )


# --- ärendet ---------------------------------------------------------------------------------------


@router.get("/arenden/{case_number}")
def case_detail(request: Request, case_number: str, lasningar: str = ""):
    return _case_page(request, case_number, include_reads=bool(lasningar))


@router.post("/arenden/{case_number}/agent")
async def case_run_agent(request: Request, case_number: str):
    form = await request.form()
    check_csrf(request, form)
    if getattr(request.app.state, "case_workspace", None) is not None:
        error = ErrorView("conflict", "Använd ärendets agentstöd",
                          "Beställ deluppdrag eller lämna över ärendet i den sparade ärendedialogen.", 409,
                          nothing_changed=True)
        return await run_in_threadpool(_case_page, request, case_number, error=error)
    agent = case_agent(request)
    if agent is None:
        error = ErrorView("error", "Agenten är inte konfigurerad",
                          "Handläggar-UI:t startades utan handläggaragent.", 409, nothing_changed=True)
        return await run_in_threadpool(_case_page, request, case_number, error=error)
    if not _agent_lock.acquire(blocking=False):
        error = ErrorView("conflict", "Agenten arbetar redan", "En körning pågår – vänta tills den är klar.", 409,
                          nothing_changed=True)
        return await run_in_threadpool(_case_page, request, case_number, error=error)
    try:
        run = await run_in_threadpool(
            agent.run, service(request), case_number, assigned_by=settings(request).handler_id
        )
    except (ServiceError, HarnessError) as exc:
        error = (describe_error(exc, service(request).rules, write=True) if isinstance(exc, ServiceError)
                 else ErrorView("blocked", "Agenten startades inte", str(exc), 422, nothing_changed=True))
        return await run_in_threadpool(_case_page, request, case_number, error=error)
    finally:
        _agent_lock.release()
    return await run_in_threadpool(_case_page, request, case_number, run=run)


@router.post("/arenden/{case_number}/status")
async def case_status(request: Request, case_number: str):
    form = await request.form()
    check_csrf(request, form)
    data = {"case_number": case_number, "status": form.get("status") or None,
            "assigned_to": clean_text(form.get("assigned_to"))}
    return await _write(request, case_number, "update_case_status", data, clean_text(form.get("reason")),
                        "Ärendets status är ändrad.")


@router.post("/arenden/{case_number}/stang")
async def case_close(request: Request, case_number: str):
    form = await request.form()
    check_csrf(request, form)
    data = {"case_number": case_number, "outcome": form.get("outcome") or None,
            "closing_note": clean_text(form.get("closing_note"))}
    return await _write(request, case_number, "close_case", data, clean_text(form.get("reason")),
                        "Ärendet är stängt.")


async def _write(request: Request, case_number: str, name: str, data: dict, reason: str | None, message: str):
    ctx = handler_ctx(request, reason=reason, case_id=case_number)
    try:
        await run_in_threadpool(service(request).execute, name, ctx, data)
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        return await run_in_threadpool(_case_page, request, case_number, error=error, form=name)
    return await run_in_threadpool(_case_page, request, case_number, message=message)


def _case_page(request: Request, case_number: str, *, error: ErrorView | None = None, message: str | None = None,
               run=None, form: str | None = None, include_reads: bool = False):
    try:
        case = read(request, "get_case", {"case_number": case_number})
        approvals = read(request, "list_approval_requests", {"status": None, "case_id": case_number})
        history = read(request, "get_operation_events", {"case_id": case_number, "include_reads": include_reads})
    except ServiceError as exc:
        return render_error(request, exc)
    overview = None
    if case.personal_id_number:
        try:
            overview = read(request, "get_insured_overview", {"personal_id_number": case.personal_id_number})
        except ServiceError:
            overview = None
    from web.operator_auth import current_session

    assistant = None
    assistant_error = None
    console = getattr(request.app.state, "case_workspace", None)
    session = current_session(request)
    if console is not None and session and session.operator_id:
        try:
            from services import Actor

            assistant = console.view(case_number, Actor.human(session.operator_id))
        except Exception:  # noqa: BLE001 – arbetsytans fel får inte exponera ärendedialog/databasuppgifter
            assistant_error = "Ärendeassistenten kan inte läsas. Kontrollera anslutning och ärendeuppdragens migration."
    response = render(request, "case.html", {
        "case": case, "o": overview, "approvals": approvals, "history": history,
        "agent": case_agent(request), "run": run, "error": error, "message": message, "form": form,
        "open_statuses": OPEN_STATUSES, "include_reads": include_reads,
        "assistant": assistant, "assistant_available": console is not None,
        "assistant_error": assistant_error, "submission_key": uuid.uuid4().hex,
    }, status_code=error.status_code if error else 200, push_url=f"/arenden/{case_number}")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/arenden/{case_number}/{action}")
def case_action_page(request: Request, case_number: str, action: str):
    """Omladdning efter en POST utan HTMX – tillbaka till ärendet."""
    return redirect(request, f"/arenden/{case_number}")
