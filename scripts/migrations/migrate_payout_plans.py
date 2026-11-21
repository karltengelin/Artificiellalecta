"""Schemamigration mot Lakebase: begäran, uttagsplaner och delning, paket B steg 4 (B-047 punkt 3, P1-PENSION-001 §5 och §12).

Skapar i en transaktion tabellerna `payout_requests`, `payout_plans` och `payout_splits`, vidgar
`ck_cases_type` med `payout_request` och `payout_review` och kopplar garantidelarna till planen
(`ledger_guarantee_parts.plan_id`, planslaget `plan`) – databasschema §7d. Inga rader ändras.
Agentrollerna får inga rättigheter (§12).

Standard är torrkörning i en skrivskyddad transaktion: visar SQL, läge, hinder och radantal, och
ändrar ingenting. En skarp körning kräver --apply och --backup med backupmappen. Körs mot den delade
databasen – stäm av enligt AGENTS.md §4.5 först och ta backup med scripts/maintenance/backup_database.py.
Varje Lakebase-ingrepp kräver Karls separata OK, och migrationen förs inte in före novembers stängning
(tidigast 2026-12-01).

Koden från steg 4 fungerar utan migrationen som steg 3: inga planer finns, och månadsstängningen
blockerar standardstarten som förut. Planer beslutas först när migrationen är införd.

Användning (från repo-roten, i .venv):
    python scripts/migrations/migrate_payout_plans.py                                     # torrkörning
    python scripts/migrations/migrate_payout_plans.py --apply --backup backups/20261202T080000Z
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from utils.db import make_engine
from utils.migration_payout_plans import migrate_payout_plans


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Genomför ändringen (annars bara torrkörning)")
    parser.add_argument("--backup", type=Path, help="Backupmapp (med manifest.json) tagen före migrationen")
    args = parser.parse_args()

    if args.apply:
        manifest = args.backup / "manifest.json" if args.backup else None
        if manifest is None or not manifest.is_file():
            raise SystemExit("Ange --backup med en backupmapp från scripts/maintenance/backup_database.py (manifest.json saknas)")
        counts = json.loads(manifest.read_text(encoding="utf-8")).get("row_counts")
        if not counts:
            raise SystemExit("Backupmanifestet saknar radantal")
        print(f"Backup: {args.backup} ({counts.get('ledger_guarantee_parts', '?')} garantidelar, "
              f"{counts.get('cases', '?')} ärenden)")

    result = migrate_payout_plans(make_engine(), dry_run=not args.apply)
    if result.already_applied:
        print("Uttagsplanerna är införda – ingenting gjort.")
        return
    print("--- MIGRERAT ---" if result.applied else "--- TORRKÖRNING (skrivskyddad transaktion, inget ändrat) ---")
    for statement in result.statements:
        print(statement.rstrip() + ";\n")
    print("Läge: " + ", ".join(f"{k}={'ja' if v else 'nej'}" for k, v in result.state.items()))
    print("Hinder:" if result.problems else "Hinder: inga")
    for problem in result.problems:
        print(f"  {problem}")
    print("Radantal" + (" efter migrationen" if result.applied else "") + ":")
    for name, count in result.row_counts.items():
        print(f"  {name}: {count}")
    if not result.applied:
        print("Kör med --apply --backup <mapp> för att genomföra – först efter Karls OK och novembers stängning.")


if __name__ == "__main__":
    main()
