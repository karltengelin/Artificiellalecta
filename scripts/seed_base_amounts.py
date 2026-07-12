"""Seedar basbeloppstabellen med IBB 2023–2026.

Värden ur 01_domän/ITP1_regelverk.md §6 (verifierade 2026-07-12).
Idempotent: befintliga år uppdateras, nya läggs till (upsert).

Användning (från repo-roten, i .venv):
    python scripts/seed_base_amounts.py
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sqlalchemy.dialects.postgresql import insert  # noqa: E402

from models import BaseAmount  # noqa: E402
from utils.db import make_engine, session_scope  # noqa: E402

BASE_AMOUNTS = [
    {"year": 2023, "income_base_amount_sek": Decimal("74300"), "source": "Regeringen/Pensionsmyndigheten (historik, se ITP1_regelverk.md §6)"},
    {"year": 2024, "income_base_amount_sek": Decimal("76200"), "source": "Regeringen/Pensionsmyndigheten (historik, se ITP1_regelverk.md §6)"},
    {"year": 2025, "income_base_amount_sek": Decimal("80600"), "source": "Regeringen/Pensionsmyndigheten (historik, se ITP1_regelverk.md §6)"},
    {"year": 2026, "income_base_amount_sek": Decimal("83400"), "source": "Förordning (2025:1002)"},
]


def main() -> None:
    engine = make_engine()
    with session_scope(engine) as session:
        for row in BASE_AMOUNTS:
            stmt = insert(BaseAmount).values(**row)
            stmt = stmt.on_conflict_do_update(
                index_elements=[BaseAmount.year],
                set_={
                    "income_base_amount_sek": stmt.excluded.income_base_amount_sek,
                    "source": stmt.excluded.source,
                },
            )
            session.execute(stmt)
    print(f"Seedade/uppdaterade {len(BASE_AMOUNTS)} basbeloppsår: "
          f"{[r['year'] for r in BASE_AMOUNTS]}")


if __name__ == "__main__":
    main()
