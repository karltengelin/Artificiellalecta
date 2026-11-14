"""Motpartssimulatorn (paket A steg 5, B-046, P1-PREMIE-001 §9).

Simulatorns filer lämnas till samma operationer som riktiga filer. Proven kontrollerar att
filerna går igenom intagets kontroller, att facit stämmer med verksamhetens utfall och att
simulatorn aldrig skriver i affärstabellerna.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, inspect, select

from models import (
    Employer,
    InsuredPerson,
    Policy,
    PolicyState,
    PremiumTransaction,
)
from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer
from services.operations import common
from simulation.counterparties import (
    PaymentBehaviour,
    SalaryScenario,
    bank_file,
    load_payload,
    salary_file,
)
from tests.conftest import add_retirement_benefit

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

START = date(2026, 11, 7)
EMPLOYER = "5560000001"
OCTOBER = date(2026, 10, 1)
RECEIVED = date(2026, 11, 5)
PEOPLE = {"198505151234": ("AL-000010", 45000), "197803031234": ("AL-000011", 60000),
          "196912121234": ("AL-000012", 38000)}
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Simulerade motparter")


def _person(s, employer, pnr, policy_number, salary):
    person = InsuredPerson(
        personal_id_number=pnr, first_name="Test", last_name=pnr[-4:], employer_id=employer.id,
        employment_start_date=date(2020, 1, 1), monthly_salary_sek=Decimal(salary), employment_rate=Decimal(100),
        itp1_start_date=date(2020, 1, 1), status="active",
    )
    s.add(person)
    s.flush()
    policy = Policy(policy_number=policy_number, insured_person_id=person.id,
                    signed_date=date(2020, 1, 1), start_date=date(2020, 1, 1))
    s.add(policy)
    s.flush()
    add_retirement_benefit(s, policy.id, date(2020, 1, 1))
    s.add(PolicyState(policy_id=policy.id, state="premium_paying", valid_from=date(2020, 1, 1)))
    s.flush()


@pytest.fixture
def clock(monkeypatch):
    state = SimpleNamespace(today=START)
    monkeypatch.setattr(common, "today", lambda: state.today)
    return state


@pytest.fixture
def db(insurance_db, clock):
    with insurance_db.session_factory() as s:
        employer = s.scalar(select(Employer).where(Employer.org_number == EMPLOYER))
        for pnr, (policy_number, salary) in PEOPLE.items():
            _person(s, employer, pnr, policy_number, salary)
        s.commit()
    return insurance_db


def run(db, operation, data):
    service = ServiceLayer(session_factory=db.session_factory, rules=ProductRuleCatalog(today=START))
    return service.execute(operation, HUMAN, data).output


def simulate(db, make, *args, **kwargs):
    with db.session_factory() as s:
        return make(s, *args, **kwargs)


def counts(db) -> dict[str, int]:
    with db.session_factory() as s:
        names = inspect(s.connection()).get_table_names()
        return {n: s.connection().exec_driver_sql(f'SELECT count(*) FROM "{n}"').scalar_one() for n in names}


def employer_file(db, seed=1, scenario=None, received=RECEIVED):
    return simulate(db, salary_file, EMPLOYER, OCTOBER, received_date=received, seed=seed, scenario=scenario)


def approve(db, sim):
    view = run(db, "import_salary_file", sim.payload)
    run(db, "approve_salary_file", {"employer_org_number": EMPLOYER, "file_reference": sim.reference,
                                    "expected_digest": view.review_digest})
    return view


def invoice(db):
    return run(db, "create_invoice", {"employer_org_number": EMPLOYER, "period_month": "2026-10-01"}).invoices


def bank(db, clock, behaviour, as_of, seed=7):
    clock.today = as_of
    sim = simulate(db, bank_file, OCTOBER, {EMPLOYER: behaviour}, as_of=as_of, seed=seed)
    result = run(db, "import_bank_file", sim.payload) if not sim.empty else None
    return sim, result


def outcome_of(result) -> dict[str, str]:
    """Verksamhetens utfall i facits språk."""
    mapped = {}
    for o in result.outcomes:
        if o.reason is not None and o.allocated_sek == 0:
            mapped[o.event_id] = f"suspense:{o.reason}"
        elif o.reason == "overpayment":
            mapped[o.event_id] = "allocated+overpayment"
        else:
            mapped[o.event_id] = "allocated" if o.unallocated_sek == 0 and o.allocated_sek == o.amount_sek else "?"
    return mapped


def expected_of(sim, result) -> dict[str, str]:
    """Facit; en delbetalning syns som fördelad utan rest i händelsen och som öppen fordran på fakturan."""
    return {e["event_id"]: "allocated" if e["expected"] == "partial" else e["expected"] for e in sim.facit["events"]}


class TestArbetsgivarfil:
    def test_fil_utan_avvikelser_gar_igenom_intaget(self, db):
        sim = employer_file(db)
        view = run(db, "import_salary_file", sim.payload)
        assert view.summary.rows == sim.facit["rows"] == 3
        assert (view.summary.valid, view.summary.deviations, view.summary.missing) == (3, 0, 0)
        assert sim.reference == "SIM1-5560000001-202610-S1"
        assert (sim.label["simulator"], sim.label["version"], sim.label["seed"]) == ("motpartssimulator", "1", 1)
        assert {r.personal_id_number: r.pensionable_salary_sek for r in view.rows} == {
            pnr: Decimal(salary) for pnr, (_, salary) in PEOPLE.items()}

    def test_samma_seed_ger_samma_fil_och_samma_intag(self, db):
        first, second = employer_file(db, seed=3), employer_file(db, seed=3)
        assert first.payload == second.payload  # fall 6: filen känns igen
        a = run(db, "import_salary_file", first.payload)
        b = run(db, "import_salary_file", second.payload)
        assert a.file_id == b.file_id

    def test_variation_ar_seedbunden(self, db):
        scenario = SalaryScenario(salary_variation=Decimal("0.05"))
        one, again, other = (employer_file(db, seed=s, scenario=scenario) for s in (1, 1, 2))
        salaries = [Decimal(r["pensionable_salary_sek"]) for r in one.payload["rows"]]
        assert one.payload["rows"] == again.payload["rows"]
        assert one.payload["rows"] != other.payload["rows"]
        assert all(Decimal(36100) <= s <= Decimal(63000) for s in salaries)

    def test_avvikelser_enligt_scenariot_och_facit(self, db):
        sim = employer_file(db, seed=4, scenario=SalaryScenario(missing=1, zero=1, unknown_person=True))
        view = run(db, "import_salary_file", sim.payload)
        assert sim.facit["expected"] == {"valid": 2, "deviations": 1, "missing": 1}
        assert (view.summary.valid, view.summary.deviations, view.summary.missing) == (2, 1, 1)
        [missing] = view.missing
        assert missing.personal_id_number == sim.facit["missing"][0]
        [deviation] = [r for r in view.rows if r.outcome == "deviation"]
        assert (deviation.personal_id_number, deviation.reason) == (sim.facit["unknown"][0], "unknown_person")
        [zero] = [r for r in view.rows if r.personal_id_number == sim.facit["zero"][0]]
        assert (zero.pensionable_salary_sek, zero.premium_preview_sek) == (Decimal("0.00"), Decimal("0.00"))

    def test_rattelse_bara_for_rapporterade(self, db):
        approve(db, employer_file(db))
        sim = employer_file(db, seed=5, scenario=SalaryScenario(corrections=1, correction_change=Decimal("0.10")))
        [row] = sim.payload["rows"]
        assert (row["kind"], row["corrects_version"]) == ("correction", 1)
        assert Decimal(row["pensionable_salary_sek"]) == Decimal(PEOPLE[row["personal_id_number"]][1]) * Decimal("1.1")
        view = run(db, "import_salary_file", sim.payload)
        assert (view.summary.valid, view.summary.corrections, view.summary.missing) == (1, 1, 0)

    def test_omojligt_scenario_stoppas_i_simulatorn(self, db):
        with pytest.raises(ValueError, match="bara 3"):
            employer_file(db, scenario=SalaryScenario(missing=2, zero=2))
        with pytest.raises(ValueError, match="bara 0"):
            employer_file(db, scenario=SalaryScenario(corrections=1))


class TestBankfil:
    @pytest.fixture
    def debit(self, db):
        approve(db, employer_file(db))
        [debit] = invoice(db)
        assert debit.total_sek == Decimal("8443.13")  # 2 025,00 + 4 708,13 + 1 710,00
        return debit

    def test_betalning_i_tid_betalar_raderna(self, db, clock, debit):
        sim, result = bank(db, clock, PaymentBehaviour("on_time", days_after_invoice=3), date(2026, 11, 10))
        assert outcome_of(result) == expected_of(sim, result)
        assert result.paid_premium_rows == 3
        summary = run(db, "get_receivables", {})
        assert (summary.receivables_sek, summary.bank_total_sek, summary.balanced) == (
            Decimal("0.00"), Decimal(sim.facit["total_sek"]), True)
        with db.session_factory() as s:
            paid = s.scalars(select(PremiumTransaction.status).where(PremiumTransaction.period_month == OCTOBER)).all()
        assert set(paid) == {"paid"}

    def test_samma_bankfil_igen_ger_inga_nya_allokeringar(self, db, clock, debit):
        sim, _ = bank(db, clock, PaymentBehaviour("on_time", days_after_invoice=3), date(2026, 11, 10))
        again = run(db, "import_bank_file", sim.payload)  # fall 15
        assert {o.status for o in again.outcomes} == {"already_received"}
        assert run(db, "get_receivables", {}).allocated_sek == Decimal("8443.13")

    def test_delbetalning_och_sedan_resten(self, db, clock, debit):
        sim, result = bank(db, clock, PaymentBehaviour("partial", share=Decimal("0.4")), date(2026, 11, 12))
        assert [e["expected"] for e in sim.facit["events"]] == ["partial"]
        assert result.outcomes[0].allocated_sek == Decimal("3377.25")
        assert run(db, "get_receivables", {}).receivables_sek == Decimal("5065.88")
        rest, result = bank(db, clock, PaymentBehaviour("late", days_late=2), date(2026, 12, 21))
        assert rest.payload["events"][0]["event_id"] != sim.payload["events"][0]["event_id"]
        assert rest.payload["events"][0]["amount_sek"] == "5065.88"
        assert result.paid_premium_rows == 3
        assert run(db, "get_receivables", {}).receivables_sek == Decimal("0.00")

    def test_dubbelbetalning_hamnar_pa_avstamningskontot(self, db, clock, debit):
        sim, result = bank(db, clock, PaymentBehaviour("twice"), date(2026, 11, 12))
        assert outcome_of(result) == expected_of(sim, result)
        assert [o.case_number is not None for o in result.outcomes] == [False, True]
        summary = run(db, "get_receivables", {})
        assert (summary.suspense_sek, summary.receivables_sek, summary.balanced) == (
            Decimal("8443.13"), Decimal("0.00"), True)

    @pytest.mark.parametrize(("kind", "reason"), [("wrong_reference", "unknown_reference"),
                                                  ("wrong_payer", "wrong_payer")])
    def test_fel_referens_eller_betalare(self, db, clock, debit, kind, reason):
        sim, result = bank(db, clock, PaymentBehaviour(kind), date(2026, 11, 12))
        [event_id] = [e["event_id"] for e in sim.payload["events"]]
        assert outcome_of(result) == expected_of(sim, result) == {event_id: f"suspense:{reason}"}
        assert run(db, "get_receivables", {}).receivables_sek == Decimal("8443.13")

    def test_sen_betalning_efter_filens_dag_kommer_inte_med(self, db, clock, debit):
        sim, result = bank(db, clock, PaymentBehaviour("late", days_late=10), date(2026, 12, 10))
        assert sim.empty and result is None
        [pending] = sim.facit["pending"]
        assert (pending["invoice"], pending["open_sek"]) == (debit.invoice_number, "8443.13")

    def test_ingen_betalning_ger_forfallet_arende(self, db, clock, debit):
        sim, _ = bank(db, clock, PaymentBehaviour("none"), date(2026, 12, 10))
        assert sim.empty and sim.facit["pending"][0]["why"] == "betalar inte"
        result = run(db, "check_overdue_invoices", {})
        assert [(a.invoice_number, a.action) for a in result.actions] == [(debit.invoice_number, "created")]


class TestSkiljeMellanSimulatorOchVerksamhet:
    def test_simulatorn_skriver_aldrig_i_databasen(self, db, clock):
        approve(db, employer_file(db))
        invoice(db)
        before = counts(db)
        with db.session_factory() as s:
            salary_file(s, EMPLOYER, OCTOBER, received_date=RECEIVED, seed=9,
                        scenario=SalaryScenario(unknown_person=True))
            bank_file(s, OCTOBER, {EMPLOYER: PaymentBehaviour("twice")}, as_of=date(2026, 11, 12), seed=9)
            assert not (s.new or s.dirty or s.deleted)
        assert counts(db) == before

    def test_facit_skrivs_bredvid_filen_inte_i_den(self, db, tmp_path):
        sim = employer_file(db, scenario=SalaryScenario(missing=1))
        content, facit = sim.write(tmp_path)
        assert content.name == "SIM1-5560000001-202610-S1.json"
        payload = load_payload(content)
        assert payload == sim.payload and "facit" not in payload
        assert '"missing"' in facit.read_text(encoding="utf-8")
        assert run(db, "import_salary_file", payload).summary.missing == 1

    def test_filen_blockeras_om_den_andras_efter_simulatorn(self, db):
        sim = employer_file(db)
        tampered = {**sim.payload, "rows": [{**sim.payload["rows"][0], "pensionable_salary_sek": "1.00"},
                                            *sim.payload["rows"][1:]]}
        from services import BlockedError

        with pytest.raises(BlockedError, match="kontrollsumma"):
            run(db, "import_salary_file", tampered)
        with db.session_factory() as s:
            assert s.scalar(select(func.count()).select_from(InsuredPerson)) >= len(PEOPLE)
