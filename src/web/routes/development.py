"""Utvecklingsytan för autentiserade beställare i demo (projekt 11, U1)."""

from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from services.change_requests import ChangeRequestDraft, ChangeRequests
from services.errors import ConflictError
from web.handler import render
from web.operator_auth import operator_action, operator_actor
from web.routes.auth import HEADERS, auth_form

BASE = "/central/utveckling"
KINDS = {"defect": "Felanmälan", "rule_change": "Regeländring", "improvement": "Förbättring"}
router = APIRouter(prefix=BASE)


def workspace(request: Request) -> ChangeRequests:
    store = request.app.state.change_requests
    if store is None:
        raise HTTPException(404, "Utvecklingsytan finns i demomiljön.")
    return store


def respond(request: Request, template: str, context: dict, *, status_code: int = 200):
    response = render(request, template, {"operator_page": True, "base": BASE, "kinds": KINDS, **context},
                      status_code=status_code, check_database=False)
    response.headers.update(HEADERS)
    return response


@router.get("")
def list_requests(request: Request):
    actor = operator_actor(request)
    items = workspace(request).list(actor)
    return respond(request, "change_requests.html", {"items": items})


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
    try:
        identifier = UUID(request_id)
    except ValueError:
        raise HTTPException(404, "Ändringsärendet finns inte bland dina ärenden.") from None
    item = store.get(actor, identifier)
    if item is None:
        raise HTTPException(404, "Ändringsärendet finns inte bland dina ärenden.")
    return respond(request, "change_request.html", {"item": item})
