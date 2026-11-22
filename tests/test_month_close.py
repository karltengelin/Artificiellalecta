"""Månadsstängning för sparandet (paket B steg 3, B-047, P1-PENSION-001 §7 och §11 fall 13, 15, 16 och 17).

Beståndet och premiekedjan är desamma som i överlämningen till månadsjournalen (`test_premium_month_export`):
fyra premiebetalande försäkrade med mottagen historik och oktoberpremier ur paket A som betalas i november
(delbetalning, rättelser, tillägg och avstämningskonto) och en betalning i december. Journalen öppnas från
S-04 per 2026-10-31 och november stängs med en syntetisk AVK för november, antagen genom A4:s väg.

- **Fall 13:** C0 = 100 000,00 och r = 1 % ger +1 000,00, −16,67 och −29,50, alltså C1 = 100 953,83.
- **Fall 15:** premie på en ej startad del medan en annan del på försäkringen är pågående: garantidel med egen
  referensplan, ingen avkastning denna månad, och den pågående delen rörs inte.
- **Fall 16:** samma stängning igen ger ingen ny post; ändrad AVK efter stängningen ger en rättelse med
  motposter som pekar på den stängda versionen.
- **Fall 17:** ingen antagen AVK för månaden blockerar stängningen utan att något skrivs.
- **Fall 37 i stängningen:** novembers premier ur paket A bokas vid månadsslut; avstämningskontot följer inte med.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError

from models import (
    Base,
    BaseAmount,
    Case,
    Employer,
    InsuredPerson,
    LedgerBatch,
    LedgerCapitalEntry,
    LedgerControl,
    LedgerGuaranteePart,
    PaymentAllocation,
    PayoutPart,
    PayoutPartState,
    Policy,
    PolicyBenefit,
    PremiumTransaction,
    ValuationBasis,
)
from services import Actor, BlockedError, OperationContext, parameters
from services import capital_ledger as cl
from services import month_close as mc
from services import valuation_bases as vb
from services.db import session_factory_for
from services.errors import AccessDeniedError, ConflictError
from services.ledger_extract import build_ledger_extract, covered_dates
from services.ledger_premiums import IntakeError, premium_intake
from services.valuation import compute_valuation
from skills.calculation.premium_origin_ledger import Origin
from tests import test_premium_month_export as export_tests
from tests.test_premium_month_export import (
    EMPLOYER,
    PERSONS,
    _person,
    bank,
    event,
    invoice,
    row,
    run,
    salary_file,
)

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

chain = export_tests.chain


def open_ledger(db):
    """Öppnar journalen från S-04 per 2026-10-31 (som i test_capital_ledger, utan delad import)."""
    review = run(db, "preview_ledger_opening", {}).payload
    return run(db, "open_capital_ledger", {"reviewed_checksum": review["review_checksum"]}).payload
clock = export_tests.clock

NOVEMBER, DECEMBER = date(2026, 11, 1), date(2026, 12, 1)
NOV_END, DEC_END = date(2026, 11, 30), date(2026, 12, 31)
SCENARIO = {"basis_code": "SIM-V-2026-01", "curve_code": "FI-SIM-2026-10"}
AGENT = OperationContext(actor=Actor.agent("forsakring", team="forsakring"), reason="prov")
SYSTEM = OperationContext(actor=Actor.system("system:prov"), reason="prov")
CENT = Decimal("0.01")


def adopt_avk(db, code: str, rates: dict[str, str], valid_from: str, supersedes: str = "AVK-SIM-2026-01") -> None:
    """AVK-version genom A4:s förslags- och antagandeväg: AVK-SIM-2026-01:s historik plus angivna månader."""
    with db.factory() as s:
        base = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "AVK-SIM-2026-01")).assumptions
    months = [m for m in vb.normalize("return_series", base)["months"]] + [
        {"month": month, "rate": rate} for month, rate in rates.items()]
    run(db, "propose_valuation_basis", {"code": code, "title": "Syntetisk avkastning för månadsstängningen",
                                         "assumptions": vb.normalize("return_series", {**base, "months": months}),
                                         "source_refs": "test", "supersedes_code": supersedes})
    run(db, "adopt_valuation_basis", {"code": code, "valid_from": valid_from, "decision_ref": "prov S5"})


def prepare(db, month="2026-11-01", **kw):
    return run(db, "prepare_month_close", {"month": month}, **kw).payload


def close(db, month="2026-11-01", checksum=None):
    review = prepare(db, month) if checksum is None else {"review_checksum": checksum}
    return run(db, "close_policy_month", {"month": month, "reviewed_checksum": review["review_checksum"]}).payload


def count(db, model, *where) -> int:
    with db.factory() as s:
        return s.scalar(select(func.count()).select_from(model).where(*where))


@pytest.fixture
def ready(chain):
    """Journalen öppnad per 2026-10-31 och AVK-SIM-2026-02 (+0,20 % i november) antagen; klockan i december."""
    open_ledger(chain)
    adopt_avk(chain, "AVK-SIM-2026-02", {"2026-11-01": "0.002"}, "2026-11-01")
    return chain


class TestFall13:
    def test_avkastning_avgift_och_skatt_pa_oppningskapitalet(self):
        result = mc.compute_month(NOVEMBER, Decimal("0.01"), Decimal("0.002"), Decimal("0.00354"),
                                  [Origin("spar", "del", Decimal("100000.00"))], [])
        assert result.amounts == {("spar", "return"): Decimal("1000.00"), ("spar", "fee"): Decimal("-16.67"),
                                  ("spar", "tax"): Decimal("-29.50")}
        assert result.closing == {"spar": Decimal("100953.83")}
        assert result.totals["closing_sek"] == Decimal("100953.83")

    def test_satserna_ar_2026_ars_parametrar(self, chain):
        with chain.factory() as s:
            fee, tax, _, _ = parameters.capital_rates(s, [NOVEMBER])[NOVEMBER]
        assert (fee, tax) == (Decimal("0.002"), Decimal("0.00354"))


class TestNovemberstangningen:
    def test_granskning_och_bokning(self, ready):
        review = prepare(ready)
        assert review["status"] == "open" and review["passed"] and review["problems"] == []
        assert all(c["passed"] for c in review["controls"]), review["controls"]
        assert review["return_basis"]["code"] == "AVK-SIM-2026-02" and review["return_basis"]["rate"] == "0.002"
        assert review["premiums"]["premium_sek"] == "10983.13"  # fall 37: paket A:s allokeringar
        assert count(ready, LedgerBatch) == 1  # granskningen skriver ingenting
        closed = close(ready, checksum=review["review_checksum"])
        assert closed["created"] and closed["review_checksum"] == review["review_checksum"]
        with ready.factory() as s:
            batch = cl.effective_batch(s, NOV_END)
            assert batch.kind == "month_close" and batch.source == "ledger" and batch.supersedes_id is None
            mc.verify_month(s, batch)
            opening = {t.origin_id: t.balance for t in cl.tracks(s, date(2026, 10, 31))}
            closing = {t.origin_id: t.balance for t in cl.tracks(s, NOV_END)}
            entries = s.scalars(select(LedgerCapitalEntry).where(LedgerCapitalEntry.batch_id == batch.id)).all()
            parts = s.scalars(select(LedgerGuaranteePart).where(LedgerGuaranteePart.batch_id == batch.id)).all()
            # Steg 2–3 per spår på öppningsbasen; ett spår per försäkring i det här beståndet. Avkastningen är
            # kollektivets avrundade summa fördelad med största rest (PR-021), så varje spår ligger inom ett öre.
            returns = [e.amount_sek for e in entries if e.reason == "return"]
            assert sum(returns) == (sum(opening.values()) * Decimal("0.002")).quantize(CENT, ROUND_HALF_UP)
            for origin, c0 in opening.items():
                mine = {e.reason: e.amount_sek for e in entries if e.origin_id == origin}
                assert abs(mine["return"] - c0 * Decimal("0.002")) < CENT
                assert mine["fee"] == -(c0 * Decimal("0.002") / 12).quantize(CENT, ROUND_HALF_UP)
                assert mine["tax"] == -(c0 * Decimal("0.00354") / 12).quantize(CENT, ROUND_HALF_UP)
                assert closing[origin] == c0 + sum(mine.values())
            # Steg 4: en garantidel och ett nytt spår per allokering, vid månadsslut och utan avkastning
            assert {(p.origin_kind, p.source, p.value_date, p.received_month) for p in parts} == {
                ("payment_allocation", "ledger", NOV_END, NOVEMBER)}
            premium_entries = [e for e in entries if e.reason == "premium"]
            assert {e.origin_id for e in premium_entries} == {p.id for p in parts}
            assert all(e.balance_before_sek == 0 for e in premium_entries)
            assert not [e for e in entries if e.origin_id in {p.id for p in parts} and e.reason != "premium"]
            assert sum(e.amount_sek for e in premium_entries) == Decimal("10983.13")
            assert sum(closing.values()) == Decimal(batch.content["totals"]["closing_sek"])
            assert s.scalar(select(func.count()).select_from(LedgerControl)
                            .where(LedgerControl.batch_id == batch.id)) == len(review["controls"])

    def test_avstamningskontot_och_efter_manadsslut_ger_ingen_effekt(self, ready):
        review = prepare(ready)
        assert review["premiums"]["suspense_sek"] == "175.00" and review["premiums"]["after_month_end_sek"] == "250.00"
        close(ready)
        with ready.factory() as s:
            booked = set(s.scalars(select(LedgerGuaranteePart.payment_allocation_id).where(
                LedgerGuaranteePart.payment_allocation_id.is_not(None))))
            suspense = set(s.scalars(select(PaymentAllocation.id).where(PaymentAllocation.kind == "suspense")))
        assert booked and not booked & suspense

    def test_ledger_utdraget_och_a6_per_november(self, ready):
        close(ready)
        with ready.factory() as s:
            assert covered_dates(s) == [date(2026, 10, 31), NOV_END]
            extract = build_ledger_extract(s, NOV_END)
            assert extract.approved, [c for c in extract.checks if not c.passed]
            assert extract.months[-1].month == NOVEMBER and extract.months[-1].rate == Decimal("0.002")
            assert extract.bases["AVK-SIM-2026-02"] and "AVK-SIM-2026-01" not in extract.bases
            assert sum(p.capital for p in extract.policies) == extract.months[-1].closing
            assert {c.name: c.passed for c in extract.checks}["en källa per premie"]
            premiums = sum(p.flows.premiums for p in extract.policies)
            assert premiums == Decimal("40000.00") + Decimal("10983.13")  # 2023 års historik plus november
            # Per 2026-10-31 är utdraget detsamma som före stängningen
            assert build_ledger_extract(s, date(2026, 10, 31)).months[-1].month == date(2026, 10, 1)
            valuation = compute_valuation(s, NOV_END, "scenario", source="ledger", **SCENARIO)
        assert valuation.checks_passed and valuation.totals.capital == extract.months[-1].closing

    def test_december_bokar_betalningen_efter_novembers_slut(self, ready, clock):
        close(ready)
        clock.today = date(2027, 1, 4)
        adopt_avk(ready, "AVK-SIM-2026-03", {"2026-11-01": "0.002", "2026-12-01": "0.001"}, "2026-12-01",
                  supersedes="AVK-SIM-2026-02")
        review = prepare(ready, "2026-12-01")
        assert review["passed"] and review["premiums"]["premium_sek"] == "250.00"
        assert review["premiums"]["late_allocations"] == 0
        assert review["previous"]["checksum"] == prepare(ready)["review_checksum"]
        close(ready, "2026-12-01")
        with ready.factory() as s:
            assert covered_dates(s) == [date(2026, 10, 31), NOV_END, DEC_END]
            assert build_ledger_extract(s, DEC_END).approved
            # November är oförändrad efter decemberstängningen
        assert prepare(ready)["status"] == "closed"


class TestStoppunkten:
    @pytest.fixture
    def open_invoice(self, tmp_path, clock):
        """Samma premiekedja men utan decemberbetalningen, så att INV-000003 har 250,00 öppet."""
        engine = create_engine(f"sqlite:///{tmp_path / 'late.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        factory = session_factory_for(engine)
        with factory() as s:
            parameters.add_missing_defaults(s)
            vb.add_missing_defaults(s)
            s.add_all([BaseAmount(year=2023, income_base_amount_sek=Decimal(74300)),
                       BaseAmount(year=2026, income_base_amount_sek=Decimal(83400))])
            employer = Employer(org_number=EMPLOYER, name="Testbolaget AB", affiliation_date=date(2010, 1, 1))
            s.add(employer)
            s.flush()
            for number, pnr in enumerate(PERSONS.values(), start=1):
                _person(s, employer, pnr, number)
            s.commit()
        db = SimpleNamespace(engine=engine, factory=factory)
        salary_file(db, [row(key) for key in PERSONS], "LON-2026-10")
        [first] = invoice(db)
        salary_file(db, [row("C", "50000", "correction", 1)], "LON-2026-10-R1")
        _, rebill = invoice(db)
        bank(db, clock, "BANK-11-10", [event("E1", "10783.13", first.ocr_reference, "2026-11-10")])
        bank(db, clock, "BANK-11-20", [event("E3", "2000.00", rebill.ocr_reference, "2026-11-20")])
        db.rebill = rebill
        yield db
        engine.dispose()

    def test_sen_registrering_bokas_i_nasta_oppna_manad(self, open_invoice, clock):
        db = open_invoice
        clock.today = date(2026, 12, 1)
        open_ledger(db)
        adopt_avk(db, "AVK-SIM-2026-02", {"2026-11-01": "0.002"}, "2026-11-01")
        close(db)
        nov = prepare(db)["review_checksum"]
        # Banken skickar en inbetalning från 2026-11-27 först efter novemberstängningen
        bank(db, clock, "BANK-11-27-SEN", [event("E7", "250.00", db.rebill.ocr_reference, "2026-11-27")])
        clock.today = date(2026, 12, 3)
        after = prepare(db)
        assert after["status"] == "closed" and after["review_checksum"] == nov  # ingen rättelse av november
        with db.factory() as s, pytest.raises(IntakeError, match="stängd"):
            premium_intake(s, NOVEMBER)
        with db.factory() as s:
            december = premium_intake(s, DECEMBER)
        assert december.summary["premium_sek"] == "250.00"
        assert (december.summary["late_allocations"], december.summary["late_sek"]) == (1, "250.00")
        assert {(a.received_month, a.value_date) for a in december.additions} == {(DECEMBER, DEC_END)}


class TestFall15:
    @pytest.fixture
    def two_parts(self, tmp_path, clock):
        """Person A har del 1 i utbetalning sedan 2026-06 och en ej startad del 2 som tar emot premien."""
        engine = create_engine(f"sqlite:///{tmp_path / 'parts.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        factory = session_factory_for(engine)
        with factory() as s:
            parameters.add_missing_defaults(s)
            vb.add_missing_defaults(s)
            s.add_all([BaseAmount(year=2023, income_base_amount_sek=Decimal(74300)),
                       BaseAmount(year=2026, income_base_amount_sek=Decimal(83400))])
            employer = Employer(org_number=EMPLOYER, name="Testbolaget AB", affiliation_date=date(2010, 1, 1))
            s.add(employer)
            s.flush()
            for number, pnr in enumerate(PERSONS.values(), start=1):
                _person(s, employer, pnr, number)
            s.flush()
            policy = s.scalar(select(Policy).join(InsuredPerson, InsuredPerson.id == Policy.insured_person_id)
                              .where(InsuredPerson.personal_id_number == PERSONS["A"]))
            benefit = s.scalar(select(PolicyBenefit).where(PolicyBenefit.policy_id == policy.id))
            part1 = s.scalar(select(PayoutPart).where(PayoutPart.benefit_id == benefit.id))
            state = s.scalar(select(PayoutPartState).where(PayoutPartState.payout_part_id == part1.id))
            state.valid_to = date(2026, 5, 31)
            s.flush()
            s.add(PayoutPartState(payout_part_id=part1.id, state="in_payout", valid_from=date(2026, 6, 1)))
            part1.share_of_origin = Decimal("0.5")
            part2 = PayoutPart(benefit_id=benefit.id, part_number=2, share_of_origin=Decimal("0.5"),
                               split_from_part_id=part1.id, split_date=date(2026, 6, 1), split_share=Decimal("0.5"))
            s.add(part2)
            s.flush()
            s.add(PayoutPartState(payout_part_id=part2.id, state="not_started", valid_from=date(2026, 6, 1)))
            s.commit()
            ids = SimpleNamespace(policy=str(policy.id), part1=part1.id, part2=part2.id)
        db = SimpleNamespace(engine=engine, factory=factory, ids=ids)
        salary_file(db, [row(key) for key in PERSONS], "LON-2026-10")
        [first] = invoice(db)
        bank(db, clock, "BANK-11-10", [event("E1", str(first.total_sek), first.ocr_reference, "2026-11-10")])
        clock.today = date(2026, 12, 1)
        yield db
        engine.dispose()

    def test_premie_pa_ej_startad_del_under_pagaende_pension(self, two_parts):
        db = two_parts
        review = run(db, "preview_ledger_opening", {}).payload
        assert any(n["policy_id"] == db.ids.policy for n in review["not_transferred"])  # del 1 är startad
        open_ledger(db)
        adopt_avk(db, "AVK-SIM-2026-02", {"2026-11-01": "0.002"}, "2026-11-01")
        review = prepare(db)
        assert review["passed"], review["problems"]
        close(db)
        with db.factory() as s:
            mine = s.scalars(select(LedgerGuaranteePart).where(
                LedgerGuaranteePart.payout_part_id.in_([db.ids.part1, db.ids.part2]))).all()
            assert [p.payout_part_id for p in mine] == [db.ids.part2]
            g = mine[0]
            born = date(1985, 5, 15)
            assert g.plan_start == date(born.year + 66, born.month, 1)  # egen referensplan från 66-årsmånaden
            entries = s.scalars(select(LedgerCapitalEntry).where(
                LedgerCapitalEntry.payout_part_id.in_([db.ids.part1, db.ids.part2]))).all()
            # Ingen avkastning denna månad; den pågående delen får inga poster
            assert [(e.payout_part_id, e.reason) for e in entries] == [(db.ids.part2, "premium")]
            assert entries[0].amount_sek == g.premium_sek > 0
            extract = build_ledger_extract(s, NOV_END)
        assert extract.approved, [c for c in extract.checks if not c.passed]
        assert [n.policy_id for n in extract.not_calculated].count(db.ids.policy) == 1


class TestFall16:
    def test_samma_stangning_igen_ger_inga_nya_poster(self, ready):
        first = close(ready)
        before = count(ready, LedgerCapitalEntry), count(ready, LedgerGuaranteePart), count(ready, LedgerBatch)
        again = close(ready, checksum=first["review_checksum"])
        assert not again["created"] and again["batch_id"] == first["batch_id"]
        review = prepare(ready)
        assert review["status"] == "closed" and review["review_checksum"] == first["review_checksum"]
        assert (count(ready, LedgerCapitalEntry), count(ready, LedgerGuaranteePart), count(ready, LedgerBatch)) == before
        with pytest.raises(ConflictError, match="annat innehåll"):
            close(ready, checksum="0" * 64)

    def test_andrad_avk_efter_stangningen_ger_rattelse_med_motposter(self, ready):
        first = close(ready)
        with ready.factory() as s:
            before = {t.origin_id: t.balance for t in cl.tracks(s, NOV_END)}
            returns = {e.origin_id: e.amount_sek for e in s.scalars(select(LedgerCapitalEntry).where(
                LedgerCapitalEntry.reason == "return"))}
        g_before = count(ready, LedgerGuaranteePart)
        adopt_avk(ready, "AVK-SIM-2026-03", {"2026-11-01": "0.003"}, "2026-11-15", supersedes="AVK-SIM-2026-02")
        review = prepare(ready)
        assert review["status"] == "correction" and review["kind"] == "month_correction" and review["passed"]
        assert review["version"] == 2 and review["supersedes"] == first["review_checksum"]
        assert review["return_basis"] == {**review["return_basis"], "code": "AVK-SIM-2026-03", "rate": "0.003"}
        fixed = close(ready, checksum=review["review_checksum"])
        assert fixed["created"]
        with ready.factory() as s:
            chain = cl.month_chain(s, NOV_END)
            assert [b.kind for b in chain] == ["month_close", "month_correction"]
            assert chain[1].supersedes_id == chain[0].id
            corrections = s.scalars(select(LedgerCapitalEntry).where(LedgerCapitalEntry.batch_id == chain[1].id)).all()
            # Motposterna är nettodifferensen för avkastningen; avgift, skatt och garanti är oförändrade
            assert {e.reason for e in corrections} == {"return"}
            for e in corrections:  # ny avkastning 0,3 % i stället för 0,2 % på samma öppningskapital
                c0 = before[e.origin_id] - returns[e.origin_id] - sum(
                    x.amount_sek for x in s.scalars(select(LedgerCapitalEntry).where(
                        LedgerCapitalEntry.origin_id == e.origin_id, LedgerCapitalEntry.month == NOVEMBER,
                        LedgerCapitalEntry.reason.in_(("fee", "tax")))))
                assert abs(returns[e.origin_id] + e.amount_sek - c0 * Decimal("0.003")) < CENT  # största rest
            after = {t.origin_id: t.balance for t in cl.tracks(s, NOV_END)}
            assert sum(after.values()) - sum(before.values()) == sum(e.amount_sek for e in corrections) > 0
            assert sum(after.values()) == Decimal(chain[1].content["totals"]["closing_sek"])
            mc.verify_month(s, chain[1])
            extract = build_ledger_extract(s, NOV_END)
        assert count(ready, LedgerGuaranteePart) == g_before
        assert extract.approved and extract.months[-1].rate == Decimal("0.003")
        assert "AVK-SIM-2026-03" in extract.bases
        again = prepare(ready)
        assert again["status"] == "closed" and again["review_checksum"] == fixed["review_checksum"]
        # Den ursprungliga summan är redan bokad i kedjan och ger ingen ny effekt
        assert not close(ready, checksum=first["review_checksum"])["created"]

    def test_bara_senast_stangda_manaden_kan_rattas(self, ready, clock, monkeypatch):
        close(ready)
        clock.today = date(2027, 1, 4)
        adopt_avk(ready, "AVK-SIM-2026-03", {"2026-11-01": "0.002", "2026-12-01": "0.001"}, "2026-12-01",
                  supersedes="AVK-SIM-2026-02")
        close(ready, "2026-12-01")
        real = mc._returns

        def changed(session, end, months):
            row, rates = real(session, end, months)
            return row, {m: (Decimal("0.004") if m == NOVEMBER else r) for m, r in rates.items()}

        monkeypatch.setattr(mc, "_returns", changed)
        with pytest.raises(BlockedError, match="senast stängda"):
            prepare(ready)

    def test_andrad_bokad_premie_i_paket_a_blockerar(self, ready):
        close(ready)
        with ready.factory() as s:
            allocation_id = s.scalar(select(LedgerGuaranteePart.payment_allocation_id).where(
                LedgerGuaranteePart.payment_allocation_id.is_not(None)).limit(1))
            allocation = s.get(PaymentAllocation, allocation_id)
            allocation.amount_sek += Decimal("1.00")
            s.commit()
        with pytest.raises(BlockedError, match="ändrats i paket A"):
            prepare(ready)


class TestFall17:
    def test_ingen_antagen_avk_blockerar_utan_att_nagot_skrivs(self, chain):
        open_ledger(chain)
        with pytest.raises(BlockedError, match="(?i)avkastning"):
            prepare(chain)
        # Ett förslag som inte är antaget räcker inte
        with chain.factory() as s:
            base = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "AVK-SIM-2026-01")).assumptions
        months = [*vb.normalize("return_series", base)["months"], {"month": "2026-11-01", "rate": "0.002"}]
        run(chain, "propose_valuation_basis", {"code": "AVK-SIM-2026-02", "title": "Syntetisk avkastning",
                                                "assumptions": vb.normalize("return_series", {**base, "months": months}),
                                                "source_refs": "test", "supersedes_code": "AVK-SIM-2026-01"})
        with pytest.raises(BlockedError, match="(?i)avkastning"):
            prepare(chain)
        with pytest.raises(BlockedError, match="(?i)avkastning"):
            close(chain, checksum="0" * 64)
        assert count(chain, LedgerBatch) == 1 and count(chain, LedgerControl) == count(
            chain, LedgerControl, LedgerControl.batch_id.in_(select(LedgerBatch.id).where(
                LedgerBatch.kind == "opening_s04")))


class TestSparrar:
    def test_manaden_maste_ha_tagit_slut(self, ready, clock):
        clock.today = NOV_END
        with pytest.raises(BlockedError, match="inte tagit slut.*2026-12-01"):
            prepare(ready)

    def test_manaderna_stangs_i_ordning(self, ready, clock):
        clock.today = date(2027, 1, 4)
        with pytest.raises(BlockedError, match="Föregående månad 2026-11"):
            prepare(ready, "2026-12-01")
        with pytest.raises(BlockedError, match="ingående läget"):
            prepare(ready, "2026-10-01")
        with ready.factory() as s, pytest.raises(IntakeError, match="Föregående månad"):
            premium_intake(s, DECEMBER)

    def test_utan_ingaende_lage_blockeras(self, chain):
        with pytest.raises(BlockedError, match="ingående läge"):
            prepare(chain)

    def test_startad_del_med_kapital_blockerar(self, ready):
        with ready.factory() as s:
            part = s.scalars(select(PayoutPart)).first()
            state = s.scalar(select(PayoutPartState).where(PayoutPartState.payout_part_id == part.id))
            state.valid_to = date(2026, 11, 14)
            s.flush()
            s.add(PayoutPartState(payout_part_id=part.id, state="in_payout", valid_from=date(2026, 11, 15)))
            s.commit()
        with pytest.raises(BlockedError, match="startat"):
            prepare(ready)

    def test_registrerat_dodsfall_blockerar(self, ready):
        with ready.factory() as s:
            person = s.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == PERSONS["B"]))
            person.status = "deceased"
            s.commit()
        review = prepare(ready)
        assert not review["passed"] and "avliden" in review["problems"][0]
        with pytest.raises(BlockedError, match="avliden"):
            close(ready, checksum=review["review_checksum"])
        assert count(ready, LedgerBatch) == 1

    def test_66_arsmanaden_stangs_och_redovisas(self, ready, monkeypatch):
        # Med 41 år som pensionsålder i provet har A (1985-05), B (1978) och C (1982) passerat startmånaden, inte D (1990)
        monkeypatch.setattr(mc, "PENSION_AGE", 41)
        # Steg 4 (V6): passerad startmånad utan plan ger ett ärende payout_review per person, sparandet stängs
        review = prepare(ready)
        assert review["passed"] and len(review["standard_start_pending"]) == 3
        control = next(c for c in review["controls"] if c["step"] == "standardstart")
        assert control["passed"] and control["actual"] == "0" and "3 nya ärenden" in control["detail"]
        assert len(review["payout"]["review_cases"]) == 3
        close(ready, checksum=review["review_checksum"])
        with ready.factory() as s:
            states = s.scalars(select(PayoutPartState.state).where(PayoutPartState.valid_to.is_(None))).all()
            cases = s.scalars(select(Case).where(Case.case_type == "payout_review")).all()
        assert set(states) == {"not_started"}  # startmånaden flyttas inte och ingen plan skapas
        assert len(cases) == 3 and {c.details["reason"] for c in cases} == {"passed_66_without_plan"}


class TestBefogenheter:
    @pytest.mark.parametrize("name, data", [
        ("prepare_month_close", {"month": "2026-11-01"}),
        ("close_policy_month", {"month": "2026-11-01", "reviewed_checksum": "0" * 64}),
        ("get_month_close", {"month": "2026-11-01"}),
    ])
    def test_agenter_nekas(self, ready, name, data):
        with pytest.raises(AccessDeniedError):
            run(ready, name, data, ctx=AGENT)

    def test_stangningen_bokas_bara_av_manniska(self, ready):
        review = prepare(ready)
        with pytest.raises(AccessDeniedError, match="människa"):
            run(ready, "close_policy_month", {"month": "2026-11-01", "reviewed_checksum": review["review_checksum"]},
                ctx=SYSTEM)

    def test_get_month_close_visar_versionerna(self, ready):
        with pytest.raises(BlockedError, match="inte stängd"):
            run(ready, "get_month_close", {"month": "2026-11-01"})
        first = close(ready)
        view = run(ready, "get_month_close", {"month": "2026-11-01"}).payload
        assert view["effective"]["checksum"] == first["review_checksum"]
        assert [v["kind"] for v in view["versions"]] == ["month_close"]


class TestVillkor:
    def test_kedjans_villkor(self, ready):
        first = close(ready)
        with ready.factory() as s:
            batch = s.get(LedgerBatch, __import__("uuid").UUID(first["batch_id"]))
            base = {"period_end": NOV_END, "source": "ledger", "content": {}, "created_by": "prov"}
            bad = [
                {"kind": "month_close", "checksum": "a" * 64},  # en andra stängning för samma månad
                {"kind": "month_correction", "checksum": "b" * 64},  # rättelse utan ersatt version
                {"kind": "month_close", "checksum": "c" * 64, "period_end": DEC_END,
                 "supersedes_id": batch.id},  # stängning som pekar på en version
            ]
            for values in bad:
                with pytest.raises(IntegrityError), s.begin_nested():
                    s.add(LedgerBatch(**{**base, **values}))
                    s.flush()
            s.add(LedgerBatch(**{**base, "kind": "month_correction", "checksum": "d" * 64, "supersedes_id": batch.id}))
            s.flush()
            # Varje version ersätts högst en gång
            with pytest.raises(IntegrityError), s.begin_nested():
                s.add(LedgerBatch(**{**base, "kind": "month_correction", "checksum": "e" * 64,
                                     "supersedes_id": batch.id}))
                s.flush()
            s.rollback()

    def test_premiekallan_tar_inte_emot_premie_i_s04(self, ready):
        close(ready)
        with ready.factory() as s:
            s04 = s.scalar(select(LedgerGuaranteePart).where(LedgerGuaranteePart.origin_kind == "s04_premium"))
            ours = s.scalar(select(LedgerGuaranteePart).where(LedgerGuaranteePart.origin_kind == "payment_allocation"))
            ours.premium_transaction_id = s04.premium_transaction_id
            s.flush()
            extract = build_ledger_extract(s, NOV_END)
            assert not {c.name: c.passed for c in extract.checks}["en källa per premie"]
            assert s.get(PremiumTransaction, s04.premium_transaction_id) is not None
