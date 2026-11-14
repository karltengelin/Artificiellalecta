"""Den operativa kapital- och garantijournalen (paket B steg 2, B-047 punkt 4, P1-PENSION-001 §6 och §11).

Beståndet och premiekedjan är desamma som i överlämningen till månadsjournalen
(`test_premium_month_export`): fyra premiebetalande försäkrade med mottagen historik, oktoberpremier ur
paket A med delbetalning, rättelser, tillägg, avstämningskonto och en betalning efter månadsslutet.

- **Fall 36:** övergången från S-04 per 2026-10-31 bevarar varje försäkrings C i ören och G i tio decimaler,
  märkt `reconstructed_s04` och knutet till uttagsdel 1; A6 med källan `ledger` ger samma värdering.
- **Fall 37:** novembers premier är exakt paket A:s allokeringar på fakturarader, delbetalningen ingår och
  avstämningskontot följer inte med. Inget bokas förrän månadsstängningen (steg 3).
- P6-MANAD-001 läser den operativa journalen som IB och skriver aldrig tillbaka till den (§6.3).

Lakebase-beloppen (42 087 223,57 kr, 119 195,6502916268 kr/mån, 51 623,90 kr) prövas med körskriptet
`scripts/simulation/paket_b_steg2/verify.py` på en återställd kopia av Lakebase-backupen.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError

from models import (
    Base,
    LedgerBatch,
    LedgerCapitalEntry,
    LedgerControl,
    LedgerGuaranteePart,
    PaymentAllocation,
    PayoutPart,
    PayoutPartState,
    PremiumTransaction,
    ValuationExtractRecord,
)
from services import Actor, BlockedError, OperationContext
from services import capital_ledger as cl
from services.db import session_factory_for
from services.errors import AccessDeniedError, ConflictError
from services.ledger_extract import build_ledger_extract
from services.ledger_premiums import IntakeError, premium_intake
from services.premium_month_inputs import MonthInputs
from services.valuation import compute_valuation
from services.valuation_extract import ExtractError, build_extract
from skills.calculation.premium_origin_ledger import reconstruct_origins
from tests import test_premium_month_export as export_tests
from tests.test_premium_month_export import (
    HUMAN,
    open_and_receive,
    package_a_allocations,
    run,
)

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

#: Premiekedjan och klockan från överlämningstestet (fixturer)
chain = export_tests.chain
clock = export_tests.clock

OPENING = date(2026, 10, 31)
NOVEMBER = date(2026, 11, 1)
SCENARIO = {"basis_code": "SIM-V-2026-01", "curve_code": "FI-SIM-2026-10"}
AGENT = OperationContext(actor=Actor.agent("forsakring", team="forsakring"), reason="prov")
SYSTEM = OperationContext(actor=Actor.system("system:prov"), reason="prov")


def preview(db, **data):
    return run(db, "preview_ledger_opening", data).payload


def open_ledger(db):
    review = preview(db)
    return run(db, "open_capital_ledger", {"reviewed_checksum": review["review_checksum"]}).payload


def totals(extract):
    return {p.policy_id: (p.capital, sum((g.guarantee for g in p.guarantee_parts), Decimal(0)))
            for p in extract.policies}


class TestFall36:
    def test_overgangen_bevarar_c_och_g_per_forsakring_exakt(self, chain):
        with chain.factory() as s:
            s04 = build_extract(s, OPENING)
        review = preview(chain, expected_extract_checksum=s04.checksum)
        assert review["passed"] and not review["opened"] and review["problems"] == []
        assert all(c["passed"] for c in review["controls"])
        assert review["totals"]["capital_sek"] == str(sum((p.capital for p in s04.policies), Decimal(0)))
        # Granskningssumman omfattar den väntade utdragshashen, så bokningen anger samma hash
        with pytest.raises(ConflictError, match="ändrats sedan granskningen"):
            run(chain, "open_capital_ledger", {"reviewed_checksum": review["review_checksum"]})
        opened = run(chain, "open_capital_ledger", {"reviewed_checksum": review["review_checksum"],
                                                    "expected_extract_checksum": s04.checksum}).payload
        assert opened["created"] and opened["review_checksum"] == review["review_checksum"]
        with chain.factory() as s:
            ledger = build_ledger_extract(s, OPENING)
            assert ledger.source == "ledger" and ledger.approved
            assert totals(ledger) == totals(s04)
            assert len(s04.policies) == 4
            # En garantidel och ett IB-spår per premierad, märkta S-04 och knutna till uttagsdel 1
            parts = s.scalars(select(LedgerGuaranteePart)).all()
            entries = s.scalars(select(LedgerCapitalEntry)).all()
            assert len(parts) == len(entries) == sum(len(p.guarantee_parts) for p in s04.policies)
            assert {(p.origin_kind, p.source, p.version, p.reason) for p in parts} == {
                ("s04_premium", "reconstructed_s04", 1, "premium")}
            assert {(e.account, e.reason, e.source, e.balance_before_sek) for e in entries} == {
                ("customer_capital", "opening", "reconstructed_s04", Decimal("0.00"))}
            assert {e.origin_id for e in entries} == {p.id for p in parts}
            numbers = s.scalars(select(PayoutPart.part_number).where(
                PayoutPart.id.in_({p.payout_part_id for p in parts}))).all()
            assert set(numbers) == {1}
            premiums = {str(p.premium_transaction_id) for p in parts}
            assert premiums == {g.premium_id for p in s04.policies for g in p.guarantee_parts}
            # Historiska premierader ändras inte; utdraget sparas och pekas ut av verifikationen
            batch = cl.opening_batch(s)
            assert s.get(ValuationExtractRecord, batch.extract_id).checksum == s04.checksum
            assert s.scalar(select(func.count()).select_from(LedgerControl)) == len(review["controls"])

    def test_spar_ar_ursprungen_ur_s04_i_oren(self, chain):
        open_ledger(chain)
        with chain.factory() as s:
            origins, _ = reconstruct_origins(build_extract(s, OPENING))
            found = cl.tracks(s, OPENING)
        assert sorted((o.id, o.policy_id, o.capital) for o in origins) == \
            sorted((t.origin_ref, t.policy_id, t.balance) for t in found)

    def test_a6_varderar_journalen_som_s04(self, chain):
        open_ledger(chain)
        with chain.factory() as s:
            a = compute_valuation(s, OPENING, "scenario", **SCENARIO)
            b = compute_valuation(s, OPENING, "scenario", source="ledger", **SCENARIO)
        assert (a.extract.source, b.extract.source) == ("reconstructed_s04", "ledger")
        assert b.checks_passed
        for name in ("policies", "capital", "guarantee", "fta", "expenses", "surplus", "deficit"):
            assert getattr(a.totals, name) == getattr(b.totals, name), name

    def test_run_valuation_med_kallan_ledger(self, chain):
        with pytest.raises(BlockedError, match="ingående läge"):
            run(chain, "run_valuation", {"valuation_date": "2026-10-31", "purpose": "scenario", "source": "ledger",
                                         **SCENARIO})
        open_ledger(chain)
        detail = run(chain, "run_valuation", {"valuation_date": "2026-10-31", "purpose": "scenario",
                                              "source": "ledger", **SCENARIO})
        assert detail.source == "ledger" and detail.checks_passed
        # Journalen har inget stängt läge för november förrän månadsstängningen finns (steg 3)
        with pytest.raises(BlockedError, match="stängt läge"):
            run(chain, "run_valuation", {"valuation_date": "2026-11-30", "purpose": "scenario", "source": "ledger",
                                         **SCENARIO})

    def test_samma_overgang_igen_ger_ingen_ny_effekt(self, chain):
        first = open_ledger(chain)
        with chain.factory() as s:
            count = s.scalar(select(func.count()).select_from(LedgerCapitalEntry))
        again = run(chain, "open_capital_ledger", {"reviewed_checksum": first["review_checksum"]}).payload
        assert not again["created"] and again["batch_id"] == first["batch_id"]
        assert preview(chain)["opened"]
        with chain.factory() as s:
            assert s.scalar(select(func.count()).select_from(LedgerCapitalEntry)) == count
            assert s.scalar(select(func.count()).select_from(LedgerBatch)) == 1
        with pytest.raises(ConflictError, match="annat innehåll"):
            run(chain, "open_capital_ledger", {"reviewed_checksum": "0" * 64})

    def test_andrat_underlag_efter_granskningen_ger_konflikt(self, chain):
        review = preview(chain)
        with chain.factory() as s:
            tx = s.scalar(select(PremiumTransaction).where(PremiumTransaction.status == "paid"))
            s.add(PremiumTransaction(benefit_id=tx.benefit_id, period_month=date(2023, 2, 1),
                                     transaction_type="premium", amount_sek=Decimal("500.00"), status="paid",
                                     paid_date=date(2023, 2, 15)))
            s.commit()
        with pytest.raises(ConflictError, match="ändrats sedan granskningen"):
            run(chain, "open_capital_ledger", {"reviewed_checksum": review["review_checksum"]})
        with chain.factory() as s:
            assert cl.opening_batch(s) is None

    def test_fel_utdragshash_stoppar(self, chain):
        review = preview(chain, expected_extract_checksum="a" * 64)
        assert not review["passed"]
        with pytest.raises(BlockedError, match="utdragets kontrollsumma"):
            run(chain, "open_capital_ledger", {"reviewed_checksum": review["review_checksum"],
                                               "expected_extract_checksum": "a" * 64})

    def test_pagaende_uttag_fors_inte_over_och_redovisas(self, chain):
        with chain.factory() as s:
            part = s.scalars(select(PayoutPart)).first()
            state = s.scalar(select(PayoutPartState).where(PayoutPartState.payout_part_id == part.id))
            state.valid_to = date(2026, 5, 31)
            s.flush()
            s.add(PayoutPartState(payout_part_id=part.id, state="in_payout", valid_from=date(2026, 6, 1)))
            s.commit()
        review = preview(chain)
        assert review["passed"] and len(review["not_transferred"]) == 1
        open_ledger(chain)
        with chain.factory() as s:
            ledger = build_ledger_extract(s, OPENING)
            assert len(ledger.policies) == 3 and len(ledger.not_calculated) == 1
            assert "Påbörjat uttag" in ledger.not_calculated[0].reason


class TestFall37:
    def test_novembers_premier_ar_paket_as_allokeringar(self, chain):
        open_ledger(chain)
        with chain.factory() as s:
            intake = premium_intake(s, NOVEMBER)
            allocations = {a.id: a.amount_sek for a in s.scalars(select(PaymentAllocation).where(
                PaymentAllocation.kind == "invoice_line"))}
        expected = package_a_allocations(chain)
        assert Decimal(intake.summary["premium_sek"]) == sum(expected.values()) == Decimal("10983.13")
        # En garantidel per allokering, med allokeringens belopp – delbetalningen E1 ingår
        assert {a.payment_allocation_id: a.premium_sek for a in intake.additions} == {
            k: v for k, v in allocations.items() if k in {a.payment_allocation_id for a in intake.additions}}
        assert len(intake.additions) == len([v for v in allocations.values()]) - 1  # E6 hör till december
        assert {(a.value_date, a.received_month, a.basis_code) for a in intake.additions} == {
            (date(2026, 11, 30), NOVEMBER, "SIM-G-2026-01")}
        assert all(a.guarantee_sek_per_month > 0 and a.factor > 0 for a in intake.additions)
        # Avstämningskontot följer inte med: 75,00 överskott på tillägget och 100,00 med okänd OCR
        assert intake.summary["suspense_sek"] == "175.00"
        assert intake.summary["after_month_end_sek"] == "250.00"
        with chain.factory() as s:
            assert s.scalar(select(func.count()).select_from(LedgerGuaranteePart).where(
                LedgerGuaranteePart.origin_kind == "payment_allocation")) == 0  # ingenting bokat (steg 3)

    def test_premien_hamnar_pa_uttagsdelen_den_raknades_for(self, chain):
        open_ledger(chain)
        with chain.factory() as s:
            intake = premium_intake(s, NOVEMBER)
            for a in intake.additions:
                part = s.get(PayoutPart, a.payout_part_id)
                tx = s.get(PremiumTransaction, a.premium_transaction_id)
                assert part.benefit_id == tx.benefit_id
                assert part.part_number == tx.calculation_basis["payout_part"]

    def test_december_tar_hansyn_till_novembers_fordelning(self, chain):
        open_ledger(chain)
        with chain.factory() as s:
            december = premium_intake(s, date(2026, 12, 1))
        assert december.summary["premium_sek"] == "250.00" and december.summary["receipts"] == 1

    def test_samma_lage_ger_samma_kontrollsumma(self, chain):
        open_ledger(chain)
        with chain.factory() as s:
            assert premium_intake(s, NOVEMBER).checksum == premium_intake(s, NOVEMBER).checksum

    def test_operationen_visar_manadens_premier(self, chain):
        open_ledger(chain)
        payload = run(chain, "preview_ledger_premiums", {"month": "2026-11-01"}).payload
        assert payload["premium_sek"] == "10983.13" and payload["by_employer"] == {"5560000001": "10983.13"}
        assert len(payload["additions"]) == payload["allocations"]

    def test_blockeras_fore_overgangen_och_for_oktober(self, chain):
        with chain.factory() as s, pytest.raises(IntakeError, match="ingående läge"):
            premium_intake(s, NOVEMBER)
        open_ledger(chain)
        with chain.factory() as s, pytest.raises(IntakeError, match="S-04:s ingående läge"):
            premium_intake(s, date(2026, 10, 1))

    def test_premie_pa_startad_del_blockeras(self, chain):
        open_ledger(chain)
        with chain.factory() as s:
            a = premium_intake(s, NOVEMBER).additions[0]
            state = s.scalar(select(PayoutPartState).where(PayoutPartState.payout_part_id == a.payout_part_id))
            state.valid_to = date(2026, 11, 14)
            s.flush()
            s.add(PayoutPartState(payout_part_id=a.payout_part_id, state="in_payout", valid_from=date(2026, 11, 15)))
            s.flush()
            with pytest.raises(IntakeError, match="har startat"):
                premium_intake(s, NOVEMBER)


class TestEnKallaPerPremie:
    def test_frammande_rad_i_ingaende_laget_stoppar_utdraget(self, chain):
        """En premie får aldrig ge både ett S-04-ursprung och ett ursprung ur paket A (§6.2 p. 5). I steg 2 finns
        bara det ingående läget, så en sådan rad kan bara hamna där – och verifikationen fångar den. Kontrollen
        "en källa per premie" i ledger-utdraget prövas mot månadsverifikationerna när de finns (steg 3)."""
        open_ledger(chain)
        with chain.factory() as s:
            s04 = s.scalars(select(LedgerGuaranteePart)).first()
            allocation = s.scalar(select(PaymentAllocation).where(PaymentAllocation.kind == "invoice_line"))
            batch = cl.opening_batch(s)
            s.add(LedgerGuaranteePart(
                batch_id=batch.id, payout_part_id=s04.payout_part_id, origin_kind="payment_allocation",
                premium_transaction_id=s04.premium_transaction_id, payment_allocation_id=allocation.id,
                premium_sek=Decimal("1.00"), period_month=s04.period_month, received_month=s04.received_month,
                value_date=s04.value_date, plan_kind="reference_lifelong", plan_start=s04.plan_start,
                basis_code=s04.basis_code, basis_checksum=s04.basis_checksum, factor=s04.factor,
                guarantee_sek_per_month=Decimal("0.01"), source="ledger", created_by="prov"))
            s.flush()
            with pytest.raises(ExtractError, match="stämmer inte med verifikationen"):
                build_ledger_extract(s, OPENING)


class TestP6LaserJournalen:
    def test_scenariot_utgar_fran_journalen_och_skriver_aldrig_tillbaka(self, chain):
        open_ledger(chain)
        with chain.factory() as s:
            ledger_checksum = build_ledger_extract(s, OPENING).checksum
            before = (s.scalar(select(func.count()).select_from(LedgerCapitalEntry)),
                      s.scalar(select(func.count()).select_from(LedgerGuaranteePart)))
            s04 = build_extract(s, OPENING)
        payload = run(chain, "export_premium_month", {"period_month": "2026-10-01", "scenario_id": "paket-b-ib-v1",
                                                     "expected_opening_checksum": ledger_checksum}).payload
        package = MonthInputs.model_validate_json(payload["inputs_json"])
        assert package.opening.source == "ledger" and package.opening.checksum == ledger_checksum
        open_and_receive(chain, payload)
        with chain.factory() as s:
            from models import PremiumMonthJournal

            journal = s.get(PremiumMonthJournal, package.scenario_id)
            origins = {o["id"]: Decimal(o["capital"]) for o in journal.content["origins"]}
            assert journal.content["replay_checksum"] == cl.opening_batch(s).checksum
            assert origins == {o.id: o.capital for o in reconstruct_origins(s04)[0]}
            after = (s.scalar(select(func.count()).select_from(LedgerCapitalEntry)),
                     s.scalar(select(func.count()).select_from(LedgerGuaranteePart)))
        assert after == before  # scenariot skriver aldrig i den operativa journalen

    def test_utan_journal_lases_s04_som_forut(self, chain):
        with chain.factory() as s:
            s04 = build_extract(s, OPENING).checksum
        payload = run(chain, "export_premium_month", {"period_month": "2026-10-01", "scenario_id": "utan-journal",
                                                     "expected_opening_checksum": s04}).payload
        assert MonthInputs.model_validate_json(payload["inputs_json"]).opening.source == "reconstructed_s04"


class TestBefogenheter:
    @pytest.mark.parametrize("name, data", [
        ("preview_ledger_opening", {}),
        ("open_capital_ledger", {"reviewed_checksum": "0" * 64}),
        ("preview_ledger_premiums", {"month": "2026-11-01"}),
    ])
    def test_agenter_nekas(self, chain, name, data):
        with pytest.raises(AccessDeniedError):
            run(chain, name, data, ctx=AGENT)

    def test_overgangen_bokas_bara_av_manniska(self, chain):
        review = preview(chain)
        with pytest.raises(AccessDeniedError, match="människa"):
            run(chain, "open_capital_ledger", {"reviewed_checksum": review["review_checksum"]}, ctx=SYSTEM)

    def test_utan_journalens_tabeller_blockeras_operationerna(self, tmp_path):
        engine = create_engine(f"sqlite:///{tmp_path / 'utan.db'}")
        Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables
                                                 if not t.name.startswith("ledger_")])
        from types import SimpleNamespace

        db = SimpleNamespace(engine=engine, factory=session_factory_for(engine))
        with pytest.raises(BlockedError, match="migrate_capital_ledger"):
            run(db, "preview_ledger_opening", {}, ctx=HUMAN)
        with db.factory() as s, pytest.raises(ExtractError, match="ingående läge"):
            build_ledger_extract(s, OPENING)
        engine.dispose()


class TestVillkor:
    def test_negativt_kundkapital_och_dubbelt_ingaende_lage_nekas(self, chain):
        open_ledger(chain)
        with chain.factory() as s:
            entry = s.scalars(select(LedgerCapitalEntry)).first()
            batch = cl.opening_batch(s)
            values = {"batch_id": entry.batch_id, "account": "customer_capital", "payout_part_id": entry.payout_part_id,
                      "origin_id": entry.origin_id, "month": date(2026, 11, 1), "source": "ledger",
                      "created_by": "prov"}
            bad_entries = [
                # negativt kundkapital
                {"reason": "fee", "amount_sek": -entry.balance_after_sek - 1,
                 "balance_before_sek": entry.balance_after_sek, "balance_after_sek": Decimal("-1.00")},
                # saldot efter är inte saldot före plus beloppet
                {"reason": "fee", "amount_sek": Decimal("-1.00"), "balance_before_sek": Decimal("10.00"),
                 "balance_after_sek": Decimal("8.00")},
                # ingående saldo som inte utgår från 0
                {"reason": "opening", "amount_sek": Decimal("1.00"), "balance_before_sek": Decimal("1.00"),
                 "balance_after_sek": Decimal("2.00")},
                # kundkapital utan kapitalspår
                {"origin_id": None, "reason": "return", "amount_sek": Decimal(1), "balance_before_sek": Decimal(0),
                 "balance_after_sek": Decimal(1)},
            ]
            for bad in bad_entries:
                with pytest.raises(IntegrityError), s.begin_nested():
                    s.add(LedgerCapitalEntry(**{**values, **bad}))
                    s.flush()
            # ett andra ingående läge
            with pytest.raises(IntegrityError), s.begin_nested():
                s.add(LedgerBatch(kind="opening_s04", period_end=OPENING, source="reconstructed_s04",
                                  extract_id=batch.extract_id, extract_checksum=batch.extract_checksum,
                                  content={}, checksum="b" * 64, created_by="prov"))
                s.flush()
