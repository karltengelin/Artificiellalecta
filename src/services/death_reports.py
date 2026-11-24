"""Dödsfallsbesked, dödsboets behörighet och läsningar för dödsfallsavräkningen (paket B steg 7, B-055, Y1–Y14).

Designstoppet P1-PENSION-001 §9.1 (PB9, PB10). Månadsstängningen (`services.month_close`) avräknar delarna
och fördelar arvsvinsten i PR-ITP1-020 steg 6–7; här finns beskeden, dödsboet och de läsningar som
stängningen och bankfilen använder.

**Besked (Y2).** `register_report` sparar ett besked som misstänkt, eller direkt som verifierat med
verifieringssätt och dokumentreferens. Ett verifierat besked kräver dödsdag, och dödsdagen ligger senast på
rapportdagen. `verify_report` verifierar ett misstänkt besked, ändrar dödsdagen som en ny version eller drar
tillbaka beskedet. Vid verifieringen sätts personens status till `deceased` och den tidigare statusen sparas i
versionen; ett tillbakadraget besked återställer den. När personens delar är avräknade kan beskedet inte
längre ändras – en sen ändring är en manuell rättelse i ett senare steg (PR-ITP1-019 p. 6). Varje registrering
öppnar ett ärende `death_report` eller fyller på det som finns.

**Misstänkt dödsfall (Y3).** Ett öppet misstänkt besked stoppar bara personens bankuppdrag; stängningen
påverkas inte.

**Dödsboet (Y10).** `register_estate` sparar dödsboets företrädare med behörighetshandling, verifiering och
en kontoversion i `payout_accounts`, registrerad efter dödsdagen. Dödsboet får bara anspråk med rätt senast
dödsmånaden, när delarna är avräknade och behörigheten är verifierad.

**Folkbokföringens avisering (Y14).** `import_notices` läser en fil med besked som misstänkta; samma fil igen
ger ingen ny effekt.

**Utan steg 7:s migration** (`deaths_present` nej) finns inget av detta, och stängningen beter sig som i steg 6.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from models import (
    Case,
    DeathReport,
    DeathSettlement,
    EstateAuthority,
    InsuredPerson,
    LedgerBatch,
    PayoutAccount,
    PayoutPart,
    PensionClaim,
    PensionClaimReversal,
    Policy,
    PolicyBenefit,
)
from models.death import (
    ESTATE_DOCUMENTS,
    ESTATE_ROLES,
    REPORT_SOURCES,
    VERIFICATION_METHODS,
)
from services import capital_ledger as cl
from services import payout_plans as pl
from utils.checksums import checksum as content_checksum

METHOD = "death-reports-1"
DEATH_TABLES = (DeathReport.__tablename__, DeathSettlement.__tablename__, PensionClaimReversal.__tablename__,
                EstateAuthority.__tablename__)
#: Folkbokföringens simulerade avisering (Y14)
POPULATION_SOURCE = "population-register-sim"
POOL = "inheritance_pool"
REVERSAL = "death_reversal"
#: Riskgrunden för arvsvinsten (PR-ITP1-011, A4)
RISK_FAMILY = "SIM-R"
ZERO = Decimal("0.00")
#: Ärendetexterna (Y5, Y7)
CASE_TEXT = {
    "death_report": "Dödsfallsbesked – verifiering, avräkning, premie efter dödsfallet och dödsbo (PR-ITP1-010)",
    "death_recovery": "Utfört anspråk efter dödsmånaden – återkravsprövning; ingen kvittning och ingen negativ "
                      "arvsvinst (PR-ITP1-010, -031)",
    "inheritance_pool": "Arvsvinstpoolen står kvar – inga mottagare, ΣE = 0 eller ingen antagen riskgrund "
                        "(PR-ITP1-011)",
}


class DeathServiceError(ValueError):
    """Beskedet, dödsboet eller avräkningen kan inte registreras eller läsas."""


class DeathConflict(DeathServiceError):
    """Ett besked krockar med ett tidigare, t.ex. samma besked-id med annat innehåll."""


def deaths_present(session: Session) -> bool:
    """Är steg 7:s migration körd (besked, avräkningar, återföringar och dödsbo)?"""
    names = set(inspect(session.connection()).get_table_names())
    return set(DEATH_TABLES) <= names


def _require(session: Session) -> None:
    if not deaths_present(session):
        raise DeathServiceError("Dödsfallsbeskeden är inte införda i vald databas – migrate_death_reports.py först")


def _stable(*parts) -> uuid.UUID:
    return cl.stable_id("death", *[str(p) for p in parts])


# --- läsningar för stängningen och bankfilen ------------------------------------------------------


def current_reports(session: Session, person_ids=None) -> dict[uuid.UUID, DeathReport]:
    """Gällande (senaste) version av beskedet per person."""
    query = select(DeathReport).order_by(DeathReport.insured_person_id, DeathReport.version)
    if person_ids is not None:
        person_ids = list(person_ids)
        if not person_ids:
            return {}
        query = query.where(DeathReport.insured_person_id.in_(person_ids))
    out: dict[uuid.UUID, DeathReport] = {}
    for row in session.scalars(query):
        out[row.insured_person_id] = row
    return out


def current_report(session: Session, person_id: uuid.UUID) -> DeathReport | None:
    return session.scalar(select(DeathReport).where(DeathReport.insured_person_id == person_id)
                          .order_by(DeathReport.version.desc()).limit(1))


def persons_of_parts(session: Session, part_ids) -> dict[uuid.UUID, uuid.UUID]:
    """Uttagsdel → ägaren."""
    part_ids = list(part_ids)
    out = {}
    for start in range(0, len(part_ids), 5000):
        out.update(dict(session.execute(
            select(PayoutPart.id, Policy.insured_person_id)
            .join(PolicyBenefit, PolicyBenefit.id == PayoutPart.benefit_id)
            .join(Policy, Policy.id == PolicyBenefit.policy_id)
            .where(PayoutPart.id.in_(part_ids[start:start + 5000]))).all()))
    return out


def parts_of_persons(session: Session, person_ids) -> dict[uuid.UUID, uuid.UUID]:
    """Uttagsdel → person för personernas alla delar."""
    person_ids = list(person_ids)
    out = {}
    for start in range(0, len(person_ids), 5000):
        out.update(dict(session.execute(
            select(PayoutPart.id, Policy.insured_person_id)
            .join(PolicyBenefit, PolicyBenefit.id == PayoutPart.benefit_id)
            .join(Policy, Policy.id == PolicyBenefit.policy_id)
            .where(Policy.insured_person_id.in_(person_ids[start:start + 5000]))).all()))
    return out


def settlements(session: Session, part_ids=None) -> dict[uuid.UUID, tuple[DeathSettlement, date]]:
    """Avräknade delar: del → (avräkning, stängningens månadsslut)."""
    query = select(DeathSettlement, LedgerBatch.period_end).join(LedgerBatch, LedgerBatch.id == DeathSettlement.batch_id)
    if part_ids is not None:
        part_ids = list(part_ids)
        if not part_ids:
            return {}
        query = query.where(DeathSettlement.payout_part_id.in_(part_ids))
    return {s.payout_part_id: (s, end) for s, end in session.execute(query)}


def person_settled(session: Session, person_id: uuid.UUID) -> bool:
    """Är alla personens delar avräknade (Y10)?"""
    parts = parts_of_persons(session, [person_id])
    return bool(parts) and set(settlements(session, parts)) == set(parts)


def reversed_claims(session: Session, claim_ids=None) -> set[uuid.UUID]:
    query = select(PensionClaimReversal.claim_id)
    if claim_ids is not None:
        claim_ids = list(claim_ids)
        if not claim_ids:
            return set()
        query = query.where(PensionClaimReversal.claim_id.in_(claim_ids))
    return set(session.scalars(query))


def current_estate(session: Session, person_id: uuid.UUID) -> EstateAuthority | None:
    return session.scalar(select(EstateAuthority).where(EstateAuthority.insured_person_id == person_id)
                          .order_by(EstateAuthority.version.desc()).limit(1))


@dataclass
class DeathMonth:
    """Dödsfallen som gäller en stängning: gällande besked, avräknade delar och delar som avräknas nu (Y6)."""

    month: date
    end: date
    #: Gällande besked per person (alla lägen)
    reports: dict[uuid.UUID, DeathReport]
    #: Delar avräknade i en tidigare stängning
    settled: set[uuid.UUID]
    #: Delar som avräknas i månaden: del → gällande verifierat besked med dödsdag senast månadens slut
    settling: dict[uuid.UUID, DeathReport]
    #: Del → person för de avlidnas delar
    owner: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    #: Avräkningen för varje del avräknad i en tidigare stängning
    settled_rows: dict[uuid.UUID, DeathSettlement] = field(default_factory=dict)

    @property
    def parts(self) -> set[uuid.UUID]:
        return self.settled | set(self.settling)

    def death_month(self, part: uuid.UUID) -> date:
        if part in self.settling:
            return self.settling[part].death_date.replace(day=1)
        return self.settled_rows[part].death_month

    def report_id(self, part: uuid.UUID) -> uuid.UUID:
        return self.settling[part].id if part in self.settling else self.settled_rows[part].report_id

    def without_right(self) -> set[uuid.UUID]:
        """Delar utan rätt i månaden: avräknade, och de som avräknas nu med dödsmånad före månaden (Y4)."""
        return self.settled | {p for p in self.settling if self.death_month(p) < self.month}

    def verified_by_end(self, person_id: uuid.UUID) -> bool:
        r = self.reports.get(person_id)
        return r is not None and r.status == "verified" and r.death_date <= self.end

    @property
    def suspected(self) -> list[uuid.UUID]:
        return sorted((p for p, r in self.reports.items() if r.status == "suspected"), key=str)


def death_month(session: Session, month: date, end: date) -> DeathMonth:
    """Läser dödsfallen för stängningen av `month` (Y6). Delar avräknade i månadens egen stängning räknas som
    delar som avräknas nu, så att en ny granskning eller rättelse ser samma läge som bokningen."""
    reports = current_reports(session)
    verified = {p: r for p, r in reports.items() if r.status == "verified" and r.death_date <= end}
    owner = parts_of_persons(session, verified)
    done = settlements(session)
    settled_rows = {part: row for part, (row, period_end) in done.items() if period_end < end}
    settled = set(settled_rows)
    settling = {part: verified[person] for part, person in owner.items() if part not in settled}
    return DeathMonth(month, end, reports, settled, settling, owner, settled_rows)


# --- ärendet death_report -------------------------------------------------------------------------


def report_case(session: Session, person_id: uuid.UUID, event: dict, *, channel: str, received: date,
                actor: str) -> Case:
    """Öppnar ärendet `death_report` för personen eller fyller på det öppna med händelsen (Y2)."""
    case = session.scalar(select(Case).where(Case.case_type == "death_report", Case.insured_person_id == person_id,
                                             Case.status != "closed").order_by(Case.created_at).limit(1))
    if case is not None:
        case.details = {**(case.details or {}), "events": [*(case.details or {}).get("events", []), event]}
    else:
        case = Case(id=uuid.uuid4(), case_number=pl.next_case_number(session), case_type="death_report",
                    status="open", insured_person_id=person_id, channel=channel, received_date=received,
                    source_reference=f"death_report:{event.get('report_id', '')}",
                    details={"reason": "death_report", "text": CASE_TEXT["death_report"], "events": [event]},
                    created_by=actor)
        session.add(case)
    session.flush()
    return case


# --- besked (Y2, Y14) -----------------------------------------------------------------------------


def _report_content(person_id, status, death_date, reported_on, source, source_ref, method, document_ref,
                    source_system, notice_id) -> dict:
    return {"method": METHOD, "rules": ["PR-ITP1-010"], "person": str(person_id), "status": status,
            "death_date": death_date.isoformat() if death_date else None, "reported_on": reported_on.isoformat(),
            "source": source, "source_ref": source_ref, "verification_method": method, "document_ref": document_ref,
            "source_system": source_system, "notice_id": notice_id}


def _check_dates(death_date: date | None, reported_on: date, received: date, today: date) -> None:
    if death_date is not None and death_date > reported_on:
        raise DeathServiceError("Dödsdagen kan inte ligga efter rapportdagen (PR-ITP1-010)")
    if reported_on > received:
        raise DeathServiceError("Rapportdagen kan inte ligga efter mottagningsdagen")
    if received > today:
        raise DeathServiceError("Mottagningsdagen ligger i framtiden")


def _not_settled(session: Session, person_id: uuid.UUID) -> None:
    parts = parts_of_persons(session, [person_id])
    if settlements(session, parts):
        raise DeathServiceError("Personens delar är avräknade – ett ändrat eller tillbakadraget besked är en manuell "
                                "rättelse (PR-ITP1-019 p. 6) som byggs i ett senare steg")


def _new_version(session: Session, person: InsuredPerson, current: DeathReport | None, *, status: str,
                 death_date: date | None, reported_on: date, received: date, source: str, source_ref: str,
                 channel: str, method: str | None, document_ref: str | None, previous_status: str | None,
                 source_system: str | None, notice_id: str | None, actor: str, content: dict) -> DeathReport:
    version = current.version + 1 if current else 1
    row = DeathReport(id=_stable("report", person.id, version), insured_person_id=person.id, version=version,
                      supersedes_id=current.id if current else None, status=status, death_date=death_date,
                      reported_on=reported_on, received_date=received, source=source, source_ref=source_ref,
                      source_system=source_system, notice_id=notice_id, channel=channel,
                      verification_method=method, document_ref=document_ref, previous_status=previous_status,
                      content=content, checksum=content_checksum(content), created_by=actor)
    session.add(row)
    session.flush()
    return row


def _event(row: DeathReport, action: str, note: str | None = None) -> dict:
    return {"action": action, "report_id": str(row.id), "version": row.version, "status": row.status,
            "death_date": row.death_date.isoformat() if row.death_date else None,
            "reported_on": row.reported_on.isoformat(), "source": row.source, "source_ref": row.source_ref,
            "verification_method": row.verification_method, "document_ref": row.document_ref,
            "created_by": row.created_by, **({"note": note} if note else {})}


def register_report(session: Session, person: InsuredPerson, *, status: str, death_date: date | None,
                    reported_on: date, received: date, source: str, source_ref: str, channel: str, actor: str,
                    today: date, method: str | None = None, document_ref: str | None = None,
                    source_system: str | None = None, notice_id: str | None = None) -> tuple[DeathReport, bool]:
    """Registrerar ett dödsfallsbesked som misstänkt eller verifierat (Y2). Samma besked igen: ingen ny version."""
    _require(session)
    if status not in ("suspected", "verified"):
        raise DeathServiceError("Ett nytt besked är misstänkt eller verifierat")
    if source not in REPORT_SOURCES:
        raise DeathServiceError(f"Okänd källa {source}")
    if status == "verified":
        if death_date is None or method not in VERIFICATION_METHODS or not document_ref:
            raise DeathServiceError("Ett verifierat besked kräver dödsdag, verifieringssätt och dokumentreferens "
                                    "(PR-ITP1-010)")
    else:
        method, document_ref = None, None
    _check_dates(death_date, reported_on, received, today)
    content = _report_content(person.id, status, death_date, reported_on, source, source_ref, method, document_ref,
                              source_system, notice_id)
    if notice_id is not None:
        existing = session.scalar(select(DeathReport).where(DeathReport.source_system == source_system,
                                                            DeathReport.notice_id == notice_id))
        if existing is not None:
            if existing.checksum != content_checksum(content):
                raise DeathConflict(f"Beskedet {notice_id} från {source_system} är redan registrerat med annat innehåll")
            return existing, False
    current = current_report(session, person.id)
    if current is not None and current.status != "withdrawn":
        if current.checksum == content_checksum(content):
            return current, False
        if current.status == "verified":
            if status == "suspected" or death_date == current.death_date:
                report_case(session, person.id, {**_event(current, "duplicate"), "source_ref": source_ref,
                                                 "received": received.isoformat()},
                            channel=channel, received=received, actor=actor)
                return current, False
            raise DeathServiceError("Personen har ett verifierat besked – ändra dödsdagen med verify_death_report")
    _not_settled(session, person.id)
    previous = person.status if status == "verified" else None
    row = _new_version(session, person, current, status=status, death_date=death_date, reported_on=reported_on,
                       received=received, source=source, source_ref=source_ref, channel=channel, method=method,
                       document_ref=document_ref, previous_status=previous, source_system=source_system,
                       notice_id=notice_id, actor=actor, content=content)
    if status == "verified":
        person.status = "deceased"
        session.flush()
    report_case(session, person.id, _event(row, "registered"), channel=channel, received=received, actor=actor)
    return row, True


def verify_report(session: Session, person: InsuredPerson, action: str, *, received: date, channel: str, actor: str,
                  today: date, death_date: date | None = None, method: str | None = None,
                  document_ref: str | None = None, note: str | None = None) -> DeathReport:
    """Verifierar ett misstänkt besked, ändrar dödsdagen eller drar tillbaka beskedet (Y2) – en ny version."""
    _require(session)
    current = current_report(session, person.id)
    if current is None or current.status == "withdrawn":
        raise DeathServiceError("Personen har inget öppet dödsfallsbesked")
    _not_settled(session, person.id)
    if action == "verify":
        if current.status != "suspected":
            raise DeathServiceError("Beskedet är redan verifierat – ändra dödsdagen med action change_date")
        death_date = death_date or current.death_date
        if death_date is None or method not in VERIFICATION_METHODS or not document_ref:
            raise DeathServiceError("Verifieringen kräver dödsdag, verifieringssätt och dokumentreferens (PR-ITP1-010)")
        status, previous = "verified", person.status
    elif action == "change_date":
        if current.status != "verified":
            raise DeathServiceError("Bara ett verifierat besked får ny dödsdag – verifiera beskedet först")
        if death_date is None or death_date == current.death_date:
            raise DeathServiceError("Ange den nya dödsdagen")
        method = method or current.verification_method
        document_ref = document_ref or current.document_ref
        if method not in VERIFICATION_METHODS:
            raise DeathServiceError(f"Okänt verifieringssätt {method}")
        status, previous = "verified", current.previous_status
    elif action == "withdraw":
        if not note:
            raise DeathServiceError("Ett tillbakadraget besked kräver en anteckning om varför")
        status, previous = "withdrawn", current.previous_status
        death_date, method, document_ref = current.death_date, None, None
    else:
        raise DeathServiceError(f"Okänd åtgärd {action}")
    _check_dates(death_date, current.reported_on, max(received, current.received_date), today)
    content = {**_report_content(person.id, status, death_date, current.reported_on, current.source,
                                 current.source_ref, method, document_ref, None, None),
               "action": action, "note": note, "supersedes": str(current.id)}
    row = _new_version(session, person, current, status=status, death_date=death_date,
                       reported_on=current.reported_on, received=max(received, current.received_date),
                       source=current.source, source_ref=current.source_ref, channel=channel, method=method,
                       document_ref=document_ref, previous_status=previous, source_system=None, notice_id=None,
                       actor=actor, content=content)
    if status == "verified":
        person.status = "deceased"
    elif current.status == "verified":  # tillbakadraget före avräkningen: den sparade statusen återställs
        person.status = current.previous_status or "active"
    session.flush()
    report_case(session, person.id, _event(row, action, note), channel=channel, received=received, actor=actor)
    return row


def notice_file_checksum(source_system: str, file_reference: str, notices: list[dict]) -> str:
    """Kontrollsumman över aviseringsfilens innehåll (samma mönster som bankens kvittofil)."""
    return content_checksum({"source_system": source_system, "file_reference": file_reference,
                             "notices": [{"notice_id": n["notice_id"], "personal_id_number": n["personal_id_number"],
                                          "death_date": str(n["death_date"]), "notified_on": str(n["notified_on"])}
                                         for n in notices]})


def import_notices(session: Session, source_system: str, file_reference: str, notices: list[dict],
                   file_checksum: str, today: date, actor: str) -> dict:
    """Läser folkbokföringens avisering: varje besked registreras som misstänkt (Y14). Idempotent per besked-id."""
    _require(session)
    if notice_file_checksum(source_system, file_reference, notices) != file_checksum:
        raise DeathServiceError("Aviseringsfilens kontrollsumma stämmer inte med innehållet – filen läses inte")
    ids = [n["notice_id"] for n in notices]
    if len(set(ids)) != len(ids):
        raise DeathServiceError("Samma besked-id förekommer flera gånger i filen")
    outcomes = []
    for n in notices:
        person = session.scalar(select(InsuredPerson).where(
            InsuredPerson.personal_id_number == n["personal_id_number"]).with_for_update())
        if person is None:
            outcomes.append({"notice_id": n["notice_id"], "status": "unknown_person"})
            continue
        row, created = register_report(session, person, status="suspected", death_date=n["death_date"],
                                       reported_on=n["notified_on"], received=today, source="population_register",
                                       source_ref=f"{file_reference}:{n['notice_id']}", channel="system",
                                       actor=actor, today=today, source_system=source_system,
                                       notice_id=n["notice_id"])
        outcomes.append({"notice_id": n["notice_id"], "status": "new" if created else "already_received",
                         "report_id": str(row.id), "report_status": row.status})
    return {"file_reference": file_reference, "notices": len(notices),
            "new": sum(1 for o in outcomes if o["status"] == "new"),
            "already_received": sum(1 for o in outcomes if o["status"] == "already_received"),
            "unknown_persons": sum(1 for o in outcomes if o["status"] == "unknown_person"), "outcomes": outcomes}


# --- dödsboet (Y10) -------------------------------------------------------------------------------


def register_estate(session: Session, person: InsuredPerson, *, role: str, representative: str, document_kind: str,
                    document_ref: str, verified: bool, method: str | None, verification_ref: str | None,
                    account_id: uuid.UUID, received: date, channel: str, actor: str,
                    today: date) -> tuple[EstateAuthority, bool]:
    """Ny version av dödsboets behörighet och konto (Y10). Samma uppgift igen: ingen ny version."""
    _require(session)
    report = current_report(session, person.id)
    if report is None or report.status != "verified":
        raise DeathServiceError("Dödsboets behörighet kräver ett verifierat dödsfallsbesked")
    if role not in ESTATE_ROLES or document_kind not in ESTATE_DOCUMENTS:
        raise DeathServiceError("Okänd roll eller behörighetshandling")
    if verified and not (method and verification_ref):
        raise DeathServiceError("En verifierad behörighet kräver verifieringssätt och referens")
    if received < report.death_date or received > today:
        raise DeathServiceError("Behörigheten tas emot efter dödsdagen och senast i dag")
    account = session.get(PayoutAccount, account_id)
    if account is None or account.insured_person_id != person.id:
        raise DeathServiceError("Kontoversionen finns inte på den avlidnes person – register_payout_account först")
    if account.received_date < report.death_date:
        raise DeathServiceError("Dödsboets konto registreras efter dödsdagen (Y10)")
    if verified and not account.verified:
        raise DeathServiceError("Dödsboets konto är inte verifierat mot behörighetshandlingen")
    content = {"method": METHOD, "rules": ["PR-ITP1-010", "PR-ITP1-026"], "person": str(person.id),
               "report": str(report.id), "role": role, "representative": representative,
               "document_kind": document_kind, "document_ref": document_ref, "verified": verified,
               "verification_method": method if verified else None,
               "verification_ref": verification_ref if verified else None, "account": str(account.id)}
    digest = content_checksum(content)
    latest = current_estate(session, person.id)
    if latest is not None and latest.checksum == digest:
        return latest, False
    version = latest.version + 1 if latest else 1
    row = EstateAuthority(id=_stable("estate", person.id, version), insured_person_id=person.id, version=version,
                          supersedes_id=latest.id if latest else None, report_id=report.id, role=role,
                          representative=representative, document_kind=document_kind, document_ref=document_ref,
                          verified=verified, verification_method=content["verification_method"],
                          verification_ref=content["verification_ref"], account_id=account.id, decided_by=actor,
                          received_date=received, channel=channel, checksum=digest, created_by=actor)
    session.add(row)
    session.flush()
    report_case(session, person.id, {"action": "estate_authority", "estate_id": str(row.id), "version": version,
                                     "role": role, "verified": verified, "account_id": str(account.id),
                                     "created_by": actor}, channel=channel, received=received, actor=actor)
    return row, True


def estate_for_payment(session: Session, person_id: uuid.UUID) -> tuple[EstateAuthority | None, PayoutAccount | None]:
    """Dödsboets gällande behörighet och konto om båda är verifierade, annars (None, None)."""
    estate = current_estate(session, person_id)
    if estate is None or not estate.verified:
        return None, None
    account = session.get(PayoutAccount, estate.account_id)
    if account is None or not account.verified:
        return None, None
    return estate, account


# --- läsning (Y11) --------------------------------------------------------------------------------


def settlement_view(session: Session, person: InsuredPerson, mask) -> dict:
    """Personens besked, avräkning, anspråk, återföringar, återkrav och dödsbo med maskerat konto."""
    _require(session)
    reports = session.scalars(select(DeathReport).where(DeathReport.insured_person_id == person.id)
                              .order_by(DeathReport.version)).all()
    parts = parts_of_persons(session, [person.id])
    done = settlements(session, parts)
    claims = session.scalars(select(PensionClaim).where(PensionClaim.payout_part_id.in_(list(parts)))
                             .order_by(PensionClaim.right_month, PensionClaim.payout_part_id)).all() if parts else []
    reversals = {r.claim_id: r for r in session.scalars(select(PensionClaimReversal).where(
        PensionClaimReversal.claim_id.in_([c.id for c in claims])))} if claims else {}
    recoveries = session.scalars(select(Case).where(Case.case_type == "death_recovery",
                                                    Case.insured_person_id == person.id)
                                 .order_by(Case.created_at)).all()
    estate = current_estate(session, person.id)
    account = session.get(PayoutAccount, estate.account_id) if estate else None
    return {
        "person_id": str(person.id), "status": person.status,
        "reports": [{"report_id": str(r.id), "version": r.version, "status": r.status,
                     "death_date": r.death_date.isoformat() if r.death_date else None,
                     "reported_on": r.reported_on.isoformat(), "received_date": r.received_date.isoformat(),
                     "source": r.source, "source_ref": r.source_ref, "verification_method": r.verification_method,
                     "document_ref": r.document_ref, "created_by": r.created_by} for r in reports],
        "settlements": [{"payout_part_id": str(p), "death_month": s.death_month.isoformat(), "period_end": end.isoformat(),
                         "capital_to_pool_sek": str(s.capital_to_pool_sek), "reversed_claims": s.reversed_claims,
                         "estate_liability_sek": str(s.estate_liability_sek), "batch_id": str(s.batch_id)}
                        for p, (s, end) in sorted(done.items(), key=lambda kv: str(kv[0]))],
        "unsettled_parts": sorted(str(p) for p in parts if p not in done),
        "claims": [{"claim_id": str(c.id), "payout_part_id": str(c.payout_part_id),
                    "right_month": c.right_month.isoformat(), "gross_sek": str(c.gross_sek),
                    "reversed": c.id in reversals,
                    **({"reversal": {"payment_state": reversals[c.id].payment_state,
                                     "liability_sek": str(reversals[c.id].liability_sek),
                                     "capital_sek": str(reversals[c.id].capital_sek),
                                     "company_sek": str(reversals[c.id].company_sek),
                                     "unfunded_dropped_sek": str(reversals[c.id].unfunded_dropped_sek)}}
                       if c.id in reversals else {})} for c in claims],
        "recoveries": [{"case_number": c.case_number, "status": c.status, **(c.details or {})} for c in recoveries],
        "estate": ({"estate_id": str(estate.id), "version": estate.version, "role": estate.role,
                    "document_kind": estate.document_kind, "verified": estate.verified,
                    "decided_by": estate.decided_by,
                    "account": {"account_id": str(account.id), "clearing_number": account.clearing_number,
                                "account_number": mask(account.account_number), "bank_name": account.bank_name,
                                "verified": account.verified}} if estate else None),
    }


__all__ = ["CASE_TEXT", "DEATH_TABLES", "METHOD", "POOL", "POPULATION_SOURCE", "REVERSAL", "RISK_FAMILY",
           "DeathConflict", "DeathMonth", "DeathServiceError", "current_estate", "current_report", "current_reports",
           "death_month", "deaths_present", "estate_for_payment", "import_notices", "notice_file_checksum",
           "parts_of_persons", "person_settled", "persons_of_parts", "register_estate", "register_report", "report_case",
           "reversed_claims", "settlement_view", "settlements", "verify_report"]
