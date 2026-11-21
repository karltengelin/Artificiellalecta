"""Journalens premiekälla: paket A:s allokeringar för en månad (paket B steg 2, B-047 punkt 4, B-046 PA6–PA7).

Från november 2026 är paket A:s betalningsallokeringar den enda källan för nya premier i den operativa
journalen (P1-PENSION-001 §6.2 p. 4). Status `paid` används inte som källa, så en delbetalning kommer
med. Avstämningskontot följer inte med: överskott, okänd referens och fel betalare har ingen kapital-
eller garantieffekt.

`premium_intake` räknar månadens premiepost i PR-ITP1-020:s steg 4 utan att skriva: en garantidel och
en kapitalpost per allokering på en fakturarad, på uttagsdelen som premien räknades för (steg 1), med
G_j = P_j / A_g på referensplanen vid mottagningsmånadens slut och den garantigrund som gäller då. Den
bokas av månadsstängningen i steg 3, efter avkastning, avgift och skattebelastning. Har delen en beslutad
uttagsplan som gäller månaden (paket B steg 4) räknas A_g i stället på planen och garantidelen pekar på den. Fall 37 (november
2026 i Lakebase): 51 623,90 kr, varav SvenskIndustries delbetalning 15 362,24 kr; avstämningskontots
36 261,66 kr ger ingen effekt.

Kontraktet mot paket A är detsamma som överlämningen till P6-MANAD-001 (`premium_month_export`): ett
`ReceiptInput` per bankhändelse och faktura med allokeringarnas belopp, och fakturan som `InvoiceInput`.
Allokeringsprovet i ören (`allocate_receipt`) körs i mottagningsordning, med tidigare månaders
allokeringar på samma faktura som redan fördelade, och ska ge exakt paket A:s fördelning.

**Stoppunkt (Karls val S3 2026-11-19, paket B steg 3):** en månads premier är paket A:s allokeringar på
fakturarader som är registrerade när månaden stängs, har mottagningsdag senast månadsslutet och inte redan
är bokade i journalen. En inbetalning med mottagningsdag i en stängd månad som registreras senare bokas
därför i nästa öppna månad, med den månadens värdedag och grund – inte som rättelse av den stängda
månaden. Mottagningar efter månadsslutet hör till en senare månad och redovisas som utanför. Månaden
kan bara tas emot när föregående månad är stängd (eller är det ingående läget), och en stängd månad tar
inte emot fler premier.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from analytics.portfolio_snapshot import birth_date
from models import (
    BankEvent,
    Employer,
    InsuredPerson,
    Invoice,
    InvoiceLineRecord,
    LedgerGuaranteePart,
    PaymentAllocation,
    PayoutPart,
    Policy,
    PremiumTransaction,
)
from services import capital_ledger as cl
from services import payout_plans
from services import valuation_bases as vb
from services.payout_parts import receiving_parts
from services.premium_month_export import (
    _invoice,
    _money,
    _source,
    line_key,
    receipt_event_id,
)
from services.premium_month_inputs import InvoiceInput, ReceiptInput, allocate_receipt
from services.valuation_extract import (
    GUARANTEE_FAMILIES,
    PRECISION,
    ExtractError,
    _adopted,
    _Guarantee,
    month_end,
)
from skills.calculation import actuarial_annuity as aa

VERSION = "ledger-premiums-1"
ZERO = Decimal("0.00")


class IntakeError(ValueError):
    """Månadens premier kan inte tas emot i journalen utan att avvika från paket A."""


@dataclass(frozen=True)
class PremiumAddition:
    """En premie som månadsstängningen bokar: garantidel och kapitalpost på en uttagsdel."""

    payment_allocation_id: uuid.UUID
    bank_event_id: uuid.UUID
    invoice_number: str
    line_number: int
    premium_transaction_id: uuid.UUID
    payout_part_id: uuid.UUID
    policy_id: uuid.UUID
    employer_org_number: str
    premium_sek: Decimal
    period_month: date
    received_month: date
    value_date: date
    plan_start: date
    basis_code: str
    basis_checksum: str
    factor: Decimal
    guarantee_sek_per_month: Decimal
    #: Planen A_g räknas på: referensplanen, eller delens beslutade plan som gäller månaden (steg 4, V7)
    plan_kind: str = "reference_lifelong"
    plan_id: uuid.UUID | None = None

    def plain(self) -> dict:
        return {k: (str(v) if isinstance(v, (uuid.UUID, Decimal, date)) else v) for k, v in asdict(self).items()}


@dataclass
class PremiumIntake:
    month: date
    additions: list[PremiumAddition]
    summary: dict
    checksum: str


def _q(value: float | Decimal) -> Decimal:
    return (value if isinstance(value, Decimal) else Decimal(repr(value))).quantize(PRECISION)


def premium_intake(session: Session, month: date) -> PremiumIntake:
    """Månadens premier ur paket A:s allokeringar som journalens tillskott (PR-020 steg 4). Skriver ingenting."""
    month = month.replace(day=1)
    end = month_end(month)
    batch = cl.opening_batch(session)
    if batch is None:
        raise IntakeError("Kapitaljournalen har inget ingående läge – övergången från S-04 görs först")
    if end <= batch.period_end:
        raise IntakeError(f"{month:%Y-%m} ligger i S-04:s ingående läge per {batch.period_end}; nya premier tas "
                          f"emot från {aa.first_month_after(batch.period_end):%Y-%m}")
    closed = cl.closed_month_ends(session)
    if end in closed:
        raise IntakeError(f"{month:%Y-%m} är stängd; sena mottagningar bokas i nästa öppna månad (stoppunkten)")
    previous = month_end(aa.add_months(month, -1))
    if previous != batch.period_end and previous not in closed:
        raise IntakeError(f"Föregående månad {previous:%Y-%m} är inte stängd – månaderna tas emot i ordning")
    booked_ids = set(session.scalars(select(LedgerGuaranteePart.payment_allocation_id).where(
        LedgerGuaranteePart.payment_allocation_id.is_not(None))))
    rows = session.execute(
        select(PaymentAllocation, BankEvent, Invoice, InvoiceLineRecord)
        .join(BankEvent, BankEvent.id == PaymentAllocation.bank_event_id)
        .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
        .join(InvoiceLineRecord, InvoiceLineRecord.id == PaymentAllocation.invoice_line_id)
        .where(PaymentAllocation.kind == "invoice_line", BankEvent.received_date <= end)
        .order_by(BankEvent.received_date, BankEvent.id, PaymentAllocation.id)).all()
    early = {e.id for _, e, _, _ in rows if e.received_date <= batch.period_end}
    if early:
        raise IntakeError(f"{len(early)} inbetalningar i paket A mottogs senast {batch.period_end} och finns inte i "
                          "S-04 – manuell prövning")

    prior: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    groups: dict[tuple, dict] = {}
    for allocation, event, invoice, line in rows:
        if allocation.id in booked_ids:  # redan bokad i en stängd månad: fördelad på fakturans rader
            prior[invoice.id][line_key(line)] += allocation.amount_sek
            continue
        group = groups.setdefault((event.received_date, event.id, invoice.id),
                                  {"event": event, "invoice": invoice, "allocations": []})
        group["allocations"].append((allocation, line))

    invoices: dict[uuid.UUID, tuple[InvoiceInput, list]] = {}
    for _, _, invoice_id in groups:
        if invoice_id in invoices:
            continue
        invoice = next(g["invoice"] for k, g in groups.items() if k[2] == invoice_id)
        if invoice.invoice_type != "debit":
            raise IntakeError(f"Allokering på kreditfakturan {invoice.invoice_number} – manuell prövning")
        body, lines, _ = _invoice(session, invoice)
        invoices[invoice_id] = (InvoiceInput.model_validate(body), lines)

    allocated = {k: dict(v) for k, v in prior.items()}
    receipts, additions_src = [], []
    for (received, _, invoice_id), group in sorted(groups.items(), key=lambda kv: (kv[0][0], str(kv[0][1]), str(kv[0][2]))):
        event, invoice = group["event"], group["invoice"]
        invoice_input, open_lines = invoices[invoice_id]
        keys = {line.id: line_key(line) for line in open_lines}
        expected: dict[str, Decimal] = defaultdict(Decimal)
        for allocation, line in group["allocations"]:
            if line.id not in keys:
                raise IntakeError(f"Allokering på en krediterad rad i {invoice.invoice_number} – manuell prövning")
            expected[keys[line.id]] += allocation.amount_sek
        amount = sum(expected.values(), ZERO)
        payload = {"event_id": receipt_event_id(event, invoice), "payment_reference": event.reference,
                   "payer_id": invoice_input.payer_id, "received_date": event.received_date.isoformat(),
                   "currency": "SEK", "gross_sek": _money(amount), "external_deduction_sek": "0.00",
                   "net_sek": _money(amount), "invoice_id": invoice.invoice_number}
        receipt = ReceiptInput.model_validate({**payload, "source": _source(
            event.source_system, f"{event.source_system}:{event.event_id}", event.content_checksum, payload)})
        shares, rest = allocate_receipt(invoice_input, receipt, allocated.setdefault(invoice_id, {}))
        if rest != 0 or shares != dict(expected):
            raise IntakeError(
                f"Journalen skulle fördela inbetalningen {receipt.source.reference} på {invoice.invoice_number} "
                "annorlunda än paket A – manuell prövning")
        for key, share in shares.items():
            allocated[invoice_id][key] = allocated[invoice_id].get(key, ZERO) + share
        receipts.append(receipt)
        additions_src.extend((allocation, event, invoice, line) for allocation, line in group["allocations"])

    additions = _additions(session, month, end, additions_src)
    late = {allocation.id for allocation, event, _, _ in additions_src if event.received_date < month}
    in_month = (BankEvent.received_date >= month, BankEvent.received_date <= end)
    suspense = session.execute(
        select(PaymentAllocation.amount_sek, PaymentAllocation.basis)
        .join(BankEvent, BankEvent.id == PaymentAllocation.bank_event_id)
        .where(PaymentAllocation.kind == "suspense", *in_month)).all()
    later = session.execute(
        select(PaymentAllocation.amount_sek).join(BankEvent, BankEvent.id == PaymentAllocation.bank_event_id)
        .where(PaymentAllocation.kind == "invoice_line", BankEvent.received_date > end)).scalars().all()
    by_employer: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for a in additions:
        by_employer[a.employer_org_number] += a.premium_sek
    summary = {
        "version": VERSION, "month": month.isoformat(), "value_date": end.isoformat(),
        "opening_batch": batch.checksum, "receipts": len(receipts), "allocations": len(additions),
        "policies": len({a.policy_id for a in additions}), "payout_parts": len({a.payout_part_id for a in additions}),
        "premium_sek": _money(sum((a.premium_sek for a in additions), ZERO)),
        # Mottagna i en redan stängd månad men registrerade efter dess stängning (stoppunkten)
        "late_allocations": len(late),
        "late_sek": _money(sum((a.premium_sek for a in additions if a.payment_allocation_id in late), ZERO)),
        "guarantee_sek_per_month": str(sum((a.guarantee_sek_per_month for a in additions), Decimal(0))),
        "by_employer": {org: _money(v) for org, v in sorted(by_employer.items())},
        "bases": sorted({a.basis_code for a in additions}),
        # Avstämningskontot följer inte med: saldo för månadens inbetalningar, kvar i paket A utan effekt
        "suspense_sek": _money(sum((amount for amount, _ in suspense), ZERO)),
        "suspense_by_basis": {basis: _money(sum((a for a, b in suspense if b == basis), ZERO))
                              for basis in sorted({b for _, b in suspense})},
        "after_month_end_sek": _money(sum(later, ZERO)),
    }
    content = {"summary": summary, "additions": [a.plain() for a in additions],
               "receipts": [r.model_dump(mode="json") for r in receipts]}
    return PremiumIntake(month=month, additions=additions, summary=summary, checksum=vb.checksum(content))


def _additions(session: Session, month: date, end: date, items: list) -> list[PremiumAddition]:
    if not items:
        return []
    premium_ids = {line.premium_transaction_id for _, _, _, line in items}
    part_numbers = {tx: (basis or {}).get("payout_part") for tx, basis in session.execute(
        select(PremiumTransaction.id, PremiumTransaction.calculation_basis)
        .where(PremiumTransaction.id.in_(premium_ids)))}
    benefits = {line.benefit_id for _, _, _, line in items}
    receiving = receiving_parts(session, benefits, month, end)
    all_parts = defaultdict(dict)
    for part in session.scalars(select(PayoutPart).where(PayoutPart.benefit_id.in_(benefits))):
        all_parts[part.benefit_id][part.part_number] = part
    policies = {line.policy_id for _, _, _, line in items}
    births = {policy: birth_date(pnr) for policy, pnr in session.execute(
        select(Policy.id, InsuredPerson.personal_id_number).join(InsuredPerson, InsuredPerson.id == Policy.insured_person_id)
        .where(Policy.id.in_(policies)))}
    payers = {invoice_id: org for invoice_id, org in session.execute(
        select(Invoice.id, Employer.org_number).join(Employer, Employer.id == Invoice.employer_id)
        .where(Invoice.id.in_({invoice.id for _, _, invoice, _ in items})))}
    # S-04-ursprung får aldrig tas emot en gång till ur paket A (§6.2 p. 5)
    covered = {uuid.UUID(c) for _, _, _, line in items for c in line.covers} | premium_ids
    double = set(session.scalars(select(LedgerGuaranteePart.premium_transaction_id).where(
        LedgerGuaranteePart.origin_kind == "s04_premium", LedgerGuaranteePart.premium_transaction_id.in_(covered))))
    if double:
        raise IntakeError(f"{len(double)} fakturerade premierader finns redan i S-04:s ingående läge – samma premie "
                          "får inte summeras två gånger (§6.2 p. 5)")
    try:
        guarantee = _Guarantee([r for f in GUARANTEE_FAMILIES for r in _adopted(session, f)])
        basis = guarantee.basis_on(end)
    except ExtractError as exc:
        raise IntakeError(f"Garantigrunden vid {end} kan inte läsas: {exc}") from exc
    # Steg 4: en premie på en ej startad del med beslutad plan får G_j direkt på planen (V7)
    plans = payout_plans.plans_in_force(session, {p.id for ps in all_parts.values() for p in ps.values()}, month)

    out = []
    for allocation, event, invoice, line in items:
        number = part_numbers.get(line.premium_transaction_id)
        parts = all_parts.get(line.benefit_id, {})
        if number is None and len(parts) == 1:
            number = next(iter(parts))
        part = parts.get(number)
        if part is None:
            raise IntakeError(f"Premien på {invoice.invoice_number} rad {line.line_number} saknar uttagsdel "
                              f"(nummer {number}) – manuell prövning")
        if part not in receiving.get(line.benefit_id, []):
            raise IntakeError(f"Uttagsdel {part.part_number} för premien på {invoice.invoice_number} rad "
                              f"{line.line_number} har startat under {month:%Y-%m}. Premie på en startad del blockeras "
                              "(PR-ITP1-025); ny försäkring för premien är ett senare steg")
        born = births.get(line.policy_id)
        if born is None:
            raise IntakeError(f"Födelsedatum saknas för försäkringen på {invoice.invoice_number} rad {line.line_number}")
        model_birth = born if born.day == 1 else born.replace(day=2)
        plan = plans.get(part.id)
        if plan is None:
            code, factor, g = guarantee.part(model_birth, month, allocation.amount_sek)
            plan_start = aa.reference_start(model_birth, end)
        else:
            schedule = payout_plans.schedule_of(plan)
            code, plan_start = basis.code, schedule.first_right
            factor = payout_plans.factor(guarantee.models[code], model_birth, end, schedule)
            g = allocation.amount_sek / factor
        out.append(PremiumAddition(
            payment_allocation_id=allocation.id, bank_event_id=event.id, invoice_number=invoice.invoice_number,
            line_number=line.line_number, premium_transaction_id=line.premium_transaction_id,
            payout_part_id=part.id, policy_id=line.policy_id, employer_org_number=payers[invoice.id],
            premium_sek=allocation.amount_sek, period_month=line.period_month, received_month=month, value_date=end,
            plan_start=plan_start, basis_code=code, basis_checksum=basis.checksum,
            factor=_q(factor), guarantee_sek_per_month=_q(g),
            plan_kind="plan" if plan is not None else "reference_lifelong", plan_id=plan.id if plan else None))
    return sorted(out, key=lambda a: (str(a.bank_event_id), a.invoice_number, a.line_number, str(a.payment_allocation_id)))


__all__ = ["VERSION", "IntakeError", "PremiumAddition", "PremiumIntake", "premium_intake"]
