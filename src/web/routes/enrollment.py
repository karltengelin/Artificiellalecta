"""Anslutning av ny försäkrad och arbetsgivare (S5).

- `/forsakrade/ny` – `enroll_insured_person` (PR-ITP1-012/013)
- `/arbetsgivare` – `list_employers`; `/arbetsgivare/ny` – `register_employer`

Registreras före routes.insured, så att `/forsakrade/ny` inte tolkas som ett personnummer.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from services import ServiceError
from web.handler import check_csrf, read, read_async, render, render_error, service
from web.presenters import clean_decimal, clean_text, describe_error
from web.routes.changes import execute, operation_info

router = APIRouter()

CATEGORIES = [
    ("ordinary", "Anställd utan särskild ställning"),
    ("ceo", "Verkställande direktör"),
    ("owner", "Företagare eller delägare"),
    ("posted_abroad", "Utlandsanställd"),
    ("opted_out", "Har avstått ITP"),
]


# --- ny försäkrad -----------------------------------------------------------------------------------


@router.get("/forsakrade/ny")
def enroll_form(request: Request, arbetsgivare: str = ""):
    values = {"employer_org_number": arbetsgivare, "employment_category": "ordinary", "employment_rate": "100"}
    return _enroll_page(request, values)


@router.post("/forsakrade/ny")
async def enroll_submit(request: Request):
    form = await request.form()
    check_csrf(request, form)
    values = {key: str(value) for key, value in form.items() if key != "csrf_token"}
    data = {
        "personal_id_number": (clean_text(values.get("personal_id_number")) or "").replace("-", "") or None,
        "first_name": clean_text(values.get("first_name")),
        "last_name": clean_text(values.get("last_name")),
        "employer_org_number": (clean_text(values.get("employer_org_number")) or "").replace("-", "") or None,
        "employment_start_date": clean_text(values.get("employment_start_date")),
        "itp1_start_date": clean_text(values.get("itp1_start_date")),
        "employment_category": clean_text(values.get("employment_category")),
        "affiliation_reference": clean_text(values.get("affiliation_reference")),
        "monthly_salary_sek": clean_decimal(values.get("monthly_salary_sek")),
        "employment_rate": clean_decimal(values.get("employment_rate")),
        "email": clean_text(values.get("email")),
        "phone": clean_text(values.get("phone")),
    }
    reason = clean_text(values.get("reason"))
    try:
        result = await execute(request, "enroll_insured_person", data, reason)
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        return await run_in_threadpool(_enroll_page, request, values, error)
    overview = await read_async(request, "get_insured_overview", {"personal_id_number": result.output.personal_id_number})
    return render(request, "write_result.html", {
        "o": overview, "tab": "overview", "operation": "enroll_insured_person", "result": result.output,
        "reason": reason,
    }, push_url=f"/forsakrade/{overview.personal_id_number}")


def _enroll_page(request: Request, values: dict[str, Any], error=None):
    try:
        employers = read(request, "list_employers", {"status": "active"})
    except ServiceError as exc:
        return render_error(request, exc)
    return render(request, "form_enroll.html", {
        "values": values, "employers": employers.employers, "categories": CATEGORIES, "error": error,
        "op": operation_info(request, "enroll_insured_person"), "today": date.today().isoformat(),
    }, status_code=error.status_code if error else 200, push_url="/forsakrade/ny" if error else None)


# --- arbetsgivare ------------------------------------------------------------------------------------


@router.get("/arbetsgivare")
def employers(request: Request, status: str = "active"):
    return _employers_page(request, status)


@router.get("/arbetsgivare/ny")
def employer_form(request: Request):
    return render(request, "form_employer.html", {"values": {}, "op": operation_info(request, "register_employer")})


@router.post("/arbetsgivare/ny")
async def employer_submit(request: Request):
    form = await request.form()
    check_csrf(request, form)
    values = {key: str(value) for key, value in form.items() if key != "csrf_token"}
    fields = ("org_number", "name", "affiliation_date", "industry_code", "address_street", "address_postal_code",
              "address_city", "contact_name", "contact_email", "contact_phone")
    data = {name: clean_text(values.get(name)) for name in fields}
    if data["org_number"]:
        data["org_number"] = data["org_number"].replace("-", "")
    reason = clean_text(values.get("reason"))
    try:
        result = await execute(request, "register_employer", data, reason)
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        return render(request, "form_employer.html", {
            "values": values, "error": error, "op": operation_info(request, "register_employer"),
        }, status_code=error.status_code, push_url="/arbetsgivare/ny")
    message = f"{result.output.name} ({result.output.org_number}) är registrerad som arbetsgivare med ITP."
    return await run_in_threadpool(_employers_page, request, "active", message)


def _employers_page(request: Request, status: str, message: str | None = None):
    filters = {"active": "active", "alla": None, "terminated": "terminated", "paused": "paused"}
    key = status if status in filters else "active"
    try:
        listing = read(request, "list_employers", {"status": filters[key]})
    except ServiceError as exc:
        return render_error(request, exc)
    return render(request, "employers.html", {"listing": listing, "filter": key, "message": message},
                  push_url="/arbetsgivare" if message else None)
