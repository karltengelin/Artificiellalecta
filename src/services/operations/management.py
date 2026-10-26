"""Ledningsaggregat i betrodd kod. Ingen individlista lämnar tjänstelagret."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func, select

from models import InsuredPerson, Policy, PolicyBenefit, PremiumTransaction
from services.contract import OperationContext, OperationKind, operation
from services.errors import InvalidInputError
from services.operations import common


class CompanyMetricsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    month: date

    @field_validator("month")
    @classmethod
    def first_of_month(cls, value):
        if value.day != 1:
            raise ValueError("Välj en hel kalendermånad")
        return value


class CompanyMetrics(BaseModel):
    read_at: datetime
    as_of_date: date
    period_from: date
    period_to: date
    insured_count: int | None
    insured_suppressed: bool
    paid_sek: Decimal | None
    paid_state: str


@operation(
    name="get_company_metrics",
    description="Läser ledningsaggregat: registrerade försäkrade och betalmarkerade premier per hel månad, med småcellsskydd.",
    kind=OperationKind.READ,
    pii=False,
)
def get_company_metrics(ctx: OperationContext, data: CompanyMetricsQuery) -> CompanyMetrics:
    today = common.today()
    this_month = today.replace(day=1)
    distance = (this_month.year - data.month.year) * 12 + this_month.month - data.month.month
    if not 0 <= distance <= 11:
        raise InvalidInputError("Välj aktuell månad eller någon av de elva föregående")
    end = date(data.month.year + (data.month.month == 12), data.month.month % 12 + 1, 1)
    paid = select(
        func.coalesce(func.sum(PremiumTransaction.amount_sek), 0).label("amount"),
        func.count(func.distinct(Policy.insured_person_id)).label("persons"),
    ).select_from(PremiumTransaction).join(PolicyBenefit).join(Policy).where(
        PremiumTransaction.status == "paid",
        PremiumTransaction.transaction_type.in_(("premium", "adjustment")),
        PremiumTransaction.paid_date >= data.month,
        PremiumTransaction.paid_date < end,
    ).subquery()
    invalid = select(func.count()).select_from(PremiumTransaction).where(
        PremiumTransaction.status == "paid",
        PremiumTransaction.transaction_type.in_(("premium", "adjustment")),
        (PremiumTransaction.paid_date.is_(None)) | (PremiumTransaction.paid_date > today),
    ).scalar_subquery()
    # Ett enda SELECT: samma databasögonblick för alla ingående aggregat.
    count, amount, people, bad = ctx.require_session().execute(select(
        select(func.count()).select_from(InsuredPerson).scalar_subquery(),
        paid.c.amount, paid.c.persons, invalid,
    )).one()
    suppressed = 0 < count < 10
    state = "failed" if bad else "suppressed" if suppressed or 0 < people < 10 else "available"
    return CompanyMetrics(
        read_at=datetime.now(UTC), as_of_date=today, period_from=data.month, period_to=end,
        insured_count=None if suppressed else count, insured_suppressed=suppressed,
        paid_sek=amount if state == "available" else None, paid_state=state,
    )
