"""Faktura och förfallobevakning (paket A steg 3, B-046, P1-PREMIE-001 §4.4–4.5 och §7).

Fallen numreras som i designstoppets §7. Premieperiod 2026-10, IBB 83 400 kr och
produktparametrarnas startvärden. Premieunderlaget skapas genom filintaget (steg 2).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from models import (
    Case,
    Employer,
    InsuredPerson,
    Invoice,
    Policy,
    PolicyBenefit,
    PolicyState,
    PremiumTransaction,
)
from services import (
    Actor,
    AgentAccess,
    BlockedError,
    OperationContext,
    ProductRuleCatalog,
    ServiceLayer,
)
from services.operations import common
from services.operations.salary_files import file_checksum
from utils.bank_calendar import invoice_due_date
from utils.ocr import valid_ocr

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

START = date(2026, 11, 7)
EMPLOYER = "5560000001"
ACTIVE = "198505151234"
SECOND = "197803031234"
OCTOBER = date(2026, 10, 1)
OPERATIVE = PremiumTransaction.period_month >= OCTOBER
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Premiefakturering för oktober")


def _person(s, employer, pnr, policy_number):
    person = InsuredPerson(
        personal_id_number=pnr, first_name="Test", last_name=pnr[-4:], employer_id=employer.id,
        employment_start_date=date(2020, 1, 1), monthly_salary_sek=Decimal(45000), employment_rate=Decimal(100),
        itp1_start_date=date(2020, 1, 1), status="active",
    )
    s.add(person)
    s.flush()
    policy = Policy(policy_number=policy_number, insured_person_id=person.id,
                    signed_date=date(2020, 1, 1), start_date=date(2020, 1, 1))
    s.add(policy)
    s.flush()
    s.add(PolicyBenefit(policy_id=policy.id, benefit_type="retirement_dc", start_date=date(2020, 1, 1)))
    s.add(PolicyState(policy_id=policy.id, state="premium_paying", valid_from=date(2020, 1, 1)))
    s.flush()


def row(pnr, amount="45000", kind="new", corrects=None):
    return {"personal_id_number": pnr, "period_month": "2026-10-01", "pensionable_salary_sek": amount,
            "kind": kind, "corrects_version": corrects}


def salary_file(rows, ref):
    received = date(2026, 11, 5)
    return {"employer_org_number": EMPLOYER, "period_month": "2026-10-01", "file_reference": ref,
            "received_date": received.isoformat(), "rows": rows,
            "checksum": file_checksum(EMPLOYER, OCTOBER, ref, received, rows)}


@pytest.fixture
def clock(monkeypatch):
    state = SimpleNamespace(today=START)
    monkeypatch.setattr(common, "today", lambda: state.today)
    return state


@pytest.fixture
def db(insurance_db, clock):
    with insurance_db.session_factory() as s:
        employer = s.scalar(select(Employer).where(Employer.org_number == EMPLOYER))
        _person(s, employer, ACTIVE, "AL-000010")
        _person(s, employer, SECOND, "AL-000011")
        s.commit()
    return insurance_db


def run(db, operation, data=None):
    service = ServiceLayer(session_factory=db.session_factory, rules=ProductRuleCatalog(today=START))
    return service.execute(operation, HUMAN, data or {}).output


def approve_file(db, rows, ref="LON-2026-10"):
    view = run(db, "import_salary_file", salary_file(rows, ref=ref))
    return run(db, "approve_salary_file", {"employer_org_number": EMPLOYER, "file_reference": ref,
                                           "expected_digest": view.review_digest})


def october(db, active="45000", second="60000"):
    approve_file(db, [row(ACTIVE, active), row(SECOND, second)])


def invoice(db):
    return run(db, "create_invoice", {"employer_org_number": EMPLOYER, "period_month": "2026-10-01"})


def correct_active(db, amount="50000", ref="LON-2026-10-R1"):
    return approve_file(db, [row(ACTIVE, amount, kind="correction", corrects=1)], ref=ref)


def premiums(db):
    with db.session_factory() as s:
        return s.scalars(select(PremiumTransaction).where(OPERATIVE)
                         .order_by(PremiumTransaction.amount_sek)).all()


def mark_premium_paid(db, amount):
    with db.session_factory() as s:
        tx = s.scalar(select(PremiumTransaction).where(OPERATIVE, PremiumTransaction.amount_sek == Decimal(amount)))
        tx.status, tx.paid_date = "paid", date(2026, 12, 1)
        s.commit()


class TestFaktura:
    def test_fall_1_och_2_ordinarie_faktura(self, db):
        october(db)
        [debit] = invoice(db).invoices
        assert (debit.invoice_number, debit.invoice_type, debit.total_sek, debit.open_sek) == (
            "INV-000001", "debit", Decimal("6733.13"), Decimal("6733.13"))
        assert [(line.line_type, line.amount_sek) for line in debit.lines] == [
            ("ordinary", Decimal("2025.00")), ("ordinary", Decimal("4708.13"))] or \
            sorted(line.amount_sek for line in debit.lines) == [Decimal("2025.00"), Decimal("4708.13")]
        assert {line.line_type for line in debit.lines} == {"ordinary"}
        assert valid_ocr(debit.ocr_reference) and debit.invoice_date == START
        assert debit.due_date == invoice_due_date(START) == date(2026, 12, 7)
        assert {p.status for p in premiums(db)} == {"invoiced"}
        assert "personal_id_number" not in debit.model_dump_json()

    def test_samma_period_igen_ger_ingen_ny_faktura(self, db):
        october(db)
        invoice(db)
        again = invoice(db)
        assert again.invoices == [] and "Inget öppet premieunderlag" in again.note
        assert run(db, "list_invoices", {}).count == 1

    def test_fall_3_noll_ger_ingen_fakturarad(self, db):
        october(db, second="0")
        [debit] = invoice(db).invoices
        assert [line.amount_sek for line in debit.lines] == [Decimal("2025.00")]
        zero = premiums(db)[0]
        assert (zero.amount_sek, zero.status) == (Decimal("0.00"), "pending")

    def test_fall_8_rattelse_fore_fakturering_ingar_i_ordinarie_rad(self, db):
        october(db)
        correct_active(db)
        [debit] = invoice(db).invoices
        active = next(line for line in debit.lines if line.amount_sek != Decimal("4708.13"))
        assert (active.line_type, active.amount_sek, len(active.covers)) == ("ordinary", Decimal("2250.00"), 2)
        assert debit.total_sek == Decimal("6958.13")


class TestRattelseEfterFakturering:
    def test_fall_9_kredit_och_ny_debet(self, db):
        october(db)
        invoice(db)
        correct_active(db)
        credit, debit = invoice(db).invoices
        assert (credit.invoice_type, credit.total_sek, credit.credited_invoice_number) == (
            "credit", Decimal("-2025.00"), "INV-000001")
        assert credit.lines[0].credits is not None and credit.lines[0].credits.startswith("INV-000001:")
        assert [(line.line_type, line.amount_sek) for line in debit.lines] == [("rebill", Decimal("2250.00"))]
        original = run(db, "get_invoice", {"invoice_number": "INV-000001"})
        assert original.open_sek == Decimal("4708.13") and original.total_sek == Decimal("6733.13")
        assert {p.status for p in premiums(db)} == {"invoiced"}

    def test_fall_10_tillagg_efter_betalning(self, db):
        october(db)
        invoice(db)
        mark_premium_paid(db, "2025.00")
        correct_active(db)
        [debit] = invoice(db).invoices
        assert [(line.line_type, line.amount_sek) for line in debit.lines] == [("additional", Decimal("225.00"))]
        assert debit.credited_invoice_number is None

    def test_fall_11_nedrattning_efter_betalning_faktureras_inte(self, db):
        october(db)
        invoice(db)
        mark_premium_paid(db, "2025.00")
        decision = correct_active(db, amount="40000")
        assert [c.reason for c in decision.cases] == ["premium_blocked"]
        assert invoice(db).invoices == []


class TestForfall:
    def test_fall_16_forfallodag_over_julen(self, db, clock):
        october(db)
        clock.today = date(2026, 11, 25)
        [debit] = invoice(db).invoices
        assert (debit.invoice_date, debit.due_date) == (date(2026, 11, 25), date(2026, 12, 28))

    def test_fall_17_paminnelse_och_eskalering(self, db, clock):
        october(db)
        clock.today = date(2026, 11, 25)
        [debit] = invoice(db).invoices
        with db.session_factory() as s:
            states_before = s.scalar(select(func.count()).select_from(PolicyState))

        clock.today = date(2026, 12, 28)  # förfallodagen
        assert run(db, "check_overdue_invoices").actions == []

        clock.today = date(2026, 12, 29)
        first = run(db, "check_overdue_invoices")
        [created] = first.actions
        assert (created.action, created.days_overdue, created.open_sek) == ("created", 1, Decimal("6733.13"))
        assert run(db, "check_overdue_invoices").actions == []  # samma dag igen

        clock.today = date(2027, 1, 27)  # 30 dagars dröjsmål
        [escalated] = run(db, "check_overdue_invoices").actions
        assert (escalated.action, escalated.case_number) == ("escalated", created.case_number)
        assert run(db, "check_overdue_invoices").actions == []

        with db.session_factory() as s:
            case = s.scalar(select(Case).where(Case.case_type == "payment_overdue"))
            assert (case.channel, case.assigned_to, case.created_by) == ("system", "operator", "invoice_monitor")
            assert case.details["escalated"] is True and case.details["invoice_number"] == debit.invoice_number
            # Fordran kvar, ingen garanti och inget pensionsstopp
            assert s.scalar(select(func.count()).select_from(PolicyState)) == states_before
        assert {p.status for p in premiums(db)} == {"invoiced"}
        assert run(db, "get_invoice", {"invoice_number": debit.invoice_number}).open_sek == Decimal("6733.13")

    def test_krediterad_faktura_ar_inte_forfallen(self, db, clock):
        october(db, second="0")
        invoice(db)
        correct_active(db, amount="0", ref="LON-2026-10-R0")
        [credit] = invoice(db).invoices
        assert credit.invoice_type == "credit" and credit.total_sek == Decimal("-2025.00")
        clock.today = date(2027, 2, 1)
        result = run(db, "check_overdue_invoices")
        assert (result.overdue_invoices, result.actions) == (0, [])


def test_startluckan_faktureras_inte(db):
    with pytest.raises(BlockedError, match="genererade historiken"):
        run(db, "create_invoice", {"employer_org_number": EMPLOYER, "period_month": "2026-09-01"})


def test_fakturor_andras_inte_och_far_unik_ocr(db):
    october(db)
    invoice(db)
    correct_active(db)
    invoice(db)
    with db.session_factory() as s:
        rows = s.scalars(select(Invoice)).all()
    assert len({r.ocr_reference for r in rows}) == len(rows) == 3
    assert all(len(r.checksum) == 64 and r.checksum != "0" * 64 for r in rows)
    assert all(isinstance(r.id, uuid.UUID) for r in rows)


def test_agenter_far_inte_fakturera(db):
    layer = ServiceLayer(session_factory=db.session_factory, rules=ProductRuleCatalog(today=START))
    for name in ("create_invoice", "check_overdue_invoices", "get_invoice", "list_invoices"):
        assert layer.decision(name).effective == AgentAccess.HUMAN_ONLY
