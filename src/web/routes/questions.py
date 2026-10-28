"""OC-3a: shared assignment pages; all work and delivery reads use QuestionConsole."""

from __future__ import annotations

import re
import secrets
import threading
import time
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from agents import HarnessError
from agents.flows.console import FlowBusyError
from agents.flows.questions import QuestionConsole, assignment_view
from agents.flows.store import FlowConflictError, FlowError
from services import ServiceError
from web.handler import render
from web.operator_auth import operator_action
from web.routes.auth import auth_form

router = APIRouter()
HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
           "Content-Security-Policy": "frame-ancestors 'none'; form-action 'self'; base-uri 'none'"}
CENTRAL = "/central/fragor"
TEAM = "/team/aktuarie"
STEP_STATUS = {"pending": "Väntar", "running": "Körs", "completed": "Klart", "failed": "Misslyckades",
               "rejected": "Avslaget", "skipped": "Hoppades över", "reconciliation_required": "Behöver avstämning"}
ANSWER_STATUS = {"answered": "Besvarad", "partial": "Delvis besvarad", "unavailable": "Underlag saknas",
                 "needs_clarification": "Behöver förtydligas"}


class Submissions:
    """Session-bound, single-use start forms. Repeated POSTs resolve to the same assignment.

    Only HTTP replay protection lives here; durable lifecycle and concurrency stay in harness.
    A lost response never silently runs the same form again.
    """
    def __init__(self):
        self._items = {}
        self._lock = threading.Lock()

    def issue(self, session_key):
        with self._lock:
            now = time.monotonic()
            self._items = {k: v for k, v in self._items.items() if now - v[0] < 8 * 3600}
            if len(self._items) >= 4096:
                raise HTTPException(503, "För många öppna formulär")
            token = secrets.token_urlsafe(32)
            self._items[token] = (now, session_key, False, None)
            return token

    def take(self, token, session_key):
        with self._lock:
            item = self._items.get(token)
            if item is None or item[1] != session_key or time.monotonic() - item[0] >= 8 * 3600:
                raise HTTPException(409, "Formuläret har gått ut. Ladda om sidan.")
            if item[2] and item[3] is None:
                raise HTTPException(409, "Beställningen har redan skickats. Kontrollera uppdragslistan.")
            self._items[token] = (*item[:2], True, item[3])
            return item[3]

    def finish(self, token, flow_id):
        with self._lock:
            item = self._items[token]
            self._items[token] = (*item[:2], True, flow_id)


def console(request: Request) -> QuestionConsole:
    value = request.app.state.question_console
    if value is None:
        raise HTTPException(503, "Bolagsfrågorna är inte anslutna i denna miljö. Modell, teamroll och rapporttypsnitt behöver anslutas.")
    config = request.app.state.settings
    if (value.environment_id, value.dataset_ref) != (config.database, config.dataset_ref):
        raise HTTPException(503, "Uppdragsadaptern stämmer inte med vald miljö och dataset")
    return value


def base(request):
    return TEAM if request.url.path.startswith(TEAM) else CENTRAL


def respond(request, template, context, *, status_code=200):
    response = render(request, template, {"operator_page": True, "base": base(request),
                      "step_status": STEP_STATUS, "answer_status": ANSWER_STATUS, **context}, status_code=status_code)
    response.headers.update(HEADERS)
    return response


def known_error(exc):
    if isinstance(exc, (FlowBusyError, FlowConflictError)):
        return 409, "Uppdraget körs redan eller har ändrats. Ladda om sidan före nästa åtgärd."
    if isinstance(exc, (FlowError, ValidationError, ValueError)):
        return 422, "Åtgärden kunde inte utföras. Kontrollera månad, skäl, version och granskningsunderlag."
    return 503, "Uppdragsunderlaget kunde inte läsas. Ingen annan datakälla används."


@router.get(CENTRAL)
@router.get(TEAM)
def assignment_list(request: Request, supersedes: str = ""):
    try:
        c = console(request)
        items, teams, months = c.list(team="aktuarie" if base(request) == TEAM else None), c.teams(), c.months()
    except HTTPException as exc:
        return respond(request, "questions.html", {"items": [], "teams": [], "months": [], "error": exc.detail}, status_code=exc.status_code)
    except Exception as exc:  # no DB strings, credentials or raw conversations in responses
        status, error = known_error(exc)
        return respond(request, "questions.html", {"items": [], "teams": [], "months": [], "error": error}, status_code=status)
    if supersedes and (not re.fullmatch(r"FLOW-\d{6}", supersedes) or not any(
        item.flow_id == supersedes and item.status == "rejected" for item in items
    )):
        raise HTTPException(422, "Välj ett avslaget uppdrag att ersätta")
    # No actor is created for reads. The form uses the session token already resolved by render().
    from web.operator_auth import current_session
    session = current_session(request)
    token = request.app.state.question_submissions.issue(session.csrf_token) if session and session.operator_id else ""
    return respond(request, "questions.html", {"items": items, "teams": teams, "months": months,
                   "request_token": token, "supersedes": supersedes, "busy": c.busy})


