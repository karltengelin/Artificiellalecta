"""Skrivskyddad kontroll av §7-fallen efter första operativa perioden 2026-10 (paket A steg 8 punkt 3).

Kontrollerar läget efter filintag och fakturering 2026-11-08, före bankdelen: 31 av 31 då. Efter bankdelen
2026-11-14 faller tre kontroller som förutsätter att ingen inbetalning finns (fakturerade rader, inga
betalningsärenden, inga bankhändelser). Bankdelen kontrolleras med `verify_bank_payments.py`.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from common import OUT  # noqa: E402  (lägger också src/ på sökvägen)

from sqlalchemy import func, select  # noqa: E402

from models import (Case, Employer, InsuredPerson, Invoice, InvoiceLineRecord, Policy, PolicyBenefit,  # noqa: E402
                    PremiumTransaction, SalaryFile, SalaryReport)
from services.db import session_factory_for  # noqa: E402
from utils.bank_calendar import next_bank_day  # noqa: E402
from utils.db import make_engine  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.parse_args()

PERIOD = date(2026, 10, 1)
IBB = Decimal("83400")
CEIL = (IBB * Decimal("7.5") / 12)  # 52 125
run = json.loads((OUT / "korning.json").read_text(encoding="utf-8"))
checks: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    checks.append((name, bool(ok), str(detail)))
    print(f"{'OK  ' if ok else 'FEL '} {name}" + (f" – {detail}" if detail else ""))


def cents(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), ROUND_HALF_UP)


def expected_premium(salary: Decimal, pnr: str) -> Decimal:
    born = date(int(pnr[:4]), int(pnr[4:6]), 1)
    start = date(born.year + 25, born.month, 1)      # 25-årsmånaden
    stop = date(born.year + 66, born.month, 1)       # 66-årsmånaden, ingen premie
    if not (start <= PERIOD < stop):
        return Decimal("0.00")
    return cents(min(salary, CEIL) * Decimal("0.045")) + cents(max(salary - CEIL, 0) * Decimal("0.30"))


def luhn_ok(s: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(s)):
        d = int(ch) * (2 if i % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


f = session_factory_for(make_engine())
with f() as s:
    s.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
    for org, entry in run["employers"].items():
        emp = s.scalar(select(Employer).where(Employer.org_number == org))
        print(f"\n== {emp.name} ({org})")
        facit = json.loads((OUT / f"{entry['reference']}.facit.json").read_text(encoding="utf-8")) \
            if (OUT / f"{entry['reference']}.facit.json").exists() else None
        files = s.scalars(select(SalaryFile).where(SalaryFile.employer_id == emp.id,
                                                   SalaryFile.period_month == PERIOD)).all()
        check("en fil, godkänd; samma fil igen gav samma intag (fall 6)",
              len(files) == 1 and files[0].status == "approved" and entry["fall6_same_file"],
              f"{len(files)} fil, status {files[0].status if files else '-'}")
        check("samma referens med ändrat innehåll stoppades (fall 7)",
              entry["fall7_conflict"].startswith(("ConflictError", "BlockedError")), entry["fall7_conflict"][:110])
        sf = files[0]
        rows = sf.content["rows"]
        reports = s.execute(select(SalaryReport, InsuredPerson.personal_id_number)
                            .join(InsuredPerson, InsuredPerson.id == SalaryReport.insured_person_id)
                            .where(SalaryReport.employer_id == emp.id, SalaryReport.period_month == PERIOD)).all()
        by_pnr = {pnr: r for r, pnr in reports}
        file_pnrs = {r["personal_id_number"] for r in rows}
        check("varje registrerad rad kommer från filen med källa employer och källreferens",
              all(r.source == "employer" and (r.source_reference or "").startswith(sf.file_reference)
                  for r in by_pnr.values()) and set(by_pnr) <= file_pnrs,
              f"{len(by_pnr)} löneunderlag")
        unknown = [r["personal_id_number"] for r in rows
                   if s.scalar(select(InsuredPerson.id).where(InsuredPerson.personal_id_number
                                                              == r["personal_id_number"])) is None]
        check("okänd person: ingen registrering (fall 5)", all(p not in by_pnr for p in unknown),
              f"{len(unknown)} okända")

        prem = s.execute(select(PremiumTransaction, InsuredPerson.personal_id_number)
                         .join(PolicyBenefit, PolicyBenefit.id == PremiumTransaction.benefit_id)
                         .join(Policy, Policy.id == PolicyBenefit.policy_id)
                         .join(InsuredPerson, InsuredPerson.id == Policy.insured_person_id)
                         .where(PremiumTransaction.period_month == PERIOD,
                                InsuredPerson.employer_id == emp.id)).all()
        premiums = [(p, pnr) for p, pnr in prem]
        check("en premierad per registrerat löneunderlag, typ premium",
              sorted(pnr for _, pnr in premiums) == sorted(by_pnr)
              and {p.transaction_type for p, _ in premiums} == {"premium"}, f"{len(premiums)} premierader")
        wrong = [(pnr, p.amount_sek, expected_premium(by_pnr[pnr].pensionable_salary_sek, pnr))
                 for p, pnr in premiums
                 if p.amount_sek != expected_premium(by_pnr[pnr].pensionable_salary_sek, pnr)]
        check("premien = 4,5 % upp till 7,5 IBB/12 + 30 % över, inom åldersfönstret (fall 1, 2, 18)",
              not wrong, f"avvikelser {wrong[:3]}" if wrong else
              f"lönesumma {sum(r.pensionable_salary_sek for r in by_pnr.values())}, "
              f"premiesumma {sum(p.amount_sek for p, _ in premiums)}")
        over = [pnr for _, pnr in premiums if by_pnr[pnr].pensionable_salary_sek > CEIL]
        outside = [pnr for _, pnr in premiums if expected_premium(Decimal(1), pnr) == 0]
        print(f"     lön över 7,5 IBB/12: {len(over)}; utanför åldersfönstret: {len(outside)}")
        trace = all((p.calculation_basis.get("salary_report") or {}).get("id") == str(by_pnr[pnr].id)
                    and (p.calculation_basis.get("salary_report") or {}).get("version") == by_pnr[pnr].version
                    for p, pnr in premiums)
        check("premien spåras till löneunderlagets id och version", trace)

        inv = s.scalar(select(Invoice).where(Invoice.employer_id == emp.id, Invoice.period_month == PERIOD))
        lines = s.scalars(select(InvoiceLineRecord).where(InvoiceLineRecord.invoice_id == inv.id)).all()
        positive = {p.id: p for p, _ in premiums if p.amount_sek > 0}
        zero = [pnr for p, pnr in premiums if p.amount_sek == 0]
        check("fakturaraderna = premieraderna med belopp > 0; noll ger ingen rad (fall 3)",
              {l.premium_transaction_id for l in lines} == set(positive)
              and all(l.amount_sek == positive[l.premium_transaction_id].amount_sek for l in lines),
              f"{len(lines)} rader, {len(zero)} nollpremier")
        check("fakturans summa = radernas summa = premiernas summa",
              inv.total_sek == sum(l.amount_sek for l in lines) == sum(positive[i].amount_sek for i in positive),
              f"{inv.invoice_number} {inv.total_sek} kr")
        check("premieraderna med fakturarad är invoiced",
              {positive[l.premium_transaction_id].status for l in lines} <= {"invoiced"})
        check("förfallodag = fakturadag + 30 dagar, nästa bankdag; OCR med kontrollsiffra",
              inv.due_date == next_bank_day(inv.invoice_date + timedelta(days=30)) and luhn_ok(inv.ocr_reference),
              f"{inv.invoice_date} → {inv.due_date}, OCR {inv.ocr_reference}")
        check("en faktura per arbetsgivare och period; fakturering igen gav ingen ny",
              s.scalar(select(func.count()).select_from(Invoice).where(Invoice.employer_id == emp.id,
                                                                       Invoice.period_month == PERIOD)) == 1
              and entry["invoice_again_new"] == 0)

        cases = s.scalars(select(Case).where(Case.employer_id == emp.id, Case.period_month == PERIOD)).all()
        facit = facit["facit"] if facit else None
        missing = facit["missing"] if facit else []
        check("avvikande och saknade rader blev ärenden salary_file_deviation via filen (fall 4, 5)",
              len(cases) == entry["intake"]["deviations"] + entry["intake"]["missing"]
              and {c.case_type for c in cases} <= {"salary_file_deviation"}
              and {c.status for c in cases} <= {"open"}
              and {c.channel for c in cases} <= {"employer_file"},
              ", ".join(f"{c.case_number} {c.status} {c.channel}" for c in cases) or "inga")
        check("saknad person: ingen premie och inget löneunderlag (fall 4)",
              all(p not in by_pnr for p in missing), f"saknade {len(missing)}")
        if facit:
            zero_rows = facit["zero"]
            check("uttrycklig nolla: underlag 0,00, ingen fakturarad, inget saknad-ärende (fall 3)",
                  all(by_pnr[p].pensionable_salary_sek == 0 for p in zero_rows)
                  and all(p in zero for p in zero_rows), f"{len(zero_rows)} nollor")

    receivable = sum(i.total_sek for i in s.scalars(select(Invoice).where(Invoice.period_month == PERIOD)))
    check("inga bankhändelser än; öppna fordringar = fakturerat",
          s.scalar(select(func.count()).select_from(__import__("models").BankEvent)) == 0, f"{receivable} kr öppet")
    s.rollback()

ok = sum(1 for _, o, _ in checks if o)
print(f"\n{ok} av {len(checks)} kontroller godkända")
(OUT / "kontroll.json").write_text(json.dumps([{"kontroll": n, "ok": o, "detalj": d} for n, o, d in checks],
                                              indent=2, ensure_ascii=False), encoding="utf-8")
