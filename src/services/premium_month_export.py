"""Överlämning av paket A:s mottagna premier till månadsjournalen (B-046 steg 6, P1-PREMIE-001 §4.7, PA7).

Paket A:s tabeller blir källpaketet som `open_premium_month` och `receive_premium_payment`
redan tar emot (P6-MANAD-001 §4.1). Paketet har samma IB, grunder och parametrar som det
syntetiska novemberförsöket (`premium_month_preparation`); bara fakturorna och kvittona
kommer från paket A:

- **Fakturor:** varje debetfaktura för premieperioden som har mottagna belopp i journalmånaden,
  som `InvoiceInput`. En krediterad rad är ingen fordran och följer inte med; kredit och ny
  debet syns därför som den nya debetraden. Radens id är `line-<nr>` som i matchningen.
  Premieunderlaget bär radtypen, premierna den fakturerar och deras beräkningsgrund.
- **Kvitton:** ett `ReceiptInput` per bankhändelse och faktura. Beloppet är summan av
  händelsens allokeringar på fakturans rader; allokeringarna är sanningskällan (PA6).
  Avstämningskontot följer inte med: en oallokerad post har ingen kapital- eller
  garantieffekt och står kvar i paket A.
- **Stoppunkt:** journalens månad, november 2026. Mottagningar efter månadsslutet hör till
  en senare journal och redovisas som utanför paketet. Mottagningar före månaden stoppar
  exporten, eftersom de varken finns i IB eller i journalmånaden.

Exporten skriver ingenting. Den prövar i förväg att journalens fördelning, i journalens egen
datum- och originalordning, blir exakt paket A:s allokeringar i ören, och stoppar annars.
Samma tabelläge ger samma paket och samma kontrollsumma, så en ny export ger ingen ny
effekt i journalen: `open_premium_month` och `receive_premium_payment` är idempotenta.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from models import (
    BankEvent,
    Employer,
    Invoice,
    InvoiceLineRecord,
    PaymentAllocation,
    PremiumTransaction,
)
from services import valuation_bases as vb
from services.premium_month_inputs import MonthInputs, allocate_receipt, receipt_key
from services.premium_month_preparation import (
    OPENING_DATE,
    PERIOD_END,
    assemble,
    opening,
)

EXPORT_VERSION = "paket-a-export-1"
#: Källsystemet för paket A:s fakturor, samma som i matchningen (payments.py)
INVOICE_SYSTEM = "artificiellalecta-invoices"
#: Den premieperiod som månadsjournalens första försök tar emot (PA1; P6-MANAD-001 §3.1)
PERIOD = date(2026, 10, 1)
MONTH_START = PERIOD_END.replace(day=1)
ZERO = Decimal("0.00")


class ExportError(ValueError):
    """Paket A:s läge kan inte lämnas till journalen utan att kvittona avviker från allokeringarna."""


def _money(value: Decimal) -> str:
    return format(Decimal(value).quantize(Decimal("0.01")), "f")


def _source(system: str, reference: str, version: str, payload: dict) -> dict:
    return {"system": system, "reference": reference, "version": version, "checksum": vb.checksum(payload),
            "synthetic": True, "payload": payload}


def line_key(line: InvoiceLineRecord) -> str:
    return f"line-{line.line_number:04d}"


def receipt_event_id(event: BankEvent, invoice: Invoice) -> str:
    """Kvittots original-ID: bankhändelsens stabila identitet och fakturan den fördelats på."""
    return f"{event.id.hex}-{invoice.invoice_number}"


def period_sources(session, period: date = PERIOD) -> tuple[list[dict], list[dict], dict, dict]:
    """Fakturor och kvitton för premieperioden, väntade radbelopp per kvitto och en sammanställning."""
    rows = session.execute(
        select(PaymentAllocation, BankEvent, Invoice)
        .join(BankEvent, BankEvent.id == PaymentAllocation.bank_event_id)
        .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
        .where(PaymentAllocation.kind == "invoice_line", Invoice.period_month == period)
        .order_by(BankEvent.received_date, BankEvent.id, PaymentAllocation.id)
    ).all()
    early = [event for _, event, _ in rows if event.received_date < MONTH_START]
    if early:
        raise ExportError(
            f"{len({e.id for e in early})} inbetalningar mottogs före {MONTH_START:%Y-%m}. De finns varken i IB "
            f"per {OPENING_DATE} eller i journalmånaden och kan inte lämnas till månadsjournalen")
    grouped: dict[tuple, dict] = {}
    later_events, later_sek = set(), ZERO
    for allocation, event, invoice in rows:
        if event.received_date > PERIOD_END:
            later_events.add(event.id)
            later_sek += allocation.amount_sek
            continue
        group = grouped.setdefault((event.id, invoice.id), {"event": event, "invoice": invoice, "lines": {}})
        group["lines"][allocation.invoice_line_id] = group["lines"].get(allocation.invoice_line_id, ZERO) \
            + allocation.amount_sek

    invoices, receipts, expected = {}, [], {}
    credited_lines = 0
    for group in grouped.values():
        event, invoice = group["event"], group["invoice"]
        if invoice.invoice_type != "debit":
            raise ExportError(f"Allokering på kreditfakturan {invoice.invoice_number} – manuell prövning")
        if invoice.id not in invoices:
            body, lines, credited = _invoice(session, invoice)
            invoices[invoice.id] = (body, lines)
            credited_lines += credited
        body, lines = invoices[invoice.id]
        keys = {line.id: line_key(line) for line in lines}
        if set(group["lines"]) - set(keys):
            raise ExportError(f"Allokering på en krediterad rad i {invoice.invoice_number} – manuell prövning")
        amount = sum(group["lines"].values(), ZERO)
        event_id = receipt_event_id(event, invoice)
        payload = {"event_id": event_id, "payment_reference": event.reference, "payer_id": body["payer_id"],
                   "received_date": event.received_date.isoformat(), "currency": "SEK",
                   "gross_sek": _money(amount), "external_deduction_sek": "0.00", "net_sek": _money(amount),
                   "invoice_id": invoice.invoice_number}
        receipts.append({**payload, "source": _source(event.source_system, f"{event.source_system}:{event.event_id}",
                                                      event.content_checksum, payload)})
        expected[event_id] = {keys[line_id]: share for line_id, share in group["lines"].items()}

    in_month = (BankEvent.received_date >= MONTH_START, BankEvent.received_date <= PERIOD_END)
    suspense = select(PaymentAllocation.amount_sek).join(BankEvent, BankEvent.id == PaymentAllocation.bank_event_id)         .where(PaymentAllocation.kind == "suspense", *in_month)
    on_invoices = sum(session.scalars(suspense.join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
                                      .where(Invoice.period_month == period)), ZERO)
    without_invoice = sum(session.scalars(suspense.where(PaymentAllocation.invoice_id.is_(None))), ZERO)
    invoice_inputs = [body for body, _ in sorted(invoices.values(), key=lambda item: item[0]["id"])]
    receipts.sort(key=lambda r: (r["received_date"], r["event_id"]))
    summary = {
        "export_version": EXPORT_VERSION, "period_month": period.isoformat(),
        "journal_month": MONTH_START.isoformat(), "journal_month_end": PERIOD_END.isoformat(),
        "invoices": len(invoice_inputs), "invoice_lines": sum(len(i["lines"]) for i in invoice_inputs),
        "credited_lines_left_out": credited_lines, "receipts": len(receipts),
        "received_sek": _money(sum((Decimal(r["net_sek"]) for r in receipts), ZERO)),
        # Avstämningskontot följer inte med: saldo för journalmånadens inbetalningar, kvar i paket A
        "suspense_on_period_invoices_sek": _money(on_invoices),
        "suspense_without_invoice_sek": _money(without_invoice),
        "after_month_end": {"bank_events": len(later_events), "allocated_sek": _money(later_sek)},
    }
    return invoice_inputs, receipts, expected, summary


def _invoice(session, invoice: Invoice) -> tuple[dict, list, int]:
    lines = session.scalars(select(InvoiceLineRecord).where(InvoiceLineRecord.invoice_id == invoice.id)
                            .order_by(InvoiceLineRecord.line_number)).all()
    credited = set(session.scalars(select(InvoiceLineRecord.credits_line_id).where(
        InvoiceLineRecord.credits_line_id.in_([line.id for line in lines]))))
    open_lines = [line for line in lines if line.id not in credited]
    payer = session.scalar(select(Employer.org_number).where(Employer.id == invoice.employer_id))
    body_lines = []
    for line in open_lines:
        ids = sorted({str(line.premium_transaction_id), *line.covers})
        bases = dict(session.execute(select(PremiumTransaction.id, PremiumTransaction.calculation_basis)
                                     .where(PremiumTransaction.id.in_([uuid.UUID(i) for i in ids]))).all())
        body_lines.append({
            "id": line_key(line), "benefit_id": str(line.benefit_id), "policy_id": str(line.policy_id),
            "period_month": line.period_month.isoformat(), "due_sek": _money(line.amount_sek),
            "calculation_basis": {
                "invoice_line_type": line.line_type, "invoice_number": invoice.invoice_number,
                "line_number": line.line_number, "premium_transaction_id": str(line.premium_transaction_id),
                "covers": list(line.covers),
                "premiums": {str(k): v or {} for k, v in sorted(bases.items(), key=lambda kv: str(kv[0]))},
                "product_package": "PR-ITP1-v1.0", "export": EXPORT_VERSION,
            },
        })
    payload = {"id": invoice.invoice_number, "payer_id": payer, "lines": body_lines}
    body = {**payload, "source": _source(INVOICE_SYSTEM, invoice.invoice_number, invoice.checksum, payload)}
    return body, open_lines, len(lines) - len(open_lines)


def verify_journal_allocation(package: MonthInputs, expected: dict[str, dict[str, Decimal]]) -> None:
    """Journalens fördelning i dess egen ordning ska bli exakt paket A:s allokeringar i ören."""
    invoices = {i.id: i for i in package.invoices}
    allocated: dict[str, dict[str, Decimal]] = defaultdict(dict)
    order = sorted(package.receipts, key=lambda r: (r.received_date, receipt_key(package.scenario_id, r)))
    for receipt in order:
        invoice = invoices[receipt.invoice_id]
        shares, rest = allocate_receipt(invoice, receipt, allocated[invoice.id])
        if rest != 0 or shares != expected[receipt.event_id]:
            raise ExportError(
                f"Månadsjournalen skulle fördela inbetalningen {receipt.source.reference} på {invoice.id} "
                f"annorlunda än paket A ({_plain(shares)} mot {_plain(expected[receipt.event_id])}). Det sker när "
                "flera inbetalningar på samma faktura har fördelats i en annan ordning än mottagningsordningen, "
                "till exempel efter en manuell fördelning – manuell prövning")
        for key, share in shares.items():
            allocated[invoice.id][key] = allocated[invoice.id].get(key, ZERO) + share


def _plain(shares: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(shares.items())) or "inget"


def _trial_population(c, invoices: list[dict]) -> None:
    """Månadsjournalens första försök kräver en fullständigt beräknad, ej påbörjad population (P6-MANAD-001)."""
    e = c.extract
    if e.not_calculated:
        raise ExportError(
            f"IB per {OPENING_DATE} har {len(e.not_calculated)} försäkringar som inte beräknas (till exempel "
            "påbörjat uttag). Månadsjournalens första försök kräver en fullständigt beräknad population")
    started = [p for p in e.policies if p.plan.start <= PERIOD_END]
    if started:
        raise ExportError(
            f"{len(started)} försäkringar i IB har en referensplan som startar senast {PERIOD_END}. Månadsjournalens "
            "första försök stöder bara ej påbörjade referensplaner")
    population = {p.policy_id for p in e.policies}
    outside = {line["policy_id"] for i in invoices for line in i["lines"]} - population
    if outside:
        raise ExportError(
            f"{len(outside)} fakturerade försäkringar saknas i IB-populationen per {OPENING_DATE}, till exempel "
            "nyanslutna utan tidigare mottagen premie. Journalen kan inte utöka den frysta populationen")


def export_inputs(session, scenario_id: str, expected_opening_checksum: str,
                  period: date = PERIOD) -> tuple[MonthInputs, dict]:
    """Källpaket för månadsjournalen ur paket A. Läser och räknar; skriver ingenting."""
    if period != PERIOD:
        raise ExportError(f"Månadsjournalen tar i dag emot premieperiod {PERIOD:%Y-%m}, mottagen i "
                          f"{MONTH_START:%Y-%m} (P6-MANAD-001)")
    invoices, receipts, expected, summary = period_sources(session, period)
    if not receipts:
        raise ExportError(f"Inga mottagna premier för {period:%Y-%m} i {MONTH_START:%Y-%m}")
    c = opening(session)
    _trial_population(c, invoices)
    package = assemble(session, c, scenario_id, expected_opening_checksum, invoices, receipts)
    verify_journal_allocation(package, expected)
    return package, {**summary, "scenario_id": scenario_id, "opening_checksum": package.opening.checksum,
                     "checksum": package.checksum}
