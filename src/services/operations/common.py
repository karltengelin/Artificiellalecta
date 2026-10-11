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
