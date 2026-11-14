"""Autentiserad pilot för fria bolagsuppdrag i demo."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from agents.company_missions import ACTIONS
from agents.gateways import GatewayError
from services.errors import (
    AccessDeniedError,
    ConflictError,
    NotFoundError,
    ServiceError,
)
from web.handler import render
from web.operator_auth import current_session, operator_action, operator_actor
from web.operator_forms import HEADERS
from web.routes.auth import auth_form

BASE = "/central/fragor"
OLD_BASE = "/central/bolagsuppdrag"
router = APIRouter()
STATUSES = {
    "queued": "Köat", "running": "Arbete pågår", "waiting_review": "Väntar på ditt beslut",
    "waiting_external": "Väntar på domänbeslut eller verifiering", "needs_information": "Behöver förtydligas",
    "needs_human": "Behöver mänsklig bedömning", "answered": "Besvarat", "budget_stopped": "Budgetstopp",
    "rejected": "Avslaget", "taken_over": "Övertaget", "reconciliation_required": "Behöver avstämning",
    "completed": "Klart", "interrupted": "Avbrutet", "cancelled": "Avbeställt", "superseded": "Ersatt",
    "failed": "Körning misslyckades", "limit_reached": "Körgräns nådd", "blocked": "Blockerat",
}
REVIEW_LABELS = {
    "approve_interpretation": "Godkänn tolkning för analysmandat",
    "prepare_parameter_activation": "Anta parameterändringen",
    "prepare_development": "Anta regeln för Utveckling",
}
TEAM_LABELS = {"compliance": "Compliance", "aktuarie": "Aktuarie", "utveckling": "Utveckling"}


def workspace(request):
    value = request.app.state.company_missions
    if value is None:
        raise HTTPException(404, "Bolagspiloten är inte tillgänglig i denna miljö")
    return value


def page(request, template, **data):
    response = render(request, template, {"operator_page": True, "base": BASE, "statuses": STATUSES,
                      "review_labels": REVIEW_LABELS, "teams": TEAM_LABELS, **data})
    response.headers.update(HEADERS)
    return response


def _error(exc):
    status = 404 if isinstance(exc, (NotFoundError, AccessDeniedError)) else (
        409 if isinstance(exc, (ConflictError, GatewayError)) else 422)
    return HTTPException(status, str(exc))


@router.get(BASE)
@router.get(OLD_BASE, include_in_schema=False)
def listing(request: Request):
    pilot = request.app.state.company_missions
    session = current_session(request)
    actor = operator_actor(request) if session and session.operator_id else None
    return page(request, "company_missions.html", items=pilot.store.list(actor) if actor and pilot else [],
                new_key=uuid4().hex, enabled=pilot is not None and pilot.ai is not None)


@router.post(BASE)
@router.post(OLD_BASE, include_in_schema=False)
async def start(request: Request):
    form = await auth_form(request, {"csrf_token", "key", "goal"})
    actor = operator_action(request, form)
    try:
        row = await run_in_threadpool(workspace(request).start, form.get("key", ""), actor, form.get("goal", ""))
    except (ServiceError, GatewayError) as exc:
        raise _error(exc) from None
    return RedirectResponse(f"{BASE}/{row['id']}", status_code=303, headers=HEADERS)


@router.get(BASE + "/{ident}")
@router.get(OLD_BASE + "/{ident}", include_in_schema=False)
def detail(request: Request, ident: str):
    actor = operator_actor(request)
    pilot = workspace(request)
    try:
        row = pilot.store.get(ident, actor)
    except NotFoundError as exc:
        raise _error(exc) from None
    state = row["state"]
    review = next(iter(state["reviews"]), None) if state["status"] == "waiting_review" else None
    basis = next((i for i in state["assignments"].values() if i["id"] == review["basis"]), None) if review else None
    domain_action = state["external"]
    return page(request, "company_mission.html", mission=row, state=state, follow_key=uuid4().hex,
                review=review, basis=basis, enabled=pilot.ai is not None, can_process=state["status"] in ACTIONS,
                development_wait=domain_action and domain_action["kind"] == "prepare_development",
                known_cost=sum((run["usage"] or {}).get("cost_usd", 0) for run in state["runs"]
                               if run["status"] != "interrupted"),
                unresolved_cost=any(run["status"] in {"interrupted", "running"} for run in state["runs"]))


@router.post(BASE + "/{ident}/{action}")
@router.post(OLD_BASE + "/{ident}/{action}", include_in_schema=False)
async def act(request: Request, ident: str, action: str):
    forms = {
        "kor": set(), "avbrott": set(), "ta-over": {"note"}, "precisera": {"key", "goal"},
        "granska": {"seen", "verdict", "note", "rule_version", "valid_from", "decision_number",
                    "commit", "rule_id", "code_reason", "affected_system", "expected_effect"},
    }
    if action not in forms:
        raise HTTPException(404, "Åtgärden finns inte")
    form = await auth_form(request, {"csrf_token", "revision", *forms[action]})
    actor = operator_action(request, form)
    pilot = workspace(request)
    try:
        revision = int(form.get("revision", ""))
    except ValueError:
        raise HTTPException(422, "Uppdragets version saknas") from None
    handlers = {
        "kor": (pilot.process, ()),
        "avbrott": (pilot.interrupted, ()),
        "ta-over": (pilot.take_over, (form.get("note", ""),)),
        "precisera": (pilot.follow_up, (form.get("key", ""), form.get("goal", ""))),
        "granska": (pilot.review, (form.get("seen", ""), form.get("verdict", ""), form)),
    }
    handler, args = handlers[action]
    try:
        await run_in_threadpool(handler, ident, actor, revision, *args)
    except (ServiceError, GatewayError) as exc:
        raise _error(exc) from None
    return RedirectResponse(f"{BASE}/{ident}", status_code=303, headers=HEADERS)


@router.get(BASE + "/{ident}/utkast/{assignment}/{name}")
@router.get(OLD_BASE + "/{ident}/utkast/{assignment}/{name}", include_in_schema=False)
def artifact(request: Request, ident: str, assignment: str, name: str):
    actor = operator_actor(request)
    try:
        value = workspace(request).artifact(ident, actor, assignment, name)
    except (ServiceError, GatewayError) as exc:
        raise _error(exc) from None
    return Response(value, media_type="text/markdown",
                    headers={**HEADERS, "Content-Disposition": f'attachment; filename="{name}"'})


@router.get(BASE + "/{ident}/spar/{run}")
@router.get(OLD_BASE + "/{ident}/spar/{run}", include_in_schema=False)
def trace(request: Request, ident: str, run: str):
    actor = operator_actor(request)
    try:
        value = workspace(request).trace(ident, actor, run)
    except NotFoundError as exc:
        raise _error(exc) from None
    return page(request, "company_trace.html", trace=value, ident=ident)
