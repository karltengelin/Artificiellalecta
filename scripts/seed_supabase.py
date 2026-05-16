"""Seedar Supabase med mockdata från `data/employers.csv` och
`data/insured_persons.csv`.

Stegen:
  1. Skapar tabellerna (om de inte finns) enligt SQLAlchemy-modellerna.
  2. Läser CSV-filerna och laddar in raderna i batchar.

Flaggor:
  --reset    Droppar och återskapar tabellerna innan inläsning.
  --append   Lägger till data utan att tömma. UPSERT på UNIQUE-nycklar (default).
  --dry-run  Skapar inga tabeller och skriver inget – verifierar bara att CSV
             är läsbara och att miljön är konfigurerad.

Användning:
    python scripts/seed_supabase.py            # idempotent append/upsert
    python scripts/seed_supabase.py --reset    # nuke + ladda om
    python scripts/seed_supabase.py --dry-run  # sanity check
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

# Säkerställ att `src/` finns på sys.path när skriptet körs direkt
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sqlalchemy.dialects.postgresql import insert  # noqa: E402

from models import Base, Employer, InsuredPerson  # noqa: E402
from utils.db import make_engine, session_scope  # noqa: E402


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_decimal(value: str) -> Decimal | None:
    if not value:
        return None
    return Decimal(value)


def load_employers(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for row in reader:
            rows.append({
                "id": UUID(row["id"]),
                "org_number": row["org_number"],
                "name": row["name"],
                "industry_code": row["industry_code"] or None,
                "address_street": row["address_street"] or None,
                "address_postal_code": row["address_postal_code"] or None,
                "address_city": row["address_city"] or None,
                "contact_name": row["contact_name"] or None,
                "contact_email": row["contact_email"] or None,
                "contact_phone": row["contact_phone"] or None,
                "collective_agreement": row["collective_agreement"] or "ITP",
                "affiliation_date": _parse_date(row["affiliation_date"]),
                "status": row["status"] or "active",
            })
        return rows


def load_insured(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for row in reader:
            rows.append({
                "id": UUID(row["id"]),
                "personal_id_number": row["personal_id_number"],
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "email": row["email"] or None,
                "phone": row["phone"] or None,
                "employer_id": UUID(row["employer_id"]),
                "employment_start_date": _parse_date(row["employment_start_date"]),
                "employment_end_date": _parse_date(row["employment_end_date"]),
                "monthly_salary_sek": _parse_decimal(row["monthly_salary_sek"]),
                "employment_rate": _parse_decimal(row["employment_rate"]),
                "itp1_start_date": _parse_date(row["itp1_start_date"]),
                "status": row["status"] or "active",
            })
        return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true",
                        help="Droppa och återskapa tabellerna innan inläsning")
    parser.add_argument("--dry-run", action="store_true",
                        help="Verifiera bara CSV och miljö – ingen DB-skrivning")
    parser.add_argument("--employers-csv", default="data/employers.csv")
    parser.add_argument("--insured-csv", default="data/insured_persons.csv")
    parser.add_argument("--echo-sql", action="store_true",
                        help="Skriv ut all SQL till stdout")
    args = parser.parse_args()

    employers_path = REPO_ROOT / args.employers_csv
    insured_path = REPO_ROOT / args.insured_csv

    print(f"Läser arbetsgivare från: {employers_path}")
    employer_rows = load_employers(employers_path)
    print(f"  {len(employer_rows)} rader")

    print(f"Läser försäkrade från:   {insured_path}")
    insured_rows = load_insured(insured_path)
    print(f"  {len(insured_rows)} rader")

    if args.dry_run:
        print("--dry-run: hoppar över DB-operationer")
        return

    engine = make_engine(echo=args.echo_sql)

    if args.reset:
        print("--reset: dropping all tables")
        Base.metadata.drop_all(engine)

    print("Skapar tabeller om de saknas")
    Base.metadata.create_all(engine)

    # UPSERT (insert ... on conflict do update) på UNIQUE-nycklar
    with session_scope(engine) as session:
        emp_stmt = insert(Employer).values(employer_rows)
        emp_stmt = emp_stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                col.name: emp_stmt.excluded[col.name]
                for col in Employer.__table__.columns
                if col.name not in ("id", "created_at")
            },
        )
        session.execute(emp_stmt)
        print(f"Upserted {len(employer_rows)} arbetsgivare")

        ins_stmt = insert(InsuredPerson).values(insured_rows)
        ins_stmt = ins_stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                col.name: ins_stmt.excluded[col.name]
                for col in InsuredPerson.__table__.columns
                if col.name not in ("id", "created_at")
            },
        )
        session.execute(ins_stmt)
        print(f"Upserted {len(insured_rows)} försäkrade")

    print("Klar.")


if __name__ == "__main__":
    main()
