"""Utvecklingsytan för autentiserade beställare i demo (projekt 11)."""

from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from services.change_releases import STEPS
from services.change_requests import STATUS_MOVES, ChangeRequestDraft, ChangeRequests, ReviewReferences
from services.development_demo import OutcomeUnknown
from services.errors import ConflictError
from web.handler import render
from web.operator_auth import operator_action, operator_actor
from web.routes.auth import HEADERS, auth_form

BASE = "/central/utveckling"
KINDS = {"defect": "Felanmälan", "rule_change": "Regeländring", "improvement": "Förbättring"}
STATUSES = {"new": "Nytt", "in_progress": "Pågår", "waiting_review": "Väntar på granskning",
            "merged": "Mergat", "deployed": "Infört", "verified": "Verifierat"}
router = APIRouter(prefix=BASE)


def workspace(request: Request) -> ChangeRequests:
    store = request.app.state.change_requests
    if store is None:
        raise HTTPException(404, "Utvecklingsytan finns i demomiljön.")
    return store


def respond(request: Request, template: str, context: dict, *, status_code: int = 200):
    response = render(request, template, {
        "operator_page": True, "base": BASE, "kinds": KINDS, "statuses": STATUSES, **context,
    }, status_code=status_code, check_database=False)
    response.headers.update(HEADERS)
    return response


@router.get("")
def list_requests(request: Request):
    actor = operator_actor(request)
    items = workspace(request).list(actor)
    github = request.app.state.development_github
    columns = {status: [] for status in STATUSES}
    github_statuses = {}
    for item in items:
        columns[item.status].append(item)
        if item.github_url:
            github_statuses[item.id] = github.status(item.github_url)
    return respond(request, "change_requests.html", {
        "items": items, "columns": columns, "github_statuses": github_statuses,
    })


@router.get("/ny")
def new_request(request: Request):
    operator_actor(request)
    workspace(request)
    return respond(request, "form_change_request.html", {"request_id": uuid4(), "values": {}, "errors": {}})


@router.post("")
async def create_request(request: Request):
    form = await auth_form(request, {"csrf_token", "request_id", *ChangeRequestDraft.model_fields},
                           max_bytes=128 * 1024)
    actor = operator_action(request, form)
    store = workspace(request)
    form.pop("csrf_token", None)
    try:
        request_id = UUID(form.pop("request_id", ""))
        if request_id.version != 4:
            raise ValueError
    except ValueError:
        raise HTTPException(422, "Registreringen saknar en giltig nyckel. Öppna ett nytt formulär.") from None

    values = {key: value.strip() for key, value in form.items() if value.strip()}
    try:
        draft = ChangeRequestDraft.model_validate(values)
    except ValidationError as exc:
        errors = {}
        for error in exc.errors():
            message = "Kontrollera värdet."
            if error["type"] == "missing":
                message = "Fyll i fältet."
            elif error["type"] == "string_too_long":
                message = f"Ange högst {error['ctx']['max_length']} tecken."
            errors[error["loc"][0]] = message
        return respond(request, "form_change_request.html", {"request_id": request_id, "values": values,
                        "errors": errors}, status_code=422)

    try:
        item = await run_in_threadpool(store.create, actor, request_id, draft)
    except ConflictError as exc:
        raise HTTPException(409, str(exc)) from None
    return RedirectResponse(f"{BASE}/{item.id}", status_code=303, headers=HEADERS)


@router.get("/{request_id}")
def request_detail(request: Request, request_id: str):
    actor = operator_actor(request)
    store = workspace(request)
    item = store.get(actor, parse_request_id(request_id))
    if item is None:
        raise missing_request()
    github = request.app.state.development_github
    return respond(request, "change_request.html", {
        "item": item,
        "moves": STATUS_MOVES[item.status],
        "release": request.app.state.change_releases.read(actor, item.id, preview=True),
        "github_repository": github.repository,
        "github_status": github.status(item.github_url, refresh=True) if item.github_url else None,
    })


