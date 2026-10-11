"""Kompatibilitet för äldre demoanteckningar: använd scripts/diagnostics/smoke_test_ai.py.

Den faktiska implementationen finns endast i diagnostics/. Den här ingången
behåller samma argument och beteende utan att duplicera AI- eller affärslogik.
"""

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parent / "diagnostics" / "smoke_test_ai.py"), run_name="__main__")
