"""Render local Markdown slides. No database, model or gateway is contacted."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from reporting.presentation import main

if __name__ == "__main__":
    main()
