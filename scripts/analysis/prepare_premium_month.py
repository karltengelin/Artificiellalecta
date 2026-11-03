"""Validera/frys novemberförsöket. Lakebase läses endast med READ ONLY.

Kräver ett granskat IB-hashvärde. Skriver aldrig till någon databas och antar
ingen grund. --output får bara ligga i repots ignorerade tmp/premium_month/.
Utan --output skrivs endast aggregerad förkontroll ut.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.premium_month_inputs import extended_returns
from services.premium_month_preparation import prepare_inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", choices=("lakebase",), required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--expected-opening-checksum", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    target = args.output.resolve() if args.output else None
    allowed = (ROOT / "tmp" / "premium_month").resolve()
    if target and (not target.is_relative_to(allowed) or target == allowed):
        parser.error("Underlaget innehåller interna individreferenser; --output ska ligga i tmp/premium_month/")
    if target and target.exists():
        parser.error("Filen finns redan; ett fryst underlag skrivs aldrig över")
    from utils.db import make_engine

    engine = make_engine()
    with Session(engine) as session:
        session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        package = prepare_inputs(session, args.scenario, args.expected_opening_checksum)
        session.rollback()
    proposed = extended_returns(package)
    if target:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as stream:
            stream.write(package.model_dump_json(indent=2))
    print(json.dumps({"scenario": package.scenario_id, "synthetic": True, "checksum": package.checksum,
        "opening_checksum": package.opening.checksum, "policies": len(package.opening.policies),
        "invoices": len(package.invoices), "receipts": len(package.receipts),
        "avk_proposal_months": len(proposed["months"]), "written": str(target) if target else None,
        "database_writes": False}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
