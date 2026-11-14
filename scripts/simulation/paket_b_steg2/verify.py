"""Skrivskyddad kontroll av kapitaljournalen (paket B steg 2, B-047, P1-PENSION-001 §11 fall 36 och 37).

Kontrollerar i en `READ ONLY`-transaktion (Postgres) med den betrodda anslutningen:
- journalens fyra tabeller och det bokade ingående läget: verifikationen, kontrollposterna och raderna;
- **fall 36:** S-04 per 2026-10-31 har den frysta hashen, och journalen bevarar varje försäkrings C i ören och
  G i tio decimaler, med summorna 42 087 223,57 kr och 119 195,6502916268 kr/mån. A6 med källan `ledger` ger
  samma FTA, VÅ och U som S-04 på samma grund och kurva;
- **fall 37:** november 2026 ur paket A:s allokeringar ger 51 623,90 kr, varav SvenskIndustries delbetalning
  15 362,24 kr, och avstämningskontots 36 261,66 kr följer inte med. Inget av det är bokat än (steg 3);
- att ingen agentroll har rättigheter på de nya tabellerna (bara Postgres);
- med `--backup`: radantalen i övriga tabeller lika med backupen, utom ett nytt utdrag i `valuation_extracts` och
  loggraderna för `open_capital_ledger` i `operation_events`.

Väntade belopp gäller Lakebase; `--expected` styr dem (`lakebase` eller `none` för att bara pröva
sambanden). Databasen väljs med DATABASE_URL. Resultatet skrivs till huvudkatalogens
`logs/simulation/paket-b-steg2/verify.json` (verify_sqlite.json för en lokal kopia). Ändrar ingenting.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from common import OUT  # noqa: E402  (lägger också src/ på sökvägen)

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--backup", type=Path, help="Backupmappen (manifest.json) tagen före migrationen")
parser.add_argument("--expected", choices=("lakebase", "none"), default="lakebase")
args = parser.parse_args()

from sqlalchemy import func, inspect, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from models import LedgerGuaranteePart, PaymentAllocation  # noqa: E402
from services import capital_ledger as cl  # noqa: E402
from services.ledger_extract import build_ledger_extract  # noqa: E402
from services.ledger_premiums import premium_intake  # noqa: E402
from services.valuation import compute_valuation  # noqa: E402
from services.valuation_extract import build_extract  # noqa: E402
from utils.db import make_engine  # noqa: E402
from utils.migration_capital_ledger import TABLES, granted_to_agents  # noqa: E402
from utils.migration_premium_flow import _agent_roles  # noqa: E402

LAKEBASE = {"extract": "023946257ca8e184028d9727e52756cc9ec541fe9c5922dcd2f9b9b8c053fefa",
            "capital": Decimal("42087223.57"), "guarantee": Decimal("119195.6502916268"),
            "november": Decimal("51623.90"), "svenskindustries": ("5553972661", Decimal("15362.24")),
            "suspense": Decimal("36261.66")}
OPENING = date(2026, 10, 31)
checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail="") -> None:
    checks.append((name, bool(ok), str(detail)))


expected = LAKEBASE if args.expected == "lakebase" else None
engine = make_engine()
with engine.connect() as conn:
    if engine.dialect.name == "postgresql":
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    names = set(inspect(conn).get_table_names())
    check("journalens tabeller finns", set(TABLES) <= names, sorted(set(TABLES) & names))
    with Session(bind=conn) as s:
        batch = cl.opening_batch(s)
        check("ingående läge bokat", batch is not None, batch.checksum if batch else "saknas")
        cl.verify_opening(s, batch)
        check("verifikationen stämmer med raderna och kontrollposterna", True, batch.content["totals"])
        s04 = build_extract(s, OPENING)
        ledger = build_ledger_extract(s, OPENING)
        check("S-04 per 2026-10-31 är journalens utdrag", s04.checksum == batch.extract_checksum, s04.checksum)
        if expected:
            check("fall 36: S-04 har den frysta hashen", s04.checksum == expected["extract"], s04.checksum)
        check("ledger-utdraget godkänt", ledger.approved and ledger.source == "ledger",
              [c.name for c in ledger.checks if not c.passed] or "alla kontroller")
        by_s04 = {p.policy_id: (p.capital, sum((g.guarantee for g in p.guarantee_parts), Decimal(0)))
                  for p in s04.policies}
        by_ledger = {p.policy_id: (p.capital, sum((g.guarantee for g in p.guarantee_parts), Decimal(0)))
                     for p in ledger.policies}
        check("fall 36: varje försäkrings C och G exakt", by_s04 == by_ledger, f"{len(by_ledger)} försäkringar")
        capital = sum((c for c, _ in by_ledger.values()), Decimal(0))
        guarantee = sum((g for _, g in by_ledger.values()), Decimal(0))
        if expected:
            check("fall 36: ΣC och ΣG", (capital, guarantee) == (expected["capital"], expected["guarantee"]),
                  f"{capital} kr, {guarantee} kr/mån")
        kwargs = {"basis_code": "SIM-V-2026-01", "curve_code": "FI-SIM-2026-10"}
        v_s04 = compute_valuation(s, OPENING, "scenario", **kwargs)
        v_ledger = compute_valuation(s, OPENING, "scenario", source="ledger", **kwargs)
        same = (v_s04.totals.capital, v_s04.totals.guarantee, v_s04.totals.fta, v_s04.totals.surplus,
                v_s04.totals.deficit) == (v_ledger.totals.capital, v_ledger.totals.guarantee, v_ledger.totals.fta,
                                          v_ledger.totals.surplus, v_ledger.totals.deficit)
        check("fall 36: A6 ger samma FTA, VÅ och U ur journalen", same and v_ledger.checks_passed,
              f"FTA {v_ledger.totals.fta} kr, VÅ {v_ledger.totals.surplus} kr, U {v_ledger.totals.deficit} kr")
        intake = premium_intake(s, date(2026, 11, 1))
        summary = intake.summary
        if expected:
            org, part = expected["svenskindustries"]
            check("fall 37: novemberpremierna", Decimal(summary["premium_sek"]) == expected["november"],
                  summary["premium_sek"])
            check("fall 37: SvenskIndustries delbetalning", Decimal(summary["by_employer"].get(org, "0")) == part,
                  summary["by_employer"])
            check("fall 37: avstämningskontot följer inte med", Decimal(summary["suspense_sek"]) == expected["suspense"]
                  and Decimal(summary["premium_sek"]) == sum((a.premium_sek for a in intake.additions), Decimal(0)),
                  summary["suspense_by_basis"])
        allocated = s.scalar(select(func.coalesce(func.sum(PaymentAllocation.amount_sek), 0)).where(
            PaymentAllocation.kind == "invoice_line"))
        check("fall 37: allokeringarna på fakturarader är premiekällan", Decimal(str(allocated)).quantize(
            Decimal("0.01")) >= Decimal(summary["premium_sek"]), f"{allocated} kr allokerat på rader")
        booked = s.scalar(select(func.count()).select_from(LedgerGuaranteePart).where(
            LedgerGuaranteePart.origin_kind == "payment_allocation"))
        check("inga premier ur paket A bokade före stängningen (steg 3)", booked == 0, booked)
    if engine.dialect.name == "postgresql":
        roles = _agent_roles(conn)
        granted = granted_to_agents(conn, roles)
        check("inga agenträttigheter på journalen", not granted, granted or roles)
    if args.backup:
        before = json.loads((args.backup / "manifest.json").read_text(encoding="utf-8"))["row_counts"]
        after = {t: conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in before}
        moved = {t: (before[t], after[t]) for t in before if before[t] != after[t]}
        logged = conn.execute(text("SELECT count(*) FROM operation_events WHERE operation = 'open_capital_ledger'"
                                   )).scalar_one()
        events = moved.pop("operation_events", (0, 0))
        extracts = moved.pop("valuation_extracts", (0, 1))
        check("övriga radantal som i backupen (utom S-04-utdraget och övergångens loggrader)",
              not moved and extracts[1] == extracts[0] + 1 and events[1] - events[0] == logged,
              {**moved, "valuation_extracts": extracts, "operation_events": events, "open_capital_ledger": logged})
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
