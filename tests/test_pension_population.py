"""Paket B steg 9: nytt startläge med pensionärer (B-057, P1-PENSION-001 §12.1, Karls val Q1–Q10).

Hela kedjan provas på paket A:s testbestånd, i den ordning som ska gälla i Lakebase (Q5):

1. journalens första ingående läge (som i Lakebase sedan 2026-11-15);
2. det nya beståndet (`simulation.pension_population`): kohorten och fyra pensionärer med fribrev och en
   syntetisk startpremie var;
3. ersättningen av det ingående läget (`services.ledger_reopening`);
4. Karin Sjöbergs delning i november, novembers AVK och stängning;
5. pensionärernas begäran om start i december och besluten efter novembers stängning;
6. bolagsinsättningen (24 gånger decembers månadsbelopp, Q6), skattestatus och konto;
7. decembers AVK och stängning, bankfilen och bankens kvitton.

Kontrollerna enligt Q10:
- de befintliga försäkringarna har exakt samma C och G;
- de nya stämmer mot listan: C är startpremien, och G är positiv;
- novembers stängning går igenom och ger ett ärende `payout_review` per person som passerat 66 utan plan;
- decembers utbetalning stämmer mot ett facit som räknas här, utanför koden. Skatten är satsen gånger
  bruttot per person i hela kronor nedåt, och nettot är bruttot minus skatten.

Samma kedja körs mot en isolerad Postgres (`svc_test`) när den finns.
"""

from __future__ import annotations

import importlib.util
import json
import runpy
import sys
import uuid
from datetime import date
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from models import (
    Case,
    InsuredPerson,
    LedgerBatch,
    PayoutPart,
    PayoutPlan,
    Policy,
    PolicyBenefit,
    PremiumTransaction,
)
from services import capital_ledger as cl
from services import ledger_reopening as lr
from services import payout_orders as po
from services import pension_claims as pc
from simulation import pension_population as pop
from simulation.counterparties import payout_receipt_file
from tests import test_premium_month_export as export_tests
from tests.test_pension_claims import (
    DECEMBER,
    JANUARY,
    NOVEMBER,
    adopt_avk,
    close_month,
    decide,
    months_ahead,
    open_ledger,
)
from tests.test_premium_month_export import run
from tests.test_services_postgres import TEST_URL, isolated_schema

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

chain = export_tests.chain
clock = export_tests.clock

ACTOR = "karl"
KARIN = next(m for m in pop.PENSIONERS if m.split_share is not None)


def add(db) -> dict:
    with db.factory() as s:
        review = pop.plan_population(s).summary()
    with db.factory() as s, s.begin():
        summary, new = pop.add_population(s, review["review_checksum"])
    assert new
    return summary


def reopen(db) -> dict:
    with db.factory() as s:
        review = lr.plan_reopening(s).summary()
    assert review["passed"], review["problems"]
    with db.factory() as s, s.begin():
        summary, new = lr.apply_reopening(s, ACTOR, review["review_checksum"])
    assert new
    return summary


def policy_number(db, member) -> str:
    with db.factory() as s:
        return s.scalar(select(Policy.policy_number).join(InsuredPerson)
                        .where(InsuredPerson.personal_id_number == member.personal_id_number))


def cases(db, case_type) -> int:
    with db.factory() as s:
        return s.scalar(select(func.count()).select_from(Case).where(Case.case_type == case_type))