@router.post("/{request_id}/inforande/{action}")
async def release_action(request: Request, request_id: str, action: str):
    if action not in ("approve", *STEPS):
        raise HTTPException(404)
    form = await auth_form(request, {"csrf_token", "review" if action == "approve" else "approval_id"})
    actor = operator_action(request, form)
    workspace(request)
    releases = request.app.state.change_releases
    identifier = parse_request_id(request_id)
    try:
        if action == "approve":
            found = await run_in_threadpool(releases.approve, actor, identifier, form.get("review", ""))
        else:
            approval = int(form.get("approval_id", ""))
            found = await run_in_threadpool(releases.advance, action, actor, identifier, approval)
    except ValueError:
        raise HTTPException(422, "Öppna ärendet igen och kontrollera granskningsunderlaget.") from None
    except ConflictError as exc:
        raise HTTPException(409, str(exc)) from None
    except OutcomeUnknown as exc:
        raise HTTPException(503, str(exc)) from None
    if not found:
        raise missing_request()
    return RedirectResponse(f"{BASE}/{identifier}#development-release", status_code=303, headers=HEADERS)


def missing_request() -> HTTPException:
    return HTTPException(404, "Ändringsärendet finns inte bland dina ärenden.")


def parse_request_id(request_id: str) -> UUID:
    try:
        return UUID(request_id)
    except ValueError:
        raise missing_request() from None


@router.post("/{request_id}/status")
async def move_request(request: Request, request_id: str):
    form = await auth_form(request, {"csrf_token", "previous", "status", "code_ref", "test_ref"})
    actor = operator_action(request, form)
    store = workspace(request)
    identifier = parse_request_id(request_id)
    try:
        status = form.get("status", "")
        review = None
        if status == "waiting_review":
            review = ReviewReferences(code_ref=form.get("code_ref", ""), test_ref=form.get("test_ref", ""))
        found = await run_in_threadpool(store.move, actor, identifier, form.get("previous", ""), status, review)
    except ValidationError:
        raise HTTPException(422, "Ange referenser till kodändringen och testbeviset (högst 300 tecken vardera).") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except ConflictError as exc:
        raise HTTPException(409, str(exc)) from None
    if not found:
        raise missing_request()
    return RedirectResponse(f"{BASE}/{identifier}", status_code=303, headers=HEADERS)


@router.post("/{request_id}/ta-over")
async def take_over_request(request: Request, request_id: str):
    form = await auth_form(request, {"csrf_token", "run_id"})
    actor = operator_action(request, form)
    store = workspace(request)
    identifier = parse_request_id(request_id)
    try:
        run_id = UUID(form.get("run_id", ""))
    except ValueError:
        raise HTTPException(422, "Öppna ärendet igen för att ta över.") from None
    try:
        found = await run_in_threadpool(store.takeover, actor, identifier, run_id)
    except ConflictError as exc:
        raise HTTPException(409, str(exc)) from None
    if not found:
        raise missing_request()
    return RedirectResponse(f"{BASE}/{identifier}", status_code=303, headers=HEADERS)


@router.post("/{request_id}/github")
async def link_request(request: Request, request_id: str):
    form = await auth_form(request, {"csrf_token", "previous", "github_url"})
    actor = operator_action(request, form)
    store = workspace(request)
    identifier = parse_request_id(request_id)
    if "github_url" not in form or "previous" not in form:
        raise HTTPException(422, "Öppna ärendet igen och ange en GitHub-länk.")
    github = request.app.state.development_github
    try:
        url = github.normalize(form["github_url"]) if form["github_url"].strip() else None
        found = await run_in_threadpool(store.link, actor, identifier, form["previous"] or None, url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except ConflictError as exc:
        raise HTTPException(409, str(exc)) from None
    if not found:
        raise missing_request()
    return RedirectResponse(f"{BASE}/{identifier}", status_code=303, headers=HEADERS)
