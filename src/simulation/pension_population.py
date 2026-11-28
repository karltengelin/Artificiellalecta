"""Paket B steg 9: pensionärerna i det nya startläget (B-057, P1-PENSION-001 §12.1, Karls val Q1–Q3).

Beståndet läggs till före journalens nya ingående läge per 2026-10-31. Det har två grupper:

- **Kohorten** (B-035 val K): de 31 personerna i `utils.demo_data.OLDER_COHORT`, födda 1959–1962.
  De 7 födda 1959–1960 har passerat 66 utan registrerat val och ger ärenden `payout_review` i novembers
  stängning (V6). De 24 födda 1961–1962 får standardstart i 66-årsmånaden från februari 2027 (V4).
- **Pensionärerna:** fyra personer som har passerat 66. Deras begäran om start i december 2026 togs emot i
  november, före fristen. Planerna beslutas efter novembers stängning, och decembers stängning ger de första
  månadsrätterna. En av dem delar först sin uttagsdel i två (Karls justering av Q1 2026-11-28).

Alla har fribrev från en avslutad anställning (Q2). Ingen betalar premie efter 2026-10-31, så paket A:s
period 2026-11 påverkas inte.

**Startvärdena (Q3, justerat av Karl 2026-11-28).** Varje försäkring får en enda syntetisk premie, märkt
`declared_opening` i `calculation_basis`. S-04 räknar sedan fram kapital C och garanti G på samma sätt som för
det övriga beståndet. Premieperioden är januari det år personen fyller 65 (senast 2026-09), alltid före
66-årsmånaden. Premien betalas 2026-10-30, som i paket C:s pensionsprov: den tillförs vid oktobers slut och
deltar inte i någon avkastningsfördelning före startläget. S-04 fördelar avkastningen för hela kollektivet i
ören efter största rest (`capital_rollforward.close_month`), så en tidigare betalning skulle flytta enstaka
ören hos befintliga försäkringar. Med betalningen 2026-10-30 får de exakt samma C och G som förut, och de nya
får C lika med premien per 2026-10-31.

Allt är fiktivt och fast: samma personer, belopp och planer varje gång. Ett personnummer eller
försäkringsnummer som redan finns stoppar tillägget. Samma innehåll igen ger ingen ny effekt.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (
    Employer,
    InsuredPerson,
    Policy,
    PolicyBenefit,
    PolicyState,
    PremiumTransaction,
)
from services.payout_parts import create_initial_part
from utils.demo_data import OLDER_COHORT

DECISION = "B-057"
SOURCE = "declared_opening"
#: Journalens ingående läge, och dagen startpremierna betalas (tillförs vid oktobers slut)
OPENING_DATE = date(2026, 10, 31)
PREMIUM_PAID = date(2026, 10, 30)
LAST_PREMIUM_MONTH = date(2026, 9, 1)
FIRST_PREMIUM_MONTH = date(2023, 1, 1)
#: Premiebeloppen för kohorten dras med ett fast frö, i hela 10 000 kr
COHORT_SEED = 57
COHORT_PREMIUM_RANGE = (300_000, 1_500_000)
#: Den månad pensionärerna begär start från, och när begäran togs emot (före fristen 2026-11-30)
START_MONTH = date(2026, 12, 1)
REQUEST_RECEIVED = date(2026, 11, 16)
#: Delningen görs i november och tas emot före novembers frist (2026-10-31)
SPLIT_MONTH = date(2026, 11, 1)
SPLIT_RECEIVED = date(2026, 10, 26)


class PopulationError(ValueError):
    """Beståndet kan inte läggas till: krock med befintliga rader, ingen arbetsgivare eller ändrat underlag."""


@dataclass(frozen=True)
class Plan:
    """En begärd plan för en uttagsdel: form och, för tidsbegränsad, antal månader."""

    part_number: int
    form: str
    payments: int | None = None

    def content(self) -> dict:
        body = {"first_right": START_MONTH.isoformat(), "form": self.form}
        return {**body, "payments": self.payments} if self.form == "fixed_term" else body


@dataclass(frozen=True)
class Member:
    """En försäkrad i det nya beståndet med sin startpremie och, för pensionärerna, begärda planer."""

    personal_id_number: str
    first_name: str
    last_name: str
    birth_date: date
    employment_start_date: date
    monthly_salary_sek: Decimal
    premium_sek: Decimal
    group: str  # "cohort" eller "pensioner"
    plans: tuple[Plan, ...] = ()
    split_share: Decimal | None = None  # andel till del 2 vid delning i november
    #: Skattestatus för 2027 (Q7): sidoinkomst 30 % eller ett individuellt beslut med procentsats
    tax_kind: str | None = None
    tax_rate: Decimal | None = None

    @property
    def premium_month(self) -> date:
        return min(date(self.birth_date.year + 65, 1, 1), LAST_PREMIUM_MONTH)

    @property
    def employment_end_date(self) -> date:
        """Anställningen slutade med premiemånaden; fribrev från dagen efter."""
        nxt = date(self.premium_month.year + self.premium_month.month // 12, self.premium_month.month % 12 + 1, 1)
        return nxt - timedelta(days=1)

    @property
    def sixty_six_month(self) -> date:
        return date(self.birth_date.year + 66, self.birth_date.month, 1)


def _pensioners() -> tuple[Member, ...]:
    """Fyra pensionärer. David Dahl är samma person som i demobeståndet (`utils.demo_data`)."""
    return (
        Member("195904202461", "David", "Dahl", date(1959, 4, 20), date(2001, 9, 1), Decimal(61000),
               Decimal("900000.00"), "pensioner", (Plan(1, "lifelong"),), tax_kind="side_income"),
        Member("195808144124", "Margareta", "Berg", date(1958, 8, 14), date(1992, 3, 1), Decimal(54500),
               Decimal("1200000.00"), "pensioner", (Plan(1, "fixed_term", 120),), tax_kind="side_income"),
        Member("196002097316", "Lars", "Ekström", date(1960, 2, 9), date(2004, 1, 1), Decimal(47000),
               Decimal("450000.00"), "pensioner", (Plan(1, "lifelong"),), tax_kind="individual_decision",
               tax_rate=Decimal("0.25")),
        Member("195910036622", "Karin", "Sjöberg", date(1959, 10, 3), date(1996, 5, 1), Decimal(58000),
               Decimal("700000.00"), "pensioner", (Plan(1, "lifelong"), Plan(2, "fixed_term", 60)),
               split_share=Decimal("0.4"), tax_kind="side_income"),
    )


def _cohort() -> tuple[Member, ...]:
    rng = random.Random(COHORT_SEED)
    low, high = COHORT_PREMIUM_RANGE
    return tuple(
        Member(p.personal_id_number, p.first_name, p.last_name, p.birth_date, p.employment_start_date,
               p.monthly_salary_sek, Decimal(rng.randrange(low, high + 1, 10_000)).quantize(Decimal("0.01")),
               "cohort")
        for p in OLDER_COHORT)


#: Hela det nya beståndet i fast ordning: pensionärerna först, sedan kohorten
MEMBERS: tuple[Member, ...] = (*_pensioners(), *_cohort())


def definition_checksum(members=MEMBERS) -> str:
    """Kontrollsumma för beståndets definition, så att granskning och tillägg gäller samma lista."""
    body = [{**asdict(m), "premium_month": m.premium_month.isoformat()} for m in members]
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class PopulationPlan:
    """Granskningen före tillägget. Skriver ingenting."""

    employer_org_number: str | None
    policy_numbers: dict[str, str] = field(default_factory=dict)
    existing: list[str] = field(default_factory=list)
    collisions: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def already_added(self) -> bool:
        return len(self.existing) == len(MEMBERS) and not self.collisions

    @property
    def passed(self) -> bool:
        return not self.problems and not self.collisions

    @property
    def checksum(self) -> str:
        body = {"definition": definition_checksum(), "employer": self.employer_org_number,
                "policy_numbers": self.policy_numbers}
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

    def summary(self) -> dict:
        groups = {g: [m for m in MEMBERS if m.group == g] for g in ("pensioner", "cohort")}
        return {
            "decision": DECISION, "employer_org_number": self.employer_org_number,
            "members": len(MEMBERS), "pensioners": len(groups["pensioner"]), "cohort": len(groups["cohort"]),
            "passed_66_by_2026_10": sum(m.sixty_six_month <= date(2026, 10, 1) for m in MEMBERS),
            "premium_total_sek": str(sum((m.premium_sek for m in MEMBERS), Decimal("0.00"))),
            "policy_numbers": self.policy_numbers, "already_added": self.already_added,
            "existing": self.existing, "collisions": self.collisions, "problems": self.problems,
            "definition_checksum": definition_checksum(), "review_checksum": self.checksum,
        }


def _employer(session: Session) -> Employer | None:
    """Den tidigare arbetsgivaren: första anslutna arbetsgivaren med avtalet ITP, efter organisationsnummer."""
    return session.scalar(select(Employer).where(Employer.collective_agreement == "ITP")
                          .order_by(Employer.org_number).limit(1))


def _next_numbers(session: Session, count: int) -> list[str]:
    numbers = [int(m.group(1)) for n in session.scalars(select(Policy.policy_number))
               if (m := re.fullmatch(r"AL-(\d{6})", n))]
    start = max(numbers, default=0) + 1
    return [f"AL-{n:06d}" for n in range(start, start + count)]


def plan_population(session: Session) -> PopulationPlan:
    """Granskar tillägget: arbetsgivare, försäkringsnummer och krockar. Skriver ingenting."""
    employer = _employer(session)
    plan = PopulationPlan(employer_org_number=employer.org_number if employer else None)
    if employer is None:
        plan.problems.append("Ingen ansluten arbetsgivare med avtalet ITP")
    pnrs = [m.personal_id_number for m in MEMBERS]
    found = dict(session.execute(
        select(InsuredPerson.personal_id_number, Policy.policy_number)
        .outerjoin(Policy, Policy.insured_person_id == InsuredPerson.id)
        .where(InsuredPerson.personal_id_number.in_(pnrs))).all())
    for m in MEMBERS:
        if m.personal_id_number not in found:
            continue
        if _matches(session, m, found[m.personal_id_number]):
            plan.existing.append(m.personal_id_number)
            plan.policy_numbers[m.personal_id_number] = found[m.personal_id_number]
        else:
            plan.collisions.append(m.personal_id_number)
    if plan.existing and len(plan.existing) != len(MEMBERS):
        plan.problems.append(f"Bara {len(plan.existing)} av {len(MEMBERS)} finns – delvis tillagt bestånd")
    if not plan.existing:
        plan.policy_numbers = dict(zip(pnrs, _next_numbers(session, len(MEMBERS)), strict=True))
    for m in MEMBERS:
        if not (FIRST_PREMIUM_MONTH <= m.premium_month <= LAST_PREMIUM_MONTH and m.premium_month < m.sixty_six_month):
            plan.problems.append(f"{m.personal_id_number}: startpremien ligger utanför tillåtna månader")
    return plan


def _matches(session: Session, m: Member, policy_number: str | None) -> bool:
    """Finns personen redan med exakt detta bestånds försäkring och startpremie?"""
    if policy_number is None:
        return False
    premium = session.scalar(
        select(PremiumTransaction.amount_sek).join(PolicyBenefit, PolicyBenefit.id == PremiumTransaction.benefit_id)
        .join(Policy, Policy.id == PolicyBenefit.policy_id)
        .where(Policy.policy_number == policy_number, PremiumTransaction.period_month == m.premium_month,
               PremiumTransaction.transaction_type == "premium"))
    return premium is not None and Decimal(premium) == m.premium_sek


def add_population(session: Session, reviewed_checksum: str) -> tuple[dict, bool]:
    """Lägger till beståndet med granskningens kontrollsumma. (sammanställning, nytt) – idempotent."""
    plan = plan_population(session)
    if plan.checksum != reviewed_checksum:
        raise PopulationError("Underlaget har ändrats sedan granskningen – granska tillägget igen")
    if plan.already_added:
        return plan.summary(), False
    if not plan.passed:
        raise PopulationError("Tillägget stoppas: " + "; ".join(plan.problems + [f"krock {c}" for c in plan.collisions]))
    employer = _employer(session)
    for m in MEMBERS:
        _add_member(session, employer, m, plan.policy_numbers[m.personal_id_number])
    session.flush()
    count = session.scalar(select(func.count()).select_from(InsuredPerson)
                           .where(InsuredPerson.personal_id_number.in_([m.personal_id_number for m in MEMBERS])))
    if count != len(MEMBERS):
        raise PopulationError(f"Efter tillägget finns {count} av {len(MEMBERS)} personer")
    return plan.summary(), True


def _add_member(session: Session, employer: Employer, m: Member, policy_number: str) -> None:
    start, end = m.employment_start_date, m.employment_end_date
    person = InsuredPerson(
        personal_id_number=m.personal_id_number, first_name=m.first_name, last_name=m.last_name,
        employer_id=employer.id, employment_start_date=start, employment_end_date=end,
        monthly_salary_sek=m.monthly_salary_sek, employment_rate=Decimal(100), itp1_start_date=start,
        status="terminated")
    session.add(person)
    session.flush()
    policy = Policy(policy_number=policy_number, insured_person_id=person.id, signed_date=start, start_date=start)
    session.add(policy)
    session.flush()
    benefit = PolicyBenefit(policy_id=policy.id, benefit_type="retirement_dc", start_date=start)
    session.add(benefit)
    session.add_all([
        PolicyState(policy_id=policy.id, state="premium_paying", valid_from=start, valid_to=end),
        PolicyState(policy_id=policy.id, state="paid_up", valid_from=end + timedelta(days=1)),
    ])
    session.flush()
    create_initial_part(session, benefit, note=f"Uttagsdel 1, ej startad ({DECISION}, nytt startläge)")
    session.add(PremiumTransaction(
        benefit_id=benefit.id, period_month=m.premium_month, transaction_type="premium",
        amount_sek=m.premium_sek, status="paid", paid_date=PREMIUM_PAID,
        calculation_basis={"source": SOURCE, "decision": DECISION,
                           "note": "Syntetisk startpremie: ger kapital och garanti i det nya startläget"}))


# --- Underlaget för pensionärernas operationer (samma i körskripten och i provet) ----------------------------

PENSIONERS: tuple[Member, ...] = tuple(m for m in MEMBERS if m.group == "pensioner")
TAX_YEAR = 2027
#: Uppgifterna om skatt och konto och bolagets beslut om insättning: första dagen novembers stängning kan göras
INPUTS_RECEIVED = date(2026, 12, 1)
CAPITAL_DECIDED = date(2026, 12, 1)
CAPITAL_REF = f"{DECISION} Q6: provisorisk insättning under byggfas (24 × decembers månadsbelopp); E_min före live"


def split_request(member: Member, policy_number: str) -> dict:
    """Begäran om delning i november: andelen till del 2, del 1 tar emot premier (PR-ITP1-015)."""
    return {"policy_number": policy_number, "part_number": 1, "kind": "split",
            "content": {"month": SPLIT_MONTH.isoformat(), "share": str(member.split_share), "premium_receiver": 1},
            "received_date": SPLIT_RECEIVED.isoformat(), "channel": "customer_portal"}


def start_requests(member: Member, policy_number: str) -> list[dict]:
    """Begäran om start i december per uttagsdel, mottagen före fristen 2026-11-30."""
    return [{"policy_number": policy_number, "part_number": plan.part_number, "kind": "start",
             "content": plan.content(), "received_date": REQUEST_RECEIVED.isoformat(), "channel": "customer_portal"}
            for plan in member.plans]


def tax_status(member: Member) -> dict:
    data = {"personal_id_number": member.personal_id_number, "tax_year": TAX_YEAR, "kind": member.tax_kind,
            "received_date": INPUTS_RECEIVED.isoformat(), "channel": "customer_portal"}
    if member.tax_kind == "individual_decision":
        data |= {"rate": str(member.tax_rate),
                 "decision_ref": f"Simulerat beslut om särskild skattesats {TAX_YEAR} ({DECISION})"}
    return data


def account_number(member: Member) -> str:
    """Ett fiktivt kontonummer per pensionär i den simulerade banken (clearing 0000)."""
    return f"{PENSIONERS.index(member) + 1:08d}"


def payout_account(member: Member) -> dict:
    number = account_number(member)
    return {"personal_id_number": member.personal_id_number, "clearing_number": "0000", "account_number": number,
            "bank_name": "Simulerad bank", "verified": True, "verification_method": "kontouppslag",
            "verification_ref": f"SIM-{DECISION}-{number}", "received_date": INPUTS_RECEIVED.isoformat(),
            "channel": "customer_portal"}


def capital_deposit(december_m_total: Decimal) -> Decimal:
    """Q6: 24 gånger decembers månadsbelopp, avrundat uppåt till hela 10 000 kr."""
    steps = (24 * december_m_total / 10_000).to_integral_value(rounding=ROUND_CEILING)
    return (steps * 10_000).quantize(Decimal("0.01"))
