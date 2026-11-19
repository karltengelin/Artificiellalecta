"""Månadsstängning för sparandet (paket B steg 3, B-047 punkt 3, P1-PENSION-001 §7).

Tre operationer, alla `HUMAN_ONLY` (PB12, Karls val S7) – agenter nekas även i operationen:

- `prepare_month_close` räknar månadens stängning, eller rättelsen av en stängd månad, utan att skriva
  och ger en sammanställning med granskningssumma.
- `close_policy_month` bokar stängningen eller rättelsen med den granskade summan, i en transaktion.
  Bara en människa i steg 3; även systemaktören nekas. Samma innehåll igen ger ingen ny effekt, och
  ändrat underlag ger konflikt.
- `get_month_close` visar en stängd månads versioner med sammanställning, utan rader.

Logiken ligger i `services.month_close`.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field

from services import month_close as mc
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, ConflictError
from services.operations import common
from services.operations.actuarial_analysis import JsonResult
from services.operations.capital_ledger import _human, _no_agent, _require_journal
from services.premium_month_inputs import HASH, Strict

RULES = ["PR-ITP1-008", "PR-ITP1-020", "PR-ITP1-021", "PR-ITP1-022", "PR-ITP1-023"]


class MonthInput(Strict):
    month: date = Field(description="Pensionsmånaden, ÅÅÅÅ-MM-01; tidigast 2026-11")


class CloseInput(MonthInput):
    reviewed_checksum: str = Field(pattern=HASH, description="review_checksum ur den granskade prepare_month_close")


@operation(
    name="prepare_month_close",
    description="Räknar månadsstängningen för sparandet (PR-ITP1-020 steg 1–4 och 8) för hela kollektivet utan att "
                "skriva: öppningskapital, avkastning enligt antagen AVK, kapitalavgift, skattebelastning, månadens "
                "premier ur paket A och kontroller, med granskningssumma. För en stängd månad: oförändrad, eller "
                "en rättelse med motposter.",
    kind=OperationKind.READ,
    rules=RULES,
)
def prepare_month_close(ctx: OperationContext, data: MonthInput) -> JsonResult:
    _no_agent(ctx, "prepare_month_close")
    session = ctx.require_session()
    _require_journal(session)
    try:
        plan = mc.plan_month(session, data.month, common.today())
    except mc.CloseError as exc:
        raise BlockedError(str(exc)) from exc
    return JsonResult(payload=plan.summary())


@operation(
    name="close_policy_month",
    description="Bokar månadsstängningen eller rättelsen med den granskade summan: avkastning, avgift och "
                "skattebelastning per kapitalspår, månadens premier med garantidelar och kontrollposter, i en "
                "transaktion. Samma innehåll igen ger ingen ny effekt.",
    kind=OperationKind.WRITE,
    rules=RULES,
)
def close_policy_month(ctx: OperationContext, data: CloseInput) -> JsonResult:
    _human(ctx, "close_policy_month", "Månadsstängningen")
    session = ctx.require_session()
    _require_journal(session)
    try:
        batch, created = mc.apply_month(session, data.month, ctx.actor.id, data.reviewed_checksum, common.today())
    except mc.CloseConflict as exc:
        raise ConflictError(str(exc)) from exc
    except mc.CloseError as exc:
        raise BlockedError(str(exc)) from exc
    return JsonResult(payload={**batch.content, "batch_id": str(batch.id), "review_checksum": batch.checksum,
                               "created": created})


@operation(
    name="get_month_close",
    description="Visar en stängd månads gällande version och versionskedja (stängning och rättelser) med "
                "sammanställning och kontroller, utan individrader.",
    kind=OperationKind.READ,
    rules=RULES,
)
def get_month_close(ctx: OperationContext, data: MonthInput) -> JsonResult:
    _no_agent(ctx, "get_month_close")
    session = ctx.require_session()
    _require_journal(session)
    try:
        return JsonResult(payload=mc.month_view(session, data.month))
    except mc.CloseError as exc:
        raise BlockedError(str(exc)) from exc
