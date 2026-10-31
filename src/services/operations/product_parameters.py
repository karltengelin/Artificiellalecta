"""Produktparametrarna: läsa, schemalägga och dra tillbaka versioner (Fas 3c, B-035, databasschema §9h).

- `get_product_parameters` (3c-P1) visar värdena en viss dag och alla versioner.
- `schedule_product_parameter_change` (3c-P2) lägger en ny version från en framtida
  månadsförsta och avslutar den föregående dagen före. Ingen retroaktivitet, ingen
  överlappning och bara en kommande version per parameter i taget.
- `withdraw_product_parameter_change` (3c-P2) drar tillbaka en version som inte börjat
  gälla och öppnar den föregående igen. Årets skattebelastning har ingen tillsvidareversion
  att öppna; året saknar då sats tills en ny läggs in.
- `schedule_customer_tax_rate` lägger in kundbelastningen för avkastningsskatt för ett
  kalenderår, räknad ur genomsnittlig SLR året före: s_y = 0,15 × max(SLR, 0,005)
  (PR-ITP1-023). Satsen gäller just det året. SLR publiceras först efter årsskiftet, så
  innevarande år får läggas in i efterhand; inget kan ha räknats på det, eftersom en
  saknad sats stoppar kapitalavräkningen. Kapitalavgiften (PR-ITP1-022) ändras inte här,
  eftersom en ändring kräver PR-ITP1-030:s ändrings- och informationsprövning.

Historiska premier räknas aldrig om (PR-ITP1-032); en ny version gäller bara premiemånader
från sin giltighetsdag. Varje ändring loggas i händelseloggen med aktör och motivering.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, inspect, select

from models import ProductParameter, ValuationExtractRecord
from models.product_parameter import PARAMETER_UNITS
from services import parameters
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, ConflictError, NotFoundError
from services.operations import common

ParameterKey = Literal[
    "premium_age_start", "premium_age_end", "premium_rate_low", "premium_rate_high",
    "premium_breakpoint_low_ibb", "premium_breakpoint_high_ibb",
]
#: Produktregeln som bär respektive parameter
RULE_OF = {d.key: d.rule_id for d in parameters.DEFAULTS}
#: Rimliga gränser för premieålder – fångar skrivfel, inte produktbeslut
AGE_RANGE = (16, 80)
#: Kundbelastningen för avkastningsskatt (PR-ITP1-023): skattesats × max(SLR året före, golv)
TAX_KEY = "customer_tax_rate"
TAX_SHARE = Decimal("0.15")
SLR_FLOOR = Decimal("0.005")
#: Samma skala som kolumnen product_parameters.value
TAX_PRECISION = Decimal("0.000001")


class ProductParametersQuery(BaseModel):
    on_date: date | None = Field(
        default=None, description="Dagen som gällande värden visas för; standard är i dag"
    )


class ParameterVersion(BaseModel):
    key: str
    value: Decimal
    unit: str = Field(description="years, rate eller ibb")
    valid_from: date
    valid_to: date | None
    state: str = Field(description="gällande, kommande, upphörd eller återkallad – i förhållande till on_date")
    rule_id: str
    rule_version: str
    source_ref: str
    decision_ref: str


class ProductParameters(BaseModel):
    on_date: date
    table_present: bool = Field(description="False om tabellen saknas – då gäller paketets värden i koden")
    effective: dict[str, Decimal] = Field(description="Värdet per parameter som gäller on_date")
    versions: list[ParameterVersion]


def _state(row: ProductParameter, on: date) -> str:
    if row.status == "withdrawn":
        return "återkallad"
    if row.valid_from > on:
        return "kommande"
    if row.valid_to is not None and row.valid_to < on:
        return "upphörd"
    return "gällande"


@operation(
    name="get_product_parameters",
    description=(
        "Visar produktparametrarna – premieålder, premiesatser och brytpunkter samt kapitalavgift och "
        "skattebelastning per år – med de värden som gäller en viss dag och alla versioner med giltighet, "
        "produktregel, källa och beslut."
    ),
    kind=OperationKind.READ,
)
def get_product_parameters(ctx: OperationContext, data: ProductParametersQuery) -> ProductParameters:
    session = ctx.require_session()
    on = data.on_date or common.today()
    if not parameters.has_parameter_table(session):
        defaults = {d.key: d.value for d in parameters.DEFAULTS if d.key in parameters.PREMIUM_FIELDS}
        return ProductParameters(on_date=on, table_present=False, effective=defaults, versions=[])

    rows = session.scalars(select(ProductParameter).order_by(ProductParameter.key, ProductParameter.valid_from)).all()
    versions = [
        ParameterVersion(
            key=r.key, value=parameters.plain(r.value), unit=r.unit, valid_from=r.valid_from, valid_to=r.valid_to,
            state=_state(r, on), rule_id=r.rule_id, rule_version=r.rule_version,
            source_ref=r.source_ref, decision_ref=r.decision_ref,
        )
        for r in rows
    ]
    found = parameters.versions_on(session, on, keys=tuple(PARAMETER_UNITS))
    effective = {key: parameters.plain(row.value) for key, row in sorted(found.items())}
    return ProductParameters(on_date=on, table_present=True, effective=effective, versions=versions)


# --- schemalägga en ny version -----------------------------------------------------------------


class ParameterChangeInput(BaseModel):
    key: ParameterKey = Field(description="Parametern som ändras")
    value: Decimal = Field(
        ge=0, description="Nytt värde i parameterns enhet: hela år, andel (0,045 = 4,5 %) eller antal IBB"
    )
    valid_from: date = Field(description="Första premiemånad som omfattas – en månadsförsta, tidigast nästa månad")
    rule_version: str = Field(pattern=r"^\d+\.\d+$", description="Produktregelns nya version, t.ex. 1.1")
    source_ref: str = Field(min_length=1, max_length=60, description="Källan i källregistret, t.ex. K-SIM-ITP-2027")
    decision_ref: str = Field(min_length=1, max_length=60, description="Beslutet: B-nummer eller flödets grindbeslut")

    @field_validator("valid_from")
    @classmethod
    def _first_of_month(cls, value: date) -> date:
        if value.day != 1:
            raise ValueError("Giltighetsdagen måste vara den första i månaden")
        return value


class ParameterChange(BaseModel):
    key: str
    value: Decimal
    unit: str
    valid_from: date
    rule_id: str
    rule_version: str
    source_ref: str
    decision_ref: str
    previous_value: Decimal | None = Field(description="Värdet i versionen som avslutas eller öppnas igen")
    previous_valid_from: date | None
    previous_valid_to: date | None = Field(description="Den föregående versionens slutdag efter ändringen (None = tills vidare)")


def first_of_next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def _locked_versions(session, key: str) -> list[ProductParameter]:
    """Alla versioner av parametern i giltighetsordning, låsta under transaktionen (radlås i Postgres)."""
    return list(session.scalars(
        select(ProductParameter).where(ProductParameter.key == key)
        .order_by(ProductParameter.valid_from).with_for_update()
    ).all())


def check_parameter_value(session, key: str, value: Decimal, valid_from: date) -> None:
    """Värdet i parameterns enhet och samstämmigheten med övriga parametrar dagen ändringen börjar gälla.

    Används av schemaläggningen och av konsekvensberäkningen (portfolio_impact) – samma gränser.
    """
    unit = PARAMETER_UNITS[key]
    if unit == "years":
        if value != value.to_integral_value() or not AGE_RANGE[0] <= value <= AGE_RANGE[1]:
            raise BlockedError(f"En premieålder anges i hela år mellan {AGE_RANGE[0]} och {AGE_RANGE[1]}, inte {value}")
    elif unit == "rate":
        if not 0 < value < 1:
            raise BlockedError(f"En premiesats anges som andel mellan 0 och 1 (0,045 = 4,5 %), inte {value}")
    elif value <= 0:
        raise BlockedError(f"En brytpunkt anges som ett positivt antal IBB, inte {value}")

    # Parametrarna ska hänga ihop den dag ändringen börjar gälla
    current = {k: parameters.plain(r.value) for k, r in parameters.versions_on(session, valid_from).items()}
    current[key] = value
    pairs = (("premium_age_start", "premium_age_end", "premieåldern"),
             ("premium_breakpoint_low_ibb", "premium_breakpoint_high_ibb", "brytpunkterna"))
    for low, high, what in pairs:
        if low in current and high in current and not current[low] < current[high]:
            raise BlockedError(
                f"Efter ändringen hänger {what} inte ihop: {low} {current[low]} ska vara mindre än {high} {current[high]}"
            )


@operation(
    name="schedule_product_parameter_change",
    description=(
        "Schemalägger en ny version av en produktparameter för premieberäkningen – premieålder, premiesats "
        "eller brytpunkt – från en framtida månadsförsta, med produktregelns version, källa och beslut. "
        "Föregående version avslutas dagen före. Historiska premier ändras inte."
    ),
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-001", "PR-ITP1-013", "PR-ITP1-032"],
)
def schedule_product_parameter_change(ctx: OperationContext, data: ParameterChangeInput) -> ParameterChange:
    session = ctx.require_session()
    earliest = first_of_next_month(common.today())
    if data.valid_from < earliest:
        raise BlockedError(
            f"Giltighetsdagen {data.valid_from} är passerad eller i innevarande månad – tidigast {earliest}. "
            "Parametrar ändras aldrig retroaktivt (PR-ITP1-032)"
        )

    versions = _locked_versions(session, data.key)
    same_day = [v for v in versions if v.valid_from == data.valid_from]
    if same_day:
        state = "en återkallad" if same_day[0].status == "withdrawn" else "en"
        raise ConflictError(
            f"Det finns redan {state} version av {data.key} från {data.valid_from} – välj en annan giltighetsdag"
        )
    later = [v for v in versions if v.status == "valid" and v.valid_from > data.valid_from]
    if later:
        raise ConflictError(
            f"Det finns en senare version av {data.key} från {later[0].valid_from} – dra tillbaka den först"
        )
    previous = next((v for v in reversed(versions) if v.status == "valid" and v.valid_from < data.valid_from), None)
    if previous is None:
        raise NotFoundError(f"Ingen version av {data.key} gäller före {data.valid_from} att ersätta")
    if previous.valid_to is not None:
        raise ConflictError(
            f"Versionen av {data.key} från {previous.valid_from} är redan avslutad {previous.valid_to} – rättas manuellt"
        )
    if parameters.plain(previous.value) == parameters.plain(data.value):
        raise ConflictError(f"{data.key} är redan {parameters.plain(data.value)} – ingen ändring")
    check_parameter_value(session, data.key, data.value, data.valid_from)

    previous.valid_to = data.valid_from - timedelta(days=1)
    row = ProductParameter(
        key=data.key, value=data.value, unit=PARAMETER_UNITS[data.key], valid_from=data.valid_from, valid_to=None,
        rule_id=RULE_OF[data.key], rule_version=data.rule_version, source_ref=data.source_ref,
        decision_ref=data.decision_ref, status="valid", created_by=ctx.actor.id,
    )
    session.add(row)
    session.flush()
    return ParameterChange(
        key=row.key, value=parameters.plain(row.value), unit=row.unit, valid_from=row.valid_from,
        rule_id=row.rule_id, rule_version=row.rule_version, source_ref=row.source_ref,
        decision_ref=row.decision_ref, previous_value=parameters.plain(previous.value),
        previous_valid_from=previous.valid_from, previous_valid_to=previous.valid_to,
    )


# --- skattebelastningen för ett år ---------------------------------------------------------------


def customer_tax_rate(slr_previous_year: Decimal) -> Decimal:
    """s_y = 0,15 × max(genomsnittlig SLR året före, 0,005), i kolumnens skala (PR-ITP1-023)."""
    return (TAX_SHARE * max(slr_previous_year, SLR_FLOOR)).quantize(TAX_PRECISION)


class TaxRateInput(BaseModel):
    year: int = Field(ge=2023, le=2100, description="Kalenderåret satsen gäller")
    slr_previous_year: Decimal = Field(
        ge=Decimal("-0.05"), le=Decimal("0.2"),
        description="Genomsnittlig statslåneränta under året före, som andel (0,0236 = 2,36 %)",
    )
    rule_version: str = Field(pattern=r"^\d+\.\d+$", description="Produktregelns version, t.ex. 1.0")
    source_ref: str = Field(min_length=1, max_length=60, description="Källan, t.ex. K-SKV-SLR med Skatteverkets meddelande")
    decision_ref: str = Field(min_length=1, max_length=60, description="Beslutet: B-nummer eller grindbeslut")


def _extracts_from(session, day: date) -> int:
    """Antal sparade datautdrag per datum från `day` (A6) – de kan ha räknat på satsen."""
    if not inspect(session.connection()).has_table(ValuationExtractRecord.__tablename__):
        return 0
    return session.scalar(select(func.count()).select_from(ValuationExtractRecord)
                          .where(ValuationExtractRecord.valuation_date >= day))


@operation(
    name="schedule_customer_tax_rate",
    description=(
        "Lägger in kundbelastningen för avkastningsskatt för ett kalenderår, räknad ur genomsnittlig "
        "statslåneränta året före: 15 % × max(SLR, 0,5 %). Satsen gäller bara det året. Innevarande eller "
        "nästa år; föregående år ska ha en sats. Inga premier påverkas."
    ),
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-023", "PR-ITP1-032"],
)
def schedule_customer_tax_rate(ctx: OperationContext, data: TaxRateInput) -> ParameterChange:
    session = ctx.require_session()
    today = common.today()
    if data.year not in (today.year, today.year + 1):
        raise BlockedError(
            f"Satsen för {data.year} kan inte läggas in {today}: bara innevarande år ({today.year}) eller nästa "
            f"({today.year + 1}). Tidigare år ändras inte i efterhand (PR-ITP1-032)"
        )
    first, last = date(data.year, 1, 1), date(data.year, 12, 31)
    versions = _locked_versions(session, TAX_KEY)
    same_day = next((v for v in versions if v.valid_from == first), None)
    if same_day is not None:
        state = "en återkallad sats" if same_day.status == "withdrawn" else "redan en sats"
        raise ConflictError(f"Det finns {state} för {data.year} – rättas manuellt")
    if any(v.status == "valid" and v.valid_from <= last and (v.valid_to is None or v.valid_to >= first)
           for v in versions):
        raise ConflictError(f"En giltig sats överlappar {data.year} – rättas manuellt")
    previous = next((v for v in versions if v.status == "valid" and v.valid_to == first - timedelta(days=1)), None)
    if previous is None:
        raise BlockedError(f"Satsen för {data.year - 1} saknas – lägg in åren i ordning, utan glapp")
    if data.year == today.year and _extracts_from(session, first):
        raise BlockedError(f"Det finns sparade datautdrag från {first} – en sats i efterhand rättas manuellt")

    row = ProductParameter(
        key=TAX_KEY, value=customer_tax_rate(data.slr_previous_year), unit=PARAMETER_UNITS[TAX_KEY],
        valid_from=first, valid_to=last, rule_id=RULE_OF[TAX_KEY], rule_version=data.rule_version,
        source_ref=data.source_ref, decision_ref=data.decision_ref, status="valid", created_by=ctx.actor.id,
    )
    session.add(row)
    session.flush()
    return ParameterChange(
        key=row.key, value=parameters.plain(row.value), unit=row.unit, valid_from=row.valid_from,
        rule_id=row.rule_id, rule_version=row.rule_version, source_ref=row.source_ref,
        decision_ref=row.decision_ref, previous_value=parameters.plain(previous.value),
        previous_valid_from=previous.valid_from, previous_valid_to=previous.valid_to,
    )


# --- dra tillbaka en kommande version ----------------------------------------------------------

WithdrawKey = Literal[
    "premium_age_start", "premium_age_end", "premium_rate_low", "premium_rate_high",
    "premium_breakpoint_low_ibb", "premium_breakpoint_high_ibb", "customer_tax_rate",
]


class ParameterWithdrawInput(BaseModel):
    key: WithdrawKey = Field(description="Parametern")
    valid_from: date = Field(description="Giltighetsdagen för versionen som dras tillbaka")


@operation(
    name="withdraw_product_parameter_change",
    description=(
        "Drar tillbaka en schemalagd version av en produktparameter som ännu inte börjat gälla. "
        "Föregående version gäller då vidare tills vidare."
    ),
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-032"],
)
def withdraw_product_parameter_change(ctx: OperationContext, data: ParameterWithdrawInput) -> ParameterChange:
    session = ctx.require_session()
    versions = _locked_versions(session, data.key)
    row = next((v for v in versions if v.valid_from == data.valid_from and v.status == "valid"), None)
    if row is None:
        raise NotFoundError(f"Ingen giltig version av {data.key} från {data.valid_from}")
    if row.valid_from <= common.today():
        raise BlockedError(
            f"Versionen av {data.key} från {row.valid_from} har redan börjat gälla – schemalägg i stället en ny version"
        )
    if any(v.status == "valid" and v.valid_from > row.valid_from for v in versions):
        raise ConflictError(f"Det finns en senare version av {data.key} – dra tillbaka den först")
    day_before = row.valid_from - timedelta(days=1)
    previous = next((v for v in versions if v.status == "valid" and v.valid_to == day_before), None)
    row.status = "withdrawn"
    if previous is not None and data.key != TAX_KEY:  # årets sats har ingen tillsvidareversion att öppna
        previous.valid_to = None
    session.flush()
    return ParameterChange(
        key=row.key, value=parameters.plain(row.value), unit=row.unit, valid_from=row.valid_from,
        rule_id=row.rule_id, rule_version=row.rule_version, source_ref=row.source_ref,
        decision_ref=row.decision_ref,
        previous_value=parameters.plain(previous.value) if previous else None,
        previous_valid_from=previous.valid_from if previous else None,
        previous_valid_to=previous.valid_to if previous else None,
    )
