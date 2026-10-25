"""Beståndsinsikt: vad en ändrad produktparameter betyder för beståndet (Fas 3c 3c-B, B-035).

`estimate_parameter_change_impact` räknar i betrodd kod, med premiemotorn, baslinje mot
scenario för de aktiva försäkrade år för år. Baslinjen är de parametrar som gäller varje
månad enligt `product_parameters` (även schemalagda versioner); scenariot är samma
parametrar med det nya värdet från giltighetsdagen. Beräkningen i analytics/parameter_impact.py.

Operationen läser individrader internt men lämnar bara aggregat: inga personnummer,
namn, födelsedatum eller löner. Celler med färre än 10 individer döljs (harness.md §5.1),
och antagandena står i svaret. Monterad i podden `bestand` sedan 3c-T; skillkatalogen visar
den med parametermandat (3c-T).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import exists, select

from analytics import parameter_impact
from models import BaseAmount, InsuredPerson, Policy, PolicyState, ProductParameter
from services import parameters
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, ConflictError, NotFoundError, ServiceError
from services.operations import common
from services.operations.product_parameters import ParameterKey, check_parameter_value, first_of_next_month

#: Längsta prognos – den yngsta aktiva har då passerat dagens premieålder
MAX_HORIZON_YEARS = 45


class ParameterImpactQuery(BaseModel):
    key: ParameterKey = Field(description="Parametern som ändras, t.ex. premium_age_end")
    value: Decimal = Field(
        ge=0, description="Nytt värde i parameterns enhet: hela år, andel (0,045 = 4,5 %) eller antal IBB"
    )
    valid_from: date = Field(description="Första premiemånad som omfattas – en månadsförsta, tidigast nästa månad")
    horizon_years: int = Field(
        default=10, ge=1, le=MAX_HORIZON_YEARS, description="Antal år från giltighetsdagen som räknas"
    )

    @field_validator("valid_from")
    @classmethod
    def _first_of_month(cls, value: date) -> date:
        if value.day != 1:
            raise ValueError("Giltighetsdagen måste vara den första i månaden")
        return value


class YearImpact(BaseModel):
    year: int
    months: int = Field(description="Antal premiemånader i perioden detta år")
    status: str = Field(description="beräknad, dold (färre än 10 berörda) eller ej beräknad")
    affected_persons: int | None = Field(description="Aktiva vars premie ändras detta år; None = dold eller ej beräknad")
    extra_premium_months: int | None = Field(description="Premiemånader i scenariot minus baslinjen (negativt om färre)")
    extra_premium_volume_sek: Decimal | None = Field(description="Premievolym i scenariot minus baslinjen, hela tusental kronor")
    baseline_premium_volume_sek: Decimal | None = Field(description="Premievolym för de aktiva med baslinjens parametrar")
    scenario_premium_volume_sek: Decimal | None = Field(description="Premievolym för de aktiva med det nya värdet")
    note: str | None = Field(default=None, description="Varför året inte gick att beräkna")


class HiddenCell(BaseModel):
    cell: str
    reason: str


class ParameterImpactEstimate(BaseModel):
    key: str
    current_value: Decimal = Field(description="Värdet i baslinjen på giltighetsdagen")
    current_version: str = Field(description="Versionen i product_parameters som baslinjen bygger på")
    value: Decimal = Field(description="Scenariots värde")
    valid_from: date
    period_from: date
    period_to: date = Field(description="Sista premiemånaden i beräkningen")
    active_persons: int | None = Field(description="Aktiva försäkrade i beräkningen; None = färre än 10")
    excluded_persons: int | None = Field(description="Aktiva som inte kunde beräknas (lön eller födelsedatum saknas)")
    totals_status: str = Field(description="beräknad, dold eller ej beräknad")
    affected_persons_total: int | None = Field(description="Aktiva vars premie ändras något år i perioden")
    extra_premium_months_total: int | None
    extra_premium_volume_total_sek: Decimal | None = Field(description="Hela tusental kronor")
    first_affected_year: int | None = Field(description="Första året någon aktiv berörs; None = ingen i perioden")
    years: list[YearImpact]
    hidden_cells: list[HiddenCell]
    min_cell_size: int = Field(description="Celler med färre individer än så döljs")
    assumptions: list[str]


def _months(start: date, years: int) -> list[date]:
    return [date(start.year + (start.month - 1 + i) // 12, (start.month - 1 + i) % 12 + 1, 1) for i in range(years * 12)]


def _money(value: Decimal) -> str:
    return f"{value:,.0f}".replace(",", " ")


def _ibb_by_year(session, years: list[int]) -> tuple[dict[int, Decimal], str]:
    """Fastställt IBB per år; år utan belopp får det senast fastställda (inga uppräkningar)."""
    known = {row.year: row.income_base_amount_sek for row in session.scalars(select(BaseAmount))}
    if not known:
        raise NotFoundError("Inkomstbasbelopp saknas (tabellen base_amounts)")
    latest = max(known)
    result = {year: known.get(year, known[max((y for y in known if y <= year), default=latest)]) for year in years}
    note = f"senast fastställda {latest}: {_money(known[latest])} kr"
    return result, note


def _active_persons(session) -> tuple[list[parameter_impact.PersonBasis], int]:
    """Aktiva försäkrade med premiebetalande försäkring – identiteten lämnar aldrig funktionen."""
    paying = exists().where(
        Policy.insured_person_id == InsuredPerson.id,
        PolicyState.policy_id == Policy.id,
        PolicyState.state == "premium_paying",
        PolicyState.valid_to.is_(None),
    )
    rows = session.execute(
        select(InsuredPerson.personal_id_number, InsuredPerson.monthly_salary_sek, InsuredPerson.employment_end_date)
        .where(InsuredPerson.status == "active", paying)
    ).all()
    persons, excluded = [], 0
    for pnr, salary, end in rows:
        try:
            born = common.birth_date(pnr)
        except BlockedError:
            excluded += 1
            continue
        if salary is None:
            excluded += 1
            continue
        persons.append(parameter_impact.PersonBasis(born, Decimal(salary), common.month_of(end) if end else None))
    return persons, excluded


def _scenario(base, field: str, value, label: str):
    """Baslinjens parametrar med det nya värdet – eller ett skäl om de inte hänger ihop."""
    if isinstance(base, str):
        return base
    scen = replace(base, **{field: value}, versions={**base.versions, "scenario": label})
    if not (scen.age_start < scen.age_end and scen.breakpoint_low_ibb < scen.breakpoint_high_ibb):
        return "parametrarna hänger inte ihop med det nya värdet"
    return scen


@operation(
    name="estimate_parameter_change_impact",
    description=(
        "Uppskattar vad en ändrad produktparameter – premieålder, premiesats eller brytpunkt – betyder för "
        "beståndet: antal berörda aktiva försäkrade, extra premiemånader och extra premievolym per år, och "
        "första berörda år. Baslinjen är de parametrar som gäller enligt produktparametrarna. Bara aggregat; "
        "celler med färre än 10 individer döljs. Ändrar ingenting."
    ),
    kind=OperationKind.READ,
    rules=["PR-ITP1-001", "PR-ITP1-013"],
)
def estimate_parameter_change_impact(ctx: OperationContext, data: ParameterImpactQuery) -> ParameterImpactEstimate:
    session = ctx.require_session()
    earliest = first_of_next_month(common.today())
    if data.valid_from < earliest:
        raise BlockedError(
            f"Giltighetsdagen {data.valid_from} är passerad eller i innevarande månad – tidigast {earliest}. "
            "En parameter ändras aldrig retroaktivt (PR-ITP1-032)"
        )
    if not parameters.has_parameter_table(session):
        raise BlockedError("Tabellen product_parameters saknas – baslinjen kan inte läsas (kör migrationen)")
    check_parameter_value(session, data.key, data.value, data.valid_from)
    later = session.scalar(
        select(ProductParameter.valid_from).where(
            ProductParameter.key == data.key, ProductParameter.status == "valid",
            ProductParameter.valid_from > data.valid_from,
        ).order_by(ProductParameter.valid_from)
    )
    if later is not None:
        raise ConflictError(
            f"Det finns en schemalagd version av {data.key} från {later} – scenariot från {data.valid_from} "
            "blir tvetydigt. Räkna från den dagen eller dra tillbaka versionen först"
        )
    current = parameters.versions_on(session, data.valid_from, keys=(data.key,)).get(data.key)
    if current is None:
        raise NotFoundError(f"Ingen version av {data.key} gäller {data.valid_from} att jämföra med")

    months = _months(data.valid_from, data.horizon_years)
    field = parameters.PREMIUM_FIELDS[data.key]
    value = int(data.value) if field in parameters.AGE_FIELDS else data.value
    label = f"{data.key} = {parameters.plain(data.value)} från {data.valid_from.isoformat()} (scenario)"
    baseline = {
        month: str(found) if isinstance(found, ServiceError) else found
        for month, found in parameters.monthly_premium_parameters(session, months).items()
    }
    scenario = {month: _scenario(base, field, value, label) for month, base in baseline.items()}
    ibb, ibb_note = _ibb_by_year(session, sorted({m.year for m in months}))
    persons, excluded = _active_persons(session)

    result = parameter_impact.estimate_impact(
        persons, months=months, baseline=baseline, scenario=scenario, ibb=ibb, excluded=excluded,
    )
    years = [
        YearImpact(
            year=y.year, months=y.months, status=y.status, affected_persons=y.affected,
            extra_premium_months=y.extra_months, extra_premium_volume_sek=y.extra_volume,
            baseline_premium_volume_sek=y.baseline_volume, scenario_premium_volume_sek=y.scenario_volume,
            note=y.note,
        )
        for y in result.years
    ]
    assumptions = [
        "Beståndet är dagens aktiva försäkrade med premiebetalande försäkring. Inga nyanställda, inga avgångar "
        "och ingen dödlighet; ett känt slutdatum för anställningen följs.",
        "Lönen är dagens månadslön i stamdata, oförändrad hela perioden – ingen lönetillväxt.",
        f"Inkomstbasbeloppet är det fastställda för året; år utan fastställt belopp räknas med det {ibb_note} – "
        "ingen uppräkning.",
        "Ingen avkastning, ränta eller avgift: volymen är summan av premier, inte kapital eller pension.",
        f"Baslinjen följer produktparametrarna som gäller varje månad enligt product_parameters "
        f"(för {data.key}: {parameters.label(current)}). Scenariot är samma parametrar med {label.removesuffix(' (scenario)')}.",
        "Premierna räknas med premiemotorn per person och månad (PR-ITP1-001, PR-ITP1-013). Inga premier, "
        "parametrar eller rättigheter ändras.",
        f"Belopp i hela tusental kronor. Celler med färre än {parameter_impact.MIN_CELL} individer döljs, och fler "
        "döljs vid behov så att en dold cell inte kan räknas fram ur totalen. Noll visas som noll; ej beräknat "
        "visas som ej beräknat.",
    ]
    return ParameterImpactEstimate(
        key=data.key, current_value=parameters.plain(current.value), current_version=parameters.label(current),
        value=parameters.plain(data.value), valid_from=data.valid_from, period_from=months[0], period_to=months[-1],
        active_persons=result.persons, excluded_persons=result.excluded, totals_status=result.totals_status,
        affected_persons_total=result.affected_total, extra_premium_months_total=result.extra_months_total,
        extra_premium_volume_total_sek=result.extra_volume_total, first_affected_year=result.first_affected_year,
        years=years, hidden_cells=[HiddenCell(cell=c, reason=r) for c, r in result.hidden_cells],
        min_cell_size=parameter_impact.MIN_CELL, assumptions=assumptions,
    )
