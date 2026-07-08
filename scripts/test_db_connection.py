"""Minimal anslutningstest mot DATABASE_URL.

Kör detta INNAN seed-skriptet, särskilt vid byte av databasleverantör
(se B-018 – öppen riskpunkt: fungerar extern SQLAlchemy-anslutning med
enkel användarnamn/lösenord mot Databricks Lakebase Free Edition?).

Gör ingen skrivning – kör bara `SELECT 1` och rapporterar tydligt om
anslutningen lyckas eller varför den inte gör det.

Användning:
    python scripts/test_db_connection.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sqlalchemy import text  # noqa: E402

from utils.db import make_engine  # noqa: E402


def main() -> None:
    print("Läser DATABASE_URL och försöker koppla upp...")
    try:
        engine = make_engine(echo=False)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            print(f"OK – anslutning lyckades, SELECT 1 gav: {result}")
    except Exception as exc:  # noqa: BLE001
        print("MISSLYCKADES – kunde inte koppla upp mot databasen.")
        print(f"Feltyp: {type(exc).__name__}")
        print(f"Meddelande: {exc}")
        print()
        print(
            "Om felet handlar om autentisering/behörighet: det kan vara "
            "B-018:s öppna riskpunkt – Databricks Free Edition saknar "
            "kontonivå-API, vilket kan påverka vissa autentiseringsvägar. "
            "Prova native Postgres-lösenord (inte OAuth-token) om du inte "
            "redan gör det."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
