"""Uppdaterar körpolicyns skills i skillkatalogen (Fas 3b-7).

Skriver tabellen mellan markeringarna i 03_skills/skillkatalog.md: varje skill i
src/agents/ecosystem.yaml med podd, operation, typ, PII, nivå i åtkomstregistret och
behöriga agenter, samt operationer som ingen podd mappar. Kräver ingen databas och
inga modellanrop.

Kör efter ändringar i ecosystem.yaml, operationerna eller åtkomstregistret.
tests/test_agents_listing.py fallerar om katalogen inte är aktuell.

Användning (från repo-roten, i .venv):
    python scripts/documentation/list_skills.py           # skriver katalogen
    python scripts/documentation/list_skills.py --check   # felkod 1 om den inte är aktuell
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agents import Ecosystem
from agents.listing import DEFAULT_PATH, render_skill_table, updated_catalog
from services import AccessRegister, default_registry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Jämför bara, skriv inte")
    args = parser.parse_args()

    table = render_skill_table(Ecosystem.load(), default_registry, AccessRegister.load())
    current = DEFAULT_PATH.read_text(encoding="utf-8")
    content = updated_catalog(current, table)
    if args.check:
        if current != content:
            print(f"{DEFAULT_PATH} är inte aktuell – kör python scripts/documentation/list_skills.py")
            sys.exit(1)
        print(f"{DEFAULT_PATH} är aktuell")
        return
    DEFAULT_PATH.write_text(content, encoding="utf-8", newline="\n")
    print(f"Skrev {DEFAULT_PATH}" + (" (oförändrad)" if current == content else ""))


if __name__ == "__main__":
    main()
