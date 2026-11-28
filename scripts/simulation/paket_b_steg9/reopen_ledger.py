"""Paket B steg 9 punkt 4: journalens nya ingående läge per 2026-10-31 (B-057 Q4).

Förutsättningar: `add_population.py` är körd, och ingen månad är stängd i journalen.

Standard är granskning i en `READ ONLY`-transaktion (`services.ledger_reopening.plan_reopening`). Den visar:

- det gamla läget och det nya;
- försäkringar som ändras, faller bort eller tillkommer;
- granskningssumman.

Ingenting skrivs. De befintliga försäkringarna ska ha exakt samma C och G, och bara de 35 nya ska tillkomma.

Den skarpa körningen ersätter läget i en transaktion med den granskade summan. Det gamla lägets
sammanställning sparas i körloggen (`reopen_ledger_<dialekt>.json`, nyckeln `replaced_content`). Den första
verifikationen finns också kvar i backupen. Samma nya läge igen ger ingen ny effekt.

    python scripts/simulation/paket_b_steg9/reopen_ledger.py                                   # granskning
    python scripts/simulation/paket_b_steg9/reopen_ledger.py --apply --backup backups/<mapp> --reviewed-checksum <summa>

Databasen väljs med DATABASE_URL. Resultatet skrivs till huvudkatalogens `logs/simulation/paket-b-steg9/`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import engine, read_only, require_backup, write

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--apply", action="store_true", help="Ersätt det ingående läget (annars bara granskning)")
parser.add_argument("--backup", type=Path, help="Backupmapp (manifest.json) tagen efter add_population.py")
parser.add_argument("--reviewed-checksum", help="review_checksum ur granskningen")
args = parser.parse_args()

from sqlalchemy.orm import Session

from services import capital_ledger as cl
from services import ledger_reopening as lr
from simulation import pension_population as pop

eng = engine()
with read_only(eng) as s:
    if not pop.plan_population(s).already_added:
        raise SystemExit("STOPP: beståndet är inte tillagt – kör add_population.py först")
    plan = lr.plan_reopening(s)
    summary = plan.summary()
    current = cl.opening_batch(s)
write("reopen_ledger_preview", eng, summary)
print(json.dumps({k: v for k, v in summary.items() if k not in ("added", "new")}, indent=2, ensure_ascii=False,
                 default=str))
print(f"Nytt läge: {summary['new']['totals']}; tillkommer {len(summary['added'])} försäkringar")
if current is not None and current.checksum == plan.new.checksum:
    print("Det nya läget är redan bokat – ingen ny effekt")
    raise SystemExit(0)
if not summary["passed"]:
    raise SystemExit("STOPP: " + "; ".join(summary["problems"]))
if not args.apply:
    print(f"GRANSKAT: kör med --apply --backup <mapp> --reviewed-checksum {summary['review_checksum']} efter Karls OK")
    raise SystemExit(0)

require_backup(args.backup)
with Session(eng) as s, s.begin():
    result, created = lr.apply_reopening(s, "karl", args.reviewed_checksum or "")
write("reopen_ledger", eng, {**result, "created": created})
print(f"ERSATT: nytt ingående läge {result.get('new_batch_id')}" if created else "Redan ersatt – ingen ny effekt")
