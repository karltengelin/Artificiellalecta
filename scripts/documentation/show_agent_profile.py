"""Visar en agents effektiva profil enligt körpolicyn (Fas 3b-1/3b-2).

Läser src/agents/ecosystem.yaml, tjänstelagrets åtkomstregister och produktreglernas
status och skriver ut vilka verktyg agenten får utföra, bara föreslå eller inte ser –
med samtliga skäl när ett verktyg är dolt. Visar också operationer som ingen podd
mappar. Kräver ingen databasanslutning och inga modellanrop; ändrar ingenting.

Profilen visas utan uppdrag: utan execution_scope är verktyg med personuppgifter dolda.

Användning (från repo-roten, i .venv):
    python scripts/documentation/show_agent_profile.py                    # case_handler i dag
    python scripts/documentation/show_agent_profile.py case_handler --date 2026-11-01
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agents import Ecosystem, SkillRegistry, compile_profile  # noqa: E402
from services import MemoryEventLog, ProductRuleCatalog, ServiceLayer, default_registry  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("agent", nargs="?", default="case_handler", help="Agent-id i ecosystem.yaml")
    parser.add_argument("--date", type=date.fromisoformat, help="Pröva regelstatus mot detta datum (ÅÅÅÅ-MM-DD)")
    args = parser.parse_args()

    eco = Ecosystem.load()
    service = ServiceLayer(events=MemoryEventLog(), rules=ProductRuleCatalog(today=args.date))
    profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), service, agent_id=args.agent)
    print(profile.explain())


if __name__ == "__main__":
    main()
