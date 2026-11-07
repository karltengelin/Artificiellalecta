"""Premieunderlag ur registrerat löneunderlag (paket A steg 1, B-046, P1-PREMIE-001 §4.3 och §7).

Fallen numreras som i designstoppets §7. Beloppen gäller premieperiod 2026-10,
IBB 83 400 kr och produktparametrarnas startvärden.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from models import Employer, InsuredPerson, OperationEventRecord, Policy, PolicyBenefit, PolicyState, PremiumTransaction
from services import (
    Actor,
    AgentAccess,
    BlockedError,
    ConflictError,
    NotFoundError,
    OperationContext,
    ProductRuleCatalog,
    ServiceLayer,
)
from services.operations import common

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 11, 7)
EMPLOYER = "5560000001"
ACTIVE = "198505151234"
TURNS_66 = "196010031234"  # 66 år i oktober 2026
OCTOBER = "2026-10-01"
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Arbetsgivarens löneunderlag för oktober")


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


def _person(s, employer, pnr, born_policy="AL-000010"):
    person = InsuredPerson(
        personal_id_number=pnr, first_name="Test", last_name=pnr[-4:], employer_id=employer.id,
        employment_start_date=date(2020, 1, 1), monthly_salary_sek=Decimal("45000"),
        employment_rate=Decimal("100"), itp1_start_date=date(2020, 1, 1), status="active",
    )
    s.add(person)
    s.flush()
    policy = Policy(policy_number=born_policy, insured_person_id=person.id,
                    signed_date=date(2020, 1, 1), start_date=date(2020, 1, 1))
    s.add(policy)
    s.flush()
    s.add(PolicyBenefit(policy_id=policy.id, benefit_type="retirement_dc", start_date=date(2020, 1, 1)))
    s.add(PolicyState(policy_id=policy.id, state="premium_paying", valid_from=date(2020, 1, 1)))
    s.flush()
    return policy


@pytest.fixture
def db(insurance_db):
    with insurance_db.session_factory() as s:
        employer = s.scalar(select(Employer).where(Employer.org_number == EMPLOYER))
        insurance_db.active_policy = _person(s, employer, ACTIVE, "AL-000010").id
        insurance_db.old_policy = _person(s, employer, TURNS_66, "AL-000011").id
        s.commit()
    return insurance_db


def service(db) -> ServiceLayer:
    return ServiceLayer(session_factory=db.session_factory, rules=ProductRuleCatalog(today=TODAY))


def salary(db, pnr=ACTIVE, amount="45000", kind="new", corrects=None, ref=None):
    data = {
        "personal_id_number": pnr, "employer_org_number": EMPLOYER, "period_month": OCTOBER,
        "pensionable_salary_sek": amount, "kind": kind, "source": "employer",
        "source_reference": ref or f"LON-{pnr[-4:]}-{amount}", "received_date": "2026-11-05",
    }
    if corrects:
        data["corrects_version"] = corrects
    return service(db).execute("register_salary_report", HUMAN, data).output


def basis(db, pnr=ACTIVE, month=OCTOBER):
    data = {"personal_id_number": pnr, "employer_org_number": EMPLOYER, "period_month": month}
    return service(db).execute("create_premium_from_salary_report", HUMAN, data).output


def rows(db):
    with db.session_factory() as s:
        return s.scalars(select(PremiumTransaction).where(PremiumTransaction.period_month == date(2026, 10, 1))
                         .order_by(PremiumTransaction.transaction_type.desc())).all()


def mark_paid(db, tx_id):
    with db.session_factory() as s:
        tx = s.get(PremiumTransaction, uuid.UUID(str(tx_id)))
        tx.status, tx.paid_date = "paid", date(2026, 11, 6)
        s.commit()


class TestNyPremie:
    def test_fall_1_lon_45000(self, db):
        salary(db)
        out = basis(db)
        assert (out.case, out.amount_sek, out.month_total_sek, out.invoiceable) == ("new_premium", Decimal("2025.00"),
                                                                                    Decimal("2025.00"), True)
        [row] = rows(db)
        assert (row.transaction_type, row.status, row.amount_sek) == ("premium", "pending", Decimal("2025.00"))
        assert row.calculation_basis["salary_report"]["version"] == 1
        assert Decimal(row.calculation_basis["ibb"]) == Decimal("83400")
        assert row.calculation_basis["rule_package"] == "PR-ITP1 v1.0"
        assert row.calculation_basis["parameters"]  # parameterversionerna följer med

    def test_fall_2_lon_60000(self, db):
        salary(db, amount="60000")
        assert basis(db).amount_sek == Decimal("4708.13")

    def test_fall_3_uttrycklig_noll(self, db):
        salary(db, amount="0")
        out = basis(db)
        assert (out.amount_sek, out.invoiceable) == (Decimal("0.00"), False)
        assert rows(db)[0].amount_sek == Decimal("0.00")

    def test_fall_18_66_arsmanaden(self, db):
        salary(db, pnr=TURNS_66, amount="45000")
        out = basis(db, pnr=TURNS_66)
        assert (out.amount_sek, out.in_age_window, out.invoiceable) == (Decimal("0.00"), False, False)
        assert "åldersfönstret" in out.note


class TestRattelse:
    def test_fall_8_rattelse_fore_betalning(self, db):
        salary(db)
        original = basis(db)
        salary(db, amount="50000", kind="correction", corrects=1)
        out = basis(db)
        assert (out.case, out.amount_sek, out.month_total_sek) == ("correction", Decimal("225.00"), Decimal("2250.00"))
        premium, adjustment = rows(db)
        assert str(adjustment.corrects_transaction_id) == original.transaction_id
        assert adjustment.calculation_basis["case"] == "unreceived_claim"
        assert adjustment.calculation_basis["salary_report"]["version"] == 2
        assert premium.amount_sek == Decimal("2025.00")  # ursprungsraden bevaras

    def test_fall_10_tillagg_efter_betalning(self, db):
        salary(db)
        original = basis(db)
        mark_paid(db, original.transaction_id)
        salary(db, amount="50000", kind="correction", corrects=1)
        out = basis(db)
        assert (out.amount_sek, out.received_sek) == (Decimal("225.00"), Decimal("2025.00"))
        assert rows(db)[1].calculation_basis["case"] == "additional_premium"

    def test_fall_11_nedrattning_efter_betalning_blockeras(self, db):
        salary(db)
        original = basis(db)
        mark_paid(db, original.transaction_id)
        salary(db, amount="40000", kind="correction", corrects=1)
        with pytest.raises(BlockedError, match="minska redan mottagen premie"):
            basis(db)
        assert len(rows(db)) == 1

    def test_oforandrad_premie_ger_ingen_ny_rad(self, db):
        salary(db, amount="220000")  # över 30 IBB/12 – taket nås
        basis(db)
        salary(db, amount="230000", kind="correction", corrects=1)
        out = basis(db)
        assert (out.case, out.transaction_id, out.amount_sek) == ("unchanged", None, Decimal("0.00"))
        assert len(rows(db)) == 1

    def test_samma_underlag_tva_ganger_ger_konflikt(self, db):
        salary(db)
        basis(db)
        with pytest.raises(ConflictError, match="version 1"):
            basis(db)
        assert len(rows(db)) == 1


class TestStopp:
    def test_startluckan_fore_oktober(self, db):
        with pytest.raises(BlockedError, match="startlucka"):
            basis(db, month="2026-09-01")

    def test_saknat_loneunderlag_ger_ingen_premie(self, db):
        with pytest.raises(NotFoundError, match="saknad rapport ger ingen premie"):
            basis(db)
        assert rows(db) == []

    def test_utbetalning_startad(self, db):
        salary(db)
        with db.session_factory() as s:
            current = s.scalar(select(PolicyState).where(PolicyState.policy_id == db.active_policy))
            current.valid_to = date(2026, 9, 30)
            s.flush()
            s.add(PolicyState(policy_id=db.active_policy, state="in_payout", valid_from=date(2026, 10, 1)))
            s.commit()
        with pytest.raises(BlockedError, match="utbetalning har startat"):
            basis(db)

    def test_flera_mottagare_kraver_fordelningsinstruktion(self, db):
        salary(db)
        with db.session_factory() as s:
            person = s.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == ACTIVE))
            extra = Policy(policy_number="AL-000012", insured_person_id=person.id,
                           signed_date=date(2026, 1, 1), start_date=date(2026, 1, 1))
            s.add(extra)
            s.flush()
            s.add(PolicyBenefit(policy_id=extra.id, benefit_type="retirement_dc", start_date=date(2026, 1, 1)))
            s.commit()
        with pytest.raises(BlockedError, match="fördelningsinstruktion"):
            basis(db)
        assert rows(db) == []

    def test_blockerat_anrop_loggas_utan_andring(self, db):
        with pytest.raises(BlockedError):
            basis(db, month="2026-09-01")
        with db.session_factory() as s:
            events = s.scalars(select(OperationEventRecord).where(
                OperationEventRecord.operation == "create_premium_from_salary_report")).all()
        assert all(e.outcome != "executed" for e in events)


def test_agenter_far_inte_skapa_premieunderlag(db):
    assert service(db).decision("create_premium_from_salary_report").effective == AgentAccess.HUMAN_ONLY
