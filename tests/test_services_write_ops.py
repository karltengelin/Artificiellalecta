"""Tjänstelagrets första skrivoperationer (Fas 1f T3) mot testdatabasen.

register_salary_report (PR-ITP1-014), set_policy_paid_up (PR-ITP1-013) och
correct_premium_transaction (PR-ITP1-019). Varje test kontrollerar både
ändringen och att ett misslyckat eller blockerat anrop lämnar data och
händelselogg orörda.

Agentåtkomst prövas mot två regelmappar: de riktiga produktreglerna (PR-ITP1
v1.0 specificerat, inte infört) och en kopia i tmp där kopians README har ett
införandebeslut. De riktiga filerna ändras aldrig.
"""

from __future__ import annotations

import shutil
import threading
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models import (
    BaseAmount,
    Employer,
    InsuredPerson,
    OperationEventRecord,
    Policy,
    PolicyBenefit,
    PolicyState,
    PremiumTransaction,
    SalaryReport,
)
from services import (
    AccessDeniedError,
    Actor,
    AgentAccess,
    ApprovalError,
    BlockedError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
    OperationContext,
    ProductRuleCatalog,
    ServiceLayer,
)
from services.operations import common
from services.rules import default_rules_dir
from skills.calculation.calculate_itp1_premium import calculate_itp1_premium

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 10, 11)
ACTIVE = "198505151234"  # aktiv, premiebetalande AL-000002
FORMER = "199001011234"  # anställningen slutade 2025-12-31, fribrev AL-000001 (conftest)
EMPLOYER = "5560000001"
OTHER_EMPLOYER = "5560000002"

HUMAN = OperationContext(actor=Actor.human("karl"), reason="Enligt underlag från arbetsgivaren")
AGENT = OperationContext(actor=Actor.agent("case_handler", team="forsakring"), reason="Lönefil inkom", run_id="run-11")
APPROVER = OperationContext(actor=Actor.human("karl"))


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


def premium(salary: str, ibb: str, period: date) -> tuple[Decimal, dict]:
    calc = calculate_itp1_premium(Decimal(salary), Decimal(ibb), birth_date=date(1985, 5, 15), period_month=period)
    return calc.total_premium_sek, calc.calculation_basis


@pytest.fixture
def db(insurance_db):
    return seed_active(insurance_db)


def seed_active(insurance_db):
    """conftest-beståndet plus en aktiv försäkrad med premier i olika lägen."""
    with insurance_db.session_factory() as s:
        employer = s.scalar(select(Employer).where(Employer.org_number == EMPLOYER))
        s.add(Employer(org_number=OTHER_EMPLOYER, name="Annat AB", affiliation_date=date(2010, 1, 1)))
        person = InsuredPerson(
            personal_id_number=ACTIVE, first_name="Aktiv", last_name="Anställd", employer_id=employer.id,
            employment_start_date=date(2020, 1, 1), monthly_salary_sek=Decimal("45000"),
            employment_rate=Decimal("100"), itp1_start_date=date(2020, 1, 1), status="active",
        )
        s.add(person)
        s.flush()
        policy = Policy(policy_number="AL-000002", insured_person_id=person.id,
                        signed_date=date(2020, 1, 1), start_date=date(2020, 1, 1))
        s.add(policy)
        s.flush()
        benefit = PolicyBenefit(policy_id=policy.id, benefit_type="retirement_dc", start_date=date(2020, 1, 1))
        s.add(benefit)
        s.add(PolicyState(policy_id=policy.id, state="premium_paying", valid_from=date(2020, 1, 1)))
        s.flush()
        rows = {}
        for period, ibb, status in (
            (date(2025, 12, 1), "80600", "paid"),
            (date(2026, 4, 1), "83400", "paid"),
            (date(2026, 5, 1), "83400", "invoiced"),
            (date(2026, 6, 1), "83400", "pending"),
        ):
            amount, basis = premium("45000", ibb, period)
            tx = PremiumTransaction(
                benefit_id=benefit.id, period_month=period, transaction_type="premium",
                pensionable_salary_sek=Decimal("45000"), amount_sek=amount, calculation_basis=basis,
                status=status, paid_date=date(period.year + period.month // 12, period.month % 12 + 1, 15)
                if status == "paid" else None,
            )
            s.add(tx)
            s.flush()
            rows[period] = tx.id
        insurance_db.active = person.id
        insurance_db.active_policy = policy.id
        insurance_db.active_benefit = benefit.id
        insurance_db.tx = rows
        insurance_db.employer = employer.id
    return insurance_db


def adopted_rules(tmp_path, valid_from: str = "2026-10-01") -> ProductRuleCatalog:
    """Kopia av de riktiga produktreglerna med införandebeslut i kopians README."""
    target = tmp_path / "produktregler"
    shutil.copytree(default_rules_dir(), target)
    readme = target / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + f"\n> **Införandebeslut:** B-999 | **Gäller från:** {valid_from}\n",
        encoding="utf-8",
    )
    return ProductRuleCatalog(target, today=TODAY)


