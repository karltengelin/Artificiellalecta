"""Läsoperation för produktparametrarna (Fas 3c 3c-P1, B-035, databasschema §9h).

Visar vilka värden premieberäkningen använder en viss dag och alla versioner med
giltighet, produktregel, källa och beslut – även kommande och återkallade.
Ändringar görs med operationerna i 3c-P2.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select

from models import ProductParameter
from services import parameters
from services.contract import OperationContext, OperationKind, operation
from services.operations import common


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
