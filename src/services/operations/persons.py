"""Stamdata på den försäkrade: aktuell lön och kontaktuppgifter (Fas 4 S5).

**Aktuell lön** (`monthly_salary_sek`, `employment_rate`) är avtalad månadslön
enligt arbetsgivaren – stamdata som visas i översikten. Den är inte
pensionsmedförande lön: PR-ITP1-014 tillåter inte att avtalad lön ersätter
faktiskt utbetald lön, så ändringen skapar varken löneunderlag eller premie
(det görs med register_salary_report). Ingen produktregel styr aktuell lön –
regelgolvet (*write utan regel*) håller operationen HUMAN_ONLY för agenter.
Modellen har bara aktuellt värde; tidigare värde står i händelseloggen.

**Kontaktuppgifter** (`email`, `phone`): båda anges som de ska vara efter
ändringen, tomt tar bort uppgiften. Rätt person ska vara verifierad
(PR-ITP1-031) – motiveringen anger hur. Namn och personnummer är
identitetsuppgifter och ändras inte här.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, ConflictError
from services.operations import common
from services.operations.enrollment import EMAIL_PATTERN, PHONE_PATTERN

# --- aktuell lön --------------------------------------------------------------------------------


class CurrentSalaryInput(BaseModel):
    personal_id_number: str = Field(pattern=r"^\d{12}$", description="Den försäkrades personnummer, 12 siffror")
    monthly_salary_sek: Decimal = Field(
        ge=0, max_digits=10, decimal_places=2, description="Aktuell (avtalad) månadslön i kronor"
    )
    employment_rate: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2,
        description="Tjänstgöringsgrad i procent; utelämnad = oförändrad",
    )


class CurrentSalaryResult(BaseModel):
    personal_id_number: str
    previous_salary_sek: Decimal | None
    monthly_salary_sek: Decimal
    previous_employment_rate: Decimal | None
    employment_rate: Decimal | None
    note: str


@operation(
    name="update_current_salary",
    description=(
        "Ändrar aktuell månadslön och tjänstgöringsgrad på den försäkrade (stamdata). Skapar varken "
        "löneunderlag eller premie – pensionsmedförande lön registreras med register_salary_report (PR-ITP1-014)."
    ),
    kind=OperationKind.WRITE,
    pii=True,
)
def update_current_salary(ctx: OperationContext, data: CurrentSalaryInput) -> CurrentSalaryResult:
    session = ctx.require_session()
    person = common.lock_person(session, data.personal_id_number)
    if person.status != "active" or person.employment_end_date is not None:
        raise BlockedError(
            f"Den försäkrade har status {person.status}"
            + (f" och anställningen slutade {person.employment_end_date}" if person.employment_end_date else "")
            + " – aktuell lön ändras bara under pågående anställning"
        )
    previous_salary, previous_rate = person.monthly_salary_sek, person.employment_rate
    new_rate = data.employment_rate if data.employment_rate is not None else previous_rate
    if _same(previous_salary, data.monthly_salary_sek) and _same(previous_rate, new_rate):
        raise ConflictError("Lön och tjänstgöringsgrad är redan de angivna – ingenting att ändra")
    person.monthly_salary_sek = data.monthly_salary_sek
    person.employment_rate = new_rate
    session.flush()
    return CurrentSalaryResult(
        personal_id_number=person.personal_id_number,
        previous_salary_sek=previous_salary,
        monthly_salary_sek=data.monthly_salary_sek,
        previous_employment_rate=previous_rate,
        employment_rate=new_rate,
        note=(
            "Aktuell lön är ändrad (stamdata). Inget löneunderlag och ingen premie har skapats – "
            "pensionsmedförande lön registreras som löneunderlag (PR-ITP1-014)."
        ),
    )


def _same(a: Decimal | None, b: Decimal | None) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and Decimal(a) == Decimal(b))


# --- kontaktuppgifter ---------------------------------------------------------------------------


class ContactDetailsInput(BaseModel):
    personal_id_number: str = Field(pattern=r"^\d{12}$", description="Den försäkrades personnummer, 12 siffror")
    email: str | None = Field(default=None, max_length=255, pattern=EMAIL_PATTERN,
                              description="E-post efter ändringen; tom = ta bort")
    phone: str | None = Field(default=None, max_length=30, pattern=PHONE_PATTERN,
                              description="Telefon efter ändringen; tom = ta bort")
    source: Literal["insured", "employer", "other"] = Field(
        description="Varifrån ändringen kommer: den försäkrade, arbetsgivaren eller annat"
    )

    @field_validator("email", "phone", mode="before")
    @classmethod
    def _empty_is_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value


class ChangedField(BaseModel):
    field: str
    previous: str | None
    new: str | None


class ContactDetailsResult(BaseModel):
    personal_id_number: str
    changed: list[ChangedField]
    source: str


@operation(
    name="update_contact_details",
    description=(
        "Ändrar den försäkrades e-post och telefon (båda anges som de ska vara; tom tar bort). Rätt person ska "
        "vara verifierad (PR-ITP1-031). Namn och personnummer ändras inte här."
    ),
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-031"],
    pii=True,
)
def update_contact_details(ctx: OperationContext, data: ContactDetailsInput) -> ContactDetailsResult:
    session = ctx.require_session()
    person = common.lock_person(session, data.personal_id_number)
    if person.status == "deceased":
        raise BlockedError("Den försäkrade är avliden – dödsboets kontakt hanteras i avräkningen (PR-ITP1-010)")
    changed = [
        ChangedField(field=name, previous=getattr(person, name), new=getattr(data, name))
        for name in ("email", "phone")
        if getattr(person, name) != getattr(data, name)
    ]
    if not changed:
        raise ConflictError("Kontaktuppgifterna är redan de angivna – ingenting att ändra")
    for change in changed:
        setattr(person, change.field, change.new)
    session.flush()
    return ContactDetailsResult(personal_id_number=person.personal_id_number, changed=changed, source=data.source)
