"""Paket A steg 8, bankdelen: inbetalningar för första operativa perioden 2026-10 i Lakebase (fall 12, 13, 15).

Karls val 2026-11-14: SvenskIndustries AB #02 delbetalar hälften (fall 12), TeknikNorden AB #01 betalar två
gånger (fall 13). Fall 15 provas genom att samma händelser kommer igen, först i samma fil och sedan i en
andra fil med egen referens. Fall 14 täcks av de lokala proven. Verklig kalender: bankdag dagen efter
fakturadagen (`days_after_invoice=1`), filens dag i dag.

    python scripts/simulation/period_2026_10/bank_payments.py          # torrkörning: bara läsning, visar filen och facit
    python scripts/simulation/period_2026_10/bank_payments.py --skarp  # importerar i Lakebase

Körd skarpt i Lakebase 2026-11-14. En ny körning ger en annan fil, eftersom de öppna beloppen har ändrats.

Körs med huvudkatalogens .venv, från repo-roten eller en worktree.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal

from common import OUT  # noqa: E402  (lägger också src/ på sökvägen)

from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer  # noqa: E402
from services.db import session_factory_for  # noqa: E402
from services.operations.payments import bank_file_checksum  # noqa: E402
from simulation.counterparties import PaymentBehaviour, bank_file  # noqa: E402
from sqlalchemy import inspect  # noqa: E402
from utils.db import make_engine  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--skarp", action="store_true", help="Importera i databasen (annars bara läsning)")
args = parser.parse_args()

PERIOD = date(2026, 10, 1)
SEED = 2026
TODAY = date.today()
assert TODAY >= date(2026, 11, 9), TODAY
BEHAVIOURS = {
    "5553972661": PaymentBehaviour(kind="partial", share=Decimal("0.5"), days_after_invoice=1),  # SvenskIndustries
    "5507466372": PaymentBehaviour(kind="twice", days_after_invoice=1),                         # TeknikNorden
}
CHANGING = {"bank_events", "payment_allocations", "cases", "operation_events"}

engine = make_engine()
factory = session_factory_for(engine)

with factory() as s:
    s.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
    sim = bank_file(s, PERIOD, BEHAVIOURS, as_of=TODAY, seed=SEED)
print(f"bankfil {sim.reference}: {len(sim.payload['events'])} händelser, {sim.facit['total_sek']} kr")
expected = {f["event_id"]: f["expected"] for f in sim.facit["events"]}
for e in sim.payload["events"]:
    print(f"  {e['event_id']} {e['received_date']} {e['amount_sek']:>10} kr  {e['payer_org_number']} "
          f"OCR {e['reference']}  -> {expected[e['event_id']]}")
for p in sim.facit["pending"]:
    print(f"  väntande: {p}")
assert not sim.facit["pending"], sim.facit["pending"]
assert len(sim.payload["events"]) == 3, sim.payload["events"]

if not args.skarp:
    print("torrkörning – ingenting är skrivet")
    sys.exit(0)

ctx = OperationContext(actor=Actor.human("rooktest"),
                       reason="Bankdelen för första operativa perioden 2026-10 (paket A steg 8, B-046, "
                              "P1-PREMIE-001 §7 fall 12, 13 och 15): simulerad bankfil, körd av Claude efter Karls OK")


def call(operation: str, data: dict):
    service = ServiceLayer(session_factory=factory, rules=ProductRuleCatalog(today=TODAY))
    return service.execute(operation, ctx, data).output


def counts() -> dict[str, int]:
    with factory() as s:
        c = s.connection()
        return {n: c.exec_driver_sql(f'SELECT count(*) FROM "{n}"').scalar_one()
                for n in sorted(inspect(c).get_table_names())}


sim.write(OUT)
log: dict = {"today": TODAY.isoformat(), "period": PERIOD.isoformat(), "seed": SEED,
             "behaviours": {o: {k: str(v) for k, v in vars(b).items()} for o, b in BEHAVIOURS.items()},
             "file": sim.reference}
before = counts()

first = call("import_bank_file", sim.payload)
log["first"] = first.model_dump(mode="json")
print(f"första filen: {first.new_events} nya, {first.allocated_sek} kr fördelat, {first.unallocated_sek} kr på "
      f"avstämningskontot, {first.paid_premium_rows} premierader betalda")
assert first.new_events == 3

again = call("import_bank_file", sim.payload)  # samma fil igen
log["same_file_again"] = again.model_dump(mode="json", include={"new_events", "already_received"})
assert (again.new_events, again.already_received) == (0, 3)

second_ref = f"{sim.reference}-B"  # fall 15: samma händelser i en annan fil
events = sim.payload["events"]
second = {"source_system": sim.payload["source_system"], "file_reference": second_ref,
          "checksum": bank_file_checksum(sim.payload["source_system"], second_ref, events), "events": events}
(OUT / f"{second_ref}.json").write_text(json.dumps(second, indent=2, ensure_ascii=False), encoding="utf-8")
dup = call("import_bank_file", second)
log["fall15_second_file"] = dup.model_dump(mode="json", include={"file_reference", "new_events", "already_received",
                                                                  "allocated_sek", "unallocated_sek"})
print(f"fall 15, {second_ref}: {dup.new_events} nya, {dup.already_received} redan mottagna")
assert (dup.new_events, dup.already_received) == (0, 3)

after = counts()
delta = {n: after[n] - before.get(n, 0) for n in after if after[n] != before.get(n)}
log["row_delta"] = delta
print("ändrade radantal:", delta)
assert set(delta) <= CHANGING, set(delta) - CHANGING
(OUT / "bank_korning.json").write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
print("klart; logg", OUT / "bank_korning.json")
