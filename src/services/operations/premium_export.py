"""Överlämning till månadsjournalen (paket A steg 6, B-046, P1-PREMIE-001 §4.7, PA7).

`export_premium_month` gör en premieperiods mottagna premier till källpaketet som
`open_premium_month` och `receive_premium_payment` redan tar emot (P6-MANAD-001 §4.1).
Operationen läser och skriver ingenting; innehållet byggs i `services.premium_month_export`.
Handläggaren granskar paketets kontrollsumma och öppnar sedan journalen med den, som för
det syntetiska försöket. Kapitalursprung och garantidelar skapas av journalen, inte här.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field

from services.contract import OperationContext, OperationKind, operation
from services.errors import AccessDeniedError, BlockedError
from services.operations.actuarial_analysis import JsonResult
from services.premium_month_export import ExportError, export_inputs
from services.premium_month_inputs import HASH, KEY, Strict


class PremiumMonthExport(Strict):
    period_month: date = Field(description="Premieperioden, ÅÅÅÅ-MM-01; i dag 2026-10")
    scenario_id: str = Field(pattern=KEY, description="Journalens ID, t.ex. paket-a-2026-10-v1")
    expected_opening_checksum: str = Field(pattern=HASH, description="Granskad kontrollsumma för IB per 2026-10-31")


@operation(
    name="export_premium_month",
    description=(
        "Gör premieperiodens mottagna premier ur paket A till månadsjournalens källpaket: debetfakturor som "
        "InvoiceInput och ett kvitto per bankhändelse och faktura med allokeringarnas belopp (PA6, PA7). "
        "Avstämningskontot följer inte med. Prövar att journalen fördelar exakt som paket A. Skriver ingenting."
    ),
    kind=OperationKind.READ,
    pii=True,
    rules=["PR-ITP1-018"],
)
def export_premium_month(ctx: OperationContext, data: PremiumMonthExport) -> JsonResult:
    if ctx.actor.is_agent:
        raise AccessDeniedError("Källpaketet till månadsjournalen tas fram av människa eller betrodd systemkod",
                                operation="export_premium_month", actor_id=ctx.actor.id)
    session = ctx.require_session()
    try:
        package, summary = export_inputs(session, data.scenario_id, data.expected_opening_checksum,
                                         data.period_month.replace(day=1))
    except ExportError as exc:
        raise BlockedError(str(exc)) from exc
    except ValueError as exc:
        raise BlockedError(f"Källpaketet godtas inte av månadsjournalen: {exc}") from exc
    return JsonResult(payload={"summary": summary, "checksum": package.checksum,
                               "inputs_json": package.model_dump_json()})
