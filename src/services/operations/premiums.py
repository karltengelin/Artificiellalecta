"""Läs- och beräkningsoperationer för premier (Fas 1f, T2)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from models import BaseAmount, Policy, PolicyBenefit, PremiumTransaction
from services.contract import OperationContext, OperationKind, operation
from services.errors import NotFoundError
from skills.calculation.calculate_itp1_premium import calculate_itp1_premium

ZERO = Decimal("0.00")


# --- premiehistorik -----------------------------------------------------------


class PremiumHistoryQuery(BaseModel):
    policy_number: str = Field(description="Försäkringsnummer, t.ex. AL-000123")
    from_month: date | None = Field(default=None, description="Första månad (inklusive), valfri")
    to_month: date | None = Field(default=None, description="Sista månad (inklusive), valfri")


class PremiumRow(BaseModel):
    period_month: date
    transaction_type: str
    benefit_type: str
    pensionable_salary_sek: Decimal | None
    amount_sek: Decimal
    status: str
    paid_date: date | None


class PremiumHistory(BaseModel):
    policy_number: str
    transactions: list[PremiumRow]
    count: int
    total_paid_sek: Decimal = Field(description="Summa betalda transaktioner i urvalet")


@operation(
    name="get_premium_history",
    description=(
        "Visar premietransaktioner för en försäkring månad för månad – typ, lön, belopp och "
        "betalstatus – med summan av betalda belopp. Valfritt urval på månader."
    ),
    kind=OperationKind.READ,
    pii=True,
)
def get_premium_history(ctx: OperationContext, data: PremiumHistoryQuery) -> PremiumHistory:
    session = ctx.require_session()
    policy = session.scalar(select(Policy).where(Policy.policy_number == data.policy_number))
    if policy is None:
        raise NotFoundError(f"Ingen försäkring med nummer {data.policy_number}")

    query = (
        select(PremiumTransaction, PolicyBenefit.benefit_type)
        .join(PolicyBenefit, PremiumTransaction.benefit_id == PolicyBenefit.id)
        .where(PolicyBenefit.policy_id == policy.id)
        .order_by(PremiumTransaction.period_month, PremiumTransaction.transaction_type)
    )
    if data.from_month is not None:
        query = query.where(PremiumTransaction.period_month >= data.from_month.replace(day=1))
    if data.to_month is not None:
        query = query.where(PremiumTransaction.period_month <= data.to_month.replace(day=1))

    rows = [
        PremiumRow(
            period_month=tx.period_month,
            transaction_type=tx.transaction_type,
            benefit_type=benefit_type,
            pensionable_salary_sek=tx.pensionable_salary_sek,
            amount_sek=tx.amount_sek,
            status=tx.status,
            paid_date=tx.paid_date,
        )
        for tx, benefit_type in session.execute(query).all()
    ]
    return PremiumHistory(
        policy_number=policy.policy_number,
        transactions=rows,
        count=len(rows),
        total_paid_sek=sum((r.amount_sek for r in rows if r.status == "paid"), ZERO).quantize(ZERO),
    )


# --- förhandsberäkning ------------------------------------------------------------


class PremiumPreviewInput(BaseModel):
    monthly_salary_sek: Decimal = Field(ge=0, description="Pensionsmedförande månadslön i kronor")
    period_month: date = Field(description="Premiemånaden – avgör vilket inkomstbasbelopp som gäller")
    birth_date: date | None = Field(
        default=None, description="Födelsedatum – om angivet kontrolleras åldersfönstret 25–66"
    )

    @field_validator("period_month")
    @classmethod
    def _first_of_month(cls, value: date) -> date:
        return value.replace(day=1)


class PremiumPreview(BaseModel):
    period_month: date
    income_base_amount_sek: Decimal
    total_premium_sek: Decimal
    amount_low_sek: Decimal = Field(description="4,5 %-delen upp till 7,5 IBB/12")
    amount_high_sek: Decimal = Field(description="30 %-delen mellan 7,5 och 30 IBB/12")
    in_age_window: bool | None = Field(description="None om åldersfönstret inte kontrollerades")
    calculation_basis: dict[str, Any]


@operation(
    name="calculate_premium_preview",
    description=(
        "Förhandsberäknar ITP1-premien för en månadslön en viss månad enligt premietrappan, "
        "med rätt inkomstbasbelopp för året. Sparar ingenting."
    ),
    kind=OperationKind.COMPUTE,
    rules=["PR-ITP1-001"],
)
def calculate_premium_preview(ctx: OperationContext, data: PremiumPreviewInput) -> PremiumPreview:
    session = ctx.require_session()
    base_amount = session.get(BaseAmount, data.period_month.year)
    if base_amount is None:
        raise NotFoundError(f"Inkomstbasbelopp saknas för {data.period_month.year} (tabellen base_amounts)")

    result = calculate_itp1_premium(
        data.monthly_salary_sek,
        base_amount.income_base_amount_sek,
        birth_date=data.birth_date,
        period_month=data.period_month if data.birth_date else None,
    )
    return PremiumPreview(
        period_month=data.period_month,
        income_base_amount_sek=base_amount.income_base_amount_sek,
        total_premium_sek=result.total_premium_sek,
        amount_low_sek=result.amount_low_sek,
        amount_high_sek=result.amount_high_sek,
        in_age_window=result.in_age_window,
        calculation_basis=result.calculation_basis,
    )
