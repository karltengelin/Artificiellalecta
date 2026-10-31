"""Produktparametrar för premieberäkningen och kapitalavräkningen – uppslag per månad (Fas 3c, B-035; A5).

    params = premium_parameters(session, date(2027, 3, 1))
    calculate_itp1_premium(lön, ibb, birth_date=..., period_month=..., parameters=params)

Värdena står i tabellen `product_parameters` (databasschema §9h) som versioner med
giltighetsintervall. Saknas en parameter för månaden stoppas beräkningen – ingen tyst
reserv. Enda undantaget är en databas där tabellen ännu inte finns (Lakebase före
migrationen `migrate_product_parameters.py`): då används paketets värden, och
calculation_basis säger det.

Kapitalavgiften (PR-ITP1-022) och kundbelastningen för avkastningsskatt (PR-ITP1-023) slås upp
per månad med `capital_rates`. Skattebelastningen har en version per kalenderår som slutar
31 december, så ett år utan beslutad sats stoppar avräkningen (PR-023: inte föregående års sats
automatiskt). Här finns ingen reserv i koden.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import inspect, or_, select
from sqlalchemy.orm import Session

from models import ProductParameter
from services.errors import BlockedError, NotFoundError, ServiceError
from skills.calculation.calculate_itp1_premium import (
    DEFAULT_PARAMETERS,
    PremiumParameters,
)

#: Parameternyckel → fält i PremiumParameters
PREMIUM_FIELDS = {
    "premium_age_start": "age_start",
    "premium_age_end": "age_end",
    "premium_rate_low": "rate_low",
    "premium_rate_high": "rate_high",
    "premium_breakpoint_low_ibb": "breakpoint_low_ibb",
    "premium_breakpoint_high_ibb": "breakpoint_high_ibb",
}
AGE_FIELDS = ("age_start", "age_end")
#: Kapitalavräkningens parametrar (PR-ITP1-022/023), nominella årssatser
CAPITAL_KEYS = ("capital_fee_rate", "customer_tax_rate")
FALLBACK_LABEL = "PR-ITP1 v1.0 i koden – tabellen product_parameters saknas (kör migrationen)"


#: Startvärdena gäller från 2023-01-01 – samma som premiemotorns standard och premiehistoriken 2023–2026
DEFAULT_VALID_FROM = date(2023, 1, 1)
DEFAULT_RULE_VERSION = "1.0"
DEFAULT_DECISION = "B-035 startvärden"


@dataclass(frozen=True)
class DefaultParameter:
    key: str
    value: Decimal
    unit: str
    rule_id: str
    source_ref: str
    valid_from: date = DEFAULT_VALID_FROM
    valid_to: date | None = None


def _tax_year(year: int, rate: str) -> DefaultParameter:
    """Årets kundbelastning 15 % × max(SLR året före, 0,5 %) ur PARAMETERREGISTER.md, bara det året."""
    return DefaultParameter("customer_tax_rate", Decimal(rate), "rate", "PR-ITP1-023", "K-SKV-SLR",
                            date(year, 1, 1), date(year, 12, 31))


DEFAULTS = (
    DefaultParameter("premium_age_start", Decimal("25"), "years", "PR-ITP1-013", "K-ITP-AVTAL-2026"),
    DefaultParameter("premium_age_end", Decimal("66"), "years", "PR-ITP1-013", "K-ITP-FIL"),
    DefaultParameter("premium_rate_low", Decimal("0.045"), "rate", "PR-ITP1-001", "K-ITP-AVTAL-2026"),
    DefaultParameter("premium_rate_high", Decimal("0.30"), "rate", "PR-ITP1-001", "K-ITP-AVTAL-2026"),
    DefaultParameter("premium_breakpoint_low_ibb", Decimal("7.5"), "ibb", "PR-ITP1-001", "K-ITP-AVTAL-2026"),
    DefaultParameter("premium_breakpoint_high_ibb", Decimal("30"), "ibb", "PR-ITP1-001", "K-ITP-AVTAL-2026"),
    DefaultParameter("capital_fee_rate", Decimal("0.002"), "rate", "PR-ITP1-022", "B-021"),
    _tax_year(2023, "0.002190"),
    _tax_year(2024, "0.003720"),
    _tax_year(2025, "0.003225"),
    _tax_year(2026, "0.003540"),
)


def default_rows(created_by: str = "system:seed") -> list[ProductParameter]:
    """Startvärdena som rader – för migrationen och demo-/testdatabaserna."""
    return [
        ProductParameter(
            key=d.key, value=d.value, unit=d.unit, valid_from=d.valid_from, valid_to=d.valid_to,
            rule_id=d.rule_id, rule_version=DEFAULT_RULE_VERSION, source_ref=d.source_ref,
            decision_ref=DEFAULT_DECISION, status="valid", created_by=created_by,
        )
        for d in DEFAULTS
    ]


def add_missing_defaults(session: Session) -> int:
    """Lägger in de startvärden som saknas (nyckel och giltighetsdag). Antal tillagda."""
    existing = set(session.execute(select(ProductParameter.key, ProductParameter.valid_from)).all())
    rows = [r for r in default_rows() if (r.key, r.valid_from) not in existing]
    session.add_all(rows)
    return len(rows)


def plain(value) -> Decimal:
    """Utan databasens efternollor: 0.045000 → 0.045, 30.000000 → 30 (inte 3E+1)."""
    value = Decimal(value)
    return value.quantize(Decimal(1)) if value == value.to_integral_value() else value.normalize()


def label(row: ProductParameter) -> str:
    return f"{row.rule_id} v{row.rule_version} från {row.valid_from.isoformat()}"


def has_parameter_table(session: Session) -> bool:
    return inspect(session.connection()).has_table(ProductParameter.__tablename__)


def _valid_rows(session: Session, keys, first: date, last: date) -> list[ProductParameter]:
    """Giltiga (ej återkallade) versioner som överlappar dagarna first–last."""
    return list(session.scalars(
        select(ProductParameter).where(
            ProductParameter.key.in_(keys),
            ProductParameter.status == "valid",
            ProductParameter.valid_from <= last,
            or_(ProductParameter.valid_to.is_(None), ProductParameter.valid_to >= first),
        )
    ).all())


def _pick(rows, on: date) -> dict[str, ProductParameter]:
    """Versionen av varje parameter som gäller dagen `on` – två giltiga versioner stoppar."""
    found: dict[str, ProductParameter] = {}
    for row in rows:
        if row.valid_from > on or (row.valid_to is not None and row.valid_to < on):
            continue
        if row.key in found:
            raise BlockedError(
                f"Produktparametern {row.key} har två giltiga versioner {on:%Y-%m-%d} "
                f"({label(found[row.key])}, {label(row)}) – rättas manuellt"
            )
        found[row.key] = row
    return found


def versions_on(session: Session, on: date, keys=tuple(PREMIUM_FIELDS)) -> dict[str, ProductParameter]:
    """Den version av varje parameter som gäller dagen `on` (ej återkallad)."""
    return _pick(_valid_rows(session, keys, on, on), on)


def _build(found: dict[str, ProductParameter], month: date) -> PremiumParameters:
    missing = [key for key in PREMIUM_FIELDS if key not in found]
    if missing:
        raise NotFoundError(
            f"Produktparametrar saknas för {month:%Y-%m}: {', '.join(missing)} (tabellen product_parameters)"
        )
    values = {}
    for key, name in PREMIUM_FIELDS.items():
        value = plain(found[key].value)
        if name in AGE_FIELDS:
            if value != value.to_integral_value():
                raise BlockedError(f"Produktparametern {key} måste vara hela år, inte {value}")
            values[name] = int(value)
        else:
            values[name] = value
    return PremiumParameters(**values, versions={key: label(found[key]) for key in PREMIUM_FIELDS})


def premium_parameters(session: Session, period_month: date) -> PremiumParameters:
    """Premiemotorns parametrar för premiemånaden, med versionerna för calculation_basis."""
    month = period_month.replace(day=1)
    if not has_parameter_table(session):
        return PremiumParameters(versions={"källa": FALLBACK_LABEL})
    return _build(versions_on(session, month), month)


def capital_rates(session: Session, months) -> dict[date, tuple[Decimal, Decimal, str, str]]:
    """Kapitalavgift och skattebelastning (årssatser) per månad, med versionernas etiketter.

    En månad utan gällande version av någon av dem stoppar med NotFoundError.
    """
    months = sorted({m.replace(day=1) for m in months})
    if not months:
        return {}
    rows = _valid_rows(session, CAPITAL_KEYS, months[0], months[-1])
    rates = {}
    for month in months:
        found = _pick(rows, month)
        missing = [key for key in CAPITAL_KEYS if key not in found]
        if missing:
            raise NotFoundError(
                f"Produktparametrar saknas för {month:%Y-%m}: {', '.join(missing)} (tabellen product_parameters)"
            )
        fee, tax = (found[key] for key in CAPITAL_KEYS)
        rates[month] = (plain(fee.value), plain(tax.value), label(fee), label(tax))
    return rates


def monthly_premium_parameters(session: Session, months) -> dict[date, PremiumParameters | ServiceError]:
    """Parametrarna för en följd av premiemånader med en enda fråga (prognoser, 3c-B).

    Samma regler som premium_parameters, men en månad som inte går att slå upp får sitt
    fel som värde i stället för att stoppa hela följden – anroparen visar den som ej beräknad.
    """
    months = sorted({m.replace(day=1) for m in months})
    if not months:
        return {}
    if not has_parameter_table(session):
        fallback = PremiumParameters(versions={"källa": FALLBACK_LABEL})
        return {m: fallback for m in months}
    rows = _valid_rows(session, tuple(PREMIUM_FIELDS), months[0], months[-1])
    result: dict[date, PremiumParameters | ServiceError] = {}
    for month in months:
        try:
            result[month] = _build(_pick(rows, month), month)
        except ServiceError as exc:
            result[month] = exc
    return result


__all__ = [
    "DEFAULTS",
    "DEFAULT_PARAMETERS",
    "PREMIUM_FIELDS",
    "add_missing_defaults",
    "default_rows",
    "has_parameter_table",
    "label",
    "monthly_premium_parameters",
    "plain",
    "premium_parameters",
    "versions_on",
]
