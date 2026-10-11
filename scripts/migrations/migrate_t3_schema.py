"""Schemamigration för Fas 1f T3 mot Lakebase (02_system/databasschema.md §12).

Skapar tabellen salary_reports och lägger till premium_transactions.
corrects_transaction_id (FK, CHECK, index) i en transaktion. Ändrar inga
befintliga rader och kontrollerar radantalen före och efter. Idempotent: en
redan migrerad databas lämnas orörd; en delvis migrerad stoppar.

Körs mot den delade databasen – stäm av enligt AGENTS.md §4.5 först och ta
backup med scripts/maintenance/backup_database.py. En skarp körning kräver --backup med
backupmappen, så att den inte kan köras utan backup.

Användning (från repo-roten, i .venv):
    python scripts/migrations/migrate_t3_schema.py --dry-run
    python scripts/migrations/migrate_t3_schema.py --backup backups/20261011T120000Z
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from utils.db import make_engine  # noqa: E402
from utils.migration_t3 import migrate_t3  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Visa SQL och radantal, ändra ingenting")
    parser.add_argument("--backup", type=Path, help="Backupmapp (med manifest.json) tagen före migrationen")
    args = parser.parse_args()

    if not args.dry_run:
        manifest = args.backup / "manifest.json" if args.backup else None
        if manifest is None or not manifest.exists():
            raise SystemExit("Ange --backup med en backupmapp från scripts/maintenance/backup_database.py (manifest.json saknas)")
        counts = json.loads(manifest.read_text(encoding="utf-8"))["row_counts"]
        print(f"Backup: {args.backup} ({counts.get('premium_transactions', '?')} premietransaktioner)")

    result = migrate_t3(make_engine(), dry_run=args.dry_run)
    if result.already_applied:
        print("Databasen är redan migrerad – ingenting gjort.")
        return
    print("--- DRY-RUN (inget ändrat) ---" if args.dry_run else "--- MIGRERAT ---")
    for statement in result.statements:
        print(statement.rstrip() + ";\n")
    print("Radantal" + (" (oförändrade)" if result.applied else "") + ":")
    for name, count in result.row_counts.items():
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
