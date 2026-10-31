"""Godkännandekön och händelseloggen (S3).

Kön och loggen läses med tjänstelagrets läsoperationer (`list_approval_requests`,
`count_approval_requests`, `get_operation_events`). Godkännande och avslag går
genom `ServiceLayer.approve/reject` – bara en människa kan avgöra ett
agentförslag, och vid godkännande körs operationen på nytt mot aktuellt läge.
Fallerar den rullas allt tillbaka och ärendet är kvar som väntande.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from services import ServiceError
from web.handler import (
    check_csrf,
    handler_ctx,
    read,
    read_async,
    render,
    render_error,
    service,
)
from web.operator_auth import current_session, operator_action
from web.presenters import ErrorView, clean_text, describe_error

router = APIRouter()

#: Filtren i kön: adressens värde → status i tjänstelagret
QUEUE_FILTERS = {"vantar": "pending", "godkanda": "approved", "avslagna": "rejected", "alla": None}


def decision_context(request, form, approval_id):
    console = getattr(request.app.state, "case_workspace", None)
    work_id = console.work_for_approval(approval_id) if console else None
    session = current_session(request)
    if work_id or (session and form.get("csrf_token") == session.csrf_token):
        actor = operator_action(request, dict(form))
        return replace(handler_ctx(request), actor=actor), work_id
    check_csrf(request, form)
    return handler_ctx(request), None


# --- godkännandekön -------------------------------------------------------------------------------


@router.get("/godkannanden")
def approvals(request: Request, status: str = "vantar"):
    return _queue_page(request, status)


@router.post("/godkannanden/{approval_id}/godkann")
async def approve(request: Request, approval_id: str):
    form = await request.form()
    ctx, work_id = await run_in_threadpool(decision_context, request, form, approval_id)
    note = clean_text(form.get("note"))
    try:
        proposal = (await read_async(
            request, "list_approval_requests", {"status": None, "approval_id": approval_id}
        )).requests[0]
        result = await run_in_threadpool(service(request).approve, approval_id, ctx, note)
        if work_id:
            await run_in_threadpool(request.app.state.case_workspace.settle, work_id)
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        return await run_in_threadpool(_queue_page, request, "vantar", error=error, focus=approval_id)

    lookup = _subject(proposal.input, result.output)
    overview = None
    if lookup:
        try:
            overview = await read_async(request, "get_insured_overview", lookup)
        except ServiceError:
            overview = None
    if overview is None:
        message = f"Förslaget {approval_id} är godkänt och utfört ({proposal.operation})."
        return await run_in_threadpool(_queue_page, request, "vantar", message=message)
    return render(request, "write_result.html", {
        "o": overview, "tab": "overview", "operation": proposal.operation, "result": result.output,
        "reason": proposal.reason, "approval": proposal,
    }, push_url=f"/forsakrade/{overview.personal_id_number}")


@router.get("/godkannanden/{approval_id}/{decision}")
def decision_page(approval_id: str, decision: str):
    """Omladdning efter ett beslut utan HTMX – tillbaka till kön."""
    return RedirectResponse("/godkannanden", status_code=303)


@router.post("/godkannanden/{approval_id}/avsla")
async def reject(request: Request, approval_id: str):
    form = await request.form()
    ctx, work_id = await run_in_threadpool(decision_context, request, form, approval_id)
    note = clean_text(form.get("note"))
    if not note:
        error = ErrorView("invalid", "Skäl saknas", "Ange varför förslaget avslås – skälet sparas i händelseloggen.",
                          422, field_errors={"note": "Obligatoriskt vid avslag"}, nothing_changed=True)
        return await run_in_threadpool(_queue_page, request, "vantar", error=error, focus=approval_id)
    try:
        await run_in_threadpool(service(request).reject, approval_id, ctx, note)
        if work_id:
            await run_in_threadpool(request.app.state.case_workspace.settle, work_id)
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        return await run_in_threadpool(_queue_page, request, "vantar", error=error, focus=approval_id)
    return await run_in_threadpool(
        _queue_page, request, "vantar", message=f"Förslaget {approval_id} är avslaget. Ingen ändring gjordes."
    )


def _queue_page(request: Request, status: str, *, error: ErrorView | None = None, message: str | None = None,
                focus: str | None = None):
    key = status if status in QUEUE_FILTERS else "vantar"
    try:
        queue = read(request, "list_approval_requests", {"status": QUEUE_FILTERS[key]})
        counts = read(request, "count_approval_requests", {})
    except ServiceError as exc:
        return render_error(request, exc)
    registry = service(request).registry
    descriptions = {r.operation: registry.get(r.operation).description
                    for r in queue.requests if r.operation in registry}
    return render(request, "approvals.html", {
        "queue": queue, "counts": counts, "filter": key, "descriptions": descriptions,
        "error": error, "message": message, "focus": focus,
    }, status_code=error.status_code if error else 200, push_url=f"/godkannanden?status={key}")


def _subject(data: dict[str, Any], output: Any) -> dict[str, str] | None:
    """Vilken försäkrad ett förslag gäller – för att visa resultatet på personens sida."""
    if data.get("personal_id_number"):
        return {"personal_id_number": data["personal_id_number"]}
    policy_number = data.get("policy_number") or getattr(output, "policy_number", None)
    return {"policy_number": policy_number} if policy_number else None


# --- händelseloggen -------------------------------------------------------------------------------


@router.get("/handelselogg")
def event_log(request: Request, operation: str = "", utfall: str = "", lasningar: str = ""):
    query = {"operation": operation or None, "outcome": utfall or None, "include_reads": bool(lasningar)}
    try:
        log = read(request, "get_operation_events", query)
    except ServiceError as exc:
        return render_error(request, exc)
    return render(request, "events.html", {
        "log": log, "operations": service(request).registry.names(),
        "filters": {"operation": operation, "utfall": utfall, "lasningar": bool(lasningar)},
    })


@router.get("/forsakrade/{pnr}/handelser")
def insured_events(request: Request, pnr: str, lasningar: str = ""):
    try:
        overview = read(request, "get_insured_overview", {"personal_id_number": pnr})
        log = read(request, "get_operation_events", {"personal_id_number": pnr, "include_reads": bool(lasningar)})
    except ServiceError as exc:
        return render_error(request, exc, "search.html", {"query": pnr})
    return render(request, "insured_events.html", {
        "o": overview, "tab": "events", "log": log, "filters": {"lasningar": bool(lasningar)},
    })
