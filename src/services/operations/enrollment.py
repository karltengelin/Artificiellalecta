"""Anslutning av en ny anställd (Fas 4 S5, PR-ITP1-012/013, villkor §2–3).

Skapar i en transaktion den försäkrade, en försäkring (nästa `AL-NNNNNN`),
förmånen ålderspension och läget `premium_paying` från den dokumenterade
ITP1-tillhörigheten. Försäkringens `signed_date` och `start_date` är
tillhörighetsdagen (databasen kräver start ≥ tecknad, så registreringsdagen kan
inte vara tecknad vid retroaktiv anslutning – den står i händelseloggen).

Premieålder är en separat fråga (PR-ITP1-012): en person under 25 ansluts med
`premium_paying` och ordinarie premie från 25-årsmånaden (PR-ITP1-013) –
premiemotorns åldersfönster ger ingen premie före dess. Anslutningen skapar
ingen premie och skickar inget försäkringsbesked (villkor §14 – ett senare
`external`-steg).

Blockeras (manuell prövning): VD, ägare, utlandsanställd eller avstående
(uttryckligt anslutnings-/undantagsbeslut, PR-ITP1-012), tillhörighet i
framtiden, 66 år eller äldre vid tillhörighetens start (frivillig premie 66–67
kräver arbetsgivarens beslut, PR-ITP1-016), arbetsgivare som inte är aktiv,
anslutning före arbetsgivarens ITP-anslutning, och befintligt personnummer med
avslutad anställning (återanställning eller ny arbetsgivare kräver
anställningshistorik som modellen saknar). Ett aktivt befintligt personnummer
är en konflikt.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select

from models import Employer, InsuredPerson, Policy, PolicyBenefit, PolicyState
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, ConflictError, NotFoundError
from services.operations import common

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PHONE_PATTERN = r"^\+?[0-9 ()-]{6,30}$"

EMPLOYMENT_CATEGORIES = {
    "ordinary": "anställd utan särskild ställning",
    "ceo": "verkställande direktör",
    "owner": "företagare eller delägare",
    "posted_abroad": "utlandsanställd",
    "opted_out": "har avstått ITP",
}


class EnrollmentInput(BaseModel):
    personal_id_number: str = Field(pattern=r"^\d{12}$", description="Personnummer, 12 siffror (ÅÅÅÅMMDDNNNN)")
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    employer_org_number: str = Field(pattern=r"^\d{10}$", description="Arbetsgivarens organisationsnummer")
    employment_start_date: date = Field(description="Anställningens första dag")
    itp1_start_date: date = Field(description="Dokumenterad ITP1-tillhörighet från – försäkringens start")
    employment_category: Literal["ordinary", "ceo", "owner", "posted_abroad", "opted_out"] = Field(
        description="ordinary = anställd utan särskild ställning; övriga kräver uttryckligt beslut (PR-ITP1-012)"
    )
    affiliation_reference: str = Field(
        min_length=3, max_length=100, description="Arbetsgivarens anmälan, t.ex. filreferens eller ärendenummer"
    )
    monthly_salary_sek: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2,
        description="Aktuell månadslön (stamdata) – inte pensionsmedförande lön",
    )
    employment_rate: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    email: str | None = Field(default=None, max_length=255, pattern=EMAIL_PATTERN)
    phone: str | None = Field(default=None, max_length=30, pattern=PHONE_PATTERN)

    @field_validator("first_name", "last_name", "affiliation_reference")
    @classmethod
    def _strip(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Får inte vara tomt")
        return value.strip()

    @field_validator("personal_id_number")
    @classmethod
    def _valid_pnr(cls, value: str) -> str:
        if not common.valid_personal_id_number(value):
            raise ValueError("Personnumret är inte giltigt (datum eller kontrollsiffra)")
        return value

    @model_validator(mode="after")
    def _dates(self) -> EnrollmentInput:
        if self.itp1_start_date < self.employment_start_date:
            raise ValueError("ITP1-tillhörigheten kan inte börja före anställningen")
        return self


class EnrollmentResult(BaseModel):
    insured_person_id: str
    personal_id_number: str
    first_name: str
    last_name: str
    employer_org_number: str
    policy_number: str
    start_date: date = Field(description="Försäkringens start = ITP1-tillhörighetens start")
    state: str
    premium_from_month: date = Field(description="Första månad med ordinarie premie (25-årsmånaden eller starten)")
    information_letter_sent: bool = Field(description="Försäkringsbesked (villkor §14) – skickas i ett senare steg")
    note: str


@operation(
    name="enroll_insured_person",
    description=(
        "Ansluter en ny anställd (PR-ITP1-012): skapar den försäkrade, en ITP1-försäkring med "
        "ålderspension och läget premiebetalande från den dokumenterade ITP1-tillhörigheten. Ordinarie "
        "premie från 25-årsmånaden (PR-ITP1-013). Skapar ingen premie och skickar inget besked."
    ),
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-012", "PR-ITP1-013"],
    pii=True,
)
def enroll_insured_person(ctx: OperationContext, data: EnrollmentInput) -> EnrollmentResult:
    session = ctx.require_session()
    today = common.today()

    if data.employment_category != "ordinary":
        raise BlockedError(
            f"Den anställde är {EMPLOYMENT_CATEGORIES[data.employment_category]} – anslutningen kräver ett "
            "uttryckligt anslutnings- eller undantagsbeslut enligt avtalet (PR-ITP1-012). Manuell prövning"
        )
    if data.itp1_start_date > today:
        raise BlockedError(
            f"ITP1-tillhörigheten börjar {data.itp1_start_date}, i framtiden. Framtidsdatering stöds inte – "
            "läsningen visar den öppna raden som dagens läge. Anslut när tillhörigheten har börjat"
        )

    existing = session.scalar(
        select(InsuredPerson).where(InsuredPerson.personal_id_number == data.personal_id_number).with_for_update()
    )
    if existing is not None:
        if existing.status == "active" and existing.employment_end_date is None:
            raise ConflictError("Personen finns redan som aktiv försäkrad – se översikten")
        raise BlockedError(
            f"Personen finns redan (status {existing.status}). Återanställning eller ny arbetsgivare kräver "
            "anställningshistorik som modellen saknar (PR-ITP1-013) – manuell prövning"
        )

    employer = session.scalar(select(Employer).where(Employer.org_number == data.employer_org_number))
    if employer is None:
        raise NotFoundError(f"Ingen arbetsgivare med organisationsnummer {data.employer_org_number}")
    if employer.status != "active":
        raise BlockedError(f"Arbetsgivaren har status {employer.status} – nya anslutningar prövas manuellt")
    if employer.collective_agreement != "ITP":
        raise BlockedError(f"Arbetsgivaren har avtalet {employer.collective_agreement} – bara ITP ingår (B-002)")
    if data.itp1_start_date < employer.affiliation_date:
        raise BlockedError(
            f"Tillhörigheten {data.itp1_start_date} ligger före arbetsgivarens ITP-anslutning "
            f"{employer.affiliation_date} (PR-ITP1-012)"
        )

    born = common.birth_date(data.personal_id_number)
    month_25, month_66 = common.month_offset(born, 25), common.month_offset(born, 66)
    start_month = common.month_of(data.itp1_start_date)
    if start_month >= month_66:
        raise BlockedError(
            f"Personen fyller 66 år {month_66:%Y-%m}, före eller samma månad som tillhörigheten börjar – ingen "
            "ordinarie premie (PR-ITP1-013). Frivillig premie 66–67 kräver arbetsgivarens beslut (PR-ITP1-016)"
        )
    premium_from = max(start_month, month_25)

    person = InsuredPerson(
        personal_id_number=data.personal_id_number,
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        phone=data.phone,
        employer_id=employer.id,
        employment_start_date=data.employment_start_date,
        monthly_salary_sek=data.monthly_salary_sek,
        employment_rate=data.employment_rate,
        itp1_start_date=data.itp1_start_date,
        status="active",
    )
    session.add(person)
    session.flush()
    policy = Policy(
        policy_number=_next_policy_number(session),
        insured_person_id=person.id,
        product_code="ITP1",
        signed_date=data.itp1_start_date,
        start_date=data.itp1_start_date,
    )
    session.add(policy)
    session.flush()
    session.add(PolicyBenefit(policy_id=policy.id, benefit_type="retirement_dc", start_date=data.itp1_start_date))
    session.add(
        PolicyState(
            policy_id=policy.id, state="premium_paying", valid_from=data.itp1_start_date,
            note=f"Anslutning enligt anmälan {data.affiliation_reference} (PR-ITP1-012)"[:255],
        )
    )
    session.flush()

    if premium_from > start_month:
        note = (
            f"Avtalet är registrerat. Ordinarie premie från 25-årsmånaden {premium_from:%Y-%m} (PR-ITP1-013). "
            "Försäkringsbesked skickas i ett senare steg."
        )
    else:
        note = "Anslutningen är registrerad. Ingen premie skapad – premien bygger på löneunderlag. Försäkringsbesked skickas i ett senare steg."
    return EnrollmentResult(
        insured_person_id=str(person.id),
        personal_id_number=person.personal_id_number,
        first_name=person.first_name,
        last_name=person.last_name,
        employer_org_number=employer.org_number,
        policy_number=policy.policy_number,
        start_date=data.itp1_start_date,
        state="premium_paying",
        premium_from_month=premium_from,
        information_letter_sent=False,
        note=note,
    )


def _next_policy_number(session) -> str:
    """Nästa AL-NNNNNN. Krockar två samtidiga anslutningar stoppar unikhetsregeln den ena (ConflictError)."""
    highest = session.scalar(select(func.max(Policy.policy_number)).where(Policy.policy_number.like("AL-%")))
    number = int(highest.removeprefix("AL-")) + 1 if highest else 1
    return f"AL-{number:06d}"
