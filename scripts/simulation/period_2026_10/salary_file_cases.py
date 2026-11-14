"""Paket A steg 8: ärendena från SvenskIndustries fil för period 2026-10 avgörs som riktiga ärenden (B-046).

Karls val 2026-11-08, körning efter hans OK 2026-11-14:

- CASE-000010 (saknad rapport): arbetsgivaren skickar en kompletterande fil med ny filreferens. Simulatorn gör den
  ur beståndet, och eftersom bara den saknade personen är orapporterad får filen exakt den raden. Filen tas emot och
  godkänns, perioden faktureras igen (en ny debetfaktura för den sena premien) och ärendet stängs som `approved`.
  Intag, godkännande och fakturering görs med ärendenumret, så att ändringen är spårbar i ärendet.
- CASE-000009 (okänd person): raden avsåg en person som inte finns i beståndet och registrerades aldrig. Ärendet
  stängs som `no_action` med motivering.

    python scripts/simulation/period_2026_10/salary_file_cases.py --db demo   # generalprov i SQLite i minnet
    python scripts/simulation/period_2026_10/salary_file_cases.py             # torrkörning i Lakebase, bara läsning
    python scripts/simulation/period_2026_10/salary_file_cases.py --skarp     # skriver i Lakebase

Körs med huvudkatalogens .venv, från repo-roten eller en worktree. Verklig kalender: filens mottagningsdag och
fakturadagen är dagens datum.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from types import SimpleNamespace

from common import OUT  # noqa: E402  (lägger också src/ på sökvägen)

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--db", choices=("lakebase", "demo"), default="lakebase")
parser.add_argument("--skarp", action="store_true", help="Skriv i Lakebase (annars bara läsning)")
args = parser.parse_args()

from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer  # noqa: E402
from services.db import session_factory_for  # noqa: E402
from simulation.counterparties import SalaryScenario, salary_file  # noqa: E402
from sqlalchemy import inspect, select  # noqa: E402

from models import Case, InsuredPerson  # noqa: E402

PERIOD = date(2026, 10, 1)
SEED = 2026
TODAY = date.today()
ORG = "5553972661"                                   # SvenskIndustries AB #02
REFERENCE = f"SIM1-{ORG}-202610-S{SEED}-K1"          # kompletterande fil, ny referens
CHANGING = {"salary_files", "salary_reports", "premium_transactions", "invoices", "invoice_lines", "cases",
            "operation_events"}
REASON = ("Ärendena från SvenskIndustries fil för period 2026-10 (paket A steg 8, B-046, P1-PREMIE-001 §7 fall 4–5): "
          "kompletterande simulerad fil och stängning, körd av Claude efter Karls OK")
NOTE_10 = ("Arbetsgivaren skickade en kompletterande fil ({ref}) med den saknade raden. Löneunderlaget är "
           "registrerat, premien skapad och fakturerad på {invoice} (sen rapportering, PR-ITP1-017).")
NOTE_9 = ("Raden avsåg en person som inte finns i beståndet och registrerades aldrig. Felaktig rad i arbetsgivarens "
          "fil; ingen premie och ingen åtgärd (P1-PREMIE-001 §7 fall 5).")


def counts(factory) -> dict[str, int]:
    with factory() as s:
        c = s.connection()
        return {n: c.exec_driver_sql(f'SELECT count(*) FROM "{n}"').scalar_one()
                for n in sorted(inspect(c).get_table_names())}


def case_ref(factory, number: str) -> dict:
    with factory() as s:
        case = s.scalar(select(Case).where(Case.case_number == number))
        pnr = s.scalar(select(InsuredPerson.personal_id_number).where(InsuredPerson.id == case.insured_person_id)) \
            if case.insured_person_id else None
        return {"case_number": number, "status": case.status, "reason": case.details.get("reason"),
                "personal_id_number": pnr, "row": case.details.get("row")}


def complementary_file(factory, org: str, reference: str):
    with factory() as s:
        if s.get_bind().dialect.name == "postgresql":
            s.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
        return salary_file(s, org, PERIOD, received_date=TODAY, seed=SEED, scenario=SalaryScenario(),
                           file_reference=reference)


def handle(factory, org: str, missing_case: str, unknown_case: str, reference: str, *, write: bool) -> dict:
    """Avgör de två ärendena. Utan `write` visas bara den kompletterande filen."""
    missing, unknown = case_ref(factory, missing_case), case_ref(factory, unknown_case)
    assert (missing["reason"], missing["status"]) == ("missing_report", "open"), missing
    assert (unknown["reason"], unknown["status"]) == ("unknown_person", "open"), unknown
    sim = complementary_file(factory, org, reference)
    rows = sim.payload["rows"]
    print(f"{missing_case}: saknad rapport för {missing['personal_id_number']}; {unknown_case}: okänd person, rad "
          f"{unknown['row']}")
    print(f"kompletterande fil {sim.reference}: {len(rows)} rad(er) – "
          + ", ".join(f"{r['personal_id_number']} {r['pensionable_salary_sek']} kr ({r['kind']})" for r in rows))
    assert [r["personal_id_number"] for r in rows] == [missing["personal_id_number"]], rows
    assert sim.facit["expected"] == {"valid": 1, "deviations": 0, "missing": 0}, sim.facit["expected"]
    log = {"today": TODAY.isoformat(), "period": PERIOD.isoformat(), "seed": SEED, "reference": sim.reference,
           "cases_before": {missing_case: missing, unknown_case: unknown}, "rows": rows}
    if not write:
        print("torrkörning – ingenting är skrivet")
        return log

    def call(operation: str, data: dict, case_id: str):
        ctx = OperationContext(actor=Actor.human("rooktest"), reason=REASON, case_id=case_id)
        service = ServiceLayer(session_factory=factory, rules=ProductRuleCatalog(today=TODAY))
        return service.execute(operation, ctx, data).output

    before = counts(factory)
    if args.db == "lakebase":
        sim.write(OUT)
    view = call("import_salary_file", sim.payload, missing_case)
    sm = view.summary
    print(f"intag: {sm.valid} giltiga, {sm.deviations} avvikande, {sm.missing} saknade")
    assert (sm.valid, sm.deviations, sm.missing) == (1, 0, 0)
    decision = call("approve_salary_file", {"employer_org_number": org, "file_reference": sim.reference,
                                            "expected_digest": view.review_digest}, missing_case)
    print(f"godkänd: {decision.salary_reports} löneunderlag, {decision.premium_rows} premierad(er), "
          f"{decision.premium_total_sek} kr, {len(decision.cases)} nya ärenden")
    assert (decision.salary_reports, decision.premium_rows, len(decision.cases)) == (1, 1, 0)
    run = call("create_invoice", {"employer_org_number": org, "period_month": PERIOD.isoformat()}, missing_case)
    [inv] = run.invoices
    print(f"faktura {inv.invoice_number}: {inv.total_sek} kr, fakturadag {inv.invoice_date}, förfaller {inv.due_date}, "
          f"OCR {inv.ocr_reference}")
    assert inv.total_sek == decision.premium_total_sek
    again = call("create_invoice", {"employer_org_number": org, "period_month": PERIOD.isoformat()}, missing_case)
    assert not again.invoices
    closed_10 = call("close_case", {"case_number": missing_case, "outcome": "approved",
                                    "closing_note": NOTE_10.format(ref=sim.reference, invoice=inv.invoice_number)},
                     missing_case)
    closed_9 = call("close_case", {"case_number": unknown_case, "outcome": "no_action", "closing_note": NOTE_9},
                    unknown_case)
    print(f"stängda: {closed_10.case_number} {closed_10.outcome}, {closed_9.case_number} {closed_9.outcome}")
    after = counts(factory)
    delta = {n: after[n] - before.get(n, 0) for n in after if after[n] != before.get(n)}
    print("ändrade radantal:", delta)
    assert set(delta) <= CHANGING, set(delta) - CHANGING
    log |= {"intake": {"file_id": str(view.file_id), "valid": sm.valid},
            "approval": decision.model_dump(mode="json"),
            "invoice": {"number": inv.invoice_number, "total_sek": str(inv.total_sek),
                        "invoice_date": inv.invoice_date.isoformat(), "due_date": inv.due_date.isoformat(),
                        "ocr": inv.ocr_reference},
            "closed": [closed_10.model_dump(mode="json"), closed_9.model_dump(mode="json")], "row_delta": delta}
    return log


def demo() -> None:
    """Generalprov: samma första fil som i Lakebase för en demoarbetsgivare, sedan ärendena."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from utils.demo_data import create_demo_database

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False)
    factory = session_factory_for(engine)
    org = "5560000001"
    ctx = OperationContext(actor=Actor.human("rooktest"), reason="Generalprov i demo")
    service = SimpleNamespace(call=lambda op, data: ServiceLayer(
        session_factory=factory, rules=ProductRuleCatalog(today=TODAY)).execute(op, ctx, data).output)
    with factory() as s:
        first = salary_file(s, org, PERIOD, received_date=TODAY, seed=SEED,
                            scenario=SalaryScenario(missing=1, zero=1, unknown_person=True))
    view = service.call("import_salary_file", first.payload)
    decision = service.call("approve_salary_file", {"employer_org_number": org, "file_reference": first.reference,
                                                    "expected_digest": view.review_digest})
    service.call("create_invoice", {"employer_org_number": org, "period_month": PERIOD.isoformat()})
    by_reason = {c.reason: c.case_number for c in decision.cases}
    print(f"demo: första filen godkänd och fakturerad, ärenden {by_reason}")
    log = handle(factory, org, by_reason["missing_report"], by_reason["unknown_person"],
                 f"SIM1-{org}-202610-S{SEED}-K1", write=True)
    with factory() as s:
        statuses = {c.case_number: (c.status, c.outcome) for c in s.scalars(select(Case))}
    print("demo: ärenden efteråt", statuses)
    assert statuses[by_reason["missing_report"]] == ("closed", "approved")
    assert statuses[by_reason["unknown_person"]] == ("closed", "no_action")
    print(f"generalprov godkänt; ny faktura {log['invoice']['number']} {log['invoice']['total_sek']} kr")


if args.db == "demo":
    demo()
    sys.exit(0)

from utils.db import make_engine  # noqa: E402

factory = session_factory_for(make_engine())
result = handle(factory, ORG, "CASE-000010", "CASE-000009", REFERENCE, write=args.skarp)
if args.skarp:
    (OUT / "arenden_korning.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("klart; logg", OUT / "arenden_korning.json")
