"""Fas 1d: Skapar försäkringsavtal och genererar retroaktiv premiehistorik.

För varje försäkrad med ITP1-startdatum:
  1. Skapar ett försäkringsavtal i `policies` (ett per person, B-021).
     Status: 'active' om personen är aktiv, annars 'paid_up' (fribrev).
  2. Genererar en `premium`-transaktion per kalendermånad från
     max(ITP1-start, anställningsstart, HISTORY_START) t.o.m. HISTORY_END,
     begränsat av anställningens slut och åldersfönstret 25–66
     (01_domän/ITP1_regelverk.md §4). Premien beräknas med premiemotorn
     (03_skills/beräkning/beräkna-itp1-premie.md) och årets IBB ur
     `base_amounts`. Status 'paid' med paid_date den 15:e månaden efter.

Lönehistorik: aktuell månadslön antas ha ökat med LÖNEDEFLATOR per år –
lönen för år Y = dagens lön / (1 + LÖNEDEFLATOR)^(2026 − Y), avrundad till
hela kronor. Förenklad men deterministisk modell; verklig lön per månad
lagras i transaktionen så varje premie är reproducerbar oavsett modell.

Idempotent: personer som redan har avtal får inga dubbletter, och månader
som redan har en premium-transaktion hoppas över.

Användning (från repo-roten, i .venv):
    python scripts/generate_premium_history.py --dry-run   # visa vad som skulle skapas
    python scripts/generate_premium_history.py             # skriv till databasen
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from models import BaseAmount, InsuredPerson, Policy, PremiumTransaction  # noqa: E402
from skills.calculation.calculate_itp1_premium import (  # noqa: E402
    calculate_itp1_premium,
)
from utils.db import make_engine, session_scope  # noqa: E402

#: Historikfönster. Start styrs av basbeloppshistoriken (base_amounts fr. 2023).
HISTORY_START = date(2023, 1, 1)
HISTORY_END = date(2026, 6, 1)  # premie faktureras i efterskott – juli ej fakturerad

#: Antagen genomsnittlig årlig löneökning för retroaktiv lönemodell
SALARY_DEFLATOR = Decimal("0.025")

CURRENT_YEAR = 2026


def parse_birth_date(personal_id_number: str) -> date:
    """Födelsedatum ur personnummer YYYYMMDDXXXX."""
    return date(
        int(personal_id_number[0:4]),
        int(personal_id_number[4:6]),
        int(personal_id_number[6:8]),
    )


def month_of(d: date) -> date:
    """Första dagen i månaden för ett datum."""
    return date(d.year, d.month, 1)


def next_month(d: date) -> date:
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)


def iter_months(start: date, end: date):
    """Månadens första dag från start t.o.m. end (båda normaliserade)."""
    m = month_of(start)
    end = month_of(end)
    while m <= end:
        yield m
        m = next_month(m)


def salary_for_year(current_salary: Decimal, year: int) -> Decimal:
    """Antagen månadslön för ett historiskt år (deflaterad, hela kronor)."""
    factor = (1 + SALARY_DEFLATOR) ** (CURRENT_YEAR - year)
    return (current_salary / factor).quantize(Decimal("1"))


def paid_date_for(period: date) -> date:
    """Betaldatum: den 15:e i månaden efter premiemånaden."""
    nm = next_month(period)
    return date(nm.year, nm.month, 15)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Visa sammanfattning utan att skriva"
    )
    args = parser.parse_args()

    engine = make_engine()
    with session_scope(engine) as session:
        ibb_by_year = {
            ba.year: ba.income_base_amount_sek
            for ba in session.scalars(select(BaseAmount))
        }
        missing_years = [
            y
            for y in range(HISTORY_START.year, HISTORY_END.year + 1)
            if y not in ibb_by_year
        ]
        if missing_years:
            raise SystemExit(
                f"base_amounts saknar år {missing_years} – kör scripts/seed_base_amounts.py först."
            )

        persons = session.scalars(select(InsuredPerson)).all()
        existing_policies = {
            p.insured_person_id: p for p in session.scalars(select(Policy))
        }

        # Löpnummer för policy_number AL-NNNNNN
        seq = len(existing_policies)

        n_new_policies = 0
        n_new_tx = 0
        n_skipped_no_itp = 0
        n_skipped_no_salary = 0
        total_premium = Decimal("0")

        for person in persons:
            if person.itp1_start_date is None:
                n_skipped_no_itp += 1
                continue

            policy = existing_policies.get(person.id)
            if policy is None:
                seq += 1
                policy_status = (
                    "active" if person.status == "active" else "paid_up"
                )
                policy = Policy(
                    policy_number=f"AL-{seq:06d}",
                    insured_person_id=person.id,
                    start_date=month_of(person.itp1_start_date),
                    end_date=person.employment_end_date,
                    status=policy_status,
                )
                if not args.dry_run:
                    session.add(policy)
                    session.flush()  # ger policy.id
                n_new_policies += 1

            if person.monthly_salary_sek is None:
                n_skipped_no_salary += 1
                continue

            birth = parse_birth_date(person.personal_id_number)

            first = max(
                month_of(person.itp1_start_date),
                month_of(person.employment_start_date),
                HISTORY_START,
            )
            last = HISTORY_END
            if person.employment_end_date is not None:
                # Sista premiemånaden = anställningens sista månad
                last = min(last, month_of(person.employment_end_date))

            existing_periods: set[date] = set()
            if not args.dry_run and policy.id is not None:
                existing_periods = set(
                    session.scalars(
                        select(PremiumTransaction.period_month).where(
                            PremiumTransaction.policy_id == policy.id,
                            PremiumTransaction.transaction_type == "premium",
                        )
                    )
                )

            for period in iter_months(first, last):
                if period in existing_periods:
                    continue

                salary = salary_for_year(person.monthly_salary_sek, period.year)
                calc = calculate_itp1_premium(
                    salary,
                    ibb_by_year[period.year],
                    birth_date=birth,
                    period_month=period,
                )
                if calc.in_age_window is False or calc.total_premium_sek == 0:
                    continue

                if not args.dry_run:
                    session.add(
                        PremiumTransaction(
                            policy_id=policy.id,
                            period_month=period,
                            transaction_type="premium",
                            pensionable_salary_sek=salary,
                            amount_sek=calc.total_premium_sek,
                            calculation_basis=calc.calculation_basis,
                            status="paid",
                            paid_date=paid_date_for(period),
                        )
                    )
                n_new_tx += 1
                total_premium += calc.total_premium_sek

        mode = "DRY-RUN (inget skrivet)" if args.dry_run else "SKRIVET till databasen"
        print(f"--- {mode} ---")
        print(f"Försäkrade totalt:        {len(persons)}")
        print(f"Nya försäkringsavtal:     {n_new_policies}")
        print(f"Nya premietransaktioner:  {n_new_tx}")
        print(f"Summa premier:            {total_premium:,.2f} kr")
        print(f"Hoppade (ej ITP1-start):  {n_skipped_no_itp}")
        print(f"Hoppade (lön saknas):     {n_skipped_no_salary}")

        if args.dry_run:
            session.rollback()


if __name__ == "__main__":
    main()
