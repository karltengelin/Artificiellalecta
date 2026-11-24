"""Skattestatus, konto, bankuppdrag och kvitton (paket B steg 6, P1-PENSION-001 §8.3, Karls val X1–X13).

Samma bestånd och kedja som i steg 5 (`test_pension_claims`): B fyller 66 i november 2026 och har en beslutad
livsvarig plan från november. I provet sätts M till 10 000 kr (som i steg 5:s prov av bolagsstödet), så att
skatten syns; bolagskontot finansierar det kundkapitalet inte räcker till. Novembers stängning bokar
anspråket med betalningsdag 2026-12-01; stängningen görs 2026-12-04, så utförandedagen blir 2026-12-04.

- **Fall 21:** saknat konto, overifierat konto, saknad skattestatus och huvudinkomst utan tabell blockerar
  med ärende; skulden står kvar.
- **Fall 22:** bankfil, godkännande, utfört kvitto och verifikationen `payout_settlement`: skulden minskar
  med bruttot och skatteskulden ökar med skatten. Samma kvitto igen ger ingen effekt.
- **Fall 23:** avvisad betalning – ärende, nytt verifierat konto, nytt försök med samma anspråk.
- **Fall 24:** återkommen betalning – exakta motposter och skulden öppen igen.
- **Fall 25:** okänt utfall väntar på bankens senare kvitto; inget nytt försök under tiden.
- **Fall 34:** en förberedd fil ersätts när underlaget ändrats, och godkännandet binder kontrollsumman.
- **X10:** decembers stängning räknar in utbetalningen och har kontrollen *utbetalningar*; utan steg 6:s
  tabeller beter sig stängningen som i steg 5 (B-052).

Den rena skatteberäkningen (fall 18–20) provas i test_payout_tax.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from models import (
    Case,
    LedgerBatch,
    PayoutFile,
    PayoutOrderLine,
    PayoutPlan,
    PayoutReceipt,
)
from services import BlockedError, ConflictError
from services import capital_ledger as cl
from services import month_close as mc
from services import payout_orders as po
from services import pension_claims as pc
from services.errors import AccessDeniedError
from simulation.counterparties import payout_receipt_file
from tests import test_premium_month_export as export_tests
from tests.test_pension_claims import (
    AGENT,
    DECEMBER,
    NOVEMBER,
    SYSTEM,
    _ready,
    capital,
    close_month,
    decide,
    months_ahead,
    part_id,
    prepare,
    request,
    steps,
)
from tests.test_premium_month_export import run

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

chain = export_tests.chain
clock = export_tests.clock

B_PNR = "196011031234"
M = Decimal("10000.00")
TAX = Decimal("3000.00")  # 30 % sidoinkomst, hela kronor
PAYMENT_DAY = "2026-12-01"


def tax(db, kind="side_income", received="2026-11-20", **kw):
    return run(db, "register_tax_status", {"personal_id_number": B_PNR, "tax_year": 2026, "kind": kind,
                                           "received_date": received, "channel": "customer_portal", **kw}).payload


def account(db, number="12345678", verified=True, **kw):
    data = {"personal_id_number": B_PNR, "clearing_number": "8327", "account_number": number,
            "bank_name": "Provbanken", "verified": verified, "received_date": "2026-11-20",
            "channel": "customer_portal", **kw}
    if verified:
        data = {"verification_method": "kontouppslag", "verification_ref": f"VER-{number}", **data}
    return run(db, "register_payout_account", data).payload


def create(db, day=PAYMENT_DAY):
    return run(db, "create_payout_orders", {"payment_day": day}).payload


def approve(db, created):
    return run(db, "approve_payout_order", {"file_id": created["file"]["file_id"],
                                            "reviewed_checksum": created["file"]["checksum"]}).payload


def receipts(db, approved, outcomes=None, *, bank_date="2026-12-04", round_number=1):
    sim = payout_receipt_file(approved["bank_file"], outcomes, bank_date=date.fromisoformat(bank_date), seed=7,
                              round_number=round_number)
    return run(db, "import_payout_receipts", sim.payload).payload


def liability(db, month=DECEMBER) -> Decimal:
    with db.factory() as s:
        return pc.account_balance(s, pc.LIABILITY, month)


def tax_liability(db, month=DECEMBER) -> Decimal:
    with db.factory() as s:
        return pc.account_balance(s, po.TAX_LIABILITY, month)


def cases(db, case_type):
    with db.factory() as s:
        return [(c.status, c.details.get("reason")) for c in
                s.scalars(select(Case).where(Case.case_type == case_type).order_by(Case.case_number))]


def claim_state(db) -> str:
    with db.factory() as s:
        [row] = po.claims_payment_view(s, NOVEMBER)
        return row["state"]


@pytest.fixture
def claimed(chain, clock):
    """B:s novemberrätt på 10 000 kr är bokad och helt finansierad; i dag är 2026-12-04."""
    db = _ready(chain, {"B": "19601103"})
    capital(db, "50000.00")
    made = request(db, "B", "start", {"first_right": "2026-11-01", "form": "lifelong"})
    decide(db, made["request_id"])
    with db.factory() as s:  # provet: M = 10 000 kr så att skatten syns; bolagskontot bär resten
        plan = s.scalar(select(PayoutPlan))
        plan.content = {**plan.content, "amount": {**plan.content["amount"], "m_sek": str(M)}}
        plan.m_sek = M
        s.commit()
    close_month(db, clock, NOVEMBER)
    assert clock.today == date(2026, 12, 4)
    return db


@pytest.fixture
def ready(claimed):
    tax(claimed)
    account(claimed)
    return claimed


class TestBlockering:
    def test_fall_21_konto_och_skattestatus_saknas(self, claimed):
        made = create(claimed)
        assert made["file"] is None and made["summary"]["orders"] == 0
        [blocked] = made["summary"]["blocked"]
        assert blocked["reason"] == "account_missing"
        assert cases(claimed, "payout_hindrance") == [("open", "account_missing")]
        assert create(claimed)["summary"]["cases_opened"] == []  # samma hinder: inget nytt ärende

        account(claimed, verified=False)
        assert create(claimed)["summary"]["blocked"][0]["reason"] == "account_unverified"
        account(claimed)  # verifierat: hindret stängs
        assert cases(claimed, "payout_hindrance") == [("closed", "account_missing")]

        made = create(claimed)
        assert made["summary"]["blocked"][0] == {**made["summary"]["blocked"][0], "reason": "tax_status_missing",
                                                 "tax_year": 2026}
        assert cases(claimed, "tax_status") == [("open", "missing")]
        create(claimed)
        assert cases(claimed, "tax_status") == [("open", "missing")]  # en gång per person och år
        assert liability(claimed, NOVEMBER) == M and claim_state(claimed) == "funded"  # skulden står kvar

        tax(claimed)
        assert cases(claimed, "tax_status") == [("closed", "missing")]
        assert create(claimed)["file"]["status"] == "prepared"

    def test_x4_huvudinkomst_utan_tabell_blockerar(self, claimed):
        account(claimed)
        with pytest.raises(BlockedError, match="kolumnen"):
            tax(claimed, "main_income", table_number=33, table_column=2)  # född 1960: kolumn 6
        tax(claimed, "main_income", table_number=33, table_column=6)
        made = create(claimed)
        assert made["file"] is None and made["summary"]["blocked"][0]["reason"] == "tax_table_missing"
        assert cases(claimed, "tax_status") == [("open", "table_missing")]

    def test_avliden_stoppas(self, ready):
        from models import InsuredPerson
        with ready.factory() as s:
            s.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == B_PNR)).status = "deceased"
            s.commit()
        made = create(ready)
        assert made["file"] is None and made["summary"]["blocked"][0]["reason"] == "deceased"
        assert cases(ready, "payout_hindrance") == []


class TestSkattestatus:
    def test_sidoinkomst_minst_30_procent_i_hela_procent(self, claimed):
        with pytest.raises(BlockedError, match="30 %"):
            tax(claimed, rate="0.25")
        with pytest.raises(BlockedError, match="hela procent"):
            tax(claimed, rate="0.305")
        first = tax(claimed)
        assert first["rate"] == "0.30" and first["valid_from"] == "2026-01-01" and first["version"] == 1
        again = tax(claimed)
        assert not again["created"] and again["tax_status_id"] == first["tax_status_id"]
        higher = tax(claimed, rate="0.40", received="2026-11-25")
        assert higher["version"] == 2 and higher["valid_from"] == "2026-12-09"  # från mottagandet + 14 dagar

    def test_sink_och_beslut_kraver_beslutsreferens(self, claimed):
        with pytest.raises(BlockedError, match="SINK"):
            tax(claimed, "sink", rate="0.25")
        with pytest.raises(BlockedError, match="beslutsreferens"):
            tax(claimed, "individual_decision", rate="0.20")
        assert tax(claimed, "sink", rate="0.25", decision_ref="SKV-SINK-1")["kind"] == "sink"

    def test_frivilligt_hogre_avdrag_galler_forst_efter_14_dagar(self, ready):
        tax(ready, rate="0.40", received="2026-11-25")  # gäller från 2026-12-09, efter utförandedagen
        [order] = create(ready)["file"]["orders"]
        assert Decimal(order["tax_sek"]) == TAX


class TestKonto:
    def test_verifierat_konto_kraver_satt_och_referens_och_visas_maskerat(self, claimed):
        with pytest.raises(BlockedError, match="verifieringssätt"):
            run(claimed, "register_payout_account", {
                "personal_id_number": B_PNR, "clearing_number": "8327", "account_number": "12345678",
                "bank_name": "Provbanken", "verified": True, "received_date": "2026-11-20",
                "channel": "customer_portal"})
        view = account(claimed)
        assert view["account_number"] == "****5678" and view["verified"] and view["version"] == 1
        assert not account(claimed)["created"]


class TestBankfil:
    def test_fall_22_fil_godkannande_kvitto_och_verifikation(self, ready):
        made = create(ready)
        assert made["created"]
        file = made["file"]
        assert (file["status"], file["payment_day"], file["execution_date"]) == ("prepared", PAYMENT_DAY, "2026-12-04")
        assert made["summary"]["delayed"] is True
        [order] = file["orders"]
        assert (Decimal(order["gross_sek"]), Decimal(order["tax_sek"]), Decimal(order["net_sek"])) == (
            M, TAX, M - TAX)
        assert order["tax_method"] == "percent" and order["account"]["account_number"] == "****5678"
        [line] = order["lines"]
        assert line["attempt"] == 1 and line["lump_sum"] is False
        assert claim_state(ready) == "bank_prepared"

        again = create(ready)  # samma underlag: samma fil
        assert not again["created"] and again["file"]["file_id"] == file["file_id"]

        with pytest.raises(ConflictError, match="Kontrollsumman"):
            run(ready, "approve_payout_order", {"file_id": file["file_id"], "reviewed_checksum": "0" * 64})
        approved = approve(ready, made)
        assert approved["created"]
        [to_bank] = approved["bank_file"]["orders"]
        assert to_bank["account_number"] == "12345678" and Decimal(to_bank["amount_sek"]) == M - TAX
        assert not approve(ready, made)["created"]  # samma godkännande igen
        assert claim_state(ready) == "sent"
        assert create(ready)["file"] is None  # skickat: inget nytt försök

        result = receipts(ready, approved)
        assert result["new"] == 1 and result["settlement"]["month"] == "2026-12-01"
        assert Decimal(result["settlement"]["paid_gross_sek"]) == M
        assert Decimal(result["settlement"]["withholding_sek"]) == TAX
        assert liability(ready) == 0 and tax_liability(ready) == TAX
        assert claim_state(ready) == "paid"

        repeat = receipts(ready, approved)  # samma kvitto igen: ingen effekt
        assert repeat["new"] == 0 and repeat["already_received"] == 1 and repeat["settlement"] is None
        with ready.factory() as s:
            assert len(s.scalars(select(LedgerBatch).where(LedgerBatch.kind == po.SETTLEMENT_KIND)).all()) == 1
        with pytest.raises(ConflictError, match="annat innehåll"):
            receipts(ready, approved, {approved["bank_file"]["orders"][0]["reference"]: "rejected"})
        assert create(ready)["file"] is None  # betalt

    def test_fall_23_avvisning_kraver_nytt_verifierat_konto(self, ready):
        approved = approve(ready, create(ready))
        reference = approved["bank_file"]["orders"][0]["reference"]
        result = receipts(ready, approved, {reference: "rejected"})
        assert result["settlement"] is None and result["cases_opened"]
        assert liability(ready) == M and claim_state(ready) == "rejected"
        assert cases(ready, "payout_hindrance") == [("open", "bank_rejected")]

        blocked = create(ready)
        assert blocked["file"] is None
        assert blocked["summary"]["blocked"][0]["reason"] == "account_after_rejection"
        assert cases(ready, "payout_hindrance") == [("open", "bank_rejected")]  # samma öppna hinder

        account(ready, number="87654321")
        assert cases(ready, "payout_hindrance") == [("closed", "bank_rejected")]
        retry = create(ready)
        [line] = retry["file"]["orders"][0]["lines"]
        assert line["attempt"] == 2 and retry["file"]["orders"][0]["account"]["account_number"] == "****4321"
        second = approve(ready, retry)
        receipts(ready, second, round_number=2)
        assert liability(ready) == 0 and claim_state(ready) == "paid"
        with ready.factory() as s:
            claims = {line.claim_id for line in s.scalars(select(PayoutOrderLine))}
            assert len(claims) == 1  # samma anspråk, två försök

    def test_fall_24_retur_ger_exakta_motposter(self, ready, clock):
        approved = approve(ready, create(ready))
        reference = approved["bank_file"]["orders"][0]["reference"]
        receipts(ready, approved)
        assert liability(ready) == 0 and tax_liability(ready) == TAX
        clock.today = date(2026, 12, 8)
        returned = receipts(ready, approved, {reference: "returned"}, bank_date="2026-12-08", round_number=2)
        assert Decimal(returned["settlement"]["returned_gross_sek"]) == M
        assert liability(ready) == M and tax_liability(ready) == 0
        assert claim_state(ready) == "returned"
        assert cases(ready, "payout_hindrance") == [("open", "bank_returned")]
        assert create(ready)["summary"]["blocked"][0]["reason"] == "account_after_rejection"
        with pytest.raises(ConflictError, match="kan inte gå"):  # retur av retur
            receipts(ready, approved, {reference: "returned"}, bank_date="2026-12-08", round_number=3)

    def test_fall_25_okant_vantar_pa_senare_kvitto(self, ready):
        approved = approve(ready, create(ready))
        reference = approved["bank_file"]["orders"][0]["reference"]
        unknown = receipts(ready, approved, {reference: "unknown"})
        assert unknown["settlement"] is None and claim_state(ready) == "unknown"
        assert create(ready)["file"] is None  # inget nytt försök medan utfallet är okänt
        receipts(ready, approved, round_number=2)
        assert claim_state(ready) == "paid" and liability(ready) == 0
        with ready.factory() as s:
            assert [r.sequence for r in s.scalars(select(PayoutReceipt).order_by(PayoutReceipt.sequence))] == [1, 2]

    def test_fall_34_forberedd_fil_ersatts_nar_underlaget_andrats(self, ready):
        first = create(ready)
        tax(ready, rate="0.35", received="2026-11-01")  # gäller från 2026-11-15, före utförandedagen
        second = create(ready)
        assert second["created"] and second["file"]["file_id"] != first["file"]["file_id"]
        assert Decimal(second["file"]["orders"][0]["tax_sek"]) == Decimal("3500.00")
        assert second["file"]["orders"][0]["lines"][0]["attempt"] == 2
        with pytest.raises(ConflictError, match="ersatt"):
            approve(ready, first)
        with ready.factory() as s:
            statuses = {f.id.hex: f.status for f in s.scalars(select(PayoutFile))}
        assert sorted(statuses.values()) == ["prepared", "superseded"]

    def test_godkannandet_ger_konflikt_nar_kontot_andrats(self, ready):
        made = create(ready)
        account(ready, number="99990000")
        with pytest.raises(ConflictError, match="Underlaget har ändrats"):
            approve(ready, made)

    def test_godkannandet_ger_konflikt_nar_utforandedagen_flyttats(self, ready, clock):
        made = create(ready)
        clock.today = date(2026, 12, 7)
        with pytest.raises(ConflictError, match="utförandedag"):
            approve(ready, made)

    def test_arsgransen_under_1000_kr(self, claimed):
        with claimed.factory() as s:  # provet: anspråket på 500 kr, ingen mer rätt i året
            from models import PensionClaim
            claim = s.scalar(select(PensionClaim))
            claim.gross_sek, claim.from_capital_sek, claim.company_support_sek = (
                Decimal("500.00"), Decimal("500.00"), Decimal("0.00"))
            s.commit()
        tax(claimed)
        account(claimed)
        [order] = create(claimed)["file"]["orders"]
        assert order["tax_method"] == "below_1000" and order["tax_sek"] == "0.00"
        assert order["expected_year_total_sek"] == "500.00"


class TestStangning:
    def test_x10_december_raknar_in_utbetalningen(self, ready, clock):
        receipts(ready, approve(ready, create(ready)))
        months_ahead(ready, clock, DECEMBER)
        december = close_month(ready, clock, DECEMBER)
        passed = steps(december)
        assert passed["utbetalningar"] and passed["skuld och bolagskonto"]
        settled = december["pension"]["settlements"]
        assert settled["batches"] == 1 and Decimal(settled["liability_sek"]) == -M
        assert Decimal(settled["tax_liability_sek"]) == TAX
        section = december["pension"]["liability"]
        assert Decimal(section["opening_sek"]) == M and Decimal(section["settled_sek"]) == -M
        assert Decimal(section["closing_sek"]) == M  # decembers rätt
        assert liability(ready, DECEMBER) == M
        with ready.factory() as s:
            mc.verify_month(s, cl.effective_batch(s, date(2026, 12, 31)))

    def test_b052_utan_steg_6_som_steg_5(self, claimed, clock):
        with claimed.engine.begin() as conn:
            for table in po.ORDER_TABLES[::-1]:
                conn.exec_driver_sql(f"DROP TABLE {table}")
        with claimed.factory() as s:
            assert not po.orders_present(s)
        months_ahead(claimed, clock, DECEMBER)
        clock.today = date(2027, 1, 4)
        review = prepare(claimed, "2026-12-01")
        assert review["passed"], review["problems"]
        assert "utbetalningar" not in steps(review)
        assert "settlements" not in review["pension"] and "settled_sek" not in review["pension"]["liability"]
        with pytest.raises(BlockedError, match="migrate_payout_orders"):
            create(claimed)


WRITES = [
    ("register_tax_status", {"personal_id_number": B_PNR, "tax_year": 2026, "kind": "side_income",
                             "received_date": "2026-11-20", "channel": "manual"}),
    ("register_payout_account", {"personal_id_number": B_PNR, "clearing_number": "8327",
                                 "account_number": "1", "bank_name": "Provbanken", "verified": False,
                                 "received_date": "2026-11-20", "channel": "manual"}),
    ("create_payout_orders", {"payment_day": PAYMENT_DAY}),
    ("approve_payout_order", {"file_id": "0" * 36, "reviewed_checksum": "0" * 64}),
    ("import_payout_receipts", {"file_reference": "X", "checksum": "0" * 64,
                                "receipts": [{"receipt_id": "R1", "reference": "P", "outcome": "executed",
                                              "bank_date": "2026-12-04"}]}),
]


class TestAtkomst:
    @pytest.mark.parametrize("name, data", [*WRITES, ("list_payout_orders", {})])
    def test_agenter_nekas(self, claimed, name, data):
        with pytest.raises(AccessDeniedError):
            run(claimed, name, data, ctx=AGENT)

    @pytest.mark.parametrize("name, data", WRITES)
    def test_systemaktoren_nekas_skrivning(self, claimed, name, data):
        with pytest.raises(AccessDeniedError):
            run(claimed, name, data, ctx=SYSTEM)

    def test_listan_visar_maskerade_konton_och_betalningslage(self, ready):
        approve(ready, create(ready))
        listed = run(ready, "list_payout_orders", {}).payload
        assert listed["count"] == 1 and listed["files"][0]["status"] == "approved"
        assert listed["files"][0]["orders"][0]["account"]["account_number"] == "****5678"
        [claim] = listed["claims"]
        assert claim["state"] == "sent" and claim["attempts"][0]["attempt"] == 1
        assert claim["payout_part_id"] == str(part_id(ready, "B"))
