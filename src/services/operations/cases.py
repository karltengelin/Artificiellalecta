"""Ärenden – handläggaragentens arbetsenhet och mandat (Fas 5 F5-2, B-033).

Tabellen `cases` (databasschema.md §9g) har ärendets aktuella status och utfall;
historiken är händelseloggen, eftersom varje ändring går genom en av operationerna
här och loggas med ärendenumret som `case_id`.

- `create_case`, `list_cases`, `update_case_status`, `close_case`: handläggaren
  (`HUMAN_ONLY`; skrivningarna saknar produktregel och stängs därför även av golvet).
  Harness skriver status efter en agentkörning som systemaktör.
- `get_case`: läsning som agenten får använda – harness begränsar den till körningens
  ärende (F5-3).

Första ärendetypen är `salary_report`: ett inrapporterat löneunderlag som ska prövas
och registreras med `register_salary_report`. Typens uppgifter ligger i `details` och
valideras här (B-033 val F). Avslag och manuell prövning motiveras alltid och avgörs av
handläggaren (PR-ITP1-031).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select

from models import (
    ApprovalRequestRecord,
    Case,
    Employer,
    InsuredPerson,
    OperationEventRecord,
    Policy,
)
from models.case import OUTCOMES_REQUIRING_NOTE
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, ConflictError, NotFoundError
from services.operations import common

CaseType = Literal["salary_report"]
OpenStatus = Literal["open", "in_progress", "waiting_approval", "waiting_info"]
CaseOutcome = Literal["approved", "rejected", "supplement_requested", "manual_review", "no_action"]

_CASE_NUMBER = r"^CASE-\d{6}$"


# --- typens uppgifter -----------------------------------------------------------------------------


class SalaryReportDetails(BaseModel):
    """Det inrapporterade löneunderlaget (PR-ITP1-014) – samma fält som register_salary_report."""

    pensionable_salary_sek: Decimal = Field(
        ge=0, max_digits=10, decimal_places=2, description="Rapporterad pensionsmedförande lön i kronor"
    )
    kind: Literal["new", "correction"] = Field(description="new = första rapporten; correction = rättelse")
    corrects_version: int | None = Field(default=None, ge=1, description="Vid rättelse: versionen som rättas")
    source: Literal["employer", "manual"] = Field(description="Arbetsgivarens rapport eller manuellt underlag")

    @model_validator(mode="after")
    def _version(self) -> SalaryReportDetails:
        if (self.kind == "correction") != (self.corrects_version is not None):
            raise ValueError("corrects_version anges vid rättelse och bara då")
        return self


# --- create_case ----------------------------------------------------------------------------------


class CaseInput(BaseModel):
    case_type: CaseType
    personal_id_number: str = Field(pattern=r"^\d{12}$", description="Den försäkrade, 12 siffror")
    employer_org_number: str = Field(pattern=r"^\d{10}$", description="Arbetsgivaren som rapporterat, 10 siffror")
    policy_number: str | None = Field(default=None, description="Försäkringen, om ärendet gäller en viss")
    period_month: date = Field(description="Månaden ärendet gäller – dagen ignoreras")
    received_date: date = Field(description="Dagen underlaget togs emot")
    source_reference: str | None = Field(default=None, min_length=1, max_length=100, description="Avsändarens referens")
    due_date: date | None = Field(default=None, description="Tidsfrist, om någon")
    assigned_to: str | None = Field(default=None, min_length=1, max_length=100, description="Handläggaren som äger ärendet")
    details: SalaryReportDetails

    @field_validator("period_month")
    @classmethod
    def _first_of_month(cls, value: date) -> date:
        return common.month_of(value)


class CaseResult(BaseModel):
    case_number: str
    case_type: str
    status: str


@operation(
    name="create_case",
    description=(
        "Registrerar ett ärende: ett inrapporterat löneunderlag för en försäkrad hos en arbetsgivare en månad, "
        "med mottagningsdag och referens. Ärendet får nästa CASE-NNNNNN och status open."
    ),
    kind=OperationKind.WRITE,
    pii=True,
)
def create_case(ctx: OperationContext, data: CaseInput) -> CaseResult:
    session = ctx.require_session()
    if data.received_date > common.today():
        raise BlockedError("Mottagningsdagen ligger i framtiden – ange dagen underlaget faktiskt kom in")
    person = session.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == data.personal_id_number))
    if person is None:
        raise NotFoundError("Ingen försäkrad med det personnumret – anslut personen först")
    employer = session.scalar(select(Employer).where(Employer.org_number == data.employer_org_number))
    if employer is None:
        raise NotFoundError(f"Ingen arbetsgivare med organisationsnummer {data.employer_org_number}")
    policy_id = None
    if data.policy_number is not None:
        policy = session.scalar(select(Policy).where(Policy.policy_number == data.policy_number))
        if policy is None or policy.insured_person_id != person.id:
            raise NotFoundError(f"Försäkringen {data.policy_number} hör inte till den försäkrade")
        policy_id = policy.id
    if data.source_reference is not None:
        duplicate = session.scalar(
            select(Case.case_number).where(
                Case.case_type == data.case_type, Case.employer_id == employer.id,
                Case.source_reference == data.source_reference,
            )
        )
        if duplicate is not None:
            raise ConflictError(f"Underlaget {data.source_reference} är redan registrerat som ärende {duplicate}")

    case = Case(
        case_number=_next_case_number(session),
        case_type=data.case_type,
        status="open",
        insured_person_id=person.id,
        policy_id=policy_id,
        employer_id=employer.id,
        period_month=data.period_month,
        channel="manual",  # v1: handläggaren registrerar (B-033 val B)
        received_date=data.received_date,
        source_reference=data.source_reference,
        due_date=data.due_date,
        details=data.details.model_dump(mode="json"),
        assigned_to=data.assigned_to,
        created_by=ctx.actor.id,
    )
    session.add(case)
    return CaseResult(case_number=case.case_number, case_type=case.case_type, status=case.status)


def _next_case_number(session) -> str:
    """Nästa CASE-NNNNNN. Krockar två samtidiga registreringar stoppar unikhetsregeln den ena (ConflictError)."""
    highest = session.scalar(select(func.max(Case.case_number)))
    number = int(highest.removeprefix("CASE-")) + 1 if highest else 1
    return f"CASE-{number:06d}"


# --- get_case och list_cases ------------------------------------------------------------------------


class CaseLookup(BaseModel):
    case_number: str = Field(pattern=_CASE_NUMBER, description="Ärendenumret, t.ex. CASE-000001")


class CaseView(BaseModel):
    case_number: str
    case_type: str
    status: str
    outcome: str | None
    personal_id_number: str | None
    employer_org_number: str | None
    policy_number: str | None
    period_month: date | None
    channel: str
    received_date: date
    source_reference: str | None
    due_date: date | None
    details: dict
    assigned_to: str | None
    last_run_id: str | None
    created_by: str
    closed_by: str | None
    closed_at: str | None
    closing_note: str | None


def _view(session, case: Case) -> CaseView:
    pid = session.scalar(select(InsuredPerson.personal_id_number).where(InsuredPerson.id == case.insured_person_id))
    org = session.scalar(select(Employer.org_number).where(Employer.id == case.employer_id))
    policy = session.scalar(select(Policy.policy_number).where(Policy.id == case.policy_id))
    return CaseView(
        case_number=case.case_number, case_type=case.case_type, status=case.status, outcome=case.outcome,
        personal_id_number=pid, employer_org_number=org, policy_number=policy, period_month=case.period_month,
        channel=case.channel, received_date=case.received_date, source_reference=case.source_reference,
        due_date=case.due_date, details=case.details, assigned_to=case.assigned_to, last_run_id=case.last_run_id,
        created_by=case.created_by, closed_by=case.closed_by,
        closed_at=case.closed_at.isoformat(timespec="seconds") if case.closed_at else None,
        closing_note=case.closing_note,
    )


def _case(session, case_number: str, *, lock: bool = False) -> Case:
    query = select(Case).where(Case.case_number == case_number)
    case = session.scalar(query.with_for_update() if lock else query)
    if case is None:
        raise NotFoundError(f"Okänt ärende: {case_number}")
    return case


@operation(
    name="get_case",
    description=(
        "Hämtar ett ärende med den försäkrade, arbetsgivaren, månaden, mottagningsdag, referens, status och "
        "de inrapporterade uppgifterna (för löneunderlag: rapporterad lön, ny rapport eller rättelse, källa)."
    ),
    kind=OperationKind.READ,
    pii=True,
)
def get_case(ctx: OperationContext, data: CaseLookup) -> CaseView:
    session = ctx.require_session()
    return _view(session, _case(session, data.case_number))


class CaseQuery(BaseModel):
    status: Literal["active", "open", "in_progress", "waiting_approval", "waiting_info", "closed"] | None = Field(
        default="active", description="active = alla som inte är stängda; None = alla"
    )
    case_type: CaseType | None = None
    assigned_to: str | None = Field(default=None, max_length=100)
    personal_id_number: str | None = Field(default=None, pattern=r"^\d{12}$")
    limit: int = Field(default=100, ge=1, le=500)


class CaseSummary(BaseModel):
    case_number: str
    case_type: str
    status: str
    outcome: str | None
    personal_id_number: str | None
    name: str | None
    period_month: date | None
    received_date: date
    assigned_to: str | None


class CaseList(BaseModel):
    cases: list[CaseSummary] = Field(description="Aktiva äldst mottagna först; stängda senast stängda först")
    count: int


@operation(
    name="list_cases",
    description="Listar ärenden med urval på status, typ, handläggare eller försäkrad.",
    kind=OperationKind.READ,
    pii=True,
)
def list_cases(ctx: OperationContext, data: CaseQuery) -> CaseList:
    session = ctx.require_session()
    query = select(Case, InsuredPerson).outerjoin(InsuredPerson, Case.insured_person_id == InsuredPerson.id)
    if data.status == "active":
        query = query.where(Case.status != "closed")
    elif data.status is not None:
        query = query.where(Case.status == data.status)
    if data.case_type is not None:
        query = query.where(Case.case_type == data.case_type)
    if data.assigned_to is not None:
        query = query.where(Case.assigned_to == data.assigned_to)
    if data.personal_id_number is not None:
        query = query.where(InsuredPerson.personal_id_number == data.personal_id_number)
    if data.status == "closed":
        query = query.order_by(Case.closed_at.desc(), Case.case_number.desc())
    else:
        query = query.order_by(Case.received_date, Case.case_number)
    rows = session.execute(query.limit(data.limit)).all()
    cases = [
        CaseSummary(
            case_number=c.case_number, case_type=c.case_type, status=c.status, outcome=c.outcome,
            personal_id_number=p.personal_id_number if p else None,
            name=f"{p.first_name} {p.last_name}" if p else None,
            period_month=c.period_month, received_date=c.received_date, assigned_to=c.assigned_to,
        )
        for c, p in rows
    ]
    return CaseList(cases=cases, count=len(cases))


# --- update_case_status och close_case ---------------------------------------------------------------


class CaseStatusInput(BaseModel):
    case_number: str = Field(pattern=_CASE_NUMBER)
    status: OpenStatus = Field(description="Ny status. Stängning görs med close_case")
    assigned_to: str | None = Field(default=None, min_length=1, max_length=100, description="Ny handläggare, om den byts")
    last_run_id: str | None = Field(default=None, min_length=1, max_length=100, description="Senaste agentkörningen")


class CaseStatusResult(BaseModel):
    case_number: str
    previous_status: str
    status: str
    assigned_to: str | None


@operation(
    name="update_case_status",
    description="Byter ett öppet ärendes status, och vid behov handläggare eller senaste agentkörning.",
    kind=OperationKind.WRITE,
)
def update_case_status(ctx: OperationContext, data: CaseStatusInput) -> CaseStatusResult:
    session = ctx.require_session()
    case = _case(session, data.case_number, lock=True)
    if case.status == "closed":
        raise ConflictError(f"Ärendet {case.case_number} är stängt och ändras inte")
    previous = case.status
    case.status = data.status
    if data.assigned_to is not None:
        case.assigned_to = data.assigned_to
    if data.last_run_id is not None:
        case.last_run_id = data.last_run_id
    return CaseStatusResult(
        case_number=case.case_number, previous_status=previous, status=case.status, assigned_to=case.assigned_to
    )


class CloseCaseInput(BaseModel):
    case_number: str = Field(pattern=_CASE_NUMBER)
    outcome: CaseOutcome
    closing_note: str | None = Field(default=None, min_length=1, max_length=2000, description="Motivering")

    @model_validator(mode="after")
    def _note(self) -> CloseCaseInput:
        if self.outcome in OUTCOMES_REQUIRING_NOTE and self.closing_note is None:
            raise ValueError("Avslag och manuell prövning kräver en motivering (closing_note), PR-ITP1-031")
        return self


class CloseCaseResult(BaseModel):
    case_number: str
    outcome: str
    closed_by: str
    closed_at: str


@operation(
    name="close_case",
    description=(
        "Stänger ett ärende med utfall: approved, rejected, supplement_requested, manual_review eller "
        "no_action. Avslag och manuell prövning kräver motivering."
    ),
    kind=OperationKind.WRITE,
)
def close_case(ctx: OperationContext, data: CloseCaseInput) -> CloseCaseResult:
    session = ctx.require_session()
    case = _case(session, data.case_number, lock=True)
    if case.status == "closed":
        raise ConflictError(f"Ärendet {case.case_number} är redan stängt ({case.outcome})")
    pending = session.scalar(
        select(func.count()).select_from(ApprovalRequestRecord).where(
            ApprovalRequestRecord.case_id == case.case_number, ApprovalRequestRecord.status == "pending"
        )
    )
    if pending:
        raise BlockedError(
            f"Ärendet {case.case_number} har {pending} förslag som väntar i godkännandekön – avgör dem först"
        )
    if data.outcome == "approved" and not _change_executed(session, case.case_number):
        raise BlockedError(
            "Utfallet approved kräver en genomförd ändring i ärendet: ett godkänt agentförslag eller en "
            "registrering som handläggaren gjort med ärendenumret. Annars: no_action eller manual_review"
        )
    case.status = "closed"
    case.outcome = data.outcome
    case.closing_note = data.closing_note
    case.closed_by = ctx.actor.id
    case.closed_at = datetime.now(UTC)
    return CloseCaseResult(
        case_number=case.case_number, outcome=case.outcome, closed_by=case.closed_by,
        closed_at=case.closed_at.isoformat(timespec="seconds"),
    )


def _change_executed(session, case_number: str) -> bool:
    """Har en affärsändring genomförts i ärendet? Godkänt förslag eller utförd skrivning med case_id."""
    approved = session.scalar(
        select(func.count()).select_from(ApprovalRequestRecord).where(
            ApprovalRequestRecord.case_id == case_number, ApprovalRequestRecord.status == "approved"
        )
    )
    if approved:
        return True
    executed = session.scalar(
        select(func.count()).select_from(OperationEventRecord).where(
            OperationEventRecord.case_id == case_number,
            OperationEventRecord.outcome == "executed",
            OperationEventRecord.kind.in_(("write", "external")),
            OperationEventRecord.operation.notin_(("create_case", "update_case_status", "close_case")),
        )
    )
    return bool(executed)
