"""Sök och visa en försäkrad: översikt, löneunderlag och premiehistorik (S1).

Varje sidvisning är läsoperationer i tjänstelagret – `get_insured_overview`,
`get_salary_reports`, `get_premium_history` – och loggas därför som läsning
av personuppgifter (vem tittade på vem).
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from services import ServiceError
from web.handler import read, render, render_error
from web.presenters import POLICY_STATES, ErrorView, clean_month

router = APIRouter()
log = logging.getLogger(__name__)

_PNR = re.compile(r"^(\d{8})-?(\d{4})$")
_POLICY = re.compile(r"^AL-?\d+$", re.IGNORECASE)


def redirect(request: Request, url: str) -> Response:
    """Vanlig omdirigering – eller HX-Location när HTMX hämtar sidan (då hamnar rätt adress i historiken)."""
    if request.headers.get("HX-Request"):
        return Response(status_code=200, headers={"HX-Location": url})
    return RedirectResponse(url, status_code=303)


def parse_query(query: str) -> tuple[str, str]:
    """Exakta identifierare går till översikten; övrig sökning till beståndet."""
    text = re.sub(r"\s", "", query or "")
    if match := _PNR.match(text):
        return "pnr", match.group(1) + match.group(2)
    if _POLICY.match(text):
        digits = text.upper().removeprefix("AL").lstrip("-")
        return "policy", f"AL-{digits}"
    if re.fullmatch(r"\d{6}-?\d{4}", text):
        return "error", "Ange personnumret med tolv siffror (ÅÅÅÅMMDD-NNNN)."
    return "list", " ".join(query.split())


@router.get("/")
def start(request: Request):
    return render(request, "search.html", {"query": ""})


@router.get("/sok")
def search(request: Request, q: str = ""):
    kind, value = parse_query(q)
    if kind == "pnr":
        return redirect(request, f"/forsakrade/{value}")
    if kind == "policy":
        return redirect(request, f"/forsakringar/{value}")
    if kind == "list" and value:
        return redirect(request, "/forsakrade?" + urlencode({"q": value}))
    return render(request, "search.html", {"query": q, "message": value if q else None},
                  status_code=422 if q else 200)


@router.get("/forsakrade")
def insured_list(
    request: Request, q: str = "", employer_org_number: str = "", policy_state: str = "",
    page: int = 1, page_size: int = 25,
):
    filters = {"q": q, "employer_org_number": employer_org_number, "policy_state": policy_state, "page_size": page_size}
    context = {"filters": filters, "states": {**POLICY_STATES, "no_policy": "Utan försäkring"}}
    try:
        result = read(request, "list_insured_persons", {**filters, "page": page})
        employers = read(request, "list_employers", {"status": None})
    except ServiceError as exc:
        return render_error(request, exc, "insured_list.html", context)
    except Exception as exc:  # noqa: BLE001 – visa aldrig databasens anslutningsdetaljer i beståndsvyn
        log.warning("Beståndsläsningen misslyckades (%s)", type(exc).__name__)
        error = ErrorView("error", "Beståndet kunde inte läsas",
                          "Kontrollera anslutningen till vald datakälla och försök igen.", 500, nothing_changed=False)
        return render(request, "insured_list.html", {**context, "error": error}, status_code=500)

    def page_url(number: int) -> str:
        return "/forsakrade?" + urlencode({**{key: value for key, value in filters.items() if value != ""}, "page": number})

    return render(request, "insured_list.html", {
        **context, "result": result, "employers": employers.employers,
        "previous_url": page_url(result.page - 1) if result.page > 1 else None,
        "next_url": page_url(result.page + 1) if result.page < result.page_count else None,
        "first_row": (result.page - 1) * result.page_size + 1 if result.total else 0,
        "last_row": min(result.page * result.page_size, result.total),
    })


@router.get("/forsakrade/{pnr}")
def insured_overview(request: Request, pnr: str):
    try:
        overview = read(request, "get_insured_overview", {"personal_id_number": pnr})
    except ServiceError as exc:
        return render_error(request, exc, "search.html", {"query": pnr})
    return render(request, "insured_overview.html", {"o": overview, "tab": "overview"})


@router.get("/forsakringar/{policy_number}")
def policy_overview(request: Request, policy_number: str):
    try:
        overview = read(request, "get_insured_overview", {"policy_number": policy_number})
    except ServiceError as exc:
        return render_error(request, exc, "search.html", {"query": policy_number})
    return render(request, "insured_overview.html",
                  {"o": overview, "tab": "overview", "highlight": policy_number})


@router.get("/forsakrade/{pnr}/loneunderlag")
def salary_reports(request: Request, pnr: str):
    try:
        overview = read(request, "get_insured_overview", {"personal_id_number": pnr})
        reports = read(request, "get_salary_reports", {"personal_id_number": pnr})
    except ServiceError as exc:
        return render_error(request, exc, "search.html", {"query": pnr})
    months: dict = {}
    for row in reports.reports:
        months.setdefault((row.period_month, row.employer_org_number), []).append(row)
    groups = [
        {"month": key[0], "employer": key[1], "current": next(r for r in rows if r.current),
         "history": [r for r in reversed(rows) if not r.current]}
        for key, rows in sorted(months.items(), reverse=True)
    ]
    return render(request, "insured_salary.html", {"o": overview, "tab": "salary", "groups": groups})


@router.get("/forsakringar/{policy_number}/premier")
def premium_history(request: Request, policy_number: str, fran: str = "", till: str = ""):
    query = {"policy_number": policy_number, "from_month": clean_month(fran), "to_month": clean_month(till)}
    try:
        overview = read(request, "get_insured_overview", {"policy_number": policy_number})
        history = read(request, "get_premium_history", {k: v for k, v in query.items() if v})
    except ServiceError as exc:
        return render_error(request, exc, "search.html", {"query": policy_number})
    return render(request, "insured_premiums.html", {
        "o": overview, "tab": f"premiums:{policy_number}", "history": history,
        "policy_number": policy_number, "fran": fran, "till": till,
    })
