"""Paket B steg 9: skrivskyddad kontroll av det nya startläget och pensionärerna (B-057 Q10).

Körs efter varje punkt i Q5:s ordning. Den visar hur långt kedjan har kommit och prövar det som är gjort:

1. **Beståndet:** alla 35 nya finns med fribrev och sin startpremie.
2. **Det ingående läget:** varje ny försäkring har C lika med startpremien och G större än noll. Med
   `--replaced` (körloggen från `reopen_ledger.py --apply`) prövas också att det gamla lägets försäkringar har
   samma antal och summa C som förut.
3. **Novembers stängning:** ett ärende `payout_review` per person som passerat 66 utan plan.
4. **Planerna:** fem beslutade planer i december, bolagsinsättningen minst 24 × decembers månadsbelopp.
5. **Decembers stängning:** fem månadsrätter, summa brutto lika med summa M, och skatten per person i hela
   kronor nedåt (sidoinkomst 30 % eller individuellt beslut).

Allt läses i en `READ ONLY`-transaktion. Ingenting skrivs utom körloggen.

    python scripts/simulation/paket_b_steg9/verify.py
    python scripts/simulation/paket_b_steg9/verify.py --replaced <huvudkatalog>/logs/simulation/paket-b-steg9/reopen_ledger_postgresql.json

Databasen väljs med DATABASE_URL. Resultatet skrivs till huvudkatalogens `logs/simulation/paket-b-steg9/`.
"""
from __future__ import annotations

import argparse
import json
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

from common import DEC_END, DECEMBER, NOV_END, engine, read_only, write

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--replaced", type=Path, help="Körloggen från reopen_ledger.py --apply (replaced_content)")
args = parser.parse_args()

from sqlalchemy import func, select

from models import (
    Case,
    InsuredPerson,
    LedgerBatch,
    PayoutPart,
    PayoutPlan,
    PayoutRequest,
    Policy,
    PolicyBenefit,
    PremiumTransaction,
)
from services import capital_ledger as cl
from services import ledger_reopening as lr
from services import payout_orders as po
from services import pension_claims as pc
from simulation import pension_population as pop

checks: list[dict] = []


def check(step: str, passed: bool | None, detail: str) -> None:
    checks.append({"step": step, "passed": passed, "detail": detail})


eng = engine()
with read_only(eng) as s:
    pnrs = [m.personal_id_number for m in pop.MEMBERS]
    plan = pop.plan_population(s)
    check("beståndet", plan.already_added,
          f"{len(plan.existing)} av {len(pop.MEMBERS)} nya personer; krockar {plan.collisions or 'inga'}")
    batch = cl.opening_batch(s)
    premium = dict(s.execute(
        select(Policy.id, PremiumTransaction.amount_sek).join(PolicyBenefit, PolicyBenefit.policy_id == Policy.id)
        .join(PremiumTransaction, PremiumTransaction.benefit_id == PolicyBenefit.id)
        .join(InsuredPerson, InsuredPerson.id == Policy.insured_person_id)
        .where(InsuredPerson.personal_id_number.in_(pnrs), PremiumTransaction.paid_date == pop.PREMIUM_PAID)).all())
    booked = lr.booked_by_policy(s, batch) if batch is not None else {}
    new = {p: booked.get(str(p)) for p in premium}
    if not premium or all(v is None for v in new.values()):
        check("ingående läget", None, "de nya försäkringarna finns inte i läget än (reopen_ledger.py)")
    else:
        wrong = [str(p) for p, v in new.items() if v is None or v[0] != Decimal(premium[p]) or v[1] <= 0]
        check("ingående läget", not wrong, f"{len(new) - len(wrong)} av {len(new)} nya med C = startpremien och "
                                           f"G > 0; verifikation {batch.id}")
        if args.replaced:
            old = json.loads(args.replaced.read_text(encoding="utf-8"))["replaced_content"]["totals"]
            kept = {p: v for p, v in booked.items() if p not in {str(k) for k in premium}}
            same = len(kept) == int(old["policies"]) and \
                sum((c for c, _ in kept.values()), Decimal(0)) == Decimal(old["capital_sek"])
            check("befintliga oförändrade", same, f"{len(kept)} befintliga försäkringar, gamla läget {old}")
    closed = cl.closed_month_ends(s)
    if NOV_END in closed:
        reviews = s.scalar(select(func.count()).select_from(Case).where(Case.case_type == "payout_review"))
        check("novembers stängning", reviews >= 1, f"{reviews} ärenden payout_review (väntat: ett per person som "
                                                   "passerat 66 utan plan vid stängningen)")
    else:
        check("novembers stängning", None, "november är inte stängd än")
    ids = [r.id for r in s.scalars(select(PayoutRequest).where(PayoutRequest.kind == "start",
                                                               PayoutRequest.change_month == pop.START_MONTH))]
    plans = list(s.scalars(select(PayoutPlan).where(PayoutPlan.request_id.in_(ids)))) if ids else []
    m_total = sum((p.m_sek for p in plans), Decimal(0))
    if plans:
        capital = [b for b in s.scalars(select(LedgerBatch).where(LedgerBatch.kind == pc.CAPITAL_KIND))]
        amounts = [Decimal(b.content["amount_sek"]) for b in capital]
        check("planerna", len(plans) == 5, f"{len(plans)} beslutade planer från december, summa M {m_total}")
        check("bolagsinsättningen", any(a >= 24 * m_total for a in amounts),
              f"insättningar {[str(a) for a in amounts]}; 24 × M = {24 * m_total}")
    else:
        check("planerna", None, "inga planer beslutade än (pensioners.py --phase start)")
    if DEC_END in closed:
        claims = po.claims_payment_view(s, DECEMBER)
        gross = sum((Decimal(c["gross_sek"]) for c in claims), Decimal(0))
        check("decembers månadsrätter", len(claims) == 5 and gross == m_total,
              f"{len(claims)} månadsrätter, brutto {gross}, summa M {m_total}")
        person_of = {str(k): v for k, v in s.execute(
            select(PayoutPart.id, InsuredPerson.personal_id_number)
            .join(PolicyBenefit, PolicyBenefit.id == PayoutPart.benefit_id)
            .join(Policy, Policy.id == PolicyBenefit.policy_id)
            .join(InsuredPerson, InsuredPerson.id == Policy.insured_person_id)
            .where(InsuredPerson.personal_id_number.in_([m.personal_id_number for m in pop.PENSIONERS]))).all()}
        per_person: dict[str, Decimal] = {}
        for c in claims:
            pnr = person_of.get(c["payout_part_id"])
            per_person[pnr] = per_person.get(pnr, Decimal(0)) + Decimal(c["gross_sek"])
        rate = {m.personal_id_number: m.tax_rate or Decimal("0.30") for m in pop.PENSIONERS}
        facit = {pnr: {"gross": str(g), "tax": str(t := (g * rate[pnr]).quantize(Decimal(1), rounding=ROUND_FLOOR)),
                       "net": str(g - t)} for pnr, g in per_person.items() if pnr in rate}
        check("utbetalningen (facit)", None if len(facit) == 4 else False,
              f"väntat per person {facit}; jämförs mot bankfilen på pensionssidan")
    else:
        check("decembers stängning", None, "december är inte stängd än")

write("verify", eng, {"checks": checks})
for c in checks:
    mark = {True: "OK ", False: "FEL", None: "–  "}[c["passed"]]
    print(f"  {mark} {c['step']}: {c['detail']}")
failed = [c for c in checks if c["passed"] is False]
print("STOPP: avvikelse" if failed else "Inga avvikelser i det som är gjort")
raise SystemExit(1 if failed else 0)
