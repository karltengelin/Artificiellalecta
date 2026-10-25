"""Schemamigration för Fas 3c 3c-P1 mot Lakebase: tabellen product_parameters (02_system/databasschema.md §9h, §12, B-035).

Skapar tabellen product_parameters med startvärdena från 2023-01-01 och räknar om
varje ordinarie premierad med de lästa parametrarna. Minsta avvikelse, eller ändrade
radantal i övriga tabeller, rullar tillbaka allt. Idempotent: finns tabellen redan
görs ingenting.

Standard är torrkörning: visar SQL, radantal och kontrollen av premierna i en
transaktion som rullas tillbaka – ändrar ingenting. En skarp körning kräver --apply och
--backup med backupmappen. Körs mot den delade databasen – stäm av enligt AGENTS.md §4.5
först och ta backup med scripts/maintenance/backup_database.py.

Användning (från repo-roten, i .venv):
    python scripts/migrations/migrate_product_parameters.py                                     # torrkörning
    python scripts/migrations/migrate_product_parameters.py --apply --backup backups/20261025T120000Z
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from utils.db import make_engine  # noqa: E402
from utils.migration_product_parameters import migrate_product_parameters  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Skapa och fyll tabellen (annars bara torrkörning)")
    parser.add_argument("--backup", type=Path, help="Backupmapp (med manifest.json) tagen före migrationen")
    args = parser.parse_args()

    if args.apply:
        manifest = args.backup / "manifest.json" if args.backup else None
        if manifest is None or not manifest.exists():
            raise SystemExit("Ange --backup med en backupmapp från scripts/maintenance/backup_database.py (manifest.json saknas)")
        counts = json.loads(manifest.read_text(encoding="utf-8"))["row_counts"]
        print(f"Backup: {args.backup} ({counts.get('premium_transactions', '?')} premietransaktioner)")

    result = migrate_product_parameters(make_engine(), dry_run=not args.apply)
    if result.already_applied:
        print("Tabellen product_parameters finns redan – ingenting gjort.")
        return
    print("--- MIGRERAT ---" if result.applied else "--- TORRKÖRNING (inget ändrat) ---")
    for statement in result.statements:
        print(statement.rstrip() + ";\n")
    print(f"Startvärden: {result.seeded} parametrar från 2023-01-01")
    check = result.check
    print(f"Premier omräknade: {check.checked}, identiska: {check.checked - len(check.mismatches)}, "
          f"överhoppade (saknat IBB-år eller personnummer): {check.skipped}")
    print("Radantal" + (" (oförändrade)" if result.applied else "") + ":")
    for name, count in result.row_counts.items():
        print(f"  {name}: {count}")
    if not result.applied:
        print("Kör med --apply --backup <mapp> för att skapa tabellen.")


if __name__ == "__main__":
    main()
