"""Månadsrätt, skuld och bolagskonto i månadsstängningen (paket B steg 5, P1-PENSION-001 §11, Karls val W1–W12).

Samma bestånd och premiekedja som i steg 3 och 4 (`test_payout_plans`): fyra försäkrade med paket A:s
oktoberpremier som betalas i november och journalen öppnad från S-04 per 2026-10-31. B fyller 66 i
november 2026. Fallen:

- **Fall 1:** verifierad ägare utan val får standardplanen sparad (ursprung `standard_start`), läget
  `in_payout`, beslutat M och första rätten i november med betalning 2026-12-01 (W3).
- **Fall 14:** rätten dras från kundkapitalet och blir betalningsskuld; posterna per spår i ören (W5).
- **Fall 35:** C räcker inte och bolagskontot räcker inte – månaden stängs, rätten bevaras, det ej
  finansierade står kvar med ett ärende `company_capital`; en ny insättning finansierar det äldsta först (W8).
- **PB11:** den första stängningen med en rätt kräver en registrerad insättning.
- **W9:** premien på en del som startar hålls utanför journalen med ett ärende.
- **Fall 5–6 och januari:** paus, återstart, förlängning och januariomräkning blir verkliga (W2, W4).
- **W10:** rättelse av en månad med anspråk ändrar bara spårens fördelning.
- Utan steg 5:s tabeller beter sig stängningen som i steg 4 (B-052).

Den rena beräkningen (fall 14, 32, 33 och 35) provas i test_pension_claim_calculation.py.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models import (
    Case,
    InsuredPerson,
    LedgerCapitalEntry,
    LedgerGuaranteePart,
    PayoutAmount,
    PayoutPartState,
    PayoutPlan,
    PensionClaim,
    PensionClaimFunding,
    ProductParameter,
    ValuationBasis,
)
from services import Actor, BlockedError, OperationContext
from services import capital_ledger as cl
from services import month_close as mc
from services import payout_plans as pl
from services import pension_claims as pc
from services import valuation_bases as vb
from services.errors import AccessDeniedError
from services.ledger_extract import build_ledger_extract
from tests import test_premium_month_export as export_tests
from tests.test_premium_month_export import PERSONS, run

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

chain = export_tests.chain
clock = export_tests.clock


# Samma hjälpare som i test_payout_plans, utan delad import mellan testfilerna
def open_ledger(db):
    review = run(db, "preview_ledger_opening", {}).payload
    return run(db, "open_capital_ledger", {"reviewed_checksum": review["review_checksum"]}).payload


def adopt_avk(db, code: str, rates: dict[str, str], valid_from: str, supersedes: str = "AVK-SIM-2026-01") -> None:
    with db.factory() as s:
        base = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "AVK-SIM-2026-01")).assumptions
    months = [*vb.normalize("return_series", base)["months"], *({"month": m, "rate": r} for m, r in rates.items())]
    run(db, "propose_valuation_basis", {"code": code, "title": "Syntetisk avkastning för månadsstängningen",
                                         "assumptions": vb.normalize("return_series", {**base, "months": months}),
                                         "source_refs": "test", "supersedes_code": supersedes})
    run(db, "adopt_valuation_basis", {"code": code, "valid_from": valid_from, "decision_ref": "prov W"})


def prepare(db, month="2026-11-01"):
    return run(db, "prepare_month_close", {"month": month}).payload


def close(db, month="2026-11-01", checksum=None):
    review = prepare(db, month) if checksum is None else {"review_checksum": checksum}
    return run(db, "close_policy_month", {"month": month, "reviewed_checksum": review["review_checksum"]}).payload


def count(db, model, *where) -> int:
    with db.factory() as s:
        return s.scalar(select(func.count()).select_from(model).where(*where))


NOVEMBER, NOV_END = date(2026, 11, 1), date(2026, 11, 30)
POLICY = {"A": "AL-000101", "B": "AL-000102", "C": "AL-000103", "D": "AL-000104"}
AGENT = OperationContext(actor=Actor.agent("forsakring", team="forsakring"), reason="prov")
SYSTEM = OperationContext(actor=Actor.system("system:prov"), reason="prov")


def _ready(db, births: dict[str, str]):
    """Ger personerna nya födelsedagar (ÅÅÅÅMMDD) innan journalen öppnas, öppnar den och antar novembers AVK."""
    with db.factory() as s:
        for key, born in births.items():
            person = s.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == PERSONS[key]))
            person.personal_id_number = born + PERSONS[key][-4:]
        s.commit()
    open_ledger(db)
    adopt_avk(db, "AVK-SIM-2026-02", {"2026-11-01": "0.002"}, "2026-11-01")
    return db


def request(db, key, kind, content, received="2026-10-20", **kw):
    data = {"policy_number": POLICY[key], "part_number": kw.pop("part_number", 1), "kind": kind,
            "content": content, "received_date": received, "channel": kw.pop("channel", "customer_portal"), **kw}
    return run(db, "register_payout_request", data).payload


def decide(db, request_id):
    review = run(db, "preview_payout_plan", {"request_id": request_id}).payload
    return run(db, "decide_payout_plan", {"request_id": request_id, "reviewed_checksum": review["review_checksum"],
                                          "reason": "Prov enligt kundens begäran"}).payload


def part_id(db, key, number=1):
    with db.factory() as s:
        return pl.find_part(s, POLICY[key], number).part.id


def without_step5(db):
    """Som Lakebase före steg 5:s migration: inga tabeller för belopp, anspråk och finansiering (B-052)."""
    with db.engine.begin() as conn:
        for table in pc.CLAIM_TABLES[::-1]:
            conn.exec_driver_sql(f"DROP TABLE {table}")
    return db


DECEMBER, JANUARY, FEBRUARY, MARCH = date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1), date(2027, 3, 1)
RATES = {"2026-11-01": "0.002", "2026-12-01": "0.001", "2027-01-01": "0.001", "2027-02-01": "0.001",
         "2027-03-01": "0.001"}


def capital(db, amount="50000.00", ref="Ägarbeslut 2026-11-20 (prov)"):
    return run(db, "register_company_capital", {"amount_sek": amount, "decided_on": "2026-11-20",
                                                "document_ref": ref}).payload


def steps(review) -> dict[str, bool]:
    return {c["step"]: c["passed"] for c in review["controls"]}


def months_ahead(db, clock, until: date) -> None:
    """AVK för månaderna till och med `until` och 2027 års skattebelastning (inte i standardvärdena)."""
    adopt_avk(db, "AVK-SIM-2026-03", {m: r for m, r in RATES.items() if date.fromisoformat(m) <= until},
              "2026-12-01", supersedes="AVK-SIM-2026-02")
    with db.factory() as s:
        s.add(ProductParameter(key="customer_tax_rate", value=Decimal("0.003540"), unit="rate",
                               valid_from=JANUARY, valid_to=date(2027, 12, 31), rule_id="PR-ITP1-023",
                               rule_version="1", source_ref="prov", decision_ref="prov", created_by="prov"))
        s.commit()


def close_month(db, clock, month: date):
    clock.today = date(month.year + (month.month == 12), month.month % 12 + 1, 4)
    review = prepare(db, month.isoformat())
    assert review["passed"], review["problems"]
    close(db, month.isoformat(), review["review_checksum"])
    return review


@pytest.fixture
def at_66(chain):
    """B fyller 66 i november 2026; bolagskontot har en startinsättning (PB11)."""
    db = _ready(chain, {"B": "19601103"})
    capital(db)
    return db


class TestStandardstart:
    def test_fall_1_och_14_standardplanen_sparas_och_forsta_ratten_bokas(self, at_66):
        review = prepare(at_66)
        assert review["passed"], review["problems"]
        b = str(part_id(at_66, "B"))
        [standard] = review["payout"]["standard_start"]
        [claim] = review["pension"]["claims"]
        assert claim["payout_part_id"] == b and claim["right_month"] == "2026-11-01" and claim["right_number"] == 1
        assert claim["payment_day"] == "2026-12-01" and claim["gross_sek"] == standard["m_sek"]
        assert (claim["from_capital_sek"], claim["company_support_sek"], claim["unfunded_sek"]) == (
            standard["m_sek"], "0.00", "0.00")
        [amount] = review["pension"]["amounts"]
        assert amount["reason"] == "start" and amount["m_sek"] == standard["m_sek"]
        passed = steps(review)
        assert all(passed[s] for s in ("standardstart", "månadsrätt", "förbrukade rätter", "skuld och bolagskonto"))
        assert "rätt enligt plan" not in passed
        assert review["totals"]["claims"] == 1 and review["totals"]["pension_debits_sek"] == standard["m_sek"]
        assert review["pension"]["economic_block"] is None
        assert review["pension"]["company"]["liquidity_12m_sek"] == str(12 * Decimal(standard["m_sek"]))
        assert "ej beräknat" in review["pension"]["company"]["stress_gap"]

        close(at_66, checksum=review["review_checksum"])
        with at_66.factory() as s:
            bid = uuid.UUID(b)
            plan = s.scalar(select(PayoutPlan))
            assert (plan.origin, plan.decided_by, plan.checksum) == ("standard_start", "karl", standard["review_checksum"])
            assert plan.first_right == NOVEMBER == plan.effective_month and plan.request_id is None
            assert pl.part_state(s, bid, NOVEMBER) == "in_payout"
            assert pl.part_state(s, bid, date(2026, 10, 1)) == "not_started"
            row = s.scalar(select(PensionClaim))
            assert row.gross_sek == Decimal(standard["m_sek"]) and row.payment_day == date(2026, 12, 1)
            assert s.get(PayoutAmount, row.amount_id).reason == "start"
            # Fall 14: skulden är rätten och kundkapitalet minskar med den, fördelat på spåren i ören
            assert pc.account_balance(s, pc.LIABILITY, NOVEMBER) == row.gross_sek
            debits = s.scalars(select(LedgerCapitalEntry).where(LedgerCapitalEntry.reason == "pension_debit",
                                                               LedgerCapitalEntry.account == cl.CUSTOMER)).all()
            assert sum(e.amount_sek for e in debits) == -row.gross_sek and {e.payout_part_id for e in debits} == {bid}
            assert all(e.balance_after_sek >= 0 for e in debits)
            # Standardplanen räknar om B:s garantidelar (V7)
            assert {g.plan_kind for g in cl.guarantee_parts(s, NOV_END) if g.payout_part_id == bid} == {"plan"}
            mc.verify_month(s, cl.effective_batch(s, NOV_END))
            extract = build_ledger_extract(s, NOV_END)
        assert extract.approved, [c for c in extract.checks if not c.passed]

    def test_w9_premien_pa_delen_som_startar_halls_utanfor_med_arende(self, at_66):
        review = prepare(at_66)
        b = str(part_id(at_66, "B"))
        withheld = review["pension"]["withheld_premiums"]
        assert withheld and {w["payout_part_id"] for w in withheld} == {b}
        assert review["premiums"]["withheld_allocations"] == len(withheld)
        assert [c["reason"] for c in review["pension"]["premium_review_cases"]] == ["premium_after_start"]
        close(at_66, checksum=review["review_checksum"])
        with at_66.factory() as s:
            assert not s.scalars(select(LedgerGuaranteePart).where(
                LedgerGuaranteePart.payout_part_id == uuid.UUID(b), LedgerGuaranteePart.received_month == NOVEMBER)).all()
            [case] = s.scalars(select(Case).where(Case.case_type == "payout_review")).all()
            assert case.details["reason"] == "premium_after_start" and case.details["payout_part_id"] == b

    def test_pb11_utan_insattning_blockerar(self, chain):
        db = _ready(chain, {"B": "19601103"})
        review = prepare(db)
        assert not review["passed"] and any("PB11" in p for p in review["problems"])
        with pytest.raises(BlockedError, match="PB11"):
            close(db, checksum=review["review_checksum"])
        assert count(db, PensionClaim) == 0 and count(db, PayoutPlan) == 0

    def test_ingen_ratt_kraver_ingen_insattning(self, chain):
        db = _ready(chain, {})
        review = prepare(db)
        assert review["passed"] and review["pension"]["claims"] == [] and steps(review)["månadsrätt"]


class TestFall35:
    def test_ekonomiskt_blockerad_korning_och_senare_finansiering(self, chain, clock):
        db = _ready(chain, {"B": "19601103"})
        capital(db, "40.00")
        made = request(db, "B", "start", {"first_right": "2026-11-01", "form": "lifelong"})
        decide(db, made["request_id"])
        with db.factory() as s:  # provet: M större än C, så att kundkapitalet inte räcker
            plan = s.scalar(select(PayoutPlan))
            plan.content = {**plan.content, "amount": {**plan.content["amount"], "m_sek": "1000000.00"}}
            plan.m_sek = Decimal("1000000.00")
            s.commit()
        review = prepare(db)
        assert review["passed"], review["problems"]  # månaden stängs ändå (W8)
        [claim] = review["pension"]["claims"]
        gross, own, support, rest = (Decimal(claim[k]) for k in (
            "gross_sek", "from_capital_sek", "company_support_sek", "unfunded_sek"))
        assert gross == Decimal("1000000.00") and support == Decimal("40.00") and rest > 0 and own > 0
        assert own + support + rest == gross
        block = review["pension"]["economic_block"]
        assert block["unfunded_sek"] == claim["unfunded_sek"] and block["claims"] == 1
        close(db, checksum=review["review_checksum"])
        b = part_id(db, "B")
        with db.factory() as s:
            assert sum(t.balance for t in cl.tracks(s, NOV_END) if t.payout_part_id == b) == 0
            assert pc.account_balance(s, pc.COMPANY, NOVEMBER) == 0
            assert pc.account_balance(s, pc.LIABILITY, NOVEMBER) == own + support  # bara det finansierade
            [case] = s.scalars(select(Case).where(Case.case_type == "company_capital")).all()
            assert case.status == "open" and case.insured_person_id is None and case.employer_id is None
            assert case.details["unfunded_sek"] == str(rest)
            mc.verify_month(s, cl.effective_batch(s, NOV_END))

        # December: ny insättning; det äldsta ej finansierade först, sedan decembers rätt (W8)
        months_ahead(db, clock, DECEMBER)
        capital(db, "3000000.00", ref="Ägarbeslut 2026-12-10 (prov)")
        december = close_month(db, clock, DECEMBER)
        [funding] = december["pension"]["fundings"]
        assert Decimal(funding["amount_sek"]) == rest and funding["remaining_sek"] == "0.00"
        [dec] = december["pension"]["claims"]
        assert dec["right_number"] == 2 and dec["from_capital_sek"] == "0.00"
        assert dec["company_support_sek"] == "1000000.00" and dec["unfunded_sek"] == "0.00"
        assert december["pension"]["economic_block"] is None
        with db.factory() as s:
            assert s.scalar(select(PensionClaimFunding)).amount_sek == rest
            listed = {c["right_month"]: c for c in pc.claims_view(s)}
            assert listed["2026-11-01"]["unfunded_remaining_sek"] == "0.00"
            assert pc.account_balance(s, pc.LIABILITY, DECEMBER) == Decimal("2000000.00")
            assert pc.account_balance(s, pc.COMPANY, DECEMBER) == Decimal("3000040.00") - Decimal("2000000.00") + own


class TestPlanforlopp:
    def test_januariomrakning_med_golv(self, at_66, clock):
        close_month(at_66, clock, NOVEMBER)
        months_ahead(at_66, clock, JANUARY)
        close_month(at_66, clock, DECEMBER)
        january = close_month(at_66, clock, JANUARY)
        [amount] = january["pension"]["amounts"]
        with at_66.factory() as s:
            first = s.scalar(select(PayoutAmount).where(PayoutAmount.effective_month == NOVEMBER))
            claims = s.scalars(select(PensionClaim).order_by(PensionClaim.right_month)).all()
        assert amount["reason"] == "january" and amount["valuation_date"] == "2026-12-31"
        # Livsvarig del under de första 60 rätterna: tidigare M är golv (PR-ITP1-009)
        assert Decimal(amount["floor_sek"]) == first.m_sek and Decimal(amount["m_sek"]) >= first.m_sek
        assert [c.right_number for c in claims] == [1, 2, 3]
        assert [c.payment_day for c in claims] == [date(2026, 12, 1), date(2027, 1, 4), date(2027, 2, 1)]
        assert claims[1].gross_sek == first.m_sek  # beloppet ligger fast mellan besluten

    def test_fall_5_paus_och_aterstart(self, chain, clock):
        db = _ready(chain, {"B": "19601103"})
        capital(db)
        made = request(db, "B", "start", {"first_right": "2026-11-01", "form": "fixed_term", "payments": 60})
        decide(db, made["request_id"])
        close_month(db, clock, NOVEMBER)
        months_ahead(db, clock, MARCH)
        close_month(db, clock, DECEMBER)
        pause = request(db, "B", "pause", {"first": "2027-01-01", "resume": "2027-03-01"}, received="2026-12-20")
        decided = decide(db, pause["request_id"])
        b = part_id(db, "B")
        with db.factory() as s:  # pausen flyttar kalenderslutet två månader
            assert s.get(PayoutPlan, uuid.UUID(decided["plan_id"])).end_month == date(2031, 12, 1)
        january = close_month(db, clock, JANUARY)
        assert january["pension"]["claims"] == []
        with db.factory() as s:
            assert pl.part_state(s, b, JANUARY) == "paused"
        close_month(db, clock, FEBRUARY)
        march = close_month(db, clock, MARCH)
        [claim] = march["pension"]["claims"]
        [amount] = march["pension"]["amounts"]
        assert claim["right_number"] == 3 and amount["reason"] == "restart"
        with db.factory() as s:
            assert pl.part_state(s, b, MARCH) == "in_payout"
            states = s.scalars(select(PayoutPartState.state).where(PayoutPartState.payout_part_id == b)
                               .order_by(PayoutPartState.valid_from)).all()
        assert states == ["not_started", "in_payout", "paused", "in_payout"]

    def test_fall_6_forlangning_till_livsvarig(self, chain, clock):
        db = _ready(chain, {"B": "19601103"})
        capital(db)
        made = request(db, "B", "start", {"first_right": "2026-11-01", "form": "fixed_term", "payments": 60})
        decide(db, made["request_id"])
        close_month(db, clock, NOVEMBER)
        months_ahead(db, clock, JANUARY)
        close_month(db, clock, DECEMBER)
        longer = request(db, "B", "extend", {"month": "2027-01-01", "form": "lifelong"}, received="2026-12-20")
        plan = decide(db, longer["request_id"])
        january = close_month(db, clock, JANUARY)
        [amount] = january["pension"]["amounts"]
        assert amount["reason"] == "plan_change" and amount["m_sek"] == plan["m_sek"]
        assert january["pension"]["claims"][0]["final_settlement"] is False


class TestRattelse:
    def test_w10_andrad_avk_rattar_bara_sparens_fordelning(self, at_66):
        first = close(at_66)
        adopt_avk(at_66, "AVK-SIM-2026-03", {"2026-11-01": "0.003"}, "2026-11-15", supersedes="AVK-SIM-2026-02")
        review = prepare(at_66)
        assert review["status"] == "correction" and review["passed"], review["problems"]
        assert review["supersedes"] == first["review_checksum"]
        close(at_66, checksum=review["review_checksum"])
        with at_66.factory() as s:
            chain_ = cl.month_chain(s, NOV_END)
            assert len(chain_) == 2 and count(at_66, PensionClaim) == 1
            mc.verify_month(s, chain_[-1])
            claim = s.scalar(select(PensionClaim))
            debits = sum(e.amount_sek for e in s.scalars(select(LedgerCapitalEntry).where(
                LedgerCapitalEntry.reason == "pension_debit", LedgerCapitalEntry.account == cl.CUSTOMER)))
            assert debits == -claim.from_capital_sek  # anspråket och skulden är oförändrade


class TestUtanSteg5:
    def test_utan_tabellerna_som_steg_4(self, at_66):
        without_step5(at_66)
        with at_66.factory() as s:
            assert not pc.claims_present(s)
        review = prepare(at_66)
        assert "pension" not in review and "withheld_allocations" not in review["premiums"]
        assert "claims" not in review["totals"] and "pension_debits_sek" not in review["totals"]
        assert any("standardstart" in p and "steg 5" in p for p in review["problems"])
        passed = steps(review)
        assert passed["standardstart"] is False and passed["rätt enligt plan"] is True
        assert "månadsrätt" not in passed
        with pytest.raises(BlockedError, match="migrate_pension_claims"):
            capital(at_66)


class TestBolagskonto:
    def test_insattningen_ar_idempotent_och_listas(self, at_66):
        again = capital(at_66)
        assert not again["created"] and again["month"] == "2026-11-01"
        close(at_66)
        listed = run(at_66, "list_pension_claims", {"month": "2026-11-01"}).payload
        assert listed["count"] == 1 and listed["claims"][0]["right_number"] == 1
        assert Decimal(listed["company"]["balance_sek"]) == Decimal("50000.00")
        assert [i["amount_sek"] for i in listed["company"]["insertions"]] == ["50000.00"]

    def test_insattningen_maste_vara_positiv(self, at_66):
        with pytest.raises(Exception):  # noqa: B017 – schemat avvisar beloppet före tjänsten
            capital(at_66, "0.00")

    @pytest.mark.parametrize("name, data", [
        ("register_company_capital", {"amount_sek": "1.00", "decided_on": "2026-11-20", "document_ref": "prov"}),
        ("list_pension_claims", {}),
    ])
    def test_agenter_nekas(self, at_66, name, data):
        with pytest.raises(AccessDeniedError):
            run(at_66, name, data, ctx=AGENT)

    def test_systemaktoren_nekas_insattning(self, at_66):
        with pytest.raises(AccessDeniedError):
            run(at_66, "register_company_capital", {"amount_sek": "1.00", "decided_on": "2026-11-20",
                                                    "document_ref": "prov"}, ctx=SYSTEM)
