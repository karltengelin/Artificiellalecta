"""Datautdraget och det rekonstruerade startbeståndet S-04 (A5, B-042 val L, VARDERINGSKONTRAKT.md §5).

Ett litet bestånd i SQLite med antagandebibliotekets startgrunder. Kapitalet är handräknat med
AVK-SIM-2026-01 (2023-01 +2,10 %, 2023-02 −1,20 %, 2023-03 +0,40 %), kapitalavgift 0,20 % och
skattebelastning 0,219 % för 2023. Garantidelarna jämförs med motorns `guarantee_part`.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from models import (
    Base,
    Employer,
    InsuredPerson,
    Policy,
    PolicyBenefit,
    PolicyState,
    PremiumTransaction,
    ValuationBasis,
)
from services import valuation_bases as vb
from services.db import session_factory_for
from services.valuation_extract import (
    NOT_CALCULATED,
    SOURCE,
    ExtractError,
    _Guarantee,
    build_extract,
    extract_checksum,
)
from skills.calculation import actuarial_annuity as aa

MARCH = date(2023, 3, 31)
SIM_HIST, _ = aa.basis_from_assumptions(
    next(a for c, _, a, *_ in vb.START_BASES if c == "SIM-HIST-2023-01"))


def _person(s, employer, pnr: str, number: str, state: str, premiums=()) -> Policy:
    person = InsuredPerson(personal_id_number=pnr, first_name="Test", last_name=number, employer_id=employer.id,
                           employment_start_date=date(2015, 1, 1), status="active")
    s.add(person)
    s.flush()
    policy = Policy(policy_number=number, insured_person_id=person.id, signed_date=date(2015, 1, 1),
                    start_date=date(2015, 1, 1))
    s.add(policy)
    s.flush()
    benefit = PolicyBenefit(policy_id=policy.id, benefit_type="retirement_dc", start_date=date(2015, 1, 1))
    s.add(benefit)
    s.add(PolicyState(policy_id=policy.id, state=state, valid_from=date(2015, 1, 1)))
    s.flush()
    for period, tx_type, amount, status, paid in premiums:
        s.add(PremiumTransaction(benefit_id=benefit.id, period_month=period, transaction_type=tx_type,
                                 amount_sek=Decimal(amount), status=status, paid_date=paid))
    return policy


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = session_factory_for(engine)
    with factory() as s:
        vb.add_missing_defaults(s)
        employer = Employer(org_number="5560000001", name="Testbolaget AB", affiliation_date=date(2010, 1, 1))
        s.add(employer)
        s.flush()
        ids = SimpleNamespace(
            a=_person(s, employer, "199001011234", "AL-1", "premium_paying", [
                (date(2022, 12, 1), "premium", "10000.00", "paid", date(2023, 1, 15)),
                (date(2023, 1, 1), "premium", "5000.00", "paid", date(2023, 2, 15)),
                (date(2023, 1, 1), "fee", "-20.00", "paid", date(2023, 2, 15)),
                (date(2023, 2, 1), "premium", "5000.00", "invoiced", None),
            ]).id,
            # Samordningsnummer: dag 75 = den 15:e
            b=_person(s, employer, "198503751234", "AL-2", "paid_up", [
                (date(2023, 2, 1), "premium", "2000.00", "paid", date(2023, 3, 10)),
            ]).id,
            negative=_person(s, employer, "198806061234", "AL-3", "premium_paying", [
                (date(2023, 1, 1), "premium", "3000.00", "paid", date(2023, 2, 15)),
                (date(2023, 1, 1), "adjustment", "-500.00", "paid", date(2023, 3, 15)),
            ]).id,
            payout=_person(s, employer, "195702021234", "AL-4", "in_payout", [
                (date(2023, 1, 1), "premium", "1000.00", "paid", date(2023, 2, 15)),
            ]).id,
            empty=_person(s, employer, "199505051234", "AL-5", "premium_paying").id,
        )
        s.commit()
    yield SimpleNamespace(factory=factory, ids=ids)
    engine.dispose()


def _extract(db, on: date = MARCH):
    with db.factory() as s:
        return build_extract(s, on)


def _policy(extract, policy_id):
    return next(p for p in extract.policies if p.policy_id == str(policy_id))


class TestRekonstruktion:
    def test_kontrollerna_godkanner_utdraget(self, db):
        extract = _extract(db)
        assert extract.approved, [c for c in extract.checks if not c.passed]
        assert [c.name for c in extract.checks] == [
            "antal försäkringar", "premiesumma", "fullständiga uppgifter", "premiehistorik",
            "inga negativa belopp", "kända grunder", "kapitalavstämning"]
        assert extract.source == SOURCE and extract.outside_population == 1
        assert set(extract.bases) == {"SIM-HIST-2023-01", "AVK-SIM-2026-01"}

    def test_kapitalet_ar_handraknat(self, db):
        extract = _extract(db)
        # jan: premie 10 000 vid månadsslut. feb: −120,00, avgift 1,67, skatt 1,83 (1,825), premie 5 000.
        # mar: 14 876,50 × 0,4 % = 59,51, avgift 2,48, skatt 2,71 → 14 930,82
        a = _policy(extract, db.ids.a)
        assert a.capital == Decimal("14930.82")
        assert (a.flows.premiums, a.flows.returns, a.flows.fees, a.flows.taxes) == (
            Decimal("15000.00"), Decimal("-60.49"), Decimal("4.15"), Decimal("4.54"))
        assert _policy(extract, db.ids.b).capital == Decimal("2000.00")  # premien kom i mars
        march = extract.months[-1]
        assert (march.opening, march.closing) == (Decimal("14876.50"), Decimal("16930.82"))

    def test_garantidelarna_ar_motorns(self, db):
        a = _policy(_extract(db), db.ids.a)
        assert [(p.received_month, p.premium, p.basis) for p in a.guarantee_parts] == [
            (date(2023, 1, 1), Decimal("10000.00"), "SIM-HIST-2023-01"),
            (date(2023, 2, 1), Decimal("5000.00"), "SIM-HIST-2023-01")]
        expected, _ = aa.guarantee_part(SIM_HIST, date(1990, 1, 1), date(2023, 1, 31), Decimal(10000))
        assert float(a.guarantee_parts[0].guarantee) == pytest.approx(expected, abs=1e-9)
        assert a.plan.start == date(2056, 1, 1) and a.birth_month == "1990-01" and a.born_on_first

    def test_bara_fodelsemanaden_och_den_forsta_paverkar(self, db):
        b = _policy(_extract(db), db.ids.b)
        assert b.birth_month == "1985-03" and not b.born_on_first and b.plan.start == date(2051, 3, 1)
        exact, _ = aa.guarantee_part(SIM_HIST, date(1985, 3, 15), date(2023, 3, 31), Decimal(2000))
        assert float(b.guarantee_parts[0].guarantee) == pytest.approx(exact, abs=1e-9)

    def test_ej_beraknade_fall_listas_med_orsak(self, db):
        extract = _extract(db)
        reasons = {n.policy_id: n.reason for n in extract.not_calculated}
        assert reasons == {str(db.ids.negative): NOT_CALCULATED["negative"],
                           str(db.ids.payout): NOT_CALCULATED["in_payout"]}
        premium_check = next(c for c in extract.checks if c.name == "premiesumma")
        assert premium_check.passed and "3 rader 3500.00 kr ej beräknade" in premium_check.detail

    def test_inga_personuppgifter_i_utdraget(self, db):
        text = json.dumps(_extract(db).model_dump(mode="json"))
        assert "199001011234" not in text and "Test" not in text and "AL-1" not in text


class TestKontrollsumma:
    def test_samma_bestand_ger_samma_summa(self, db):
        first, second = _extract(db), _extract(db)
        assert first.checksum == second.checksum == extract_checksum(second)

    def test_andrad_premie_ger_ny_summa(self, db):
        before = _extract(db).checksum
        with db.factory() as s:
            tx = s.scalar(select(PremiumTransaction).where(PremiumTransaction.amount_sek == Decimal("2000.00")))
            tx.amount_sek = Decimal("2000.01")
            s.commit()
        assert _extract(db).checksum != before


class TestKontroller:
    def test_saknat_lage_underkanner(self, db):
        with db.factory() as s:
            s.delete(s.scalar(select(PolicyState).where(PolicyState.policy_id == db.ids.b)))
            s.commit()
        extract = _extract(db)
        failed = [c.name for c in extract.checks if not c.passed]
        assert not extract.approved and "fullständiga uppgifter" in failed and "premiesumma" in failed

    def test_olasligt_personnummer_underkanner(self, db):
        with db.factory() as s:
            s.scalar(select(InsuredPerson).where(InsuredPerson.last_name == "AL-1")).personal_id_number = "199013011234"
            s.commit()
        assert not _extract(db).approved

    def test_saknad_avkastning_blockerar(self, db):
        with pytest.raises(ExtractError, match="Avkastning saknas för 2026-11"):
            _extract(db, date(2026, 11, 30))

    def test_andrad_grund_blockerar(self, db):
        with db.factory() as s:
            row = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "AVK-SIM-2026-01"))
            row.assumptions = {**row.assumptions, "description": "ändrad"}
            s.commit()
        with pytest.raises(ExtractError, match="AVK-SIM-2026-01"):
            _extract(db)

    def test_datumet_ska_vara_ett_manadsslut(self, db):
        with pytest.raises(ExtractError, match="månadsslut"):
            _extract(db, date(2023, 3, 30))
        with pytest.raises(ExtractError, match="2023-01"):
            _extract(db, date(2022, 12, 31))

    def test_garantigrunden_foljer_mottagningsmanaden(self, db):
        with db.factory() as s:
            rows = list(s.scalars(select(ValuationBasis).where(ValuationBasis.family.in_(("SIM-HIST", "SIM-G")))))
        guarantee = _Guarantee(rows)
        assert guarantee.basis_on(date(2026, 10, 31)).code == "SIM-HIST-2023-01"
        assert guarantee.basis_on(date(2026, 11, 30)).code == "SIM-G-2026-01"
