"""Skrivskyddad kontroll av bankdelen för period 2026-10 i Lakebase (paket A steg 8, fall 12, 13 och 15)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from decimal import Decimal

from common import OUT  # noqa: E402  (lägger också src/ på sökvägen)

from sqlalchemy import func, select  # noqa: E402

from models import Case, Invoice, InvoiceLineRecord, PremiumTransaction  # noqa: E402
from models.bank import BankEvent, PaymentAllocation  # noqa: E402
from services.db import session_factory_for  # noqa: E402
from utils.db import make_engine  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.parse_args()

run = json.loads((OUT / "bank_korning.json").read_text(encoding="utf-8"))
facit = json.loads((OUT / f"{run['file']}.facit.json").read_text(encoding="utf-8"))["facit"]
checks: list[tuple[str, bool, str]] = []
C = Decimal("0.01")


def check(name, ok, detail=""):
    checks.append((name, bool(ok), str(detail)))
    print(f"{'OK  ' if ok else 'FEL '} {name}" + (f" – {detail}" if detail else ""))


def total(rows) -> Decimal:
    return sum((Decimal(r) for r in rows), Decimal(0)).quantize(C)


f = session_factory_for(make_engine())
with f() as s:
    s.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
    events = s.scalars(select(BankEvent).order_by(BankEvent.event_id)).all()
    allocs = s.scalars(select(PaymentAllocation)).all()
    by_event = {e.id: [a for a in allocs if a.bank_event_id == e.id] for e in events}

    check("tre bankhändelser, alla ur första filen (fall 15)",
          len(events) == 3 and {e.file_reference for e in events} == {run["file"]},
          f"{len(events)} st, filer {sorted({e.file_reference for e in events})}")
    check("varje händelse är fördelad exakt en gång på sitt belopp",
          all(total(a.amount_sek for a in by_event[e.id]) == e.amount_sek for e in events))
    keys = Counter(a.allocation_key for a in allocs)
    check("inga dubbla allokeringar", max(keys.values()) == 1, f"{len(allocs)} allokeringar")

    expected = {e["event_id"]: e["expected"] for e in facit["events"]}
    for e in events:
        kinds = sorted({(a.kind, a.basis) for a in by_event[e.id]})
        want = expected[e.event_id]
        got = "allocated" if kinds == [("invoice_line", "ocr_match")] else \
              f"suspense:{kinds[0][1]}" if len(kinds) == 1 and kinds[0][0] == "suspense" else str(kinds)
        if want == "partial":
            want = "allocated"
        check(f"{e.event_id}: utfall enligt facit", got == want, f"{got}, {e.amount_sek} kr")

    for number, label in (("INV-000001", "fall 12 SvenskIndustries"), ("INV-000002", "fall 13 TeknikNorden")):
        inv = s.scalar(select(Invoice).where(Invoice.invoice_number == number))
        lines = s.scalars(select(InvoiceLineRecord).where(InvoiceLineRecord.invoice_id == inv.id)).all()
        on_lines = total(a.amount_sek for a in allocs if a.kind == "invoice_line" and a.invoice_id == inv.id)
        open_sek = (inv.total_sek - on_lines).quantize(C)
        per_line_ok = all(total(a.amount_sek for a in allocs if a.invoice_line_id == ln.id) <= ln.amount_sek
                          for ln in lines)
        ids = {r for ln in lines for r in ln.covers} | {str(ln.premium_transaction_id) for ln in lines
                                                          if ln.premium_transaction_id}
        rows = s.scalars(select(PremiumTransaction)).all()
        statuses = Counter(r.status for r in rows if str(r.id) in ids)
        paid_dates = {r.paid_date for r in rows if str(r.id) in ids and r.status == "paid"}
        if number == "INV-000001":
            half = (inv.total_sek * Decimal("0.5")).quantize(C)
            check(f"{label}: hälften fördelad, resten öppen", on_lines == half and open_sek == inv.total_sek - half,
                  f"fördelat {on_lines}, öppet {open_sek} av {inv.total_sek}")
            check(f"{label}: premieraderna förblir fakturerade", set(statuses) == {"invoiced"}, dict(statuses))
        else:
            check(f"{label}: fakturan fullt betald", on_lines == inv.total_sek and open_sek == 0,
                  f"fördelat {on_lines} av {inv.total_sek}")
            check(f"{label}: premieraderna betalda med mottagningsdagen", set(statuses) == {"paid"}
                  and paid_dates == {min(e.received_date for e in events)}, f"{dict(statuses)} {paid_dates}")
            susp = [a for a in allocs if a.kind == "suspense" and a.invoice_id == inv.id]
            check(f"{label}: andra betalningen på avstämningskontot", len(susp) == 1 and susp[0].basis == "overpayment"
                  and susp[0].amount_sek == inv.total_sek, f"{[(a.basis, a.amount_sek) for a in susp]}")
        check(f"{label}: ingen rad överbetald", per_line_ok)

    cases = s.scalars(select(Case).where(Case.case_type == "payment_unmatched")).all()
    check("ett ärende payment_unmatched för överbetalningen",
          len(cases) == 1 and cases[0].details.get("reason") == "overpayment"
          and cases[0].details.get("invoice_number") == "INV-000002" and cases[0].status == "open",
          [(c.case_number, c.details.get("reason"), c.status) for c in cases])
    old = {c.case_number: c.status for c in s.scalars(select(Case).where(
        Case.case_number.in_(["CASE-000009", "CASE-000010"])))}
    check("CASE-000009–000010 orörda och öppna", old == {"CASE-000009": "open", "CASE-000010": "open"}, old)

    received = total(e.amount_sek for e in events)
    on_lines = total(a.amount_sek for a in allocs if a.kind == "invoice_line")
    suspense = total(a.amount_sek for a in allocs if a.kind == "suspense")
    check("inbetalt = fördelat + avstämningskonto", received == on_lines + suspense,
          f"{received} = {on_lines} + {suspense}")
    invoiced = total(s.scalars(select(Invoice.total_sek)).all())
    open_total = (invoiced - on_lines).quantize(C)
    check("fakturerat − fördelat = öppna fordringar", open_total == Decimal("15362.24"),
          f"{invoiced} − {on_lines} = {open_total}")
    check("summa enligt facit", received == Decimal(facit["total_sek"]), f"{received} kr")

ok = sum(1 for _, good, _ in checks if good)
print(f"\n{ok} av {len(checks)} kontroller godkända")
(OUT / "bank_kontroll.json").write_text(json.dumps(
    {"checks": [{"name": n, "ok": g, "detail": d} for n, g, d in checks], "passed": ok, "total": len(checks)},
    indent=2, ensure_ascii=False), encoding="utf-8")
sys.exit(0 if ok == len(checks) else 1)
