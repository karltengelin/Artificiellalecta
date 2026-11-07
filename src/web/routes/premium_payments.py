"""Premier och betalningar – paket A steg 7 (B-046, P1-PREMIE-001 §8).

Handläggarens sida för premieflödet: löneunderlagsfiler, fakturor, inbetalningar och
avstämningskontot. Allt går genom tjänstelagrets befintliga operationer:

- läsning: `list_salary_files`, `get_salary_file`, `list_invoices`, `get_invoice`,
  `list_bank_events`, `get_receivables`, `list_employers`
- ändring: `import_salary_file`, `approve_salary_file`, `reject_salary_file`, `create_invoice`,
  `check_overdue_invoices`, `import_bank_file`, `allocate_unmatched_payment`

Alla är `HUMAN_ONLY` i åtkomstregistret; sidan ger ingen agent nya befogenheter.
Personnummer visas bara i filens rader, som `get_salary_file` lämnar och loggar som läsning.

Filerna lämnas som JSON i operationernas format, till exempel från motpartssimulatorn
(`simulation.counterparties`). Märkningen `_label` följer inte med till operationen.

Saknas paket A:s tabeller i vald databas (Lakebase före steg 8) visar sidan det i stället för
ett fel, och inga formulär. En ändring som postas ändå utförs inte.
"""

from __future__ import annotations

import json
import secrets
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from services import ServiceError
from web.handler import check_csrf, read, render, render_error, service
from web.presenters import ErrorView, clean_decimal, clean_month, clean_text, describe_error, sek
from web.routes.changes import execute, operation_info

router = APIRouter()

BASE = "/premier"
#: Största fil som tas emot i formuläret
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class UploadError(Exception):
    """Den uppladdade filen kunde inte läsas som JSON i operationens format."""


# --- sidor ----------------------------------------------------------------------------------------


@router.get(BASE)
def overview(request: Request, period: str = "", arbetsgivare: str = ""):
    return _overview(request, _filters(period, arbetsgivare))


@router.get(f"{BASE}/fil")
def salary_file_page(request: Request, arbetsgivare: str = "", referens: str = ""):
    missing = _missing_tables(request)
    if missing:
        return _unavailable(request, missing)
    return _file_page(request, arbetsgivare, referens)


@router.get(f"{BASE}/fakturor/{{invoice_number}}")
def invoice_page(request: Request, invoice_number: str):
    missing = _missing_tables(request)
    if missing:
        return _unavailable(request, missing)
    try:
        invoice = read(request, "get_invoice", {"invoice_number": invoice_number})
    except ServiceError as exc:
        return render_error(request, exc)
    return render(request, "premium_invoice.html",
                  {"invoice": invoice, "employer_name": _employer_names(request).get(invoice.employer_org_number)})


# --- löneunderlagsfil -----------------------------------------------------------------------------


@router.post(f"{BASE}/filer")
async def import_salary_file(request: Request):
    form = await request.form()
    check_csrf(request, form)
    reason = clean_text(form.get("reason"))
    values = {"reason": reason or ""}
    if missing := await run_in_threadpool(_missing_tables, request):
        return await run_in_threadpool(_unavailable, request, missing, 409)
    try:
        data = await _upload(form)
        result = await execute(request, "import_salary_file", data, reason)
    except (UploadError, ServiceError) as exc:
        error = _upload_error(exc) if isinstance(exc, UploadError) else describe_error(
            exc, service(request).rules, write=True)
        return await run_in_threadpool(
            _overview, request, {}, error=error, values={"salary": values}, status_code=error.status_code)
    view = result.output
    message = (
        f"Filen {view.file_reference} var redan mottagen med samma innehåll – samma kvitto, inga nya poster."
        if view.already_received else
        f"Filen {view.file_reference} är mottagen och validerad. Ingenting är registrerat än; granska och godkänn."
    )
    return await run_in_threadpool(_file_page, request, view.employer_org_number, view.file_reference, message)


@router.post(f"{BASE}/fil/godkann")
async def approve_salary_file(request: Request):
    form = await request.form()
    check_csrf(request, form)
    org, ref = clean_text(form.get("employer_org_number")) or "", clean_text(form.get("file_reference")) or ""
    reason = clean_text(form.get("reason"))
    if missing := await run_in_threadpool(_missing_tables, request):
        return await run_in_threadpool(_unavailable, request, missing, 409)
    data = {"employer_org_number": org, "file_reference": ref, "expected_digest": clean_text(form.get("expected_digest"))}
    try:
        result = await execute(request, "approve_salary_file", data, reason)
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        return await run_in_threadpool(
            _file_page, request, org, ref, None, error, {"approve": {"reason": reason or ""}}, error.status_code)
    return await run_in_threadpool(_file_page, request, org, ref, result.output.note, None, None, 200, result.output)


