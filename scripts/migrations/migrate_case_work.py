"""Ärendedialog/arbetskö: torrkörning som standard. Lakebase kräver backup och samordning."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from utils.db import make_engine
from utils.migration_case_work import migrate_case_work


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    if args.apply and (not args.backup or not (args.backup / "manifest.json").is_file()):
        parser.error("--apply kräver --backup med manifest.json från databasbackupen")
    result = migrate_case_work(make_engine(), dry_run=not args.apply)
    print("Redan infört" if result.already_applied else "Infört" if result.applied else "Torrkörning")
    for sql in result.statements:
        print(sql.strip())
    print("Befintliga radantal:", result.row_counts)


if __name__ == "__main__":
    main()
