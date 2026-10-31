"""Schemamigration för A4 mot Lakebase: antagandebiblioteket `valuation_bases` (databasschema.md §9j, §12, B-042).

Skapar bara valuation_bases med index och startgrunderna (SIM-HIST/G/B/R-…, SIM-V-2026-01 och den
syntetiska kurvan FI-SIM-2026-10), i en transaktion. Ändrar inga befintliga tabeller eller rader och
kontrollerar radantal och kontrollsummor. Idempotent: finns tabellen redan görs ingenting.

Standard är torrkörning: visar SQL, startgrunder och radantal, ändrar ingenting. En skarp körning
kräver --apply och --backup med backupmappen, så att den inte kan köras utan backup. Körs mot den
delade databasen – stäm av enligt AGENTS.md §4.5 först och ta backup med
scripts/maintenance/backup_database.py. Kör därefter scripts/setup/grant_agent_role.py --team aktuarie
så att agent_aktuarie får SELECT på tabellen.

Användning (från repo-roten, i .venv):
    python scripts/migrations/migrate_valuation_bases.py                                     # torrkörning
    python scripts/migrations/migrate_valuation_bases.py --apply --backup backups/20261101T120000Z
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from utils.db import make_engine  # noqa: E402
from utils.migration_valuation_bases import migrate_valuation_bases  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Skapa tabellen (annars bara torrkörning)")
    parser.add_argument("--backup", type=Path, help="Backupmapp (med manifest.json) tagen före migrationen")
    args = parser.parse_args()

    if args.apply:
        manifest = args.backup / "manifest.json" if args.backup else None
        if manifest is None or not manifest.exists():
            raise SystemExit("Ange --backup med en backupmapp från scripts/maintenance/backup_database.py (manifest.json saknas)")
        counts = json.loads(manifest.read_text(encoding="utf-8"))["row_counts"]
        print(f"Backup: {args.backup} ({counts.get('insured_persons', '?')} försäkrade)")

    result = migrate_valuation_bases(make_engine(), dry_run=not args.apply)
    if result.already_applied:
        print("Tabellen valuation_bases finns redan – ingenting gjort.")
        return
    print("--- MIGRERAT ---" if result.applied else "--- TORRKÖRNING (inget ändrat) ---")
    for statement in result.statements:
        print(statement.rstrip() + ";\n")
    print(f"Startgrunder: {', '.join(result.seeded)}")
    print("Radantal" + (" (oförändrade)" if result.applied else "") + ":")
    for name, count in result.row_counts.items():
        print(f"  {name}: {count}")
    if not result.applied:
        print("Kör med --apply --backup <mapp> för att skapa tabellen.")


if __name__ == "__main__":
    main()
