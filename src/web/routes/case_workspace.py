"""Autentiserad ärendedialog; webben använder bara arbetsytans adapter."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from agents.errors import HarnessError
from services.errors import ServiceError
from web.operator_auth import operator_action

router = APIRouter()


def workspace(request):
    result = getattr(request.app.state, "case_workspace", None)
    if result is None:
        raise HTTPException(503, "Ärendeassistenten är inte ansluten")
    return result


async def checked(request, fields):
    form = dict(await request.form())
    actor = operator_action(request, form)
    if set(form) - (set(fields) | {"csrf_token"}):
        raise HTTPException(422, "Formuläret innehåller okända uppgifter")
    return form, actor


@router.post("/arenden/{case_number}/komplettera")
async def amend(request: Request, case_number: str):
    form, actor = await checked(request, {"expected_digest", "salary", "kind", "corrects_version", "source", "reason"})
    try:
        await run_in_threadpool(workspace(request).amend, case_number, {
            "pensionable_salary_sek": str(form.get("salary", "")), "kind": str(form.get("kind", "new")),
            "corrects_version": str(form["corrects_version"]) if form.get("corrects_version") else None,
            "source": str(form.get("source", "employer")),
        }, actor=actor, expected_digest=str(form.get("expected_digest", "")), reason=str(form.get("reason", "")))
    except (ServiceError, HarnessError, ValueError):
        raise HTTPException(409, "Underlaget kunde inte ändras. Läs ärendet, pausa agenten och avgör väntande förslag.") from None
    return RedirectResponse(f"/arenden/{case_number}#agentstod", status_code=303)


@router.post("/arenden/{case_number}/uppdrag")
async def submit(request: Request, case_number: str, background: BackgroundTasks):
    form, actor = await checked(request, {"instruction", "submission_key", "mode", "allow_proposals"})
    console = workspace(request)
    try:
        ident = await run_in_threadpool(console.submit, case_number, str(form.get("instruction", "")),
            actor=actor, key=str(form.get("submission_key", "")), mode=str(form.get("mode", "assist")),
            allow_proposals=form.get("allow_proposals") == "yes")
    except (ServiceError, HarnessError, ValueError):
        raise HTTPException(409, "Uppdraget kunde inte beställas. Läs pågående uppdrag och kontrollera uppgifterna.") from None
    background.add_task(console.process, ident)
    return RedirectResponse(f"/arenden/{case_number}#agentstod", status_code=303)


@router.post("/arenden/{case_number}/uppdrag/{work_id}/{action}")
async def act(request: Request, case_number: str, work_id: str, action: str, background: BackgroundTasks):
    form, actor = await checked(request, {"revision", "message", "worker_stopped"})
    console = workspace(request)
    try:
        revision = int(str(form.get("revision", "")))
        if action == "interrupted":
            view = await run_in_threadpool(console.view, case_number, actor)
            if form.get("worker_stopped") != "yes" or not any(w["id"] == work_id for w in view["works"]):
                raise ValueError("Kontrollera först att tidigare arbetare har stoppats")
            await run_in_threadpool(console.mark_interrupted, work_id, actor=actor, revision=revision)
        else:
            await run_in_threadpool(console.action, case_number, work_id, action, actor=actor,
                                    revision=revision, message=str(form.get("message", "")))
        if action == "continue":
            background.add_task(console.process, work_id)
    except (ServiceError, HarnessError, ValueError):
        raise HTTPException(409, "Uppdraget har ändrats eller åtgärden är inte tillåten. Läs ärendet igen.") from None
    return RedirectResponse(f"/arenden/{case_number}#agentstod", status_code=303)
