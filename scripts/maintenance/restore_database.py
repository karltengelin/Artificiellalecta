"""Återställer en backup (från scripts/maintenance/backup_database.py) till databasen.

Skapar saknade tabeller och läser in alla rader. Avbryter om någon av
tabellerna redan innehåller data – inget skrivs över. Används t.ex. om
Lakebase-projektet försvinner: skapa nytt projekt, uppdatera DATABASE_URL,
kör det här skriptet.

Körs mot den delade databasen – stäm av enligt AGENTS.md §4.5 först.

Användning (från repo-roten, i .venv):
    python scripts/maintenance/restore_database.py backups/20261011T120000Z
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from utils.backup import restore_database  # noqa: E402
from utils.db import make_engine  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="Backupmapp med manifest.json")
    args = parser.parse_args()

    restored = restore_database(make_engine(), args.source)
    print(f"Återställt från {args.source}:")
    for name, count in restored.items():
        print(f"  {name}: {count} rader")


if __name__ == "__main__":
    main()
