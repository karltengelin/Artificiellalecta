"""Inbetalningar, matchning och avstämningskonto (paket A steg 4, B-046, P1-PREMIE-001 §4.6–4.7).

`import_bank_file` läser en bankfil med inbetalningar. Varje händelse sparas en gång
per källsystem och bankens händelse-ID; samma händelse i en ny fil ger samma kvitto
och samma ID med ändrat innehåll ger konflikt. Matchningen sker i samma transaktion
(PR-ITP1-018):

1. OCR-referensen pekar ut en debetfaktura, och betalaren ska vara fakturans arbetsgivare.
2. Nettot fördelas på fakturans återstående positiva rader med `allocate_receipt`:
   proportionellt efter återstående belopp, med största bråkrest och stabil radordning.
3. Överskott, okänd referens och fel betalare blir en oallokerad post på
   avstämningskontot och ett ärende `payment_unmatched` till handläggaren. Posten har
   ingen kapital- eller garantieffekt.
4. Intern simulering har ingen valcentral: brutto = netto och externt avdrag = 0.

`allocate_unmatched_payment` låter handläggaren fördela en oallokerad post till rätt
faktura när betalaren är verifierad. Återbetalning ingår inte.

Mottagningsallokeringarna är sanningskällan (PA6). En premierad får `status='paid'`
och `paid_date` (sista mottagningsdagen) först när dess fakturarad är fullt betald.
En delbetald rad behåller `invoiced`. Paket A skapar ingen garanti och ändrar inget
kapital; det gör månadsjournalen (PA7, steg 6).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from models import (
    BankEvent,
    Case,
    Employer,
    Invoice,
    InvoiceLineRecord,
    PaymentAllocation,
    PremiumTransaction,
)
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, ConflictError, NotFoundError
from services.operations import common
from services.operations.cases import _next_case_number
from services.premium_month_inputs import InvoiceInput, ReceiptInput, allocate_receipt
from utils.checksums import checksum as content_checksum
from utils.ocr import valid_ocr

RULES = ["PR-ITP1-018"]
BASIS_VERSION = "PR-ITP1-018 v1"
#: Systemvägen som skapar matchningens ärenden (P1-PREMIE-001 §6)
MATCHING_ACTOR = "payment_matching"
INVOICE_SOURCE = "artificiellalecta-invoices"
ZERO = Decimal("0.00")
_EVENT_ID = r"^[A-Za-z0-9._:/-]{1,64}$"


# --- filformat ------------------------------------------------------------------------------------


class BankEventInput(BaseModel):
    event_id: str = Field(pattern=_EVENT_ID, description="Bankens händelse-ID")
    received_date: date = Field(description="Dagen pengarna kom in på kontot")
    amount_sek: Decimal = Field(gt=0, max_digits=12, decimal_places=2, description="Inbetalt belopp")
    payer_org_number: str = Field(pattern=r"^\d{10}$", description="Betalarens organisationsnummer")
    reference: str = Field(min_length=1, max_length=35, description="Angiven referens, normalt fakturans OCR")


class BankFileInput(BaseModel):
    source_system: str = Field(default="bank-sim", pattern=r"^[a-z0-9-]{1,40}$", description="Bankens källsystem")
    file_reference: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9._/-]+$")
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$", description="SHA-256 över filens innehåll (bank_file_checksum)")
    events: list[BankEventInput] = Field(min_length=1, max_length=10000)


def _event_content(event: BankEventInput) -> dict[str, Any]:
    return {
        "event_id": event.event_id, "received_date": event.received_date.isoformat(),
        "amount_sek": format(Decimal(event.amount_sek).quantize(Decimal("0.01")), "f"),
        "payer_org_number": event.payer_org_number, "reference": event.reference,
    }


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def bank_file_checksum(source_system: str, file_reference: str, events: list[dict | BankEventInput]) -> str:
    """Bankfilens kontrollsumma: SHA-256 över det kanoniska innehållet. Avsändaren räknar likadant."""
    parsed = [e if isinstance(e, BankEventInput) else BankEventInput.model_validate(e) for e in events]
    return _sha256({"source_system": source_system, "file_reference": file_reference,
                    "events": [_event_content(e) for e in parsed]})


# --- resultat -------------------------------------------------------------------------------------


class LineAllocation(BaseModel):
    invoice_number: str
    line_number: int
    amount_sek: Decimal


class EventOutcome(BaseModel):
    event_id: str
    status: Literal["new", "already_received"]
    amount_sek: Decimal
    invoice_number: str | None
    allocated_sek: Decimal
    unallocated_sek: Decimal
    reason: str | None = Field(description="Varför en del gick till avstämningskontot")
    allocations: list[LineAllocation]
    case_number: str | None


class BankFileResult(BaseModel):
    file_reference: str
    events: int
    new_events: int
    already_received: int
    allocated_sek: Decimal
    unallocated_sek: Decimal
    paid_premium_rows: int = Field(description="Premierader som blev fullt betalda")
    outcomes: list[EventOutcome]
    note: str


# --- import_bank_file -----------------------------------------------------------------------------


@operation(
    name="import_bank_file",
    description=(
        "Läser en bankfil med inbetalningar och matchar varje ny händelse på OCR och betalare (PR-ITP1-018). "
        "Nettot fördelas på fakturans återstående rader med största bråkrest. Överskott, okänd referens och fel "
        "betalare går till avstämningskontot med ett ärende. Samma händelse igen ger samma kvitto."
    ),
    kind=OperationKind.WRITE,
    rules=RULES,
)
def import_bank_file(ctx: OperationContext, data: BankFileInput) -> BankFileResult:
    session = ctx.require_session()
    today = common.today()
    file_checksum = bank_file_checksum(data.source_system, data.file_reference, data.events)
    if file_checksum != data.checksum:
        raise BlockedError("Bankfilens kontrollsumma stämmer inte med innehållet – filen läses inte (skadad fil)")
    ids = [e.event_id for e in data.events]
    if len(set(ids)) != len(ids):
        raise BlockedError("Samma händelse-ID förekommer flera gånger i filen")
    if any(e.received_date > today for e in data.events):
        raise BlockedError("En händelse har mottagningsdag i framtiden")

    outcomes: list[EventOutcome] = []
    paid_rows = 0
    for event_in in data.events:
        content = _event_content(event_in)
        digest = _sha256(content)
        existing = session.scalar(
            select(BankEvent).where(BankEvent.source_system == data.source_system,
                                    BankEvent.event_id == event_in.event_id).with_for_update()
        )
        if existing is not None:
            if existing.content_checksum != digest:
                raise ConflictError(
                    f"Händelsen {event_in.event_id} är redan inläst med annat innehåll – banken ska rätta med en "
                    "ny händelse. Ingenting i filen är registrerat"
                )
            outcomes.append(_outcome(session, existing, "already_received"))
            continue
        event = BankEvent(
            id=uuid.uuid4(), source_system=data.source_system, event_id=event_in.event_id,
            file_reference=data.file_reference, file_checksum=file_checksum, content_checksum=digest,
            received_date=event_in.received_date, amount_sek=event_in.amount_sek,
            payer_org_number=event_in.payer_org_number, reference=event_in.reference, created_by=ctx.actor.id,
        )
        session.add(event)
        session.flush()
        paid_rows += _match(session, ctx, event)
        outcomes.append(_outcome(session, event, "new"))

    allocated = sum((o.allocated_sek for o in outcomes if o.status == "new"), ZERO)
    unallocated = sum((o.unallocated_sek for o in outcomes if o.status == "new"), ZERO)
    new = sum(1 for o in outcomes if o.status == "new")
    return BankFileResult(
        file_reference=data.file_reference, events=len(outcomes), new_events=new,
        already_received=len(outcomes) - new, allocated_sek=allocated, unallocated_sek=unallocated,
        paid_premium_rows=paid_rows, outcomes=outcomes,
        note=(f"{new} nya inbetalningar: {allocated} kr fördelat på fakturor och {unallocated} kr på "
              "avstämningskontot. Ingen garanti eller kapital skapas här (PA7)."),
    )


def _match(session, ctx, event: BankEvent) -> int:
    """Deterministisk matchning av en ny händelse. Returnerar antalet premierader som blev betalda."""
    invoice = None
    if valid_ocr(event.reference):
        invoice = session.scalar(
            select(Invoice).where(Invoice.ocr_reference == event.reference, Invoice.invoice_type == "debit")
            .with_for_update()
        )
    if invoice is None:
        _suspense(session, ctx, event, event.amount_sek, "unknown_reference", invoice=None)
        return 0
    payer = session.scalar(select(Employer.org_number).where(Employer.id == invoice.employer_id))
    if payer != event.payer_org_number:
        _suspense(session, ctx, event, event.amount_sek, "wrong_payer", invoice=invoice)
        return 0
    shares, remainder = _allocate(session, invoice, event, event.amount_sek, payer)
    for line, share in shares:
        _add_allocation(session, ctx, event, "invoice_line", share, "ocr_match", invoice=invoice, line=line)
    if remainder > 0:
        _suspense(session, ctx, event, remainder, "overpayment", invoice=invoice)
    return _settle(session, [line for line, _ in shares])


def _allocate(session, invoice: Invoice, event: BankEvent, amount: Decimal, payer: str):
    """allocate_receipt på fakturans rader: krediterade och redan betalda delar räknas som allokerade."""
    lines = session.scalars(
        select(InvoiceLineRecord).where(InvoiceLineRecord.invoice_id == invoice.id)
        .order_by(InvoiceLineRecord.line_number)
    ).all()
    by_key = {f"line-{line.line_number:04d}": line for line in lines}
    taken = {key: _allocated_to(session, line) + _credited(session, line) for key, line in by_key.items()}
    contract = _invoice_input(session, invoice, by_key, payer)
    receipt = _receipt_input(event, amount, invoice.invoice_number, payer)
    shares, remainder = allocate_receipt(contract, receipt, taken)
    return [(by_key[key], share) for key, share in sorted(shares.items())], remainder


def _invoice_input(session, invoice: Invoice, by_key: dict, payer: str) -> InvoiceInput:
    lines = []
    for key, line in by_key.items():
        basis = session.scalar(select(PremiumTransaction.calculation_basis)
                               .where(PremiumTransaction.id == line.premium_transaction_id)) or {}
        lines.append({
            "id": key, "benefit_id": str(line.benefit_id), "policy_id": str(line.policy_id),
            "period_month": line.period_month.isoformat(), "due_sek": format(line.amount_sek, "f"),
            "calculation_basis": basis or {"invoice_line": key},
        })
    # En debetfaktura har bara positiva rader; en krediterad rad räknas som allokerad (vikt noll)
    payload = {"id": invoice.invoice_number, "payer_id": payer, "lines": lines}
    source = {"system": INVOICE_SOURCE, "reference": invoice.invoice_number, "version": invoice.checksum[:16],
              "checksum": content_checksum(payload), "synthetic": True, "payload": payload}
    return InvoiceInput.model_validate({**payload, "source": source})


def _receipt_input(event: BankEvent, amount: Decimal, invoice_number: str, payer: str) -> ReceiptInput:
    amount = Decimal(amount).quantize(Decimal("0.01"))
    payload = {
        "event_id": event.id.hex, "payment_reference": event.reference, "payer_id": payer,
        "received_date": event.received_date.isoformat(), "currency": "SEK",
        "gross_sek": format(amount, "f"), "external_deduction_sek": "0.00", "net_sek": format(amount, "f"),
        "invoice_id": invoice_number,
    }
    source = {"system": event.source_system, "reference": event.event_id, "version": BASIS_VERSION,
              "checksum": content_checksum(payload), "synthetic": True, "payload": payload}
    return ReceiptInput.model_validate({**payload, "source": source})


def _allocated_to(session, line: InvoiceLineRecord) -> Decimal:
    return Decimal(session.scalar(
        select(func.coalesce(func.sum(PaymentAllocation.amount_sek), 0))
        .where(PaymentAllocation.invoice_line_id == line.id)
    ))


def _credited(session, line: InvoiceLineRecord) -> Decimal:
    credit = session.scalar(select(InvoiceLineRecord.amount_sek).where(InvoiceLineRecord.credits_line_id == line.id))
    return -Decimal(credit) if credit is not None else ZERO


def _add_allocation(session, ctx, event, kind, amount, basis, *, invoice, line=None, key=None) -> PaymentAllocation:
    allocation = PaymentAllocation(
        id=uuid.uuid4(), bank_event_id=event.id, kind=kind, invoice_id=invoice.id if invoice is not None else None,
        invoice_line_id=line.id if line is not None else None, amount_sek=amount, basis=basis,
        basis_version=BASIS_VERSION, created_by=ctx.actor.id,
        allocation_key=key or _sha256({"event": str(event.id), "kind": kind, "basis": basis,
                                       "line": str(line.id) if line is not None else None}),
    )
    session.add(allocation)
    session.flush()
    return allocation


def _suspense(session, ctx, event, amount, reason, *, invoice) -> None:
    _add_allocation(session, ctx, event, "suspense", amount, reason, invoice=invoice)
    payer = session.scalar(select(Employer).where(Employer.org_number == event.payer_org_number))
    details = {
        "source_system": event.source_system, "event_id": event.event_id,
        "received_date": event.received_date.isoformat(), "amount_sek": str(event.amount_sek),
        "unallocated_sek": str(amount), "reason": reason, "reference": event.reference,
        "payer_org_number": event.payer_org_number,
        "invoice_number": invoice.invoice_number if invoice is not None else None, "rule": "PR-ITP1-018",
    }
    session.add(Case(
        id=uuid.uuid4(), case_number=_next_case_number(session), case_type="payment_unmatched", status="open",
        employer_id=payer.id if payer is not None else None,
        period_month=invoice.period_month if invoice is not None else None, channel="system",
        received_date=event.received_date, source_reference=f"{event.source_system}:{event.event_id}",
        details=details, created_by=MATCHING_ACTOR,
    ))
    session.flush()


def _settle(session, lines: list[InvoiceLineRecord]) -> int:
    """PA6: premieraderna blir betalda när fakturaraden är fullt betald, med sista mottagningsdagen."""
    paid = 0
    for line in lines:
        if line.line_type == "credit" or _allocated_to(session, line) < line.amount_sek:
            continue
        last = session.scalar(
            select(func.max(BankEvent.received_date)).join(PaymentAllocation, PaymentAllocation.bank_event_id == BankEvent.id)
            .where(PaymentAllocation.invoice_line_id == line.id)
        )
        ids = {uuid.UUID(i) for i in line.covers}
        if line.line_type in ("ordinary", "rebill"):
            ids.add(line.premium_transaction_id)
        for row in session.scalars(select(PremiumTransaction).where(PremiumTransaction.id.in_(ids))):
            if row.status != "paid":
                row.status, row.paid_date = "paid", last
                paid += 1
    return paid


def _outcome(session, event: BankEvent, status: str) -> EventOutcome:
    allocations = session.scalars(
        select(PaymentAllocation).where(PaymentAllocation.bank_event_id == event.id)
        .order_by(PaymentAllocation.created_at, PaymentAllocation.id)
    ).all()
    line_rows = []
    invoice_number = None
    for allocation in allocations:
        if allocation.invoice_id is not None and invoice_number is None:
            invoice_number = session.scalar(select(Invoice.invoice_number).where(Invoice.id == allocation.invoice_id))
        if allocation.kind == "invoice_line":
            number = session.scalar(select(InvoiceLineRecord.line_number)
                                    .where(InvoiceLineRecord.id == allocation.invoice_line_id))
            line_invoice = session.scalar(select(Invoice.invoice_number).where(Invoice.id == allocation.invoice_id))
            line_rows.append(LineAllocation(invoice_number=line_invoice, line_number=number,
                                            amount_sek=allocation.amount_sek))
    suspense = [a for a in allocations if a.kind == "suspense"]
    reasons = [a.basis for a in suspense if a.amount_sek > 0]
    case_number = session.scalar(select(Case.case_number).where(
        Case.case_type == "payment_unmatched", Case.source_reference == f"{event.source_system}:{event.event_id}"))
    line_rows.sort(key=lambda r: (r.invoice_number, r.line_number))
    return EventOutcome(
        event_id=event.event_id, status=status, amount_sek=event.amount_sek, invoice_number=invoice_number,
        allocated_sek=sum((r.amount_sek for r in line_rows), ZERO),
        unallocated_sek=sum((a.amount_sek for a in suspense), ZERO),
        reason=reasons[0] if reasons else None, allocations=line_rows, case_number=case_number,
    )


# --- allocate_unmatched_payment -------------------------------------------------------------------


class ManualAllocationInput(BaseModel):
    source_system: str = Field(default="bank-sim", pattern=r"^[a-z0-9-]{1,40}$")
    event_id: str = Field(pattern=_EVENT_ID)
    invoice_number: str = Field(pattern=r"^INV-\d{6}$", description="Debetfakturan som posten avser")
    amount_sek: Decimal | None = Field(default=None, gt=0, decimal_places=2,
                                       description="Del av den oallokerade posten; tomt = hela")
    payer_verification: str = Field(min_length=1, max_length=500,
                                    description="Hur betalaren verifierats, t.ex. kontakt med arbetsgivaren")
    request_key: str = Field(min_length=1, max_length=64, description="Idempotensnyckel för fördelningen")


class ManualAllocationResult(BaseModel):
    event_id: str
    invoice_number: str
    status: Literal["allocated", "already_applied"]
    allocated_sek: Decimal
    remaining_suspense_sek: Decimal
    allocations: list[LineAllocation]
    paid_premium_rows: int
    note: str


@operation(
    name="allocate_unmatched_payment",
    description=(
        "Fördelar en oallokerad post på avstämningskontot till en debetfaktura när betalaren är verifierad "
        "(PR-ITP1-018). Samma fördelningsgrund som matchningen; det som inte ryms blir kvar på kontot. "
        "Ingen återbetalning."
    ),
    kind=OperationKind.WRITE,
    rules=RULES,
)
def allocate_unmatched_payment(ctx: OperationContext, data: ManualAllocationInput) -> ManualAllocationResult:
    session = ctx.require_session()
    event = session.scalar(
        select(BankEvent).where(BankEvent.source_system == data.source_system, BankEvent.event_id == data.event_id)
        .with_for_update()
    )
    if event is None:
        raise NotFoundError(f"Ingen bankhändelse {data.source_system}:{data.event_id}")
    release_key = _sha256({"event": str(event.id), "request": data.request_key, "kind": "manual_release"})
    previous = session.scalar(select(PaymentAllocation).where(PaymentAllocation.allocation_key == release_key))
    invoice = session.scalar(select(Invoice).where(Invoice.invoice_number == data.invoice_number).with_for_update())
    if invoice is None or invoice.invoice_type != "debit":
        raise NotFoundError(f"Ingen debetfaktura {data.invoice_number}")
    if previous is not None:
        if previous.invoice_id != invoice.id:
            raise ConflictError("Idempotensnyckeln är redan använd för en annan faktura")
        manual = session.scalars(select(PaymentAllocation).where(
            PaymentAllocation.bank_event_id == event.id, PaymentAllocation.basis == "manual",
            PaymentAllocation.invoice_id == invoice.id)).all()
        return _manual_result(session, event, invoice, "already_applied", manual, 0)

    balance = Decimal(session.scalar(
        select(func.coalesce(func.sum(PaymentAllocation.amount_sek), 0))
        .where(PaymentAllocation.bank_event_id == event.id, PaymentAllocation.kind == "suspense")
    ))
    if balance <= 0:
        raise BlockedError(f"Händelsen {event.event_id} har inget oallokerat belopp")
    amount = min(data.amount_sek or balance, balance)
    payer = session.scalar(select(Employer.org_number).where(Employer.id == invoice.employer_id))
    shares, _ = _allocate(session, invoice, event, amount, payer)
    matched = sum((share for _, share in shares), ZERO)
    if matched <= 0:
        raise BlockedError(f"Fakturan {invoice.invoice_number} har inget öppet belopp att fördela till")
    created = [
        _add_allocation(session, ctx, event, "invoice_line", share, "manual", invoice=invoice, line=line,
                        key=_sha256({"release": release_key, "line": str(line.id)}))
        for line, share in shares
    ]
    _add_allocation(session, ctx, event, "suspense", -matched, "manual_release", invoice=invoice, key=release_key)
    paid = _settle(session, [line for line, _ in shares])
    return _manual_result(session, event, invoice, "allocated", created, paid)


def _manual_result(session, event, invoice, status, allocations, paid) -> ManualAllocationResult:
    rows = []
    for allocation in allocations:
        number = session.scalar(select(InvoiceLineRecord.line_number)
                                .where(InvoiceLineRecord.id == allocation.invoice_line_id))
        rows.append(LineAllocation(invoice_number=invoice.invoice_number, line_number=number,
                                   amount_sek=allocation.amount_sek))
    remaining = Decimal(session.scalar(
        select(func.coalesce(func.sum(PaymentAllocation.amount_sek), 0))
        .where(PaymentAllocation.bank_event_id == event.id, PaymentAllocation.kind == "suspense")
    ))
    total = sum((r.amount_sek for r in rows), ZERO)
    return ManualAllocationResult(
        event_id=event.event_id, invoice_number=invoice.invoice_number, status=status, allocated_sek=total,
        remaining_suspense_sek=remaining, allocations=sorted(rows, key=lambda r: r.line_number),
        paid_premium_rows=paid,
        note=(f"{total} kr fördelat från avstämningskontot till {invoice.invoice_number}; {remaining} kr kvar."
              if status == "allocated" else "Fördelningen är redan gjord med samma idempotensnyckel."),
    )


# --- get_receivables ------------------------------------------------------------------------------


class ReceivablesQuery(BaseModel):
    employer_org_number: str | None = Field(default=None, pattern=r"^\d{10}$",
                                            description="Arbetsgivare; tomt = hela bolaget")


class OpenInvoice(BaseModel):
    invoice_number: str
    employer_org_number: str
    period_month: date
    due_date: date
    total_sek: Decimal
    credited_sek: Decimal
    allocated_sek: Decimal
    open_sek: Decimal


class Receivables(BaseModel):
    open_invoices: list[OpenInvoice]
    receivables_sek: Decimal = Field(description="Fakturerat minus krediterat och mottaget")
    invoiced_sek: Decimal = Field(description="Debetfakturor minus kreditfakturor")
    bank_total_sek: Decimal = Field(description="Summa inbetalningar")
    allocated_sek: Decimal = Field(description="Fördelat på fakturarader")
    suspense_sek: Decimal = Field(description="Kvar på avstämningskontot")
    balanced: bool = Field(description="Inbetalningar = fördelat + avstämningskonto, och fakturerat − fördelat = fordringar")


@operation(
    name="get_receivables",
    description=(
        "Visar öppna premiefordringar per faktura och avstämningen: inbetalningar = fördelat + "
        "avstämningskonto, och fakturerat − fördelat = öppna fordringar (P1-PREMIE-001 §7)."
    ),
    kind=OperationKind.READ,
)
def get_receivables(ctx: OperationContext, data: ReceivablesQuery) -> Receivables:
    session = ctx.require_session()
    invoices_query = select(Invoice, Employer.org_number).join(Employer, Employer.id == Invoice.employer_id)
    events_query = select(BankEvent)
    if data.employer_org_number is not None:
        invoices_query = invoices_query.where(Employer.org_number == data.employer_org_number)
        events_query = events_query.where(BankEvent.payer_org_number == data.employer_org_number)
    rows = session.execute(invoices_query.order_by(Invoice.invoice_number)).all()
    invoiced = ZERO
    open_rows = []
    for invoice, org in rows:
        invoiced += invoice.total_sek
        if invoice.invoice_type != "debit":
            continue
        credited = Decimal(session.scalar(select(func.coalesce(func.sum(Invoice.total_sek), 0))
                                          .where(Invoice.credited_invoice_id == invoice.id)))
        allocated = Decimal(session.scalar(select(func.coalesce(func.sum(PaymentAllocation.amount_sek), 0))
                                           .where(PaymentAllocation.invoice_id == invoice.id,
                                                  PaymentAllocation.kind == "invoice_line")))
        open_sek = invoice.total_sek + credited - allocated
        if open_sek != 0:
            open_rows.append(OpenInvoice(
                invoice_number=invoice.invoice_number, employer_org_number=org, period_month=invoice.period_month,
                due_date=invoice.due_date, total_sek=invoice.total_sek, credited_sek=credited,
                allocated_sek=allocated, open_sek=open_sek,
            ))
    events = session.scalars(events_query).all()
    event_ids = [e.id for e in events]
    bank_total = sum((e.amount_sek for e in events), ZERO)

    def _sum(kind: str) -> Decimal:
        if not event_ids:
            return ZERO
        return Decimal(session.scalar(select(func.coalesce(func.sum(PaymentAllocation.amount_sek), 0)).where(
            PaymentAllocation.bank_event_id.in_(event_ids), PaymentAllocation.kind == kind)))

    allocated_total, suspense = _sum("invoice_line"), _sum("suspense")
    receivables = sum((r.open_sek for r in open_rows), ZERO)
    balanced = bank_total == allocated_total + suspense
    if data.employer_org_number is None:
        balanced = balanced and invoiced - allocated_total == receivables
    return Receivables(
        open_invoices=open_rows, receivables_sek=receivables, invoiced_sek=invoiced, bank_total_sek=bank_total,
        allocated_sek=allocated_total, suspense_sek=suspense, balanced=balanced,
    )
