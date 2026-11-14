"""Operativ kapital- och garantijournal (paket B steg 2, B-047 punkt 4, P1-PENSION-001 §6).

Tre operationer, alla `HUMAN_ONLY` (PB12) – agenter nekas även i operationen:

- `preview_ledger_opening` granskar övergången från S-04 per 2026-10-31 och ger en granskningssumma.
  Skriver ingenting.
- `open_capital_ledger` bokar det ingående läget med den granskade summan. Bara en människa; samma
  innehåll igen ger ingen ny effekt, och ändrat underlag ger konflikt.
- `preview_ledger_premiums` visar månadens premier ur paket A:s allokeringar som journalens tillskott
  (PR-ITP1-020 steg 4). Skriver ingenting; månadsstängningen i steg 3 bokar dem.

Logiken ligger i `services.capital_ledger` och `services.ledger_premiums`.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field

from services import capital_ledger as cl
from services.contract import OperationContext, OperationKind, operation
from services.errors import AccessDeniedError, BlockedError, ConflictError
from services.ledger_premiums import IntakeError, premium_intake
from services.operations.actuarial_analysis import JsonResult
from services.premium_month_inputs import HASH, Strict


class OpeningPreview(Strict):
    expected_extract_checksum: str | None = Field(
        default=None, pattern=HASH,
        description="Väntad kontrollsumma för S-04 per 2026-10-31, t.ex. den P6-MANAD-001 frös; avvikelse stoppar")


class OpenLedger(OpeningPreview):
    reviewed_checksum: str = Field(pattern=HASH, description="review_checksum ur den granskade preview_ledger_opening")


class PremiumPreview(Strict):
    month: date = Field(description="Journalmånaden, ÅÅÅÅ-MM-01; tidigast 2026-11")


def _human(ctx: OperationContext, name: str, what: str) -> None:
    if ctx.actor.type != "human":
        raise AccessDeniedError(f"{what} görs av en människa", operation=name, actor_id=ctx.actor.id)


def _no_agent(ctx: OperationContext, name: str) -> None:
    if ctx.actor.is_agent:
        raise AccessDeniedError("Kapitaljournalen läses av människa eller betrodd systemkod", operation=name,
                                actor_id=ctx.actor.id)


def _require_journal(session) -> None:
    if not cl.journal_present(session):
        raise BlockedError("Kapitaljournalen är inte införd i vald databas – migrate_capital_ledger.py först")


@operation(
    name="preview_ledger_opening",
    description="Granskar övergången från S-04 per 2026-10-31 till den operativa kapital- och garantijournalen: "
                "C och G per försäkring och totalt, garantidelar och kapitalspår per uttagsdel, kontroller och "
                "granskningssumma. Skriver ingenting.",
    kind=OperationKind.READ,
    rules=["PR-ITP1-008", "PR-ITP1-020"],
)
def preview_ledger_opening(ctx: OperationContext, data: OpeningPreview) -> JsonResult:
    _no_agent(ctx, "preview_ledger_opening")
    session = ctx.require_session()
    _require_journal(session)
    existing = cl.opening_batch(session)
    if existing is not None:
        return JsonResult(payload={**existing.content, "review_checksum": existing.checksum, "passed": True,
                                   "problems": [], "opened": True})
    try:
        plan = cl.plan_opening(session, data.expected_extract_checksum)
    except cl.LedgerError as exc:
        raise BlockedError(str(exc)) from exc
    return JsonResult(payload={**plan.summary(), "opened": False})


@operation(
    name="open_capital_ledger",
    description="Bokar journalens ingående läge från S-04 per 2026-10-31 med den granskade summan: en garantidel "
                "per premierad och en IB-post per kapitalspår på uttagsdel 1, märkta reconstructed_s04. Samma "
                "innehåll igen ger ingen ny effekt.",
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-008", "PR-ITP1-020"],
)
def open_capital_ledger(ctx: OperationContext, data: OpenLedger) -> JsonResult:
    _human(ctx, "open_capital_ledger", "Övergången till kapitaljournalen")
    session = ctx.require_session()
    _require_journal(session)
    try:
        batch, created = cl.apply_opening(session, ctx.actor.id, data.reviewed_checksum,
                                          data.expected_extract_checksum)
    except cl.LedgerConflict as exc:
        raise ConflictError(str(exc)) from exc
    except cl.LedgerError as exc:
        raise BlockedError(str(exc)) from exc
    return JsonResult(payload={**batch.content, "batch_id": str(batch.id), "review_checksum": batch.checksum,
                               "created": created})


@operation(
    name="preview_ledger_premiums",
    description="Visar månadens mottagna premier ur paket A:s allokeringar som journalens tillskott: garantidel och "
                "kapitalpost per allokering och uttagsdel, summa per arbetsgivare och avstämningskontot som inte "
                "följer med. Skriver ingenting.",
    kind=OperationKind.READ,
    pii=True,
    rules=["PR-ITP1-008", "PR-ITP1-018", "PR-ITP1-020"],
)
def preview_ledger_premiums(ctx: OperationContext, data: PremiumPreview) -> JsonResult:
    _no_agent(ctx, "preview_ledger_premiums")
    session = ctx.require_session()
    _require_journal(session)
    try:
        intake = premium_intake(session, data.month)
    except IntakeError as exc:
        raise BlockedError(str(exc)) from exc
    return JsonResult(payload={**intake.summary, "checksum": intake.checksum,
                               "additions": [a.plain() for a in intake.additions]})
