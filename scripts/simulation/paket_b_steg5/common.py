"""Gemensamma sökvägar och tidpunkter för körskripten för paket B steg 5 i Lakebase (P1-PENSION-001 §7.1, §12).

Skripten importerar verksamhetskoden ur `src/` i den checkout de ligger i. Utdata skrivs till
huvudkatalogens `logs/simulation/paket-b-steg5/`, även när skriptet körs från en worktree.

Ordningen i Lakebase (Karls val W12), varje steg efter Karls separata OK i chatten och samordning
enligt AGENTS.md §4.5:

1. **Före allt:** novembers stängning är bokad och kontrollerad (`paket_b_steg3/verify.py`), steg 4:s
   migration är införd och `paket_b_steg4/verify.py --backup <mapp>` godkänd. Steg 5 är mergat efter Karls OK.
2. `survey.py` (skrivskyddad): vad nästa stängning skulle göra med steg 5 – månadsrätter, debiteringar,
   bolagsstöd, ej finansierat och kontrollerna.
3. Backup (`scripts/maintenance/backup_database.py`) och torrkörning av
   `scripts/migrations/migrate_pension_claims.py`; därefter `--apply --backup <mapp>`.
4. `verify.py --backup <mapp>` (skrivskyddad): tabellerna tomma, villkoren på plats, journalen orörd,
   radantalen oförändrade och inga agenträttigheter.
5. Bolagskapital registreras av en människa med operationen `register_company_capital` (PB11) innan en
   månad med rätt som C inte täcker kan bokas utan ej finansierat belopp.

`compare_main.py` (lokal SQLite, rör ingen delad databas) prövar B-052: novembers stängning med main:s och
branchens kod på samma databas.
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


OUT = _main_checkout() / "logs" / "simulation" / "paket-b-steg5"
OUT.mkdir(parents=True, exist_ok=True)

#: Migrationen förs inte in före novembers stängning och steg 4:s migration (W12)
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