@router.post(f"{BASE}/fil/avsla")
async def reject_salary_file(request: Request):
    form = await request.form()
    check_csrf(request, form)
    org, ref = clean_text(form.get("employer_org_number")) or "", clean_text(form.get("file_reference")) or ""
    reason, note = clean_text(form.get("reason")), clean_text(form.get("decision_note"))
    if missing := await run_in_threadpool(_missing_tables, request):
        return await run_in_threadpool(_unavailable, request, missing, 409)
    data = {"employer_org_number": org, "file_reference": ref, "decision_note": note}
    try:
        result = await execute(request, "reject_salary_file", data, reason)
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        values = {"reject": {"reason": reason or "", "decision_note": note or ""}}
        return await run_in_threadpool(_file_page, request, org, ref, None, error, values, error.status_code)
    return await run_in_threadpool(_file_page, request, org, ref, result.output.note, None, None, 200, result.output)


# --- faktura och bevakning ------------------------------------------------------------------------


@router.post(f"{BASE}/fakturera")
async def create_invoice(request: Request):
    form = await request.form()
    check_csrf(request, form)
    org, period = clean_text(form.get("employer_org_number")), clean_month(form.get("period_month"))
    reason = clean_text(form.get("reason"))
    values = {"employer_org_number": org or "", "period_month": (period or "")[:7], "reason": reason or ""}
    if missing := await run_in_threadpool(_missing_tables, request):
        return await run_in_threadpool(_unavailable, request, missing, 409)
    try:
        result = await execute(request, "create_invoice", {"employer_org_number": org, "period_month": period}, reason)
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        return await run_in_threadpool(
            _overview, request, {}, error=error, values={"invoice": values}, status_code=error.status_code)
    return await run_in_threadpool(_overview, request, {}, message=result.output.note,
                                   outcome={"kind": "invoice", "result": result.output})


@router.post(f"{BASE}/bevakning")
async def check_overdue(request: Request):
    form = await request.form()
    check_csrf(request, form)
    reason = clean_text(form.get("reason"))
    if missing := await run_in_threadpool(_missing_tables, request):
        return await run_in_threadpool(_unavailable, request, missing, 409)
    try:
        result = await execute(request, "check_overdue_invoices", {}, reason)
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        return await run_in_threadpool(_overview, request, {}, error=error,
                                       values={"overdue": {"reason": reason or ""}}, status_code=error.status_code)
    return await run_in_threadpool(_overview, request, {}, message=result.output.note,
                                   outcome={"kind": "overdue", "result": result.output})


# --- bankfil och avstämningskonto -----------------------------------------------------------------


@router.post(f"{BASE}/bankfil")
async def import_bank_file(request: Request):
    form = await request.form()
    check_csrf(request, form)
    reason = clean_text(form.get("reason"))
    if missing := await run_in_threadpool(_missing_tables, request):
        return await run_in_threadpool(_unavailable, request, missing, 409)
    try:
        data = await _upload(form)
        result = await execute(request, "import_bank_file", data, reason)
    except (UploadError, ServiceError) as exc:
        error = _upload_error(exc) if isinstance(exc, UploadError) else describe_error(
            exc, service(request).rules, write=True)
        return await run_in_threadpool(_overview, request, {}, error=error,
                                       values={"bank": {"reason": reason or ""}}, status_code=error.status_code)
    return await run_in_threadpool(_overview, request, {}, message=_bank_message(result.output),
                                   outcome={"kind": "bank", "result": result.output})


@router.post(f"{BASE}/fordela")
async def allocate_unmatched(request: Request):
    form = await request.form()
    check_csrf(request, form)
    values = {key: str(value) for key, value in form.items() if key != "csrf_token"}
    data = {
        "source_system": clean_text(values.get("source_system")),
        "event_id": clean_text(values.get("event_id")),
        "invoice_number": clean_text(values.get("invoice_number")),
        "amount_sek": clean_decimal(values.get("amount_sek")),
        "payer_verification": clean_text(values.get("payer_verification")),
        "request_key": clean_text(values.get("request_key")),
    }
    if missing := await run_in_threadpool(_missing_tables, request):
        return await run_in_threadpool(_unavailable, request, missing, 409)
    try:
        result = await execute(request, "allocate_unmatched_payment", data, clean_text(values.get("reason")))
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        return await run_in_threadpool(_overview, request, {}, error=error,
                                       values={"allocate": values}, status_code=error.status_code)
    return await run_in_threadpool(_overview, request, {}, message=_allocation_message(result.output),
                                   outcome={"kind": "allocate", "result": result.output})


# --- hjälpare -------------------------------------------------------------------------------------


def _employer_names(request: Request) -> dict[str, str]:
    """Namn till rubriker; saknas registret visas organisationsnumret i stället."""
    try:
        return {e.org_number: e.name for e in read(request, "list_employers", {}).employers}
    except ServiceError:
        return {}


