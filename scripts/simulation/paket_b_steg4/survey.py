"""Skrivskyddad översikt: vad nästa månadsstängning gör med steg 4 (paket B steg 4, P1-PENSION-001 §5 och §13).

Räknar nästa öppna månads stängning i en `READ ONLY`-transaktion (Postgres) och redovisar steg 4:s del:

- delar vars ägare fyllt 66 senast månaden: med beslutad plan, med standardstart i månaden (blockerar
  tills månadsrätten finns i steg 5) och de ärenden `payout_review` stängningen skulle öppna – för
  overifierat underlag och för personer som passerat 66 utan plan (Karls val V4–V6);
- planer och delningar som genomförs i månaden, och delar som har rätt enligt plan (V3).

Fungerar även före steg 4:s migration: då visar den att inga planer finns och vad steg 3 redovisar.
Inga personuppgifter skrivs ut, bara uttagsdelarnas id och antal. Ändrar ingenting; i Lakebase krävs
ändå Karls OK för körningen och samordning enligt AGENTS.md §4.5.

    python scripts/simulation/paket_b_steg4/survey.py                  # nästa öppna månad
    python scripts/simulation/paket_b_steg4/survey.py --month 2026-12-01

Databasen väljs med DATABASE_URL. Resultatet skrivs till huvudkatalogens
`logs/simulation/paket-b-steg4/survey_<månad>_<dialekt>.json`.
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
from services.operations.common import today
from skills.calculation import actuarial_annuity as aa
from utils.db import make_engine

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
        present = pl.plans_present(session)
        try:
            plan = mc.plan_month(session, month, today())
        except mc.CloseError as exc:
            raise SystemExit(f"STOPP: {exc}") from exc
        summary = plan.summary()
    conn.rollback()

payout = summary.get("payout")
report = {
    "month": month.isoformat(), "steg4_migration": present, "status": summary["status"], "passed": summary["passed"],
    "problems": summary["problems"], "pending_66": len(summary["standard_start_pending"]),
    "payout": None if payout is None else {
        "planned_parts": len(payout["planned_parts"]), "standard_start": len(payout["standard_start"]),
        "review_cases": dict(Counter(c["reason"] for c in payout["review_cases"])),
        "plans": len(payout["plans"]), "splits": len(payout["splits"]), "with_right": len(payout["with_right"]),
        "standard_start_parts": [s["payout_part_id"] for s in payout["standard_start"]],
    },
    "controls": {c["step"]: {"passed": c["passed"], "detail": c["detail"]} for c in summary["controls"]
                 if c["step"] in ("standardstart", "standardstart väntar på steg 4", "rätt enligt plan", "garanti totalt",
                                   "startade delar")},
}
(OUT / f"survey_{month:%Y-%m}_{engine.dialect.name}.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
if not present:
    print("Steg 4:s migration är inte införd: stängningen redovisar standardstarten som i steg 3.")
