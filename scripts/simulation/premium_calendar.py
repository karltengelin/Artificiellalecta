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
from simulation.pension_calendar import ACTIONS as PENSION_ACTIONS
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
    if state["status"] == "waiting_pension":
        pending = state["pension_review"]
        print(json.dumps(pending["view"], ensure_ascii=True, indent=2))
        print(f"Beslutsunderlag {pending['action']} {state['id']} --revision {state['cursor']} "
              f"--digest {pending['digest']}")
        return
    if state["status"] in ("waiting_opening", "waiting_close"):
        view = state["ledger_review"]
        # Äldre Windows-konsoler kan inte skriva alla symboler i B:s kontrolltexter.
        output = json.dumps(view, ensure_ascii=False, indent=2)
        encoding = sys.stdout.encoding or "utf-8"
        print(output.encode(encoding, errors="backslashreplace").decode(encoding))
        action = "open-ledger" if state["status"] == "waiting_opening" else "close-month"
        print(f"Beslutsunderlag {action} {state['id']} --revision {state['cursor']} --digest {view['review_checksum']}")
        return
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
    if "pension_report" in state:
        pension = state["pension_report"]
        save("pension.json", pension)
        save("payout-bank.json", state["outgoing_bank"])
        outcome = pension["outcome"]
        rows = ["# Decemberpension, dödsfallsavräkning och arvsvinst", "",
                f"Bankdag {state['day']} · körning `{state['id']}`.", "",
                "| Brutto | Preliminär skatt | Netto | Kvarvarande betalningsskuld | Skatteskuld |",
                "|---:|---:|---:|---:|---:|",
                "| " + " | ".join(money(outcome[k]) for k in
                                  ("gross", "tax", "net", "payment_liability", "tax_liability")) + " |",
                "", "| Försäkring | Arvsvinst | Utgående kundkapital |",
                "|---|---:|---:|"]
        rows.extend(f"| {policy} | {money(outcome['inheritance'].get(policy, '0'))} | {money(balance)} |"
                    for policy, balance in outcome["balances"].items())
        rows.extend(["", f"Ur arvsvinstpoolen fördelades {money(outcome['pool'])} kr.",
                     f"Återleveransen gav {pension['retry']['new']} nya kvitton.",
                     "Underkänd avstämning." if pension["failures"] else "Godkänd avstämning.",
                     *pension["failures"], "", "[Anspråk, bankkvitto, avräkning och kontroller](pension.json)"])
        write_file(directory / "pension.md", "\n".join(rows) + "\n")
    if "savings_report" in state:
        report = state["savings_report"]
        save("sparande.json", report)
        totals = report["close"]["totals"]
        rows = ["# Novembers bokade sparande", "",
                f"Handläggare {report['actor']} · affärsdag {report['day']} · körning `{state['id']}`.",
                f"Motivering: {report['note']}", "",
                "| Försäkring | IB | Avkastning | Avgift | Skattebelastning | Nettopremie | UB |",
                "|---|---:|---:|---:|---:|---:|---:|"]
        for policy, values in report["bridge"].items():
            cells = [money(values.get(k, "0")) for k in ("opening", "return", "fee", "tax", "premium", "closing")]
            rows.append(f"| {policy} | " + " | ".join(cells) + " |")
        total_row = [totals["opening_sek"], totals["returns_sek"], -Decimal(totals["fees_sek"]),
                     -Decimal(totals["taxes_sek"]), totals["premiums_sek"], totals["closing_sek"]]
        rows.append("| Totalt | " + " | ".join(money(v) for v in total_row) + " |")
        rows.extend(["", "| Försäkring | Bankallokering | Bokad nettopremie | Garantigrund |",
                     "|---|---:|---:|---:|"])
        for trace in report["traces"]:
            rows.append(f"| {trace['policy']} | {money(trace['allocated'])} | {money(trace['net_premium'])} | "
                        f"{money(trace['guarantee_base'])} |")
        rows.extend(["",
                     f"Öppen premiefordran {money(report['balances']['receivables_sek'])} kr.",
                     f"Verifikation `{report['close']['batch_id']}`, granskningssumma `{report['close']['review_checksum']}`.",
                     "Underkänd avstämning." if report["failures"] else "Godkänd avstämning.",
                     *report["failures"], "", "[Bokade källspår och kontroller](sparande.json)"])
        write_file(directory / "sparande.md", "\n".join(rows) + "\n")
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
    mode = new.add_mutually_exclusive_group()
    mode.add_argument("--savings", action="store_true", help="Samprova delbetalningen med novembers journalstängning")
    mode.add_argument("--pension", action="store_true", help="Fortsätt med decemberpension, dödsfall och arvsvinst")
    for name in ("status", "resume", "approve", "reject", "open-ledger", "close-month", *sorted(PENSION_ACTIONS)):
        command = commands.add_parser(name)
        command.add_argument("run_id")
        if name not in ("status", "resume"):
            command.add_argument("--revision", type=int, required=True)
            command.add_argument("--digest", required=True)
            command.add_argument("--note", required=True)
    args = parser.parse_args()
    if args.action == "start":
        ident = start(RUNS, args.scenario, with_savings=args.savings, with_pension=args.pension)
        state = advance(RUNS, ident)
    elif args.action == "status":
        state = review(RUNS, args.run_id, Actor.human(os_user()))
    elif args.action == "resume":
        state = advance(RUNS, args.run_id)
    else:
        state = advance(RUNS, args.run_id, revision=args.revision,
                        decision=(Actor.human(os_user()), args.action, args.digest, args.note))
    if args.action != "status" and state["status"] in ("waiting_opening", "waiting_close"):
        state = review(RUNS, state["id"], Actor.human(os_user()))
    directory = RUNS / state["id"]
    publish(directory, state)
    print(f"{state['id']}  {state['status']}  {state['day']}  {directory}")
    if state["status"] in ("waiting_review", "waiting_opening", "waiting_close", "waiting_pension"):
        show_review(state)
    return int(state["status"] == "failed" or any(report["failures"] for report in state["reports"].values()))


if __name__ == "__main__":
    sys.exit(main())
