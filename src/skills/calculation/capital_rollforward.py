"""Pensionskapitalets månadsavräkning: avkastning, kapitalavgift, skattebelastning och premier (A5, B-042).

Instruktion: 03_skills/beräkning/kapitalavrakning.md
Domänregler: PR-ITP1-020 (ordningen), PR-ITP1-021 (avkastning), PR-ITP1-022 (avgift),
PR-ITP1-023 (skattebelastning); satserna ur 01_domän/parametrar/PARAMETERREGISTER.md

Ren beräkning utan sidoeffekter, i hela ören. Månaden för ett kollektiv av delar:

    avkastning_i = andel av round_half_up(Σ C_i_öppning × r) efter C_i_öppning × r, största bråkrest
    F_i          = min(round_half_up(C_i_öppning × 0,002/12), C_i efter avkastning)
    T_i          = min(round_half_up(C_i_öppning × s_y/12), C_i efter avgift)
    C_i_stängning = C_i_öppning + avkastning_i − F_i − T_i + månadens premier

Premier tillförs vid månadsslut och får avkastning, avgift och skatt först nästa månad. Det
som inte kan debiteras avstås av bolaget och blir ingen kundskuld. Arvsvinst (PR-011) och
pensionsdebitering (PR-020 steg 5–7) ingår inte: det rekonstruerade startbeståndet S-04 har
inga dödsfall eller påbörjade uttag, så poolen är noll.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
#: Kapitalavgift nominellt per år (B-021, PR-ITP1-022)
CAPITAL_FEE_RATE = Decimal("0.002")
#: Kundbelastning avkastningsskatt per år, 15 % × max(SLR året före, 0,5 %) (PARAMETERREGISTER.md, PR-ITP1-023)
CUSTOMER_TAX_RATES = {
    2023: Decimal("0.002190"),
    2024: Decimal("0.003720"),
    2025: Decimal("0.003225"),
    2026: Decimal("0.003540"),
}


class RollforwardError(ValueError):
    """Avräkningen kan inte göras, t.ex. saknad årssats eller ogiltig avkastning."""


def round_half_up(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def tax_rate(year: int) -> Decimal:
    """Årets skattebelastning; ett saknat år blockerar (PR-023: inte föregående års sats automatiskt)."""
    try:
        return CUSTOMER_TAX_RATES[year]
    except KeyError:
        raise RollforwardError(f"Skattebelastning för {year} saknas i parameterregistret") from None


def allocate_cents(total: Decimal, weights: Sequence[Decimal]) -> list[Decimal]:
    """Fördela `total` i hela ören proportionellt mot vikterna, med största bråkrest.

    Vikterna har samma tecken som beloppet; förluster fördelas på magnitud (PR-021) och
    arvsvinst efter E_i (PR-011). Lika rest avgörs av ordningen i `weights` (stabilt del-ID hos
    anroparen). Summan blir exakt `total`, och ingen andel överstiger sin exakta andel med ett öre.
    """
    if total != total.quantize(CENT):
        raise RollforwardError("Beloppet som fördelas ska vara i hela ören")
    sign = -1 if total < 0 else 1
    if any(w * sign < 0 for w in weights):
        raise RollforwardError("Vikterna ska ha samma tecken som beloppet")
    mass = sum((abs(w) for w in weights), Decimal(0))
    if mass == 0:
        if total != 0:
            raise RollforwardError("Ett belopp kan inte fördelas på vikten noll")
        return [Decimal("0.00")] * len(weights)
    cents = [abs(total) / CENT * abs(w) / mass for w in weights]
    floors = [c.to_integral_value(rounding=ROUND_FLOOR) for c in cents]
    left = int(abs(total) / CENT - sum(floors))
    order = sorted(range(len(weights)), key=lambda i: (-(cents[i] - floors[i]), i))
    for i in order[:left]:
        floors[i] += 1
    return [sign * f * CENT for f in floors]


@dataclass(frozen=True)
class Line:
    """En dels avräkning för månaden."""

    opening: Decimal
    investment_return: Decimal
    fee: Decimal
    tax: Decimal
    premiums: Decimal
    closing: Decimal
    fee_waived: Decimal = Decimal(0)
    tax_waived: Decimal = Decimal(0)


@dataclass(frozen=True)
class Month:
    month: date
    rate: Decimal
    lines: dict[Hashable, Line]

    def total(self, field: str) -> Decimal:
        return sum((getattr(line, field) for line in self.lines.values()), Decimal(0))


def close_month(
    month: date, rate: Decimal, openings: Mapping[Hashable, Decimal], premiums: Mapping[Hashable, Decimal],
) -> Month:
    """Avräkna en månad enligt PR-020 steg 1–4 för alla delar i `openings` och `premiums`.

    Delarna ordnas efter nyckel, så att fördelningen i ören är stabil.
    """
    if rate < -1:
        raise RollforwardError(f"Avkastningen {rate} för {month:%Y-%m} är under −100 %")
    keys = sorted(set(openings) | set(premiums))
    opening = {k: openings.get(k, Decimal(0)) for k in keys}
    added = {k: premiums.get(k, Decimal(0)) for k in keys}
    for k in keys:
        if opening[k] < 0 or opening[k] != opening[k].quantize(CENT):
            raise RollforwardError(f"Öppningskapitalet för {k} ska vara icke-negativt och i hela ören")
        if added[k] < 0:
            raise RollforwardError(f"Premien för {k} är negativ")
    shares = [opening[k] * rate for k in keys]
    returns = dict(zip(keys, allocate_cents(round_half_up(sum(shares, Decimal(0))), shares), strict=True))
    fee_rate, tax_monthly = CAPITAL_FEE_RATE / 12, tax_rate(month.year) / 12
    lines = {}
    for k in keys:
        available = opening[k] + returns[k]
        fee_due = round_half_up(opening[k] * fee_rate)
        fee = min(fee_due, available)
        tax_due = round_half_up(opening[k] * tax_monthly)
        tax = min(tax_due, available - fee)
        lines[k] = Line(opening[k], returns[k], fee, tax, added[k], available - fee - tax + added[k],
                        fee_due - fee, tax_due - tax)
    return Month(month, rate, lines)
