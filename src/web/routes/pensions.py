"""Pensioner och utbetalningar – paket B steg 8 (B-056, P1-PENSION-001 §10.1, Karls val Z1–Z14).

Handläggarens sida för uttagsflödet: översikten och sex flöden – pensionsakten per försäkring med begäran,
plan, skatt, konto och dödsfall, månadsrätterna och bolagskontot, bankfilerna, dödsfallen och
månadsstängningen. Allt går genom tjänstelagrets operationer:

- läsning: `get_pension_status`, `list_payout_parts`, `get_payout_person` (nya i steg 8, Z4) och steg 3–7:s
  `get_payout_part`, `preview_payout_plan`, `list_pension_claims`, `list_payout_orders`,
  `get_death_settlement`, `prepare_month_close`, `get_month_close`
- ändring: steg 3–7:s fjorton skrivande operationer (Z3)

Alla är `HUMAN_ONLY`; sidan ger ingen agent nya befogenheter (Z14). Registreringar görs av handläggaren;
månadsstängningen, bankfilens godkännande och bolagskapitalet kräver inloggad operatör (Z5). Kanalen sätts
här till `manual` – kundportal och chattbot har egna vägar (Z5, Z12).

Personnummer finns aldrig i adresser eller listor; pensionsakten öppnas på försäkringsnumret och visar
personnumret bara i sidhuvudet (Z6). Kontonummer visas maskerade.

Varje vy hör till ett steg (Z9). Är steget – eller ett steg före det – inte infört i vald databas visar vyn
det, med tabeller och migrationsskript, och inga formulär. En ändring som postas ändå utförs inte (409)
och loggas inte.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from services import OperationContext, ServiceError
from web.handler import check_csrf, handler_ctx, read, render, render_error, service, settings
from web.operator_auth import operator_action
from web.presenters import ErrorView, clean_month, clean_text, describe_error
from web.routes.changes import operation_info
from web.uploads import UploadError, read_upload, upload_error

router = APIRouter()

BASE = "/pensioner"
PAGE_SIZE = 50
#: Tidigaste dag en migration får köras mot Lakebase (novembers stängning först, Karls OK)
EARLIEST_MIGRATION = "2026-12-01"

#: Operationerna sidan skriver med: steget de kräver och vem som är aktör (Z3, Z5, Z9)
WRITES: dict[str, tuple[int, str]] = {
    "register_payout_request": (4, "handler"),
    "decide_payout_plan": (4, "handler"),
    "split_payout_part": (4, "handler"),
    "register_company_capital": (5, "operator"),
    "register_tax_status": (6, "handler"),
    "register_payout_account": (6, "handler"),
    "create_payout_orders": (6, "handler"),
    "approve_payout_order": (6, "operator"),
    "import_payout_receipts": (6, "handler"),
    "register_death_report": (7, "handler"),
    "verify_death_report": (7, "handler"),
    "import_death_notices": (7, "handler"),
    "register_estate_authority": (7, "handler"),
    "close_policy_month": (3, "operator"),
}
#: Vyerna och stegen de bygger på (Z9)
VIEW_STEPS = {"overview": 1, "akt": 2, "claims": 5, "bank": 6, "deaths": 7, "close": 3}
VIEW_TITLES = {"overview": "Översikten", "akt": "Pensionsakten", "claims": "Månadsrätter och bolagskonto",
               "bank": "Bankfilerna", "deaths": "Dödsfallen", "close": "Månadsstängningen"}


class FormError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


class Refused(Exception):
    """Steget som ändringen kräver är inte infört – ingenting anropas eller loggas."""

    def __init__(self, status: dict, step: int):
        super().__init__(step)
        self.status, self.step = status, step


# --- läget och stegen -----------------------------------------------------------------------------


def _status(request: Request) -> dict:
    return read(request, "get_pension_status", {}).payload


def _ready(status: dict, step: int) -> bool:
    return all(s["introduced"] for s in status["steps"] if s["step"] <= step)


def _missing(status: dict, step: int) -> list[dict]:
    return [s for s in status["steps"] if s["step"] <= step and not s["introduced"]]


def _unavailable(request: Request, status: dict, view: str, step: int, status_code: int = 200):
    return render(request, "pensions_unavailable.html", {
        "status": status, "view_title": VIEW_TITLES[view], "missing": _missing(status, step),
        "earliest": EARLIEST_MIGRATION, "write_refused": status_code != 200,
    }, status_code=status_code, push_url=BASE if request.method == "POST" else None)


def _today(request: Request) -> date:
    return settings(request).business_day or date.today()


def _base_context(request: Request, status: dict, **extra) -> dict:
    return {"status": status, "steps": {s["step"]: s for s in status["steps"]}, "today": _today(request).isoformat(),
            "can_book": settings(request).database != "lakebase", **extra}


# --- formulärvärden -------------------------------------------------------------------------------


def _text(form, name: str, *, required: bool = False) -> str | None:
    value = clean_text(form.get(name))
    if required and not value:
        raise FormError(name, "Fältet behövs")
    return value


def _date(form, name: str, *, required: bool = True) -> str | None:
    raw = clean_text(form.get(name))
    if not raw:
        if required:
            raise FormError(name, "Ange ett datum")
        return None
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        raise FormError(name, "Ange datumet som ÅÅÅÅ-MM-DD") from None


def _month(form, name: str, *, required: bool = True) -> str | None:
    value = clean_month(form.get(name))
    if value is None and required:
        raise FormError(name, "Ange månaden som ÅÅÅÅ-MM")
    return value


def _int(form, name: str, *, required: bool = True) -> int | None:
    raw = clean_text(form.get(name))
    if not raw:
        if required:
            raise FormError(name, "Ange ett heltal")
        return None
    try:
        return int(raw)
    except ValueError:
        raise FormError(name, "Ange ett heltal") from None


def _decimal(form, name: str, *, required: bool = True) -> str | None:
    raw = clean_text(form.get(name))
    if not raw:
        if required:
            raise FormError(name, "Ange ett belopp")
        return None
    try:
        return str(Decimal(raw.replace(" ", "").replace(" ", "").replace(",", ".")))
    except InvalidOperation:
        raise FormError(name, "Ange ett tal, t.ex. 1234,50") from None


def _checked(form, name: str) -> bool:
    return form.get(name) in {"on", "true", "1", "yes"}


def _channel(form) -> str:
    """Sidan registrerar det som kommit in manuellt; kundportal och chattbot har egna vägar (Z5, Z12)."""
    channel = clean_text(form.get("channel")) or "manual"
    if channel != "manual":
        raise FormError("channel", "Sidan registrerar bara uppgifter som kommit in manuellt – kundportalen och "
                                   "chattboten har egna vägar")
    return channel


def _values(form) -> dict[str, str]:
    """Formulärets värden för omvisning; kontonummer visas aldrig igen (Z6)."""
    return {k: str(v) for k, v in form.items()
            if k not in {"csrf_token", "file", "account_number"} and isinstance(v, str)}


def _form_error(exc: FormError) -> ErrorView:
    return ErrorView("invalid", "Uppgifterna behöver rättas", str(exc), 422, field_errors={exc.field: str(exc)},
                     nothing_changed=True)


def _service_error(request: Request, exc: ServiceError) -> ErrorView:
    error = describe_error(exc, service(request).rules, write=True)
    if error.kind == "conflict":  # Z8: ändrat underlag sedan granskningen
        error = replace(error, title="Underlaget har ändrats – granska igen")
    return error


# --- skrivvägen -----------------------------------------------------------------------------------


Page = Callable[..., Response]


async def _submit(request: Request, form, op: str, build: Callable[[], Awaitable[dict] | dict], page: Page,
                  *, form_key: str, message: Callable[[dict], str] | None = None, view: str = "overview"):
    """Gemensam skrivväg: aktör och token, stegkontroll, indata, operationen, felruta eller resultat."""
    step, who = WRITES[op]
    actor = operator_action(request, form) if who == "operator" else None
    if actor is None:
        check_csrf(request, form)
    status = await run_in_threadpool(_status, request)
    if not _ready(status, step):
        return await run_in_threadpool(_unavailable, request, status, view, step, 409)
    reason = clean_text(form.get("reason"))
    values = {form_key: _values(form)}
    try:
        if not reason or len(reason) < 3:
            raise FormError("reason", "Skriv en motivering – den sparas i händelseloggen")
        data = build()
        if hasattr(data, "__await__"):
            data = await data
        ctx = OperationContext(actor=actor, reason=reason) if actor else handler_ctx(request, reason=reason)
        result = await run_in_threadpool(service(request).execute, op, ctx, data)
    except FormError as exc:
        error = _form_error(exc)
    except UploadError as exc:
        error = upload_error(exc)
    except ServiceError as exc:
        error = _service_error(request, exc)
    else:
        payload = result.output.payload
        text = message(payload) if message else "Klart."
        return await run_in_threadpool(lambda: page(message=text, outcome={"op": op, "result": payload}))
    return await run_in_threadpool(lambda: page(error=error, values=values, status_code=error.status_code))


# --- översikten -----------------------------------------------------------------------------------


@router.get(BASE)
def overview(request: Request, lage: str = "", sextiosex: str = "", sok: str = "", sida: int = 1):
    filters = {"lage": clean_text(lage) or "", "sextiosex": "1" if sextiosex else "", "sok": clean_text(sok) or ""}
    return _overview(request, filters, max(sida, 1))


def _overview(request: Request, filters: dict, page_number: int = 1):
    try:
        status = _status(request)
        if not _ready(status, VIEW_STEPS["overview"]):
            return _unavailable(request, status, "overview", 1)
        query: dict[str, Any] = {"limit": PAGE_SIZE, "offset": (page_number - 1) * PAGE_SIZE}
        if filters["lage"]:
            query["state"] = filters["lage"]
        if filters["sextiosex"]:
            query["turning_66"] = True
        if filters["sok"] and len(filters["sok"]) >= 2:
            if filters["sok"].isdigit() and len(filters["sok"]) >= 6:
                parts = None  # Z6: ingen sökning på personnummer
            else:
                query["query"] = filters["sok"]
                parts = read(request, "list_payout_parts", query).payload
        else:
            parts = read(request, "list_payout_parts", query).payload
    except ServiceError as exc:
        return render_error(request, exc)
    pages = max(1, -(-parts["total"] // PAGE_SIZE)) if parts else 1
    url_filters = {k: v for k, v in filters.items() if v}
    return render(request, "pensions.html", _base_context(
        request, status, parts=parts, filters=filters, page=page_number, pages=pages,
        page_url=lambda n: f"{BASE}?{urlencode({**url_filters, 'sida': n})}"))


# --- pensionsakten --------------------------------------------------------------------------------


def _person(request: Request, policy: str) -> dict:
    return read(request, "get_payout_person", {"policy_number": policy}).payload


def _all_parts(request: Request) -> dict[str, dict]:
    """Delarna per id för tabeller som bara bär intern id (anspråk, bankuppdrag)."""
    out, offset = {}, 0
    while True:
        page = read(request, "list_payout_parts", {"limit": 500, "offset": offset}).payload
        out.update({p["part_id"]: p for p in page["parts"]})
        offset += page["count"]
        if not page["count"] or offset >= page["total"]:
            return out


@router.get(BASE + "/forsakringar/{policy}")
def policy_page(request: Request, policy: str):
    return _akt(request, policy)


def _akt(request: Request, policy: str, *, error: ErrorView | None = None, message: str | None = None,
         values: dict | None = None, outcome: dict | None = None, status_code: int = 200, preview: dict | None = None):
    try:
        status = _status(request)
        if not _ready(status, VIEW_STEPS["akt"]):
            return _unavailable(request, status, "akt", VIEW_STEPS["akt"], 409 if request.method == "POST" else 200)
        person = _person(request, policy)
        own = [p for p in person["parts"] if p["policy_number"] == policy]
        part_views = [read(request, "get_payout_part", {"policy_number": policy, "part_number": p["part_number"]}).payload
                      for p in own]
        ids = {p["part_id"]: p["part_number"] for p in own}
        claims, payment = [], {}
        if _ready(status, 5):
            claims = [c for c in read(request, "list_pension_claims", {}).payload["claims"] if c["payout_part_id"] in ids]
        if _ready(status, 6):
            payment = {c["claim_id"]: c for c in read(request, "list_payout_orders", {}).payload["claims"]
                       if c["payout_part_id"] in ids}
        death = None
        if _ready(status, 7):
            death = read(request, "get_death_settlement", {"personal_id_number": person["personal_id_number"]}).payload
    except ServiceError as exc:
        return render_error(request, exc)
    url = f"{BASE}/forsakringar/{policy}"
    return render(request, "pensions_policy.html", _base_context(
        request, status, policy=policy, person=person, parts=own, part_views=part_views, part_numbers=ids,
        claims=claims, payment=payment, death=death, error=error, message=message, values=values or {},
        outcome=outcome, preview=preview, url=url,
        ops={name: operation_info(request, name) for name in (
            "register_payout_request", "decide_payout_plan", "split_payout_part", "register_tax_status",
            "register_payout_account", "register_death_report", "verify_death_report",
            "register_estate_authority")},
    ), status_code=status_code, push_url=url if request.method == "POST" else None)


def _pnr(request: Request, policy: str) -> str:
    """Personnumret slås upp på servern – det skickas aldrig i formuläret eller adressen (Z6)."""
    return _person(request, policy)["personal_id_number"]


@router.post(BASE + "/forsakringar/{policy}/begaran")
async def register_request(request: Request, policy: str):
    form = await request.form()

    def build():
        kind = _text(form, "kind", required=True)
        content: dict[str, Any] = {}
        if kind == "start":
            content = {"first_right": _month(form, "first_right"), "form": _text(form, "form", required=True)}
            if content["form"] == "fixed_term":
                content["payments"] = _int(form, "payments")
        elif kind == "pause":
            content = {"first": _month(form, "pause_first"), "resume": _month(form, "pause_resume")}
        elif kind == "extend":
            content = {"month": _month(form, "extend_month"), "form": _text(form, "extend_form", required=True)}
            if content["form"] == "fixed_term":
                content["payments"] = _int(form, "extend_payments")
        elif kind == "split":
            content = {"month": _month(form, "split_month"), "share": _decimal(form, "split_share"),
                       "premium_receiver": _int(form, "premium_receiver")}
        requester = _text(form, "requester") or "insured"
        if requester == "representative" and not _checked(form, "authority_verified"):
            raise FormError("authority_verified", "Ombudets behörighet ska vara verifierad innan begäran registreras")
        return {"policy_number": policy, "part_number": _int(form, "part_number"), "kind": kind, "content": content,
                "received_date": _date(form, "received_date"), "channel": _channel(form), "requester": requester,
                "authority_verified": _checked(form, "authority_verified")}

    return await _submit(request, form, "register_payout_request", build,
                         lambda **kw: _akt(request, policy, **kw), form_key="request", view="akt",
                         message=lambda r: (f"Begäran är registrerad: ändringsmånad {r['change_month'][:7]}, frist "
                                            f"{r['deadline']}. Förhandsberäkna och besluta den under Begäran."
                                            if r.get("created") else "Samma begäran fanns redan – ingen ny registrering."))


@router.get(BASE + "/forsakringar/{policy}/begaran/{request_id}")
def preview_request(request: Request, policy: str, request_id: str):
    try:
        status = _status(request)
        if not _ready(status, 4):
            return _unavailable(request, status, "akt", 4)
    except ServiceError as exc:
        return render_error(request, exc)
    try:
        preview = read(request, "preview_payout_plan", {"request_id": request_id}).payload
    except ServiceError as exc:  # t.ex. begäran är redan beslutad eller delen har startat – akten visar skälet
        error = describe_error(exc, service(request).rules)
        return _akt(request, policy, error=replace(error, title="Begäran kan inte förhandsberäknas"),
                    status_code=error.status_code)
    return _akt(request, policy, preview={"request_id": request_id, **preview})


@router.post(BASE + "/forsakringar/{policy}/begaran/{request_id}/beslut")
async def decide_request(request: Request, policy: str, request_id: str):
    form = await request.form()
    op = "split_payout_part" if form.get("kind") == "split" else "decide_payout_plan"

    def build():
        return {"request_id": request_id, "reviewed_checksum": _text(form, "reviewed_checksum", required=True),
                "reason": _text(form, "reason", required=True)}

    return await _submit(request, form, op, build, lambda **kw: _akt(request, policy, **kw), form_key="decide",
                         view="akt", message=lambda r: (
                             f"Delningen är beslutad: del {r.get('new_part_number')} från {r.get('effective_month')}."
                             if op == "split_payout_part" else
                             f"Planversion {r.get('version')} är beslutad från {r.get('effective_month')}. "
                             "Ändringsmånadens stängning genomför den."))


@router.post(BASE + "/forsakringar/{policy}/skatt")
async def register_tax(request: Request, policy: str):
    form = await request.form()

    def build():
        return {"personal_id_number": _pnr(request, policy), "tax_year": _int(form, "tax_year"),
                "kind": _text(form, "kind", required=True), "rate": _decimal(form, "rate", required=False),
                "fixed_amount_sek": _decimal(form, "fixed_amount_sek", required=False),
                "table_number": _int(form, "table_number", required=False),
                "table_column": _int(form, "table_column", required=False),
                "raised_deduction": _checked(form, "raised_deduction"),
                "decision_ref": _text(form, "decision_ref"), "received_date": _date(form, "received_date"),
                "channel": _channel(form)}

    return await _submit(request, form, "register_tax_status", build, lambda **kw: _akt(request, policy, **kw),
                         form_key="tax", view="akt", message=lambda r: (
                             f"Skattestatus för {r['tax_year']} är registrerad som version {r['version']}, gäller från "
                             f"{r['valid_from']}." if r.get("created") else
                             "Samma skattestatus fanns redan – ingen ny version."))


@router.post(BASE + "/forsakringar/{policy}/konto")
async def register_account(request: Request, policy: str):
    form = await request.form()

    def build():
        verified = _checked(form, "verified")
        return {"personal_id_number": _pnr(request, policy), "clearing_number": _text(form, "clearing_number", required=True),
                "account_number": _text(form, "account_number", required=True),
                "bank_name": _text(form, "bank_name", required=True), "verified": verified,
                "verification_method": _text(form, "verification_method"),
                "verification_ref": _text(form, "verification_ref"), "received_date": _date(form, "received_date"),
                "channel": _channel(form)}

    return await _submit(request, form, "register_payout_account", build, lambda **kw: _akt(request, policy, **kw),
                         form_key="account", view="akt", message=lambda r: (
                             f"Kontot {r['clearing_number']} {r['account_number']} är registrerat som version "
                             f"{r['version']}." if r.get("created") else "Samma konto fanns redan – ingen ny version."))


@router.post(BASE + "/forsakringar/{policy}/dodsfall")
async def register_death(request: Request, policy: str):
    form = await request.form()

    def build():
        return {"personal_id_number": _pnr(request, policy), "status": _text(form, "status", required=True),
                "death_date": _date(form, "death_date", required=False), "reported_on": _date(form, "reported_on"),
                "received_date": _date(form, "received_date"), "source": _text(form, "source", required=True),
                "source_ref": _text(form, "source_ref", required=True),
                "verification_method": _text(form, "verification_method"),
                "document_ref": _text(form, "document_ref"), "channel": _channel(form)}

    return await _submit(request, form, "register_death_report", build, lambda **kw: _akt(request, policy, **kw),
                         form_key="death", view="akt",
                         message=lambda r: "Dödsfallsbeskedet är registrerat. Bankuppdragen stoppas; avräkningen görs i "
                                           "dödsmånadens stängning.")


@router.post(BASE + "/forsakringar/{policy}/dodsfall/andra")
async def verify_death(request: Request, policy: str):
    form = await request.form()

    def build():
        return {"personal_id_number": _pnr(request, policy), "action": _text(form, "action", required=True),
                "death_date": _date(form, "death_date", required=False),
                "verification_method": _text(form, "verification_method"),
                "document_ref": _text(form, "document_ref"), "received_date": _date(form, "received_date"),
                "note": _text(form, "note"), "channel": _channel(form)}

    return await _submit(request, form, "verify_death_report", build, lambda **kw: _akt(request, policy, **kw),
                         form_key="verify", view="akt", message=lambda r: "Beskedet har fått en ny version.")


@router.post(BASE + "/forsakringar/{policy}/dodsbo")
async def register_estate(request: Request, policy: str):
    form = await request.form()

    def build():
        return {"personal_id_number": _pnr(request, policy), "role": _text(form, "role", required=True),
                "representative": _text(form, "representative", required=True),
                "document_kind": _text(form, "document_kind", required=True),
                "document_ref": _text(form, "document_ref", required=True), "verified": _checked(form, "verified"),
                "verification_method": _text(form, "verification_method"),
                "verification_ref": _text(form, "verification_ref"),
                "account_id": _text(form, "account_id", required=True), "received_date": _date(form, "received_date"),
                "channel": _channel(form)}

    return await _submit(request, form, "register_estate_authority", build, lambda **kw: _akt(request, policy, **kw),
                         form_key="estate", view="akt", message=lambda r: "Dödsboets behörighet är registrerad.")


@router.get(BASE + "/arenden/{case_number}")
def case_link(request: Request, case_number: str):
    """Ärendesidans länk (Z11): till pensionsakten, bolagskontot eller dödsfallen – utan personnummer i adressen."""
    try:
        case = read(request, "get_case", {"case_number": case_number})
        if case.case_type == "company_capital":
            return RedirectResponse(f"{BASE}/manadsratter#bolagskonto", status_code=303)
        if case.case_type == "inheritance_pool":
            return RedirectResponse(f"{BASE}/dodsfall", status_code=303)
        policy = case.policy_number
        if policy is None and case.personal_id_number:
            policies = read(request, "get_payout_person", {"personal_id_number": case.personal_id_number}).payload
            policy = (policies["policies"] or [None])[0]
    except ServiceError as exc:
        return render_error(request, exc)
    if policy is None:
        raise HTTPException(404, "Ärendet hör inte till någon försäkring")
    return RedirectResponse(f"{BASE}/forsakringar/{policy}", status_code=303)


# --- månadsrätter och bolagskonto -----------------------------------------------------------------


@router.get(BASE + "/manadsratter")
def claims_page(request: Request, manad: str = ""):
    return _claims(request, clean_month(manad))


def _claims(request: Request, month: str | None = None, *, error: ErrorView | None = None, message: str | None = None,
            values: dict | None = None, outcome: dict | None = None, status_code: int = 200):
    try:
        status = _status(request)
        if not _ready(status, VIEW_STEPS["claims"]):
            return _unavailable(request, status, "claims", 5, 409 if request.method == "POST" else 200)
        claims = read(request, "list_pension_claims", {"month": month} if month else {}).payload
        parts = _all_parts(request)
    except ServiceError as exc:
        return render_error(request, exc)
    url = f"{BASE}/manadsratter" + (f"?manad={month[:7]}" if month else "")
    return render(request, "pensions_claims.html", _base_context(
        request, status, claims=claims, parts=parts, month=(month or "")[:7], error=error, message=message,
        values=values or {}, outcome=outcome, op=operation_info(request, "register_company_capital"),
    ), status_code=status_code, push_url=url if request.method == "POST" else None)


@router.post(BASE + "/manadsratter/bolagskonto")
async def company_capital(request: Request):
    form = await request.form()

    def build():
        return {"amount_sek": _decimal(form, "amount_sek"), "decided_on": _date(form, "decided_on"),
                "document_ref": _text(form, "document_ref", required=True), "note": _text(form, "note") or "",
                "emin_reference": _text(form, "emin_reference")}

    return await _submit(request, form, "register_company_capital", build, lambda **kw: _claims(request, **kw),
                         form_key="capital", view="claims", message=lambda r: (
                             f"Insättningen är bokad på bolagskontot i {r.get('month')}." if r.get("created") else
                             "Samma insättning fanns redan – ingen ny verifikation."))


# --- bankfilerna ----------------------------------------------------------------------------------


@router.get(BASE + "/bankfiler")
def bank_page(request: Request):
    return _bank(request)


def _bank(request: Request, *, error: ErrorView | None = None, message: str | None = None, values: dict | None = None,
          outcome: dict | None = None, status_code: int = 200):
    try:
        status = _status(request)
        if not _ready(status, VIEW_STEPS["bank"]):
            return _unavailable(request, status, "bank", 6, 409 if request.method == "POST" else 200)
        orders = read(request, "list_payout_orders", {}).payload
        parts = _all_parts(request)
    except ServiceError as exc:
        return render_error(request, exc)
    return render(request, "pensions_bank.html", _base_context(
        request, status, orders=orders, parts=parts, error=error, message=message, values=values or {},
        outcome=outcome, ops={name: operation_info(request, name) for name in (
            "create_payout_orders", "approve_payout_order", "import_payout_receipts")},
    ), status_code=status_code, push_url=f"{BASE}/bankfiler" if request.method == "POST" else None)


@router.post(BASE + "/bankfiler/skapa")
async def create_orders(request: Request):
    form = await request.form()
    return await _submit(request, form, "create_payout_orders", lambda: {"payment_day": _date(form, "payment_day")},
                         lambda **kw: _bank(request, **kw), form_key="create", view="bank",
                         message=lambda r: ("Bankfilen är skapad. Granska uppdragen och godkänn filen nedan." if r.get("created")
                                            else "Bankfilen för dagen finns redan – inget nytt skapades.")
                         if r.get("file") else
                         "Inga anspråk att betala för dagen – ingen bankfil.")


@router.post(BASE + "/bankfiler/godkann")
async def approve_orders(request: Request):
    form = await request.form()

    def build():
        if not _checked(form, "reviewed"):
            raise FormError("reviewed", "Bekräfta att du har granskat filen innan den godkänns")
        return {"file_id": _text(form, "file_id", required=True),
                "reviewed_checksum": _text(form, "reviewed_checksum", required=True)}

    return await _submit(request, form, "approve_payout_order", build, lambda **kw: _bank(request, **kw),
                         form_key="approve", view="bank", message=lambda r: (
                             f"Bankfilen {r['file_reference']} är godkänd och lämnad till banken. Hämta filen nedan."
                             if r.get("created") else f"Bankfilen {r['file_reference']} var redan godkänd."))


@router.post(BASE + "/bankfiler/hamta")
async def download_orders(request: Request):
    """Den godkända bankfilen som JSON (Z7). Godkännandet görs om med samma summa – det ändrar inget men
    loggas – så att filen aldrig ligger i sidans HTML med omaskerade konton (Z6)."""
    form = await request.form()
    actor = operator_action(request, form)
    status = await run_in_threadpool(_status, request)
    if not _ready(status, 6):
        return await run_in_threadpool(_unavailable, request, status, "bank", 6, 409)
    data = {"file_id": clean_text(form.get("file_id")) or "", "reviewed_checksum": clean_text(form.get("reviewed_checksum")) or ""}
    try:
        result = await run_in_threadpool(service(request).execute, "approve_payout_order",
                                         OperationContext(actor=actor, reason="Hämtning av godkänd bankfil"), data)
    except ServiceError as exc:
        error = _service_error(request, exc)
        return await run_in_threadpool(lambda: _bank(request, error=error, status_code=error.status_code))
    payload = result.output.payload
    if payload.get("created"):  # filen var inte godkänd – hämtningen godkänner aldrig
        raise HTTPException(409, "Filen var inte godkänd")
    name = f"{payload['file_reference'].replace('/', '_')}.json"
    return Response(json.dumps(payload["bank_file"], ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.post(BASE + "/bankfiler/kvitton")
async def import_receipts(request: Request):
    form = await request.form()
    return await _submit(request, form, "import_payout_receipts", lambda: read_upload(form),
                         lambda **kw: _bank(request, **kw), form_key="receipts", view="bank",
                         message=lambda r: _receipt_message(r))


def _receipt_message(r: dict) -> str:
    text = (f"Kvittofilen {r['file_reference']}: {r['receipts']} kvitton, {r['new']} nya och {r['already_received']} "
            f"redan inlästa")
    cases = r.get("cases_opened") or []
    if cases:
        text += f"; {len(cases)} nya ärenden om konto ({', '.join(cases)})"
    if r.get("settlement"):
        return text + ". Utbetalningarna är bokade."
    return text + (". Inga utförda utbetalningar att boka." if r.get("new") else ". Ingenting nytt att boka.")


# --- dödsfallen -----------------------------------------------------------------------------------


@router.get(BASE + "/dodsfall")
def deaths_page(request: Request):
    return _deaths(request)


def _deaths(request: Request, *, error: ErrorView | None = None, message: str | None = None, values: dict | None = None,
            outcome: dict | None = None, status_code: int = 200):
    try:
        status = _status(request)
        if not _ready(status, VIEW_STEPS["deaths"]):
            return _unavailable(request, status, "deaths", 7, 409 if request.method == "POST" else 200)
        reported = read(request, "list_payout_parts", {"case_type": "death_report", "limit": 500}).payload
        recovery = read(request, "list_payout_parts", {"case_type": "death_recovery", "limit": 500}).payload
        ended = read(request, "list_payout_parts", {"state": "ended", "limit": 500}).payload
    except ServiceError as exc:
        return render_error(request, exc)
    return render(request, "pensions_deaths.html", _base_context(
        request, status, reported=reported, recovery=recovery,
        ended=[p for p in ended["parts"] if p["end_reason"] == "death"], error=error, message=message,
        values=values or {}, outcome=outcome, op=operation_info(request, "import_death_notices"),
    ), status_code=status_code, push_url=f"{BASE}/dodsfall" if request.method == "POST" else None)


@router.post(BASE + "/dodsfall/avisering")
async def import_notices(request: Request):
    form = await request.form()
    return await _submit(request, form, "import_death_notices", lambda: read_upload(form),
                         lambda **kw: _deaths(request, **kw), form_key="notices", view="deaths",
                         message=lambda r: (f"Aviseringen {r['file_reference']}: {r['new']} nya misstänkta besked, "
                                            f"{r['already_received']} redan inlästa och {r['unknown_persons']} okända "
                                            "personnummer. Beskeden verifieras i pensionsakten."))


# --- månadsstängningen ----------------------------------------------------------------------------


@router.get(BASE + "/manadsstangning")
def close_page(request: Request, manad: str = ""):
    return _close(request, clean_month(manad))


def _close(request: Request, month: str | None = None, *, error: ErrorView | None = None, message: str | None = None,
           values: dict | None = None, outcome: dict | None = None, status_code: int = 200):
    try:
        status = _status(request)
        if not _ready(status, VIEW_STEPS["close"]):
            return _unavailable(request, status, "close", 3, 409 if request.method == "POST" else 200)
        month = month or status["months"]["next_open"]
        review = chain = None
        review_error = None
        try:
            review = read(request, "prepare_month_close", {"month": month}).payload
        except ServiceError as exc:  # t.ex. månaden kan inte räknas än; sidan visar skälet
            review_error = describe_error(exc, service(request).rules)
        if month <= (status["months"]["last_closed"] or ""):
            chain = read(request, "get_month_close", {"month": month}).payload
    except ServiceError as exc:
        return render_error(request, exc)
    return render(request, "pensions_close.html", _base_context(
        request, status, month=month[:7], month_value=month, review=review, review_error=review_error, chain=chain,
        error=error, message=message, values=values or {}, outcome=outcome,
        op=operation_info(request, "close_policy_month"),
    ), status_code=status_code, push_url=f"{BASE}/manadsstangning?manad={month[:7]}" if request.method == "POST" else None)


@router.post(BASE + "/manadsstangning/stang")
async def close_month(request: Request):
    form = await request.form()
    month = clean_month(form.get("month"))
    if settings(request).database == "lakebase":
        operator_action(request, form)
        error = ErrorView("blocked", "Stängningen bokas inte från sidan i Lakebase",
                          "I Lakebase bokas månadsstängningen med körskriptet enligt B-050 S6, efter granskning och "
                          "Karls OK.", 409, nothing_changed=True)
        return await run_in_threadpool(lambda: _close(request, month, error=error, status_code=409))

    def build():
        return {"month": _month(form, "month"), "reviewed_checksum": _text(form, "reviewed_checksum", required=True)}

    return await _submit(request, form, "close_policy_month", build, lambda **kw: _close(request, month, **kw),
                         form_key="close", view="close", message=lambda r: (
                             f"Månaden {month[:7]} är stängd." if r.get("created") else
                             f"Månaden {month[:7]} var redan stängd med samma innehåll – ingen ny verifikation."))
