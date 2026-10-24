"""Skrivformulär för de befintliga skrivoperationerna (S2).

- `register_salary_report` – löneunderlag, ny rapport eller rättelse (PR-ITP1-014)
- `set_policy_paid_up` – avanmälan och fribrev (PR-ITP1-013)
- `correct_premium_transaction` – rättelse av en premierad (PR-ITP1-019)

Varje formulär kräver en motivering och skickas till `ServiceLayer.execute` med
handläggaren som aktör. Stoppas anropet (`BlockedError`, `ConflictError`,
valideringsfel) visas formuläret igen med skäl och regel – tjänstelagret har då
rullat tillbaka allt. Ett lyckat anrop visar operationens resultat.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from services import ServiceError
from web.handler import check_csrf, handler_ctx, read, read_async, render, render_error, service
from web.presenters import clean_decimal, clean_month, clean_text, describe_error

router = APIRouter()


def operation_info(request: Request, name: str) -> dict[str, Any]:
    """Det formuläret visar om operationen: beskrivning, regler med status och agenters nivå."""
    svc = service(request)
    op = svc.registry.get(name)
    decision = svc.decision(name)
    return {
        "name": op.name,
        "description": op.description,
        "rules": [{"id": r, "title": svc.rules.title(r), "status": svc.rules.label(r)} for r in op.rules],
        "registered": decision.registered.value if decision.registered else None,
        "effective": decision.effective.value,
        "reasons": list(decision.reasons),
    }


async def execute(request: Request, name: str, data: dict[str, Any], reason: str | None, case_id: str | None = None):
    ctx = handler_ctx(request, reason=reason, case_id=case_id)
    return await run_in_threadpool(service(request).execute, name, ctx, data)


def _form_dict(form) -> dict[str, str]:
    return {key: str(value) for key, value in form.items() if key != "csrf_token"}


# --- löneunderlag -------------------------------------------------------------------------------


@router.get("/forsakrade/{pnr}/loneunderlag/ny")
def salary_form(
    request: Request, pnr: str, typ: str = "ny", manad: str = "", version: str = "", lon: str = "", arende: str = "",
):
    try:
        overview = read(request, "get_insured_overview", {"personal_id_number": pnr})
    except ServiceError as exc:
        return render_error(request, exc)
    values = {
        "employer_org_number": overview.employer.org_number,
        "period_month": manad,
        "pensionable_salary_sek": lon,
        "kind": "correction" if typ == "rattelse" else "new",
        "corrects_version": version,
        "source": "employer",
        "received_date": date.today().isoformat(),
        "case_number": arende,
    }
    if arende:  # registrering i ett ärende (Fas 5): referens och mottagning ur ärendet
        try:
            case = read(request, "get_case", {"case_number": arende})
        except ServiceError as exc:
            return render_error(request, exc)
        values.update(
            employer_org_number=case.employer_org_number or values["employer_org_number"],
            source=case.details.get("source", "employer"),
            source_reference=case.source_reference or "",
            received_date=case.received_date.isoformat(),
        )
    return render(request, "form_salary.html", {
        "o": overview, "tab": "salary", "values": values, "op": operation_info(request, "register_salary_report"),
    })


@router.post("/forsakrade/{pnr}/loneunderlag")
async def salary_submit(request: Request, pnr: str):
    form = await request.form()
    check_csrf(request, form)
    values = _form_dict(form)
    data = {
        "personal_id_number": pnr,
        "employer_org_number": clean_text(values.get("employer_org_number")),
        "period_month": clean_month(values.get("period_month")),
        "pensionable_salary_sek": clean_decimal(values.get("pensionable_salary_sek")),
        "kind": values.get("kind") or None,
        "corrects_version": clean_text(values.get("corrects_version")) if values.get("kind") == "correction" else None,
        "source": values.get("source") or None,
        "source_reference": clean_text(values.get("source_reference")),
        "received_date": clean_text(values.get("received_date")),
    }
    return await _submit(
        request, "register_salary_report", data, values,
        form_template="form_salary.html", lookup={"personal_id_number": pnr}, tab="salary",
        case_id=clean_text(values.get("case_number")),
    )


# --- fribrev ------------------------------------------------------------------------------------


@router.get("/forsakringar/{policy_number}/fribrev")
def paid_up_form(request: Request, policy_number: str):
    try:
        overview = read(request, "get_insured_overview", {"policy_number": policy_number})
    except ServiceError as exc:
        return render_error(request, exc)
    return render(request, "form_paid_up.html", {
        "o": overview, "tab": "overview", "policy": _policy(overview, policy_number), "values": {},
        "op": operation_info(request, "set_policy_paid_up"),
    })


@router.post("/forsakringar/{policy_number}/fribrev")
async def paid_up_submit(request: Request, policy_number: str):
    form = await request.form()
    check_csrf(request, form)
    values = _form_dict(form)
    data = {"policy_number": policy_number, "employment_end_date": clean_text(values.get("employment_end_date"))}
    return await _submit(
        request, "set_policy_paid_up", data, values,
        form_template="form_paid_up.html", lookup={"policy_number": policy_number}, tab="overview",
        policy_number=policy_number,
    )


# --- premierättelse ------------------------------------------------------------------------------


@router.get("/forsakringar/{policy_number}/premier/{transaction_id}/rattelse")
def correction_form(request: Request, policy_number: str, transaction_id: str, lon: str = ""):
    try:
        overview, transaction, linked = _transaction(request, policy_number, transaction_id)
    except ServiceError as exc:
        return render_error(request, exc)
    return render(request, "form_correction.html", {
        "o": overview, "tab": f"premiums:{policy_number}", "policy_number": policy_number,
        "t": transaction, "linked": linked, "values": {"corrected_salary_sek": lon},
        "op": operation_info(request, "correct_premium_transaction"),
    })


@router.post("/forsakringar/{policy_number}/premier/{transaction_id}/rattelse")
async def correction_submit(request: Request, policy_number: str, transaction_id: str):
    form = await request.form()
    check_csrf(request, form)
    values = _form_dict(form)
    data = {
        "transaction_id": transaction_id,
        "corrected_salary_sek": clean_decimal(values.get("corrected_salary_sek")),
        "basis_reference": clean_text(values.get("basis_reference")),
    }
    return await _submit(
        request, "correct_premium_transaction", data, values,
        form_template="form_correction.html", lookup={"policy_number": policy_number},
        tab=f"premiums:{policy_number}", policy_number=policy_number, transaction_id=transaction_id,
    )


# --- aktuell lön och kontaktuppgifter (stamdata, S5) ------------------------------------------------


@router.get("/forsakrade/{pnr}/lon")
def current_salary_form(request: Request, pnr: str):
    try:
        overview = read(request, "get_insured_overview", {"personal_id_number": pnr})
    except ServiceError as exc:
        return render_error(request, exc)
    values = {
        "monthly_salary_sek": "" if overview.monthly_salary_sek is None else str(overview.monthly_salary_sek),
        "employment_rate": "" if overview.employment_rate is None else str(overview.employment_rate),
    }
    return render(request, "form_current_salary.html", {
        "o": overview, "tab": "overview", "values": values, "op": operation_info(request, "update_current_salary"),
    })


@router.post("/forsakrade/{pnr}/lon")
async def current_salary_submit(request: Request, pnr: str):
    form = await request.form()
    check_csrf(request, form)
    values = _form_dict(form)
    data = {
        "personal_id_number": pnr,
        "monthly_salary_sek": clean_decimal(values.get("monthly_salary_sek")),
        "employment_rate": clean_decimal(values.get("employment_rate")),
    }
    return await _submit(
        request, "update_current_salary", data, values,
        form_template="form_current_salary.html", lookup={"personal_id_number": pnr}, tab="overview",
    )


@router.get("/forsakrade/{pnr}/kontakt")
def contact_form(request: Request, pnr: str):
    try:
        overview = read(request, "get_insured_overview", {"personal_id_number": pnr})
    except ServiceError as exc:
        return render_error(request, exc)
    values = {"email": overview.email or "", "phone": overview.phone or "", "source": "insured"}
    return render(request, "form_contact.html", {
        "o": overview, "tab": "overview", "values": values, "op": operation_info(request, "update_contact_details"),
    })


@router.post("/forsakrade/{pnr}/kontakt")
async def contact_submit(request: Request, pnr: str):
    form = await request.form()
    check_csrf(request, form)
    values = _form_dict(form)
    data = {
        "personal_id_number": pnr,
        "email": clean_text(values.get("email")),
        "phone": clean_text(values.get("phone")),
        "source": values.get("source") or None,
    }
    return await _submit(
        request, "update_contact_details", data, values,
        form_template="form_contact.html", lookup={"personal_id_number": pnr}, tab="overview",
    )


# --- förhandsberäkning (compute, sparar ingenting) ---------------------------------------------------


@router.post("/berakna/premie")
async def premium_preview(request: Request):
    form = await request.form()
    check_csrf(request, form)
    salary = form.get("pensionable_salary_sek") or form.get("corrected_salary_sek")
    pnr = str(form.get("personal_id_number") or "")
    data = {
        "monthly_salary_sek": clean_decimal(str(salary or "")),
        "period_month": clean_month(str(form.get("period_month") or "")),
        "birth_date": f"{pnr[0:4]}-{pnr[4:6]}-{pnr[6:8]}" if len(pnr) == 12 and pnr.isdigit() else None,
    }
    try:
        preview = await read_async(request, "calculate_premium_preview", data)
    except ServiceError as exc:
        return render(request, "partials/premium_preview.html", {"error": describe_error(exc, service(request).rules)})
    return render(request, "partials/premium_preview.html", {"preview": preview})


# --- gemensamt -------------------------------------------------------------------------------------


async def _submit(
    request: Request, name: str, data: dict[str, Any], values: dict[str, str], *,
    form_template: str, lookup: dict[str, str], tab: str, case_id: str | None = None, **context: Any,
):
    reason = clean_text(values.get("reason"))
    try:
        result = await execute(request, name, data, reason, case_id)
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        page = await _form_context(request, name, lookup, tab, values, context)
        if page["o"] is None:  # den försäkrade eller försäkringen finns inte – inget formulär att visa
            return render_error(request, exc, write=True)
        return render(request, form_template, {**page, "error": error}, status_code=error.status_code)
    overview = await read_async(request, "get_insured_overview", lookup)
    return render(request, "write_result.html", {
        "o": overview, "tab": tab, "operation": name, "result": result.output, "reason": reason,
        "op": operation_info(request, name), **context,
    })


async def _form_context(request, name, lookup, tab, values, context) -> dict[str, Any]:
    """Formuläret igen efter ett stopp – med de inmatade värdena kvar."""
    page: dict[str, Any] = {"tab": tab, "values": values, "op": operation_info(request, name), **context}
    try:
        page["o"] = await read_async(request, "get_insured_overview", lookup)
    except ServiceError:
        page["o"] = None
    if name == "set_policy_paid_up" and page["o"] is not None:
        page["policy"] = _policy(page["o"], context["policy_number"])
    if name == "correct_premium_transaction":
        try:
            _, page["t"], page["linked"] = await run_in_threadpool(
                _transaction, request, context["policy_number"], context["transaction_id"]
            )
        except ServiceError:
            page["t"], page["linked"] = None, []
    return page


def _policy(overview, policy_number: str):
    return next((p for p in overview.policies if p.policy_number == policy_number), None)


def _transaction(request: Request, policy_number: str, transaction_id: str):
    """Premieraden ur försäkringens premiehistorik, med dess länkade rättelser."""
    from services import NotFoundError

    overview = read(request, "get_insured_overview", {"policy_number": policy_number})
    history = read(request, "get_premium_history", {"policy_number": policy_number})
    transaction = next((t for t in history.transactions if t.transaction_id == transaction_id), None)
    if transaction is None:
        raise NotFoundError(f"Premieraden {transaction_id} finns inte i {policy_number}")
    linked = [t for t in history.transactions if t.corrects_transaction_id == transaction_id]
    return overview, transaction, linked
