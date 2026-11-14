"""Paket A steg 8 punkt 3: första operativa perioden 2026-10 i Lakebase – filintag, godkännande, fakturering.

Verklig kalender (Karls val 2026-11-08): operationernas dag är dagens datum. Bankdelen är `bank_payments.py`.
Körd i Lakebase 2026-11-08. Skriptet stoppar på andra datum och ska inte köras om.
Körs med huvudkatalogens .venv, från repo-roten eller en worktree.
"""
from __future__ import annotations

import copy
import argparse
import json
import sys
from datetime import date

from common import OUT  # noqa: E402  (lägger också src/ på sökvägen)

from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer  # noqa: E402
from services.db import session_factory_for  # noqa: E402
from services.errors import ServiceError  # noqa: E402
from services.operations.salary_files import file_checksum  # noqa: E402
from simulation.counterparties import SalaryScenario, salary_file  # noqa: E402
from sqlalchemy import inspect  # noqa: E402
from utils.db import make_engine  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.parse_args()

PERIOD = date(2026, 10, 1)
SEED = 2026
TODAY = date.today()
assert TODAY == date(2026, 11, 8), TODAY
SCENARIOS = {
    "5553972661": SalaryScenario(missing=1, zero=1, unknown_person=True),  # SvenskIndustries AB #02
    "5507466372": SalaryScenario(),                                        # TeknikNorden AB #01
}
CHANGING = {"salary_files", "salary_reports", "premium_transactions", "invoices", "invoice_lines", "cases",
            "operation_events"}

engine = make_engine()
factory = session_factory_for(engine)
ctx = OperationContext(actor=Actor.human("rooktest"),
                       reason="Första operativa perioden 2026-10 (paket A steg 8, B-046, P1-PREMIE-001 §11 p. 3): "
                              "simulerade filer, körd av Claude efter Karls OK")
log: dict = {"today": TODAY.isoformat(), "period": PERIOD.isoformat(), "seed": SEED, "employers": {}}


def call(operation: str, data: dict):
    service = ServiceLayer(session_factory=factory, rules=ProductRuleCatalog(today=TODAY))
    return service.execute(operation, ctx, data).output


def counts() -> dict[str, int]:
    with factory() as s:
        c = s.connection()
        return {n: c.exec_driver_sql(f'SELECT count(*) FROM "{n}"').scalar_one()
                for n in sorted(inspect(c).get_table_names())}


before = counts()
for org, scenario in SCENARIOS.items():
    with factory() as s:
        sim = salary_file(s, org, PERIOD, received_date=TODAY, seed=SEED, scenario=scenario)
    sim.write(OUT)
    entry = log["employers"][org] = {"reference": sim.reference, "facit": sim.facit["expected"]}

    view = call("import_salary_file", sim.payload)
    sm = view.summary
    entry["intake"] = {"file_id": str(view.file_id), "valid": sm.valid, "deviations": sm.deviations,
                       "missing": sm.missing}
    print(f"{org}: intag {sm.valid} giltiga, {sm.deviations} avvikande, {sm.missing} saknade "
          f"(facit {sim.facit['expected']})")
    assert (sm.valid, sm.deviations, sm.missing) == tuple(sim.facit["expected"].values())

    again = call("import_salary_file", sim.payload)  # fall 6
    entry["fall6_same_file"] = again.file_id == view.file_id
    assert entry["fall6_same_file"]

    changed = copy.deepcopy(sim.payload)  # fall 7: samma referens, ändrat innehåll
    row = next(r for r in changed["rows"] if r["pensionable_salary_sek"] not in ("0.00", "0"))
    row["pensionable_salary_sek"] = f"{float(row['pensionable_salary_sek']) + 100:.2f}"
    changed["checksum"] = file_checksum(org, PERIOD, changed["file_reference"], TODAY, changed["rows"])
    try:
        call("import_salary_file", changed)
        entry["fall7_conflict"] = "INGEN KONFLIKT"
    except ServiceError as exc:
        entry["fall7_conflict"] = f"{type(exc).__name__}: {exc}"
    print(f"  fall 7: {entry['fall7_conflict']}")
    assert entry["fall7_conflict"].startswith(("ConflictError", "BlockedError"))

    decision = call("approve_salary_file", {"employer_org_number": org, "file_reference": sim.reference,
                                            "expected_digest": view.review_digest})
    entry["cases"] = [c.model_dump(mode="json") for c in decision.cases]
    print(f"  godkänd: {len(decision.cases)} ärenden")
    assert len(decision.cases) == sm.deviations + sm.missing

for org in SCENARIOS:
    run = call("create_invoice", {"employer_org_number": org, "period_month": PERIOD.isoformat()})
    [inv] = run.invoices
    log["employers"][org]["invoice_run"] = run.model_dump(mode="json", exclude={"invoices"})
    log["employers"][org]["invoice"] = {"number": inv.invoice_number, "total_sek": str(inv.total_sek),
                                        "invoice_date": inv.invoice_date.isoformat(),
                                        "due_date": inv.due_date.isoformat(), "ocr": inv.ocr_reference}
    print(f"{org}: {inv.invoice_number} {inv.total_sek} kr, fakturadag {inv.invoice_date}, förfaller "
          f"{inv.due_date}, OCR {inv.ocr_reference}")
    again = call("create_invoice", {"employer_org_number": org, "period_month": PERIOD.isoformat()})
    log["employers"][org]["invoice_again_new"] = len(again.invoices)
    assert not again.invoices

after = counts()
delta = {n: after[n] - before.get(n, 0) for n in after if after[n] != before.get(n)}
log["row_delta"] = delta
print("ändrade tabeller:", delta)
assert set(delta) <= CHANGING, set(delta) - CHANGING
(OUT / "korning.json").write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
print("klart; logg", OUT / "korning.json")
