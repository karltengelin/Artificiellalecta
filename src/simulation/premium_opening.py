"""Fryst, lokalt startbestånd för den första premiemånaden."""

import hashlib
import json
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep

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
    ValuationBasis,
)
from services import valuation_bases
from services.parameters import default_rows, premium_parameters
from services.payout_parts import create_initial_part
from services.premium_month_inputs import november_returns

PERIOD = date(2026, 10, 1)
EMPLOYER = "5560000001"
PEOPLE = [("198505151234", "AL-000001", 45000), ("197803031234", "AL-000002", 60000)]
OPENING = "premiebestand-20261031-v1"
SAVINGS_OPENING = "sparbestand-20261031-v1"
PENSION_OPENING = "pensionsbestand-20261031-v1"
PENSIONER = ("196012151234", "AL-000003", 0)
DB = "premium.sqlite"


def local_engine(path):
    return create_engine(URL.create("sqlite", database=str(path)))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def publish_directory(source, destination):
    """Windows kan kort hålla en nyss stängd SQLite-fil öppen vid katalogbytet."""
    for delay in (0.05, 0.1, 0.2, 0.4, 0.8):
        try:
            return source.rename(destination)
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in (5, 32) or destination.exists():
                raise
            sleep(delay)
    return source.rename(destination)


def _seed(session, savings, pension):
    start = date(2020, 1, 1)
    employer = Employer(org_number=EMPLOYER, name="Premieprov AB", affiliation_date=start)
    session.add_all([employer, BaseAmount(year=2026, income_base_amount_sek=83400), *default_rows()])
    session.flush()
    for pnr, number, salary in [*PEOPLE, PENSIONER] if pension else PEOPLE:
        state = "paid_up" if pnr == PENSIONER[0] else "premium_paying"
        person = InsuredPerson(personal_id_number=pnr, first_name="Simulerad", last_name=number,
                               employer_id=employer.id, employment_start_date=start, employment_rate=100,
                               monthly_salary_sek=salary, itp1_start_date=start, status="active")
        session.add(person)
        session.flush()
        policy = Policy(policy_number=number, insured_person_id=person.id, signed_date=start, start_date=start)
        session.add(policy)
        session.flush()
        benefit = PolicyBenefit(policy_id=policy.id, benefit_type="retirement_dc", start_date=start)
        session.add_all([benefit, PolicyState(policy_id=policy.id, state=state, valid_from=start)])
        session.flush()
        create_initial_part(session, benefit)
        if savings:
            session.add(PremiumTransaction(
                benefit_id=benefit.id, period_month=date(2026, 9, 1), transaction_type="premium",
                amount_sek={"AL-000001": 10000, "AL-000002": 20000, "AL-000003": 600000}[number],
                status="paid", paid_date=date(2026, 10, 30)))
    if savings:
        # Antagna syntetiska grunder ingår i den frysta provbilden (B-050 S5).
        bases = valuation_bases.default_rows()
        previous = next(row for row in bases if row.code == "AVK-SIM-2026-01")
        previous.valid_to = date(2026, 10, 31)
        content = november_returns(previous.assumptions, Decimal("0.002"))
        session.add_all(bases)
        session.add(ValuationBasis(
            code="AVK-SIM-2026-02", title="November i isolerat sparprov", family=previous.family,
            purpose=previous.purpose, assumptions=content, checksum=valuation_bases.checksum(content),
            supersedes_code=previous.code, valid_from=date(2026, 11, 1), status="adopted",
            valid_to=date(2026, 11, 30) if pension else None,
            source_refs="B-050 S5", decision_ref="Paket C, syntetisk startbild",
            proposal_reason="Isolerat samprov", created_by="system:seed", adopted_by="system:seed"))
        if pension:
            december = {**content, "description": "Lokalt pensionsprov, nollavkastning i december.",
                        "months": [*content["months"], {"month": "2026-12-01", "rate": "0"}]}
            session.add(ValuationBasis(
                code="AVK-SIM-2026-03", title="December i isolerat pensionsprov", family=previous.family,
                purpose=previous.purpose, assumptions=december, checksum=valuation_bases.checksum(december),
                supersedes_code="AVK-SIM-2026-02", valid_from=date(2026, 12, 1), status="adopted",
                source_refs="Paket C, isolerat pensionsprov", decision_ref="Paket C, syntetisk startbild",
                proposal_reason="Isolerat samprov", created_by="system:seed", adopted_by="system:seed"))


def _inspect(session, opening, savings, pension):
    empty = (SalaryReport, SalaryFile, PremiumTransaction, Invoice, InvoiceLineRecord, BankEvent, PaymentAllocation, Case)
    counts = {model.__tablename__: session.scalar(select(func.count()).select_from(model)) for model in empty}
    sizes = {m.__tablename__: session.scalar(select(func.count()).select_from(m))
             for m in (Employer, InsuredPerson, Policy, PolicyBenefit, PayoutPart, PayoutPartState, PolicyState)}
    population_size = 3 if pension else 2
    if sizes != {**dict.fromkeys(sizes, population_size), "employers": 1}:
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
    expected_counts = dict.fromkeys(counts, 0)
    if savings:
        expected_counts["premium_transactions"] = population_size
    if counts != expected_counts or population != PEOPLE or session.get(BaseAmount, 2026).income_base_amount_sek != 83400:
        raise ValueError("Startbeståndet stämmer inte med premieprovet")
    if pension:
        paid_up = session.execute(
            select(InsuredPerson.personal_id_number, Policy.policy_number, InsuredPerson.monthly_salary_sek)
            .join(Policy).join(PolicyState).join(PolicyBenefit, PolicyBenefit.policy_id == Policy.id)
            .join(PayoutPart).join(PayoutPartState)
            .where(PolicyState.state == "paid_up", PayoutPart.part_number == 1, PayoutPartState.state == "not_started")
        ).one_or_none()
        if paid_up != PENSIONER:
            raise ValueError("Fribrevet stämmer inte med pensionsprovet")
    return {"opening": opening, "period": PERIOD.isoformat(), "counts": {**sizes, **counts},
            "policies": [row[1] for row in population], "ibb": 83400,
            "parameters": premium_parameters(session, PERIOD).versions}


def opening_name(*, savings, pension):
    if pension:
        return PENSION_OPENING
    return SAVINGS_OPENING if savings else OPENING


def copy_opening(root: Path, destination: Path, *, savings=False, pension=False):
    """Publicera en färdig startbild atomärt även vid samtidiga starter."""
    name = opening_name(savings=savings, pension=pension)
    opening = root / name
    if not opening.exists():
        with TemporaryDirectory(dir=root) as tmp:
            build = Path(tmp) / "opening"
            build.mkdir()
            engine = local_engine(build / DB)
            try:
                Base.metadata.create_all(engine)
                with Session(engine) as session, session.begin():
                    _seed(session, savings, pension)
                    session.flush()
                    manifest = _inspect(session, name, savings, pension)
            finally:
                engine.dispose()
            manifest["sha256"] = digest(build / DB)
            (build / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            try:
                publish_directory(build, opening)
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
            if manifest != {**_inspect(session, name, savings, pension), "sha256": manifest["sha256"]}:
                raise ValueError("Startmanifestet stämmer inte")
    finally:
        engine.dispose()
    return manifest
