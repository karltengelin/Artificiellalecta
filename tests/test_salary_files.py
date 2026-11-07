"""Löneunderlagsfil: intag, granskning och godkännande (paket A steg 2, B-046, P1-PREMIE-001 §4.1–4.2 och §7).

Fallen numreras som i designstoppets §7. Premieperiod 2026-10, IBB 83 400 kr och
produktparametrarnas startvärden.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models import (
    Case,
    Employer,
    InsuredPerson,
    Policy,
    PolicyBenefit,
    PolicyState,
    PremiumTransaction,
    SalaryFile,
    SalaryReport,
)
from services import (
    Actor,
    AgentAccess,
    BlockedError,
    ConflictError,
    OperationContext,
    ProductRuleCatalog,
    ServiceLayer,
)
from services.operations import common
from services.operations.salary_files import file_checksum

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 11, 7)
EMPLOYER = "5560000001"
OTHER_EMPLOYER = "5560000002"
ACTIVE = "198505151234"
SECOND = "197803031234"
LEAVER = "199203031234"  # anställningen slutar 2026-10-15
OTHER = "198808081234"  # ansluten via annan arbetsgivare
UNKNOWN = "200001011234"
OCTOBER = date(2026, 10, 1)
#: Seedens genererade historik ligger före första operativa period
OPERATIVE = PremiumTransaction.period_month >= OCTOBER
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Arbetsgivarens lönefil för oktober")


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


def _person(s, employer, pnr, policy_number, end=None):
    person = InsuredPerson(
        personal_id_number=pnr, first_name="Test", last_name=pnr[-4:], employer_id=employer.id,
        employment_start_date=date(2020, 1, 1), employment_end_date=end, monthly_salary_sek=Decimal(45000),
        employment_rate=Decimal(100), itp1_start_date=date(2020, 1, 1),
        status="terminated" if end else "active",
    )
    s.add(person)
    s.flush()
    policy = Policy(policy_number=policy_number, insured_person_id=person.id,
                    signed_date=date(2020, 1, 1), start_date=date(2020, 1, 1))
    s.add(policy)
    s.flush()
    s.add(PolicyBenefit(policy_id=policy.id, benefit_type="retirement_dc", start_date=date(2020, 1, 1)))
    s.add(PolicyState(policy_id=policy.id, state="premium_paying", valid_from=date(2020, 1, 1), valid_to=end))
    if end:
        s.flush()
        s.add(PolicyState(policy_id=policy.id, state="paid_up", valid_from=date(2026, 10, 16)))
    s.flush()
    return person


@pytest.fixture
def db(insurance_db):
    with insurance_db.session_factory() as s:
        employer = s.scalar(select(Employer).where(Employer.org_number == EMPLOYER))
        other = Employer(org_number=OTHER_EMPLOYER, name="Annat AB", affiliation_date=date(2010, 1, 1))
        s.add(other)
        s.flush()
        _person(s, employer, ACTIVE, "AL-000010")
        _person(s, employer, SECOND, "AL-000011")
        _person(s, employer, LEAVER, "AL-000012", end=date(2026, 10, 15))
        _person(s, other, OTHER, "AL-000013")
        s.commit()
    return insurance_db


def service(db) -> ServiceLayer:
    return ServiceLayer(session_factory=db.session_factory, rules=ProductRuleCatalog(today=TODAY))


def row(pnr, amount="45000", month=OCTOBER, kind="new", corrects=None):
    return {"personal_id_number": pnr, "period_month": month.isoformat(), "pensionable_salary_sek": amount,
            "kind": kind, "corrects_version": corrects}


def salary_file(rows, ref="LON-2026-10", period=OCTOBER, received=date(2026, 11, 5), checksum=None):
    return {
        "employer_org_number": EMPLOYER, "period_month": period.isoformat(), "file_reference": ref,
        "received_date": received.isoformat(), "rows": rows,
        "checksum": checksum or file_checksum(EMPLOYER, period, ref, received, rows),
    }


def run(db, operation, data):
    return service(db).execute(operation, HUMAN, data).output


def import_file(db, rows, **kwargs):
    return run(db, "import_salary_file", salary_file(rows, **kwargs))


def approve(db, view):
    return run(db, "approve_salary_file", {"employer_org_number": EMPLOYER, "file_reference": view.file_reference,
                                           "expected_digest": view.review_digest})


def full_october(**overrides):
    rows = {ACTIVE: row(ACTIVE), SECOND: row(SECOND, "60000"), LEAVER: row(LEAVER, "30000")}
    rows.update(overrides)
    return [r for r in rows.values() if r is not None]


def count(db, model, *where):
    with db.session_factory() as s:
        return s.scalar(select(func.count()).select_from(model).where(*where))


def cases(db):
    with db.session_factory() as s:
        return s.scalars(select(Case).order_by(Case.case_number)).all()


class TestIntag:
    def test_giltig_fil_sammanstalls_utan_registrering(self, db):
        view = import_file(db, full_october())
        assert (view.status, view.summary.rows, view.summary.valid, view.summary.missing) == ("received", 3, 3, 0)
        assert view.summary.salary_total_sek == Decimal("135000.00")
        # 2 025,00 + 4 708,13 + 1 350,00 (fall 1 och 2 samt 30 000 kr)
        assert view.summary.premium_preview_sek == Decimal("8083.13")
        assert count(db, SalaryReport) == 0 and count(db, PremiumTransaction, OPERATIVE) == 0 and cases(db) == []

    def test_fall_4_saknad_rad(self, db):
        view = import_file(db, full_october(**{SECOND: None}))
        assert [m.personal_id_number for m in view.missing] == [SECOND]
        decision = approve(db, view)
        assert (decision.salary_reports, decision.premium_rows) == (2, 2)
        assert decision.premium_total_sek == Decimal("3375.00")
        [case] = cases(db)
        assert (case.case_type, case.channel, case.details["reason"]) == (
            "salary_file_deviation", "employer_file", "missing_report")
        assert case.policy_id is not None and case.created_by == "salary_file_intake"
        with db.session_factory() as s:
            second = s.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == SECOND))
            assert s.scalar(select(func.count()).select_from(SalaryReport)
                            .where(SalaryReport.insured_person_id == second.id)) == 0

    def test_fall_5_okand_person_och_annan_arbetsgivare(self, db):
        view = import_file(db, [*full_october(), row(UNKNOWN), row(OTHER)])
        assert [(r.row, r.reason) for r in view.rows if r.outcome == "deviation"] == [
            (4, "unknown_person"), (5, "other_employer")]
        decision = approve(db, view)
        assert decision.salary_reports == 3
        assert [(c.reason, c.case_type) for c in decision.cases] == [
            ("unknown_person", "salary_file_deviation"), ("other_employer", "salary_file_deviation")]
        unknown = cases(db)[0]
        assert unknown.insured_person_id is None and unknown.details["reported"]["personal_id_number"] == UNKNOWN
        assert count(db, SalaryReport) == 3

    def test_fall_6_samma_fil_igen(self, db):
        first = import_file(db, full_october())
        again = import_file(db, full_october())
        assert (again.file_id, again.already_received, again.review_digest) == (first.file_id, True, first.review_digest)
        approve(db, first)
        after = import_file(db, full_october())
        assert (after.already_received, after.status) == (True, "approved")
        assert count(db, SalaryFile) == 1 and count(db, SalaryReport) == 3 and count(db, PremiumTransaction, OPERATIVE) == 3

    def test_fall_7_samma_referens_andrat_innehall(self, db):
        import_file(db, full_october())
        with pytest.raises(ConflictError, match="annat innehåll"):
            import_file(db, full_october(**{ACTIVE: row(ACTIVE, "46000")}))
        assert count(db, SalaryFile) == 1 and count(db, SalaryReport) == 0

    def test_fel_kontrollsumma_tas_inte_emot(self, db):
        with pytest.raises(BlockedError, match="kontrollsumma"):
            import_file(db, full_october(), checksum="0" * 64)
        assert count(db, SalaryFile) == 0

    def test_startluckan_tas_inte_emot(self, db):
        with pytest.raises(BlockedError, match="startlucka"):
            import_file(db, [row(ACTIVE, month=date(2026, 9, 1))], period=date(2026, 9, 1),
                        received=date(2026, 10, 5), ref="LON-2026-09")

    def test_uttrycklig_noll_ar_giltig_och_inte_saknad(self, db):
        view = import_file(db, full_october(**{SECOND: row(SECOND, "0")}))
        assert (view.summary.valid, view.summary.missing) == (3, 0)
        decision = approve(db, view)
        assert decision.cases == []
        with db.session_factory() as s:
            amounts = sorted(s.scalars(select(PremiumTransaction.amount_sek).where(OPERATIVE)).all())
        assert amounts == [Decimal("0.00"), Decimal("1350.00"), Decimal("2025.00")]

    def test_dubblett_i_filen(self, db):
        view = import_file(db, [*full_october(), row(ACTIVE, "50000")])
        assert [r.reason for r in view.rows if r.outcome == "deviation"] == ["duplicate_in_file"] * 2
        decision = approve(db, view)
        assert decision.salary_reports == 2 and len(decision.cases) == 2


class TestGranskning:
    def test_andrat_underlag_stoppar_godkannandet(self, db):
        view = import_file(db, full_october(**{SECOND: None}))
        run(db, "register_salary_report", {
            "personal_id_number": SECOND, "employer_org_number": EMPLOYER, "period_month": "2026-10-01",
            "pensionable_salary_sek": "60000", "kind": "new", "source": "manual", "received_date": "2026-11-06",
        })
        with pytest.raises(ConflictError, match="granska filen igen"):
            approve(db, view)
        assert count(db, SalaryReport) == 1
        fresh = run(db, "get_salary_file", {"employer_org_number": EMPLOYER, "file_reference": "LON-2026-10"})
        assert fresh.review_digest != view.review_digest and fresh.missing == []
        assert approve(db, fresh).cases == []

    def test_godkand_fil_godkanns_inte_igen(self, db):
        view = import_file(db, full_october())
        approve(db, view)
        with pytest.raises(ConflictError, match="redan godkänd"):
            approve(db, view)
        assert count(db, SalaryReport) == 3

    def test_avslag_registrerar_ingenting(self, db):
        view = import_file(db, full_october())
        decision = run(db, "reject_salary_file", {"employer_org_number": EMPLOYER, "file_reference": view.file_reference,
                                                  "decision_note": "Fel period enligt arbetsgivaren"})
        assert decision.status == "rejected"
        [case] = cases(db)
        assert (case.details["reason"], case.insured_person_id) == ("file_rejected", None)
        assert count(db, SalaryReport) == 0 and count(db, PremiumTransaction, OPERATIVE) == 0
        with pytest.raises(ConflictError, match="redan avslagen"):
            approve(db, view)

    def test_kallreferens_och_premie_spars_per_rad(self, db):
        approve(db, import_file(db, full_october()))
        with db.session_factory() as s:
            refs = sorted(s.scalars(select(SalaryReport.source_reference)).all())
            tx = s.scalars(select(PremiumTransaction).where(OPERATIVE)).all()
        assert refs == ["LON-2026-10:1", "LON-2026-10:2", "LON-2026-10:3"]
        assert {t.calculation_basis["salary_report"]["source_reference"] for t in tx} == set(refs)
        assert {t.status for t in tx} == {"pending"}


class TestRattelser:
    def test_rattelse_i_ny_fil_ger_justering(self, db):
        """Fall 8 genom filintaget: 45 000 → 50 000 före fakturering."""
        approve(db, import_file(db, full_october()))
        correction = import_file(db, [row(ACTIVE, "50000", kind="correction", corrects=1)], ref="LON-2026-10-R1")
        assert (correction.summary.valid, correction.summary.corrections, correction.summary.missing) == (1, 1, 0)
        decision = approve(db, correction)
        assert (decision.premium_rows, decision.premium_total_sek) == (1, Decimal("225.00"))

    def test_inaktuell_rattelse_blir_loneunderlagsarende(self, db):
        approve(db, import_file(db, full_october()))
        view = import_file(db, [row(ACTIVE, "50000", kind="correction", corrects=2)], ref="LON-2026-10-R1")
        assert view.rows[0].reason == "stale_correction"
        [ref] = approve(db, view).cases
        [case] = cases(db)
        assert (ref.case_type, case.details["kind"], case.details["corrects_version"], case.details["source"]) == (
            "salary_report", "correction", 2, "employer")
        assert case.source_reference == "LON-2026-10-R1:1"


class TestAnstallning:
    def test_fall_19_slutlon_i_avslutsmanaden(self, db):
        view = import_file(db, full_october())
        leaver = next(r for r in view.rows if r.personal_id_number == LEAVER)
        assert (leaver.outcome, leaver.premium_preview_sek) == ("valid", Decimal("1350.00"))
        approve(db, view)
        november = date(2026, 11, 1)
        late = import_file(db, [row(LEAVER, "5000", month=november)], ref="LON-2026-11", period=november,
                           received=date(2026, 11, 6))
        assert (late.rows[0].reason, late.summary.missing) == ("outside_employment", 2)
        assert "efter anställningens slut" in late.rows[0].message

    def test_premie_som_inte_kan_skapas_blir_arende(self, db):
        with db.session_factory() as s:
            person = s.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == ACTIVE))
            extra = Policy(policy_number="AL-000019", insured_person_id=person.id,
                           signed_date=date(2026, 1, 1), start_date=date(2026, 1, 1))
            s.add(extra)
            s.flush()
            s.add(PolicyBenefit(policy_id=extra.id, benefit_type="retirement_dc", start_date=date(2026, 1, 1)))
            s.commit()
        view = import_file(db, full_october())
        active = view.rows[0]
        assert active.outcome == "valid" and "fördelningsinstruktion" in active.premium_issue
        decision = approve(db, view)
        assert (decision.salary_reports, decision.premium_rows) == (3, 2)
        [ref] = decision.cases
        assert (ref.reason, ref.case_type) == ("premium_blocked", "salary_file_deviation")


def test_agenter_far_inte_hantera_filer(db):
    layer = service(db)
    for name in ("import_salary_file", "get_salary_file", "approve_salary_file", "reject_salary_file"):
        assert layer.decision(name).effective == AgentAccess.HUMAN_ONLY
