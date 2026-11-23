"""Ledningsunderlag för den första isolerade premiemånaden (V-12)."""

import json
import re
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

from services.operations.payments import bank_file_checksum
from services.operations.salary_files import file_checksum
from simulation.premium_calendar import CUTOFF, END, VERSION, schedule, status
from simulation.premium_opening import DB, OPENING, digest
from simulation.premium_verification import FACIT, FACIT_VERSION, business_hash, verify
from utils.checksums import canonical_hash

DAYS = (CUTOFF.isoformat(), END.isoformat())
AMOUNTS = {
    "Nettofakturerat": "invoiced_sek", "Bankinbetalningar": "bank_total_sek",
    "Mottaget på fakturarader": "allocated_sek", "Avstämningskonto": "suspense_sek",
    "Öppen fordran": "receivables_sek",
}
OPERATIONS = {
    "Granskade lönefiler": "reviews", "Avslagna lönefiler": "rejections",
    "Återlevererade bankhändelser": "redeliveries", "Aktiv tid (s)": "active_seconds",
    "Väntetid på filbeslut (s)": "wait_seconds", "Modellanrop": "model_calls",
    "Modellkostnad (USD)": "model_cost_usd",
}


def amount(value):
    number = Decimal(str(value))
    if not number.is_finite() or number != number.quantize(Decimal("0.01")):
        raise ValueError("Ogiltigt öresbelopp")
    return number


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_files(state, report, scenario, exported, check):
    required = {"salary", "bank"} | ({"redelivery"} if scenario == "duplicate" else set())
    check("Samtliga motpartsfiler", set(report["file_checksums"]) == required)
    events = {}
    for name in sorted(required):
        item = state["files"][name]
        payload = item["payload"]
        exported(name + ".json", {**payload, "_label": item["label"]})
        exported(name + ".facit.json", {"label": item["label"], "facit": item["facit"]})
        if name == "salary":
            checksum = file_checksum(payload["employer_org_number"], date.fromisoformat(payload["period_month"]),
                                     payload["file_reference"], date.fromisoformat(payload["received_date"]),
                                     payload["rows"])
            expected = item["facit"]["expected"]
            check("Lönefil mot motpartsfacit", set(expected) == {"valid", "missing", "deviations"}
                  and all(state["review"]["summary"][k] == v for k, v in expected.items()))
        else:
            checksum = bank_file_checksum(payload["source_system"], payload["file_reference"], payload["events"])
            for event in payload["events"]:
                key = (payload["source_system"], event["event_id"])
                check("Unika original och identisk återleverans",
                      events.get(key) == event if name == "redelivery" else key not in events)
                events[key] = event
        check("Innehållssumma " + name, checksum == payload["checksum"] == report["file_checksums"][name])
    return events


def calculate_balances(report, scenario, day, events, state, refs, amounts, actions, check):
    observed = report["observed"]
    balances = observed["balances"]
    refs["Affärsutfall"] = business_hash(observed)
    check("Affärssumma", refs["Affärsutfall"] == report["hash"])
    check("Radutfall och ärenden mot scenariefacit",
          not verify(observed, scenario, december=day == DAYS[1]) and report["failures"] == [])
    amounts.update({label: format(amount(balances[key]), ".2f") for label, key in AMOUNTS.items()})
    bank, allocated, suspense = (amount(balances[k]) for k in ("bank_total_sek", "allocated_sek", "suspense_sek"))
    open_total = amount(balances["receivables_sek"])
    bank_diff = bank - allocated - suspense
    invoice_diff = amount(balances["invoiced_sek"]) - allocated - open_total
    amounts.update({"Bankdifferens": f"{bank_diff:.2f}", "Fakturadifferens": f"{invoice_diff:.2f}"})
    check("Bank- och fakturaavstämning till öret", bank_diff == invoice_diff == 0)
    check("Unika bankhändelser mot bankfacit", len(events) == observed["counts"]["bank_events"]
          and sum(amount(e["amount_sek"]) for e in events.values()) == bank
          and amount(state["files"]["bank"]["facit"]["total_sek"]) == bank)
    decision = state["decision"]
    check("Källspår till godkänd lönefil och regelversion", report["decision"] == decision
          and decision["verdict"] == "approve" and decision["receipt"]["status"] == "approved"
          and all(t["review"] == decision["digest"] and t["operator"] == decision["actor"]
                  and t["file"] == state["files"]["salary"]["payload"]["file_reference"]
                  and t["rule"] == state["manifest"]["rule_package"]
                  and t["parameters"] == state["manifest"]["opening"]["parameters"] for t in observed["traces"]))
    rows = observed["rows"]
    invoices = balances["open_invoices"]
    check("Rad- och fakturasummor", sum(amount(r["allocated"]) for r in rows) == allocated
          and sum(amount(i["open_sek"]) for i in invoices) == open_total)
    bank_source = state["files"]["bank"]["payload"]["source_system"]
    check("Allokeringsspår", all(
        r["policy"] == t["policy"] and amount(r["allocated"]) == sum(amount(e["amount"]) for e in t["receipts"])
        and all(events.get((bank_source, e["event"]), {}).get("received_date") == e["received"] for e in t["receipts"])
        for r, t in zip(rows, observed["traces"], strict=True)))
    overdue = Decimal(0)
    for invoice in invoices:
        due = date.fromisoformat(invoice["due_date"])
        late = due < date.fromisoformat(day)
        value = amount(invoice["open_sek"])
        if late:
            overdue += value
        actions.append({"belopp": f"{value:.2f}", "orsak": "Förfallen fordran" if late else "Återstår att betala",
                        "ansvar": "Försäkringsadministration", "kontroll": (
                            "Följ upp förfalloärendet nästa arbetsdag" if late else
                            f"Kontrollera betalning efter förfall {due + timedelta(days=1)}")})
    amounts["Därav förfallen fordran"] = f"{overdue:.2f}"
    if suspense:
        actions.append({"belopp": f"{suspense:.2f}", "orsak": "Överskott" if scenario == "twice" else "Okänd OCR",
                        "ansvar": "Försäkringsadministration", "kontroll": "Utred matchningsärendet nästa arbetsdag"})
    cases = observed["cases"]
    check("Öppna poster med ansvar och nästa kontroll",
          all(i["due_date"] == "2026-12-28" and amount(i["open_sek"]) > 0 for i in invoices)
          and all(c["status"] == "open" for c in cases)
          and sum(amount(c["amount"]) for c in cases if c["type"] == "payment_unmatched") == suspense
          and sum(amount(c["amount"]) for c in cases if c["type"] == "payment_overdue") == overdue)