def run_chain(db, clock) -> dict:
    """Kedjan från det nya startläget till decembers utbetalning. Svarar med facit och utfall."""
    split = run(db, "register_payout_request", pop.split_request(KARIN, policy_number(db, KARIN))).payload
    review = run(db, "preview_payout_plan", {"request_id": split["request_id"]}).payload
    run(db, "split_payout_part", {"request_id": split["request_id"], "reviewed_checksum": review["review_checksum"],
                                  "reason": "Kundens begäran om delning"})

    adopt_avk(db, "AVK-SIM-2026-02", {"2026-11-01": "0.002"}, "2026-11-01")
    november = close_month(db, clock, NOVEMBER)
    review_cases = cases(db, "payout_review")

    for member in pop.PENSIONERS:
        for data in pop.start_requests(member, policy_number(db, member)):
            made = run(db, "register_payout_request", data).payload
            assert made["outcome"] == "in_time", made
            decide(db, made["request_id"])
    with db.factory() as s:
        m_total = sum((p.m_sek for p in s.scalars(select(PayoutPlan))), Decimal(0))
    deposit = pop.capital_deposit(m_total)
    run(db, "register_company_capital", {"amount_sek": str(deposit), "decided_on": pop.CAPITAL_DECIDED.isoformat(),
                                         "document_ref": pop.CAPITAL_REF})
    for member in pop.PENSIONERS:
        run(db, "register_tax_status", pop.tax_status(member))
        run(db, "register_payout_account", pop.payout_account(member))

    months_ahead(db, clock, DECEMBER)
    december = close_month(db, clock, DECEMBER)
    with db.factory() as s:
        claims = po.claims_payment_view(s, DECEMBER)
        person_of = dict(s.execute(
            select(PayoutPart.id, InsuredPerson.personal_id_number)
            .join(PolicyBenefit, PolicyBenefit.id == PayoutPart.benefit_id)
            .join(Policy, Policy.id == PolicyBenefit.policy_id)
            .join(InsuredPerson, InsuredPerson.id == Policy.insured_person_id)).all())

    day = claims[0]["payment_day"]
    created = run(db, "create_payout_orders", {"payment_day": day}).payload
    approved = run(db, "approve_payout_order", {"file_id": created["file"]["file_id"],
                                                "reviewed_checksum": created["file"]["checksum"]}).payload
    sim = payout_receipt_file(approved["bank_file"], None, bank_date=date.fromisoformat(day), seed=7, round_number=1)
    run(db, "import_payout_receipts", sim.payload)

    # Facit utanför koden: brutto per person, skatten i hela kronor nedåt, netto = brutto − skatt
    gross = {}
    for c in claims:
        pnr = person_of[uuid.UUID(c["payout_part_id"])]
        gross[pnr] = gross.get(pnr, Decimal(0)) + Decimal(c["gross_sek"])
    rate = {m.personal_id_number: m.tax_rate or Decimal("0.30") for m in pop.PENSIONERS}
    tax = {p: (g * rate[p]).quantize(Decimal(1), rounding=ROUND_FLOOR) for p, g in gross.items()}
    pnr_of_account = {pop.account_number(m): m.personal_id_number for m in pop.PENSIONERS}
    paid = {pnr_of_account[o["account_number"]]: Decimal(o["amount_sek"]) for o in approved["bank_file"]["orders"]}
    with db.factory() as s:
        balances = {"liability": pc.account_balance(s, pc.LIABILITY, JANUARY),
                    "tax_liability": pc.account_balance(s, po.TAX_LIABILITY, JANUARY),
                    "states": {c["state"] for c in po.claims_payment_view(s, DECEMBER)}}
    return {"november": november, "december": december, "review_cases": review_cases, "claims": claims,
            "m_total": m_total, "deposit": deposit, "blocked": created["summary"]["blocked"],
            "gross": gross, "tax": tax, "net": {p: g - tax[p] for p, g in gross.items()}, "paid": paid, **balances}


def check_chain(out: dict) -> None:
    assert out["november"]["passed"] and out["december"]["passed"]
    assert out["review_cases"] == 11  # de som passerat 66 utan plan, ett ärende var (V6)
    assert len(out["claims"]) == 5  # fyra personer, Karin med två delar
    assert sum((Decimal(c["gross_sek"]) for c in out["claims"]), Decimal(0)) == out["m_total"]
    assert out["deposit"] >= 24 * out["m_total"] and out["deposit"] % 10_000 == 0
    assert out["blocked"] == []
    assert out["paid"] == out["net"] and len(out["paid"]) == 4
    # Utbetalningen bokas i januari, när banken har betalat ut
    assert out["liability"] == Decimal("0.00")
    assert out["tax_liability"] == sum(out["tax"].values(), Decimal(0))
    assert out["states"] == {"paid"}


