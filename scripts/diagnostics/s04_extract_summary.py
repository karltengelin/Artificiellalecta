"""Datautdraget S-04 som aggregat: garantidelar, pensionskapital och kontroller (A5, B-042 val L).

Bygger utdraget per ett månadsslut med `services.valuation_extract.build_extract` i en
skrivskyddad transaktion och skriver bara aggregat: antal, summor per år, kontrollerna och
utdragets kontrollsumma. Inga individrader, personnummer eller födelsemånader skrivs ut.
Utdraget sparas inte; samma bestånd, grunder och kod ger samma kontrollsumma.

Standard är demobeståndet i minnet. `--db lakebase` läser den delade databasen (DATABASE_URL ur
.env) med `SET TRANSACTION READ ONLY`; ingenting skrivs.

Användning (från repo-roten, i .venv):
    python scripts/diagnostics/s04_extract_summary.py                          # demo, 2026-09-30
    python scripts/diagnostics/s04_extract_summary.py --db lakebase --date 2026-09-30
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from services.valuation_extract import build_extract  # noqa: E402


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
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    engine = _engine(args.db)
    started = time.monotonic()
    with Session(engine) as session:
        if engine.dialect.name == "postgresql":
            session.execute(text("SET TRANSACTION READ ONLY"))
        extract = build_extract(session, args.date)
        session.rollback()

    print(f"Datautdrag S-04 per {extract.valuation_date} ({args.db}), {time.monotonic() - started:.0f} s")
    print(f"Kontrollsumma: {extract.checksum}")
    print(f"Grunder: {', '.join(extract.bases)}")
    print(f"Godkänt: {'ja' if extract.approved else 'NEJ'}")
    for check in extract.checks:
        print(f"  {'OK ' if check.passed else 'FEL'} {check.name}: {check.detail}")

    parts = [p for x in extract.policies for p in x.guarantee_parts]
    print(f"\nFörsäkringar i utdraget: {len(extract.policies)}; utan garanti och kapital: {extract.outside_population}")
    for state, n in sorted(Counter(x.state for x in extract.policies).items()):
        print(f"  {state}: {n}")
    for reason, n in Counter(n.reason for n in extract.not_calculated).items():
        print(f"  Ej beräknade: {n} – {reason}")
    print(f"Garantidelar: {len(parts)}, premier {_kr(sum((p.premium for p in parts), Decimal(0)))}")
    for basis, n in sorted(Counter(p.basis for p in parts).items()):
        print(f"  {basis}: {n}")
    print(f"Garanterad pension ΣG: {_kr(sum((p.guarantee for p in parts), Decimal(0)))} per månad")
    print(f"Pensionskapital ΣC: {_kr(sum((x.capital for x in extract.policies), Decimal(0)))}")

    years: dict[int, Counter] = defaultdict(Counter)
    for m in extract.months:
        for name in ("premiums", "returns", "fees", "taxes", "fees_waived", "taxes_waived"):
            years[m.month.year][name] += getattr(m, name)
    print("\nKapitalets rörelser per år (premier, avkastning, kapitalavgift, skattebelastning, avstått):")
    for year, v in sorted(years.items()):
        print(f"  {year}: {_kr(v['premiums'])}, {_kr(v['returns'])}, {_kr(v['fees'])}, {_kr(v['taxes'])}, "
              f"{_kr(v['fees_waived'] + v['taxes_waived'])}")


if __name__ == "__main__":
    main()
