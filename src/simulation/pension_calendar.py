"""Paket C:s syntetiska pension, dödsfallsavisering och utbetalning."""

from datetime import date
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select

from models import (
    LedgerBatch,
    LedgerCapitalEntry,
    PayoutPart,
    PayoutPartState,
    Policy,
    PolicyBenefit,
)
from services import pension_claims
from services.payout_orders import TAX_LIABILITY
from simulation import counterparties
from simulation.premium_opening import PENSIONER, PEOPLE
from utils.bank_calendar import next_bank_day
from utils.checksums import canonical_hash

DECEMBER = date(2026, 12, 1)
DEATH_DAY = date(2026, 12, 14)
NOTICE_DAY = date(2026, 12, 15)
PAYMENT_DAY = next_bank_day(date(2027, 1, 1))
DECEASED, DECEASED_POLICY, _ = PEOPLE[1]
PENSIONER_ID, PENSIONER_POLICY, _ = PENSIONER
NOVEMBER_EXTRA = {PENSIONER_POLICY: ("600000.00", "1200.00", "-100.00", "-177.00", "0.00", "600923.00")}
EXPECTED = {
    "gross": "2040.07", "tax": "612.00", "net": "1428.07",
    "payment_liability": "0.00", "tax_liability": "612.00",
    "inheritance": {"AL-000001": "44.49", "AL-000003": "22772.74"},
    "balances": {"AL-000001": "11257.70", "AL-000002": "0.00", "AL-000003": "621378.25"},
    "pool": "22817.23",
}
STEPS = [
    (NOTICE_DAY, "prepare-pension-inputs"), (NOTICE_DAY, "pension-inputs"),
    (NOTICE_DAY, "verify-death"),
    (PAYMENT_DAY, "prepare_close"), (PAYMENT_DAY, "close-month"),
    (PAYMENT_DAY, "review-bank-preparation"), (PAYMENT_DAY, "prepare-bank"), (PAYMENT_DAY, "approve-bank"),
    (PAYMENT_DAY, "import-receipt"),
]
ACTIONS = {"pension-inputs", "verify-death", "prepare-bank", "approve-bank", "import-receipt"}


def _await_decision(state, action, view, checksum=None):
    state["status"] = "waiting_pension"
    state["pension_review"] = {"action": action, "view": view, "digest": checksum or canonical_hash(view)}


def next_decision(state, step):
    if step == "prepare-pension-inputs":
        simulated = counterparties.death_notice_file(
            [counterparties.DeathCase(DECEASED, DEATH_DAY)], notified_on=NOTICE_DAY, seed=state["manifest"]["seed"])
        state["files"]["death-notice"] = {"payload": simulated.payload, "label": simulated.label, "facit": simulated.facit}
        _await_decision(state, "pension-inputs", {
            "avisering": simulated.payload, "pensionär": PENSIONER_POLICY, "bolagsinsättning_sek": "10000.00",
            "skatt": "sidoinkomst 2027", "konto": "Verifierat syntetiskt konto"})
    else:
        _await_decision(state, "prepare-bank", {"pay_on": str(PAYMENT_DAY), "month": str(DECEMBER),
                                                "closing": state["december_close"]["batch_id"]})


def act(session, state, call, step, day, actor, note):
    def execute(operation, data):
        return call(operation, data, actor, note)["payload"]

    received = {"received_date": str(day), "channel": "manual"}
    if step == "pension-inputs":
        execute("register_company_capital", {"amount_sek": "10000.00", "decided_on": str(day),
                                             "document_ref": "Paket C, syntetiskt insättningsbeslut"})
        execute("register_tax_status", {"personal_id_number": PENSIONER_ID, "tax_year": PAYMENT_DAY.year,
                                        "kind": "side_income", **received})
        execute("register_payout_account", {"personal_id_number": PENSIONER_ID, "clearing_number": "0000",
                                            "account_number": "00000001", "bank_name": "Simulerad bank",
                                            "verified": True, "verification_method": "syntetiskt kontouppslag",
                                            "verification_ref": "Paket C provkonto", **received})
        notice = execute("import_death_notices", state["files"]["death-notice"]["payload"])
        _await_decision(state, "verify-death", {"intag": notice, "besked": state["files"]["death-notice"]["payload"]})
    elif step == "verify-death":
        current = execute("get_death_settlement", {"personal_id_number": DECEASED})
        report = current["reports"][-1]
        payload = state["files"]["death-notice"]["payload"]
        [notice] = payload["notices"]
        [imported] = state["pension_review"]["view"]["intag"]["outcomes"]
        if (report["status"], report["report_id"], report["death_date"]) != (
            "suspected", imported["report_id"], notice["death_date"]
        ):
            raise ValueError("Dödsfallsbeskedet har ändrats")
        state["verified_death"] = execute("verify_death_report", {
            "personal_id_number": DECEASED, "action": "verify", "death_date": str(DEATH_DAY),
            "verification_method": "population_register", "document_ref": notice["notice_id"], **received})
        state["status"] = "ready"
    elif step == "prepare-bank":
        prepared = execute("create_payout_orders", {"payment_day": str(PAYMENT_DAY)})
        bank = prepared["file"]
        if bank is None or len(bank["orders"]) != 1:
            raise ValueError("Provets bankfil ska ha exakt ett uppdrag")
        _await_decision(state, "approve-bank", bank, bank["checksum"])
    elif step == "approve-bank":
        bank = state["pension_review"]["view"]
        approved = execute("approve_payout_order", {"file_id": bank["file_id"], "reviewed_checksum": bank["checksum"]})
        state["outgoing_bank"] = approved["bank_file"]
        simulated = counterparties.payout_receipt_file(approved["bank_file"], bank_date=day, seed=state["manifest"]["seed"])
        state["files"]["payout-receipt"] = {"payload": simulated.payload, "label": simulated.label, "facit": simulated.facit}
        state["payout_file_id"] = bank["file_id"]
        _await_decision(state, "import-receipt", simulated.payload, simulated.payload["checksum"])
    elif step == "import-receipt":
        receipt = state["files"]["payout-receipt"]["payload"]
        imported = execute("import_payout_receipts", receipt)
        retry = execute("import_payout_receipts", receipt)
        view = execute("list_payout_orders", {"file_id": state["payout_file_id"]})
        claims = execute("list_payout_orders", {"month": str(DECEMBER)})["claims"]
        death = execute("get_death_settlement", {"personal_id_number": DECEASED})
        report = reconcile(session, state["december_close"], view, claims, death, imported, retry)
        state["pension_report"] = {**report, "run": state["id"], "manifest_hash": state["manifest_hash"]}
        state["status"] = "failed" if state["pension_report"]["failures"] else "completed"


