"""Historiskt engångsskript för Fas 1e (B-022), inte en aktuell schemamigration.

Bevarat för spårbarhet. Tar bort tabeller och data; ska inte användas som
normal uppsättning eller uppgradering av dagens databas.

Droppar `premium_transactions` och `policies` (gamla strukturen) och skapar
`policies`, `policy_states`, `policy_benefits`, `premium_transactions` enligt
02_system/databasschema.md §5–8. Rör INTE `employers`, `insured_persons`
eller `base_amounts`.

All data i de droppade tabellerna är genererad och återskapas med
scripts/demo/generate_premium_history.py efteråt.

Användning (från repo-roten, i .venv):
    python scripts/migrations/legacy/rebuild_insurance_tables.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from sqlalchemy import inspect, text  # noqa: E402

from models import Base  # noqa: E402
from utils.db import make_engine  # noqa: E402

#: Droppas i denna ordning (transaktioner refererar policies via benefits)
TABLES_TO_DROP = ["premium_transactions", "policy_benefits", "policy_states", "policies"]


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    engine = make_engine()

    existing = set(inspect(engine).get_table_names())
    print(f"Tabeller före: {sorted(existing)}")

    with engine.begin() as conn:
        for table in TABLES_TO_DROP:
            if table in existing:
                conn.execute(text(f'DROP TABLE "{table}" CASCADE'))
                print(f"Droppade: {table}")

    Base.metadata.create_all(engine)

    after = set(inspect(engine).get_table_names())
    print(f"Tabeller efter: {sorted(after)}")
    print("Kör nu: python scripts/demo/generate_premium_history.py --dry-run")


if __name__ == "__main__":
    main()
