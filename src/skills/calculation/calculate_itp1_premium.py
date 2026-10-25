"""Skill: Beräkna ITP1-premie (bolagets premiemotor).

Instruktion: 03_skills/beräkning/beräkna-itp1-premie.md
Domänregler: 01_domän/ITP1_regelverk.md §2-§4, §8

Ren beräkningsfunktion utan sidoeffekter: hämtar ingen data, skriver inga
transaktioner. Anroparen ansvarar för lön och IBB (tabellen base_amounts).

Premiesatser, brytpunkter och åldersfönster kommer som `PremiumParameters`
(B-035). Tjänstelagret slår upp dem i tabellen product_parameters för
premiemånaden; utan parametrar gäller paketets värden PR-ITP1 v1.0 nedan.

Avrundning: delbeloppen (4,5 %- och 30 %-delen) avrundas var för sig till
hela ören (ROUND_HALF_UP); totalen är summan av de avrundade delarna. Så
stämmer komponenterna alltid exakt med totalen, vilket krävs för
spårbarheten i premium_transactions.calculation_basis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

#: Premiesatser enligt ITP-avtalet (01_domän/ITP1_regelverk.md §2)
RATE_LOW = Decimal("0.045")
RATE_HIGH = Decimal("0.30")

#: Brytpunkter i antal IBB per år (delas med 12 för månadsbelopp)
BREAKPOINT_LOW_IBB = Decimal("7.5")
BREAKPOINT_HIGH_IBB = Decimal("30")

#: Åldersfönster (månadsbaserat, regelverket §4)
AGE_PREMIUM_START = 25
AGE_PREMIUM_END = 66  # premie t.o.m. månaden innan personen fyller 66

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class PremiumParameters:
    """Produktparametrar för premieberäkningen (B-035, databasschema §9h).

    `versions` anger varifrån varje värde kommer (parameter → version) och sparas
    i calculation_basis. Tomt för standardvärdena.
    """

    rate_low: Decimal = RATE_LOW
    rate_high: Decimal = RATE_HIGH
    breakpoint_low_ibb: Decimal = BREAKPOINT_LOW_IBB
    breakpoint_high_ibb: Decimal = BREAKPOINT_HIGH_IBB
    age_start: int = AGE_PREMIUM_START
    age_end: int = AGE_PREMIUM_END
    versions: dict[str, str] = field(default_factory=dict, compare=False)


DEFAULT_PARAMETERS = PremiumParameters()


@dataclass(frozen=True)
class PremiumCalculation:
    """Resultat av en premieberäkning för en månad."""

    total_premium_sek: Decimal
    amount_low_sek: Decimal
    amount_high_sek: Decimal
    in_age_window: bool | None  # None = åldersfönster ej kontrollerat
    calculation_basis: dict[str, Any] = field(default_factory=dict)


def months_since_birth(birth_date: date, period_month: date) -> int:
    """Hela månader från födelsemånaden till periodmånaden."""
    return (period_month.year - birth_date.year) * 12 + (
        period_month.month - birth_date.month
    )


def is_in_age_window(
    birth_date: date, period_month: date, parameters: PremiumParameters = DEFAULT_PARAMETERS
) -> bool:
    """True om premiemånaden ligger i åldersfönstret (månadsupplösning).

    Premie betalas fr.o.m. månaden personen fyller `age_start` t.o.m. månaden
    innan personen fyller `age_end` – med standardvärdena 25 och 66
    (regelverket §4, PR-ITP1-013).
    """
    months = months_since_birth(birth_date, period_month)
    return parameters.age_start * 12 <= months < parameters.age_end * 12


def calculate_itp1_premium(
    monthly_salary_sek: Decimal | str | int,
    income_base_amount_sek: Decimal | str | int,
    birth_date: date | None = None,
    period_month: date | None = None,
    parameters: PremiumParameters | None = None,
) -> PremiumCalculation:
    """Beräknar ITP1 ålderspensionspremie för en månad.

    Args:
        monthly_salary_sek: Pensionsmedförande lön för månaden (>= 0).
        income_base_amount_sek: IBB för premieåret (> 0), ur base_amounts.
        birth_date: Den försäkrades födelsedatum. Om satt krävs period_month,
            och premien blir 0 utanför åldersfönstret (25-66 som standard).
        period_month: Premiemånaden (dag ignoreras).
        parameters: Produktparametrar för premiemånaden; standard är PR-ITP1 v1.0.

    Raises:
        ValueError: negativ lön, icke-positivt IBB, eller birth_date utan
            period_month.
    """
    salary = Decimal(monthly_salary_sek)
    ibb = Decimal(income_base_amount_sek)

    if salary < 0:
        raise ValueError(
            "Pensionsmedförande lön kan inte vara negativ - korrigeringar "
            "hanteras som adjustment-transaktioner, inte negativa premier."
        )
    if ibb <= 0:
        raise ValueError("Inkomstbasbeloppet måste vara positivt.")
    if birth_date is not None and period_month is None:
        raise ValueError("period_month krävs när birth_date anges.")

    p = parameters or DEFAULT_PARAMETERS
    breakpoint_low = p.breakpoint_low_ibb * ibb / 12
    breakpoint_high = p.breakpoint_high_ibb * ibb / 12

    in_age_window: bool | None = None
    if birth_date is not None and period_month is not None:
        in_age_window = is_in_age_window(birth_date, period_month, p)

    if in_age_window is False:
        amount_low = Decimal("0.00")
        amount_high = Decimal("0.00")
    else:
        amount_low = (p.rate_low * min(salary, breakpoint_low)).quantize(
            _CENT, rounding=ROUND_HALF_UP
        )
        high_base = max(Decimal(0), min(salary, breakpoint_high) - breakpoint_low)
        amount_high = (p.rate_high * high_base).quantize(_CENT, rounding=ROUND_HALF_UP)

    total = amount_low + amount_high

    basis: dict[str, Any] = {
        "ibb": str(ibb),
        "breakpoint_low": str(breakpoint_low.quantize(_CENT)),
        "breakpoint_high": str(breakpoint_high.quantize(_CENT)),
        "rate_low": str(p.rate_low),
        "rate_high": str(p.rate_high),
        "amount_low": str(amount_low),
        "amount_high": str(amount_high),
        "monthly_salary": str(salary),
    }
    if in_age_window is not None:
        basis["in_age_window"] = in_age_window
    if p.versions:
        basis["age_window"] = [p.age_start, p.age_end]
        basis["parameters"] = dict(p.versions)

    return PremiumCalculation(
        total_premium_sek=total,
        amount_low_sek=amount_low,
        amount_high_sek=amount_high,
        in_age_window=in_age_window,
        calculation_basis=basis,
    )
