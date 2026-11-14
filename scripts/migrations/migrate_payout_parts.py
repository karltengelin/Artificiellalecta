"""Schemamigration mot Lakebase: uttagsdelar och tre förlopp, paket B steg 1 (B-047, P1-PENSION-001 §4 och §12).

Skapar `payout_parts` och `payout_part_states`, vidgar `ck_cases_type` med `payout_reconstruction`,
ger varje ålderspensionsförmån uttagsdel 1 i läget `not_started`, flyttar eventuella gamla
uttagslägen till delen med ett rekonstruktionsärende och smalnar `ck_policy_states_state` till
premieförloppets två lägen. Allt i en transaktion. Agentrollerna får inga rättigheter här; läsrätten
enligt B-048 sätts därefter med scripts/setup/grant_agent_role.py (torrkörning först).

Standard är torrkörning i en skrivskyddad transaktion: visar SQL, villkorens nuvarande
definitioner, övergångens plan, schemaskillnader, hinder och radantal, och ändrar ingenting. En
skarp körning kräver --apply och --backup med backupmappen. Körs mot den delade databasen – stäm
av enligt AGENTS.md §4.5 först och ta backup med scripts/maintenance/backup_database.py. Varje
Lakebase-ingrepp kräver Karls separata OK (P1-PENSION-001 §12).

Ordning: migrationen ska vara körd innan koden från paket B steg 1 används mot databasen, eftersom
läsningarna och premieunderlaget läser uttagsdelarna.

Användning (från repo-roten, i .venv):
    python scripts/migrations/migrate_payout_parts.py                                     # torrkörning
    python scripts/migrations/migrate_payout_parts.py --apply --backup backups/20261115T120000Z
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from utils.db import make_engine
from utils.migration_payout_parts import TABLES, migrate_payout_parts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Inför tabellerna och övergången (annars bara torrkörning)")
    parser.add_argument("--backup", type=Path, help="Backupmapp (med manifest.json) tagen före migrationen")
    args = parser.parse_args()

    if args.apply:
        manifest = args.backup / "manifest.json" if args.backup else None
        if manifest is None or not manifest.is_file():
            raise SystemExit("Ange --backup med en backupmapp från scripts/maintenance/backup_database.py (manifest.json saknas)")
        counts = json.loads(manifest.read_text(encoding="utf-8")).get("row_counts")
        if not counts:
            raise SystemExit("Backupmanifestet saknar radantal")
        print(f"Backup: {args.backup} ({counts.get('policy_benefits', '?')} förmåner, "
              f"{counts.get('policy_states', '?')} lägen, {counts.get('cases', '?')} ärenden)")

    result = migrate_payout_parts(make_engine(), dry_run=not args.apply)
    if result.already_applied:
        print(f"Uttagsdelarna är införda ({', '.join(TABLES)} och villkoren) – ingenting gjort.")
        return
    print("--- MIGRERAT ---" if result.applied else "--- TORRKÖRNING (skrivskyddad transaktion, inget ändrat) ---")
    for statement in result.statements:
        print(statement.rstrip() + ";\n")
    print("Villkoren före migrationen:")
    for name, definition in result.checks.items():
        print(f"  {name}: {definition}")
    plan = result.transition
    print(f"Övergången: {plan.benefits} ålderspensionsförmåner, {plan.parts_to_create} får uttagsdel 1 "
          f"(not_started); {len(plan.moved)} uttag flyttas från policy_states"
          + (f"; {plan.other_benefit_types} förmåner av annan typ rörs inte" if plan.other_benefit_types else ""))
    for moved in plan.moved:
        print(f"  {moved.policy_number}: {', '.join(f'{s} från {f}' for s, f, _ in moved.rows)}; "
              f"premieförloppet: {moved.premium_course}"
              + (f"; ärende {moved.case_number}" if moved.case_number else "; rekonstruktionsärende skapas"))
    print("Schemaskillnader i befintliga tabeller (utöver det migrationen inför):")
    for table, issues in result.drift.items():
        for issue in issues:
            print(f"  {table}: {issue}")
    if not result.drift:
        print("  inga")
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
