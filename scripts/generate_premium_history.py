"""Fas 1d/1e: Skapar försäkringar med förmåner, lägen och premiehistorik.

För varje försäkrad med ITP1-startdatum (som inte slutade före ITP1-start):
  1. Försäkring i `policies` (produktkod ITP1, tecknad = ikraftträdande)
  2. Förmån `retirement_dc` i `policy_benefits`
  3. Lägeshistorik i `policy_states`:
       - `premium_paying` från start; öppen om personen är aktiv
       - annars stängd vid anställningens slut, följd av öppet `paid_up` (fribrev)
  4. En `premium`-transaktion per kalendermånad på förmånen, från
     max(ITP1-start, anställningsstart, HISTORY_START) t.o.m. HISTORY_END,
     begränsad av anställningens slut och åldersfönstret 25–66.
     Premie via premiemotorn med årets IBB ur `base_amounts`.

Lönehistorik: dagens lön deflaterad med SALARY_DEFLATOR per år bakåt
(hela kronor). Verklig lön lagras per transaktion, så varje premie är
reproducerbar oavsett lönemodell.

Idempotent: personer med befintlig försäkring får inga dubbletter, och
månader som redan har premium-transaktion på förmånen hoppas över.

Användning (från repo-roten, i .venv):
    python scripts/generate_premium_history.py --dry-run
    python scripts/generate_premium_history.py
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from models import (  # noqa: E402
    BaseAmount,
    InsuredPerson,
    Policy,
    PolicyBenefit,
    PolicyState,
    PremiumTransaction,
)
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
        persons_with_policy = set(
            session.scalars(select(Policy.insured_person_id))
        )
        seq = len(persons_with_policy)

        n_new_policies = 0
        n_new_tx = 0
        n_skipped_no_itp = 0
        n_skipped_no_salary = 0
        n_skipped_no_coverage = 0
        total_premium = Decimal("0")

        for person in persons:
            if person.itp1_start_date is None:
                n_skipped_no_itp += 1
                continue

            # Slutade innan ITP1-täckningen började → ingen försäkring alls
            if (
                person.employment_end_date is not None
                and month_of(person.employment_end_date)
                < month_of(person.itp1_start_date)
            ):
                n_skipped_no_coverage += 1
                continue

            policy_start = month_of(person.itp1_start_date)

            if person.id in persons_with_policy:
                # Befintlig försäkring – hämta dess ålderspensionsförmån
                policy = session.scalars(
                    select(Policy).where(Policy.insured_person_id == person.id)
                ).first()
                benefit = next(
                    (b for b in policy.benefits if b.benefit_type == "retirement_dc"),
                    None,
                )
                if benefit is None:
                    continue  # försäkring utan pensionsförmån – rör ej
            else:
                seq += 1
                policy = Policy(
                    policy_number=f"AL-{seq:06d}",
                    insured_person_id=person.id,
                    product_code="ITP1",
                    signed_date=policy_start,
                    start_date=policy_start,
                )
                benefit = PolicyBenefit(
                    policy=policy,
                    benefit_type="retirement_dc",
                    start_date=policy_start,
                )

                # Lägeshistorik
                if person.employment_end_date is None or person.status == "active":
                    states = [
                        PolicyState(
                            policy=policy,
                            state="premium_paying",
                            valid_from=policy_start,
                            valid_to=None,
                        )
                    ]
                else:
                    end = person.employment_end_date
                    states = [
                        PolicyState(
                            policy=policy,
                            state="premium_paying",
                            valid_from=policy_start,
                            valid_to=end,
                        ),
                        PolicyState(
                            policy=policy,
                            state="paid_up",
                            valid_from=end + timedelta(days=1),
                            valid_to=None,
                            note="Anställning upphörde (fribrev)",
                        ),
                    ]

                if not args.dry_run:
                    session.add(policy)
                    session.add(benefit)
                    session.add_all(states)
                    session.flush()  # ger policy.id och benefit.id
                n_new_policies += 1

            if person.monthly_salary_sek is None:
                n_skipped_no_salary += 1
                continue

            birth = parse_birth_date(person.personal_id_number)

            first = max(
                policy_start,
                month_of(person.employment_start_date),
                HISTORY_START,
            )
            last = HISTORY_END
            if person.employment_end_date is not None:
                last = min(last, month_of(person.employment_end_date))

            existing_periods: set[date] = set()
            if not args.dry_run and benefit.id is not None:
                existing_periods = set(
                    session.scalars(
                        select(PremiumTransaction.period_month).where(
                            PremiumTransaction.benefit_id == benefit.id,
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
                            benefit_id=benefit.id,
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
        print(f"Nya försäkringar:         {n_new_policies}")
        print(f"Nya premietransaktioner:  {n_new_tx}")
        print(f"Summa premier:            {total_premium:,.2f} kr")
        print(f"Hoppade (ej ITP1-start):  {n_skipped_no_itp}")
        print(f"Hoppade (lön saknas):     {n_skipped_no_salary}")
        print(f"Hoppade (slutade före ITP1-start): {n_skipped_no_coverage}")

        if args.dry_run:
            session.rollback()


if __name__ == "__main__":
    main()
