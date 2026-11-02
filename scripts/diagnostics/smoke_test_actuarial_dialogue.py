"""Röktesta öppen aktuariedialog mot riktig modell i ett separat demobestånd.

Startar inga publika tjänster och använder inte Lakebase-beståndet.
--run-model är ett aktivt val: körningen använder aktuarieteamets budget.
"""

import argparse
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-model", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "tmp/actuarial-smoke")
    args = parser.parse_args()
    if not args.run_model:
        print("Ingen körning. Ange --run-model för ett betalt modellanrop mot separat lokal övningsdata.")
        return
    from agents.actuarial_dialogue import ActuarialDialogue
    from ai import AIClient
    from services import Actor, ServiceLayer
    from services.db import session_factory_for
    from web.database import demo_engine

    args.output_dir.mkdir(parents=True, exist_ok=True)
    service = ServiceLayer(session_factory=session_factory_for(demo_engine(args.output_dir / "smoke.db")))
    dialog = ActuarialDialogue(service, service, AIClient(), journal_dir=args.output_dir / "journal")
    ident, actor = uuid4().hex, Actor.human("smoke_operator")
    message = ("Undersök grunden SIM-R-2026-01 med katalog och grundläsning. Visa modellens överlevnad "
               "för födda 1960 mellan ålder 50 och 110. Skapa ett diagram och en kort rapport med diagrammet. "
               "Förklara vad som krävs för en prövning mot utfall. Ingen ny grund ska föreslås. "
               "Slutsvaret kan vara utan numeriska uppgifter, med analysreferenser till leveranserna.")
    turn_id = dialog.submit(ident, message, actor=actor, key=uuid4().hex)
    dialog.process(turn_id)
    view = dialog.view(ident, actor)
    turn = view["turns"][0]
    kinds = {d["kind"] for d in view["deliveries"]}
    print(f"Dialog {ident}; status={turn['status']}; kostnad={turn['result'].get('cost_usd', 'okänd')} USD")
    print("Leveranser: " + ", ".join(sorted(kinds)))
    print(turn["result"].get("summary", ""))
    if turn["status"] != "completed" or not {"data", "analysis", "chart", "report"} <= kinds:
        raise SystemExit("Röktestet uppfyllde inte acceptansen; kontrollera körjournal och leveranser")
    print("Godkänt: katalog/grund, analys, diagram och rapport via ordinarie harness och riktig modell.")


if __name__ == "__main__":
    main()
