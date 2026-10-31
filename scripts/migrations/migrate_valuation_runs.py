"""Schemamigration mot Lakebase: värderingsmotorns tabeller (databasschema.md §9k, §12, A6, B-042).

Skapar `valuation_extracts`, `valuation_runs` och `valuation_results` tomma, med index och villkor,
i en transaktion. Antagandebiblioteket `valuation_bases` ska finnas först. Övriga tabeller ändras
inte och deras radantal kontrolleras. Idempotent: finns tabellerna görs ingenting.

Standard är torrkörning: visar SQL och radantal, ändrar ingenting. En skarp körning kräver --apply
och --backup med backupmappen, så att den inte kan köras utan backup. Körs mot den delade
databasen – stäm av enligt AGENTS.md §4.5 först och ta backup med
scripts/maintenance/backup_database.py. Kör därefter scripts/setup/grant_agent_role.py --team aktuarie
så att agent_aktuarie får SELECT på valuation_runs och valuation_results (inte på utdragen).

Användning (från repo-roten, i .venv):
    python scripts/migrations/migrate_valuation_runs.py                                     # torrkörning
    python scripts/migrations/migrate_valuation_runs.py --apply --backup backups/20261101T120000Z
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from utils.db import make_engine
from utils.migration_valuation_runs import migrate_valuation_runs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Skapa tabellerna (annars bara torrkörning)")
    parser.add_argument("--backup", type=Path, help="Backupmapp (med manifest.json) tagen före migrationen")
    args = parser.parse_args()

    if args.apply:
        manifest = args.backup / "manifest.json" if args.backup else None
        if manifest is None or not manifest.exists():
            raise SystemExit("Ange --backup med en backupmapp från scripts/maintenance/backup_database.py (manifest.json saknas)")
        counts = json.loads(manifest.read_text(encoding="utf-8"))["row_counts"]
        print(f"Backup: {args.backup} ({counts.get('insured_persons', '?')} försäkrade)")

    result = migrate_valuation_runs(make_engine(), dry_run=not args.apply)
    if result.already_applied:
        print("Tabellerna valuation_extracts, valuation_runs och valuation_results finns – ingenting gjort.")
        return
    print("--- MIGRERAT ---" if result.applied else "--- TORRKÖRNING (inget ändrat) ---")
    for statement in result.statements:
        print(statement.rstrip() + ";\n")
    print("Radantal" + (" (oförändrade)" if result.applied else "") + ":")
    for name, count in result.row_counts.items():
        print(f"  {name}: {count}")
    if not result.applied:
        print("Kör med --apply --backup <mapp> för att genomföra.")


if __name__ == "__main__":
    main()
