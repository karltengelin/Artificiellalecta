"""Schemamigration mot Lakebase: månadsstängning och rättelse i kapitaljournalen, paket B steg 3 (B-047, P1-PENSION-001 §7 och §12).

Vidgar `ledger_batches` i en transaktion: slagen `month_close` och `month_correction`, kolumnen
`supersedes_id` och villkoret och de unika index som gör versionerna till en rak kedja (databasschema
§7c). Inga rader ändras och inga tabeller skapas. Agentrollerna får inga rättigheter (§12).

Standard är torrkörning i en skrivskyddad transaktion: visar SQL, läge, hinder och radantal, och
ändrar ingenting. En skarp körning kräver --apply och --backup med backupmappen. Körs mot den delade
databasen – stäm av enligt AGENTS.md §4.5 först och ta backup med scripts/maintenance/backup_database.py.
Varje Lakebase-ingrepp kräver Karls separata OK (§12).

Koden från steg 3 fungerar utan migrationen så länge ingen månad stängs: stängningen blockeras då med
hänvisning hit. Själva stängningen görs med scripts/simulation/paket_b_steg3/close_month.py.

Användning (från repo-roten, i .venv):
    python scripts/migrations/migrate_month_close.py                                     # torrkörning
    python scripts/migrations/migrate_month_close.py --apply --backup backups/20261201T080000Z
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from utils.db import make_engine
from utils.migration_month_close import TABLE, migrate_month_close


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Genomför ändringen (annars bara torrkörning)")
    parser.add_argument("--backup", type=Path, help="Backupmapp (med manifest.json) tagen före migrationen")
    args = parser.parse_args()

    if args.apply:
        manifest = args.backup / "manifest.json" if args.backup else None
        if manifest is None or not manifest.is_file():
            raise SystemExit("Ange --backup med en backupmapp från scripts/maintenance/backup_database.py (manifest.json saknas)")
        counts = json.loads(manifest.read_text(encoding="utf-8")).get("row_counts")
        if not counts:
            raise SystemExit("Backupmanifestet saknar radantal")
        print(f"Backup: {args.backup} ({counts.get('ledger_batches', '?')} verifikationer, "
              f"{counts.get('ledger_capital_entries', '?')} kapitalposter)")

    result = migrate_month_close(make_engine(), dry_run=not args.apply)
    if result.already_applied:
        print(f"Månadsstängningen är införd i {TABLE} – ingenting gjort.")
        return
    print("--- MIGRERAT ---" if result.applied else "--- TORRKÖRNING (skrivskyddad transaktion, inget ändrat) ---")
    for statement in result.statements:
        print(statement.rstrip() + ";\n")
    print("Läge: " + ", ".join(f"{k}={'ja' if v else 'nej'}" for k, v in result.state.items()))
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