def _bank_message(output) -> str:
    """Operationens notering med belopp i kronformat (noteringen i loggen är oförändrad)."""
    return (f"{output.new_events} nya inbetalningar: {sek(output.allocated_sek)} fördelat på fakturor och "
            f"{sek(output.unallocated_sek)} på avstämningskontot. Ingen garanti eller kapital skapas här (PA7).")


def _allocation_message(output) -> str:
    if output.status != "allocated":
        return output.note
    return (f"{sek(output.allocated_sek)} fördelat från avstämningskontot till {output.invoice_number}; "
            f"{sek(output.remaining_suspense_sek)} kvar.")


def _filters(period: str, employer: str) -> dict[str, str]:
    filters = {}
    if month := clean_month(period):
        filters["period"] = month
    if org := clean_text(employer):
        filters["employer"] = org
    return filters


def _missing_tables(request: Request) -> list[str]:
    """Paket A:s tabeller som saknas i vald databas (list_salary_files läser bara schemat då)."""
    return list(read(request, "list_salary_files", {"limit": 1}).missing_tables)


def _unavailable(request: Request, missing: list[str], status_code: int = 200):
    return render(request, "premium_payments.html", {"missing_tables": missing, "write_refused": status_code != 200},
                  status_code=status_code, push_url=BASE if request.method == "POST" else None)


def _overview(request: Request, filters: dict[str, str], *, error: ErrorView | None = None,
              message: str | None = None, values: dict | None = None, outcome: dict | None = None,
              status_code: int = 200):
    query: dict[str, Any] = {}
    if filters.get("period"):
        query["period_month"] = filters["period"]
    if filters.get("employer"):
        query["employer_org_number"] = filters["employer"]
    try:
        files = read(request, "list_salary_files", query)
        if files.missing_tables:
            return _unavailable(request, list(files.missing_tables))
        invoices = read(request, "list_invoices", query)
        events = read(request, "list_bank_events", {"payer_org_number": filters.get("employer")})
        suspense = read(request, "list_bank_events", {"unallocated_only": True})
        receivables = read(request, "get_receivables", {"employer_org_number": filters.get("employer")})
        open_debits = read(request, "get_receivables", {}).open_invoices
        employers = read(request, "list_employers", {}).employers
    except ServiceError as exc:
        return render_error(request, exc)
    push = f"{BASE}?{urlencode({k: v for k, v in _url_filters(filters).items() if v})}".rstrip("?")
    return render(request, "premium_payments.html", {
        "missing_tables": [], "filters": filters, "url_filters": _url_filters(filters),
        "files": files, "invoices": invoices, "events": events, "suspense": suspense, "receivables": receivables,
        "open_debits": open_debits, "employers": employers, "employer_names": {e.org_number: e.name for e in employers},
        "error": error, "message": message, "values": values or {}, "outcome": outcome,
        "new_key": lambda: secrets.token_hex(16),
        "ops": {name: operation_info(request, name) for name in (
            "import_salary_file", "create_invoice", "check_overdue_invoices", "import_bank_file",
            "allocate_unmatched_payment")},
    }, status_code=status_code, push_url=push if request.method == "POST" else None)


def _url_filters(filters: dict[str, str]) -> dict[str, str]:
    return {"period": (filters.get("period") or "")[:7], "arbetsgivare": filters.get("employer") or ""}


def _file_page(request: Request, org: str, ref: str, message: str | None = None, error: ErrorView | None = None,
               values: dict | None = None, status_code: int = 200, decision=None):
    try:
        view = read(request, "get_salary_file", {"employer_org_number": org, "file_reference": ref})
    except ServiceError as exc:
        if error is None:
            return render_error(request, exc)
        view = None
    names = _employer_names(request)
    url = f"{BASE}/fil?{urlencode({'arbetsgivare': org, 'referens': ref})}"
    return render(request, "premium_file.html", {
        "file": view, "employer_name": names.get(org), "message": message, "error": error,
        "values": values or {}, "decision": decision, "file_url": url,
        "approve_op": operation_info(request, "approve_salary_file"),
        "reject_op": operation_info(request, "reject_salary_file"),
    }, status_code=status_code, push_url=url if request.method == "POST" else None)


async def _upload(form) -> dict[str, Any]:
    """Den uppladdade JSON-filen som operationens indata; märkningen `_label` tas bort."""
    upload = form.get("file")
    if upload is None or isinstance(upload, str) or not getattr(upload, "filename", None):
        raise UploadError("Välj en fil att läsa in")
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadError(f"Filen är större än {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    try:
        data = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UploadError(f"Filen är inte giltig JSON ({exc.__class__.__name__})") from exc
    if not isinstance(data, dict):
        raise UploadError("Filen ska innehålla ett JSON-objekt i operationens format")
    data.pop("_label", None)
    return data


def _upload_error(exc: UploadError) -> ErrorView:
    return ErrorView("invalid", "Filen kunde inte läsas", str(exc), 422, field_errors={"file": str(exc)},
                     nothing_changed=True)
