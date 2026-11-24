"""Oberoende öresfacit och bokade källspår för C:s delbetalning till B."""

from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from models import (
    BankEvent,
    Invoice,
    InvoiceLineRecord,
    LedgerCapitalEntry,
    LedgerGuaranteePart,
    PaymentAllocation,
    PayoutPart,
    Policy,
    PolicyBenefit,
    PremiumTransaction,
)
from utils.checksums import canonical_hash

# Oktober-IB har en historisk premie per del. November har +0,20 %,
# årsavgift 0,20 % och årlig skattebelastning 0,354 %, avrundade per del.
FIELDS = ("opening", "return", "fee", "tax", "premium", "closing")
EXPECTED = {
    "AL-000001": ("10000.00", "20.00", "-1.67", "-2.95", "1203.01", "11218.39"),
    "AL-000002": ("20000.00", "40.00", "-3.33", "-5.90", "2796.99", "22827.76"),
}


def report(session, receipt, balances):
    batch = UUID(receipt["batch_id"])
    failures = []

    def check(label, actual, expected):
        if actual != expected:
            failures.append(f"{label}: väntat {expected}, fick {actual}")

    postings = defaultdict(lambda: defaultdict(lambda: Decimal("0.00")))
    for entry, number in session.execute(
        select(LedgerCapitalEntry, Policy.policy_number)
        .join(PayoutPart, PayoutPart.id == LedgerCapitalEntry.payout_part_id)
        .join(PolicyBenefit, PolicyBenefit.id == PayoutPart.benefit_id)
        .join(Policy, Policy.id == PolicyBenefit.policy_id)
        .where(LedgerCapitalEntry.account == "customer_capital")
    ):
        postings[number][entry.reason] += entry.amount_sek
        if entry.reason != "opening":
            check("stängningsverifikation", entry.batch_id, batch)
    bridge = {}
    for number, amounts in sorted(postings.items()):
        amounts["closing"] = sum(amounts.values())
        bridge[number] = {key: str(amount) for key, amount in amounts.items()}
    check("kapitalbrygga per försäkring", bridge,
          {number: dict(zip(FIELDS, values)) for number, values in EXPECTED.items()})
    totals = receipt["totals"]
    close_totals = (totals["opening_sek"], totals["returns_sek"], -Decimal(totals["fees_sek"]),
                    -Decimal(totals["taxes_sek"]), totals["premiums_sek"], totals["closing_sek"])
    check("verifikationens summor", tuple(map(Decimal, close_totals)),
          tuple(sum(map(Decimal, column)) for column in zip(*EXPECTED.values())))
    check("stängningskontroller", all(c["passed"] for c in receipt["controls"]), True)
    check("nya garantidelar", totals["new_guarantee_parts"], 2)

    traces = []
    rows = session.execute(
        select(PaymentAllocation, BankEvent, InvoiceLineRecord, Invoice, PremiumTransaction, Policy,
               PayoutPart, LedgerGuaranteePart, LedgerCapitalEntry)
        .select_from(PaymentAllocation)
        .join(BankEvent, BankEvent.id == PaymentAllocation.bank_event_id)
        .join(InvoiceLineRecord, InvoiceLineRecord.id == PaymentAllocation.invoice_line_id)
        .join(Invoice, Invoice.id == InvoiceLineRecord.invoice_id)
        .join(PremiumTransaction, PremiumTransaction.id == InvoiceLineRecord.premium_transaction_id)
        .join(Policy, Policy.id == InvoiceLineRecord.policy_id)
        .join(LedgerGuaranteePart, LedgerGuaranteePart.payment_allocation_id == PaymentAllocation.id)
        .join(PayoutPart, PayoutPart.id == LedgerGuaranteePart.payout_part_id)
        .join(LedgerCapitalEntry, LedgerCapitalEntry.origin_id == LedgerGuaranteePart.id)
        .order_by(Policy.policy_number))
    for allocation, event, line, invoice, premium, policy, part, guarantee, entry in rows:
        amount = allocation.amount_sek
        check(f"{policy.policy_number} belopp", (entry.amount_sek, guarantee.premium_sek), (amount, amount))
        check("faktura och premierad", (allocation.invoice_id, guarantee.premium_transaction_id),
              (invoice.id, premium.id))
        check("förmån och uttagsdel", (premium.benefit_id, part.benefit_id, entry.payout_part_id, part.part_number),
              (line.benefit_id, line.benefit_id, part.id, premium.calculation_basis["payout_part"]))
        check("bokning", (entry.batch_id, guarantee.batch_id, entry.reason, entry.account, guarantee.origin_kind),
              (batch, batch, "premium", "customer_capital", "payment_allocation"))
        check("period och värdedag", (str(guarantee.period_month), str(guarantee.value_date),
              str(guarantee.received_month), str(event.received_date)),
              ("2026-10-01", "2026-11-30", "2026-11-01", "2026-11-30"))
        traces.append({
            "policy": policy.policy_number, "part_number": part.part_number, "part_id": str(part.id),
            "bank_source": event.source_system, "event": event.event_id, "event_id": str(event.id),
            "received_date": str(event.received_date), "period": str(guarantee.period_month),
            "invoice": invoice.invoice_number, "invoice_line": line.line_number, "line_id": str(line.id),
            "premium_id": str(premium.id), "benefit_id": str(part.benefit_id), "allocation": str(allocation.id),
            "allocated": str(amount), "capital_entry": str(entry.id), "net_premium": str(entry.amount_sek),
            "guarantee_part": str(guarantee.id), "guarantee_base": str(guarantee.premium_sek),
            "guarantee_per_month": str(guarantee.guarantee_sek_per_month), "basis": guarantee.basis_code,
            "basis_checksum": guarantee.basis_checksum, "value_date": str(guarantee.value_date)})
    check("en källkedja per allokering", [(t["policy"], t["allocated"]) for t in traces],
          [(number, values[4]) for number, values in EXPECTED.items()])
    allocation_ids = set(session.scalars(select(PaymentAllocation.id)))
    check("alla bankallokeringar bokade en gång", sorted(str(a) for a in allocation_ids),
          sorted(t["allocation"] for t in traces))
    check("bank, fördelat, rest, avstämningskonto",
          tuple(Decimal(balances[k]) for k in ("bank_total_sek", "allocated_sek", "receivables_sek", "suspense_sek")),
          tuple(map(Decimal, ("4000.00", "4000.00", "2733.13", "0.00"))))
    check("avstämda fordringar", balances["balanced"], True)
    stable = [{k: t[k] for k in ("policy", "part_number", "allocated", "net_premium", "guarantee_base",
                                  "guarantee_per_month", "basis_checksum", "value_date")} for t in traces]
    return {"bridge": bridge, "traces": traces, "balances": balances, "close": receipt,
            "hash": canonical_hash([bridge, stable, balances]), "failures": failures}
