"""Dödsfallsbesked, folkbokföringens avisering, dödsboets behörighet och avräkningens läsning (paket B steg 7, B-055).

Fem operationer, alla `HUMAN_ONLY` (PB12, Karls val Y11 2026-11-24). Agenter nekas även i operationen, och
de skrivande nekar också systemaktören – ett dödsfallsbeslut är en människas (PR-ITP1-031):

- `register_death_report` registrerar ett besked som misstänkt, eller direkt som verifierat med
  verifieringssätt och dokumentreferens (Y2). Ett verifierat besked sätter personens status till avliden.
- `verify_death_report` verifierar ett misstänkt besked, ändrar dödsdagen eller drar tillbaka beskedet –
  alltid som en ny version och bara före avräkningen (Y2).
- `import_death_notices` läser folkbokföringens avisering; varje besked registreras som misstänkt och samma fil
  igen ger ingen effekt (Y14).
- `register_estate_authority` registrerar dödsboets företrädare med behörighetshandling och konto (Y10).
- `get_death_settlement` visar personens besked, avräkning, anspråk, återföringar, återkrav och dödsbo med
  maskerat konto (Y11).

Själva avräkningen och arvsvinsten görs i månadsstängningen (`close_month`). Logiken ligger i
`services.death_reports`.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from models import InsuredPerson, PayoutAccount
from models.case import CASE_CHANNELS
from models.death import ESTATE_DOCUMENTS, ESTATE_ROLES, VERIFICATION_METHODS
from services import death_reports as dr
from services import payout_orders as po
from services.contract import OperationContext, OperationKind, operation
from services.errors import (
    AccessDeniedError,
    BlockedError,
    ConflictError,
    NotFoundError,
)
from services.operations import common
from services.operations.actuarial_analysis import JsonResult
from services.operations.payout_orders import _session as _order_session
from services.premium_month_inputs import HASH, Strict

RULES = ["PR-ITP1-010", "PR-ITP1-011", "PR-ITP1-031"]
Channel = Literal[CASE_CHANNELS]  # type: ignore[valid-type]
Method = Literal[VERIFICATION_METHODS]  # type: ignore[valid-type]
Role = Literal[ESTATE_ROLES]  # type: ignore[valid-type]
Document = Literal[ESTATE_DOCUMENTS]  # type: ignore[valid-type]
_NOTICE_ID = r"^[A-Za-z0-9._:/-]{1,64}$"


def _human(ctx: OperationContext, name: str) -> None:
    if ctx.actor.type != "human":
        raise AccessDeniedError("Dödsfall och dödsbo hanteras av en människa (PR-ITP1-031, PB12, Y11)",
                                operation=name, actor_id=ctx.actor.id)


def _no_agent(ctx: OperationContext, name: str) -> None:
    if ctx.actor.is_agent:
        raise AccessDeniedError("Dödsfallsavräkningen läses av människa eller betrodd systemkod (Y11)", operation=name,
                                actor_id=ctx.actor.id)


def _session(ctx: OperationContext):
    session = _order_session(ctx)
    if not dr.deaths_present(session):
        raise BlockedError("Dödsfallsbeskeden är inte införda i vald databas – migrate_death_reports.py först")
    return session


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except dr.DeathConflict as exc:
        raise ConflictError(str(exc)) from exc
    except dr.DeathServiceError as exc:
        raise BlockedError(str(exc)) from exc


def _report(row) -> dict:
    return {"report_id": str(row.id), "version": row.version, "status": row.status,
            "death_date": row.death_date.isoformat() if row.death_date else None,
            "reported_on": row.reported_on.isoformat(), "source": row.source,
            "verification_method": row.verification_method, "checksum": row.checksum}


# --- indata ---------------------------------------------------------------------------------------


class PersonRef(Strict):
    personal_id_number: str = Field(pattern=r"^\d{12}$", description="Den försäkrade, 12 siffror")


class ReportInput(PersonRef):
    status: Literal["suspected", "verified"] = Field(
        description="suspected: misstänkt, stoppar bara bankuppdragen; verified: verifierat med handling")
    death_date: date | None = Field(default=None, description="Dödsdagen (krävs för verifierat besked)")
    reported_on: date = Field(description="Rapportdagen: dagen källan lämnade beskedet")
    received_date: date = Field(description="Dagen beskedet togs emot")
    source: Literal["population_register", "relative", "employer", "case_handler", "other"] = Field(
        description="Varifrån beskedet kom")
    source_ref: str = Field(min_length=3, max_length=200, description="Källans referens, t.ex. aviseringens id")
    verification_method: Method | None = Field(default=None, description="Hur dödsfallet verifierats")
    document_ref: str | None = Field(default=None, min_length=3, max_length=200,
                                     description="Handlingen som verifierar dödsfallet")
    channel: Channel = Field(description="Kanalen beskedet kom in genom")


class VerifyInput(PersonRef):
    action: Literal["verify", "change_date", "withdraw"] = Field(
        description="verify: verifiera ett misstänkt besked; change_date: ny dödsdag; withdraw: dra tillbaka")
    death_date: date | None = Field(default=None, description="Dödsdagen (verify, change_date)")
    verification_method: Method | None = Field(default=None, description="Hur dödsfallet verifierats")
    document_ref: str | None = Field(default=None, min_length=3, max_length=200,
                                     description="Handlingen som verifierar dödsfallet")
    received_date: date = Field(description="Dagen uppgiften togs emot")
    note: str | None = Field(default=None, min_length=3, max_length=500,
                             description="Anteckning (krävs vid tillbakadragning)")
    channel: Channel = Field(description="Kanalen uppgiften kom in genom")


class NoticeInput(BaseModel):
    notice_id: str = Field(pattern=_NOTICE_ID, description="Aviseringens besked-id")
    personal_id_number: str = Field(pattern=r"^\d{12}$")
    death_date: date
    notified_on: date = Field(description="Aviseringsdagen")


class NoticeFileInput(Strict):
    source_system: str = Field(default=dr.POPULATION_SOURCE, pattern=r"^[a-z0-9-]{1,40}$",
                               description="Folkbokföringens källsystem")
    file_reference: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9._/-]+$")
    checksum: str = Field(pattern=HASH, description="SHA-256 över filens innehåll (notice_file_checksum)")
    notices: list[NoticeInput] = Field(min_length=1, max_length=10000)


class EstateInput(PersonRef):
    role: Role = Field(description="estate_member: dödsbodelägare med fullmakt; estate_administrator: "
                                   "boutredningsman; representative: ombud")
    representative: str = Field(min_length=2, max_length=200, description="Företrädarens namn eller beteckning")
    document_kind: Document = Field(description="Behörighetshandlingen")
    document_ref: str = Field(min_length=3, max_length=200, description="Handlingens referens")
    verified: bool = Field(description="Behörigheten är prövad mot handlingen")
    verification_method: str | None = Field(default=None, min_length=3, max_length=40)
    verification_ref: str | None = Field(default=None, min_length=3, max_length=200)
    account_id: str = Field(min_length=36, max_length=36,
                            description="Kontoversionen ur register_payout_account på den avlidnes person")
    received_date: date = Field(description="Dagen handlingen togs emot")
    channel: Channel = Field(description="Kanalen uppgiften kom in genom")


# --- operationer ----------------------------------------------------------------------------------


@operation(
    name="register_death_report",
    description="Registrerar ett dödsfallsbesked som misstänkt (stoppar bara bankuppdragen) eller som verifierat "
                "med dödsdag, verifieringssätt och dokumentreferens (personen blir avliden; avräkningen sker i "
                "nästa månadsstängning). Öppnar eller fyller på ärendet death_report. Samma besked igen ger ingen "
                "ny version.",
    kind=OperationKind.WRITE,
    rules=RULES,
    pii=True,
)
def register_death_report(ctx: OperationContext, data: ReportInput) -> JsonResult:
    _human(ctx, "register_death_report")
    session = _session(ctx)
    person = common.lock_person(session, data.personal_id_number)
    row, created = _call(dr.register_report, session, person, status=data.status, death_date=data.death_date,
                         reported_on=data.reported_on, received=data.received_date, source=data.source,
                         source_ref=data.source_ref, channel=data.channel, actor=ctx.actor.id, today=common.today(),
                         method=data.verification_method, document_ref=data.document_ref)
    return JsonResult(payload={"created": created, **_report(row), "person_status": person.status})


@operation(
    name="verify_death_report",
    description="Verifierar ett misstänkt dödsfallsbesked, ändrar dödsdagen eller drar tillbaka beskedet – som en "
                "ny version och bara innan personens delar är avräknade. Ett tillbakadraget verifierat besked "
                "återställer personens tidigare status.",
    kind=OperationKind.WRITE,
    rules=RULES,
    pii=True,
)
def verify_death_report(ctx: OperationContext, data: VerifyInput) -> JsonResult:
    _human(ctx, "verify_death_report")
    session = _session(ctx)
    person = common.lock_person(session, data.personal_id_number)
    row = _call(dr.verify_report, session, person, data.action, received=data.received_date, channel=data.channel,
                actor=ctx.actor.id, today=common.today(), death_date=data.death_date,
                method=data.verification_method, document_ref=data.document_ref, note=data.note)
    return JsonResult(payload={**_report(row), "person_status": person.status})


@operation(
    name="import_death_notices",
    description="Läser folkbokföringens avisering om dödsfall: varje besked registreras som misstänkt och "
                "verifieras av handläggaren. Samma besked igen ger ingen effekt; samma besked-id med annat "
                "innehåll ger konflikt för hela filen. Okända personnummer redovisas.",
    kind=OperationKind.WRITE,
    rules=RULES,
    pii=True,
)
def import_death_notices(ctx: OperationContext, data: NoticeFileInput) -> JsonResult:
    _human(ctx, "import_death_notices")
    session = _session(ctx)
    notices = [n.model_dump() for n in data.notices]
    result = _call(dr.import_notices, session, data.source_system, data.file_reference, notices, data.checksum,
                   common.today(), ctx.actor.id)
    return JsonResult(payload=result)


@operation(
    name="register_estate_authority",
    description="Registrerar dödsboets företrädare med behörighetshandling, verifiering och konto (registrerat "
                "efter dödsdagen på den avlidnes person). Dödsboet får bara anspråk med rätt senast dödsmånaden, "
                "när delarna är avräknade och behörigheten verifierad.",
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-010", "PR-ITP1-026", "PR-ITP1-031"],
    pii=True,
)
def register_estate_authority(ctx: OperationContext, data: EstateInput) -> JsonResult:
    _human(ctx, "register_estate_authority")
    session = _session(ctx)
    person = common.lock_person(session, data.personal_id_number)
    row, created = _call(dr.register_estate, session, person, role=data.role, representative=data.representative,
                         document_kind=data.document_kind, document_ref=data.document_ref, verified=data.verified,
                         method=data.verification_method, verification_ref=data.verification_ref,
                         account_id=uuid.UUID(data.account_id), received=data.received_date, channel=data.channel,
                         actor=ctx.actor.id, today=common.today())
    return JsonResult(payload={"created": created, "estate_id": str(row.id), "version": row.version,
                               "role": row.role, "verified": row.verified, "decided_by": row.decided_by,
                               "account": po.account_view(session.get(PayoutAccount, row.account_id))})


@operation(
    name="get_death_settlement",
    description="Visar personens dödsfallsbesked i alla versioner, avräkningen per uttagsdel, anspråken med "
                "återföringar, återkravsärenden och dödsboet med maskerat konto.",
    kind=OperationKind.READ,
    rules=RULES,
    pii=True,
)
def get_death_settlement(ctx: OperationContext, data: PersonRef) -> JsonResult:
    _no_agent(ctx, "get_death_settlement")
    session = _session(ctx)
    person = session.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == data.personal_id_number))
    if person is None:
        raise NotFoundError("Ingen försäkrad med det personnumret")
    return JsonResult(payload=_call(dr.settlement_view, session, person, po.mask))
