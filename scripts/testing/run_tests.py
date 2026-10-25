"""Planera/kör testgrupper eller ett ändringsstyrt urval. Standard är att bara visa planen."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from testing.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
