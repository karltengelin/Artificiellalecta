"""Inbetalning, matchning och avstämningskonto (paket A steg 4, B-046, P1-PREMIE-001 §4.6–4.7 och §7).

Fallen numreras som i designstoppets §7. Fakturan INV-000001 har 2 025,00 och
4 708,13 kr (6 733,13 kr) för premieperiod 2026-10 och skapas genom filintaget och
faktureringen (steg 2–3).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from models import (
    BankEvent,
    Case,
    Employer,
    InsuredPerson,
    PaymentAllocation,
    Policy,
    PolicyState,
    PremiumTransaction,
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
from services.operations.payments import bank_file_checksum
from services.operations.salary_files import file_checksum
from tests.conftest import add_retirement_benefit

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

START = date(2026, 11, 7)
EMPLOYER = "5560000001"
STRANGER = "5569999999"  # inte ansluten
ACTIVE = "198505151234"
SECOND = "197803031234"
OCTOBER = date(2026, 10, 1)
OPERATIVE = PremiumTransaction.period_month >= OCTOBER
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Bankfil från simulerad bank")


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
        _person(s, employer, ACTIVE, "AL-000010")
        _person(s, employer, SECOND, "AL-000011")
        s.commit()
    return insurance_db


def run(db, operation, data=None):
    service = ServiceLayer(session_factory=db.session_factory, rules=ProductRuleCatalog(today=START))
    return service.execute(operation, HUMAN, data or {}).output


def row(pnr, amount, kind="new", corrects=None):
    return {"personal_id_number": pnr, "period_month": "2026-10-01", "pensionable_salary_sek": amount,
            "kind": kind, "corrects_version": corrects}


def approve_file(db, rows, ref):
    received = date(2026, 11, 5)
    view = run(db, "import_salary_file", {
        "employer_org_number": EMPLOYER, "period_month": "2026-10-01", "file_reference": ref,
        "received_date": received.isoformat(), "rows": rows,
        "checksum": file_checksum(EMPLOYER, OCTOBER, ref, received, rows),
    })
    return run(db, "approve_salary_file", {"employer_org_number": EMPLOYER, "file_reference": ref,
                                           "expected_digest": view.review_digest})


@pytest.fixture
def invoiced(db):
    approve_file(db, [row(ACTIVE, "45000"), row(SECOND, "60000")], "LON-2026-10")
    [debit] = run(db, "create_invoice", {"employer_org_number": EMPLOYER, "period_month": "2026-10-01"}).invoices
    assert debit.total_sek == Decimal("6733.13")
    return debit


def event(event_id, amount, reference, payer=EMPLOYER, received="2026-11-10"):
    return {"event_id": event_id, "received_date": received, "amount_sek": amount,
            "payer_org_number": payer, "reference": reference}


def bank(db, clock, events, ref="BANK-2026-11-10"):
    clock.today = max(date.fromisoformat(e["received_date"]) for e in events)
    return run(db, "import_bank_file", {"source_system": "bank-sim", "file_reference": ref, "events": events,
                                        "checksum": bank_file_checksum("bank-sim", ref, events)})


def statuses(db):
    with db.session_factory() as s:
        return [(p.amount_sek, p.status, p.paid_date) for p in
                s.scalars(select(PremiumTransaction).where(OPERATIVE).order_by(PremiumTransaction.amount_sek))]


def receivables(db):
    return run(db, "get_receivables", {})


class TestMatchning:
    def test_fall_1_full_betalning(self, db, clock, invoiced):
        result = bank(db, clock, [event("E1", "6733.13", invoiced.ocr_reference)])
        [outcome] = result.outcomes
        assert (outcome.allocated_sek, outcome.unallocated_sek, outcome.case_number) == (
            Decimal("6733.13"), Decimal("0.00"), None)
        assert result.paid_premium_rows == 2
        assert statuses(db) == [(Decimal("2025.00"), "paid", date(2026, 11, 10)),
                                (Decimal("4708.13"), "paid", date(2026, 11, 10))]
        summary = receivables(db)
        assert (summary.receivables_sek, summary.suspense_sek, summary.balanced) == (Decimal("0.00"), Decimal("0.00"), True)

    def test_fall_12_delbetalning(self, db, clock, invoiced):
        [outcome] = bank(db, clock, [event("E1", "4000.00", invoiced.ocr_reference)]).outcomes
        assert sorted(a.amount_sek for a in outcome.allocations) == [Decimal("1203.01"), Decimal("2796.99")]
        assert {status for _, status, _ in statuses(db)} == {"invoiced"}
        summary = receivables(db)
        assert (summary.receivables_sek, summary.balanced) == (Decimal("2733.13"), True)
        assert run(db, "get_invoice", {"invoice_number": invoiced.invoice_number}).open_sek == Decimal("2733.13")
        # Resten betalas: raderna blir betalda med sista mottagningsdagen
        rest = bank(db, clock, [event("E2", "2733.13", invoiced.ocr_reference, received="2026-11-20")],
                    ref="BANK-2026-11-20")
        assert rest.paid_premium_rows == 2
        assert {(status, paid) for _, status, paid in statuses(db)} == {("paid", date(2026, 11, 20))}

    def test_fall_13_overbetalning(self, db, clock, invoiced):
        [outcome] = bank(db, clock, [event("E1", "7000.00", invoiced.ocr_reference)]).outcomes
        assert (outcome.allocated_sek, outcome.unallocated_sek, outcome.reason) == (
            Decimal("6733.13"), Decimal("266.87"), "overpayment")
        with db.session_factory() as s:
            case = s.scalar(select(Case).where(Case.case_type == "payment_unmatched"))
            assert (case.case_number, case.channel, case.details["unallocated_sek"]) == (
                outcome.case_number, "system", "266.87")
        summary = receivables(db)
        assert (summary.suspense_sek, summary.receivables_sek, summary.balanced) == (
            Decimal("266.87"), Decimal("0.00"), True)

    def test_fall_14_okand_ocr(self, db, clock, invoiced):
        [outcome] = bank(db, clock, [event("E1", "6733.13", "700099991")]).outcomes
        assert (outcome.allocated_sek, outcome.unallocated_sek, outcome.reason) == (
            Decimal("0.00"), Decimal("6733.13"), "unknown_reference")
        assert {status for _, status, _ in statuses(db)} == {"invoiced"}  # ingen garanti
        assert outcome.case_number is not None

    def test_fall_14_fel_betalare(self, db, clock, invoiced):
        [outcome] = bank(db, clock, [event("E1", "6733.13", invoiced.ocr_reference, payer=STRANGER)]).outcomes
        assert (outcome.reason, outcome.unallocated_sek) == ("wrong_payer", Decimal("6733.13"))
        with db.session_factory() as s:
            case = s.scalar(select(Case).where(Case.case_type == "payment_unmatched"))
            assert case.employer_id is None and case.insured_person_id is None  # okänd betalare
        assert receivables(db).receivables_sek == Decimal("6733.13")

    def test_fall_15_samma_handelse_i_tva_filer(self, db, clock, invoiced):
        first = bank(db, clock, [event("E1", "4000.00", invoiced.ocr_reference)])
        second = bank(db, clock, [event("E1", "4000.00", invoiced.ocr_reference),
                                  event("E2", "2733.13", invoiced.ocr_reference)], ref="BANK-2026-11-11")
        assert [(o.event_id, o.status) for o in second.outcomes] == [("E1", "already_received"), ("E2", "new")]
        assert second.outcomes[0].allocated_sek == first.outcomes[0].allocated_sek
        with db.session_factory() as s:
            assert s.scalar(select(func.count()).select_from(BankEvent)) == 2
            assert s.scalar(select(func.sum(PaymentAllocation.amount_sek))) == Decimal("6733.13")
        assert receivables(db).balanced

    def test_samma_handelse_med_andrat_innehall_ger_konflikt(self, db, clock, invoiced):
        bank(db, clock, [event("E1", "4000.00", invoiced.ocr_reference)])
        with pytest.raises(ConflictError, match="annat innehåll"):
            bank(db, clock, [event("E2", "100.00", invoiced.ocr_reference),
                             event("E1", "4100.00", invoiced.ocr_reference)], ref="BANK-2026-11-11")
        with db.session_factory() as s:
            assert s.scalar(select(func.count()).select_from(BankEvent)) == 1  # inget i filen registrerat

    def test_fel_kontrollsumma_lases_inte(self, db, clock, invoiced):
        events = [event("E1", "6733.13", invoiced.ocr_reference)]
        clock.today = date(2026, 11, 10)
        with pytest.raises(BlockedError, match="kontrollsumma"):
            run(db, "import_bank_file", {"file_reference": "B", "events": events, "checksum": "0" * 64})


class TestManuellFordelning:
    def test_verifierad_betalare_fordelas_fran_avstamningskontot(self, db, clock, invoiced):
        bank(db, clock, [event("E1", "6733.13", invoiced.ocr_reference, payer=STRANGER)])
        request = {"event_id": "E1", "invoice_number": invoiced.invoice_number, "request_key": "verifierad-1",
                   "payer_verification": "Moderbolaget betalade enligt arbetsgivarens kontaktperson"}
        result = run(db, "allocate_unmatched_payment", request)
        assert (result.status, result.allocated_sek, result.remaining_suspense_sek, result.paid_premium_rows) == (
            "allocated", Decimal("6733.13"), Decimal("0.00"), 2)
        again = run(db, "allocate_unmatched_payment", request)
        assert (again.status, again.allocated_sek) == ("already_applied", Decimal("6733.13"))
        summary = receivables(db)
        assert (summary.receivables_sek, summary.suspense_sek, summary.balanced) == (
            Decimal("0.00"), Decimal("0.00"), True)

    def test_delvis_fordelning_lamnar_resten(self, db, clock, invoiced):
        bank(db, clock, [event("E1", "7000.00", "700099991")])
        result = run(db, "allocate_unmatched_payment", {
            "event_id": "E1", "invoice_number": invoiced.invoice_number, "request_key": "k1",
            "payer_verification": "Fel OCR enligt arbetsgivaren"})
        assert (result.allocated_sek, result.remaining_suspense_sek) == (Decimal("6733.13"), Decimal("266.87"))
        with pytest.raises(BlockedError, match="inget öppet belopp"):
            run(db, "allocate_unmatched_payment", {
                "event_id": "E1", "invoice_number": invoiced.invoice_number, "request_key": "k2",
                "payer_verification": "Samma betalare"})
        assert receivables(db).balanced


class TestFordringar:
    def test_betald_faktura_ar_inte_forfallen(self, db, clock, invoiced):
        bank(db, clock, [event("E1", "6733.13", invoiced.ocr_reference)])
        clock.today = date(2027, 2, 1)
        assert run(db, "check_overdue_invoices").overdue_invoices == 0

    def test_delbetald_faktura_bevakas_med_rest(self, db, clock, invoiced):
        bank(db, clock, [event("E1", "4000.00", invoiced.ocr_reference)])
        clock.today = date(2026, 12, 9)
        [action] = run(db, "check_overdue_invoices").actions
        assert action.open_sek == Decimal("2733.13")

    def test_rattelse_av_delbetald_premie_kraver_manuell_provning(self, db, clock, invoiced):
        bank(db, clock, [event("E1", "4000.00", invoiced.ocr_reference)])
        approve_file(db, [row(ACTIVE, "50000", kind="correction", corrects=1)], "LON-2026-10-R1")
        run_result = run(db, "create_invoice", {"employer_org_number": EMPLOYER, "period_month": "2026-10-01"})
        assert run_result.invoices == []
        assert "Delbetald" in run_result.skipped[0].reason


def test_agenter_far_inte_hantera_betalningar(db):
    layer = ServiceLayer(session_factory=db.session_factory, rules=ProductRuleCatalog(today=START))
    for name in ("import_bank_file", "allocate_unmatched_payment", "get_receivables"):
        assert layer.decision(name).effective == AgentAccess.HUMAN_ONLY


class TestInbetalningslistan:
    """list_bank_events – sidan Premier och betalningar (steg 7)."""

    def test_inbetalningar_och_avstamningskontots_poster(self, db, clock, invoiced):
        bank(db, clock, [event("E1", "4000.00", invoiced.ocr_reference, received="2026-11-09"),
                         event("E2", "100.00", "99999999", received="2026-11-10")])
        listing = run(db, "list_bank_events", {})
        assert listing.missing_tables == []
        assert [(e.event_id, e.invoice_number, e.allocated_sek, e.unallocated_sek, e.reason) for e in listing.events] == [
            ("E2", None, Decimal("0.00"), Decimal("100.00"), "unknown_reference"),
            ("E1", invoiced.invoice_number, Decimal("4000.00"), Decimal("0.00"), None),
        ]
        assert listing.events[0].case_number is not None and listing.events[0].file_reference == "BANK-2026-11-10"
        [open_post] = run(db, "list_bank_events", {"unallocated_only": True}).events
        assert open_post.event_id == "E2"
        assert run(db, "list_bank_events", {"payer_org_number": STRANGER}).events == []

    def test_fordelad_post_lamnar_avstamningskontot(self, db, clock, invoiced):
        bank(db, clock, [event("E1", "100.00", "99999999")])
        run(db, "allocate_unmatched_payment", {"event_id": "E1", "invoice_number": invoiced.invoice_number,
                                               "payer_verification": "Telefon", "request_key": "k1"})
        assert run(db, "list_bank_events", {"unallocated_only": True}).events == []
        [listed] = run(db, "list_bank_events", {}).events
        assert (listed.allocated_sek, listed.unallocated_sek) == (Decimal("100.00"), Decimal("0.00"))

    def test_saknade_tabeller_ger_besked_i_stallet_for_fel(self, db):
        with db.engine.begin() as connection:
            for table in reversed(common.PREMIUM_FLOW_TABLES):
                connection.exec_driver_sql(f"DROP TABLE {table}")
        listing = run(db, "list_bank_events", {})
        assert (listing.events, listing.missing_tables) == ([], list(common.PREMIUM_FLOW_TABLES))
        assert ServiceLayer(session_factory=db.session_factory).decision("list_bank_events").effective \
            == AgentAccess.HUMAN_ONLY