def make_service(db, rules: ProductRuleCatalog | None = None) -> ServiceLayer:
    return ServiceLayer(session_factory=db.session_factory, rules=rules or ProductRuleCatalog(today=TODAY))


def rows(db, model, *where):
    with db.session_factory() as s:
        return s.scalars(select(model).where(*where)).all()


def events(db, outcome=None, operation=None):
    found = rows(db, OperationEventRecord)
    return [
        e for e in sorted(found, key=lambda e: e.occurred_at)
        if (outcome is None or e.outcome == outcome) and (operation is None or e.operation == operation)
    ]


def report(month: str = "2026-07-01", salary: str = "45000", **overrides) -> dict:
    data = {
        "personal_id_number": ACTIVE, "employer_org_number": EMPLOYER, "period_month": month,
        "pensionable_salary_sek": salary, "kind": "new", "source": "employer",
        "source_reference": f"LON-{month[:7]}", "received_date": "2026-10-05",
    }
    return data | overrides


# --- register_salary_report -------------------------------------------------------------


class TestLoneunderlag:
    def test_ny_rapport_sparas_som_version_1_och_loggas_med_regelstatus(self, db):
        out = make_service(db).execute("register_salary_report", HUMAN, report()).output
        assert (out.version, out.kind, out.period_month, out.previous_salary_sek) == (1, "new", date(2026, 7, 1), None)
        (saved,) = rows(db, SalaryReport)
        assert (saved.version, saved.supersedes_id, saved.pensionable_salary_sek) == (1, None, Decimal("45000.00"))
        assert (saved.source, saved.source_reference, saved.received_date) == ("employer", "LON-2026-07", date(2026, 10, 5))
        (event,) = events(db, "executed", "register_salary_report")
        assert event.output["report_id"] == str(saved.id)
        assert event.rules == ["PR-ITP1-013", "PR-ITP1-014", "PR-ITP1-017"]
        assert "PR-ITP1-014 v1.0 specificerad" in event.detail and "ej infört" in event.detail
        assert rows(db, PremiumTransaction, PremiumTransaction.period_month == date(2026, 7, 1)) == []  # ingen premie

    def test_uttrycklig_noll_skiljs_fran_saknad_rapport(self, db):
        service = make_service(db)
        service.execute("register_salary_report", HUMAN, report(month="2026-08-01", salary="0"))
        out = service.execute("get_salary_reports", HUMAN, {"personal_id_number": ACTIVE}).output
        assert [(r.period_month, r.pensionable_salary_sek) for r in out.reports] == [(date(2026, 8, 1), Decimal("0.00"))]
        # juli saknar rapport – den finns inte som rad, och blir inte noll
        assert all(r.period_month != date(2026, 7, 1) for r in out.reports)

    def test_dubblett_ersatter_inte_rapporten(self, db):
        service = make_service(db)
        service.execute("register_salary_report", HUMAN, report())
        with pytest.raises(ConflictError, match="finns redan"):
            service.execute("register_salary_report", HUMAN, report(salary="46000", source_reference="LON-ANNAN"))
        (saved,) = rows(db, SalaryReport)
        assert saved.pensionable_salary_sek == Decimal("45000.00")
        assert len(events(db, "executed", "register_salary_report")) == 1

    def test_samma_avsandarreferens_registreras_inte_tva_ganger(self, db):
        service = make_service(db)
        service.execute("register_salary_report", HUMAN, report())
        with pytest.raises(ConflictError, match="LON-2026-07 är redan registrerad"):
            service.execute("register_salary_report", HUMAN, report(month="2026-08-01", source_reference="LON-2026-07"))

    def test_rattelse_blir_ny_version_och_tidigare_underlag_bevaras(self, db):
        service = make_service(db)
        service.execute("register_salary_report", HUMAN, report())
        out = service.execute(
            "register_salary_report", HUMAN,
            report(salary="47500", kind="correction", corrects_version=1, source_reference="LON-2026-07-R1"),
        ).output
        assert (out.version, out.previous_salary_sek, out.affected_premiums) == (2, Decimal("45000.00"), [])
        listed = service.execute("get_salary_reports", HUMAN, {"personal_id_number": ACTIVE}).output.reports
        assert [(r.version, r.pensionable_salary_sek, r.current) for r in listed] == [
            (1, Decimal("45000.00"), False), (2, Decimal("47500.00"), True),
        ]
        v1, v2 = sorted(rows(db, SalaryReport), key=lambda r: r.version)
        assert v2.supersedes_id == v1.id

    def test_rattelse_maste_utga_fran_gallande_version_och_andra_lonen(self, db):
        service = make_service(db)
        service.execute("register_salary_report", HUMAN, report())
        correction = report(salary="47500", kind="correction", corrects_version=1, source_reference=None)
        service.execute("register_salary_report", HUMAN, correction)
        with pytest.raises(ConflictError, match="inte den gällande"):  # samma rättelse en gång till
            service.execute("register_salary_report", HUMAN, correction)
        with pytest.raises(ConflictError, match="ändrar inte lönen"):
            service.execute("register_salary_report", HUMAN, correction | {"corrects_version": 2})
        with pytest.raises(ConflictError, match="ingen rapport"):
            service.execute("register_salary_report", HUMAN, correction | {"period_month": "2026-08-01"})
        assert len(rows(db, SalaryReport)) == 2

    def test_rattelse_av_manad_med_premie_redovisar_premien_men_raknar_inte_om_den(self, db):
        with db.session_factory() as s:  # underlaget för juni har registrerats tidigare
            s.add(SalaryReport(insured_person_id=db.active, employer_id=db.employer, period_month=date(2026, 6, 1),
                               version=1, pensionable_salary_sek=Decimal("45000"), source="employer",
                               received_date=date(2026, 7, 2)))
        out = make_service(db).execute(
            "register_salary_report", HUMAN,
            report(month="2026-06-01", salary="50000", kind="correction", corrects_version=1, source_reference=None),
        ).output
        (affected,) = out.affected_premiums
        assert (affected.transaction_id, affected.amount_sek) == (str(db.tx[date(2026, 6, 1)]), Decimal("2025.00"))
        assert "correct_premium_transaction" in out.note
        (june,) = rows(db, PremiumTransaction, PremiumTransaction.id == db.tx[date(2026, 6, 1)])
        assert (june.amount_sek, june.pensionable_salary_sek) == (Decimal("2025.00"), Decimal("45000.00"))

    @pytest.mark.parametrize(
        ("overrides", "match"),
        [
            ({"period_month": "2026-11-01"}, "har inte kommit"),
            ({"employer_org_number": OTHER_EMPLOYER}, "annan arbetsgivare"),
            ({"period_month": "2019-12-01"}, "före ITP1-tillhörighetens start"),
            ({"received_date": "2026-10-12"}, "Mottagningsdagen ligger i framtiden"),
            ({"received_date": "2026-06-30"}, "före rapportmånaden"),
            ({"period_month": "2026-04-01", "source_reference": None}, "redan premie"),
            ({"personal_id_number": FORMER, "period_month": "2026-01-01"}, "efter anställningens slut"),
        ],
    )
    def test_ej_stodda_fall_blockeras_utan_andring(self, db, overrides, match):
        with pytest.raises(BlockedError, match=match):
            make_service(db).execute("register_salary_report", HUMAN, report(**overrides))
        assert rows(db, SalaryReport) == []
        assert events(db, "executed") == []

    def test_avliden_forsakrad_blockeras(self, db):
        with db.session_factory() as s:
            s.get(InsuredPerson, db.active).status = "deceased"
        with pytest.raises(BlockedError, match="avliden"):
            make_service(db).execute("register_salary_report", HUMAN, report())

    @pytest.mark.parametrize(
        "overrides",
        [{"pensionable_salary_sek": "-1"}, {"kind": "correction"}, {"corrects_version": 1},
         {"pensionable_salary_sek": "100.001"}, {"personal_id_number": "1985"}],
    )
    def test_ogiltig_indata(self, db, overrides):
        with pytest.raises(InvalidInputError):
            make_service(db).execute("register_salary_report", HUMAN, report(**overrides))

    def test_okand_forsakrad_eller_arbetsgivare(self, db):
        with pytest.raises(NotFoundError):
            make_service(db).execute("register_salary_report", HUMAN, report(personal_id_number="190001010000"))
        with pytest.raises(NotFoundError):
            make_service(db).execute("register_salary_report", HUMAN, report(employer_org_number="5569999999"))

    def test_databasen_tillater_inte_tva_rapporter_med_samma_version(self, db):
        with pytest.raises(IntegrityError), db.session_factory() as s:
            for _ in range(2):
                s.add(SalaryReport(insured_person_id=db.active, employer_id=db.employer, period_month=date(2026, 7, 1),
                                   version=1, pensionable_salary_sek=Decimal("1"), source="manual",
                                   received_date=date(2026, 8, 1)))
            s.flush()


