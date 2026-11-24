"""Dödsfallsbesked, dödsfallsavräkning, arvsvinst och dödsbo (paket B steg 7, P1-PENSION-001 §9.1, Karls val Y1–Y14).

Samma bestånd och kedja som i steg 5 och 6 (`test_pension_claims`, `test_payout_orders`): fyra försäkrade med
paket A:s oktoberpremier som betalas i november och journalen öppnad från S-04 per 2026-10-31. B fyller 66 i
november 2026; SIM-R-2026-01 är antagen i standardgrunderna. Fallen:

- **Fall 26:** en sparare dör i november – kapitalet går till poolen, G = 0, delen avslutas (`death`) och
  poolen fördelas samma månad efter E = C × q/(1 − q) (Y4, Y6, Y7). Premien efter dödsfallet hålls utanför.
- **Fall 27:** en pensionär dör i november – dödsmånadens rätt står kvar som dödsboets fordran och betalas
  till dödsboets verifierade konto med 30 % utan småbeloppsgränser, först när delarna är avräknade (Y10).
- **Fall 28:** död före första rätten, på startdagen och under en paus.
- **Fall 29:** utan antagen SIM-R står poolen kvar med ärendet `inheritance_pool`.
- **Fall 30:** ett misstänkt besked stoppar bara bankuppdragen; en förberedd fil ger konflikt; ett
  tillbakadraget besked släpper stoppet (Y2, Y3).
- **Fall 31:** sent besked – ej betalda anspråk efter dödsmånaden återförs exakt, betalda ger ärendet
  `death_recovery` och ingen negativ arvsvinst (Y5).
- **Y8:** rättelse av en månad med avräkning blockeras. **B-052:** utan steg 7:s tabeller som steg 6.
- **Y11:** alla fem operationer är för människor; agenter och systemaktören nekas.
- **Y14:** folkbokföringens simulerade avisering ger misstänkta besked; samma fil igen ger ingen effekt.

Migrationen provas i test_migration_death_reports.py och jämförelsen med main i
scripts/simulation/paket_b_steg7/compare_main.py.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

from models import (
    Case,
    DeathReport,
    DeathSettlement,
    InsuredPerson,
    LedgerCapitalEntry,
    LedgerGuaranteePart,
    PayoutPartState,
    PensionClaimReversal,
    ValuationBasis,
)
from services import BlockedError, ConflictError
from services import capital_ledger as cl
from services import death_reports as dr
from services import month_close as mc
from services import payout_plans as pl
from services import pension_claims as pc
from services.errors import AccessDeniedError
from simulation.counterparties import DeathCase, death_notice_file
from tests import test_payout_orders as orders
from tests import test_premium_month_export as export_tests
from tests.test_payout_orders import (
    B_PNR,
    TAX,
    M,
    account,
    approve,
    cases,
    claim_state,
    create,
    liability,
    receipts,
    tax,
)
from tests.test_pension_claims import (
    AGENT,
    DECEMBER,
    JANUARY,
    NOV_END,
    NOVEMBER,
    SYSTEM,
    _ready,
    adopt_avk,
    capital,
    close_month,
    decide,
    months_ahead,
    part_id,
    prepare,
    request,
    steps,
)
from tests.test_premium_month_export import PERSONS, run

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

chain = export_tests.chain
clock = export_tests.clock
claimed = orders.claimed
ready = orders.ready

A_PNR = PERSONS["A"]
FEBRUARY = date(2027, 2, 1)
COMPARE = Path(__file__).resolve().parents[1] / "scripts" / "simulation" / "paket_b_steg7" / "compare_main.py"
MAIN_SHAPE = COMPARE.with_name("main_shape.json")


def report(db, pnr, status="verified", death="2026-11-10", reported="2026-11-12", received="2026-11-13", **kw):
    data = {"personal_id_number": pnr, "status": status, "reported_on": reported, "received_date": received,
            "source": "relative", "source_ref": "Samtal med anhörig", "channel": "manual", **kw}
    if death is not None:
        data["death_date"] = death
    if status == "verified":
        data = {"verification_method": "population_register", "document_ref": f"SPAR-{pnr[-4:]}", **data}
    return run(db, "register_death_report", data).payload


def change(db, pnr, action, received="2026-11-20", **kw):
    data = {"personal_id_number": pnr, "action": action, "received_date": received, "channel": "manual", **kw}
    return run(db, "verify_death_report", data).payload


def estate(db, account_id, received="2026-12-03", verified=True, pnr=B_PNR):
    data = {"personal_id_number": pnr, "role": "estate_member", "representative": "Dödsbodelägare (prov)",
            "document_kind": "death_certificate_with_family", "document_ref": "DBI-prov-1", "verified": verified,
            "account_id": account_id, "received_date": received, "channel": "manual"}
    if verified:
        data = {"verification_method": "handling", "verification_ref": "Granskad 2026-12-03", **data}
    return run(db, "register_estate_authority", data).payload


def person(s, pnr) -> InsuredPerson:
    return s.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == pnr))


def customer_sum(s, part) -> Decimal:
    return s.scalar(select(func.coalesce(func.sum(LedgerCapitalEntry.amount_sek), 0)).where(
        LedgerCapitalEntry.account == cl.CUSTOMER, LedgerCapitalEntry.payout_part_id == part))


def latest_guarantees(s, part) -> list[LedgerGuaranteePart]:
    rows = s.scalars(select(LedgerGuaranteePart).where(LedgerGuaranteePart.payout_part_id == part)).all()
    replaced = {r.supersedes_id for r in rows}
    return [r for r in rows if r.id not in replaced]


def report_events(db, pnr) -> list[str]:
    with db.factory() as s:
        case = s.scalar(select(Case).where(Case.case_type == "death_report",
                                           Case.insured_person_id == person(s, pnr).id))
        return [e["action"] for e in case.details["events"]]


@pytest.fixture
def at_66(chain, clock):
    """B fyller 66 i november 2026 (standardstart), bolagskontot har en startinsättning; i dag 2026-11-20."""
    db = _ready(chain, {"B": "19601103"})
    capital(db)
    clock.today = date(2026, 11, 20)
    return db


class TestBesked:
    def test_misstankt_verifieras_och_versioneras(self, at_66):
        first = report(at_66, A_PNR, status="suspected", death=None)
        assert first["created"] and first["status"] == "suspected" and first["person_status"] == "active"
        assert not report(at_66, A_PNR, status="suspected", death=None)["created"]  # samma besked igen
        with pytest.raises(BlockedError, match="dödsdag, verifieringssätt"):
            change(at_66, A_PNR, "verify")
        verified = change(at_66, A_PNR, "verify", death_date="2026-11-10", verification_method="death_certificate",
                          document_ref="Dödsbevis prov")
        assert (verified["version"], verified["status"], verified["person_status"]) == (2, "verified", "deceased")
        again = report(at_66, A_PNR, status="suspected", death=None)  # ett verifierat besked nedgraderas inte
        assert not again["created"] and again["status"] == "verified"
        with pytest.raises(BlockedError, match="verify_death_report"):
            report(at_66, A_PNR, death="2026-11-09", reported="2026-11-14", received="2026-11-15")
        moved = change(at_66, A_PNR, "change_date", death_date="2026-11-09")
        assert moved["version"] == 3 and moved["death_date"] == "2026-11-09"
        assert report_events(at_66, A_PNR) == ["registered", "verify", "duplicate", "change_date"]

    def test_datumvillkor(self, at_66):
        with pytest.raises(BlockedError, match="efter rapportdagen"):
            report(at_66, A_PNR, death="2026-11-13", reported="2026-11-12")
        with pytest.raises(BlockedError, match="mottagningsdagen"):
            report(at_66, A_PNR, reported="2026-11-14", received="2026-11-13")
        with pytest.raises(BlockedError, match="framtiden"):
            report(at_66, A_PNR, received="2026-11-21")

    def test_tillbakadraget_aterstaller_status(self, at_66):
        report(at_66, A_PNR)
        with pytest.raises(BlockedError, match="anteckning"):
            change(at_66, A_PNR, "withdraw")
        withdrawn = change(at_66, A_PNR, "withdraw", note="Fel person – förväxlat personnummer")
        assert withdrawn["status"] == "withdrawn" and withdrawn["person_status"] == "active"

    def test_avraknat_besked_kan_inte_andras(self, at_66, clock):
        report(at_66, A_PNR)
        close_month(at_66, clock, NOVEMBER)
        with pytest.raises(BlockedError, match="manuell"):
            change(at_66, A_PNR, "change_date", received="2026-12-04", death_date="2026-11-09")
        with pytest.raises(BlockedError, match="manuell"):
            change(at_66, A_PNR, "withdraw", received="2026-12-04", note="Prov efter avräkningen")


class TestAvrakning:
    def test_fall_26_sparare_till_poolen_och_arvsvinst(self, at_66, clock):
        report(at_66, A_PNR)
        a = part_id(at_66, "A")
        review = close_month(at_66, clock, NOVEMBER)
        passed = steps(review)
        assert passed["dödsfall"] and passed["arvsvinstpool"] and passed["kapital totalt"]
        assert len(review["controls"]) == 17  # steg 6:s femton och dödsfall och arvsvinstpool (Y9)
        death = review["death"]
        [settled] = death["settlements"]
        assert settled["payout_part_id"] == str(a) and settled["death_month"] == "2026-11-01"
        assert settled["reversed_claims"] == 0 and Decimal(settled["estate_liability_sek"]) == 0
        to_pool = Decimal(settled["capital_to_pool_sek"])
        pool = death["pool"]
        assert to_pool > 0 and Decimal(pool["inflow_sek"]) == to_pool
        assert Decimal(pool["distributed_sek"]) == to_pool and pool["closing_sek"] == "0.00"
        assert pool["recipients"] == 3 and pool["basis"]["code"] == "SIM-R-2026-01"
        assert death["guarantee_versions"] >= 1
        assert {w["payout_part_id"] for w in death["withheld_premiums"]} == {str(a)}  # premien efter dödsfallet
        with at_66.factory() as s:
            assert customer_sum(s, a) == 0
            assert pc.account_balance(s, dr.POOL, NOVEMBER) == 0
            assert all(g.guarantee_sek_per_month == 0 and g.reason == "death" for g in latest_guarantees(s, a))
            assert pl.part_state(s, a, NOVEMBER) != "ended" and pl.part_state(s, a, DECEMBER) == "ended"
            ended = s.scalar(select(PayoutPartState).where(PayoutPartState.payout_part_id == a,
                                                           PayoutPartState.valid_to.is_(None)))
            assert ended.end_reason == "death" and ended.valid_from == DECEMBER
            assert s.scalar(select(func.count()).select_from(DeathSettlement)) == 1
            inherited = s.scalars(select(LedgerCapitalEntry).where(LedgerCapitalEntry.reason == "pool_out",
                                                                   LedgerCapitalEntry.account == cl.CUSTOMER)).all()
            assert sum(e.amount_sek for e in inherited) == to_pool and a not in {e.payout_part_id for e in inherited}
            mc.verify_month(s, cl.effective_batch(s, NOV_END))
        assert report_events(at_66, A_PNR) == ["registered", "settled"]

        # December: delen är avräknad, ingen ny avräkning och poolen är tom
        months_ahead(at_66, clock, DECEMBER)
        december = close_month(at_66, clock, DECEMBER)
        assert december["death"]["settlements"] == [] and december["death"]["reports"]["settled_before"] == 1
        assert december["death"]["pool"]["inflow_sek"] == "0.00"

    def test_fall_28_dod_fore_forsta_ratten(self, at_66, clock):
        report(at_66, B_PNR, death="2026-10-25", reported="2026-10-28", received="2026-11-02")
        b = part_id(at_66, "B")
        review = close_month(at_66, clock, NOVEMBER)
        assert review["pension"]["claims"] == [] and review["payout"]["standard_start"] == []
        assert not any(mc.DECEASED_PROBLEM in p for p in review["problems"])
        [settled] = review["death"]["settlements"]
        assert settled["death_month"] == "2026-10-01"
        with at_66.factory() as s:
            assert pl.part_state(s, b, NOVEMBER) == "ended" and customer_sum(s, b) == 0

    def test_fall_28_dod_pa_startdagen_ger_dodsmanadens_ratt(self, at_66, clock):
        report(at_66, B_PNR, death="2026-11-01", reported="2026-11-02", received="2026-11-03")
        b = part_id(at_66, "B")
        review = close_month(at_66, clock, NOVEMBER)
        [claim] = review["pension"]["claims"]
        [settled] = review["death"]["settlements"]
        assert settled["death_month"] == "2026-11-01"
        assert settled["death_month_claim_id"] == claim["id"]
        assert Decimal(settled["estate_liability_sek"]) == Decimal(claim["gross_sek"])
        with at_66.factory() as s:
            assert pl.part_state(s, b, NOVEMBER) == "in_payout" and pl.part_state(s, b, DECEMBER) == "ended"
            assert customer_sum(s, b) == 0 and liability(at_66, NOVEMBER) == Decimal(claim["gross_sek"])

    def test_fall_28_dod_under_paus(self, chain, clock):
        db = _ready(chain, {"B": "19601103"})
        capital(db)
        made = request(db, "B", "start", {"first_right": "2026-11-01", "form": "fixed_term", "payments": 60})
        decide(db, made["request_id"])
        close_month(db, clock, NOVEMBER)
        months_ahead(db, clock, JANUARY)
        close_month(db, clock, DECEMBER)
        pause = request(db, "B", "pause", {"first": "2027-01-01", "resume": "2027-03-01"}, received="2026-12-20")
        decide(db, pause["request_id"])
        clock.today = date(2027, 1, 20)
        report(db, B_PNR, death="2027-01-15", reported="2027-01-16", received="2027-01-18")
        january = close_month(db, clock, JANUARY)
        assert january["pension"]["claims"] == []
        [settled] = january["death"]["settlements"]
        assert settled["death_month"] == "2027-01-01"
        b = part_id(db, "B")
        with db.factory() as s:
            assert pl.part_state(s, b, JANUARY) == "paused" and pl.part_state(s, b, FEBRUARY) == "ended"

    def test_fall_29_utan_riskgrund_star_poolen_kvar(self, at_66, clock):
        with at_66.factory() as s:
            s.execute(delete(ValuationBasis).where(ValuationBasis.family == "SIM-R"))
            s.commit()
        report(at_66, A_PNR)
        review = close_month(at_66, clock, NOVEMBER)
        pool = review["death"]["pool"]
        assert steps(review)["arvsvinstpool"] and pool["distributed_sek"] == "0.00"
        assert pool["closing_sek"] == pool["inflow_sek"] and "SIM-R" in pool["left_reason"]
        with at_66.factory() as s:
            assert pc.account_balance(s, dr.POOL, NOVEMBER) == Decimal(pool["inflow_sek"])
            [case] = s.scalars(select(Case).where(Case.case_type == "inheritance_pool")).all()
            assert case.status == "open" and case.insured_person_id is None
            assert case.details["pool_sek"] == pool["closing_sek"]
            mc.verify_month(s, cl.effective_batch(s, NOV_END))

    def test_y8_rattelse_med_avrakning_blockeras(self, at_66, clock):
        report(at_66, A_PNR)
        close_month(at_66, clock, NOVEMBER)
        adopt_avk(at_66, "AVK-SIM-2026-03", {"2026-11-01": "0.003"}, "2026-11-15", supersedes="AVK-SIM-2026-02")
        with pytest.raises(BlockedError, match="Y8"):
            prepare(at_66)

    def test_misstankt_paverkar_inte_stangningen(self, at_66, clock):
        report(at_66, A_PNR, status="suspected", death=None)
        review = close_month(at_66, clock, NOVEMBER)
        assert review["death"]["settlements"] == [] and review["death"]["reports"]["suspected"] == 1
        assert review["death"]["pool"]["inflow_sek"] == "0.00"


class TestDodsbo:
    def _settled(self, db, clock):
        """B dör 2026-11-20 efter novembers stängning; dödsboets konto och behörighet registreras."""
        tax(db)
        tax(db, tax_year=2027, received="2026-12-01")
        made = report(db, B_PNR, death="2026-11-20", reported="2026-11-25", received="2026-12-02")
        assert made["person_status"] == "deceased"
        blocked = create(db)
        assert blocked["file"] is None and blocked["summary"]["blocked"][0]["reason"] == "estate_missing"
        konto = account(db, number="55550000", received_date="2026-12-03")
        with pytest.raises(BlockedError, match="verifierat dödsfallsbesked|efter dödsdagen"):
            estate(db, konto["account_id"], received="2026-11-19")
        registered = estate(db, konto["account_id"])
        assert registered["verified"] and registered["account"]["account_number"] == "****0000"
        assert create(db)["summary"]["blocked"][0]["reason"] == "estate_missing"  # delarna är inte avräknade
        months_ahead(db, clock, DECEMBER)
        december = close_month(db, clock, DECEMBER)
        assert december["pension"]["claims"] == []  # ingen rätt efter dödsmånaden
        [settled] = december["death"]["settlements"]
        assert settled["death_month"] == "2026-11-01" and Decimal(settled["estate_liability_sek"]) == M
        return december

    def test_fall_27_dodsmanadens_ratt_betalas_till_dodsboet(self, claimed, clock):
        self._settled(claimed, clock)
        made = create(claimed)
        [order] = made["file"]["orders"]
        assert (Decimal(order["gross_sek"]), Decimal(order["tax_sek"])) == (M, TAX)
        assert order["account"]["account_number"] == "****0000"
        approved = approve(claimed, made)
        receipts(claimed, approved, bank_date="2027-01-04")
        assert claim_state(claimed) == "paid" and liability(claimed, JANUARY) == 0
        view = run(claimed, "get_death_settlement", {"personal_id_number": B_PNR}).payload
        assert view["status"] == "deceased" and view["estate"]["account"]["account_number"] == "****0000"
        assert [r["status"] for r in view["reports"]] == ["verified"] and view["unsettled_parts"] == []
        assert view["claims"][0]["reversed"] is False


class TestMisstankt:
    def test_fall_30_misstankt_stoppar_bankuppdraget(self, ready):
        made = report(ready, B_PNR, status="suspected", death=None, reported="2026-12-01", received="2026-12-02")
        assert made["person_status"] == "active"
        blocked = create(ready)
        assert blocked["file"] is None and blocked["summary"]["blocked"][0]["reason"] == "death_suspected"
        assert cases(ready, "payout_hindrance") == []
        change(ready, B_PNR, "withdraw", received="2026-12-03", note="Avisering avsåg annan person")
        assert create(ready)["file"]["status"] == "prepared"

    def test_fall_30_forberedd_fil_ger_konflikt(self, ready):
        made = create(ready)
        report(ready, B_PNR, status="suspected", death=None, reported="2026-12-01", received="2026-12-02")
        with pytest.raises(ConflictError):
            approve(ready, made)


class TestSentBesked:
    def _december(self, db, clock):
        receipts(db, approve(db, create(db)))  # novembers rätt betald 2026-12-04
        months_ahead(db, clock, JANUARY)
        close_month(db, clock, DECEMBER)  # decembers rätt bokad, i dag 2027-01-04
        tax(db, tax_year=2027, received="2027-01-02")

    def test_fall_31_ej_betalt_efter_dodsmanaden_aterfors(self, ready, clock):
        self._december(ready, clock)
        assert liability(ready, DECEMBER) == M
        report(ready, B_PNR, death="2026-11-20", reported="2027-01-02", received="2027-01-03")
        january = close_month(ready, clock, JANUARY)
        passed = steps(january)
        assert passed["dödsfall"] and passed["skuld och bolagskonto"] and passed["kapital totalt"]
        assert january["pension"]["claims"] == []
        [reversal] = january["death"]["reversals"]
        assert reversal["payment_state"] == "funded" and Decimal(reversal["liability_sek"]) == M
        assert Decimal(reversal["capital_sek"]) + Decimal(reversal["company_sek"]) == M
        [settled] = january["death"]["settlements"]
        assert settled["reversed_claims"] == 1 and settled["death_month"] == "2026-11-01"
        assert liability(ready, JANUARY) == 0
        b = part_id(ready, "B")
        with ready.factory() as s:
            assert customer_sum(s, b) == 0
            assert s.scalar(select(func.count()).select_from(PensionClaimReversal)) == 1
            mc.verify_month(s, cl.effective_batch(s, date(2027, 1, 31)))
        assert create(ready, "2027-01-04")["file"] is None  # det återförda betalas inte

    def test_fall_31_betalt_efter_dodsmanaden_ger_aterkrav(self, ready, clock):
        self._december(ready, clock)
        made = create(ready, "2027-01-04")
        assert made["file"]["status"] == "prepared"  # decembers rätt betalas innan beskedet kommer
        receipts(ready, approve(ready, made), bank_date="2027-01-04")
        assert liability(ready, JANUARY) == 0
        clock.today = date(2027, 1, 20)
        report(ready, B_PNR, death="2026-11-20", reported="2027-01-18", received="2027-01-19")
        january = close_month(ready, clock, JANUARY)
        assert january["death"]["reversals"] == [] and len(january["death"]["recoveries"]) == 1
        assert steps(january)["dödsfall"]
        [recovery] = cases(ready, "death_recovery")
        assert recovery == ("open", "death_recovery")
        view = run(ready, "get_death_settlement", {"personal_id_number": B_PNR}).payload
        assert view["recoveries"][0]["right_month"] == "2026-12-01"
        assert Decimal(view["recoveries"][0]["order_gross_sek"]) == M


class TestAvisering:
    def test_y14_aviseringen_ger_misstankta_besked_en_gang(self, at_66):
        sim = death_notice_file([DeathCase(A_PNR, date(2026, 11, 10)),
                                 DeathCase("190001011234", date(2026, 11, 11), "late_notice")],
                                notified_on=date(2026, 11, 12), seed=7)
        assert "scenario" not in str(sim.payload)
        first = run(at_66, "import_death_notices", sim.payload).payload
        assert (first["new"], first["unknown_persons"]) == (1, 1)
        again = run(at_66, "import_death_notices", sim.payload).payload
        assert (again["new"], again["already_received"]) == (0, 1)
        with at_66.factory() as s:
            [row] = s.scalars(select(DeathReport)).all()
            assert row.status == "suspected" and row.channel == "system" and row.notice_id.startswith("SIM")
        with pytest.raises(BlockedError, match="kontrollsumma"):
            run(at_66, "import_death_notices", {**sim.payload, "checksum": "0" * 64})


class TestUtanSteg7:
    def test_b052_utan_tabellerna_som_steg_6(self, at_66, clock):
        with at_66.engine.begin() as conn:
            for table in dr.DEATH_TABLES[::-1]:
                conn.exec_driver_sql(f"DROP TABLE {table}")
        with at_66.factory() as s:
            assert not dr.deaths_present(s)
        clock.today = date(2026, 12, 4)
        review = prepare(at_66)
        assert review["passed"], review["problems"]
        assert "death" not in review and "dödsfall" not in steps(review)
        assert "pool_in_sek" not in review["totals"] and "death_reversed_sek" not in review["pension"]["liability"]
        with pytest.raises(BlockedError, match="migrate_death_reports"):
            report(at_66, A_PNR)

    @pytest.mark.parametrize("scenario", list(json.loads(MAIN_SHAPE.read_text(encoding="utf-8"))))
    def test_y13_samma_form_som_main(self, scenario, tmp_path, monkeypatch):
        """Låser compare_main.py:s resultat: utan steg 7:s tabeller samma kontroller, sektioner och antal rader
        som main:s kod (main_shape.json, räknad med main df93ea2 2026-11-24)."""
        from services.operations import common
        spec = importlib.util.spec_from_file_location("compare_main_steg7", COMPARE)
        compare = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(compare)
        monkeypatch.setattr(common, "today", common.today)  # _build byter klockan; återställs efter provet
        db = str(tmp_path / f"{scenario}.db")
        compare._build(db, scenario)
        result = compare._close(db)
        assert not set(compare.STEP7) & set(result["tables"])
        assert compare.shape(result) == json.loads(MAIN_SHAPE.read_text(encoding="utf-8"))[scenario]


WRITES = [
    ("register_death_report", {"personal_id_number": A_PNR, "status": "suspected", "reported_on": "2026-11-12",
                               "received_date": "2026-11-13", "source": "relative", "source_ref": "Prov",
                               "channel": "manual"}),
    ("verify_death_report", {"personal_id_number": A_PNR, "action": "withdraw", "received_date": "2026-11-13",
                             "note": "Prov", "channel": "manual"}),
    ("import_death_notices", {"file_reference": "X", "checksum": "0" * 64,
                              "notices": [{"notice_id": "N1", "personal_id_number": A_PNR,
                                           "death_date": "2026-11-10", "notified_on": "2026-11-12"}]}),
    ("register_estate_authority", {"personal_id_number": A_PNR, "role": "estate_member", "representative": "Prov",
                                   "document_kind": "estate_inventory", "document_ref": "Prov",
                                   "verified": False, "account_id": "0" * 36, "received_date": "2026-11-13",
                                   "channel": "manual"}),
]


class TestAtkomst:
    @pytest.mark.parametrize("name, data", [*WRITES, ("get_death_settlement", {"personal_id_number": A_PNR})])
    def test_agenter_nekas(self, at_66, name, data):
        with pytest.raises(AccessDeniedError):
            run(at_66, name, data, ctx=AGENT)

    @pytest.mark.parametrize("name, data", WRITES)
    def test_systemaktoren_nekas_skrivning(self, at_66, name, data):
        with pytest.raises(AccessDeniedError):
            run(at_66, name, data, ctx=SYSTEM)

    def test_systemaktoren_far_lasa(self, at_66):
        report(at_66, A_PNR)
        view = run(at_66, "get_death_settlement", {"personal_id_number": A_PNR}, ctx=SYSTEM).payload
        assert view["status"] == "deceased" and view["settlements"] == []
