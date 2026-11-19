"""Gemensamma sökvägar och väntade värden för körskripten för paket B steg 3 i Lakebase (B-047, P1-PENSION-001 §7, §12).

Skripten importerar verksamhetskoden ur `src/` i den checkout de ligger i. Utdata skrivs till
huvudkatalogens `logs/simulation/paket-b-steg3/`, även när skriptet körs från en worktree.

Ordningen i Lakebase (Karls val S6), varje skrivande steg efter Karls separata OK i chatten:

1. backup (`scripts/maintenance/backup_database.py`) och torrkörning av migrationen;
2. `scripts/migrations/migrate_month_close.py --apply --backup <mapp>`;
3. tidigast 2026-12-01, efter novembers sista bankfil: `adopt_avk.py` (granska, sedan `--apply`);
4. `close_month.py` (granska, sedan `--apply` med granskningssumman);
5. `verify.py --backup <mapp>` (skrivskyddad).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))


def _main_checkout() -> Path:
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO_ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent


OUT = _main_checkout() / "logs" / "simulation" / "paket-b-steg3"
OUT.mkdir(parents=True, exist_ok=True)

NOVEMBER = date(2026, 11, 1)
NOV_END = date(2026, 11, 30)
#: AVK, granskning och stängning tidigast när november är slut och sista bankfilen läst (S6)
EARLIEST = date(2026, 12, 1)
AVK_CODE = "AVK-SIM-2026-02"
AVK_RATE = Decimal("0.002")  # P6-MANAD-001 D5
AVK_DECISION = "P1-PENSION-001 S5 (paket B steg 3); innehåll enligt P6-MANAD-001 D5"
#: Lakebase efter steg 2 (paket B steg 2 verify.py och fall 37)
LAKEBASE = {"opening": Decimal("42087223.57"), "guarantee": Decimal("119195.6502916268"),
            "november": Decimal("51623.90"), "svenskindustries": ("5553972661", Decimal("15362.24")),
            "suspense": Decimal("36261.66")}
SCENARIO = {"basis_code": "SIM-V-2026-01", "curve_code": "FI-SIM-2026-10"}


def require_backup(path: Path | None) -> Path:
    manifest = path / "manifest.json" if path else None
    if manifest is None or not manifest.is_file():
        raise SystemExit("Ange --backup med en backupmapp från scripts/maintenance/backup_database.py "
                         "(manifest.json saknas)")
    return manifest


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    print(OUT)