class TestLoneunderlagSamtidigt:
    def test_samtidiga_identiska_rapporter_ger_en_rad(self, insurance_file_db, monkeypatch):
        db = insurance_file_db
        with db.session_factory() as s:
            s.get(InsuredPerson, db.ids.person).employment_end_date = None
            s.get(InsuredPerson, db.ids.person).status = "active"
        service = make_service(db)
        payload = report(personal_id_number=FORMER, month="2026-09-01", source_reference=None)
        results = []
        barrier = threading.Barrier(2)

        def run():
            barrier.wait()
            try:
                results.append(service.execute("register_salary_report", HUMAN, payload))
            except Exception as exc:  # noqa: BLE001
                results.append(exc)

        threads = [threading.Thread(target=run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)
        assert sorted(type(r).__name__ for r in results) == ["ConflictError", "OperationResult"]
        assert len(rows(db, SalaryReport)) == 1


# --- set_policy_paid_up --------------------------------------------------------------


class TestFribrev:
    def test_avanmalan_stanger_premieperioden_och_oppnar_fribrev(self, db):
        service = make_service(db)
        capital_before = service.execute("get_insured_overview", HUMAN, {"personal_id_number": ACTIVE}).output
        out = service.execute(
            "set_policy_paid_up", HUMAN, {"policy_number": "AL-000002", "employment_end_date": "2026-09-30"}
        ).output
        assert (out.paid_up_from, out.closed_period.valid_to, out.employment_end_registered) == (
            date(2026, 10, 1), date(2026, 9, 30), True,
        )
        assert (out.person_status_before, out.person_status_after) == ("active", "terminated")
        states = sorted(rows(db, PolicyState, PolicyState.policy_id == db.active_policy), key=lambda s: s.valid_from)
        assert [(s.state, s.valid_from, s.valid_to) for s in states] == [
            ("premium_paying", date(2020, 1, 1), date(2026, 9, 30)),
            ("paid_up", date(2026, 10, 1), None),
        ]
        (person,) = rows(db, InsuredPerson, InsuredPerson.id == db.active)
        assert (person.employment_end_date, person.status) == (date(2026, 9, 30), "terminated")
        # Läsningen visar nytt läge och oförändrat kapital
        overview = service.execute("get_insured_overview", HUMAN, {"personal_id_number": ACTIVE}).output
        (policy,) = overview.policies
        assert (policy.current_state.state, policy.current_state.valid_from) == ("paid_up", date(2026, 10, 1))
        assert overview.total_capital_sek == capital_before.total_capital_sek
        (event,) = events(db, "executed", "set_policy_paid_up")
        assert event.output["paid_up_from"] == "2026-10-01" and "PR-ITP1-013" in event.detail

    def test_upprepat_anrop_andrar_inget(self, db):
        service = make_service(db)
        payload = {"policy_number": "AL-000002", "employment_end_date": "2026-09-30"}
        service.execute("set_policy_paid_up", HUMAN, payload)
        with pytest.raises(ConflictError, match="redan fribrev"):
            service.execute("set_policy_paid_up", HUMAN, payload)
        assert len(rows(db, PolicyState, PolicyState.policy_id == db.active_policy)) == 2
        assert len(events(db, "executed", "set_policy_paid_up")) == 1

    @pytest.mark.parametrize(
        ("end", "match"),
        [
            ("2026-10-11", "ligger i framtiden"),  # fribrev från i morgon
            ("2026-12-31", "ligger i framtiden"),
            ("2019-12-31", "före anställningens start"),
            ("2026-03-31", "premie för 2026-04"),
        ],
    )
    def test_datumgranser_och_senare_premie_blockeras(self, db, end, match):
        with pytest.raises(BlockedError, match=match):
            make_service(db).execute("set_policy_paid_up", HUMAN, {"policy_number": "AL-000002", "employment_end_date": end})
        self.assert_unchanged(db)

    def test_lonunderlag_efter_slutdagen_blockeras(self, db):
        make_service(db).execute("register_salary_report", HUMAN, report(month="2026-09-01"))
        with pytest.raises(BlockedError, match="löneunderlag för 2026-09"):
            make_service(db).execute(
                "set_policy_paid_up", HUMAN, {"policy_number": "AL-000002", "employment_end_date": "2026-08-31"}
            )
        self.assert_unchanged(db)

    def test_pension_startad_blockeras_och_uttagslaget_rors_inte(self, db):
        with db.session_factory() as s:
            state = s.scalar(select(PolicyState).where(PolicyState.policy_id == db.active_policy))
            state.valid_to = date(2026, 5, 31)
            s.flush()
            s.add(PolicyState(policy_id=db.active_policy, state="in_payout", valid_from=date(2026, 6, 1)))
        with pytest.raises(BlockedError, match="uttag"):
            make_service(db).execute(
                "set_policy_paid_up", HUMAN, {"policy_number": "AL-000002", "employment_end_date": "2026-09-30"}
            )
        open_state = rows(db, PolicyState, PolicyState.policy_id == db.active_policy, PolicyState.valid_to.is_(None))
        assert [s.state for s in open_state] == ["in_payout"]

    def test_annat_registrerat_slutdatum_ar_en_konflikt(self, db):
        with db.session_factory() as s:
            s.get(InsuredPerson, db.active).employment_end_date = date(2026, 8, 31)
        with pytest.raises(ConflictError, match="redan registrerat som 2026-08-31"):
            make_service(db).execute(
                "set_policy_paid_up", HUMAN, {"policy_number": "AL-000002", "employment_end_date": "2026-09-30"}
            )

    def test_fler_premiebetalande_forsakringar_blockeras(self, db):
        with db.session_factory() as s:
            other = Policy(policy_number="AL-000003", insured_person_id=db.active,
                           signed_date=date(2024, 1, 1), start_date=date(2024, 1, 1))
            s.add(other)
            s.flush()
            s.add(PolicyState(policy_id=other.id, state="premium_paying", valid_from=date(2024, 1, 1)))
        with pytest.raises(BlockedError, match="AL-000003"):
            make_service(db).execute(
                "set_policy_paid_up", HUMAN, {"policy_number": "AL-000002", "employment_end_date": "2026-09-30"}
            )
        self.assert_unchanged(db)

    def test_hela_tidslinjen_valideras(self, db):
        with db.session_factory() as s:  # trasig historik: ett gammalt fribrev inne i premieperioden
            s.add(PolicyState(policy_id=db.active_policy, state="paid_up",
                              valid_from=date(2026, 9, 15), valid_to=date(2026, 9, 20)))
        with pytest.raises(BlockedError, match="överlappa"):
            make_service(db).execute(
                "set_policy_paid_up", HUMAN, {"policy_number": "AL-000002", "employment_end_date": "2026-09-30"}
            )
        self.assert_unchanged(db, states=2)

    def test_okand_forsakring(self, db):
        with pytest.raises(NotFoundError):
            make_service(db).execute("set_policy_paid_up", HUMAN, {"policy_number": "AL-999999",
                                                                   "employment_end_date": "2026-09-30"})

    @staticmethod
    def assert_unchanged(db, states: int = 1) -> None:
        found = rows(db, PolicyState, PolicyState.policy_id == db.active_policy)
        assert len(found) == states
        assert [s.state for s in found if s.valid_to is None] == ["premium_paying"]
        (person,) = rows(db, InsuredPerson, InsuredPerson.id == db.active)
        assert (person.employment_end_date, person.status) == (None, "active")
        assert events(db, "executed", "set_policy_paid_up") == []


# --- correct_premium_transaction -----------------------------------------------------------


def correction(tx_id, salary: str, reference: str = "Rättat lönebesked") -> dict:
    return {"transaction_id": str(tx_id), "corrected_salary_sek": salary, "basis_reference": reference}


class TestPremierattelse:
    def test_ej_mottagen_premie_far_lankad_rattelserad_och_ursprunget_bevaras(self, db):
        service = make_service(db)
        june = db.tx[date(2026, 6, 1)]
        out = service.execute("correct_premium_transaction", HUMAN, correction(june, "50000")).output
        # 4,5 % av 50 000 = 2 250,00 mot tidigare 2 025,00
        assert (out.case, out.previous_total_sek, out.corrected_total_sek, out.difference_sek) == (
            "unreceived_claim", Decimal("2025.00"), Decimal("2250.00"), Decimal("225.00"),
        )
        (original,) = rows(db, PremiumTransaction, PremiumTransaction.id == june)
        assert (original.amount_sek, original.status, original.pensionable_salary_sek) == (
            Decimal("2025.00"), "pending", Decimal("45000.00"),
        )
        (adjustment,) = rows(db, PremiumTransaction, PremiumTransaction.corrects_transaction_id == june)
        assert (adjustment.transaction_type, adjustment.amount_sek, adjustment.status) == (
            "adjustment", Decimal("225.00"), "pending",
        )
        assert adjustment.calculation_basis["basis_reference"] == "Rättat lönebesked"
        assert adjustment.calculation_basis["ibb_year"] == 2026
        (event,) = events(db, "executed", "correct_premium_transaction")
        assert event.output["adjustment_transaction_id"] == str(adjustment.id)

    def test_kredit_pa_fakturerad_men_ej_betald_premie(self, db):
        out = make_service(db).execute(
            "correct_premium_transaction", HUMAN, correction(db.tx[date(2026, 5, 1)], "40000")
        ).output
        assert (out.case, out.difference_sek, out.received_sek) == ("unreceived_claim", Decimal("-225.00"), Decimal("0"))

    def test_tillagg_pa_mottagen_premie_blir_fordran_och_kapitalet_ar_oforandrat(self, db):
        service = make_service(db)
        before = service.execute("get_premium_history", HUMAN, {"policy_number": "AL-000002"}).output
        out = service.execute("correct_premium_transaction", HUMAN, correction(db.tx[date(2026, 4, 1)], "50000")).output
        assert (out.case, out.difference_sek, out.received_sek) == (
            "additional_premium", Decimal("225.00"), Decimal("2025.00"),
        )
        after = service.execute("get_premium_history", HUMAN, {"policy_number": "AL-000002"}).output
        assert after.count == before.count + 1
        assert after.total_paid_sek == before.total_paid_sek  # kapital först när tillägget tas emot
        linked = [r for r in after.transactions if r.corrects_transaction_id == str(db.tx[date(2026, 4, 1)])]
        assert [(r.transaction_type, r.amount_sek, r.status) for r in linked] == [
            ("adjustment", Decimal("225.00"), "pending"),
        ]
        overview = service.execute("get_insured_overview", HUMAN, {"personal_id_number": ACTIVE}).output
        assert overview.total_capital_sek == before.total_paid_sek

    def test_minskning_av_mottagen_premie_blockeras(self, db):
        with pytest.raises(BlockedError, match="spårad kapitalandel"):
            make_service(db).execute("correct_premium_transaction", HUMAN, correction(db.tx[date(2026, 4, 1)], "40000"))
        assert rows(db, PremiumTransaction, PremiumTransaction.corrects_transaction_id.is_not(None)) == []
        assert events(db, "executed") == []

    def test_ursprungsmanadens_ibb_anvands(self, db):
        out = make_service(db).execute(
            "correct_premium_transaction", HUMAN, correction(db.tx[date(2025, 12, 1)], "60000")
        ).output
        # 2025: B1 = 7,5 × 80 600 / 12 = 50 375 → 2 266,88 + 30 % × 9 625 = 2 887,50 → 5 154,38
        assert (out.income_base_amount_sek, out.corrected_total_sek) == (Decimal("80600"), Decimal("5154.38"))
        assert out.difference_sek == Decimal("3129.38")
        with_2026_ibb, _ = premium("60000", "83400", date(2025, 12, 1))
        assert with_2026_ibb != out.corrected_total_sek

    def test_upprepad_rattelse_ger_inget_nytt_ekonomiskt_utfall(self, db):
        service = make_service(db)
        payload = correction(db.tx[date(2026, 6, 1)], "50000")
        service.execute("correct_premium_transaction", HUMAN, payload)
        with pytest.raises(ConflictError, match="redan det rättade underlaget"):
            service.execute("correct_premium_transaction", HUMAN, payload)
        assert len(rows(db, PremiumTransaction, PremiumTransaction.corrects_transaction_id.is_not(None))) == 1

    def test_ny_rattelse_bygger_pa_tidigare_rattelser(self, db):
        service = make_service(db)
        june = db.tx[date(2026, 6, 1)]
        service.execute("correct_premium_transaction", HUMAN, correction(june, "50000"))
        out = service.execute("correct_premium_transaction", HUMAN, correction(june, "55000", "Andra rättelsen")).output
        # 55 000 > B1 52 125: 2 345,63 + 30 % × 2 875 = 862,50 → 3 208,13; tidigare 2 025 + 225
        assert (out.previous_total_sek, out.corrected_total_sek, out.difference_sek) == (
            Decimal("2250.00"), Decimal("3208.13"), Decimal("958.13"),
        )
        linked = rows(db, PremiumTransaction, PremiumTransaction.corrects_transaction_id == june)
        assert sum(r.amount_sek for r in linked) + Decimal("2025.00") == Decimal("3208.13")

    def test_registrerat_loneunderlag_maste_stamma(self, db):
        with db.session_factory() as s:
            s.add(SalaryReport(insured_person_id=db.active, employer_id=db.employer, period_month=date(2026, 6, 1),
                               version=1, pensionable_salary_sek=Decimal("48000"), source="employer",
                               received_date=date(2026, 7, 2)))
        service = make_service(db)
        with pytest.raises(BlockedError, match="Rätta först underlaget"):
            service.execute("correct_premium_transaction", HUMAN, correction(db.tx[date(2026, 6, 1)], "50000"))
        out = service.execute("correct_premium_transaction", HUMAN, correction(db.tx[date(2026, 6, 1)], "48000")).output
        assert out.corrected_total_sek == Decimal("2160.00")
        (adjustment,) = rows(db, PremiumTransaction, PremiumTransaction.corrects_transaction_id == db.tx[date(2026, 6, 1)])
        assert adjustment.calculation_basis["salary_report"]["version"] == 1

    def test_ibb_som_avviker_fran_radens_underlag_blockeras(self, db):
        with db.session_factory() as s:
            s.get(BaseAmount, 2026).income_base_amount_sek = Decimal("83500")
        with pytest.raises(BlockedError, match="avviker"):
            make_service(db).execute("correct_premium_transaction", HUMAN, correction(db.tx[date(2026, 6, 1)], "50000"))

    def test_rader_som_inte_kan_rattas_spararbart_blockeras(self, db):
        service = make_service(db)
        with db.session_factory() as s:
            former = {(t.period_month, t.transaction_type): t.id for t in s.scalars(
                select(PremiumTransaction).where(PremiumTransaction.benefit_id == db.ids.benefit))}
        with pytest.raises(BlockedError, match="justeringar utan länk"):
            service.execute("correct_premium_transaction", HUMAN, correction(former[(date(2025, 12, 1), "premium")], "1"))
        with pytest.raises(BlockedError, match="saknar beräkningsunderlag"):
            service.execute("correct_premium_transaction", HUMAN, correction(former[(date(2025, 11, 1), "premium")], "1"))
        with pytest.raises(BlockedError, match="Bara ordinarie premierader"):
            service.execute("correct_premium_transaction", HUMAN, correction(former[(date(2025, 12, 1), "fee")], "1"))
        with pytest.raises(NotFoundError):
            service.execute("correct_premium_transaction", HUMAN,
                            correction("00000000-0000-0000-0000-000000000000", "1"))
        assert events(db, "executed") == []

    def test_flera_premierader_samma_manad_blockeras(self, db):
        with db.session_factory() as s:
            other = Policy(policy_number="AL-000003", insured_person_id=db.active,
                           signed_date=date(2024, 1, 1), start_date=date(2024, 1, 1))
            s.add(other)
            s.flush()
            benefit = PolicyBenefit(policy_id=other.id, benefit_type="retirement_dc", start_date=date(2024, 1, 1))
            s.add(benefit)
            s.flush()
            amount, basis = premium("45000", "83400", date(2026, 6, 1))
            s.add(PremiumTransaction(benefit_id=benefit.id, period_month=date(2026, 6, 1), transaction_type="premium",
                                     pensionable_salary_sek=Decimal("45000"), amount_sek=amount,
                                     calculation_basis=basis, status="pending"))
        with pytest.raises(BlockedError, match="PR-ITP1-015"):
            make_service(db).execute("correct_premium_transaction", HUMAN, correction(db.tx[date(2026, 6, 1)], "50000"))

    def test_avliden_forsakrad_blockeras(self, db):
        with db.session_factory() as s:
            s.get(InsuredPerson, db.active).status = "deceased"
        with pytest.raises(BlockedError, match="PR-ITP1-010"):
            make_service(db).execute("correct_premium_transaction", HUMAN, correction(db.tx[date(2026, 6, 1)], "50000"))

    def test_databasen_tillater_bara_lank_fran_adjustment(self, db):
        with pytest.raises(IntegrityError), db.session_factory() as s:
            s.add(PremiumTransaction(benefit_id=db.active_benefit, period_month=date(2026, 7, 1),
                                     transaction_type="premium", amount_sek=Decimal("1"),
                                     corrects_transaction_id=db.tx[date(2026, 6, 1)]))
            s.flush()


# --- agentåtkomst ------------------------------------------------------------------------------


class TestAgentatkomst:
    WRITES = ("register_salary_report", "set_policy_paid_up", "correct_premium_transaction")

    def test_utan_infort_paket_ar_alla_skrivningar_endast_handlaggare(self, db):
        service = make_service(db)
        for name in self.WRITES:
            decision = service.decision(name)
            assert decision.effective == AgentAccess.HUMAN_ONLY, name
        assert any("PR-ITP1-014 (specificerad)" in r for r in service.decision("register_salary_report").reasons)
        assert service.decision("register_salary_report").registered == AgentAccess.APPROVAL

    def test_agent_nekas_och_forsoket_loggas_utan_andring(self, db):
        service = make_service(db)
        with pytest.raises(AccessDeniedError):
            service.execute("register_salary_report", AGENT, report())
        with pytest.raises(AccessDeniedError):
            service.execute("set_policy_paid_up", AGENT, {"policy_number": "AL-000002",
                                                          "employment_end_date": "2026-09-30"})
        assert rows(db, SalaryReport) == []
        assert [e.outcome for e in events(db)] == ["denied", "denied"]

    def test_med_infort_och_giltigt_paket_foljer_registret(self, db, tmp_path):
        service = make_service(db, adopted_rules(tmp_path))
        assert service.decision("register_salary_report").effective == AgentAccess.APPROVAL
        assert service.decision("set_policy_paid_up").effective == AgentAccess.APPROVAL
        assert service.decision("correct_premium_transaction").effective == AgentAccess.HUMAN_ONLY

    def test_infort_paket_med_senare_giltighetsdag_stanger_fortfarande(self, db, tmp_path):
        service = make_service(db, adopted_rules(tmp_path, valid_from="2026-11-01"))
        decision = service.decision("register_salary_report")
        assert decision.effective == AgentAccess.HUMAN_ONLY
        assert any("kommande, gäller från 2026-11-01" in r for r in decision.reasons)

    def test_agentforslag_godkanns_och_verkstalls_en_gang(self, db, tmp_path):
        service = make_service(db, adopted_rules(tmp_path))
        result = service.execute("register_salary_report", AGENT, report())
        assert result.pending and rows(db, SalaryReport) == []  # provkörd, inget sparat
        done = service.approve(result.approval_id, APPROVER, note="Stämmer med lönefilen")
        assert done.output.version == 1
        with pytest.raises(ApprovalError, match="redan approved"):
            service.approve(result.approval_id, APPROVER)
        assert len(rows(db, SalaryReport)) == 1
        (executed,) = events(db, "executed", "register_salary_report")
        assert (executed.actor_id, executed.proposed_by, executed.approval_id, executed.run_id) == (
            "karl", "case_handler", result.approval_id, "run-11",
        )
        assert "infört B-999" in executed.detail

    def test_agentforslag_som_inte_galler_nu_avvisas_direkt(self, db, tmp_path):
        service = make_service(db, adopted_rules(tmp_path))
        with pytest.raises(BlockedError, match="har inte kommit"):
            service.execute("register_salary_report", AGENT, report(month="2026-12-01"))
        assert service.approvals.list() == [] and events(db) == []

    def test_godkant_forslag_provas_mot_aktuellt_lage(self, db, tmp_path):
        service = make_service(db, adopted_rules(tmp_path))
        approval_id = service.execute("register_salary_report", AGENT, report()).approval_id
        service.execute("register_salary_report", HUMAN, report(source_reference="LON-HANDLAGGARE"))
        with pytest.raises(ConflictError, match="finns redan"):
            service.approve(approval_id, APPROVER)
        assert service.approvals.get(approval_id).status == "pending"
        service.reject(approval_id, APPROVER, note="Redan registrerad av handläggare")
        assert len(rows(db, SalaryReport)) == 1

    def test_fribrev_som_agentforslag(self, db, tmp_path):
        service = make_service(db, adopted_rules(tmp_path))
        payload = {"policy_number": "AL-000002", "employment_end_date": "2026-09-30"}
        approval_id = service.execute("set_policy_paid_up", AGENT, payload).approval_id
        TestFribrev.assert_unchanged(db)  # provkörningen ändrade inget
        service.approve(approval_id, APPROVER)
        assert [s.state for s in rows(db, PolicyState, PolicyState.policy_id == db.active_policy,
                                      PolicyState.valid_to.is_(None))] == ["paid_up"]

    def test_skrivoperationerna_blir_strikta_verktyg_nar_paketet_galler(self, db, tmp_path):
        from ai import ToolSpec

        service = make_service(db, adopted_rules(tmp_path))
        visible = service.operations_for_agents()
        names = {op.name for op in visible}
        assert {"register_salary_report", "set_policy_paid_up", "get_salary_reports"} <= names
        assert "correct_premium_transaction" not in names  # HUMAN_ONLY visas aldrig
        for op in visible:
            tool = ToolSpec.from_model(op.name, op.description, op.input_model)
            assert tool.strict and tool.parameters["additionalProperties"] is False

    def test_agent_nekas_alltid_premierattelse(self, db, tmp_path):
        service = make_service(db, adopted_rules(tmp_path))
        with pytest.raises(AccessDeniedError):
            service.execute("correct_premium_transaction", AGENT, correction(db.tx[date(2026, 6, 1)], "50000"))
        assert rows(db, PremiumTransaction, PremiumTransaction.corrects_transaction_id.is_not(None)) == []
        (denied,) = events(db, "denied")
        assert denied.operation == "correct_premium_transaction"