def operating_metrics(report, event_count, scenario, check):
    operations = {label: report[field] for label, field in OPERATIONS.items()}
    cases = report["observed"]["cases"]
    operations["Unika bankhändelser"] = event_count
    operations["Ärenden"] = len(cases)
    labels = {"payment_unmatched": "Öppna matchningsärenden", "payment_overdue": "Öppna förfalloärenden"}
    for kind, count in Counter(c["type"] for c in cases if c["status"] == "open").items():
        operations[labels[kind]] = count
    check("Handläggningsmått", all(isinstance(v, (int, float)) and v >= 0 for v in operations.values())
          and report["reviews"] == 1 and report["rejections"] == 0
          and report["redeliveries"] == int(scenario == "duplicate"))
    return operations


def collect(root, run, day):
    if day not in DAYS:
        raise ValueError("Okänd avstämningsdag")
    state = status(root, run)
    if day not in state["reports"]:
        raise ValueError("Periodunderlaget är ej framtaget")
    report = state["reports"][day]
    manifest = state["manifest"]
    scenario = manifest["scenario"]
    folder = root / run
    failures = []
    refs = {}
    amounts, operations, actions = {}, {}, []
    checks = {}

    def check(label, passed):
        checks[label] = checks.get(label, True) and bool(passed)
        if not passed and label not in failures:
            failures.append(label)

    def exported(name, expected):
        try:
            actual = read_json(folder / name)
            refs[name] = canonical_hash(actual)
            matches = refs[name] == canonical_hash(expected)
        except (OSError, ValueError):
            matches = False
            refs[name] = "Saknas eller oläsbar"
        check("Källfil " + name, matches)

    exported("manifest.json", manifest)
    exported(day + ".json", report)
    opening = root / OPENING
    try:
        valid = (read_json(opening / "manifest.json") == manifest["opening"]
                 and digest(opening / DB) == manifest["opening"]["sha256"])
    except (KeyError, ValueError, OSError):
        valid = False
    check("Fryst startbestånd", valid)
    try:
        check("Körmanifestets versioner och källkodssummor", manifest["version"] == VERSION
              and re.fullmatch("[0-9a-f]{40}", manifest["code"]) and re.fullmatch("[0-9a-f]{64}", manifest["source_hash"])
              and manifest["seed"] == 1 and manifest["rule_package"] and manifest["opening"]["parameters"])
        steps = schedule(scenario)
        check("Rapportens avgränsning", set(report["unverified"]) ==
              {"agentkvalitet", "kapital", "garanti", "FTA", "portfölj", "huvudbok"})
        last = steps.index((day, "report"))
        journal = [(e["day"], e["step"]) for e in state["journal"][:last + 1]]
        check("Körning, period och sista kalendersteg",
              report["run"] == run and report["as_of"] == day and report["period"] == "2026-11"
              and report["manifest_hash"] == canonical_hash(manifest)
              and manifest["steps"] == [list(step) for step in steps] and journal == steps[:last + 1]
              and manifest["opening"]["period"] == "2026-10-01"
              and manifest["facit"] == FACIT_VERSION and manifest["facit_hash"] == canonical_hash(FACIT))
        events = check_files(state, report, scenario, exported, check)

        calculate_balances(report, scenario, day, events, state, refs, amounts, actions, check)
        operations.update(operating_metrics(report, len(events), scenario, check))
    except (KeyError, IndexError, TypeError, ValueError, ArithmeticError):
        check("Obligatoriskt underlag saknas eller är oläsbart", False)

    if failures:
        conclusion = "Underlaget behöver rättas före godkännande."
    else:
        def kronor(label):
            return format(amount(amounts[label]), ",.2f").replace(",", " ").replace(".", ",") + " kr"

        conclusion = (f"Av {kronor('Nettofakturerat')} nettofakturerat har {kronor('Mottaget på fakturarader')} "
                      f"fördelats. Öppen fordran är {kronor('Öppen fordran')}, varav "
                      f"{kronor('Därav förfallen fordran')} är förfallen. På avstämningskontot finns "
                      f"{kronor('Avstämningskonto')}.")
    last_step = (f"{day} · rapport efter förfallobevakning" if checks.get("Körning, period och sista kalendersteg")
                 else "Ej verifierat")
    summary = {"period": "2026-11-01 – 2026-12-01 (exklusivt slut)", "salary_period": "2026-10",
               "day": day, "scenario": scenario, "last_step": last_step, "conclusion": conclusion,
               "amounts": amounts, "operations": operations, "actions": actions, "checks": checks, "refs": refs,
               "unverified": ["Agentkvalitet", "Kapital", "Garanti", "FTA", "Portfölj", "Huvudbok"]}
    return summary, {"report": report, "manifest": manifest, "files": state["files"]}, failures
