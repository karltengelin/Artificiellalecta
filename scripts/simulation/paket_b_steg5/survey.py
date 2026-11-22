"""Skrivskyddad översikt: vad nästa månadsstängning gör med steg 5 (paket B steg 5, P1-PENSION-001 §7.1 och §13).

Räknar nästa öppna månads stängning i en `READ ONLY`-transaktion (Postgres) och redovisar steg 5:s del:

- standardplaner som beslutas vid 66 och beloppsbeslut (start, januariomräkning, omstart, planändring);
- månadsrätter med debitering ur kundkapitalet, bolagsstöd och ej finansierat belopp (PR-ITP1-027, -028);
- bolagskontots och skuldens in- och utgående saldo, och om stängningen skulle öppna ett ärende
  `company_capital` (W8);
- premier som hålls utanför journalen för startade delar (W9) och kontrollerna för steg 5.

Fungerar även före steg 5:s migration: då visar den att inga anspråk finns och vad steg 4 (eller steg 3)
redovisar. Inga personuppgifter skrivs ut, bara uttagsdelarnas id, antal och summor. Ändrar ingenting;
i Lakebase krävs ändå Karls OK för körningen och samordning enligt AGENTS.md §4.5.

    python scripts/simulation/paket_b_steg5/survey.py                  # nästa öppna månad
    python scripts/simulation/paket_b_steg5/survey.py --month 2026-12-01

Databasen väljs med DATABASE_URL. Resultatet skrivs till huvudkatalogens
`logs/simulation/paket-b-steg5/survey_<månad>_<dialekt>.json`.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date

from common import OUT

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--month", type=date.fromisoformat, help="Pensionsmånaden (ÅÅÅÅ-MM-01); standard nästa öppna")
args = parser.parse_args()

from sqlalchemy.orm import Session

from services import capital_ledger as cl
from services import month_close as mc
from services import payout_plans as pl
from services import pension_claims as pc
from services.operations.common import today
from skills.calculation import actuarial_annuity as aa
from utils.db import make_engine

STEPS = ("standardstart", "standardstart väntar på steg 4", "rätt enligt plan", "månadsrätt", "förbrukade rätter",
         "skuld och bolagskonto", "startade delar", "garanti totalt")

engine = make_engine()
with engine.connect() as conn:
    if engine.dialect.name == "postgresql":
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    with Session(bind=conn) as session:
        month = args.month
        if month is None:
            opening = cl.opening_batch(session)
            last = max([opening.period_end, *cl.closed_month_ends(session)]) if opening else None
            if last is None:
                raise SystemExit("STOPP: kapitaljournalen har inget ingående läge")
            month = aa.first_month_after(last)
        steg4 = pl.plans_present(session)
        steg5 = steg4 and pc.claims_present(session)
        try:
            plan = mc.plan_month(session, month, today())
        except mc.CloseError as exc:
            raise SystemExit(f"STOPP: {exc}") from exc
        summary = plan.summary()
        company = pc.company_view(session, month) if steg5 else None
    conn.rollback()

pension = summary.get("pension")
totals = summary["totals"]
report = {
    "month": month.isoformat(), "steg4_migration": steg4, "steg5_migration": steg5, "status": summary["status"],
    "passed": summary["passed"], "problems": summary["problems"],
    "pension": None if pension is None else {
        "standard_plans": len(pension["standard_plans"]),
        "amount_decisions": dict(Counter(a["reason"] for a in pension["amounts"])),
        "claims": len(pension["claims"]), "final_settlements": sum(1 for c in pension["claims"] if c["final_settlement"]),
        "fundings_of_earlier_claims": len(pension["fundings"]),
        "state_changes": dict(Counter(s["state"] for s in pension["states"])),
        "debits_sek": totals.get("pension_debits_sek"), "claims_gross_sek": totals.get("claims_gross_sek"),
        "company_support_sek": totals.get("company_support_sek"), "unfunded_sek": totals.get("unfunded_sek"),
        "company": pension["company"], "liability": pension["liability"],
        "economic_block": None if pension["economic_block"] is None else {
            k: v for k, v in pension["economic_block"].items() if k != "claims"},
        "withheld_premiums": len(pension["withheld_premiums"]),
        "premium_review_cases": len(pension["premium_review_cases"]),
        "claim_parts": sorted({c["payout_part_id"] for c in pension["claims"]}),
    },
    "company_account": None if company is None else {k: v for k, v in company.items() if k != "insertions"}
    | {"insertions": len(company["insertions"])},
    "controls": {c["step"]: {"passed": c["passed"], "detail": c["detail"]} for c in summary["controls"]
                 if c["step"] in STEPS},
}
(OUT / f"survey_{month:%Y-%m}_{engine.dialect.name}.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
if not steg5:
    print("Steg 5:s migration är inte införd: stängningen redovisar som " + ("steg 4." if steg4 else "steg 3."))
