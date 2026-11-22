"""Begäran, plan, beslut, standardstart och delning med journal och stängning (paket B steg 4, Karls val V1–V11).

Beståndet och premiekedjan är desamma som i steg 3 (`test_month_close`): fyra försäkrade med paket A:s
oktoberpremier som betalas i november och journalen öppnad från S-04 per 2026-10-31. För pensionsfallen
får en eller två av dem en födelsedag nära 66 innan journalen öppnas, så att S-04 och garantidelarna räknas
på den födelsedagen. Fallen ur P1-PENSION-001 §11:

- **Fall 1:** fyller 66 i november 2026 utan val, verifierad – standardplan livsvarig med november som första
  rätt och betalning 2026-12-01; stängningen blockeras tills månadsrätten finns (steg 5, V3–V4).
- **Fall 2 och 12:** uppskov från 66 till 72 i tid – ingen rätt i mellanliggande månader, kapitalet förvaltas
  och varje garantidel räknas om värdebevarande på sin historiska grund i novembers stängning (V7).
- **Fall 3:** sen begäran – förslag på nästa möjliga månad; planen ändras först efter kundens bekräftelse.
- **Fall 4:** N = 59 avslås, N = 60 ger sista rätt oktober 2031.
- **Fall 5–6:** paus och förlängning räknas vägledande på en påbörjad del (beslut kräver bokat underlag).
- **Fall 7:** delning 30/70 i stängningen med G proportionellt; 5 % och fjärde del avslås.
- **Fall 8:** uttag före 66 blockeras med ärende.
- Ärende när underlaget inte kan verifieras och när 66 passerat utan plan (V4–V6), en gång per person.

De rena reglerna (fall 9–12) provas i test_payout_plan_calculation.py.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models import (
    Case,
    Employer,
    InsuredPerson,
    LedgerBatch,
    LedgerGuaranteePart,
    PayoutPart,
    PayoutPartState,
    PayoutPlan,
    PayoutRequest,
    ValuationBasis,
)
from services import Actor, BlockedError, OperationContext
from services import capital_ledger as cl
from services import month_close as mc
from services import payout_plans as pl
from services import valuation_bases as vb
from services.errors import AccessDeniedError, ConflictError
from services.ledger_extract import build_ledger_extract
from services.ledger_premiums import premium_intake
from services.operations.premium_basis import _recipient
from tests import test_premium_month_export as export_tests
from tests.test_premium_month_export import PERSONS, run

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

chain = export_tests.chain
clock = export_tests.clock


# Samma hjälpare som i test_month_close, utan delad import mellan testfilerna
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
    run(db, "adopt_valuation_basis", {"code": code, "valid_from": valid_from, "decision_ref": "prov S5"})


def prepare(db, month="2026-11-01"):
    return run(db, "prepare_month_close", {"month": month}).payload


def close(db, month="2026-11-01", checksum=None):
    review = prepare(db, month) if checksum is None else {"review_checksum": checksum}
    return run(db, "close_policy_month", {"month": month, "reviewed_checksum": review["review_checksum"]}).payload


def count(db, model, *where) -> int:
    with db.factory() as s:
        return s.scalar(select(func.count()).select_from(model).where(*where))

NOVEMBER, DECEMBER = date(2026, 11, 1), date(2026, 12, 1)
OCT_END, NOV_END = date(2026, 10, 31), date(2026, 11, 30)
POLICY = {"A": "AL-000101", "B": "AL-000102", "C": "AL-000103", "D": "AL-000104"}
AGENT = OperationContext(actor=Actor.agent("forsakring", team="forsakring"), reason="prov")
SYSTEM = OperationContext(actor=Actor.system("system:prov"), reason="prov")


def _born(db, births: dict[str, str]) -> None:
    """Ger personerna nya födelsedagar (ÅÅÅÅMMDD) innan journalen öppnas."""
    with db.factory() as s:
        for key, born in births.items():
            person = s.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == PERSONS[key]))
            person.personal_id_number = born + PERSONS[key][-4:]
        s.commit()


def _ready(db, births: dict[str, str]):
    _born(db, births)
    open_ledger(db)
    adopt_avk(db, "AVK-SIM-2026-02", {"2026-11-01": "0.002"}, "2026-11-01")
    return db


def request(db, key, kind, content, received="2026-10-20", **kw):
    data = {"policy_number": POLICY[key], "part_number": kw.pop("part_number", 1), "kind": kind,
            "content": content, "received_date": received, "channel": kw.pop("channel", "customer_portal"), **kw}
    return run(db, "register_payout_request", data).payload


def preview(db, request_id):
    return run(db, "preview_payout_plan", {"request_id": request_id}).payload


def decide(db, request_id, name="decide_payout_plan"):
    review = preview(db, request_id)
    return run(db, name, {"request_id": request_id, "reviewed_checksum": review["review_checksum"],
                          "reason": "Prov enligt kundens begäran"}).payload


def without_step5(db):
    """Som Lakebase före steg 5:s migration: inga tabeller för belopp, anspråk och finansiering (B-052)."""
    with db.engine.begin() as conn:
        for table in ("pension_claim_fundings", "pension_claims", "payout_amounts"):
            conn.exec_driver_sql(f"DROP TABLE {table}")
    return db


def part_id(db, key, number=1):
    with db.factory() as s:
        return pl.find_part(s, POLICY[key], number).part.id


@pytest.fixture
def at_66(chain):
    """B fyller 66 i november 2026 (fall 1); övriga som i steg 3."""
    return _ready(chain, {"B": "19601103"})


@pytest.fixture
def ready(chain):
    return _ready(chain, {})


class TestStandardstart:
    def test_fall_1_verifierad_agare_far_standardplan_och_stangningen_blockeras(self, at_66):
        without_step5(at_66)  # med steg 5:s tabeller bokas standardstarten (test_pension_claims)
        review = prepare(at_66)
        assert not review["passed"]
        assert any("standardstart" in p and "steg 5" in p for p in review["problems"])
        [standard] = review["payout"]["standard_start"]
        assert standard["payout_part_id"] == str(part_id(at_66, "B"))
        assert standard["first_right"] == "2026-11-01" and standard["first_payment_day"] == "2026-12-01"
        assert Decimal(standard["m_sek"]) >= Decimal(standard["guarantee_sek_per_month"]).quantize(Decimal("0.01"))
        assert {c["step"]: c["passed"] for c in review["controls"]}["standardstart"] is False
        with pytest.raises(BlockedError, match="standardstart"):
            close(at_66, checksum=review["review_checksum"])
        assert count(at_66, LedgerBatch) == 1 and count(at_66, PayoutPlan) == 0 and count(at_66, Case,
                                                                                         Case.case_type == "payout_review") == 0

    def test_overifierad_agare_ger_arende_och_sparandet_stangs(self, at_66):
        with at_66.factory() as s:
            s.scalar(select(Employer)).collective_agreement = "SAF-LO"
            s.commit()
        review = prepare(at_66)
        assert review["passed"], review["problems"]
        [case] = review["payout"]["review_cases"]
        assert case["reason"] == "standard_start_unverified" and "avtal" in case["detail"]
        assert "person_id" not in case  # sammanställningen bär inga personuppgifter
        close(at_66, checksum=review["review_checksum"])
        with at_66.factory() as s:
            cases = s.scalars(select(Case).where(Case.case_type == "payout_review")).all()
            states = s.scalars(select(PayoutPartState.state).where(PayoutPartState.valid_to.is_(None))).all()
        assert len(cases) == 1 and cases[0].details["reason"] == "standard_start_unverified"
        assert cases[0].channel == "system" and cases[0].status == "open"
        assert set(states) == {"not_started"}  # startmånaden flyttas inte tyst
        assert count(at_66, PayoutPlan) == 0

    def test_66_passerat_utan_plan_ger_ett_arende_per_person_en_gang(self, chain, clock):
        db = _ready(chain, {"C": "19580315"})
        review = prepare(db)
        assert review["passed"]
        assert [c["reason"] for c in review["payout"]["review_cases"]] == ["passed_66_without_plan"]
        close(db, checksum=review["review_checksum"])
        clock.today = date(2027, 1, 4)
        adopt_avk(db, "AVK-SIM-2026-03", {"2026-11-01": "0.002", "2026-12-01": "0.001"}, "2026-12-01",
                  supersedes="AVK-SIM-2026-02")
        december = prepare(db, "2026-12-01")
        assert december["passed"] and december["payout"]["review_cases"] == []
        assert "1 med ärende sedan tidigare" in next(c for c in december["controls"]
                                                     if c["step"] == "standardstart")["detail"]
        close(db, "2026-12-01")
        assert count(db, Case, Case.case_type == "payout_review") == 1


class TestUppskov:
    def test_fall_2_och_12_uppskov_till_72_raknas_om_i_novembers_stangning(self, at_66):
        made = request(at_66, "B", "start", {"first_right": "2032-11-01", "form": "lifelong"})
        assert made["outcome"] == "in_time" and made["change_month"] == "2026-11-01"
        assert made["deadline"] == "2026-10-31"
        review = preview(at_66, made["request_id"])
        assert review["bindable"] and review["valuation_date"] == "2026-10-31"
        assert review["schedule"]["first_right"] == "2032-11-01" and review["next_right"] == "2032-11-01"
        assert review["guarantees"], "B har garantidelar ur S-04"
        for g in review["guarantees"]:
            # Fall 12: V_j = G_j × A_gammal = G_j_ny × A_ny på samma historiska grund; uppskov höjer G_j
            assert Decimal(g["factor_new"]) < Decimal(g["factor_old"]) and Decimal(g["g_new"]) > Decimal(g["g_old"])
            assert abs(Decimal(g["g_new"]) * Decimal(g["factor_new"]) - Decimal(g["value"])) < Decimal("1e-6")
        decided = decide(at_66, made["request_id"])
        assert decided["version"] == 1 and decided["first_right"] == "2032-11-01"
        assert count(at_66, LedgerGuaranteePart, LedgerGuaranteePart.version > 1) == 0  # beslutet bokar inget

        closing = prepare(at_66)
        assert closing["passed"], closing["problems"]
        assert closing["payout"]["planned_parts"] == [str(part_id(at_66, "B"))]
        assert closing["totals"]["guarantee_versions"] == len(review["guarantees"])
        close(at_66, checksum=closing["review_checksum"])
        with at_66.factory() as s:
            batch = cl.effective_batch(s, NOV_END)
            mc.verify_month(s, batch)
            b = pl.find_part(s, POLICY["B"], 1).part.id
            current = [g for g in cl.guarantee_parts(s, NOV_END) if g.payout_part_id == b]
            before = [g for g in cl.guarantee_parts(s, OCT_END) if g.payout_part_id == b]
            assert {g.plan_kind for g in current} == {"plan"} and {g.plan_kind for g in before} == {"reference_lifelong"}
            recalculated = [g for g in current if g.reason == "recalculation"]
            assert {str(g.supersedes_id) for g in recalculated} == {x["id"] for x in review["guarantees"]}
            assert {g.plan_start for g in current} == {date(2032, 11, 1)}
            plan = s.get(PayoutPlan, s.scalar(select(PayoutPlan.id)))
            assert {g.plan_id for g in current} == {plan.id}
            # Inga rättigheter mellan 66 och 72; delen är ej startad och kapitalet förvaltas
            assert not pl.schedule_of(plan).has_right(NOVEMBER)
            assert pl.part_state(s, b, NOVEMBER) == "not_started"
            extract = build_ledger_extract(s, NOV_END)
            assert extract.approved, [c for c in extract.checks if not c.passed]
            assert any(n.reason.startswith("Beslutad uttagsplan") for n in extract.not_calculated)

    def test_v3_plan_med_ratt_i_manaden_blockerar(self, at_66):
        without_step5(at_66)  # med steg 5:s tabeller bokas rätten (test_pension_claims)
        made = request(at_66, "B", "start", {"first_right": "2026-11-01", "form": "lifelong"})
        decide(at_66, made["request_id"])
        review = prepare(at_66)
        assert not review["passed"] and review["payout"]["with_right"] == [str(part_id(at_66, "B"))]
        assert review["payout"]["standard_start"] == []  # delen har en beslutad plan
        with pytest.raises(BlockedError, match="steg 5"):
            close(at_66, checksum=review["review_checksum"])

    def test_beslut_kraver_granskad_summa_och_ett_beslut_per_begaran(self, at_66):
        made = request(at_66, "B", "start", {"first_right": "2032-11-01", "form": "lifelong"})
        with pytest.raises(ConflictError):
            run(at_66, "decide_payout_plan", {"request_id": made["request_id"], "reviewed_checksum": "0" * 64,
                                              "reason": "fel summa"})
        decide(at_66, made["request_id"])
        with pytest.raises(BlockedError, match="redan beslutad"):
            decide(at_66, made["request_id"])

    def test_premie_pa_del_med_plan_far_garanti_pa_planen(self, at_66):
        made = request(at_66, "B", "start", {"first_right": "2032-11-01", "form": "lifelong"})
        decide(at_66, made["request_id"])
        review = prepare(at_66)
        close(at_66, checksum=review["review_checksum"])
        with at_66.factory() as s:
            b = pl.find_part(s, POLICY["B"], 1).part.id
            new = s.scalars(select(LedgerGuaranteePart).where(LedgerGuaranteePart.payout_part_id == b,
                                                              LedgerGuaranteePart.version == 1,
                                                              LedgerGuaranteePart.received_month == NOVEMBER)).all()
            assert new and {(g.plan_kind, g.plan_start) for g in new} == {("plan", date(2032, 11, 1))}


class TestBegaran:
    def test_fall_3_sen_begaran_far_forslag_och_bekraftelse(self, at_66):
        late = request(at_66, "B", "start", {"first_right": "2026-12-01", "form": "lifelong"}, received="2026-12-01")
        assert late["outcome"] == "late" and late["proposed_month"] == "2027-01-01"
        with at_66.factory() as s:
            case = s.get(Case, uuid.UUID(late["case_id"]))
            assert case.case_type == "payout_request" and case.details["outcome"] == "late"
        with pytest.raises(BlockedError, match="late"):
            decide(at_66, late["request_id"])
        confirmed = request(at_66, "B", "start", {"first_right": "2027-01-01", "form": "lifelong"},
                            received="2026-12-01", confirms_request_id=late["request_id"])
        assert confirmed["outcome"] == "in_time" and confirmed["change_month"] == "2027-01-01"
        assert not preview(at_66, confirmed["request_id"])["bindable"]  # december är inte stängd

    def test_fall_4_n_59_avslas_och_n_60_ger_oktober_2031(self, at_66):
        fixed = request(at_66, "B", "start", {"first_right": "2026-11-01", "form": "fixed_term", "payments": 60})
        assert preview(at_66, fixed["request_id"])["schedule"]["end_month"] == "2031-10-01"
        short = request(at_66, "B", "start", {"first_right": "2026-11-01", "form": "fixed_term", "payments": 59})
        with pytest.raises(BlockedError, match="minst 60"):
            preview(at_66, short["request_id"])

    def test_fall_8_uttag_fore_66_blockeras_med_arende(self, ready):
        made = request(ready, "A", "start", {"first_right": "2027-01-01", "form": "lifelong"})
        assert made["outcome"] == "blocked" and any("PB1" in m for m in made["missing"])
        assert count(ready, Case, Case.case_type == "payout_request") == 1

    def test_ofullstandig_stoppad_och_idempotent(self, at_66):
        missing = request(at_66, "B", "start", {"first_right": "2032-11-01", "form": "fixed_term"})
        assert missing["outcome"] == "incomplete" and any("payments" in m for m in missing["missing"])
        assert count(at_66, Case, Case.case_type == "payout_request", Case.status == "waiting_info") == 1
        agent = request(at_66, "B", "start", {"first_right": "2032-11-01", "form": "lifelong"},
                        requester="representative", authority_verified=False)
        assert agent["outcome"] == "stopped" and any("behörighet" in m for m in agent["missing"])
        again = request(at_66, "B", "start", {"first_right": "2032-11-01", "form": "lifelong"},
                        requester="representative", authority_verified=False)
        assert not again["created"] and again["request_id"] == agent["request_id"]
        assert count(at_66, PayoutRequest) == 2 and count(at_66, Case, Case.case_type == "payout_request") == 2

    def test_fall_5_och_6_paus_och_forlangning_vagledande_pa_paborjad_del(self, at_66):
        made = request(at_66, "B", "start", {"first_right": "2026-11-01", "form": "fixed_term", "payments": 60})
        decide(at_66, made["request_id"])
        with at_66.factory() as s:  # delen har startat i november (månadsrätten kommer i steg 5)
            b = pl.find_part(s, POLICY["B"], 1).part.id
            state = s.scalar(select(PayoutPartState).where(PayoutPartState.payout_part_id == b))
            state.valid_to = date(2026, 10, 31)
            s.add(PayoutPartState(payout_part_id=b, state="in_payout", valid_from=NOVEMBER))
            s.commit()
        pause = request(at_66, "B", "pause", {"first": "2027-11-01", "resume": "2028-02-01"})
        review = preview(at_66, pause["request_id"])
        assert not review["bindable"] and review["consumed"] == 12 and review["remaining"] == 48
        assert review["schedule"]["end_month"] == "2032-01-01"
        with pytest.raises(BlockedError, match="Vägledande"):
            decide(at_66, pause["request_id"])
        longer = request(at_66, "B", "extend", {"month": "2027-11-01", "form": "fixed_term", "payments": 120})
        assert preview(at_66, longer["request_id"])["remaining"] == 108
        late = request(at_66, "B", "extend", {"month": "2031-11-01", "form": "fixed_term", "payments": 120})
        with pytest.raises(BlockedError, match="för sent"):
            preview(at_66, late["request_id"])


class TestDelning:
    def test_fall_7_delning_30_70_i_stangningen(self, ready, clock):
        made = request(ready, "A", "split", {"month": "2026-11-01", "share": "0.3", "premium_receiver": 1})
        assert made["outcome"] == "in_time"
        review = preview(ready, made["request_id"])
        capital = Decimal(review["capital_sek"])
        assert Decimal(review["new_capital_sek"]) == (capital * Decimal("0.3")).quantize(Decimal("0.01"))
        assert review["new_part_number"] == 2
        decide(ready, made["request_id"], name="split_payout_part")
        assert count(ready, PayoutPart) == 4  # delen skapas först i stängningen

        closing = prepare(ready)
        assert closing["passed"], closing["problems"]
        close(ready, checksum=closing["review_checksum"])
        with ready.factory() as s:
            mc.verify_month(s, cl.effective_batch(s, NOV_END))
            one, two = (pl.find_part(s, POLICY["A"], n).part for n in (1, 2))
            assert two.split_from_part_id == one.id and two.split_share == Decimal("0.3")
            assert (one.share_of_origin, two.share_of_origin) == (Decimal("0.7"), Decimal("0.3"))
            assert pl.part_state(s, two.id, NOVEMBER) == "not_started"
            moved = sum(e.amount_sek for e in s.scalars(select(cl.LedgerCapitalEntry).where(
                cl.LedgerCapitalEntry.reason == "split", cl.LedgerCapitalEntry.payout_part_id == two.id)))
            assert moved == Decimal(review["new_capital_sek"])
            g_old = sum(g.guarantee_sek_per_month for g in cl.guarantee_parts(s, OCT_END) if g.payout_part_id == one.id)
            now = cl.guarantee_parts(s, NOV_END)
            g_one = sum(g.guarantee_sek_per_month for g in now if g.payout_part_id == one.id and g.reason == "split")
            g_two = sum(g.guarantee_sek_per_month for g in now if g.payout_part_id == two.id)
            assert g_one + g_two == g_old and abs(g_two - g_old * Decimal("0.3")) < Decimal("1e-8")
            tracks = cl.tracks(s, NOV_END)
            assert sum(t.balance for t in tracks if t.payout_part_id == two.id) > 0
            assert all(t.balance >= 0 for t in tracks)
            extract = build_ledger_extract(s, NOV_END)
            assert extract.approved, [c for c in extract.checks if not c.passed]
            # Premiemottagaren ur delningsbeslutet (PR-ITP1-015)
            person = s.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == PERSONS["A"]))
            assert _recipient(s, person, DECEMBER)[2].part_number == 1

    def test_fall_7_fem_procent_och_fjarde_del_avslas(self, ready):
        small = request(ready, "A", "split", {"month": "2026-11-01", "share": "0.05", "premium_receiver": 1})
        with pytest.raises(BlockedError, match="minst 10"):
            preview(ready, small["request_id"])
        with ready.factory() as s:
            first = pl.find_part(s, POLICY["A"], 1).part
            for number in (2, 3):
                part = PayoutPart(benefit_id=first.benefit_id, part_number=number, share_of_origin=Decimal("0.2"),
                                  split_from_part_id=first.id, split_date=NOVEMBER, split_share=Decimal("0.2"))
                s.add(part)
                s.flush()
                s.add(PayoutPartState(payout_part_id=part.id, state="not_started", valid_from=NOVEMBER))
            s.commit()
        fourth = request(ready, "A", "split", {"month": "2026-11-01", "share": "0.3", "premium_receiver": 1})
        with pytest.raises(BlockedError, match="högst 3"):
            preview(ready, fourth["request_id"])


class TestUtanSteg4:
    def test_utan_tabellerna_som_steg_3(self, ready):
        without_step5(ready)
        with ready.engine.begin() as conn:
            for table in ("payout_splits", "payout_plans", "payout_requests"):
                conn.exec_driver_sql(f"DROP TABLE {table}")
        with ready.factory() as s:
            assert not pl.plans_present(s)
        review = prepare(ready)
        assert review["passed"] and "payout" not in review and "guarantee_versions" not in review["totals"]
        # Före migrationen är sammanställningen identisk med steg 3 (B-052): samma kontrollpost och
        # premiernas innehåll utan steg 4:s fält, så att novembers stängning får samma kontrollsumma
        steps = [c["step"] for c in review["controls"]]
        assert "standardstart väntar på steg 4" in steps and "standardstart" not in steps and "rätt enligt plan" not in steps
        assert next(c for c in review["controls"] if c["step"] == "standardstart väntar på steg 4")["passed"]
        with ready.factory() as s:
            intake = premium_intake(s, NOVEMBER)
        assert intake.additions and all({"plan_kind", "plan_id"}.isdisjoint(a.plain()) for a in intake.additions)
        with pytest.raises(BlockedError, match="migrate_payout_plans"):
            request(ready, "A", "split", {"month": "2026-11-01", "share": "0.3", "premium_receiver": 1})
        close(ready, checksum=review["review_checksum"])


class TestBefogenheter:
    @pytest.mark.parametrize("name, data", [
        ("register_payout_request", {"policy_number": "AL-000101", "kind": "start", "content": {},
                                     "received_date": "2026-10-20", "channel": "manual"}),
        ("preview_payout_plan", {"request_id": "0" * 8 + "-0000-0000-0000-" + "0" * 12}),
        ("decide_payout_plan", {"request_id": "0" * 8 + "-0000-0000-0000-" + "0" * 12,
                                "reviewed_checksum": "0" * 64, "reason": "prov"}),
        ("split_payout_part", {"request_id": "0" * 8 + "-0000-0000-0000-" + "0" * 12,
                               "reviewed_checksum": "0" * 64, "reason": "prov"}),
        ("get_payout_part", {"policy_number": "AL-000101"}),
    ])
    def test_agenter_nekas(self, ready, name, data):
        with pytest.raises(AccessDeniedError):
            run(ready, name, data, ctx=AGENT)

    @pytest.mark.parametrize("name", ["register_payout_request", "decide_payout_plan", "split_payout_part"])
    def test_systemaktoren_nekas_skrivningar(self, ready, name):
        data = ({"policy_number": "AL-000101", "kind": "start", "content": {}, "received_date": "2026-10-20",
                 "channel": "system"} if name == "register_payout_request" else
                {"request_id": "0" * 8 + "-0000-0000-0000-" + "0" * 12, "reviewed_checksum": "0" * 64,
                 "reason": "prov"})
        with pytest.raises(AccessDeniedError):
            run(ready, name, data, ctx=SYSTEM)

    def test_get_payout_part_visar_planer_och_begaran(self, at_66):
        made = request(at_66, "B", "start", {"first_right": "2032-11-01", "form": "lifelong"})
        decide(at_66, made["request_id"])
        view = run(at_66, "get_payout_part", {"policy_number": POLICY["B"]}).payload
        assert view["sixty_six_month"] == "2026-11-01" and view["on"] == "2026-10-31"
        assert [p["first_right"] for p in view["plans"]] == ["2032-11-01"]
        assert [r["outcome"] for r in view["requests"]] == ["in_time"]
        assert Decimal(view["capital_sek"]) > 0
