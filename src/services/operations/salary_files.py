"""Löneunderlagsfil från arbetsgivaren – intag, granskning och godkännande (paket A steg 2, B-046).

P1-PREMIE-001 §4.1–4.2. Arbetsgivaren lämnar en fil per period med en rad per
anställd och månad. Filen valideras i betrodd kod utan att något registreras
(`import_salary_file`). Handläggaren granskar sammanställningen och godkänner den
med granskningens kontrollsumma (`approve_salary_file`). I samma transaktion:

1. varje giltig rad registreras med `register_salary_report` (källa `employer`,
   källreferens `<filens referens>:<radnummer>`);
2. premieunderlag skapas med `create_premium_from_salary_report` (§4.3);
3. ett ärende skapas per avvikande eller saknad rad, med filen som ursprung.

Rättelserelaterade avvikelser hos en känd person blir `salary_report`-ärenden som
ärendearbetaren kan förbereda (§8). Övriga avvikelser, saknade rader och avslagna
filer blir `salary_file_deviation`-ärenden, som bara handläggaren avgör.
Ärendena skapas av betrodd kod som systemvägen `salary_file_intake` (§6, §13).

Samma referens med samma kontrollsumma ger samma intagskvitto. Samma referens med
ändrat innehåll ger konflikt. Ändrat underlag mellan granskning och godkännande
stoppar godkännandet. En avslagen fil registrerar ingenting.

Saknade rader kontrolleras från första operativa premieperiod 2026-10 (PA1). En
uttrycklig nolla är en giltig rad, inte en saknad rad (PR-ITP1-014, -017).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from models import (
    BaseAmount,
    Case,
    Employer,
    InsuredPerson,
    Policy,
    PolicyState,
    SalaryFile,
    SalaryReport,
)
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, ConflictError, NotFoundError
from services.operations import common
from services.operations.cases import _next_case_number
from services.operations.premium_basis import (
    FIRST_OPERATIVE_PERIOD,
    PremiumBasisInput,
    _recipient,
    create_premium_from_salary_report,
)
from services.operations.salary import (
    SalaryReportInput,
    _check_employment,
    register_salary_report,
)
from services.parameters import premium_parameters
from skills.calculation.calculate_itp1_premium import calculate_itp1_premium

RULES = ["PR-ITP1-013", "PR-ITP1-014", "PR-ITP1-017"]
#: Systemvägen som skapar filens avvikelseärenden (P1-PREMIE-001 §6)
INTAKE_ACTOR = "salary_file_intake"
MAX_ROWS = 5000

#: Avvikelser som ärendearbetaren kan förbereda som löneunderlag (rättelser, §8)
AGENT_REASONS = ("already_reported", "correction_without_base", "stale_correction")

ReasonCode = Literal[
    "duplicate_in_file", "unknown_person", "other_employer", "negative_salary", "invalid_version_relation",
    "start_gap", "after_file_period", "outside_employment", "already_reported", "correction_without_base",
    "stale_correction", "correction_unchanged", "premium_exists",
]


# --- filformat ------------------------------------------------------------------------------------


class SalaryFileRow(BaseModel):
    personal_id_number: str = Field(pattern=r"^\d{12}$", description="Den anställdes personnummer, 12 siffror")
    period_month: date = Field(description="Utbetalningsmånaden – dagen i datumet ignoreras")
    pensionable_salary_sek: Decimal = Field(
        max_digits=12, decimal_places=2,
        description="Pensionsmedförande lön efter löneväxling (PR-ITP1-014). Negativ lön blir en avvikelse",
    )
    kind: Literal["new", "correction"] = Field(description="new = första rapporten; correction = rättelse")
    corrects_version: int | None = Field(default=None, ge=1, description="Vid rättelse: versionen som rättas")

    @field_validator("period_month")
    @classmethod
    def _first_of_month(cls, value: date) -> date:
        return common.month_of(value)


class SalaryFileInput(BaseModel):
    employer_org_number: str = Field(pattern=r"^\d{10}$", description="Arbetsgivarens organisationsnummer")
    period_month: date = Field(description="Filens period – dagen i datumet ignoreras")
    file_reference: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9._/-]+$",
                                description="Arbetsgivarens referens för filen, unik per arbetsgivare")
    received_date: date = Field(description="Dagen filen togs emot")
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$", description="SHA-256 över filens innehåll (file_checksum)")
    rows: list[SalaryFileRow] = Field(max_length=MAX_ROWS, description="En rad per anställd och månad")

    @field_validator("period_month")
    @classmethod
    def _first_of_month(cls, value: date) -> date:
        return common.month_of(value)


def _canonical(employer_org_number: str, period_month: date, file_reference: str, received_date: date,
               rows: list[SalaryFileRow]) -> dict[str, Any]:
    return {
        "employer_org_number": employer_org_number,
        "period_month": period_month.isoformat(),
        "file_reference": file_reference,
        "received_date": received_date.isoformat(),
        "rows": [
            {
                "personal_id_number": r.personal_id_number,
                "period_month": r.period_month.isoformat(),
                "pensionable_salary_sek": format(Decimal(r.pensionable_salary_sek).quantize(Decimal("0.01")), "f"),
                "kind": r.kind,
                "corrects_version": r.corrects_version,
            }
            for r in rows
        ],
    }


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def file_checksum(employer_org_number: str, period_month: date, file_reference: str, received_date: date,
                  rows: list[dict | SalaryFileRow]) -> str:
    """Filens kontrollsumma: SHA-256 över det kanoniska innehållet. Avsändaren räknar likadant."""
    parsed = [r if isinstance(r, SalaryFileRow) else SalaryFileRow.model_validate(r) for r in rows]
    return _sha256(_canonical(employer_org_number, common.month_of(period_month), file_reference,
                              received_date, parsed))


def _review_digest(checksum: str, validation: dict) -> str:
    return _sha256({"checksum": checksum, "validation": validation})


# --- validering -----------------------------------------------------------------------------------


def _month_end(month: date) -> date:
    following = month.replace(day=28) + timedelta(days=4)
    return following - timedelta(days=following.day)


def _validate(session, employer: Employer, period: date, rows: list[SalaryFileRow]) -> dict[str, Any]:
    """Betrodd kontroll av filen mot beståndet. Deterministisk: samma läge ger samma resultat."""
    today = common.today()
    keys = [(r.personal_id_number, r.period_month) for r in rows]
    duplicates = {k for k in keys if keys.count(k) > 1}
    outcomes: list[dict[str, Any]] = []
    salary_total = premium_total = Decimal("0.00")
    corrections = 0

    for number, row in enumerate(rows, start=1):
        reason, message = _row_deviation(session, employer, period, row, duplicates, today)
        entry: dict[str, Any] = {"row": number, "outcome": "deviation" if reason else "valid",
                                 "reason": reason, "message": message}
        if reason is None:
            salary_total += Decimal(row.pensionable_salary_sek)
            preview, issue = _premium_preview(session, row)
            entry["premium_preview_sek"] = None if preview is None else str(preview)
            entry["premium_issue"] = issue
            if row.kind == "correction":
                corrections += 1
            elif preview is not None:
                premium_total += preview
        outcomes.append(entry)

    in_file = {r.personal_id_number for r in rows if r.period_month == period}
    missing = _missing_reports(session, employer, period, in_file)
    deviations = [o for o in outcomes if o["outcome"] == "deviation"]
    by_reason: dict[str, int] = {}
    for o in deviations:
        by_reason[o["reason"]] = by_reason.get(o["reason"], 0) + 1
    return {
        "rows": outcomes,
        "missing": missing,
        "summary": {
            "rows": len(rows),
            "valid": len(rows) - len(deviations),
            "deviations": len(deviations),
            "missing": len(missing),
            "corrections": corrections,
            "salary_total_sek": str(salary_total),
            "premium_preview_sek": str(premium_total),
            "by_reason": by_reason,
        },
    }


def _row_deviation(session, employer, period, row: SalaryFileRow, duplicates, today):
    month = row.period_month
    if (row.personal_id_number, month) in duplicates:
        return "duplicate_in_file", "Personen och månaden förekommer flera gånger i filen – oklart vilken rad som gäller"
    person = session.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == row.personal_id_number))
    if person is None:
        return "unknown_person", "Personen är inte ansluten – anslutning eller rättat personnummer krävs"
    if person.employer_id != employer.id:
        return "other_employer", "Personen är ansluten via en annan arbetsgivare – anställningshistorik saknas (PA9)"
    if row.pensionable_salary_sek < 0:
        return "negative_salary", "Negativ lön – rättelser anges som ny version med rätt belopp (PR-ITP1-014)"
    if (row.kind == "correction") != (row.corrects_version is not None):
        return "invalid_version_relation", "corrects_version anges vid rättelse och bara då"
    if month < FIRST_OPERATIVE_PERIOD:
        return "start_gap", (f"{month:%Y-%m} ligger i startluckan före {FIRST_OPERATIVE_PERIOD:%Y-%m} – "
                             "sen rapportering prövas separat (PA1)")
    if month > period:
        return "after_file_period", f"{month:%Y-%m} ligger efter filens period {period:%Y-%m}"
    try:
        _check_employment(person, employer, month, today)
    except BlockedError as error:
        return "outside_employment", str(error)
    current = session.scalar(
        select(SalaryReport).where(
            SalaryReport.insured_person_id == person.id, SalaryReport.employer_id == employer.id,
            SalaryReport.period_month == month,
        ).order_by(SalaryReport.version.desc()).limit(1)
    )
    if row.kind == "new":
        if current is not None:
            return "already_reported", (f"Rapport för {month:%Y-%m} finns redan (version {current.version}) – "
                                        "en ny rad ersätter den inte (PR-ITP1-017)")
        if common.premium_rows_in_month(session, common.benefit_ids_of(session, person.id), month):
            return "premium_exists", f"{month:%Y-%m} har redan premie som inte bygger på detta underlag"
        return None, None
    if current is None:
        return "correction_without_base", f"Det finns ingen rapport för {month:%Y-%m} att rätta"
    if row.corrects_version != current.version:
        return "stale_correction", (f"Rättelsen gäller version {row.corrects_version}, men gällande är "
                                    f"version {current.version}")
    if Decimal(row.pensionable_salary_sek) == Decimal(current.pensionable_salary_sek):
        return "correction_unchanged", "Rättelsen ändrar inte lönen"
    return None, None


def _premium_preview(session, row: SalaryFileRow) -> tuple[Decimal | None, str | None]:
    """Månadens premie med radens lön – samma motor och parametrar som premieunderlaget (§4.3)."""
    month = row.period_month
    person = session.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == row.personal_id_number))
    base = session.get(BaseAmount, month.year)
    if base is None:
        return None, f"Inkomstbasbelopp saknas för {month.year}"
    try:
        _recipient(session, person, month)
        calc = calculate_itp1_premium(
            row.pensionable_salary_sek, Decimal(base.income_base_amount_sek),
            birth_date=common.birth_date(person.personal_id_number), period_month=month,
            parameters=premium_parameters(session, month),
        )
    except BlockedError as error:
        return None, str(error)
    return calc.total_premium_sek, None


def _missing_reports(session, employer, period: date, in_file: set[str]) -> list[dict[str, Any]]:
    """Premiebetalande personer hos arbetsgivaren utan rad i filen och utan registrerad rapport (PR-ITP1-017)."""
    if period < FIRST_OPERATIVE_PERIOD:
        return []
    end = _month_end(period)
    rows = session.execute(
        select(InsuredPerson, Policy.policy_number)
        .join(Policy, Policy.insured_person_id == InsuredPerson.id)
        .join(PolicyState, PolicyState.policy_id == Policy.id)
        .where(
            InsuredPerson.employer_id == employer.id,
            InsuredPerson.status != "deceased",
            PolicyState.state == "premium_paying",
            PolicyState.valid_from <= end,
            (PolicyState.valid_to.is_(None)) | (PolicyState.valid_to >= period),
        )
        .order_by(InsuredPerson.personal_id_number, Policy.policy_number)
    ).all()
    missing: dict[str, dict[str, Any]] = {}
    for person, policy_number in rows:
        pnr = person.personal_id_number
        if pnr in in_file or pnr in missing:
            continue
        reported = session.scalar(
            select(SalaryReport.id).where(
                SalaryReport.insured_person_id == person.id, SalaryReport.employer_id == employer.id,
                SalaryReport.period_month == period,
            ).limit(1)
        )
        if reported is None:
            missing[pnr] = {
                "personal_id_number": pnr, "policy_number": policy_number,
                "message": (f"Premiebetalande hos arbetsgivaren men saknas i filen för {period:%Y-%m}. Ingen "
                            "premie skapas och förra månadens lön antas inte (PR-ITP1-017)"),
            }
    return list(missing.values())


# --- resultat -------------------------------------------------------------------------------------


class RowOutcome(BaseModel):
    row: int
    personal_id_number: str
    period_month: date
    pensionable_salary_sek: Decimal
    kind: str
    outcome: Literal["valid", "deviation"]
    reason: ReasonCode | None
    message: str | None
    premium_preview_sek: Decimal | None = Field(
        default=None, description="Månadens premie med radens lön (för rättelse: den rättade premien)"
    )
    premium_issue: str | None = Field(default=None, description="Varför premie inte kan skapas för en giltig rad")


class MissingReport(BaseModel):
    personal_id_number: str
    policy_number: str
    message: str


class SalaryFileSummary(BaseModel):
    rows: int
    valid: int
    deviations: int
    missing: int
    corrections: int = Field(description="Giltiga rättelser bland raderna")
    salary_total_sek: Decimal = Field(description="Lönesumma för giltiga rader")
    premium_preview_sek: Decimal = Field(description="Förhandsberäknad premie för giltiga nya rader")
    by_reason: dict[str, int]


class SalaryFileView(BaseModel):
    file_id: str
    employer_org_number: str
    period_month: date
    file_reference: str
    received_date: date
    checksum: str
    status: Literal["received", "approved", "rejected"]
    review_digest: str = Field(description="Granskningens kontrollsumma – anges vid godkännande")
    summary: SalaryFileSummary
    rows: list[RowOutcome]
    missing: list[MissingReport]
    already_received: bool = Field(default=False, description="Filen var redan mottagen med samma innehåll")
    decided_by: str | None = None
    decided_at: str | None = None
    decision_note: str | None = None
    outcome: dict[str, Any] | None = None


def _view(file: SalaryFile, org: str, validation: dict, digest: str, *, already: bool = False) -> SalaryFileView:
    content_rows = file.content["rows"]
    return SalaryFileView(
        file_id=str(file.id), employer_org_number=org, period_month=file.period_month,
        file_reference=file.file_reference, received_date=file.received_date, checksum=file.checksum,
        status=file.status, review_digest=digest, summary=SalaryFileSummary(**validation["summary"]),
        rows=[RowOutcome(**{k: v for k, v in raw.items() if k != "corrects_version"}, **outcome)
              for raw, outcome in zip(content_rows, validation["rows"], strict=True)],
        missing=[MissingReport(**m) for m in validation["missing"]], already_received=already,
        decided_by=file.decided_by,
        decided_at=file.decided_at.isoformat(timespec="seconds") if file.decided_at else None,
        decision_note=file.decision_note, outcome=file.outcome,
    )


# --- import_salary_file ---------------------------------------------------------------------------


@operation(
    name="import_salary_file",
    description=(
        "Tar emot arbetsgivarens löneunderlagsfil för en period och validerar varje rad mot beståndet i "
        "betrodd kod: giltiga rader, avvikelser med skäl och saknade premiebetalande personer, med lönesumma "
        "och förhandsberäknad premie. Registrerar inga löner eller premier. Samma fil igen ger samma kvitto."
    ),
    kind=OperationKind.WRITE,
    rules=RULES,
    pii=True,
)
def import_salary_file(ctx: OperationContext, data: SalaryFileInput) -> SalaryFileView:
    session = ctx.require_session()
    today = common.today()
    employer = _employer(session, data.employer_org_number)
    period = data.period_month
    checksum = file_checksum(data.employer_org_number, period, data.file_reference, data.received_date, data.rows)
    if checksum != data.checksum:
        raise BlockedError("Filens kontrollsumma stämmer inte med innehållet – filen tas inte emot (skadad fil)")

    existing = session.scalar(
        select(SalaryFile).where(SalaryFile.employer_id == employer.id,
                                 SalaryFile.file_reference == data.file_reference)
    )
    if existing is not None:
        if existing.checksum != checksum:
            raise ConflictError(
                f"Filen {data.file_reference} är redan mottagen med annat innehåll – en korrigerad fil får en ny "
                "referens och rättelserader (P1-PREMIE-001 §4.1)"
            )
        return _view(existing, employer.org_number, existing.validation, existing.review_digest, already=True)

    if period < FIRST_OPERATIVE_PERIOD:
        raise BlockedError(
            f"{period:%Y-%m} ligger före första operativa premieperiod {FIRST_OPERATIVE_PERIOD:%Y-%m}. "
            "Juli–september 2026 är en märkt startlucka (B-046, PA1)"
        )
    if period > common.month_of(today):
        raise BlockedError(f"{period:%Y-%m} har inte kommit – bara utbetald lön rapporteras (PR-ITP1-014)")
    if data.received_date > today:
        raise BlockedError("Mottagningsdagen ligger i framtiden")
    if data.received_date < period:
        raise BlockedError("Mottagningsdagen ligger före filens period – lön rapporteras när den betalats ut")

    validation = _validate(session, employer, period, data.rows)
    digest = _review_digest(checksum, validation)
    file = SalaryFile(
        employer_id=employer.id, period_month=period, file_reference=data.file_reference,
        received_date=data.received_date,
        content=_canonical(data.employer_org_number, period, data.file_reference, data.received_date, data.rows),
        checksum=checksum, validation=validation, review_digest=digest, status="received",
        created_by=ctx.actor.id,
    )
    session.add(file)
    session.flush()
    return _view(file, employer.org_number, validation, digest)


# --- get_salary_file ------------------------------------------------------------------------------


class SalaryFileLookup(BaseModel):
    employer_org_number: str = Field(pattern=r"^\d{10}$")
    file_reference: str = Field(min_length=1, max_length=60)


@operation(
    name="get_salary_file",
    description=(
        "Visar en löneunderlagsfil med sammanställning, varje rads utfall och saknade rader. För en fil som "
        "väntar på granskning valideras den om mot dagens bestånd och får en aktuell granskningssumma."
    ),
    kind=OperationKind.READ,
    pii=True,
)
def get_salary_file(ctx: OperationContext, data: SalaryFileLookup) -> SalaryFileView:
    session = ctx.require_session()
    employer = _employer(session, data.employer_org_number)
    file = _file(session, employer, data.file_reference)
    if file.status != "received":
        return _view(file, employer.org_number, file.validation, file.review_digest)
    validation, digest = _current_validation(session, employer, file)
    return _view(file, employer.org_number, validation, digest)


# --- approve_salary_file --------------------------------------------------------------------------


class SalaryFileApproval(BaseModel):
    employer_org_number: str = Field(pattern=r"^\d{10}$")
    file_reference: str = Field(min_length=1, max_length=60)
    expected_digest: str = Field(pattern=r"^[a-f0-9]{64}$", description="review_digest från granskningen")


class CaseRef(BaseModel):
    case_number: str
    case_type: str
    reason: str
    row: int | None


class SalaryFileDecision(BaseModel):
    file_reference: str
    status: Literal["approved", "rejected"]
    salary_reports: int = Field(description="Registrerade löneunderlag")
    premium_rows: int = Field(description="Skapade premie- och rättelserader")
    premium_total_sek: Decimal = Field(description="Summa av skapade rader (+ fordran, − kredit)")
    cases: list[CaseRef]
    note: str


@operation(
    name="approve_salary_file",
    description=(
        "Godkänner en granskad löneunderlagsfil med granskningens kontrollsumma. I en transaktion registreras "
        "giltiga rader som löneunderlag, premieunderlag skapas (PR-ITP1-001, -015) och varje avvikande eller "
        "saknad rad blir ett ärende. Ändrat underlag sedan granskningen stoppar godkännandet."
    ),
    kind=OperationKind.WRITE,
    rules=RULES + ["PR-ITP1-001", "PR-ITP1-015", "PR-ITP1-019"],
    pii=True,
)
def approve_salary_file(ctx: OperationContext, data: SalaryFileApproval) -> SalaryFileDecision:
    session = ctx.require_session()
    employer = _employer(session, data.employer_org_number)
    file = _file(session, employer, data.file_reference, lock=True)
    if file.status != "received":
        raise ConflictError(f"Filen {file.file_reference} är redan {_STATUS_TEXT[file.status]}")
    validation, digest = _current_validation(session, employer, file)
    if digest != data.expected_digest:
        raise ConflictError(
            "Filens granskningsunderlag har ändrats sedan granskningen (beståndet eller registreringar har "
            "ändrats) – granska filen igen med get_salary_file"
        )

    rows = [SalaryFileRow.model_validate(r) for r in file.content["rows"]]
    reports, premium_ids, cases = [], [], []
    premium_total = Decimal("0.00")
    for row, outcome in zip(rows, validation["rows"], strict=True):
        number = outcome["row"]
        source_reference = f"{file.file_reference}:{number}"
        if outcome["outcome"] == "deviation":
            cases.append(_row_case(session, employer, file, row, number, outcome))
            continue
        report = register_salary_report(ctx, SalaryReportInput(
            personal_id_number=row.personal_id_number, employer_org_number=employer.org_number,
            period_month=row.period_month, pensionable_salary_sek=row.pensionable_salary_sek, kind=row.kind,
            corrects_version=row.corrects_version, source="employer", source_reference=source_reference,
            received_date=file.received_date,
        ))
        reports.append(report.report_id)
        try:
            premium = create_premium_from_salary_report(ctx, PremiumBasisInput(
                personal_id_number=row.personal_id_number, employer_org_number=employer.org_number,
                period_month=row.period_month,
            ))
        except (BlockedError, ConflictError, NotFoundError) as error:
            cases.append(_deviation_case(
                session, employer, file, reason="premium_blocked", row=number, month=row.period_month,
                message=f"Löneunderlaget är registrerat men premie kunde inte skapas: {error}",
                person=_person(session, row.personal_id_number), reported=_reported(row),
                source_reference=f"{source_reference}:premie",
            ))
            continue
        if premium.transaction_id is not None:
            premium_ids.append(premium.transaction_id)
            premium_total += premium.amount_sek
    for item in validation["missing"]:
        person = _person(session, item["personal_id_number"])
        policy = session.scalar(select(Policy).where(Policy.policy_number == item["policy_number"]))
        cases.append(_deviation_case(
            session, employer, file, reason="missing_report", row=None, month=file.period_month,
            message=item["message"], person=person, policy=policy, reported=None,
            source_reference=f"{file.file_reference}:saknas:{item['policy_number']}",
        ))

    file.status = "approved"
    file.validation, file.review_digest = validation, digest
    file.decided_by, file.decided_at = ctx.actor.id, datetime.now(UTC)
    file.outcome = {
        "salary_reports": reports, "premium_transactions": premium_ids,
        "premium_total_sek": str(premium_total), "cases": [c.model_dump() for c in cases],
    }
    return SalaryFileDecision(
        file_reference=file.file_reference, status="approved", salary_reports=len(reports),
        premium_rows=len(premium_ids), premium_total_sek=premium_total, cases=cases,
        note=(f"{len(reports)} löneunderlag och {len(premium_ids)} premierader registrerade; "
              f"{len(cases)} ärenden för avvikelser och saknade rader. Ingen faktura är skapad."),
    )


# --- reject_salary_file ---------------------------------------------------------------------------


class SalaryFileRejection(BaseModel):
    employer_org_number: str = Field(pattern=r"^\d{10}$")
    file_reference: str = Field(min_length=1, max_length=60)
    decision_note: str = Field(min_length=1, max_length=2000, description="Varför filen avslås")


@operation(
    name="reject_salary_file",
    description=(
        "Avslår en mottagen löneunderlagsfil med motivering. Ingenting registreras; ett ärende skapas för "
        "uppföljning med arbetsgivaren. Ingen extern sändning sker."
    ),
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-017"],
)
def reject_salary_file(ctx: OperationContext, data: SalaryFileRejection) -> SalaryFileDecision:
    session = ctx.require_session()
    employer = _employer(session, data.employer_org_number)
    file = _file(session, employer, data.file_reference, lock=True)
    if file.status != "received":
        raise ConflictError(f"Filen {file.file_reference} är redan {_STATUS_TEXT[file.status]}")
    file.status = "rejected"
    file.decided_by, file.decided_at, file.decision_note = ctx.actor.id, datetime.now(UTC), data.decision_note
    case = _deviation_case(
        session, employer, file, reason="file_rejected", row=None, month=file.period_month,
        message=f"Filen avslogs: {data.decision_note}. Följ upp med arbetsgivaren", person=None, reported=None,
        source_reference=file.file_reference,
    )
    file.outcome = {"cases": [case.model_dump()]}
    return SalaryFileDecision(
        file_reference=file.file_reference, status="rejected", salary_reports=0, premium_rows=0,
        premium_total_sek=Decimal("0.00"), cases=[case],
        note="Filen är avslagen. Ingenting registrerat; uppföljningsärende skapat.",
    )


# --- list_salary_files ----------------------------------------------------------------------------


class SalaryFileQuery(BaseModel):
    employer_org_number: str | None = Field(default=None, pattern=r"^\d{10}$", description="Arbetsgivare, valfri")
    period_month: date | None = Field(default=None, description="Filens period, valfri – dagen ignoreras")
    status: Literal["received", "approved", "rejected"] | None = Field(default=None, description="Valfri status")
    limit: int = Field(default=100, ge=1, le=500)


class SalaryFileListRow(BaseModel):
    employer_org_number: str
    employer_name: str
    period_month: date
    file_reference: str
    received_date: date
    status: Literal["received", "approved", "rejected"]
    summary: SalaryFileSummary = Field(
        description="Sammanställningen vid intaget eller beslutet; en väntande fil valideras om när den öppnas"
    )
    cases: int = Field(description="Ärenden som beslutet skapade")
    decided_by: str | None
    decided_at: str | None


class SalaryFileList(BaseModel):
    files: list[SalaryFileListRow]
    count: int
    missing_tables: list[str] = Field(
        description="Paket A:s tabeller som saknas i vald databas; listan är då tom (Lakebase före steg 8)"
    )


@operation(
    name="list_salary_files",
    description=(
        "Listar mottagna löneunderlagsfiler med arbetsgivare, period, status och sammanställning, senast "
        "mottagna först. Inga personuppgifter; filens rader visas med get_salary_file."
    ),
    kind=OperationKind.READ,
)
def list_salary_files(ctx: OperationContext, data: SalaryFileQuery) -> SalaryFileList:
    session = ctx.require_session()
    missing = common.missing_tables(session, common.PREMIUM_FLOW_TABLES)
    if missing:
        return SalaryFileList(files=[], count=0, missing_tables=missing)
    query = select(SalaryFile, Employer).join(Employer, Employer.id == SalaryFile.employer_id)
    if data.employer_org_number is not None:
        query = query.where(Employer.org_number == data.employer_org_number)
    if data.period_month is not None:
        query = query.where(SalaryFile.period_month == common.month_of(data.period_month))
    if data.status is not None:
        query = query.where(SalaryFile.status == data.status)
    query = query.order_by(SalaryFile.received_date.desc(), SalaryFile.created_at.desc(), SalaryFile.file_reference)
    rows = [
        SalaryFileListRow(
            employer_org_number=employer.org_number, employer_name=employer.name, period_month=file.period_month,
            file_reference=file.file_reference, received_date=file.received_date, status=file.status,
            summary=SalaryFileSummary(**file.validation["summary"]),
            cases=len((file.outcome or {}).get("cases", [])), decided_by=file.decided_by,
            decided_at=file.decided_at.isoformat(timespec="seconds") if file.decided_at else None,
        )
        for file, employer in session.execute(query.limit(data.limit)).all()
    ]
    return SalaryFileList(files=rows, count=len(rows), missing_tables=[])


# --- hjälpare -------------------------------------------------------------------------------------

_STATUS_TEXT = {"approved": "godkänd", "rejected": "avslagen", "received": "mottagen"}


def _employer(session, org_number: str) -> Employer:
    employer = session.scalar(select(Employer).where(Employer.org_number == org_number))
    if employer is None:
        raise NotFoundError(f"Ingen arbetsgivare med organisationsnummer {org_number}")
    return employer


def _file(session, employer, reference: str, *, lock: bool = False) -> SalaryFile:
    query = select(SalaryFile).where(SalaryFile.employer_id == employer.id, SalaryFile.file_reference == reference)
    file = session.scalar(query.with_for_update() if lock else query)
    if file is None:
        raise NotFoundError(f"Ingen löneunderlagsfil {reference} från arbetsgivaren")
    return file


def _current_validation(session, employer, file: SalaryFile) -> tuple[dict, str]:
    rows = [SalaryFileRow.model_validate(r) for r in file.content["rows"]]
    validation = _validate(session, employer, file.period_month, rows)
    return validation, _review_digest(file.checksum, validation)


def _person(session, pnr: str) -> InsuredPerson | None:
    return session.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == pnr))


def _reported(row: SalaryFileRow) -> dict[str, Any]:
    return {
        "personal_id_number": row.personal_id_number, "period_month": row.period_month.isoformat(),
        "pensionable_salary_sek": format(Decimal(row.pensionable_salary_sek).quantize(Decimal("0.01")), "f"),
        "kind": row.kind, "corrects_version": row.corrects_version,
    }


def _row_case(session, employer, file, row: SalaryFileRow, number: int, outcome: dict) -> CaseRef:
    person = _person(session, row.personal_id_number)
    if outcome["reason"] in AGENT_REASONS and person is not None and person.employer_id == employer.id:
        # Rättelse eller dubblett hos en känd person: ett löneunderlagsärende som agenten kan förbereda (§8)
        details = {
            "pensionable_salary_sek": format(Decimal(row.pensionable_salary_sek).quantize(Decimal("0.01")), "f"),
            "kind": row.kind, "corrects_version": row.corrects_version, "source": "employer",
        }
        case = _add_case(session, "salary_report", employer, file, person=person, policy=None,
                         month=row.period_month, source_reference=f"{file.file_reference}:{number}",
                         details=details)
        return CaseRef(case_number=case.case_number, case_type=case.case_type, reason=outcome["reason"], row=number)
    return _deviation_case(
        session, employer, file, reason=outcome["reason"], row=number, month=row.period_month,
        message=outcome["message"], person=person, reported=_reported(row),
        source_reference=f"{file.file_reference}:{number}",
    )


def _deviation_case(session, employer, file, *, reason, row, month, message, person, reported, source_reference,
                    policy=None) -> CaseRef:
    details = {"reason": reason, "message": message, "file_id": str(file.id),
               "file_reference": file.file_reference, "row": row, "reported": reported}
    case = _add_case(session, "salary_file_deviation", employer, file, person=person, policy=policy,
                     month=month, source_reference=source_reference, details=details)
    return CaseRef(case_number=case.case_number, case_type=case.case_type, reason=reason, row=row)


def _add_case(session, case_type, employer, file, *, person, policy, month, source_reference, details) -> Case:
    """Betrodd systemväg för filens ärenden (P1-PREMIE-001 §6): samma transaktion som godkännandet."""
    case = Case(
        id=uuid.uuid4(), case_number=_next_case_number(session), case_type=case_type, status="open",
        insured_person_id=person.id if person is not None else None,
        policy_id=policy.id if policy is not None else None, employer_id=employer.id, period_month=month,
        channel="employer_file", received_date=file.received_date, source_reference=source_reference,
        details=details, created_by=INTAKE_ACTOR,
    )
    session.add(case)
    session.flush()  # nästa ärendenummer ser raden
    return case
