"""Fryst, lokalt startbestånd för den första premiemånaden."""

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import URL, create_engine, func, select
from sqlalchemy.orm import Session

from models import (
    BankEvent,
    Base,
    BaseAmount,
    Case,
    Employer,
    InsuredPerson,
    Invoice,
    InvoiceLineRecord,
    PaymentAllocation,
    PayoutPart,
    PayoutPartState,
    Policy,
    PolicyBenefit,
    PolicyState,
    PremiumTransaction,
    SalaryFile,
    SalaryReport,
)
from services.parameters import default_rows, premium_parameters
from services.payout_parts import create_initial_part

PERIOD = date(2026, 10, 1)
EMPLOYER = "5560000001"
PEOPLE = [("198505151234", "AL-000001", 45000), ("197803031234", "AL-000002", 60000)]
OPENING = "premiebestand-20261031-v1"
DB = "premium.sqlite"


def local_engine(path):
    return create_engine(URL.create("sqlite", database=str(path)))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _seed(session):
    start = date(2020, 1, 1)
    employer = Employer(org_number=EMPLOYER, name="Premieprov AB", affiliation_date=start)
    session.add_all([employer, BaseAmount(year=2026, income_base_amount_sek=83400), *default_rows()])
    session.flush()
    for pnr, number, salary in PEOPLE:
        person = InsuredPerson(personal_id_number=pnr, first_name="Simulerad", last_name=number,
                               employer_id=employer.id, employment_start_date=start, employment_rate=100,
                               monthly_salary_sek=salary, itp1_start_date=start, status="active")
        session.add(person)
        session.flush()
        policy = Policy(policy_number=number, insured_person_id=person.id, signed_date=start, start_date=start)
        session.add(policy)
        session.flush()
        benefit = PolicyBenefit(policy_id=policy.id, benefit_type="retirement_dc", start_date=start)
        session.add_all([benefit, PolicyState(policy_id=policy.id, state="premium_paying", valid_from=start)])
        session.flush()
        create_initial_part(session, benefit)


def _inspect(session):
    empty = (SalaryReport, SalaryFile, PremiumTransaction, Invoice, InvoiceLineRecord, BankEvent, PaymentAllocation, Case)
    counts = {model.__tablename__: session.scalar(select(func.count()).select_from(model)) for model in empty}
    sizes = {m.__tablename__: session.scalar(select(func.count()).select_from(m))
             for m in (Employer, InsuredPerson, Policy, PolicyBenefit, PayoutPart, PayoutPartState, PolicyState)}
    if sizes != {"employers": 1, "insured_persons": 2, "policies": 2, "policy_benefits": 2,
                 "payout_parts": 2, "payout_part_states": 2, "policy_states": 2}:
        raise ValueError("Fel antal arbetsgivare, försäkrade eller mottagande delar i startbeståndet")
    population = session.execute(
        select(InsuredPerson.personal_id_number, Policy.policy_number, InsuredPerson.monthly_salary_sek)
        .join(Policy, Policy.insured_person_id == InsuredPerson.id)
        .join(Employer, Employer.id == InsuredPerson.employer_id)
        .join(PolicyState, PolicyState.policy_id == Policy.id)
        .join(PolicyBenefit, PolicyBenefit.policy_id == Policy.id)
        .join(PayoutPart, PayoutPart.benefit_id == PolicyBenefit.id)
        .join(PayoutPartState, PayoutPartState.payout_part_id == PayoutPart.id)
        .where(Employer.org_number == EMPLOYER, PolicyState.state == "premium_paying",
               PayoutPart.part_number == 1, PayoutPartState.state == "not_started")
        .order_by(Policy.policy_number)
    ).all()
    if any(counts.values()) or population != PEOPLE or session.get(BaseAmount, 2026).income_base_amount_sek != 83400:
        raise ValueError("Startbeståndet stämmer inte med premieprovet")
    return {"opening": OPENING, "period": PERIOD.isoformat(), "counts": {**sizes, **counts},
            "policies": [row[1] for row in population], "ibb": 83400,
            "parameters": premium_parameters(session, PERIOD).versions}


def copy_opening(root: Path, destination: Path):
    """Publicera en färdig startbild atomärt även vid samtidiga starter."""
    opening = root / OPENING
    if not opening.exists():
        with TemporaryDirectory(dir=root) as tmp:
            build = Path(tmp) / "opening"
            build.mkdir()
            engine = local_engine(build / DB)
            try:
                Base.metadata.create_all(engine)
                with Session(engine) as session, session.begin():
                    _seed(session)
                    session.flush()
                    manifest = _inspect(session)
            finally:
                engine.dispose()
            manifest["sha256"] = digest(build / DB)
            (build / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            try:
                build.rename(opening)
            except OSError:
                if not opening.is_dir():
                    raise
    manifest = json.loads((opening / "manifest.json").read_text(encoding="utf-8"))
    shutil.copyfile(opening / DB, destination)
    if digest(destination) != manifest["sha256"]:
        raise ValueError("Startbildens kontrollsumma avviker")
    engine = local_engine(destination)
    try:
        with Session(engine) as session:
            if manifest != {**_inspect(session), "sha256": manifest["sha256"]}:
                raise ValueError("Startmanifestet stämmer inte")
    finally:
        engine.dispose()
    return manifest