@pytest.fixture
def opened(chain):
    """Paket A:s testbestånd med journalens första ingående läge, som Lakebase sedan 2026-11-15."""
    open_ledger(chain)
    return chain


@pytest.fixture
def reopened(opened):
    add(opened)
    reopen(opened)
    return opened


class TestBestandet:
    def test_definitionen(self):
        assert len(pop.MEMBERS) == 35 and len(pop.PENSIONERS) == 4
        assert len({m.personal_id_number for m in pop.MEMBERS}) == 35
        assert sum(m.sixty_six_month <= date(2026, 10, 1) for m in pop.MEMBERS) == 11  # 7 i kohorten + 4
        for m in pop.MEMBERS:
            assert pop.FIRST_PREMIUM_MONTH <= m.premium_month < m.sixty_six_month
            assert m.premium_month <= pop.LAST_PREMIUM_MONTH
            assert Decimal(300_000) <= m.premium_sek <= Decimal(1_500_000)
        assert pop.capital_deposit(Decimal("12345.67")) == Decimal("300000.00")  # 24 × = 296 296,08

    def test_tillagget_ar_idempotent(self, opened):
        summary = add(opened)
        assert summary["members"] == 35 and summary["passed_66_by_2026_10"] == 11
        with opened.factory() as s:
            again = pop.plan_population(s)
            assert again.already_added
            assert pop.add_population(s, again.checksum) == (again.summary(), False)
            rows = s.scalars(select(PremiumTransaction).where(PremiumTransaction.paid_date == pop.PREMIUM_PAID,
                                                               PremiumTransaction.calculation_basis.is_not(None)))
            assert sum(r.calculation_basis.get("source") == pop.SOURCE for r in rows) == 35

    def test_krock_med_befintligt_personnummer(self, opened):
        with opened.factory() as s:
            person = s.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == "198505151234"))
            person.personal_id_number = pop.MEMBERS[0].personal_id_number
            s.commit()
        with opened.factory() as s:
            plan = pop.plan_population(s)
            assert plan.collisions == [pop.MEMBERS[0].personal_id_number] and not plan.passed
            with pytest.raises(pop.PopulationError):
                pop.add_population(s, plan.checksum)


class TestNyttStartlage:
    def test_befintliga_oforandrade_och_35_nya(self, opened):
        with opened.factory() as s:
            before = lr.booked_by_policy(s, cl.opening_batch(s))
        add(opened)
        summary = reopen(opened)
        assert summary["changed"] == [] and summary["removed"] == []
        assert len(summary["added"]) == 35 and summary["unchanged_policies"] == len(before)
        assert summary["replaced_content"]["totals"]["policies"] == len(before)
        with opened.factory() as s:
            after = lr.booked_by_policy(s, cl.opening_batch(s))
            assert {p: after[p] for p in before} == before
            premium = dict(s.execute(
                select(PolicyBenefit.policy_id, PremiumTransaction.amount_sek)
                .join(PremiumTransaction, PremiumTransaction.benefit_id == PolicyBenefit.id)
                .where(PremiumTransaction.paid_date == pop.PREMIUM_PAID)).all())
            new = {p: v for p, v in after.items() if p not in before}
            assert len(new) == 35
            assert all(c == Decimal(premium[uuid.UUID(p)]) and g > 0 for p, (c, g) in new.items())
            assert s.scalar(select(func.count()).select_from(LedgerBatch)) == 1

    def test_ersattningen_ar_idempotent(self, reopened):
        with reopened.factory() as s:
            batch = cl.opening_batch(s)
            plan = lr.plan_reopening(s)
            assert not plan.passed and any("detsamma som det bokade" in p for p in plan.problems)
            assert lr.apply_reopening(s, ACTOR, "fel")[1] is False  # redan ersatt: ingen ny effekt
            assert cl.opening_batch(s).id == batch.id

    def test_ersattningen_stoppas_efter_en_stangning(self, reopened, clock):
        adopt_avk(reopened, "AVK-SIM-2026-02", {"2026-11-01": "0.002"}, "2026-11-01")
        close_month(reopened, clock, NOVEMBER)
        with reopened.factory() as s:
            plan = lr.plan_reopening(s)
            assert any("verifikationer utöver" in p for p in plan.problems)


