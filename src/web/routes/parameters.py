"""Produktparametrar för premieberäkningen (Fas 3c 3c-P2, B-035).

- `/parametrar` – `get_product_parameters`: gällande värden och alla versioner
- `/parametrar/ny` (POST) – `schedule_product_parameter_change`
- `/parametrar/aterkalla` (POST) – `withdraw_product_parameter_change`

Handläggaren utför ändringarna direkt (B-017). Agenter kan bara föreslå en ny version;
förslaget avgörs i `/godkannanden`.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from services import ServiceError
from web.handler import check_csrf, read, render, render_error, service
from web.presenters import clean_decimal, clean_text, describe_error
from web.routes.changes import execute, operation_info

router = APIRouter()

#: Parametrarna i visningsordning: namn, regel och hjälptext för värdet
PARAMETERS = {
    "premium_age_start": ("Premieålder från", "år", "Hela år – premie från månaden personen fyller åldern"),
    "premium_age_end": ("Premieålder till", "år", "Hela år – premie t.o.m. månaden före personen fyller åldern"),
    "premium_rate_low": ("Premiesats under brytpunkten", "%", "Andel, t.ex. 0,045 för 4,5 %"),
    "premium_rate_high": ("Premiesats över brytpunkten", "%", "Andel, t.ex. 0,30 för 30 %"),
    "premium_breakpoint_low_ibb": ("Brytpunkt", "IBB", "Antal inkomstbasbelopp per år, t.ex. 7,5"),
    "premium_breakpoint_high_ibb": ("Lönetak", "IBB", "Antal inkomstbasbelopp per år, t.ex. 30"),
}
STATE_PILLS = {"gällande": "approved", "kommande": "pending", "upphörd": "", "återkallad": "rejected"}


def display(key: str, value: Decimal) -> str:
    """66 → '66 år', 0.045 → '4,5 %', 7.5 → '7,5 IBB'."""
    unit = PARAMETERS[key][1]
    if unit == "%":
        number = (value * 100).normalize()
        number = number.quantize(Decimal(1)) if number == number.to_integral_value() else number
    else:
        number = value
    return f"{str(number).replace('.', ',')} {unit}"


def _month_first(raw: str | None) -> str | None:
    """'2027-01' (månadsfält) eller '2027-01-01' → '2027-01-01'."""
    text = clean_text(raw)
    return f"{text}-01" if text and len(text) == 7 else text


@router.get("/parametrar")
def parameters_page(request: Request):
    return _page(request)


@router.post("/parametrar/ny")
async def schedule_submit(request: Request):
    form = await request.form()
    check_csrf(request, form)
    values = {key: str(value) for key, value in form.items() if key != "csrf_token"}
    data = {
        "key": clean_text(values.get("key")),
        "value": clean_decimal(values.get("value")),
        "valid_from": _month_first(values.get("valid_from")),
        "rule_version": clean_text(values.get("rule_version")),
        "source_ref": clean_text(values.get("source_ref")),
        "decision_ref": clean_text(values.get("decision_ref")),
    }
    try:
        result = await execute(request, "schedule_product_parameter_change", data, clean_text(values.get("reason")))
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        return await run_in_threadpool(_page, request, None, values, error, error.status_code)
    out = result.output
    message = (
        f"{PARAMETERS[out.key][0]} blir {display(out.key, out.value)} från {out.valid_from} "
        f"({out.rule_id} v{out.rule_version}). Föregående version gäller till och med {out.previous_valid_to}."
    )
    return await run_in_threadpool(_page, request, message)


@router.post("/parametrar/aterkalla")
async def withdraw_submit(request: Request):
    form = await request.form()
    check_csrf(request, form)
    data = {"key": clean_text(form.get("key")), "valid_from": clean_text(form.get("valid_from"))}
    try:
        result = await execute(request, "withdraw_product_parameter_change", data, clean_text(form.get("reason")))
    except ServiceError as exc:
        error = describe_error(exc, service(request).rules, write=True)
        return await run_in_threadpool(_page, request, None, {}, error, error.status_code)
    out = result.output
    message = f"Versionen av {PARAMETERS[out.key][0].lower()} från {out.valid_from} är återkallad."
    if out.previous_value is not None:
        message += f" {display(out.key, out.previous_value)} gäller vidare tills vidare."
    return await run_in_threadpool(_page, request, message)


def _page(request: Request, message: str | None = None, values: dict | None = None, error=None, status_code: int = 200):
    try:
        listing = read(request, "get_product_parameters", {})  # dagens värden; operationen sätter dagen
    except ServiceError as exc:
        return render_error(request, exc)
    by_key = {key: [v for v in listing.versions if v.key == key] for key in PARAMETERS}
    return render(request, "parameters.html", {
        "listing": listing, "by_key": by_key, "parameters": PARAMETERS, "display": display,
        "state_pills": STATE_PILLS, "message": message, "values": values or {}, "error": error,
        "op": operation_info(request, "schedule_product_parameter_change"),
        "withdraw_op": operation_info(request, "withdraw_product_parameter_change"),
    }, status_code=status_code, push_url="/parametrar" if request.method == "POST" else None)
