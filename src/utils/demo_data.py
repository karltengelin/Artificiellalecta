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

Två agentförslag läggs i godkännandekön via tjänstelagret, så att kön går att
pröva. Förslagen prövas mot regelpaketet som om det redan gällde
(`ProductRuleCatalog(today=…)`) – bara här, i demodatabasen. Verkställigheten
vid ett godkännande loggar den verkliga regelstatusen.
"""

from __future__ import annotations

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
from skills.calculation.calculate_itp1_premium import calculate_itp1_premium

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


def create_demo_database(engine: Engine, *, with_proposals: bool = True, today: date | None = None) -> None:
    """Skapar tabellerna i en TOM databas och fyller den med demobeståndet.

    Vägrar om databasen (eller schemat i search_path) redan har tabeller –
    befintliga tabeller ändras aldrig härifrån. `today` sätts i tester.
    """
    existing = inspect(engine).get_table_names()
    if existing:
        raise RuntimeError(
            f"Databasen har redan tabeller ({', '.join(sorted(existing)[:5])} …) – demobeståndet skapas bara i en tom databas"
        )
    Base.metadata.create_all(engine)
    session_factory = session_factory_for(engine)
    seed_demo_stock(session_factory)
    if with_proposals:
        add_demo_proposals(session_factory, today=today)


def add_missing_demo_tables(engine: Engine) -> None:
    """Skapar tabeller som saknas i en befintlig demo- eller testdatabas (t.ex. `cases`, Fas 5).

    Befintliga tabeller och rader rörs inte, och inget bestånd läggs till. Bara för
    demo- och testdatabaserna – Lakebase-schemat ändras med migrationsskripten.
    """
    Base.metadata.create_all(engine)


def seed_demo_stock(session_factory) -> None:
    with session_factory() as s:
        s.add_all(BaseAmount(year=y, income_base_amount_sek=Decimal(v)) for y, v in IBB.items())
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


def _add_premiums(s, benefit_id, pnr: str, salary_2026: Decimal, first: date, last: date, last_paid: date) -> None:
    born = date(int(pnr[0:4]), int(pnr[4:6]), int(pnr[6:8]))
    month = first
    while month <= last:
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
