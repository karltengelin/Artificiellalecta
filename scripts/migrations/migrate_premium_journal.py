"""Torrkör/inför endast de tre tomma journaltabellerna (P6-MANAD-001).

Delad Lakebase kräver Karls separata OK och samordning enligt AGENTS §4.5.
Ingen AVK-grund, mottagning, journalpost eller agenträttighet skapas här.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from utils.migration_premium_journal import migrate_premium_journal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    if args.apply:
        manifest = args.backup / "manifest.json" if args.backup else None
        if manifest is None or not manifest.is_file():
            parser.error("--apply kräver --backup med verifierat manifest.json")
        if not json.loads(manifest.read_text(encoding="utf-8")).get("row_counts"):
            parser.error("Backupmanifestet saknar radantalsunderlag")
    from utils.db import make_engine

    result = migrate_premium_journal(make_engine(), dry_run=not args.apply)
    print(json.dumps({"applied": result.applied, "already_applied": result.already_applied,
                      "statements": result.statements, "row_counts": result.row_counts}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
