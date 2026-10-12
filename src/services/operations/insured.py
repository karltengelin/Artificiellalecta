"""Läsoperationer för försäkrade (Fas 1f, T2)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select

from models import Employer, InsuredPerson, Policy, PolicyState, PremiumTransaction
from services.contract import OperationContext, OperationKind, operation
from services.errors import NotFoundError

ZERO = Decimal("0.00")


class InsuredLookup(BaseModel):
    """Ange exakt ett av fälten."""

    personal_id_number: str | None = Field(
        default=None, description="Personnummer med 12 siffror (ÅÅÅÅMMDDNNNN)"
    )
    policy_number: str | None = Field(
        default=None, description="Försäkringsnummer, t.ex. AL-000123"
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> InsuredLookup:
        if (self.personal_id_number is None) == (self.policy_number is None):
            raise ValueError("Ange antingen personnummer eller försäkringsnummer")
        return self


class EmployerInfo(BaseModel):
    org_number: str
    name: str


class StateInfo(BaseModel):
    state: str
    valid_from: date


class BenefitSummary(BaseModel):
    benefit_type: str
    start_date: date
    end_date: date | None
    capital_sek: Decimal = Field(description="Summa betalda transaktioner (databasschema §8)")


class PolicySummary(BaseModel):
    policy_number: str
    product_code: str
    signed_date: date
    start_date: date
    current_state: StateInfo | None = Field(description="Pågående läge (öppen rad), om något")
    benefits: list[BenefitSummary]
    capital_sek: Decimal


class InsuredOverview(BaseModel):
    insured_person_id: str
    personal_id_number: str
    first_name: str
    last_name: str
    email: str | None = Field(default=None, description="Kontaktuppgift")
    phone: str | None = Field(default=None, description="Kontaktuppgift")
    status: str
    employer: EmployerInfo
    employment_start_date: date
    employment_end_date: date | None
    monthly_salary_sek: Decimal | None
    employment_rate: Decimal | None
    itp1_start_date: date | None
    policies: list[PolicySummary]
    total_capital_sek: Decimal


@operation(
    name="get_insured_overview",
    description=(
        "Visar en försäkrad med kontaktuppgifter, anställning, lön, försäkringar, pågående läge per "
        "försäkring och kapital per förmån. Sök på personnummer eller försäkringsnummer."
    ),
    kind=OperationKind.READ,
    pii=True,
)
def get_insured_overview(ctx: OperationContext, data: InsuredLookup) -> InsuredOverview:
    session = ctx.require_session()

    if data.personal_id_number is not None:
        person = session.scalar(
            select(InsuredPerson).where(InsuredPerson.personal_id_number == data.personal_id_number)
        )
        if person is None:
            raise NotFoundError("Ingen försäkrad med det personnumret")
    else:
        policy = session.scalar(select(Policy).where(Policy.policy_number == data.policy_number))
        if policy is None:
            raise NotFoundError(f"Ingen försäkring med nummer {data.policy_number}")
        person = policy.insured_person

    employer = session.get(Employer, person.employer_id)
    policies = session.scalars(
        select(Policy).where(Policy.insured_person_id == person.id).order_by(Policy.start_date)
    ).all()
    capital = _capital_per_benefit(session, [b.id for p in policies for b in p.benefits])

    summaries = []
    for policy in policies:
        benefits = [
            BenefitSummary(
                benefit_type=b.benefit_type,
                start_date=b.start_date,
                end_date=b.end_date,
                capital_sek=capital.get(b.id, ZERO),
            )
            for b in sorted(policy.benefits, key=lambda b: b.start_date)
        ]
        open_state = session.scalar(
            select(PolicyState).where(
                PolicyState.policy_id == policy.id, PolicyState.valid_to.is_(None)
            )
        )
        summaries.append(
            PolicySummary(
                policy_number=policy.policy_number,
                product_code=policy.product_code,
                signed_date=policy.signed_date,
                start_date=policy.start_date,
                current_state=(
                    StateInfo(state=open_state.state, valid_from=open_state.valid_from)
                    if open_state
                    else None
                ),
                benefits=benefits,
                capital_sek=sum((b.capital_sek for b in benefits), ZERO),
            )
        )

    return InsuredOverview(
        insured_person_id=str(person.id),
        personal_id_number=person.personal_id_number,
        first_name=person.first_name,
        last_name=person.last_name,
        email=person.email,
        phone=person.phone,
        status=person.status,
        employer=EmployerInfo(org_number=employer.org_number, name=employer.name),
        employment_start_date=person.employment_start_date,
        employment_end_date=person.employment_end_date,
        monthly_salary_sek=person.monthly_salary_sek,
        employment_rate=person.employment_rate,
        itp1_start_date=person.itp1_start_date,
        policies=summaries,
        total_capital_sek=sum((p.capital_sek for p in summaries), ZERO),
    )


def _capital_per_benefit(session, benefit_ids: list) -> dict:
    """Förmånens kapital = SUM(amount_sek) WHERE status = 'paid' (databasschema §8)."""
    if not benefit_ids:
        return {}
    rows = session.execute(
        select(PremiumTransaction.benefit_id, func.sum(PremiumTransaction.amount_sek))
        .where(
            PremiumTransaction.benefit_id.in_(benefit_ids),
            PremiumTransaction.status == "paid",
        )
        .group_by(PremiumTransaction.benefit_id)
    ).all()
    return {benefit_id: Decimal(total).quantize(ZERO) for benefit_id, total in rows}
