"""Schemamigration mot Lakebase: premieflödet, paket A steg 8 (B-046, P1-PREMIE-001 §11, databasschema.md §12).

Skapar `salary_files`, `invoices`, `invoice_lines`, `bank_events` och `payment_allocations` tomma,
med index och villkor, och byter tre CHECK-villkor på `cases`: de nya ärendetyperna, kanalen
`system` och undantaget att `payment_unmatched` får sakna försäkrad och arbetsgivare. Allt i en
transaktion. `premium_transactions` ändras inte. Agentrollerna får inga rättigheter.

Standard är torrkörning i en skrivskyddad transaktion: visar SQL, villkorens nuvarande
definitioner, schemaskillnader, hinder och radantal, och ändrar ingenting. En skarp körning kräver
--apply och --backup med backupmappen, så att den inte kan köras utan backup. Körs mot den delade
databasen – stäm av enligt AGENTS.md §4.5 först och ta backup med
scripts/maintenance/backup_database.py. Varje Lakebase-ingrepp kräver Karls separata OK (§11).

Användning (från repo-roten, i .venv):
    python scripts/migrations/migrate_premium_flow.py                                     # torrkörning
    python scripts/migrations/migrate_premium_flow.py --apply --backup backups/20261108T120000Z
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from utils.db import make_engine  # noqa: E402
from utils.migration_premium_flow import TABLES, migrate_premium_flow  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Inför tabellerna och villkoren (annars bara torrkörning)")
    parser.add_argument("--backup", type=Path, help="Backupmapp (med manifest.json) tagen före migrationen")
    args = parser.parse_args()

    if args.apply:
        manifest = args.backup / "manifest.json" if args.backup else None
        if manifest is None or not manifest.is_file():
            raise SystemExit("Ange --backup med en backupmapp från scripts/maintenance/backup_database.py (manifest.json saknas)")
        counts = json.loads(manifest.read_text(encoding="utf-8")).get("row_counts")
        if not counts:
            raise SystemExit("Backupmanifestet saknar radantal")
        print(f"Backup: {args.backup} ({counts.get('insured_persons', '?')} försäkrade, "
              f"{counts.get('cases', '?')} ärenden)")

    result = migrate_premium_flow(make_engine(), dry_run=not args.apply)
    if result.already_applied:
        print(f"Premieflödet är infört ({', '.join(TABLES)} och villkoren på cases) – ingenting gjort.")
        return
    print("--- MIGRERAT ---" if result.applied else "--- TORRKÖRNING (skrivskyddad transaktion, inget ändrat) ---")
    for statement in result.statements:
        print(statement.rstrip() + ";\n")
    print("Villkoren på cases före migrationen:")
    for name, definition in result.case_checks.items():
        print(f"  {name}: {definition}")
    print("Schemaskillnader i befintliga tabeller (utöver det migrationen inför):")
    for table, issues in result.drift.items():
        for issue in issues:
            print(f"  {table}: {issue}")
    if not result.drift:
        print("  inga")
    print("Hinder:" if result.problems else "Hinder: inga")
    for problem in result.problems:
        print(f"  {problem}")
    print("Radantal" + (" (oförändrade)" if result.applied else "") + ":")
    for name, count in result.row_counts.items():
        print(f"  {name}: {count}")
    if not result.applied:
        print("Kör med --apply --backup <mapp> för att genomföra – först efter Karls OK.")


if __name__ == "__main__":
    main()
