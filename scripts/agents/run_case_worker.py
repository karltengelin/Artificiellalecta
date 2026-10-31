"""Arbeta från den varaktiga ärendekön. Dagligt urval styrs av case_policy.yaml.

python scripts/agents/run_case_worker.py --db demo --once
python scripts/agents/run_case_worker.py --db demo --serve
Ingen daglig regel är påslagen i levererad konfiguration. Inga testmodeller injiceras.
"""

import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from agents.case_workspace import CaseWorkspace
from services import ProductRuleCatalog
from web.config import WebSettings
from web.database import build_services


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, choices=("demo", "svc_test", "lakebase"))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true")
    group.add_argument("--serve", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=15)
    args = parser.parse_args()
    if not 1 <= args.poll_seconds <= 60:
        parser.error("--poll-seconds ska vara 1–60")
    settings = replace(WebSettings.from_env(), database=args.db)
    trusted, agent, _ = build_services(settings)
    workspace = CaseWorkspace.build(trusted, agent)
    while True:
        # Förnya regelkatalogen över datumskiften utan att skapa nya anslutningspooler.
        trusted.rules = ProductRuleCatalog()
        try:
            count = workspace.tick()
        except Exception:  # noqa: BLE001 – inga råa databasfel/personuppgifter i driftloggen
            print("Ärendearbetaren stoppades. Kontrollera anslutning, schema och uppdragens status.")
            raise SystemExit(1) from None
        print(f"Behandlade köposter: {count}", flush=True)
        if args.once:
            return
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