class TestKedjan:
    def test_november_december_och_forsta_utbetalningen(self, reopened, clock):
        check_chain(run_chain(reopened, clock))


@pytest.fixture
def chain_on_postgres(monkeypatch):
    """Paket A:s testbestånd i ett isolerat Postgres-schema i stället för SQLite."""
    if not TEST_URL:
        pytest.skip("SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")
    with isolated_schema() as schema:
        monkeypatch.setattr(export_tests, "create_engine", lambda *args, **kwargs: schema.engine)
        yield schema


def test_kedjan_mot_postgres(chain_on_postgres, chain, clock):
    open_ledger(chain)
    add(chain)
    summary = reopen(chain)
    assert summary["changed"] == [] and len(summary["added"]) == 35
    check_chain(run_chain(chain, clock))


# --- Körskripten (scripts/simulation/paket_b_steg9) -----------------------------------------------

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "simulation" / "paket_b_steg9"


@pytest.fixture
def scripts(opened, tmp_path, monkeypatch):
    """Kör körskripten i processen mot provets databas, med loggarna i tmp_path och provets klocka."""
    spec = importlib.util.spec_from_file_location("common", SCRIPTS / "common.py")
    common = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "common", common)
    spec.loader.exec_module(common)
    monkeypatch.setattr(common, "OUT", tmp_path)
    monkeypatch.setenv("DATABASE_URL", str(opened.engine.url))
    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "manifest.json").write_text("{}", encoding="utf-8")

    def script(name: str, *argv: str, apply: bool = False) -> dict:
        """Granskar och, med apply, kör skarpt med granskningens summa. Svarar med granskningen."""
        log = {"pensioners.py": f"pensioners_{argv[1]}" if argv else "", "adopt_avk_december.py": "adopt_avk_december"}
        stem = log.get(name) or name.removesuffix(".py")
        run_script(name, *argv)
        preview = json.loads((tmp_path / f"{stem}_preview_sqlite.json").read_text(encoding="utf-8"))
        if apply:
            run_script(name, *argv, "--apply", "--backup", str(backup), "--reviewed-checksum",
                       preview.get("review_checksum") or preview.get("content_checksum"))
        return preview

    def run_script(name: str, *argv: str) -> None:
        monkeypatch.setattr(sys, "argv", [name, *argv])
        try:
            runpy.run_path(str(SCRIPTS / name), run_name="__main__")
        except SystemExit as stop:
            assert stop.code in (0, None), stop.code

    script.run = run_script
    return script


class TestKorskripten:
    def test_hela_ordningen_med_skripten(self, scripts, opened, clock, tmp_path):
        assert scripts("add_population.py", apply=True)["members"] == 35
        assert scripts("reopen_ledger.py", apply=True)["changed"] == []
        scripts("pensioners.py", "--phase", "split", apply=True)
        adopt_avk(opened, "AVK-SIM-2026-02", {"2026-11-01": "0.002"}, "2026-11-01")
        close_month(opened, clock, NOVEMBER)
        clock.today = pop.INPUTS_RECEIVED
        scripts("pensioners.py", "--phase", "start", apply=True)
        again = scripts("pensioners.py", "--phase", "start", apply=True)  # samma igen: redan beslutade
        assert all(again["state"]["decided"].values()) and len(again["state"]["decided"]) == 5
        scripts("pensioners.py", "--phase", "inputs", apply=True)
        capital = scripts("pensioners.py", "--phase", "capital", apply=True)
        assert Decimal(capital["capital"]["amount_sek"]) == pop.capital_deposit(Decimal(capital["december_m_total_sek"]))
        clock.today = date(2027, 1, 2)
        scripts("adopt_avk_december.py", apply=True)
        close_month(opened, clock, DECEMBER)
        scripts.run("verify.py", "--replaced", str(tmp_path / "reopen_ledger_sqlite.json"))
        checks = json.loads((tmp_path / "verify_sqlite.json").read_text(encoding="utf-8"))["checks"]
        assert [c["passed"] for c in checks] == [True, True, True, True, True, True, True, None], checks
