"""Lokal månadssimulator för Paket C. Kör med --help för kommandon."""

import argparse
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from services import Actor
from simulation.premium_calendar import SCENARIOS, advance, review, start

RUNS = ROOT / "logs" / "simulation" / "paket-c"


def money(value):
    return format(Decimal(value), ",.2f").replace(",", " ").replace(".", ",")


def os_user():
    if os.name == "nt":
        return subprocess.check_output(["whoami.exe"], text=True).strip()
    import pwd

    return pwd.getpwuid(os.getuid()).pw_name


def show_review(state):
    view = state["review"]
    print(f"Fil {view['file_reference']} för {view['employer_org_number']}, period {view['period_month']}")
    for row in view["rows"]:
        print(f"Rad {row['row']}: {row['outcome']}, lön {row['pensionable_salary_sek']}, "
              f"premie {row['premium_preview_sek']}, avvikelse {row['reason'] or 'ingen'}")
    print(json.dumps(view["summary"], ensure_ascii=False))
    print(f"Beslutsunderlag --revision {state['cursor']} --digest {view['review_digest']}")


def write_file(path, content):
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(content)
    Path(tmp.name).replace(path)


def publish(directory, state):
    def save(name, data):
        write_file(directory / name, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    save("manifest.json", state["manifest"])
    for key, item in state["files"].items():
        save(f"{key}.json", {**item["payload"], "_label": item["label"]})
        save(f"{key}.facit.json", {"label": item["label"], "facit": item["facit"]})
    for day, report in state["reports"].items():
        save(f"{day}.json", report)
        observed = report["observed"]
        totals = observed["balances"]
        period_title = {"2026-11-30": "Novemberavstämning", "2026-12-29": "Decemberuppföljning",
                        "decision": "Beslut om lönefilen"}[day]
        rows = [f"# {period_title} för oktoberpremierna", "",
                f"Körning `{state['id']}` · scenario `{state['manifest']['scenario']}` · per {report['as_of']}.",
                "", "Samtliga belopp i kronor.",
                "", "| Fakturerat | Bank | Fördelat | Öppen fordran | Avstämningskonto |",
                "|---:|---:|---:|---:|---:|", "| " + " | ".join(money(totals[k]) for k in
                ("invoiced_sek", "bank_total_sek", "allocated_sek", "receivables_sek", "suspense_sek")) + " |",
                "", "| Försäkring | Premie | Mottaget | Status |", "|---|---:|---:|---|"]
        labels = {"invoiced": "Fakturerad", "paid": "Betald"}
        rows.extend(f"| {r['policy']} | {money(r['premium'])} | {money(r['allocated'])} | "
                    f"{labels.get(r['status'], r['status'])} |" for r in observed["rows"])
        rows.extend(["", f"Ärenden ({len(observed['cases'])})", ""])
        rows.extend(f"- {c['case']} · {c['type']} · {c['status']} · {c['date']}" for c in observed["cases"])
        rows.extend(["", "Godkända avstämningskontroller." if not report["failures"] else "Underkänd avstämning.",
                     *report["failures"], "", f"Affärsutfall `{report['hash']}`.",
                     f"Filen {'godkändes' if not report['rejections'] else 'avslogs'} av {state['decision']['actor']}.",
                     (f"Granskade filbeslut {report['reviews']}, avslag {report['rejections']}, "
                      f"återleveranser {report['redeliveries']}."),
                     f"Aktiv tid {report['active_seconds']:.3f} s, beslutstid i vänteläge {report['wait_seconds']:.3f} s.",
                     "Modellanrop 0, modellkostnad 0 USD.", "Ej prövat: " + ", ".join(report["unverified"]) + ".",
                     "", f"[Källor och radspår]({day}.json) · [Körmanifest](manifest.json)"])
        write_file(directory / f"{day}.md", "\n".join(rows) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    new = commands.add_parser("start", help="Ny körning från fryst startbild, fram till filbeslut")
    new.add_argument("scenario", choices=SCENARIOS)
    for name in ("status", "resume", "approve", "reject"):
        command = commands.add_parser(name)
        command.add_argument("run_id")
        if name in ("approve", "reject"):
            command.add_argument("--revision", type=int, required=True)
            command.add_argument("--digest", required=True)
            command.add_argument("--note", required=True)
    args = parser.parse_args()
    if args.action == "start":
        ident = start(RUNS, args.scenario)
        state = advance(RUNS, ident)
    elif args.action == "status":
        state = review(RUNS, args.run_id, Actor.human(os_user()))
    elif args.action == "resume":
        state = advance(RUNS, args.run_id)
    else:
        state = advance(RUNS, args.run_id, revision=args.revision,
                        decision=(Actor.human(os_user()), args.action, args.digest, args.note))
    directory = RUNS / state["id"]
    publish(directory, state)
    print(f"{state['id']}  {state['status']}  {state['day']}  {directory}")
    if state["status"] == "waiting_review":
        show_review(state)
    return int(any(report["failures"] for report in state["reports"].values()))


if __name__ == "__main__":
    sys.exit(main())
