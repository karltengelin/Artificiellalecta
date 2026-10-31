"""Provvärdering som aggregat: FTA, villkorad återbäring och underskott per läge och kohort (A6, B-042).

Kör värderingsmotorn (`services.valuation.compute_valuation`) i en skrivskyddad transaktion och skriver
bara aggregat: totaler, segment per läge och födelsedecennium med småcellsskydd (celler med 1–9
försäkringar döljs, med kompletterande döljning), ej beräknade fall per orsak, kontrollerna och
kontrollsummorna. Inga individrader, personnummer eller födelsemånader skrivs ut, och ingen
körning sparas – det gör operationen `run_valuation`.

Standard är demobeståndet i minnet. `--db lakebase` läser den delade databasen (DATABASE_URL ur
.env) med `SET TRANSACTION READ ONLY`; ingenting skrivs.

SIM-V-2026-01 gäller från 2026-12-31 och FI-SIM-2026-10 från 2026-10-31, medan avkastningsserien
AVK-SIM-2026-01 slutar 2026-10. En provvärdering per 2026-09-30 är därför ett scenario med
uttryckligen angiven grund och kurva (VARDERINGSKONTRAKT.md §2): den märks och blir aldrig bas.

Användning (från repo-roten, i .venv):
    python scripts/diagnostics/valuation_summary.py                       # demo, scenario 2026-09-30
    python scripts/diagnostics/valuation_summary.py --db lakebase --date 2026-09-30
    python scripts/diagnostics/valuation_summary.py --purpose base --date 2026-12-31
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from sqlalchemy import text
from sqlalchemy.orm import Session

from analytics.portfolio_snapshot import MIN_CELL, suppress_counts
from services.valuation import SOURCE_NOTE, compute_valuation


def _kr(amount: Decimal) -> str:
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",") + " kr"


def _engine(db: str):
    if db == "lakebase":
        from utils.db import make_engine

        return make_engine()
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from utils.demo_data import create_demo_database

    engine = create_engine("sqlite://", poolclass=StaticPool)
    create_demo_database(engine)
    return engine


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", choices=("demo", "lakebase"), default="demo")
    parser.add_argument("--date", type=date.fromisoformat, default=date(2026, 9, 30), help="Månadsslut")
    parser.add_argument("--purpose", choices=("base", "scenario"), default="scenario")
    parser.add_argument("--basis", default="SIM-V-2026-01", help="Scenario: värderingsgrund")
    parser.add_argument("--curve", default="FI-SIM-2026-10", help="Scenario: kurva")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    codes = {} if args.purpose == "base" else {"basis_code": args.basis, "curve_code": args.curve}
    engine = _engine(args.db)
    started = time.monotonic()
    with Session(engine) as session:
        if engine.dialect.name == "postgresql":
            session.execute(text("SET TRANSACTION READ ONLY"))
        c = compute_valuation(session, args.date, args.purpose, **codes)
        session.rollback()

    t = c.totals
    label = "SCENARIO – aldrig bas" if c.purpose == "scenario" else "basvärdering (utkast, inte sparad)"
    print(f"Värdering per {c.valuation_date} ({args.db}), {label}, {time.monotonic() - started:.0f} s")
    print(f"Märkning: {SOURCE_NOTE[c.extract.source]}")
    print(f"Grund: {c.basis.code} ({c.basis.checksum[:12]}), kurva: {c.curve.code} ({c.curve.checksum[:12]}), "
          f"s_y = {c.tax_reduction} ({c.tax_parameter})")
    print(f"Datautdrag: {c.extract.checksum}")
    print(f"Kodversion: {c.code_version}; resultatets kontrollsumma: {c.result_checksum}")
    for check in c.checks:
        print(f"  {'OK ' if check.passed else 'FEL'} {check.name}: {check.detail}")

    print(f"\nFörsäkringar: {t.policies}")
    print(f"Pensionskapital ΣC:            {_kr(t.capital)}")
    print(f"Garanterad pension ΣG:         {_kr(t.guarantee)} per månad")
    print(f"FTA:                           {_kr(t.fta)}")
    print(f"  därav garanterad pension:    {_kr(t.guarantee_value)}")
    print(f"  därav driftkostnader K:      {_kr(t.expenses)}")
    print(f"Villkorad återbäring VÅ:       {_kr(t.surplus)}")
    print(f"Underskott U:                  {_kr(t.deficit)}")
    print(f"VÅ − U = {_kr(t.surplus - t.deficit)}; ΣC − FTA = {_kr(t.capital - t.fta)}")
    with_deficit = sum(1 for v in c.values if v.deficit > 0)
    print(f"Försäkringar med underskott: {with_deficit if with_deficit == 0 or with_deficit >= MIN_CELL else 'dolt'}")

    hidden = suppress_counts({f"{s}|{k}": x.policies for (s, k), x in c.segments.items()})
    print(f"\nPer läge och födelsedecennium (celler med 1–{MIN_CELL - 1} försäkringar döljs):")
    print(f"  {'läge':<16}{'kohort':<12}{'antal':>6}{'C':>18}{'FTA':>18}{'VÅ':>18}{'U':>16}")
    for (state, cohort), x in c.segments.items():
        if f"{state}|{cohort}" in hidden:
            print(f"  {state:<16}{cohort:<12}{'dolt':>6}")
            continue
        print(f"  {state:<16}{cohort:<12}{x.policies:>6}{_kr(x.capital):>18}{_kr(x.fta):>18}{_kr(x.surplus):>18}"
              f"{_kr(x.deficit):>16}")
    reasons = Counter(n.reason for n in c.extract.not_calculated)
    hidden_reasons = suppress_counts(dict(reasons))
    for reason, n in reasons.items():
        print(f"Ej beräknade: {'dolt' if reason in hidden_reasons else n} – {reason}")


if __name__ == "__main__":
    main()
