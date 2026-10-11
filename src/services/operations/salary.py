"""Löneunderlag – pensionsmedförande lön per person, arbetsgivare och månad (Fas 1f T3).

PR-ITP1-014: faktiskt utbetald kontant bruttolön efter löneväxling, i
utbetalningsmånaden. Noll rapporteras uttryckligen och skiljs från saknad
rapport. Rättelse av en tidigare rapport ändrar just den månaden – som en ny
version, aldrig genom att skriva över (PR-ITP1-017: ingen dubblett utan
uttrycklig versionsrelation).

Underlaget skiljs från aktuell lön på personen (`monthly_salary_sek`) och från
premien. Registreringen skapar ingen premie och räknar inte om gamla premier;
en rättelse av en månad med premie redovisar den berörda premien, som rättas
med correct_premium_transaction (PR-ITP1-019 p.1).

Stöds: rapport för den försäkrades nuvarande arbetsgivare, inom anställningen
och ITP1-tillhörigheten, för månader till och med innevarande.
Blockeras (manuell prövning): annan arbetsgivare (anställningshistorik saknas),
månad efter anställningens slut (slutlön/bonus, PR-ITP1-013), avliden
försäkrad, framtida månad, och ny rapport för en månad som redan har premie
från den genererade historiken.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select

from models import Employer, InsuredPerson, SalaryReport
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, ConflictError, NotFoundError
from services.operations import common

# --- registrering -------------------------------------------------------------------


class SalaryReportInput(BaseModel):
    personal_id_number: str = Field(pattern=r"^\d{12}$", description="Den försäkrades personnummer, 12 siffror")
    employer_org_number: str = Field(pattern=r"^\d{10}$", description="Arbetsgivarens organisationsnummer, 10 siffror")
    period_month: date = Field(description="Utbetalningsmånaden – dagen i datumet ignoreras")
    pensionable_salary_sek: Decimal = Field(
        ge=0, max_digits=10, decimal_places=2,
        description="Pensionsmedförande lön i kronor (PR-ITP1-014). 0 = uttryckligen rapporterad noll",
    )
    kind: Literal["new", "correction"] = Field(
        description="new = första rapporten för månaden; correction = rättelse av den gällande versionen"
    )
    corrects_version: int | None = Field(
        default=None, ge=1, description="Vid rättelse: versionen som rättas – måste vara den gällande"
    )
    source: Literal["employer", "manual"] = Field(
        description="employer = arbetsgivarens rapport; manual = underlag som handläggaren registrerar"
    )
    source_reference: str | None = Field(
        default=None, min_length=1, max_length=100, description="Avsändarens referens, t.ex. lönefil eller lönebesked"
    )
    received_date: date = Field(description="Dagen underlaget togs emot")

    @field_validator("period_month")
    @classmethod
    def _first_of_month(cls, value: date) -> date:
        return common.month_of(value)

    @model_validator(mode="after")
    def _version_relation(self) -> SalaryReportInput:
        if self.kind == "correction" and self.corrects_version is None:
            raise ValueError("En rättelse måste ange corrects_version (versionen som rättas)")
        if self.kind == "new" and self.corrects_version is not None:
            raise ValueError("En ny rapport kan inte ange corrects_version – använd kind='correction'")
        return self


class AffectedPremium(BaseModel):
    transaction_id: str
    transaction_type: str
    pensionable_salary_sek: Decimal | None
    amount_sek: Decimal
    status: str


class SalaryReportResult(BaseModel):
    report_id: str
    period_month: date
    employer_org_number: str
    kind: str
    version: int
    pensionable_salary_sek: Decimal
    previous_salary_sek: Decimal | None = Field(description="Den rättade versionens lön, vid rättelse")
    affected_premiums: list[AffectedPremium] = Field(
        description="Premie för månaden som bygger på tidigare underlag – rättas separat (correct_premium_transaction)"
    )
    note: str


@operation(
    name="register_salary_report",
    description=(
        "Registrerar pensionsmedförande lön (PR-ITP1-014) för en försäkrad hos sin arbetsgivare en "
        "utbetalningsmånad: ny rapport eller rättelse som ny version. Uttrycklig noll tillåts. "
        "Skapar ingen premie och räknar inte om gamla premier."
    ),
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-013", "PR-ITP1-014", "PR-ITP1-017"],
    pii=True,
)
def register_salary_report(ctx: OperationContext, data: SalaryReportInput) -> SalaryReportResult:
    session = ctx.require_session()
    today = common.today()
    person = common.lock_person(session, data.personal_id_number)
    employer = session.scalar(select(Employer).where(Employer.org_number == data.employer_org_number))
    if employer is None:
        raise NotFoundError(f"Ingen arbetsgivare med organisationsnummer {data.employer_org_number}")

    month = data.period_month
    _check_employment(person, employer, month, today)
    if data.received_date > today:
        raise BlockedError("Mottagningsdagen ligger i framtiden")
    if data.received_date < month:
        raise BlockedError("Mottagningsdagen ligger före rapportmånaden – lön rapporteras när den betalats ut")

    versions = list(
        session.scalars(
            select(SalaryReport)
            .where(
                SalaryReport.insured_person_id == person.id,
                SalaryReport.employer_id == employer.id,
                SalaryReport.period_month == month,
            )
            .order_by(SalaryReport.version.desc())
        )
    )
    current = versions[0] if versions else None
    premiums = common.premium_rows_in_month(session, common.benefit_ids_of(session, person.id), month)

    if data.kind == "new":
        if current is not None:
            raise ConflictError(
                f"Rapport för {month:%Y-%m} finns redan (version {current.version}) – en dubblett ersätter "
                "den inte (PR-ITP1-017). Rätta med kind='correction' och corrects_version="
                f"{current.version}"
            )
        if premiums:
            raise BlockedError(
                f"{month:%Y-%m} har redan premie med löneunderlag från premiehistoriken. En ny rapport "
                "skulle inte påverka den – rätta premien med correct_premium_transaction"
            )
        version, supersedes, previous_salary = 1, None, None
    else:
        if current is None:
            raise ConflictError(f"Det finns ingen rapport för {month:%Y-%m} att rätta – registrera kind='new'")
        if data.corrects_version != current.version:
            raise ConflictError(
                f"Version {data.corrects_version} är inte den gällande för {month:%Y-%m} (gällande: "
                f"version {current.version}) – rättelsen bygger på inaktuellt underlag"
            )
        if Decimal(data.pensionable_salary_sek) == Decimal(current.pensionable_salary_sek):
            raise ConflictError("Rättelsen ändrar inte lönen – den gällande versionen har redan det beloppet")
        version, supersedes, previous_salary = current.version + 1, current.id, current.pensionable_salary_sek

    if data.source_reference is not None:
        duplicate = session.scalar(
            select(SalaryReport).where(
                SalaryReport.employer_id == employer.id, SalaryReport.source_reference == data.source_reference
            )
        )
        if duplicate is not None:
            raise ConflictError(
                f"Rapporten med referens {data.source_reference} är redan registrerad "
                f"({duplicate.period_month:%Y-%m}, version {duplicate.version})"
            )

    report = SalaryReport(
        insured_person_id=person.id,
        employer_id=employer.id,
        period_month=month,
        version=version,
        supersedes_id=supersedes,
        pensionable_salary_sek=data.pensionable_salary_sek,
        source=data.source,
        source_reference=data.source_reference,
        received_date=data.received_date,
    )
    session.add(report)
    session.flush()

    affected = [
        AffectedPremium(
            transaction_id=str(tx.id), transaction_type=tx.transaction_type,
            pensionable_salary_sek=tx.pensionable_salary_sek, amount_sek=tx.amount_sek, status=tx.status,
        )
        for tx in premiums
    ]
    if data.kind == "new":
        note = "Nytt löneunderlag registrerat. Ingen premie skapad."
    elif affected:
        note = (
            f"Rättat från {previous_salary} till {data.pensionable_salary_sek} kr. Premien för månaden bygger på "
            "tidigare underlag och rättas separat med correct_premium_transaction (PR-ITP1-019 p.1)."
        )
    else:
        note = f"Rättat från {previous_salary} till {data.pensionable_salary_sek} kr. Ingen premie berörs."
    return SalaryReportResult(
        report_id=str(report.id),
        period_month=month,
        employer_org_number=employer.org_number,
        kind=data.kind,
        version=version,
        pensionable_salary_sek=data.pensionable_salary_sek,
        previous_salary_sek=previous_salary,
        affected_premiums=affected,
        note=note,
    )


def _check_employment(person, employer, month: date, today: date) -> None:
    """Underlaget ska höra till en anställning med ITP1-tillhörighet som modellen känner till."""
    if person.status == "deceased":
        raise BlockedError("Den försäkrade är avliden – underlag efter dödsfall prövas manuellt (PR-ITP1-010, -013)")
    if person.employer_id != employer.id:
        raise BlockedError(
            "Rapporten gäller en annan arbetsgivare än den försäkrades nuvarande – anställningshistorik "
            "saknas i modellen, så kopplingen kan inte verifieras (PR-ITP1-013)"
        )
    if person.itp1_start_date is None:
        raise BlockedError("ITP1-tillhörighet saknas för den försäkrade (PR-ITP1-012)")
    if month < common.month_of(person.itp1_start_date):
        raise BlockedError(f"{month:%Y-%m} ligger före ITP1-tillhörighetens start {person.itp1_start_date}")
    if month < common.month_of(person.employment_start_date):
        raise BlockedError(f"{month:%Y-%m} ligger före anställningens start {person.employment_start_date}")
    if person.employment_end_date is not None and month > common.month_of(person.employment_end_date):
        raise BlockedError(
            f"{month:%Y-%m} ligger efter anställningens slut {person.employment_end_date}. Slutlön eller bonus "
            "efter avslut prövas manuellt mot den avslutade anställningen (PR-ITP1-013) – stöds inte här"
        )
    if month > common.month_of(today):
        raise BlockedError(f"{month:%Y-%m} har inte kommit – bara utbetald lön kan rapporteras (PR-ITP1-014)")


# --- läsning --------------------------------------------------------------------------


class SalaryReportQuery(BaseModel):
    personal_id_number: str = Field(pattern=r"^\d{12}$", description="Den försäkrades personnummer, 12 siffror")
    from_month: date | None = Field(default=None, description="Första månad (inklusive), valfri")
    to_month: date | None = Field(default=None, description="Sista månad (inklusive), valfri")


class SalaryReportRow(BaseModel):
    report_id: str
    period_month: date
    employer_org_number: str
    version: int
    current: bool = Field(description="Gällande version för månaden (högsta versionen)")
    pensionable_salary_sek: Decimal
    source: str
    source_reference: str | None
    received_date: date


class SalaryReports(BaseModel):
    personal_id_number: str
    reports: list[SalaryReportRow] = Field(
        description="Alla versioner. En månad utan rad saknar rapport; 0,00 är en rapporterad noll"
    )


@operation(
    name="get_salary_reports",
    description=(
        "Visar registrerat löneunderlag (pensionsmedförande lön per månad) för en försäkrad, med alla "
        "versioner och vilken som gäller. Saknad månad = ingen rapport; 0,00 = rapporterad noll."
    ),
    kind=OperationKind.READ,
    pii=True,
)
def get_salary_reports(ctx: OperationContext, data: SalaryReportQuery) -> SalaryReports:
    session = ctx.require_session()
    person = session.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == data.personal_id_number))
    if person is None:
        raise NotFoundError("Ingen försäkrad med det personnumret")
    query = (
        select(SalaryReport, Employer.org_number)
        .join(Employer, SalaryReport.employer_id == Employer.id)
        .where(SalaryReport.insured_person_id == person.id)
        .order_by(SalaryReport.period_month, Employer.org_number, SalaryReport.version)
    )
    if data.from_month is not None:
        query = query.where(SalaryReport.period_month >= common.month_of(data.from_month))
    if data.to_month is not None:
        query = query.where(SalaryReport.period_month <= common.month_of(data.to_month))
    rows = session.execute(query).all()
    latest: dict[tuple, int] = {}
    for report, org in rows:
        key = (report.period_month, org)
        latest[key] = max(latest.get(key, 0), report.version)
    return SalaryReports(
        personal_id_number=person.personal_id_number,
        reports=[
            SalaryReportRow(
                report_id=str(report.id),
                period_month=report.period_month,
                employer_org_number=org,
                version=report.version,
                current=report.version == latest[(report.period_month, org)],
                pensionable_salary_sek=report.pensionable_salary_sek,
                source=report.source,
                source_reference=report.source_reference,
                received_date=report.received_date,
            )
            for report, org in rows
        ],
    )
