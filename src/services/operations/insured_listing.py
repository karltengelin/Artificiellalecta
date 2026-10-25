"""Beståndslista för handläggare: en rad per försäkrad, filtrering och sidindelning."""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, or_, select

from models import Employer, InsuredPerson, Policy, PolicyState
from services.contract import OperationContext, OperationKind, operation
from services.operations.insured import EmployerInfo


class InsuredQuery(BaseModel):
    q: str = Field(default="", max_length=200, description="Namn, personnummer eller försäkringsnummer; även delar")
    employer_org_number: str | None = Field(default=None, pattern=r"^\d{10}$")
    policy_state: Literal["premium_paying", "paid_up", "in_payout", "payout_paused", "terminated", "no_policy"] | None = None
    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=25, ge=1, le=100)

    @field_validator("q", mode="before")
    @classmethod
    def _clean_query(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("employer_org_number", "policy_state", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        return value.strip() or None if isinstance(value, str) else value


class ListedPolicy(BaseModel):
    policy_number: str
    current_state: str | None


class InsuredRow(BaseModel):
    personal_id_number: str
    first_name: str
    last_name: str
    status: str
    employer: EmployerInfo
    policies: list[ListedPolicy]


class InsuredList(BaseModel):
    persons: list[InsuredRow]
    total: int = Field(description="Antal försäkrade som matchar urvalet, inte antal försäkringar")
    total_in_database: int
    page: int
    page_size: int
    page_count: int


def _fold_name(column):
    # SQLite lower() hanterar inte ÅÄÖ. Gör svensk namnsökning likvärdig med Postgres.
    return func.lower(func.replace(func.replace(func.replace(column, "Å", "å"), "Ä", "ä"), "Ö", "ö"))


@operation(
    name="list_insured_persons",
    description="Listar försäkrade med namnsökning, person-/försäkringsnummer, arbetsgivare, nuvarande försäkringsläge och sidindelning.",
    kind=OperationKind.READ,
    pii=True,
)
def list_insured_persons(ctx: OperationContext, data: InsuredQuery) -> InsuredList:
    session = ctx.require_session()
    query = select(InsuredPerson.id).join(Employer, Employer.id == InsuredPerson.employer_id)
    if data.q:
        names = and_(*[
            or_(_fold_name(InsuredPerson.first_name).contains(part, autoescape=True),
                _fold_name(InsuredPerson.last_name).contains(part, autoescape=True))
            for part in data.q.casefold().split()
        ])
        compact = re.sub(r"[\s-]", "", data.q)
        policy_number = "AL-" + compact[2:] if re.fullmatch(r"AL\d+", compact, re.IGNORECASE) else data.q.upper()
        policy_match = select(Policy.id).where(
            Policy.insured_person_id == InsuredPerson.id,
            Policy.policy_number.contains(policy_number, autoescape=True),
        ).exists()
        query = query.where(or_(
            names, and_(bool(compact), InsuredPerson.personal_id_number.contains(compact, autoescape=True)), policy_match,
        ))
    if data.employer_org_number:
        query = query.where(Employer.org_number == data.employer_org_number)
    if data.policy_state == "no_policy":
        query = query.where(~select(Policy.id).where(Policy.insured_person_id == InsuredPerson.id).exists())
    elif data.policy_state:
        query = query.where(select(Policy.id).join(PolicyState, PolicyState.policy_id == Policy.id).where(
            Policy.insured_person_id == InsuredPerson.id, PolicyState.valid_to.is_(None), PolicyState.state == data.policy_state,
        ).exists())

    total_in_database = session.scalar(select(func.count()).select_from(InsuredPerson))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    page_count = max(1, math.ceil(total / data.page_size))
    page = min(data.page, page_count)
    rows = session.execute(select(
        InsuredPerson.id, InsuredPerson.personal_id_number, InsuredPerson.first_name, InsuredPerson.last_name,
        InsuredPerson.status, Employer.org_number, Employer.name,
    ).join(Employer, Employer.id == InsuredPerson.employer_id).where(InsuredPerson.id.in_(query)).order_by(
        _fold_name(InsuredPerson.last_name), _fold_name(InsuredPerson.first_name), InsuredPerson.personal_id_number,
    ).offset((page - 1) * data.page_size).limit(data.page_size)).all()

    policies_by_person = {row.id: [] for row in rows}
    if rows:
        for person_id, number, state in session.execute(select(
            Policy.insured_person_id, Policy.policy_number, PolicyState.state,
        ).outerjoin(PolicyState, and_(PolicyState.policy_id == Policy.id, PolicyState.valid_to.is_(None))).where(
            Policy.insured_person_id.in_(policies_by_person),
        ).order_by(Policy.policy_number)):
            policies_by_person[person_id].append(ListedPolicy(policy_number=number, current_state=state))
    return InsuredList(
        persons=[InsuredRow(
            personal_id_number=row.personal_id_number, first_name=row.first_name, last_name=row.last_name, status=row.status,
            employer=EmployerInfo(org_number=row.org_number, name=row.name), policies=policies_by_person[row.id],
        ) for row in rows],
        total=total, total_in_database=total_in_database, page=page, page_size=data.page_size, page_count=page_count,
    )
