"""Tar en backup av hela databasen (Lakebase via DATABASE_URL) till filer.

Skriver en mapp `backups/<tidsstämpel>/` med en JSONL-fil per tabell och
`manifest.json`. Mappen är gitignorerad – backupen innehåller (fiktiva)
personuppgifter och ska inte in i repot. Bara läsning mot databasen.

Kör regelbundet, t.ex. via Windows Schemaläggaren, och alltid före större
ändringar. Återställning: scripts/maintenance/restore_database.py.

Användning (från repo-roten, i .venv):
    python scripts/maintenance/backup_database.py
    python scripts/maintenance/backup_database.py --target D:/backup/artificiellalecta
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from utils.backup import backup_database  # noqa: E402
from utils.db import make_engine  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", type=Path, default=REPO_ROOT / "backups", help="Rotmapp för backuper")
    args = parser.parse_args()

    target = backup_database(make_engine(), args.target)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    print(f"Backup skriven till {target}")
    for name, count in manifest["row_counts"].items():
        print(f"  {name}: {count} rader")


if __name__ == "__main__":
    main()
