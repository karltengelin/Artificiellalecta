"""Gemensamma sökvägar och tidpunkter för körskripten för paket B steg 4 i Lakebase (P1-PENSION-001 §5, §12).

Skripten importerar verksamhetskoden ur `src/` i den checkout de ligger i. Utdata skrivs till
huvudkatalogens `logs/simulation/paket-b-steg4/`, även när skriptet körs från en worktree.

Ordningen i Lakebase (Karls val V11), varje steg efter Karls separata OK i chatten och samordning
enligt AGENTS.md §4.5:

1. **Före allt:** novembers stängning är bokad och kontrollerad med steg 3:s skript
   (`paket_b_steg3/verify.py`), tidigast 2026-12-01, och steg 4 är mergat efter Karls OK.
2. `survey.py` (skrivskyddad): vad nästa stängning skulle göra med steg 4 – standardstarter,
   ärenden för personer som passerat 66 utan plan och delar med beslutade planer.
3. Backup (`scripts/maintenance/backup_database.py`) och torrkörning av
   `scripts/migrations/migrate_payout_plans.py`; därefter `--apply --backup <mapp>`.
4. `verify.py --backup <mapp>` (skrivskyddad): tabellerna tomma, villkoren och kolumnen på plats,
   radantalen oförändrade och inga agenträttigheter.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))
# Utskrifterna har tecken som Σ och ö; en Windows-konsol med cp1252 klarar dem inte
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _main_checkout() -> Path:
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO_ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent


OUT = _main_checkout() / "logs" / "simulation" / "paket-b-steg4"
OUT.mkdir(parents=True, exist_ok=True)

NOV_END = date(2026, 11, 30)
DECEMBER = date(2026, 12, 1)
#: Migrationen förs inte in före novembers stängning (V11)
EARLIEST = date(2026, 12, 1)


def require_backup(path: Path | None) -> Path:
    manifest = path / "manifest.json" if path else None
    if manifest is None or not manifest.is_file():
        raise SystemExit("Ange --backup med en backupmapp från scripts/maintenance/backup_database.py "
                         "(manifest.json saknas)")
    return manifest


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    print(OUT)
