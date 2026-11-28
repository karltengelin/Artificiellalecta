"""Paket B steg 9 punkt 3: de 35 nya personerna med fribrev och startpremie (B-057 Q1–Q3).

Standard är granskning i en `READ ONLY`-transaktion. Den visar arbetsgivaren, försäkringsnumren,
eventuella krockar och granskningssumman (`review_checksum`). Ingenting skrivs. Den skarpa körningen lägger
till hela beståndet i en transaktion med den granskade summan (`simulation.pension_population`). Samma
innehåll igen ger ingen ny effekt, och en krock stoppar allt.

    python scripts/simulation/paket_b_steg9/add_population.py                                   # granskning
    python scripts/simulation/paket_b_steg9/add_population.py --apply --backup backups/<mapp> --reviewed-checksum <summa>

Databasen väljs med DATABASE_URL. Resultatet skrivs till huvudkatalogens `logs/simulation/paket-b-steg9/`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import engine, read_only, require_backup, write

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--apply", action="store_true", help="Lägg till beståndet (annars bara granskning)")
parser.add_argument("--backup", type=Path, help="Backupmapp (manifest.json) tagen före punkten")
parser.add_argument("--reviewed-checksum", help="review_checksum ur granskningen")
args = parser.parse_args()

from sqlalchemy.orm import Session

from simulation import pension_population as pop

eng = engine()
with read_only(eng) as s:
    summary = pop.plan_population(s).summary()
write("add_population_preview", eng, summary)
print(json.dumps({k: v for k, v in summary.items() if k != "policy_numbers"}, indent=2, ensure_ascii=False))
if summary["already_added"]:
    print("Beståndet finns redan med samma innehåll – ingen ny effekt")
    raise SystemExit(0)
if summary["problems"] or summary["collisions"]:
    raise SystemExit("STOPP: tillägget har hinder eller krockar")
if not args.apply:
    print(f"GRANSKAT: kör med --apply --backup <mapp> --reviewed-checksum {summary['review_checksum']} efter Karls OK")
    raise SystemExit(0)

require_backup(args.backup)
with Session(eng) as s, s.begin():
    result, created = pop.add_population(s, args.reviewed_checksum or "")
write("add_population", eng, {**result, "created": created})
print("TILLAGT: 35 personer med fribrev och startpremie" if created else "Redan tillagt – ingen ny effekt")
