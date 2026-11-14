"""Schemamigration mot Lakebase: den operativa kapital- och garantijournalen, paket B steg 2 (B-047, P1-PENSION-001 §6 och §12).

Skapar `ledger_batches`, `ledger_guarantee_parts`, `ledger_capital_entries` och `ledger_controls`
tomma, med index och villkor, i en transaktion. Inga befintliga tabeller eller rader ändras.
Agentrollerna får inga rättigheter på tabellerna (§12).

Standard är torrkörning i en skrivskyddad transaktion: visar SQL, schemaskillnader, hinder och
radantal, och ändrar ingenting. En skarp körning kräver --apply och --backup med backupmappen. Körs
mot den delade databasen – stäm av enligt AGENTS.md §4.5 först och ta backup med
scripts/maintenance/backup_database.py. Varje Lakebase-ingrepp kräver Karls separata OK (§12).

Ordning: migrationen körs först (§12 punkt 2). Övergången från S-04 per 2026-10-31 är ett eget
ingrepp efteråt med scripts/simulation/paket_b_steg2/open_ledger.py och ytterligare OK (punkt 3).
Koden från steg 2 fungerar utan tabellerna: värderingen och P6-MANAD-001 läser då S-04 som förut.

Användning (från repo-roten, i .venv):
    python scripts/migrations/migrate_capital_ledger.py                                     # torrkörning
    python scripts/migrations/migrate_capital_ledger.py --apply --backup backups/20261115T120000Z
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from utils.db import make_engine
from utils.migration_capital_ledger import TABLES, migrate_capital_ledger


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Inför tabellerna (annars bara torrkörning)")
    parser.add_argument("--backup", type=Path, help="Backupmapp (med manifest.json) tagen före migrationen")
    args = parser.parse_args()

    if args.apply:
        manifest = args.backup / "manifest.json" if args.backup else None
        if manifest is None or not manifest.is_file():
            raise SystemExit("Ange --backup med en backupmapp från scripts/maintenance/backup_database.py (manifest.json saknas)")
        counts = json.loads(manifest.read_text(encoding="utf-8")).get("row_counts")
        if not counts:
            raise SystemExit("Backupmanifestet saknar radantal")
        print(f"Backup: {args.backup} ({counts.get('premium_transactions', '?')} premier, "
              f"{counts.get('payout_parts', '?')} uttagsdelar, {counts.get('payment_allocations', '?')} allokeringar)")

    result = migrate_capital_ledger(make_engine(), dry_run=not args.apply)
    if result.already_applied:
        print(f"Kapitaljournalen är införd ({', '.join(TABLES)}) – ingenting gjort.")
        return
    print("--- MIGRERAT ---" if result.applied else "--- TORRKÖRNING (skrivskyddad transaktion, inget ändrat) ---")
    for statement in result.statements:
        print(statement.rstrip() + ";\n")
    print("Schemaskillnader i befintliga tabeller:")
    for table, issues in result.drift.items():
        for issue in issues:
            print(f"  {table}: {issue}")
    if not result.drift:
        print("  inga")
    print("Hinder:" if result.problems else "Hinder: inga")
    for problem in result.problems:
        print(f"  {problem}")
    print("Radantal" + (" efter migrationen" if result.applied else "") + ":")
    for name, count in result.row_counts.items():
        print(f"  {name}: {count}")
    if not result.applied:
        print("Kör med --apply --backup <mapp> för att genomföra – först efter Karls OK.")


if __name__ == "__main__":
    main()
