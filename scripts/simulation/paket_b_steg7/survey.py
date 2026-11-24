"""Skrivskyddad översikt före steg 7:s migration och nästa stängning (paket B steg 7, P1-PENSION-001 §9.1, Y12).

Räknar i en `READ ONLY`-transaktion (Postgres):

- personer med status `deceased`, och hur många av dem som har uttagsdelar i journalen, en månadsrätt eller ett
  bankuppdrag. Före steg 7 saknar de besked; var och en behöver ett verifierat besked (`register_death_report`)
  innan nästa stängning avräknar dem, annars blockeras en standardstart och bankuppdragen (`deceased`);
- efter migrationen: gällande besked per läge, avräknade delar, återföringar, arvsvinstpoolens saldo och
  öppna ärenden `death_report`, `death_recovery` och `inheritance_pool`;
- med `--month`: vad stängningen av månaden gör med steg 7 – avräkningar, återföringar, poolens in- och
  utflöde och kontrollerna *dödsfall* och *arvsvinstpool*.

Inga personuppgifter skrivs ut, bara antal, summor och uttagsdelarnas id. Ändrar ingenting; i Lakebase krävs
ändå Karls OK för körningen och samordning enligt AGENTS.md §4.5.

    python scripts/simulation/paket_b_steg7/survey.py
    python scripts/simulation/paket_b_steg7/survey.py --month 2026-12-01

Databasen väljs med DATABASE_URL. Resultatet skrivs till huvudkatalogens
`logs/simulation/paket-b-steg7/survey_<dialekt>.json`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--month", type=date.fromisoformat, help="Räkna också stängningen av månaden (ÅÅÅÅ-MM-01)")
args = parser.parse_args()

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from models import Case, InsuredPerson, PensionClaim
from services import death_reports as dr
from services import month_close as mc
from services import pension_claims as pc
from services.operations.common import today
from utils.db import make_engine

STEPS = ("dödsfall", "arvsvinstpool", "kapital totalt", "garanti totalt", "skuld och bolagskonto", "levandestatus")


def _main_checkout() -> Path:
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO_ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent


engine = make_engine()
with engine.connect() as conn:
    if engine.dialect.name == "postgresql":
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    with Session(bind=conn) as session:
        names = set(inspect(conn).get_table_names())
        steg7 = dr.deaths_present(session)
        deceased = session.scalars(select(InsuredPerson.id).where(InsuredPerson.status == "deceased")).all()
        parts = dr.parts_of_persons(session, deceased) if deceased else {}
        claims = 0
        if pc.claims_present(session) and parts:
            claims = session.scalar(select(func.count()).select_from(PensionClaim)
                                    .where(PensionClaim.payout_part_id.in_(list(parts))))
        report = {"steg7_migration": steg7, "deceased_persons": len(deceased),
                  "deceased_with_parts": len(set(parts.values())), "deceased_parts": len(parts),
                  "deceased_claims": claims}
        if steg7:
            reports = dr.current_reports(session)
            settled = dr.settlements(session)
            report |= {
                "reports": dict(Counter(r.status for r in reports.values())),
                "deceased_without_verified_report": sum(
                    1 for p in deceased if (reports.get(p) is None or reports[p].status != "verified")),
                "settled_parts": len(settled), "reversed_claims": len(dr.reversed_claims(session)),
                "open_cases": {t: session.scalar(select(func.count()).select_from(Case).where(
                    Case.case_type == t, Case.status != "closed")) for t in ("death_report", "death_recovery",
                                                                             "inheritance_pool")}}
        elif deceased:
            report["note"] = ("Personer med status deceased saknar besked före steg 7. Var och en behöver ett "
                              "verifierat besked innan nästa stängning kan avräkna dem (Y12).")
        if args.month is not None and "ledger_batches" in names:
            try:
                plan = mc.plan_month(session, args.month, today())
            except mc.CloseError as exc:
                report["close"] = {"blocked": str(exc)}
            else:
                summary = plan.summary()
                death = summary.get("death") or {}
                report["close"] = {
                    "month": args.month.isoformat(), "status": summary["status"], "passed": summary["passed"],
                    "problems": summary["problems"],
                    "settlements": len(death.get("settlements", [])), "reversals": len(death.get("reversals", [])),
                    "waiting": len(death.get("waiting", [])), "recoveries": len(death.get("recoveries", [])),
                    "withheld_premiums": len(death.get("withheld_premiums", [])),
                    "pool": death.get("pool"),
                    "settled_parts": sorted(s["payout_part_id"] for s in death.get("settlements", [])),
                    "controls": {c["step"]: {"passed": c["passed"], "detail": c["detail"]} for c in summary["controls"]
                                 if c["step"] in STEPS}}
    conn.rollback()

out = _main_checkout() / "logs" / "simulation" / "paket-b-steg7"
out.mkdir(parents=True, exist_ok=True)
(out / f"survey_{engine.dialect.name}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                                                     default=str), encoding="utf-8")
print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
if not steg7:
    print("Steg 7:s migration är inte införd: stängningen redovisar som steg 6.")
