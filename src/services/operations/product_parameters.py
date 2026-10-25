"""Produktparametrarna: läsa, schemalägga och dra tillbaka versioner (Fas 3c, B-035, databasschema §9h).

- `get_product_parameters` (3c-P1) visar värdena en viss dag och alla versioner.
- `schedule_product_parameter_change` (3c-P2) lägger en ny version från en framtida
  månadsförsta och avslutar den föregående dagen före. Ingen retroaktivitet, ingen
  överlappning och bara en kommande version per parameter i taget.
- `withdraw_product_parameter_change` (3c-P2) drar tillbaka en version som inte börjat
  gälla och öppnar den föregående igen.

Historiska premier räknas aldrig om (PR-ITP1-032); en ny version gäller bara premiemånader
från sin giltighetsdag. Varje ändring loggas i händelseloggen med aktör och motivering.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from models import ProductParameter
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
        "Visar produktparametrarna för premieberäkningen – premieålder, premiesatser och brytpunkter – "
        "med de värden som gäller en viss dag och alla versioner med giltighet, produktregel, källa och beslut."
    ),
    kind=OperationKind.READ,
)
def get_product_parameters(ctx: OperationContext, data: ProductParametersQuery) -> ProductParameters:
    session = ctx.require_session()
    on = data.on_date or common.today()
    if not parameters.has_parameter_table(session):
        defaults = {d.key: d.value for d in parameters.DEFAULTS}
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
    effective = {key: parameters.plain(row.value) for key, row in sorted(parameters.versions_on(session, on).items())}
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


def _first_of_next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def _locked_versions(session, key: str) -> list[ProductParameter]:
    """Alla versioner av parametern i giltighetsordning, låsta under transaktionen (radlås i Postgres)."""
    return list(session.scalars(
        select(ProductParameter).where(ProductParameter.key == key)
        .order_by(ProductParameter.valid_from).with_for_update()
    ).all())


def _check_value(session, data: ParameterChangeInput) -> None:
    unit = PARAMETER_UNITS[data.key]
    value = data.value
    if unit == "years":
        if value != value.to_integral_value() or not AGE_RANGE[0] <= value <= AGE_RANGE[1]:
            raise BlockedError(f"En premieålder anges i hela år mellan {AGE_RANGE[0]} och {AGE_RANGE[1]}, inte {value}")
    elif unit == "rate":
        if not 0 < value < 1:
            raise BlockedError(f"En premiesats anges som andel mellan 0 och 1 (0,045 = 4,5 %), inte {value}")
    elif value <= 0:
        raise BlockedError(f"En brytpunkt anges som ett positivt antal IBB, inte {value}")

    # Parametrarna ska hänga ihop den dag ändringen börjar gälla
    current = {k: parameters.plain(r.value) for k, r in parameters.versions_on(session, data.valid_from).items()}
    current[data.key] = value
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
    earliest = _first_of_next_month(common.today())
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
    _check_value(session, data)

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


# --- dra tillbaka en kommande version ----------------------------------------------------------


class ParameterWithdrawInput(BaseModel):
    key: ParameterKey = Field(description="Parametern")
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
    if previous is not None:
        previous.valid_to = None
    session.flush()
    return ParameterChange(
        key=row.key, value=parameters.plain(row.value), unit=row.unit, valid_from=row.valid_from,
        rule_id=row.rule_id, rule_version=row.rule_version, source_ref=row.source_ref,
        decision_ref=row.decision_ref,
        previous_value=parameters.plain(previous.value) if previous else None,
        previous_valid_from=previous.valid_from if previous else None,
        previous_valid_to=None,
    )
