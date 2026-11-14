"""Skrivskyddad kontroll efter att CASE-000009–000010 avgjorts för period 2026-10 (paket A steg 8, B-046).

Kontrollerar den kompletterande filen, den sena premien och dess faktura, att ärendena är stängda med rätt utfall
och spårbara ändringar, att den okända personen inte registrerats och att periodens avstämning fortfarande går ihop.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from common import OUT  # noqa: E402  (lägger också src/ på sökvägen)

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.parse_args()

from sqlalchemy import func, select  # noqa: E402

from models import (Case, Employer, InsuredPerson, Invoice, InvoiceLineRecord, PremiumTransaction,  # noqa: E402
                    SalaryFile, SalaryReport)
from models.bank import BankEvent, PaymentAllocation  # noqa: E402
from models.operation_event import OperationEventRecord  # noqa: E402
from services.db import session_factory_for  # noqa: E402
from utils.bank_calendar import next_bank_day  # noqa: E402
from utils.db import make_engine  # noqa: E402

run = json.loads((OUT / "arenden_korning.json").read_text(encoding="utf-8"))
first = json.loads((OUT / "SIM1-5553972661-202610-S2026.facit.json").read_text(encoding="utf-8"))["facit"]
C = Decimal("0.01")
checks: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    checks.append((name, bool(ok), str(detail)))
    print(f"{'OK  ' if ok else 'FEL '} {name}" + (f" – {detail}" if detail else ""))


def total(values) -> Decimal:
    return sum((Decimal(v) for v in values), Decimal(0)).quantize(C)


f = session_factory_for(make_engine())
with f() as s:
    s.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
    emp = s.scalar(select(Employer).where(Employer.org_number == "5553972661"))
    [late_pnr] = first["missing"]
    [unknown_pnr] = first["unknown"]

    file = s.scalar(select(SalaryFile).where(SalaryFile.file_reference == run["reference"]))
    check("kompletterande fil godkänd med en rad", file is not None and file.status == "approved"
          and len(file.content["rows"]) == 1 and file.content["rows"][0]["personal_id_number"] == late_pnr,
          f"{file.file_reference if file else None}, {file.status if file else None}")

    person = s.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == late_pnr))
    reports = s.scalars(select(SalaryReport).where(SalaryReport.insured_person_id == person.id,
                                                   SalaryReport.period_month == file.period_month)).all()
    check("ett löneunderlag för den sena personen, från den kompletterande filen",
          len(reports) == 1 and reports[0].source_reference == f"{run['reference']}:1",
          [(r.source_reference, str(r.pensionable_salary_sek)) for r in reports])
    salary = reports[0].pensionable_salary_sek
    expected = (min(salary, Decimal("52125")) * Decimal("0.045")).quantize(C, ROUND_HALF_UP) \
        + (max(salary - Decimal("52125"), 0) * Decimal("0.30")).quantize(C, ROUND_HALF_UP)
    inv = s.scalar(select(Invoice).where(Invoice.invoice_number == run["invoice"]["number"]))
    lines = s.scalars(select(InvoiceLineRecord).where(InvoiceLineRecord.invoice_id == inv.id)).all()
    check("ny debetfaktura för SvenskIndustries och period 2026-10", inv.invoice_type == "debit"
          and inv.employer_id == emp.id and inv.period_month == file.period_month, inv.invoice_number)
    check("fakturan har en ordinarie rad med premien enligt trappan", len(lines) == 1
          and lines[0].line_type == "ordinary" and lines[0].amount_sek == expected and inv.total_sek == expected,
          f"lön {salary}, premie {expected}, faktura {inv.total_sek}")
    row = s.get(PremiumTransaction, lines[0].premium_transaction_id)
    check("premieraden är fakturerad", row is not None and row.status == "invoiced" and row.amount_sek == expected,
          f"{row.status if row else None} {row.amount_sek if row else None}")
    check("förfallodag nästa bankdag efter 30 dagar", inv.due_date == next_bank_day(inv.invoice_date + timedelta(days=30)),
          f"{inv.invoice_date} → {inv.due_date}")
    check("INV-000001 orörd (delbetald, rest 15 362,24 kr)", s.scalar(
        select(Invoice.total_sek).where(Invoice.invoice_number == "INV-000001")) == Decimal("30724.48"))

    cases = {c.case_number: c for c in s.scalars(select(Case).where(
        Case.case_number.in_(["CASE-000009", "CASE-000010", "CASE-000011"])))}
    c10, c9, c11 = cases["CASE-000010"], cases["CASE-000009"], cases["CASE-000011"]
    check("CASE-000010 stängt som approved med motivering", c10.status == "closed" and c10.outcome == "approved"
          and run["reference"] in (c10.closing_note or ""), c10.outcome)
    executed = s.scalars(select(OperationEventRecord.operation).where(
        OperationEventRecord.case_id == "CASE-000010", OperationEventRecord.outcome == "executed")).all()
    check("intag, godkännande och fakturering registrerade i CASE-000010",
          {"import_salary_file", "approve_salary_file", "create_invoice", "close_case"} <= set(executed),
          sorted(set(executed)))
    check("CASE-000009 stängt som no_action med motivering", c9.status == "closed" and c9.outcome == "no_action"
          and bool(c9.closing_note), c9.outcome)
    check("den okända personen finns inte i beståndet och fick inget löneunderlag",
          s.scalar(select(InsuredPerson.id).where(InsuredPerson.personal_id_number == unknown_pnr)) is None)
    check("CASE-000011 (överbetalningen) står kvar öppet", c11.status == "open", c11.status)
    others = s.scalar(select(func.count()).select_from(Case).where(
        Case.case_type == "salary_file_deviation", Case.status != "closed"))
    check("inga öppna filavvikelser kvar", others == 0, others)

    received = total(s.scalars(select(BankEvent.amount_sek)).all())
    allocs = s.scalars(select(PaymentAllocation)).all()
    on_lines = total(a.amount_sek for a in allocs if a.kind == "invoice_line")
    suspense = total(a.amount_sek for a in allocs if a.kind == "suspense")
    invoiced = total(s.scalars(select(Invoice.total_sek)).all())
    check("inbetalt = fördelat + avstämningskonto (oförändrat)", received == on_lines + suspense
          and received == Decimal("87885.56"), f"{received} = {on_lines} + {suspense}")
    check("fakturerat − fördelat = öppna fordringar", invoiced - on_lines == Decimal("15362.24") + expected,
          f"{invoiced} − {on_lines} = {invoiced - on_lines}")

ok = sum(1 for _, good, _ in checks if good)
print(f"\n{ok} av {len(checks)} kontroller godkända")
(OUT / "arenden_kontroll.json").write_text(json.dumps(
    {"checks": [{"name": n, "ok": g, "detail": d} for n, g, d in checks], "passed": ok, "total": len(checks)},
    indent=2, ensure_ascii=False), encoding="utf-8")
sys.exit(0 if ok == len(checks) else 1)
