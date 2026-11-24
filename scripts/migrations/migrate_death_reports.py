"""Schemamigration mot Lakebase: dödsfallsbesked, avräkning och dödsbo, paket B steg 7 (B-055, P1-PENSION-001 §12).

Skapar i en transaktion tabellerna `death_reports`, `death_settlements`, `pension_claim_reversals` och
`estate_authorities`, vidgar `ck_ledger_capital_entries_reason` med `death_reversal`,
`ck_ledger_capital_entries_accounts` med arvsvinstpoolen, `ck_ledger_guarantee_parts_reason` med `death`,
`ck_cases_type` med `death_report`, `death_recovery` och `inheritance_pool` och `ck_cases_subject` med
`inheritance_pool` – databasschema §7g. Inga rader ändras. Agentrollerna får inga rättigheter (§12, Y11).

Standard är torrkörning i en skrivskyddad transaktion: visar SQL, läge, hinder och radantal, och
ändrar ingenting. En skarp körning kräver --apply och --backup med backupmappen. Körs mot den delade
databasen – stäm av enligt AGENTS.md §4.5 först och ta backup med scripts/maintenance/backup_database.py.
Varje Lakebase-ingrepp kräver Karls separata OK. Ordningen i Lakebase är novembers stängning,
migrationerna för steg 4, 5 och 6 och sedan denna, var och en efter eget OK (Y12). Räkna först personer
med status `deceased` med scripts/simulation/paket_b_steg7/survey.py: var och en behöver ett besked innan
nästa stängning kan bokas.

Koden från steg 7 fungerar utan migrationen som steg 6: inga besked finns, och månadsstängningen har
samma sektion, kontroller och kontrollsumma som förut (B-052, Y13).

Användning (från repo-roten, i .venv):
    python scripts/migrations/migrate_death_reports.py                                     # torrkörning
    python scripts/migrations/migrate_death_reports.py --apply --backup backups/20261203T090000Z
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from utils.db import make_engine
from utils.migration_death_reports import migrate_death_reports


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
        print(f"Backup: {args.backup} ({counts.get('ledger_capital_entries', '?')} kapitalposter, "
              f"{counts.get('cases', '?')} ärenden)")

    result = migrate_death_reports(make_engine(), dry_run=not args.apply)
    if result.already_applied:
        print("Dödsfallstabellerna är införda – ingenting gjort.")
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
        print("Kör med --apply --backup <mapp> för att genomföra – först efter Karls OK och steg 6:s migration.")


if __name__ == "__main__":
    main()
