"""Ett litet, fiktivt demobestånd för handläggar-UI:t (Fas 4).

Används när UI:t körs mot den lokala demodatabasen (SQLite) eller mot ett eget
schema i den isolerade testdatabasen `svc_test` – aldrig mot Lakebase-beståndet.
Mönstret följer `tests/conftest.py`: samma modeller, tabellerna skapas i en tom
databas och fylls med ett fåtal personer vars premier är beräknade med
premiemotorn (så att rättelser kan räknas fram igen).

Demobeståndet (personnummer är fiktiva men Luhn-giltiga):

| Personnummer   | Namn             | Läge                                           |
|----------------|------------------|------------------------------------------------|
| 198505151236   | Anna Andersson   | aktiv, premiebetalande AL-000001               |
| 197203034561   | Bertil Berg      | aktiv, lön över 7,5 IBB, premiebetalande AL-000002 |
| 199001017897   | Cecilia Carlsson | anställningen slutade 2025-12-31, fribrev AL-000003 |
| 195904202461   | David Dahl       | pensionerad, utbetalning pågår AL-000004       |

Därtill en **äldre kohort** för flaggskeppsdemon (B-035 val K): 31 aktiva,
premiebetalande försäkrade födda 1959–1962 (`OLDER_COHORT`, AL-000005 och framåt), så
att en premieålder på 67 berör någon redan 2027–2029. Huvudregeln för ITP1 gäller födda
1979 eller senare, men arbetsgivare kan ha ITP1 för fler årskullar (`01_domän/ITP1_regelverk.md`
§1) – så antas det här. Kohorten tas fram med ett fast
slumpfrö och används också av generatorn för det delade beståndet
(`scripts/demo/generate_mock_data.py`). I Lakebase läggs den in först efter backup och
operatörens OK (AGENTS.md §4.5).

Två agentförslag läggs i godkännandekön via tjänstelagret, så att kön går att
pröva. Förslagen prövas mot regelpaketet som om det redan gällde
(`ProductRuleCatalog(today=…)`) – bara här, i demodatabasen. Verkställigheten
vid ett godkännande loggar den verkliga regelstatusen.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from models import (
    Base,
    BaseAmount,
    Employer,
    InsuredPerson,
    Policy,
    PolicyBenefit,
    PolicyState,
    PremiumTransaction,
)
from services import Actor, OperationContext, ProductRuleCatalog, ServiceError, ServiceLayer
from services.db import session_factory_for
from services.operations.common import luhn_valid
from services.parameters import add_missing_defaults as add_missing_parameters
from services.parameters import default_rows as default_parameter_rows
from skills.calculation.calculate_itp1_premium import calculate_itp1_premium, is_in_age_window

DEMO_AGENT = Actor.agent("demo_handlaggaragent", team="forsakring")

IBB = {2023: "74300", 2024: "76200", 2025: "80600", 2026: "83400"}

EMPLOYERS = [
    {"org_number": "5560000001", "name": "Demobolaget AB", "affiliation_date": date(2010, 1, 1),
     "address_city": "Göteborg"},
    {"org_number": "5560000002", "name": "Exempelverken AB", "affiliation_date": date(2004, 1, 1),
     "address_city": "Uppsala"},
]

# (personnummer, förnamn, efternamn, arbetsgivare, anställd från, anställd till, lön 2026, status,
#  ITP1 från, lägen [(läge, från, till)], premiemånader (från, till), sista betalda månad)
PERSONS = [
    ("198505151236", "Anna", "Andersson", "5560000001", date(2015, 3, 1), None, "45000", "active",
     date(2015, 3, 1), [("premium_paying", date(2015, 3, 1), None)],
     (date(2025, 1, 1), date(2026, 9, 1)), date(2026, 8, 1)),
    ("197203034561", "Bertil", "Berg", "5560000001", date(2012, 1, 1), None, "72000", "active",
     date(2012, 1, 1), [("premium_paying", date(2012, 1, 1), None)],
     (date(2025, 1, 1), date(2026, 9, 1)), date(2026, 8, 1)),
    ("199001017897", "Cecilia", "Carlsson", "5560000002", date(2018, 6, 1), date(2025, 12, 31), "52000",
     "terminated", date(2018, 6, 1),
     [("premium_paying", date(2018, 6, 1), date(2025, 12, 31)), ("paid_up", date(2026, 1, 1), None)],
     (date(2025, 1, 1), date(2025, 12, 1)), date(2025, 12, 1)),
    ("195904202461", "David", "Dahl", "5560000002", date(2001, 9, 1), date(2024, 4, 30), "61000", "retired",
     date(2001, 9, 1),
     [("premium_paying", date(2001, 9, 1), date(2024, 4, 30)), ("in_payout", date(2024, 5, 1), None)],
     (date(2024, 1, 1), date(2024, 4, 1)), date(2024, 4, 1)),
]

#: Äldre kohort (B-035 val K): födelseår och antal. Födda 1961–1962 har födelsemånad
#: februari–december, så att varje berört år 2027–2029 får minst 10 berörda vid 67 år.
OLDER_COHORT_YEARS = ((1959, 3), (1960, 4), (1961, 12), (1962, 12))
OLDER_COHORT_SEED = 1959
COHORT_FIRST_NAMES = (
    "Agneta", "Bengt", "Birgitta", "Christer", "Eva", "Göran", "Gunilla", "Hans", "Inger", "Jan",
    "Kerstin", "Lars", "Lena", "Leif", "Margareta", "Mats", "Monica", "Per", "Ulla", "Åke",
)
COHORT_LAST_NAMES = ("Ek", "Falk", "Holm", "Hägg", "Lind", "Lundin", "Nord", "Sjögren", "Strand", "Viklund")
#: Kohortens premiemånader i demobeståndet (från, till, sista betalda) – som för de aktiva ovan
COHORT_PREMIUMS = (date(2025, 1, 1), date(2026, 9, 1), date(2026, 8, 1))


@dataclass(frozen=True)
class CohortPerson:
    """En fiktiv försäkrad i den äldre kohorten. Arbetsgivaren väljs av den som lägger in kohorten."""

    personal_id_number: str
    first_name: str
    last_name: str
    birth_date: date
    employment_start_date: date
    monthly_salary_sek: Decimal


def _personal_id_number(birth: date, serial: int) -> str:
    """Luhn-giltigt personnummer ÅÅÅÅMMDDNNNK för ett fiktivt födelsedatum."""
    stem = f"{birth:%y%m%d}{serial:03d}"
    check = next(d for d in range(10) if luhn_valid(f"{stem}{d}"))
    return f"{birth.year}{stem[2:]}{check}"


def older_cohort() -> list[CohortPerson]:
    """Den äldre kohorten – samma personer varje gång (fast slumpfrö)."""
    rng = random.Random(OLDER_COHORT_SEED)
    taken = {person[0] for person in PERSONS}
    cohort = []
    for year, count in OLDER_COHORT_YEARS:
        for _ in range(count):
            birth = date(year, rng.randint(2 if year >= 1961 else 1, 12), rng.randint(1, 28))
            pnr = _personal_id_number(birth, rng.randint(100, 899))
            while pnr in taken:
                pnr = _personal_id_number(birth, rng.randint(100, 899))
            taken.add(pnr)
            cohort.append(CohortPerson(
                personal_id_number=pnr, first_name=rng.choice(COHORT_FIRST_NAMES),
                last_name=rng.choice(COHORT_LAST_NAMES), birth_date=birth,
                employment_start_date=date(rng.randint(1988, 2012), rng.randint(1, 12), 1),
                monthly_salary_sek=Decimal(rng.randrange(36000, 78001, 500)),
            ))
    return cohort


OLDER_COHORT = older_cohort()


def create_demo_database(
    engine: Engine, *, with_proposals: bool = True, with_older_cohort: bool = True, today: date | None = None
) -> None:
    """Skapar tabellerna i en TOM databas och fyller den med demobeståndet.

    Vägrar om databasen (eller schemat i search_path) redan har tabeller –
    befintliga tabeller ändras aldrig härifrån. `today` sätts i tester;
    `with_older_cohort=False` ger bara de fyra personerna, utan den äldre kohorten.
    """
    existing = inspect(engine).get_table_names()
    if existing:
        raise RuntimeError(
            f"Databasen har redan tabeller ({', '.join(sorted(existing)[:5])} …) – demobeståndet skapas bara i en tom databas"
        )
    Base.metadata.create_all(engine)
    session_factory = session_factory_for(engine)
    seed_demo_stock(session_factory, with_older_cohort=with_older_cohort)
    if with_proposals:
        add_demo_proposals(session_factory, today=today)


def add_missing_demo_tables(engine: Engine) -> None:
    """Skapar tabeller som saknas i en befintlig demo- eller testdatabas (t.ex. `cases`, Fas 5).

    Befintliga tabeller och rader rörs inte, och inget bestånd läggs till. Bara för
    demo- och testdatabaserna – Lakebase-schemat ändras med migrationsskripten.
    """
    Base.metadata.create_all(engine)
    # Produktparametrarna (B-035) i en demo- eller testdatabas som skapades före 3c-P1
    with session_factory_for(engine)() as s:
        if add_missing_parameters(s):
            s.commit()


def seed_demo_stock(session_factory, *, with_older_cohort: bool = True) -> None:
    with session_factory() as s:
        s.add_all(BaseAmount(year=y, income_base_amount_sek=Decimal(v)) for y, v in IBB.items())
        s.add_all(default_parameter_rows())
        employers = {}
        for data in EMPLOYERS:
            employer = Employer(**data)
            s.add(employer)
            employers[data["org_number"]] = employer
        s.flush()

        for number, (pnr, first, last, org, emp_from, emp_to, salary, status, itp1_from, states,
                     (prem_from, prem_to), last_paid) in enumerate(PERSONS, start=1):
            person = InsuredPerson(
                personal_id_number=pnr, first_name=first, last_name=last,
                email=f"{first.lower()}.{last.lower()}@example.se",
                employer_id=employers[org].id, employment_start_date=emp_from, employment_end_date=emp_to,
                monthly_salary_sek=Decimal(salary), employment_rate=Decimal("100"),
                itp1_start_date=itp1_from, status=status,
            )
            s.add(person)
            s.flush()
            policy = Policy(policy_number=f"AL-{number:06d}", insured_person_id=person.id,
                            signed_date=itp1_from, start_date=itp1_from)
            s.add(policy)
            s.flush()
            benefit = PolicyBenefit(policy_id=policy.id, benefit_type="retirement_dc", start_date=itp1_from)
            s.add(benefit)
            s.flush()
            for state, valid_from, valid_to in states:
                s.add(PolicyState(policy_id=policy.id, state=state, valid_from=valid_from, valid_to=valid_to))
            _add_premiums(s, benefit.id, pnr, Decimal(salary), prem_from, prem_to, last_paid)

        if with_older_cohort:
            _add_older_cohort(s, [employers[data["org_number"]] for data in EMPLOYERS])


def _add_older_cohort(s, employers: list[Employer]) -> None:
    """Kohorten som aktiva, premiebetalande försäkrade hos demoarbetsgivarna i tur och ordning."""
    for number, person in enumerate(OLDER_COHORT, start=len(PERSONS) + 1):
        employer = employers[number % len(employers)]
        itp1_from = max(person.employment_start_date, employer.affiliation_date)
        insured = InsuredPerson(
            personal_id_number=person.personal_id_number, first_name=person.first_name,
            last_name=person.last_name,
            email=f"{person.first_name.lower()}.{person.last_name.lower()}.{number}@example.se",
            employer_id=employer.id, employment_start_date=person.employment_start_date,
            monthly_salary_sek=person.monthly_salary_sek, employment_rate=Decimal("100"),
            itp1_start_date=itp1_from, status="active",
        )
        s.add(insured)
        s.flush()
        policy = Policy(policy_number=f"AL-{number:06d}", insured_person_id=insured.id,
                        signed_date=itp1_from, start_date=itp1_from)
        s.add(policy)
        s.flush()
        benefit = PolicyBenefit(policy_id=policy.id, benefit_type="retirement_dc", start_date=itp1_from)
        s.add(benefit)
        s.flush()
        s.add(PolicyState(policy_id=policy.id, state="premium_paying", valid_from=itp1_from, valid_to=None))
        _add_premiums(s, benefit.id, person.personal_id_number, person.monthly_salary_sek, *COHORT_PREMIUMS)


def _add_premiums(s, benefit_id, pnr: str, salary_2026: Decimal, first: date, last: date, last_paid: date) -> None:
    """En premierad per månad i premieåldern; månader utanför den får ingen rad."""
    born = date(int(pnr[0:4]), int(pnr[4:6]), int(pnr[6:8]))
    month = first
    while month <= last:
        if is_in_age_window(born, month):
            # Lönen 2,5 % lägre per år bakåt, som i den genererade premiehistoriken
            salary = (salary_2026 / Decimal("1.025") ** (2026 - month.year)).quantize(Decimal("1"))
            calc = calculate_itp1_premium(salary, Decimal(IBB[month.year]), birth_date=born, period_month=month)
            paid = month <= last_paid
            s.add(
                PremiumTransaction(
                    benefit_id=benefit_id, period_month=month, transaction_type="premium",
                    pensionable_salary_sek=salary, amount_sek=calc.total_premium_sek,
                    calculation_basis=calc.calculation_basis,
                    status="paid" if paid else "invoiced",
                    paid_date=date(month.year, month.month, 25) if paid else None,
                )
            )
        month = date(month.year + month.month // 12, month.month % 12 + 1, 1)


def add_demo_proposals(session_factory, today: date | None = None) -> list[str]:
    """Två agentförslag i godkännandekön. Ett förslag som inte går att lägga i dag hoppas över."""
    today = today or date.today()
    rules = ProductRuleCatalog(today=today)
    if rules.valid_from and rules.valid_from > today:
        rules = ProductRuleCatalog(today=rules.valid_from)  # som om paketet gällde – bara i demodatabasen
    service = ServiceLayer(session_factory=session_factory, rules=rules)
    proposals = [
        (
            "register_salary_report",
            "Lönefil från Demobolaget AB för innevarande månad",
            {
                "personal_id_number": "198505151236", "employer_org_number": "5560000001",
                "period_month": today.replace(day=1).isoformat(), "pensionable_salary_sek": "46500.00",
                "kind": "new", "source": "employer", "source_reference": f"DEMO-LON-{today:%Y%m}-001",
                "received_date": today.isoformat(),
            },
        ),
        (
            "set_policy_paid_up",
            "Avanmälan från Demobolaget AB: anställningen upphörde",
            {"policy_number": "AL-000002", "employment_end_date": "2026-09-30"},
        ),
    ]
    added = []
    for name, reason, data in proposals:
        ctx = OperationContext(actor=DEMO_AGENT, reason=reason, run_id="demo-seed")
        try:
            result = service.execute(name, ctx, data)
        except ServiceError as exc:  # t.ex. datum som inte passar dagens läge
            print(f"Demoförslaget {name} lades inte: {exc}")
            continue
        if result.approval_id:
            added.append(result.approval_id)
    return added
