"""Skrivskyddade historiksidor och ingångar från äldre bokmärken."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from starlette.convertors import Convertor, register_url_convertor

from agents.deliveries import DeliveryError
from agents.gateways import GatewayError
from agents.mission_archive import TITLES
from services.errors import NotFoundError
from web.handler import render
from web.operator_auth import operator_actor
from web.operator_forms import HEADERS

router = APIRouter()
BASE = "/central/uppdragsarkiv"


class ArchivedId(Convertor[str]):
    regex = r"FLOW-\d{6}"

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return value


register_url_convertor("archived_id", ArchivedId())


def archive(request):
    operator_actor(request)
    value = request.app.state.mission_archive
    if value is None:
        raise HTTPException(404, "Uppdragsarkivet är inte tillgängligt")
    return value


def page(request, **context):
    response = render(request, "mission_archive.html", {"base": BASE, "titles": TITLES,
                       "operator_page": True, **context})
    response.headers.update(HEADERS)
    return response


@router.get(BASE)
@router.get("/floden", include_in_schema=False)
@router.get("/team/aktuarie/rapporter", include_in_schema=False)
@router.get("/team/aktuarie/uppdrag", include_in_schema=False)
def listing(request: Request):
    return page(request, records=archive(request).list())


@router.get(BASE + "/{ident}")
@router.get("/floden/{ident:archived_id}", include_in_schema=False)
@router.get("/central/fragor/{ident:archived_id}", include_in_schema=False)
@router.get("/team/aktuarie/uppdrag/{ident:archived_id}", include_in_schema=False)
@router.get("/team/aktuarie/rapporter/{ident:archived_id}", include_in_schema=False)
@router.get("/team/aktuarie/{ident:archived_id}", include_in_schema=False)
def detail(request: Request, ident: str):
    store = archive(request)
    try:
        record, steps, decisions = store.get(ident)
    except NotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    return page(request, record=record, steps=steps, decisions=decisions, receipt=store.delivery_receipt(steps))


@router.get(BASE + "/{ident}/leverans/{version}/{name}")
@router.get("/central/fragor/{ident:archived_id}/leverans/{version}/{name}", include_in_schema=False)
@router.get("/team/aktuarie/uppdrag/{ident:archived_id}/leverans/{version}/{name}", include_in_schema=False)
@router.get("/team/aktuarie/rapporter/{ident:archived_id}/leverans/{version}/{name}", include_in_schema=False)
@router.get("/team/aktuarie/{ident:archived_id}/leverans/{version}/{name}", include_in_schema=False)
def delivery(request: Request, ident: str, version: int, name: str):
    try:
        data = archive(request).delivery(ident, version, name)
    except NotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    except DeliveryError:
        raise HTTPException(409, "Rapportfilen saknas eller avviker från sparad kontrollsumma") from None
    return Response(data, media_type="application/pdf" if name == "rapport.pdf" else "text/markdown",
                    headers={**HEADERS, "Content-Disposition": f'attachment; filename="{name}"'})


@router.get(BASE + "/{ident}/steg/{key}/utkast/{name}")
@router.get("/floden/{ident:archived_id}/steg/{key}/utkast/{name}", include_in_schema=False)
def draft(request: Request, ident: str, key: str, name: str):
    try:
        data = archive(request).draft(ident, key, name)
    except (NotFoundError, GatewayError, FileNotFoundError):
        raise HTTPException(404, "Utkastet finns inte i arkivet") from None
    return Response(data, media_type="text/markdown", headers=HEADERS)


@router.get(BASE + "/{ident}/steg/{key}/journal")
@router.get("/floden/{ident:archived_id}/steg/{key}/journal", include_in_schema=False)
def trace(request: Request, ident: str, key: str):
    try:
        value = archive(request).trace(ident, key)
    except NotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    response = render(request, "company_trace.html", {"base": BASE, "trace": value,
                      "ident": ident, "statuses": {}, "operator_page": True})
    response.headers.update(HEADERS)
    return response
