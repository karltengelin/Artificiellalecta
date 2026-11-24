"""Skattestatus, konto, bankuppdrag och bankkvitton (paket B steg 6, B-054, P1-PENSION-001 §8.3).

Sex operationer, alla `HUMAN_ONLY` (PB12, Karls val X12 2026-11-24). Agenter nekas även i operationen, och
de skrivande nekar också systemaktören:

- `register_tax_status` registrerar en ny version av personens skattestatus för ett år: sidoinkomst (minst
  30 %, frivilligt högre gäller från mottagandet + 14 dagar), huvudinkomst med tabell och kolumn,
  individuellt beslut eller SINK med beslutsreferens (PR-ITP1-026, X5).
- `register_payout_account` registrerar en ny version av utbetalningskontot med verifiering (X6).
- `create_payout_orders` skapar bankfilen för en betalningsdag med skatt per uppdrag; blockerade personer
  får ärende och skulden står kvar (X2, X3, X7).
- `approve_payout_order` godkänner bankfilen hashbundet och lämnar den till banken – den externa handlingen.
- `import_payout_receipts` läser bankens kvittofil idempotent och bokar utförda och återkomna betalningar
  som verifikationen `payout_settlement` (X8, X9).
- `list_payout_orders` visar bankfilerna, uppdragen med maskerade konton och anspråkens betalningsläge.

Logiken ligger i `services.payout_orders`.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from models.case import CASE_CHANNELS
from services import payout_orders as po
from services import pension_claims as pc
from services.contract import OperationContext, OperationKind, operation
from services.errors import AccessDeniedError, BlockedError, ConflictError
from services.operations import common
from services.operations.actuarial_analysis import JsonResult
from services.operations.capital_ledger import _require_journal
from services.premium_month_inputs import HASH, Strict

RULES = ["PR-ITP1-026"]
Channel = Literal[CASE_CHANNELS]  # type: ignore[valid-type]
_RECEIPT_ID = r"^[A-Za-z0-9._:/-]{1,64}$"


def _human(ctx: OperationContext, name: str) -> None:
    if ctx.actor.type != "human":
        raise AccessDeniedError("Skatt, konto och bankuppdrag hanteras av en människa (PB12, X12)", operation=name,
                                actor_id=ctx.actor.id)


def _no_agent(ctx: OperationContext, name: str) -> None:
    if ctx.actor.is_agent:
        raise AccessDeniedError("Bankuppdragen läses av människa eller betrodd systemkod", operation=name,
                                actor_id=ctx.actor.id)


def _session(ctx: OperationContext):
    session = ctx.require_session()
    _require_journal(session)
    if not pc.claims_present(session):
        raise BlockedError("Månadsrätterna är inte införda i vald databas – migrate_pension_claims.py först")
    if not po.orders_present(session):
        raise BlockedError("Bankuppdragen är inte införda i vald databas – migrate_payout_orders.py först")
    return session


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except po.OrderConflict as exc:
        raise ConflictError(str(exc)) from exc
    except (po.OrderServiceError, pc.ClaimServiceError) as exc:
        raise BlockedError(str(exc)) from exc


# --- indata ---------------------------------------------------------------------------------------


class PersonRef(Strict):
    personal_id_number: str = Field(pattern=r"^\d{12}$", description="Den försäkrade, 12 siffror")


class TaxStatusInput(PersonRef):
    tax_year: int = Field(ge=2026, le=2100, description="Inkomståret statusen gäller")
    kind: Literal["side_income", "main_income", "individual_decision", "sink"] = Field(
        description="side_income: sidoinkomst (30 % eller frivilligt högre); main_income: huvudinkomst med "
                    "skattetabell; individual_decision: Skatteverkets beslut; sink: SINK-beslut")
    rate: Decimal | None = Field(default=None, ge=0, le=1, max_digits=7, decimal_places=4,
                                 description="Satsen som andel, t.ex. 0.30")
    fixed_amount_sek: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2,
                                             description="Fast avdrag per utbetalning enligt beslut")
    table_number: int | None = Field(default=None, ge=29, le=42, description="Skattetabell (huvudinkomst)")
    table_column: int | None = Field(default=None, ge=1, le=6, description="Tabellens kolumn (huvudinkomst)")
    raised_deduction: bool = Field(default=False, description="Personen har begärt förhöjt avdrag")
    decision_ref: str | None = Field(default=None, min_length=3, max_length=100,
                                     description="Skatteverkets beslut (krävs för SINK och individuellt beslut)")
    received_date: date = Field(description="Dagen uppgiften togs emot")
    channel: Channel = Field(description="Kanalen uppgiften kom in genom")


class AccountInput(PersonRef):
    clearing_number: str = Field(pattern=r"^\d{4,5}$", description="Clearingnumret")
    account_number: str = Field(pattern=r"^\d{1,20}$", description="Kontonumret")
    bank_name: str = Field(min_length=2, max_length=60, description="Banken")
    verified: bool = Field(description="Kontot är verifierat mot kontoinnehavaren")
    verification_method: str | None = Field(default=None, min_length=3, max_length=40,
                                            description="Hur kontot verifierats, t.ex. kontouppslag eller BankID")
    verification_ref: str | None = Field(default=None, min_length=3, max_length=100,
                                         description="Referens till verifieringen")
    received_date: date = Field(description="Dagen uppgiften togs emot")
    channel: Channel = Field(description="Kanalen uppgiften kom in genom")


class CreateInput(Strict):
    payment_day: date = Field(description="Betalningsdagen: anspråk med betalningsdag senast denna dag tas med")


class ApproveInput(Strict):
    file_id: str = Field(min_length=36, max_length=36, description="Bankfilens id ur create_payout_orders")
    reviewed_checksum: str = Field(pattern=HASH, description="Bankfilens kontrollsumma som granskats")


class ReceiptInput(BaseModel):
    receipt_id: str = Field(pattern=_RECEIPT_ID, description="Bankens kvitto-id")
    reference: str = Field(min_length=1, max_length=35, description="Uppdragets referens")
    outcome: Literal["executed", "rejected", "returned", "unknown"]
    bank_date: date = Field(description="Bankdagen för utfallet")
    reason_code: str | None = Field(default=None, max_length=20, description="Bankens orsakskod")


class ReceiptFileInput(Strict):
    source_system: str = Field(default="bank-sim-payout", pattern=r"^[a-z0-9-]{1,40}$",
                               description="Bankens källsystem")
    file_reference: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9._/-]+$")
    checksum: str = Field(pattern=HASH, description="SHA-256 över filens innehåll (receipt_file_checksum)")
    receipts: list[ReceiptInput] = Field(min_length=1, max_length=10000)


class ListInput(Strict):
    file_id: str | None = Field(default=None, min_length=36, max_length=36, description="En viss bankfil")
    month: date | None = Field(default=None, description="Anspråkens rättighetsmånad, ÅÅÅÅ-MM-01")


# --- operationer ----------------------------------------------------------------------------------


@operation(
    name="register_tax_status",
    description="Registrerar en ny version av personens skattestatus för ett år: sidoinkomst (minst 30 %), "
                "huvudinkomst med skattetabell och kolumn, individuellt beslut eller SINK med beslutsreferens. "
                "Saknad status antas aldrig; samma uppgift igen ger ingen ny version.",
    kind=OperationKind.WRITE,
    rules=RULES,
    pii=True,
)
def register_tax_status(ctx: OperationContext, data: TaxStatusInput) -> JsonResult:
    _human(ctx, "register_tax_status")
    session = _session(ctx)
    person = common.lock_person(session, data.personal_id_number)
    row, created = _call(po.register_tax_status, session, person, data.tax_year, data.kind, rate=data.rate,
                         fixed_amount=data.fixed_amount_sek, table_number=data.table_number,
                         table_column=data.table_column, raised_deduction=data.raised_deduction,
                         decision_ref=data.decision_ref, received=data.received_date, channel=data.channel,
                         actor=ctx.actor.id)
    return JsonResult(payload={"tax_status_id": str(row.id), "created": created, "version": row.version,
                               "tax_year": row.tax_year, "kind": row.kind,
                               "rate": str(row.rate) if row.rate is not None else None,
                               "valid_from": row.valid_from.isoformat(), "checksum": row.checksum})


@operation(
    name="register_payout_account",
    description="Registrerar en ny version av personens utbetalningskonto med verifieringssätt och referens. "
                "Ett nytt verifierat konto stänger öppna utbetalningshinder; kontonumret visas maskerat.",
    kind=OperationKind.WRITE,
    rules=RULES,
    pii=True,
)
def register_payout_account(ctx: OperationContext, data: AccountInput) -> JsonResult:
    _human(ctx, "register_payout_account")
    session = _session(ctx)
    person = common.lock_person(session, data.personal_id_number)
    row, created = _call(po.register_account, session, person, data.clearing_number, data.account_number,
                         data.bank_name, verified=data.verified, method=data.verification_method,
                         reference=data.verification_ref, received=data.received_date, channel=data.channel,
                         actor=ctx.actor.id)
    return JsonResult(payload={"created": created, **po.account_view(row)})


@operation(
    name="create_payout_orders",
    description="Skapar bankfilen för betalningsdagen: helt finansierade anspråk utan öppen eller betald rad, ett "
                "uppdrag per person med preliminärskatt på summan. Personer utan verifierat konto eller "
                "skattestatus blockeras med ärende och skulden står kvar. En ej godkänd fil ersätts när "
                "underlaget ändrats; samma underlag ger samma fil.",
    kind=OperationKind.WRITE,
    rules=RULES,
    pii=True,
)
def create_payout_orders(ctx: OperationContext, data: CreateInput) -> JsonResult:
    _human(ctx, "create_payout_orders")
    session = _session(ctx)
    file, summary, created = _call(po.create_file, session, data.payment_day, common.today(), ctx.actor.id)
    view = po.files_view(session, file_id=file.id)[0] if file else None
    return JsonResult(payload={"created": created, "file": view, "summary": summary,
                               "note": "Granska filen och godkänn den med approve_payout_order och filens "
                                       "kontrollsumma." if view and view["status"] == "prepared" else None})


@operation(
    name="approve_payout_order",
    description="Godkänner bankfilen med dess kontrollsumma och lämnar den till banken. Ändrat underlag sedan "
                "filen skapades (konto, skatt, anspråk eller utförandedag) ger konflikt. En godkänd fil ändras "
                "aldrig.",
    kind=OperationKind.EXTERNAL,
    rules=RULES,
    pii=True,
)
def approve_payout_order(ctx: OperationContext, data: ApproveInput) -> JsonResult:
    _human(ctx, "approve_payout_order")
    session = _session(ctx)
    result = _call(po.approve_file, session, uuid.UUID(data.file_id), data.reviewed_checksum, common.today(),
                   ctx.actor.id)
    return JsonResult(payload=result)


@operation(
    name="import_payout_receipts",
    description="Läser bankens kvittofil: utfört, avvisat, återkommet eller okänt per uppdrag. Samma kvitto igen "
                "ger ingen effekt; samma kvitto-id med annat innehåll ger konflikt. Utförda och återkomna "
                "betalningar bokas som en egen verifikation (skuld, skatteskuld). Avvisat och återkommet ger "
                "ärende om nytt konto.",
    kind=OperationKind.WRITE,
    rules=RULES,
    pii=True,
)
def import_payout_receipts(ctx: OperationContext, data: ReceiptFileInput) -> JsonResult:
    _human(ctx, "import_payout_receipts")
    session = _session(ctx)
    receipts = [r.model_dump() for r in data.receipts]
    result = _call(po.import_receipts, session, data.source_system, data.file_reference, receipts, data.checksum,
                   common.today(), ctx.actor.id)
    return JsonResult(payload=result)


@operation(
    name="list_payout_orders",
    description="Visar bankfilerna med uppdrag, skatt, maskerade konton och bankens utfall, och anspråkens "
                "betalningsläge (ej finansierat, finansierat, i bankfil, skickat, betalt, avvisat, återkommet).",
    kind=OperationKind.READ,
    rules=RULES,
    pii=True,
)
def list_payout_orders(ctx: OperationContext, data: ListInput) -> JsonResult:
    _no_agent(ctx, "list_payout_orders")
    session = _session(ctx)
    files = po.files_view(session, file_id=uuid.UUID(data.file_id) if data.file_id else None)
    claims = po.claims_payment_view(session, data.month) if data.file_id is None else []
    return JsonResult(payload={"files": files, "claims": claims, "count": len(files)})
