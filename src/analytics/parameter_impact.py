"""Konsekvens för beståndet av en ändrad produktparameter (Fas 3c 3c-B, B-035).

Ren beräkning utan databas. Anroparen (tjänsteoperationen
estimate_parameter_change_impact) lämnar de aktiva försäkrades födelsedatum och
lön utan identitet, parametrarna per premiemånad för baslinje och scenario och
inkomstbasbeloppet per år. Premien räknas med premiemotorn för varje person och
månad, baslinje och scenario var för sig.

Celler med färre än MIN_CELL individer döljs (harness.md §5.1). Fler celler döljs
vid behov, så att en dold cell inte kan räknas fram som totalen minus de synliga.
En månad utan parametrar gör året ej beräknat – aldrig noll.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Mapping

from skills.calculation.calculate_itp1_premium import PremiumParameters, calculate_itp1_premium

ZERO = Decimal("0.00")
#: Minsta antal individer i en synlig cell (harness.md §5.1)
MIN_CELL = 10
#: Belopp redovisas i hela tusental kronor – grövre än en enskild månadspremie
ROUNDING = Decimal("1000")

COMPUTED = "beräknad"
HIDDEN = "dold"
NOT_COMPUTED = "ej beräknad"
PRIMARY = f"färre än {MIN_CELL} individer"
COMPLEMENTARY = "kompletterande döljning – annars går en dold cell att räkna fram ur totalen"


@dataclass(frozen=True)
class PersonBasis:
    """En aktiv försäkrad utan identitet: bara det premieberäkningen behöver."""

    birth_date: date
    monthly_salary: Decimal
    last_month: date | None = None  # sista anställningsmånaden; None = tills vidare


@dataclass
class _Year:
    year: int
    months: int = 0
    missing: str | None = None  # första skälet till att en månad inte gick att räkna
    paying: set[int] = field(default_factory=set)  # personer med premie i baslinjen
    affected: set[int] = field(default_factory=set)  # personer vars premie ändras
    extra_months: int = 0
    baseline: Decimal = ZERO
    scenario: Decimal = ZERO


@dataclass(frozen=True)
class YearImpact:
    year: int
    months: int
    status: str
    affected: int | None
    extra_months: int | None
    extra_volume: Decimal | None
    baseline_volume: Decimal | None
    scenario_volume: Decimal | None
    note: str | None = None


@dataclass(frozen=True)
class ImpactEstimate:
    persons: int | None
    excluded: int | None
    years: tuple[YearImpact, ...]
    totals_status: str
    affected_total: int | None
    extra_months_total: int | None
    extra_volume_total: Decimal | None
    first_affected_year: int | None
    hidden_cells: tuple[tuple[str, str], ...]


def rounded(value: Decimal) -> Decimal:
    return (value / ROUNDING).quantize(Decimal(1), rounding=ROUND_HALF_UP) * ROUNDING


def _count(value: int) -> int | None:
    """Ett antal individer: noll och minst MIN_CELL visas, 1–9 döljs."""
    return value if value == 0 or value >= MIN_CELL else None


def _small(ids: set) -> bool:
    return 0 < len(ids) < MIN_CELL


def _suppress(cells: Mapping[int, set[int]]) -> dict[int, str]:
    """Primär döljning av små celler och kompletterande döljning mot totalen.

    De dolda cellerna ska tillsammans omfatta minst MIN_CELL individer – annars döljs
    den minsta synliga cellen med berörda, tills villkoret håller.
    """
    hidden = {year: PRIMARY for year, ids in cells.items() if _small(ids)}
    union = set().union(*(cells[year] for year in hidden)) if hidden else set()
    candidates = sorted((len(ids), year) for year, ids in cells.items() if ids and year not in hidden)
    while hidden and len(union) < MIN_CELL and candidates:
        _, year = candidates.pop(0)
        hidden[year] = COMPLEMENTARY
        union |= cells[year]
    return hidden


def estimate_impact(
    persons: Iterable[PersonBasis],
    *,
    months: Iterable[date],
    baseline: Mapping[date, PremiumParameters | str],
    scenario: Mapping[date, PremiumParameters | str],
    ibb: Mapping[int, Decimal],
    excluded: int = 0,
) -> ImpactEstimate:
    """Baslinje mot scenario per kalenderår för `months` (månadsförstor).

    `baseline` och `scenario` ger parametrarna per månad, eller ett skäl (text) när
    månaden inte gick att slå upp – då blir året ej beräknat. `excluded` är antalet
    aktiva som inte kunde räknas (saknad lön eller födelsedatum).
    """
    persons = list(persons)
    months = sorted(set(months))
    if any(m.day != 1 for m in months):
        raise ValueError("Premiemånader ska vara månadens första dag")
    years: dict[int, _Year] = {}
    usable: list[date] = []
    for month in months:
        cell = years.setdefault(month.year, _Year(month.year))
        cell.months += 1
        reason = next((p for p in (baseline[month], scenario[month]) if isinstance(p, str)), None)
        if reason is not None:
            cell.missing = cell.missing or f"{month:%Y-%m}: {reason}"
        else:
            usable.append(month)

    for index, person in enumerate(persons):
        for month in usable:
            if person.last_month is not None and month > person.last_month:
                break
            base_p, scen_p = baseline[month], scenario[month]
            args = (person.monthly_salary, ibb[month.year])
            base = calculate_itp1_premium(*args, birth_date=person.birth_date, period_month=month, parameters=base_p)
            scen = base if scen_p == base_p else calculate_itp1_premium(
                *args, birth_date=person.birth_date, period_month=month, parameters=scen_p
            )
            cell = years[month.year]
            cell.baseline += base.total_premium_sek
            cell.scenario += scen.total_premium_sek
            if base.total_premium_sek > 0:
                cell.paying.add(index)
            if base.total_premium_sek != scen.total_premium_sek:
                cell.affected.add(index)
            cell.extra_months += int(bool(scen.in_age_window)) - int(bool(base.in_age_window))

    computed = {year: cell for year, cell in years.items() if cell.missing is None}
    hidden_impact = _suppress({year: cell.affected for year, cell in computed.items()})
    hidden_cells: list[tuple[str, str]] = []
    result: list[YearImpact] = []
    for year, cell in sorted(years.items()):
        if cell.missing is not None:
            result.append(YearImpact(year, cell.months, NOT_COMPUTED, None, None, None, None, None, cell.missing))
            continue
        base_hidden = _small(cell.paying)
        impact_hidden = year in hidden_impact
        if impact_hidden:
            hidden_cells.append((f"{year}: berörda, extra premiemånader, extra premievolym och scenario", hidden_impact[year]))
        if base_hidden:
            hidden_cells.append((f"{year}: premievolym i baslinjen och scenario", PRIMARY))
        result.append(YearImpact(
            year, cell.months, HIDDEN if impact_hidden else COMPUTED,
            None if impact_hidden else len(cell.affected),
            None if impact_hidden else cell.extra_months,
            None if impact_hidden else rounded(cell.scenario - cell.baseline),
            None if base_hidden else rounded(cell.baseline),
            None if base_hidden or impact_hidden else rounded(cell.scenario),
        ))

    affected = set().union(*(cell.affected for cell in computed.values())) if computed else set()
    first = min((year for year, cell in computed.items() if cell.affected), default=None)
    if len(computed) < len(years):
        totals = (NOT_COMPUTED, None, None, None)
    elif _small(affected):
        totals = (HIDDEN, None, None, None)
        hidden_cells.append(("Totalt: berörda, extra premiemånader och extra premievolym", PRIMARY))
    else:
        totals = (
            COMPUTED, len(affected), sum(cell.extra_months for cell in computed.values()),
            rounded(sum((cell.scenario - cell.baseline for cell in computed.values()), ZERO)),
        )
    population = _count(len(persons))
    if population is None:
        hidden_cells.append(("Antal aktiva försäkrade i beräkningen", PRIMARY))
    excluded_count = _count(excluded)
    if excluded_count is None:
        hidden_cells.append(("Antal aktiva som inte kunde beräknas", PRIMARY))
    return ImpactEstimate(
        population, excluded_count, tuple(result), *totals, first, tuple(hidden_cells),
    )