def reconcile(session, close, bank, claims, death, imported, retry):
    """Stäm av bokade poster mot källkedjan och scenariots oberoende öresutfall."""
    failures = []

    def check(label, actual, expected):
        if actual != expected:
            failures.append(f"{label}: väntat {expected}, fick {actual}")

    [claim] = claims
    [bank_file] = bank["files"]
    [order] = bank_file["orders"]
    [line] = order["lines"]
    [settlement] = death["settlements"]
    [paid] = imported["outcomes"]
    pool = close["death"]["pool"]
    inheritance = {}
    balances = {}
    for number, part, entry in session.execute(
        select(Policy.policy_number, PayoutPart.id, LedgerCapitalEntry)
        .join(PolicyBenefit, PolicyBenefit.policy_id == Policy.id)
        .join(PayoutPart, PayoutPart.benefit_id == PolicyBenefit.id)
        .join(LedgerCapitalEntry, LedgerCapitalEntry.payout_part_id == PayoutPart.id)
        .where(LedgerCapitalEntry.account == "customer_capital").order_by(Policy.policy_number)
    ):
        balances[number] = balances.get(number, Decimal("0.00")) + entry.amount_sek
        if entry.reason == "pool_out":
            inheritance[number] = inheritance.get(number, Decimal("0.00")) + entry.amount_sek
        if entry.reason == "pension_debit":
            check("anspråkets uttagsdel", (number, str(part)), (PENSIONER_POLICY, claim["payout_part_id"]))
    gross, tax, net = (Decimal(order[k]) for k in ("gross_sek", "tax_sek", "net_sek"))
    payment_liability = pension_claims.account_balance(session, pension_claims.LIABILITY, PAYMENT_DAY.replace(day=1))
    tax_liability = pension_claims.account_balance(session, TAX_LIABILITY, PAYMENT_DAY.replace(day=1))
    check("anspråk till bankrad", (line["claim_id"], Decimal(claim["gross_sek"]), line["attempt"]),
          (claim["claim_id"], gross, 1))
    check("brutto minus skatt", net, gross - tax)
    check("30 procent sidoinkomst i hela kronor", tax, (gross * Decimal("0.30")).quantize(Decimal(1), ROUND_DOWN))
    check("betalt och rätt inkomstår", (order["outcome"], order["tax_year"]), ("executed", PAYMENT_DAY.year))
    check("anspråkets period och betalningsdag", (claim["right_month"], claim["payment_day"], claim["state"]),
          (str(DECEMBER), str(PAYMENT_DAY), "paid"))
    check("skulder efter kvittot", (payment_liability, tax_liability), (Decimal(0), tax))
    check("kvittots nya och återlevererade händelser", (imported["new"], retry["new"], retry["already_received"]), (1, 0, 1))
    check("återleveransens verifikation", retry["settlement"], None)
    check("en bokning för kvittot",
          [str(batch_id) for batch_id in session.scalars(select(LedgerBatch.id).where(LedgerBatch.kind == "payout_settlement"))],
          [imported["settlement"]["batch_id"]])
    check("avräknad del och pool", (balances[DECEASED_POLICY], Decimal(pool["closing_sek"])), (Decimal(0), Decimal(0)))
    check("arvsvinstens grund", pool["basis"]["code"], "SIM-R-2026-01")
    check("kapital till pool i ören", Decimal(settlement["capital_to_pool_sek"]), Decimal(EXPECTED["pool"]))
    check("utdelning i ören", sum(inheritance.values()), Decimal(EXPECTED["pool"]))
    ended = session.execute(select(PayoutPartState.state, PayoutPartState.valid_from, PayoutPartState.end_reason)
                            .join(PayoutPart).join(PolicyBenefit).join(Policy)
                            .where(Policy.policy_number == DECEASED_POLICY, PayoutPartState.valid_to.is_(None))).one()
    check("den avlidnes uttagsdel", tuple(ended), ("ended", date(2027, 1, 1), "death"))
    check("dödsfallsbesked", [r["status"] for r in death["reports"]], ["suspected", "verified"])
    check("kontroller i december", all(c["passed"] for c in close["controls"]), True)
    outcome = {"gross": str(gross), "tax": str(tax), "net": str(net), "payment_liability": str(payment_liability),
               "tax_liability": str(tax_liability), "inheritance": {k: str(v) for k, v in inheritance.items()},
               "balances": {k: str(v) for k, v in balances.items()}, "pool": pool["distributed_sek"]}
    for key, value in EXPECTED.items():
        check(key, outcome[key], value)
    return {"outcome": outcome, "hash": canonical_hash(outcome), "claims": claims, "bank": bank, "death": death,
            "close": close, "imported": imported, "retry": retry, "receipt_outcome": paid, "failures": failures}
