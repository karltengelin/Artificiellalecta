"""Skrivskyddad kontroll av novembers månadsstängning (paket B steg 3, B-047, P1-PENSION-001 §7 och §11).

Kontrollerar i en `READ ONLY`-transaktion (Postgres) med den betrodda anslutningen:
- att migrationen för månadsstängning är införd och att det ingående läget per 2026-10-31 är orört;
- november 2026: gällande version, versionskedjan, sammanställningen mot raderna och kontrollposterna;
- AVK-SIM-2026-02 är antagen från 2026-11-01 med innehållet enligt P6-MANAD-001 D5 och är månadens grund;
- **fall 16:** en ny granskning ger samma summa och status `closed` – ingen ny effekt;
- **fall 37:** novembers premier är 51 623,90 kr ur paket A, varav SvenskIndustries delbetalning 15 362,24 kr,
  bokade som garantidelar och premieposter; avstämningskontots 36 261,66 kr följer inte med;
- ledger-utdraget per 2026-11-30 är godkänt och stämmer med stängningens utgående kapital; A6 med källan
  `ledger` per 2026-11-30 klarar sina kontroller;
- att ingen agentroll har rättigheter på journalen (bara Postgres);
- med `--backup`: bara journalens fyra tabeller, `valuation_bases` (en ny grund) och `operation_events`
  (loggrader efter backupen) har ändrats, med journalens tillskott lika med verifikationernas innehåll.

Väntade belopp gäller Lakebase; `--expected none` prövar bara sambanden. Databasen väljs med DATABASE_URL.
Resultatet skrivs till huvudkatalogens `logs/simulation/paket-b-steg3/verify.json`. Ändrar ingenting.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from common import AVK_CODE, AVK_RATE, LAKEBASE, NOV_END, NOVEMBER, OUT, SCENARIO  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--backup", type=Path, help="Backupmappen (manifest.json) tagen före steg 3")
parser.add_argument("--expected", choices=("lakebase", "none"), default="lakebase")
args = parser.parse_args()

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from models import (  # noqa: E402
    LedgerCapitalEntry,
    LedgerControl,
    LedgerGuaranteePart,
    ValuationBasis,
)
from services import capital_ledger as cl  # noqa: E402
from services import month_close as mc  # noqa: E402
from services import valuation_bases as vb  # noqa: E402
from services.ledger_extract import build_ledger_extract, covered_dates  # noqa: E402
from services.operations.common import today  # noqa: E402
from services.premium_month_inputs import november_returns  # noqa: E402
from services.valuation import compute_valuation  # noqa: E402
from utils.db import make_engine  # noqa: E402
from utils.migration_capital_ledger import TABLES, granted_to_agents  # noqa: E402
from utils.migration_premium_flow import _agent_roles  # noqa: E402

#: Operationerna steg 3 loggar mellan backupen och kontrollen (A4:s väg och stängningen)
STEP3_OPS = {"propose_valuation_basis", "adopt_valuation_basis", "prepare_month_close", "close_policy_month",
             "get_month_close"}
checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail="") -> None:
    checks.append((name, bool(ok), str(detail)))


def count(s, model, *where) -> int:
    return s.scalar(select(func.count()).select_from(model).where(*where))


expected = LAKEBASE if args.expected == "lakebase" else None
engine = make_engine()
with engine.connect() as conn:
    if engine.dialect.name == "postgresql":
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    with Session(bind=conn) as s:
        check("migrationen för månadsstängning är införd", cl.month_close_present(s))
        opening = cl.opening_batch(s)
        cl.verify_opening(s, opening)
        check("det ingående läget per 2026-10-31 är orört", True, opening.checksum)
        chain = cl.month_chain(s, NOV_END)
        batch = chain[-1]
        check("november stängd", chain[0].kind == "month_close", [f"{b.kind} v{b.content['version']}" for b in chain])
        mc.verify_month(s, batch)
        check("verifikationen stämmer med raderna och kontrollposterna", True, batch.content["totals"])
        check("föregående läge är det ingående läget", batch.content["previous"]["checksum"] == opening.checksum)
        # AVK enligt P6-MANAD-001 D5, antagen genom A4
        old = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "AVK-SIM-2026-01"))
        avk = s.scalar(select(ValuationBasis).where(ValuationBasis.code == AVK_CODE))
        digest = vb.checksum(november_returns(old.assumptions, AVK_RATE))
        check("AVK-SIM-2026-02 antagen från 2026-11-01 med D5:s innehåll",
              avk is not None and avk.status == "adopted" and avk.valid_from == NOVEMBER and avk.checksum == digest
              and old.valid_to == date(2026, 10, 31), avk.checksum if avk else "saknas")
        basis = batch.content["return_basis"]
        check("månadens avkastningsgrund", basis["code"] == AVK_CODE and basis["checksum"] == digest
              and Decimal(basis["rate"]) == AVK_RATE, basis)
        # Fall 16: samma stängning igen ger ingen ny effekt
        plan = mc.plan_month(s, NOVEMBER, today())
        check("fall 16: ny granskning ger samma summa utan ny effekt",
              plan.status == "closed" and plan.checksum == batch.checksum, f"{plan.status} {plan.checksum[:12]}")
        # Fall 37 i stängningen
        premiums = chain[0].content["premiums"]
        parts = s.scalars(select(LedgerGuaranteePart).where(LedgerGuaranteePart.batch_id == chain[0].id)).all()
        entries = s.scalars(select(LedgerCapitalEntry).where(LedgerCapitalEntry.batch_id == chain[0].id,
                                                             LedgerCapitalEntry.reason == "premium")).all()
        booked = sum((p.premium_sek for p in parts), Decimal(0))
        check("fall 37: premierna bokade som garantidelar och premieposter",
              booked == sum((e.amount_sek for e in entries), Decimal(0)) == Decimal(premiums["premium_sek"])
              and len(parts) == len(entries) == premiums["allocations"],
              f"{len(parts)} allokeringar, {booked} kr")
        check("fall 37: värdedag och mottagningsmånad", {(p.value_date, p.received_month) for p in parts}
              <= {(NOV_END, NOVEMBER)}, sorted({(str(p.value_date), str(p.received_month)) for p in parts}))
        if expected:
            org, part = expected["svenskindustries"]
            check("fall 37: novemberpremierna", booked == expected["november"], booked)
            check("fall 37: SvenskIndustries delbetalning", Decimal(premiums["by_employer"].get(org, "0")) == part,
                  premiums["by_employer"].get(org))
            check("fall 37: avstämningskontot följer inte med", Decimal(premiums["suspense_sek"]) ==
                  expected["suspense"], premiums["suspense_by_basis"])
            check("öppningskapitalet är det ingående lägets", Decimal(batch.content["totals"]["opening_sek"]) ==
                  expected["opening"], batch.content["totals"]["opening_sek"])
        # Utdraget och A6 per 2026-11-30
        check("journalen har ett stängt läge per 2026-11-30", NOV_END in covered_dates(s), covered_dates(s))
        extract = build_ledger_extract(s, NOV_END)
        failed = [c.name for c in extract.checks if not c.passed]
        check("ledger-utdraget per 2026-11-30 godkänt", extract.approved and not failed, failed or extract.checksum)
        check("utdragets sista månad är november", extract.months[-1].month == NOVEMBER and
              extract.months[-1].closing == Decimal(batch.content["totals"]["closing_sek"]),
              f"{extract.months[-1].month} {extract.months[-1].closing} kr")
        valuation = compute_valuation(s, NOV_END, "scenario", source="ledger", **SCENARIO)
        check("A6 per 2026-11-30 ur journalen klarar sina kontroller", valuation.checks_passed,
              f"C {valuation.totals.capital} kr, FTA {valuation.totals.fta} kr")
        added = {"ledger_batches": len(chain), "ledger_guarantee_parts": sum(
                     count(s, LedgerGuaranteePart, LedgerGuaranteePart.batch_id == b.id) for b in chain),
                 "ledger_capital_entries": sum(
                     count(s, LedgerCapitalEntry, LedgerCapitalEntry.batch_id == b.id) for b in chain),
                 "ledger_controls": sum(count(s, LedgerControl, LedgerControl.batch_id == b.id) for b in chain)}
        check("radernas antal enligt verifikationerna", added["ledger_capital_entries"] == sum(
            b.content["totals"]["entries"] for b in chain) and added["ledger_guarantee_parts"] == sum(
            b.content["totals"]["new_guarantee_parts"] for b in chain), added)
    if engine.dialect.name == "postgresql":
        roles = _agent_roles(conn)
        granted = granted_to_agents(conn, roles)
        check("inga agenträttigheter på journalen", not granted, granted or roles)
    if args.backup:
        manifest = json.loads((args.backup / "manifest.json").read_text(encoding="utf-8"))
        before = manifest["row_counts"]
        after = {t: conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in before}
        moved = {t: (before[t], after[t]) for t in before if before[t] != after[t]}
        events = moved.pop("operation_events", (0, 0))
        # De nyaste loggraderna efter backupen ska alla komma från steg 3:s operationer
        logged = [r[0] for r in conn.execute(text(
            "SELECT operation FROM operation_events ORDER BY occurred_at DESC LIMIT :n"),
            {"n": max(events[1] - events[0], 0)})]
        bases = moved.pop("valuation_bases", (0, 0))
        ledger = {t: moved.pop(t, (before.get(t, 0), before.get(t, 0))) for t in TABLES}
        ok = (not moved and bases[1] - bases[0] in (0, 1) and events[1] >= events[0] and set(logged) <= STEP3_OPS
              and all(ledger[t][1] - ledger[t][0] == added[t] for t in added))
        check("övriga radantal som i backupen (utom journalens tillskott, AVK-grunden och loggraderna)", ok,
              {**moved, "valuation_bases": bases, "operation_events": events,
               "logged_since_backup": sorted(set(logged)), **{t: ledger[t] for t in added}})
    conn.rollback()

result = {"database": f"{engine.dialect.name}:{engine.url.database}",
          "checks": [{"check": n, "passed": ok, "detail": d} for n, ok, d in checks]}
name = "verify.json" if engine.dialect.name == "postgresql" else f"verify_{engine.dialect.name}.json"
(OUT / name).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
for n, ok, d in checks:
    print(f"{'OK ' if ok else 'FEL'} {n}: {d}")
passed = sum(ok for _, ok, _ in checks)
print(f"{passed} av {len(checks)} kontroller godkända")
raise SystemExit(0 if passed == len(checks) else 1)
