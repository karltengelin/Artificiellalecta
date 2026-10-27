"""Sätt en lokal operatörslösenfras interaktivt; inga databasanrop."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from web.provision_operator import main

if __name__ == "__main__":
    main()
