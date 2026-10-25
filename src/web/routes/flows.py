"""Flöden: från regeländring till produktparameter (Fas 3c 3c-3, B-035, flaggskeppsflöde.md §6–7).

- `/floden` – listan och *Starta flöde* med källhandtag.
- `/floden/{id}` – stegen med status, resultat och kostnad, och åtgärden flödet väntar på.
- *Kör nästa steg* (`/kor`) tar flödets nästa agent- eller systemsteg synkront (val F), eller
  prövar om aktiveringsförslaget är avgjort i `/godkannanden`.
- *Godkänn* och *Avslå* (`/grind`) med anteckning. Formuläret bär hashen av underlaget som
  visades (`seen_hash`) och flödets version; har något ändrats sedan dess stoppas beslutet.
- *Markera klart* (`/klart`) med commit-referens för regeltexten.
- Avstämning (`/avstam`) av ett steg som avbröts och avbrott av flödet (`/avbryt`).
- Utkasten och körjournalen för ett agentsteg visas här; förslaget länkar till kön.

Allt går genom adaptern `agents.flows.console.FlowConsole` – webben rör varken modeller,
sessioner eller operationsmoduler. Aktören är handläggaren.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from agents import HarnessError
from agents.flows import FlowConflictError
from agents.flows.console import FlowBusyError
from services import ServiceError
from web.handler import check_csrf, handler_ctx, read, render, render_error, service
from web.presenters import ErrorView, clean_text, describe_error
from web.routes.insured import redirect

router = APIRouter()

STEP_KINDS = {"agent": "Agent", "gate": "Grind", "manual": "Manuellt", "system": "System"}
FLOW_STATUS = {
    "running": "Pågår", "waiting_gate": "Väntar på grindbeslut", "waiting_manual": "Väntar på manuellt steg",
    "waiting_approval": "Väntar på godkännande", "completed": "Klart", "rejected": "Avslaget",
    "cancelled": "Avbrutet", "failed": "Misslyckat", "reconciliation_required": "Kräver avstämning",
}
STEP_STATUS = {
    "pending": "Väntar", "running": "Körs", "completed": "Klart", "waiting": "Väntar på kön",
    "rejected": "Avslaget", "failed": "Misslyckat", "skipped": "Hoppades över",
    "reconciliation_required": "Kräver avstämning",
}


def console(request: Request):
    return getattr(request.app.state, "flow_console", None)


def actor(request: Request):
    return handler_ctx(request).actor


def _not_configured() -> ErrorView:
    return ErrorView(
        "blocked", "Flödena finns inte i den här miljön",
        "Flödesmotorns tabeller är inte införda i Lakebase (migrate_flows.py är inte körd), och riktiga "
        "modellanrop hör till 3c-V. Flödena körs i demo- och testdatabasen.", 409, nothing_changed=True,
    )


def _error(request: Request, exc: Exception) -> ErrorView:
    if isinstance(exc, ServiceError):
        return describe_error(exc, service(request).rules, write=True)
    if isinstance(exc, FlowBusyError):
        return ErrorView("conflict", "Ett steg körs redan", str(exc), 409, nothing_changed=True)
    if isinstance(exc, FlowConflictError):
        return ErrorView("conflict", "Flödet har ändrats", f"{exc}. Sidan visar nu flödets aktuella läge.", 409,
                         nothing_changed=True)
    return ErrorView("blocked", "Stoppat", str(exc), 422, nothing_changed=True)


def _int(raw) -> int:
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return 0  # ingen version stämmer – motorn svarar med en konflikt


# --- lista och start ---------------------------------------------------------------------------------


@router.get("/floden")
def flow_list(request: Request):
    return _list_page(request)


@router.post("/floden")
async def flow_start(request: Request):
    form = await request.form()
    check_csrf(request, form)
    flows = console(request)
    if flows is None:
        return await run_in_threadpool(_list_page, request, error=_not_configured())
    source = clean_text(form.get("source_handle")) or ""
    try:
        flow = await run_in_threadpool(flows.start, source, actor(request))
    except (HarnessError, ServiceError) as exc:
        return await run_in_threadpool(_list_page, request, error=_error(request, exc))
    return await run_in_threadpool(_flow_page, request, flow.flow_id, message=f"Flödet {flow.flow_id} är startat.")


def _list_page(request: Request, *, error: ErrorView | None = None):
    flows = console(request)
    items, sources = [], []
    if flows is None:
        error = error or _not_configured()
    else:
        try:
            items, sources = flows.list(), flows.sources()
        except Exception as exc:  # noqa: BLE001 – t.ex. databasen svarar inte; visas som fel
            error = error or ErrorView("error", "Flödena kunde inte läsas", f"{type(exc).__name__}: {exc}", 500,
                                       nothing_changed=False)
    return render(request, "flows.html", {
        "flows": items, "sources": sources, "console": flows, "error": error, "flow_status": FLOW_STATUS,
    }, status_code=error.status_code if error else 200, push_url="/floden" if request.method == "POST" else None)


# --- flödet ---------------------------------------------------------------------------------------------


@router.get("/floden/{flow_id}")
def flow_detail(request: Request, flow_id: str):
    return _flow_page(request, flow_id)


@router.post("/floden/{flow_id}/kor")
async def flow_run_next(request: Request, flow_id: str):
    form = await request.form()
    check_csrf(request, form)
    return await _act(request, flow_id, "run_next", _int(form.get("version")), message="Steget är kört.")


@router.post("/floden/{flow_id}/grind")
async def flow_gate(request: Request, flow_id: str):
    form = await request.form()
    check_csrf(request, form)
    decision = "approved" if form.get("decision") == "approved" else "rejected"
    details = None
    if decision == "approved" and form.get("has_details"):
        details = {"rule_version": clean_text(form.get("rule_version")), "valid_from": clean_text(form.get("valid_from")),
                   "decision_number": clean_text(form.get("decision_number"))}
    message = "Grinden är godkänd." if decision == "approved" else "Grinden är avslagen – flödet är stoppat."
    return await _act(request, flow_id, "decide", _int(form.get("version")), message=message, decision=decision,
                      seen_hash=str(form.get("seen_hash") or ""), note=clean_text(form.get("note")), details=details)


@router.post("/floden/{flow_id}/klart")
async def flow_manual_done(request: Request, flow_id: str):
    form = await request.form()
    check_csrf(request, form)
    data = {"commit": clean_text(form.get("commit")) or "", "note": clean_text(form.get("note"))}
    return await _act(request, flow_id, "complete_manual", _int(form.get("version")), data,
                      message="Steget är markerat klart.")


@router.post("/floden/{flow_id}/avstam")
async def flow_reconcile(request: Request, flow_id: str):
    form = await request.form()
    check_csrf(request, form)
    retry = form.get("retry") == "1"
    message = "Steget körs om vid nästa klick." if retry else "Flödet är avslutat som misslyckat."
    return await _act(request, flow_id, "reconcile", _int(form.get("version")), message=message, retry=retry,
                      note=clean_text(form.get("note")) or "")


@router.post("/floden/{flow_id}/avbryt")
async def flow_cancel(request: Request, flow_id: str):
    form = await request.form()
    check_csrf(request, form)
    return await _act(request, flow_id, "cancel", _int(form.get("version")), clean_text(form.get("note")) or "",
                      message="Flödet är avbrutet.")


async def _act(request: Request, flow_id: str, action: str, version: int, *args, message: str, **kwargs):
    flows = console(request)
    if flows is None:
        return await run_in_threadpool(_flow_page, request, flow_id, error=_not_configured())
    try:
        await run_in_threadpool(getattr(flows, action), flow_id, version, actor(request), *args, **kwargs)
    except (HarnessError, ServiceError) as exc:
        return await run_in_threadpool(_flow_page, request, flow_id, error=_error(request, exc))
    return await run_in_threadpool(_flow_page, request, flow_id, message=message)


def _flow_page(request: Request, flow_id: str, *, error: ErrorView | None = None, message: str | None = None):
    flows = console(request)
    if flows is None:
        return _list_page(request)
    try:
        flow = flows.get(flow_id)
    except HarnessError as exc:
        return render(request, "error.html", {"error": ErrorView("not_found", "Hittades inte", str(exc), 404,
                                                                  nothing_changed=False)}, status_code=404)
    approval = None
    step = next((s for s in flow.steps if s.approval_id), None)
    if step is not None:
        try:
            found = read(request, "list_approval_requests", {"status": None, "approval_id": step.approval_id})
        except ServiceError as exc:
            return render_error(request, exc)
        approval = found.requests[0] if found.requests else None
    return render(request, "flow.html", {
        "flow": flow, "console": flows, "error": error, "message": message, "approval": approval,
        "current": flow.step(flow.current_step) if flow.current_step else None,
        "flow_status": FLOW_STATUS, "step_status": STEP_STATUS, "step_kinds": STEP_KINDS,
    }, status_code=error.status_code if error else 200, push_url=f"/floden/{flow_id}")


# --- utkast och körjournal --------------------------------------------------------------------------------


@router.get("/floden/{flow_id}/steg/{step_key}/utkast/{name}")
def flow_draft(request: Request, flow_id: str, step_key: str, name: str):
    flows = console(request)
    try:
        if flows is None:
            raise HarnessError("Flödena finns inte i den här miljön")
        text = flows.draft(flow_id, step_key, name)
    except (HarnessError, OSError) as exc:
        error = ErrorView("not_found", "Utkastet kunde inte visas", str(exc), 404, nothing_changed=False)
        return render(request, "error.html", {"error": error}, status_code=404)
    return render(request, "flow_text.html", {"flow_id": flow_id, "step_key": step_key, "title": name, "text": text,
                                              "kind": "utkast"})


@router.get("/floden/{flow_id}/steg/{step_key}/journal")
def flow_journal(request: Request, flow_id: str, step_key: str):
    flows = console(request)
    try:
        if flows is None:
            raise HarnessError("Flödena finns inte i den här miljön")
        events = flows.journal(flow_id, step_key)
    except (HarnessError, OSError, ValueError) as exc:
        error = ErrorView("not_found", "Körjournalen kunde inte visas", str(exc), 404, nothing_changed=False)
        return render(request, "error.html", {"error": error}, status_code=404)
    return render(request, "flow_journal.html", {"flow_id": flow_id, "step_key": step_key, "events": events})


@router.get("/floden/{flow_id}/{action}")
def flow_action_page(request: Request, flow_id: str, action: str):
    """Omladdning efter en POST utan HTMX – tillbaka till flödet."""
    return redirect(request, f"/floden/{flow_id}")