@router.post(CENTRAL)
@router.post(TEAM)
async def start_assignment(request: Request):
    form = await auth_form(request, {"csrf_token", "request_token", "month", "team", "question_type", "note", "supersedes"})
    actor = operator_action(request, form)
    c = console(request)
    if form.get("team") != "aktuarie" or form.get("question_type") != "portfolio_overview":
        raise HTTPException(422, "Bara beståndsöversikt till aktuarieteamet är tillgänglig")
    try:
        month = date.fromisoformat(form.get("month", "") + "-01")
        if month not in c.months() or len(form.get("note", "")) > 500:
            raise ValueError
    except ValueError:
        raise HTTPException(422, "Välj en av de elva avslutade månaderna och högst 500 tecken precisering") from None
    tickets = request.app.state.question_submissions
    token = form.get("request_token", "")
    existing = tickets.take(token, form["csrf_token"])
    if existing:
        return RedirectResponse(f"{base(request)}/{existing}", status_code=303, headers=HEADERS)
    try:
        view = await run_in_threadpool(c.start, month, form.get("note", ""), actor,
                                       supersedes=form.get("supersedes") or None)
    except Exception as exc:
        status, detail = known_error(exc)
        raise HTTPException(status, detail) from None
    tickets.finish(token, view.flow_id)
    return RedirectResponse(f"{base(request)}/{view.flow_id}", status_code=303, headers=HEADERS)


def detail_page(request, flow_id, *, error=None, status_code=200):
    c = console(request)
    try:
        flow = c.flow(flow_id)
        view = assignment_view(flow)
        output = (flow.step("answer").result or {}).get("output") or {}
        answer = output.get("result")
        observations = (flow.step("render").result or {}).get("observations") or []
        # Verify the very files displayed for review. A modified file disables all review controls.
        integrity_error = False
        if view.delivery_version is not None:
            try:
                c.delivery(flow_id, "rapport.pdf")
                c.delivery(flow_id, "rapport.md")
            except HarnessError:
                integrity_error = True
        return respond(request, "question.html", {"assignment": view, "flow": flow, "answer": answer,
                       "observations": observations, "integrity_error": integrity_error,
                       "error": error, "busy": c.busy}, status_code=409 if integrity_error else status_code)
    except FlowError:
        raise HTTPException(404, "Uppdraget finns inte i denna miljö") from None
    except Exception:
        raise HTTPException(503, "Uppdragsunderlaget kunde inte läsas. Ingen annan datakälla används.") from None


@router.get(CENTRAL + "/{flow_id}")
@router.get(TEAM + "/{flow_id}")
def assignment_detail(request: Request, flow_id: str):
    return detail_page(request, flow_id)


@router.post(CENTRAL + "/{flow_id}/{action}")
@router.post(TEAM + "/{flow_id}/{action}")
async def assignment_action(request: Request, flow_id: str, action: str):
    form = await auth_form(request, {"csrf_token", "version", "decision", "seen_hash", "note", "retry"})
    actor = operator_action(request, form)
    c = console(request)
    try:
        version = int(form.get("version", ""))
        if action == "granska":
            view = await run_in_threadpool(c.decide, flow_id, version, actor, decision=form.get("decision", ""),
                                           seen_hash=form.get("seen_hash", ""), note=form.get("note") or None)
        elif action == "avbryt":
            view = await run_in_threadpool(c.cancel, flow_id, version, actor, form.get("note", ""))
        elif action == "avstam" and form.get("retry") in {"yes", "no"}:
            view = await run_in_threadpool(c.reconcile, flow_id, version, actor, retry=form["retry"] == "yes", note=form.get("note", ""))
        else:
            raise HTTPException(404, "Åtgärden finns inte")
    except (HarnessError, ServiceError, ValidationError, ValueError) as exc:
        status, error = known_error(exc)
        return await run_in_threadpool(detail_page, request, flow_id, error=error, status_code=status)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Åtgärdens utfall behöver kontrolleras i uppdragslistan. Kör inte om beställningen.") from None
    return RedirectResponse(f"{base(request)}/{view.flow_id}", status_code=303, headers=HEADERS)


@router.get(CENTRAL + "/{flow_id}/leverans/{version}/{name}")
@router.get(TEAM + "/{flow_id}/leverans/{version}/{name}")
def delivery(request: Request, flow_id: str, version: int, name: str):
    if name not in {"rapport.pdf", "rapport.md"}:
        raise HTTPException(404, "Leveransfilen finns inte")
    c = console(request)
    try:
        if c.get(flow_id).delivery_version != version:
            raise FlowError("Okänd leveransversion")
        data = c.delivery(flow_id, name)
    except HarnessError:
        raise HTTPException(409, "Leveransfilen saknas eller stämmer inte med uppdragets kontrollsumma") from None
    except Exception:
        raise HTTPException(503, "Leveransen kunde inte läsas") from None
    return Response(data, media_type="application/pdf" if name.endswith("pdf") else "text/markdown; charset=utf-8",
                    headers={**HEADERS, "Content-Disposition": f'{"inline" if name.endswith("pdf") else "attachment"}; filename="{name}"',
                             "X-Frame-Options": "SAMEORIGIN", "Content-Security-Policy": "frame-ancestors 'self'"})
