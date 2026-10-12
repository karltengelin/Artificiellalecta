"""Gemensamma hjälpare för tjänstelagrets operationer (Fas 1f T3)."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from models import InsuredPerson, Policy, PolicyBenefit, PremiumTransaction
from services.errors import BlockedError, NotFoundError


def today() -> date:
    """Dagens datum – en funktion så att tester kan sätta dagen."""
    return date.today()


def month_of(d: date) -> date:
    return d.replace(day=1)


def next_day(d: date) -> date:
    return d + timedelta(days=1)


def birth_date(personal_id_number: str) -> date:
    """Födelsedatum ur personnummer ÅÅÅÅMMDDNNNN."""
    try:
        return date(int(personal_id_number[0:4]), int(personal_id_number[4:6]), int(personal_id_number[6:8]))
    except ValueError:
        raise BlockedError("Födelsedatum går inte att läsa ur personnumret – manuell prövning") from None


def luhn_valid(digits: str) -> bool:
    """Kontrollsiffran i personnummer (de tio sista siffrorna) och organisationsnummer."""
    if not digits.isdigit():
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char) * (2 if index % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def valid_personal_id_number(personal_id_number: str) -> bool:
    """ÅÅÅÅMMDDNNNN med giltigt datum och kontrollsiffra (databasschema §10)."""
    if len(personal_id_number) != 12 or not personal_id_number.isdigit():
        return False
    try:
        date(int(personal_id_number[0:4]), int(personal_id_number[4:6]), int(personal_id_number[6:8]))
    except ValueError:
        return False
    return luhn_valid(personal_id_number[2:])


def valid_org_number(org_number: str) -> bool:
    return len(org_number) == 10 and luhn_valid(org_number)


def month_offset(d: date, years: int) -> date:
    """Månaden `years` år efter d:s månad, t.ex. 25-årsmånaden ur födelsedatumet."""
    return date(d.year + years, d.month, 1)


def lock_person(session, personal_id_number: str) -> InsuredPerson:
    """Den försäkrade, låst för ändring under transaktionen (radlås i Postgres)."""
    person = session.scalar(
        select(InsuredPerson).where(InsuredPerson.personal_id_number == personal_id_number).with_for_update()
    )
    if person is None:
        raise NotFoundError("Ingen försäkrad med det personnumret")
    return person


def benefit_ids_of(session, person_id) -> list:
    return list(
        session.scalars(
            select(PolicyBenefit.id).join(Policy, PolicyBenefit.policy_id == Policy.id)
            .where(Policy.insured_person_id == person_id)
        )
    )


def premium_rows_in_month(session, benefit_ids: list, period_month: date) -> list[PremiumTransaction]:
    """Premie- och justeringsrader (ej makulerade) för personens förmåner en månad."""
    if not benefit_ids:
        return []
    return list(
        session.scalars(
            select(PremiumTransaction)
            .where(
                PremiumTransaction.benefit_id.in_(benefit_ids),
                PremiumTransaction.period_month == period_month,
                PremiumTransaction.transaction_type.in_(("premium", "adjustment")),
                PremiumTransaction.status != "cancelled",
            )
            .order_by(PremiumTransaction.transaction_type.desc(), PremiumTransaction.created_at)
        )
    )
