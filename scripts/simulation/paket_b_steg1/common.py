"""Gemensamma sökvägar för körskripten för paket B steg 1 i Lakebase (B-047, B-048, P1-PENSION-001 §4).

Skripten importerar verksamhetskoden ur `src/` i den checkout de ligger i. Utdata skrivs till
huvudkatalogens `logs/simulation/paket-b-steg1/`, även när skriptet körs från en worktree.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))


def _main_checkout() -> Path:
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO_ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent


OUT = _main_checkout() / "logs" / "simulation" / "paket-b-steg1"
OUT.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    print(OUT)
