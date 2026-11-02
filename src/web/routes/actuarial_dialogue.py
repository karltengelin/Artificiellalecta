"""Samtal med aktuarien. Inga uppgiftsspecifika analysknappar eller modellval i formuläret."""

from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from services import Actor
from services.errors import ServiceError
from web.operator_auth import current_session, operator_action
from web.routes.actuary import page
from web.routes.auth import auth_form
from web.routes.questions import HEADERS

router = APIRouter()
ROOT = "/team/aktuarie/dialog"


def workspace(request):
    value = getattr(request.app.state, "actuarial_dialogue", None)
    if value is None:
        raise HTTPException(503, "Aktuariedialogen är inte ansluten. Starta arbetsytan med --actuary-workspace.")
    settings = request.app.state.settings
    if ((value.environment_id is not None and value.environment_id != settings.database)
            or (value.dataset_ref is not None and value.dataset_ref != settings.dataset_ref)):
        raise HTTPException(503, "Aktuariedialogen stämmer inte med vald datamiljö")
    return value


def reader(request):
    session = current_session(request)
    if session is None or not session.operator_id:
        raise HTTPException(403, "Logga in som operatör för att läsa dialogen")
    return Actor.human(session.operator_id)


@router.get(ROOT)
def listing(request: Request):
    session = current_session(request)
    items = workspace(request).listing(reader(request)) if session and session.operator_id else []
    return page(request, "actuarial_dialogue.html", {"conversations": items, "dialogue": None,
        "conversation_id": uuid4().hex, "submission_key": uuid4().hex})


@router.get(ROOT + "/{ident}")
def detail(request: Request, ident: str):
    console, actor = workspace(request), reader(request)
    return page(request, "actuarial_dialogue.html", {"conversations": console.listing(actor),
        "dialogue": console.view(ident, actor), "conversation_id": ident, "submission_key": uuid4().hex})


@router.post(ROOT + "/{ident}")
async def submit(request: Request, ident: str, background: BackgroundTasks):
    form = await auth_form(request, {"csrf_token", "message", "submission_key"})
    actor = operator_action(request, form)
    try:
        turn_id = await run_in_threadpool(workspace(request).submit, ident, form.get("message", ""),
            actor=actor, key=form.get("submission_key", ""))
    except (ValueError, ServiceError):
        raise HTTPException(409, "Meddelandet kunde inte beställas. Läs dialogen och kontrollera pågående arbete.") from None
    background.add_task(workspace(request).process, turn_id)
    return RedirectResponse(f"{ROOT}/{ident}", status_code=303, headers=HEADERS)


@router.post(ROOT + "/{ident}/avbryt/{turn_id}")
async def interrupt(request: Request, ident: str, turn_id: str):
    form = await auth_form(request, {"csrf_token"})
    actor = operator_action(request, form)
    await run_in_threadpool(workspace(request).interrupt, ident, turn_id, actor)
    return RedirectResponse(f"{ROOT}/{ident}", status_code=303, headers=HEADERS)


@router.get(ROOT + "/{ident}/leverans/{delivery_id}/{filename}")
def delivery(request: Request, ident: str, delivery_id: str, filename: str):
    result = workspace(request).delivery(ident, delivery_id, reader(request))
    content = result["content"]
    headers = {**HEADERS, "X-Content-Type-Options": "nosniff"}
    if filename == "diagram.svg" and result["kind"] == "chart":
        headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return Response(content["svg"], media_type="image/svg+xml", headers=headers)
    if filename in {"rapport.md", "rapport.pdf"} and result["kind"] == "report":
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        if filename == "rapport.md":
            return Response(content["markdown"], media_type="text/markdown; charset=utf-8", headers=headers)
        from reporting import ReportMetadata, render_report
        from reporting.analysis_chart import analysis_drawing

        charts = {}
        for ref in content.get("charts", []):
            chart = workspace(request).delivery(ident, ref["id"], reader(request))
            if chart["checksum"] != ref["checksum"]:
                raise HTTPException(409, "Rapportens diagram har ändrats")
            charts[ref["id"]] = analysis_drawing(chart["content"]["svg"])

        return Response(render_report(content["markdown"], ReportMetadata(title=result["title"],
            eyebrow="AKTUARIELL ANALYS / UTKAST", header="Artificiellalecta", footer=result["checksum"]), charts=charts),
            media_type="application/pdf", headers=headers)
    if filename == "underlag.json" and result["kind"] in {"analysis", "data"}:
        import json

        headers["Content-Disposition"] = 'attachment; filename="underlag.json"'
        return Response(json.dumps(result, ensure_ascii=False), media_type="application/json", headers=headers)
    raise HTTPException(404, "Leveransformatet saknas")
