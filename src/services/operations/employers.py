"""Arbetsgivare (försäkringstagare): registrera och lista (Fas 4 S5, PR-ITP1-012).

Arbetsgivaren är försäkringstagare (PR-ITP1-012); en ny arbetsgivare är ett
nytt avtal och därför ett mänskligt beslut (HUMAN_ONLY i registret).
Kollektivavtalet är alltid ITP (B-002). Kontaktpersonen är en personuppgift.
Status, organisationsnummer och anslutningsdag ändras inte här – en
arbetsgivares avslut berör alla dess försäkrade och är ett eget flöde.

Listan visar inte kontaktpersoner och loggas därför inte som läsning av
personuppgifter. Den används bland annat när en ny anställd ansluts.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, select

from models import Employer, InsuredPerson
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, ConflictError
from services.operations import common
from services.operations.enrollment import EMAIL_PATTERN, PHONE_PATTERN


class EmployerInput(BaseModel):
    org_number: str = Field(pattern=r"^\d{10}$", description="Organisationsnummer, 10 siffror utan bindestreck")
    name: str = Field(min_length=1, max_length=255)
    affiliation_date: date = Field(description="Dagen arbetsgivaren anslöt till ITP")
    industry_code: str | None = Field(default=None, pattern=r"^\d{5}$", description="SNI-kod, 5 siffror")
    address_street: str | None = Field(default=None, max_length=255)
    address_postal_code: str | None = Field(default=None, pattern=r"^\d{5}$", description="Postnummer, 5 siffror")
    address_city: str | None = Field(default=None, max_length=100)
    contact_name: str | None = Field(default=None, max_length=255, description="Kontaktperson (HR/lön)")
    contact_email: str | None = Field(default=None, max_length=255, pattern=EMAIL_PATTERN)
    contact_phone: str | None = Field(default=None, max_length=30, pattern=PHONE_PATTERN)

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("address_postal_code", mode="before")
    @classmethod
    def _postal_code(cls, value):
        return value.replace(" ", "") if isinstance(value, str) else value

    @field_validator("org_number")
    @classmethod
    def _valid_org(cls, value: str) -> str:
        if not common.valid_org_number(value):
            raise ValueError("Organisationsnumret är inte giltigt (kontrollsiffra)")
        return value


class EmployerResult(BaseModel):
    org_number: str
    name: str
    affiliation_date: date
    collective_agreement: str
    status: str


@operation(
    name="register_employer",
    description=(
        "Registrerar en ny arbetsgivare (försäkringstagare, PR-ITP1-012) med ITP som kollektivavtal, "
        "anslutningsdag, adress och kontaktperson."
    ),
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-012"],
    pii=True,
)
def register_employer(ctx: OperationContext, data: EmployerInput) -> EmployerResult:
    session = ctx.require_session()
    if data.affiliation_date > common.today():
        raise BlockedError(f"Anslutningsdagen {data.affiliation_date} ligger i framtiden – registrera när avtalet gäller")
    existing = session.scalar(select(Employer).where(Employer.org_number == data.org_number))
    if existing is not None:
        raise ConflictError(f"Arbetsgivaren {data.org_number} finns redan ({existing.name})")
    employer = Employer(**data.model_dump(), collective_agreement="ITP", status="active")
    session.add(employer)
    session.flush()
    return EmployerResult(
        org_number=employer.org_number, name=employer.name, affiliation_date=employer.affiliation_date,
        collective_agreement=employer.collective_agreement, status=employer.status,
    )


class EmployerQuery(BaseModel):
    status: Literal["active", "terminated", "paused"] | None = Field(
        default="active", description="Urval på status; None = alla"
    )


class EmployerRow(BaseModel):
    org_number: str
    name: str
    status: str
    collective_agreement: str
    affiliation_date: date
    active_insured: int = Field(description="Antal försäkrade med status aktiv")


class EmployerList(BaseModel):
    employers: list[EmployerRow]
    count: int


@operation(
    name="list_employers",
    description=(
        "Listar arbetsgivare med organisationsnummer, namn, status, anslutningsdag och antal aktiva "
        "försäkrade. Inga kontaktpersoner."
    ),
    kind=OperationKind.READ,
)
def list_employers(ctx: OperationContext, data: EmployerQuery) -> EmployerList:
    session = ctx.require_session()
    active = func.count(InsuredPerson.id)
    query = (
        select(Employer, active)
        .outerjoin(InsuredPerson, and_(InsuredPerson.employer_id == Employer.id, InsuredPerson.status == "active"))
        .group_by(Employer.id)
        .order_by(Employer.name)
    )
    if data.status is not None:
        query = query.where(Employer.status == data.status)
    rows = [
        EmployerRow(
            org_number=e.org_number, name=e.name, status=e.status, collective_agreement=e.collective_agreement,
            affiliation_date=e.affiliation_date, active_insured=count,
        )
        for e, count in session.execute(query).all()
    ]
    return EmployerList(employers=rows, count=len(rows))
