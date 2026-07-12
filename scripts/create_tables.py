"""Skapar databastabeller som saknas i Lakebase.

Kör `Base.metadata.create_all` – skapar bara tabeller som inte redan finns,
befintliga tabeller och data rörs inte. Körs av operatören från Windows
(sandboxen når inte databasen). Se 02_system/databasschema.md §9.

Användning (från repo-roten):
    python scripts/create_tables.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Gör src/ importerbar när skriptet körs direkt från repo-roten
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import inspect  # noqa: E402

from models import Base  # noqa: E402
from utils.db import make_engine  # noqa: E402


def main() -> None:
    engine = make_engine()

    before = set(inspect(engine).get_table_names())
    print(f"Tabeller före: {sorted(before) or '(inga)'}")

    Base.metadata.create_all(engine)

    after = set(inspect(engine).get_table_names())
    created = sorted(after - before)
    print(f"Tabeller efter: {sorted(after)}")
    print(f"Nya tabeller: {created or '(inga – allt fanns redan)'}")


if __name__ == "__main__":
    main()
