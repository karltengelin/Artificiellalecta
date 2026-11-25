"""Utfall från affärstabellerna och oberoende öresfacit för den isolerade körningen."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from models import (
    BankEvent,
    Case,
    Invoice,
    InvoiceLineRecord,
    PaymentAllocation,
    Policy,
    PremiumTransaction,
    SalaryFile,
    SalaryReport,
)
from utils.checksums import canonical_hash

FACIT_VERSION = "Paket C 1.0"
# Bank, belopp per försäkring, öppet, avstämningskonto, unika bankhändelser.
FACIT = {
    "full": ("6733.13", "2025.00", "4708.13", "0.00", "0.00", 1),
    "partial": ("4000.00", "1203.01", "2796.99", "2733.13", "0.00", 1),
    "duplicate": ("6733.13", "2025.00", "4708.13", "0.00", "0.00", 1),
    "twice": ("13466.26", "2025.00", "4708.13", "0.00", "6733.13", 2),
    "unknown": ("6733.13", "0.00", "0.00", "6733.13", "6733.13", 1),
}


def observation(session, balances, *, premium_period=None):
    rows = []
    traces = []
    for line, premium, policy in session.execute(
        select(InvoiceLineRecord, PremiumTransaction, Policy)
        .join(PremiumTransaction, PremiumTransaction.id == InvoiceLineRecord.premium_transaction_id)
        .join(Policy, Policy.id == InvoiceLineRecord.policy_id).order_by(Policy.policy_number)
    ):
        invoice = session.get(Invoice, line.invoice_id)
        basis = premium.calculation_basis
        source = basis["salary_report"]
        report = session.get(SalaryReport, UUID(source["id"]))
        file_ref, _, row_number = report.source_reference.rpartition(":")
        salary = session.scalars(select(SalaryFile).where(SalaryFile.file_reference == file_ref)).one()
        payments = session.execute(
            select(PaymentAllocation, BankEvent).join(BankEvent, BankEvent.id == PaymentAllocation.bank_event_id)
            .where(PaymentAllocation.invoice_line_id == line.id).order_by(BankEvent.event_id)
        ).all()
        received = sum((allocation.amount_sek for allocation, _ in payments), Decimal("0.00"))
        rows.append({"policy": policy.policy_number, "premium": str(premium.amount_sek), "line": str(line.amount_sek),
                     "allocated": str(received), "status": premium.status, "paid_date": premium.paid_date})
        traces.append({"policy": policy.policy_number, "benefit": str(line.benefit_id), "part": basis["payout_part"],
                       "file": file_ref, "row": int(row_number), "salary_version": report.version,
                       "salary_id": str(report.id), "premium_id": str(premium.id), "period": str(report.period_month),
                       "rule": basis["rule_package"], "parameters": basis["parameters"], "review": salary.review_digest,
                       "operator": salary.decided_by, "invoice": invoice.invoice_number, "ocr": invoice.ocr_reference,
                       "invoice_line": line.line_number, "due": str(invoice.due_date), "issued": str(invoice.invoice_date),
                       "receipts": [{"allocation": str(a.id), "event": e.event_id, "received": str(e.received_date),
                                     "amount": str(a.amount_sek)} for a, e in payments]})
    counts = {m.__tablename__: session.scalar(select(func.count()).select_from(m))
              for m in (SalaryReport, PremiumTransaction, Invoice, InvoiceLineRecord, BankEvent, PaymentAllocation)}
    if premium_period is not None:
        counts["premium_transactions"] = session.scalar(select(func.count()).select_from(PremiumTransaction)
                                                        .where(PremiumTransaction.period_month == premium_period))
    cases = [{"case": c.case_number, "type": c.case_type, "date": str(c.received_date), "status": c.status,
              "amount": c.details.get("open_sek") or c.details.get("unallocated_sek")}
             for c in session.scalars(select(Case).order_by(Case.case_number))]
    return {"balances": balances, "rows": rows, "traces": traces, "counts": counts, "cases": cases}


def verify(observed, scenario, *, december=False, rejected=False):
    """Varje avvikelse får en namngiven rad. Ingen beräkning hämtas från motparten."""
    failures = []

    def check(label, actual, expected):
        if actual != expected:
            failures.append(f"{label}: väntat {expected}, fick {actual}")

    totals = observed["balances"]
    counts = observed["counts"]
    if rejected:
        for key, value in counts.items():
            check(key, value, 0)
        check("avslagsärende", [c["type"] for c in observed["cases"]], ["salary_file_deviation"])
        return failures
    bank, first, second, balance, suspense, events = FACIT[scenario]
    for field, expected in (("bank_total_sek", bank), ("allocated_sek", str(Decimal(first) + Decimal(second))),
                            ("invoiced_sek", "6733.13"), ("receivables_sek", balance), ("suspense_sek", suspense)):
        check(field, Decimal(totals[field]), Decimal(expected))
    check("avstämd", totals["balanced"], True)
    for table, expected in (("salary_reports", 2), ("premium_transactions", 2), ("invoices", 1),
                            ("invoice_lines", 2), ("bank_events", events),
                            ("payment_allocations", (0 if scenario == "unknown" else 2) + int(suspense != "0.00"))):
        check(table, counts[table], expected)
    check("försäkringar", [r["policy"] for r in observed["rows"]], ["AL-000001", "AL-000002"])
    check("antal källkedjor", len(observed["traces"]), 2)
    for row, trace, premium, received in zip(observed["rows"], observed["traces"], ("2025.00", "4708.13"), (first, second)):
        paid = received == premium
        for field, expected in (("premium", premium), ("line", premium), ("allocated", received),
                                ("status", "paid" if paid else "invoiced"),
                                ("paid_date", "2026-11-30" if paid else None)):
            check(f"{row['policy']} {field}", row[field], expected)
        check("fakturadag", trace["issued"], "2026-11-25")
        check("förfallodag", trace["due"], "2026-12-28")
        check("mottagare", trace["part"], 1)
        check("löneversion", trace["salary_version"], 1)
        check("ursprungsperiod", trace["period"], "2026-10-01")
        check("mottagningsdagar", [r["received"] for r in trace["receipts"]],
              ["2026-11-30"] if Decimal(received) else [])
        check("spårbart beslut", bool(trace["review"] and trace["operator"] and trace["parameters"]), True)
    expected_cases = []
    if suspense != "0.00":
        expected_cases.append(("payment_unmatched", "2026-11-30", suspense))
    if december and balance != "0.00":
        expected_cases.append(("payment_overdue", "2026-12-29", balance))
    check("ärenden", [(c["type"], c["date"], c["amount"]) for c in observed["cases"]], expected_cases)
    return failures


def business_hash(observed):
    """Tekniska radnummer och UUID:n kan bytas när A skapar en ny faktura."""
    traces = []
    for trace in observed["traces"]:
        stable = {k: trace[k] for k in ("policy", "part", "file", "row", "salary_version", "period", "rule",
                                         "parameters", "invoice", "issued", "due", "ocr")}
        stable["receipts"] = [{k: r[k] for k in ("event", "received", "amount")} for r in trace["receipts"]]
        traces.append(stable)
    return canonical_hash({**observed, "traces": traces})
