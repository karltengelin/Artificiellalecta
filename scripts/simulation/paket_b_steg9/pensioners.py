"""Paket B steg 9 punkt 5 och 7: pensionärernas begäran, planer, skatt, konto och bolagsinsättningen (B-057 Q1, Q6, Q7).

Underlaget är detsamma som i provet `tests/test_pension_population.py` (`simulation.pension_population`).
Varje fas körs med operationerna som Karl. Alla operationer är idempotenta, så samma fas igen ger ingen ny
effekt.

| Fas | När | Vad |
|---|---|---|
| `split` | före novembers stängning | Karin Sjöbergs delning från november: begäran och `split_payout_part` |
| `start` | efter novembers stängning | begäran om start i december per uttagsdel (mottagen 2026-11-16), förhandsberäkning och `decide_payout_plan` |
| `inputs` | efter `start` | skattestatus 2027 (`register_tax_status`) och verifierat konto (`register_payout_account`) |
| `capital` | efter `start`, före decembers stängning | `register_company_capital` med 24 × decembers månadsbelopp, uppåt till hela 10 000 kr (Q6) |

Standard är granskning i en `READ ONLY`-transaktion. Den visar fasens underlag, läget per person och
granskningssumman. Ingenting skrivs. Den skarpa körningen kräver backup, den granskade summan och Karls
separata OK.

    python scripts/simulation/paket_b_steg9/pensioners.py --phase split                     # granskning
    python scripts/simulation/paket_b_steg9/pensioners.py --phase split --apply --backup backups/<mapp> --reviewed-checksum <summa>

Databasen väljs med DATABASE_URL. Resultatet skrivs till huvudkatalogens
`logs/simulation/paket-b-steg9/pensioners_<fas>*_<dialekt>.json`.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from common import NOV_END, context, engine, read_only, require_backup, service, write

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--phase", required=True, choices=("split", "start", "inputs", "capital"))
parser.add_argument("--apply", action="store_true", help="Kör fasens operationer (annars bara granskning)")
parser.add_argument("--backup", type=Path, help="Backupmapp (manifest.json) tagen före fasen")
parser.add_argument("--reviewed-checksum", help="review_checksum ur granskningen")
args = parser.parse_args()

from sqlalchemy import select

from models import InsuredPerson, PayoutPlan, PayoutRequest, PayoutSplit, Policy
from services import capital_ledger as cl
from services import valuation_bases as vb
from simulation import pension_population as pop

KARIN = next(m for m in pop.PENSIONERS if m.split_share is not None)
eng = engine()


def policy_numbers(s) -> dict[str, str]:
    return dict(s.execute(select(InsuredPerson.personal_id_number, Policy.policy_number).join(Policy)
                          .where(InsuredPerson.personal_id_number.in_([m.personal_id_number for m in pop.PENSIONERS]))
                          ).all())


def requests(numbers: dict[str, str]) -> list[dict]:
    if args.phase == "split":
        return [pop.split_request(KARIN, numbers[KARIN.personal_id_number])]
    return [r for m in pop.PENSIONERS for r in pop.start_requests(m, numbers[m.personal_id_number])]


def decided(s, kind: str) -> dict[str, bool]:
    """Vilka av pensionärernas begäran av slaget som redan är registrerade och beslutade."""
    model = PayoutSplit if kind == "split" else PayoutPlan
    rows = s.scalars(select(PayoutRequest).where(PayoutRequest.kind == kind,
                                                 PayoutRequest.change_month == (pop.SPLIT_MONTH if kind == "split"
                                                                                else pop.START_MONTH)))
    return {str(r.id): s.scalar(select(model.id).where(model.request_id == r.id)) is not None for r in rows}


def december_m(s) -> Decimal:
    ids = [r.id for r in s.scalars(select(PayoutRequest).where(PayoutRequest.kind == "start",
                                                               PayoutRequest.change_month == pop.START_MONTH))]
    plans = list(s.scalars(select(PayoutPlan).where(PayoutPlan.request_id.in_(ids)))) if ids else []
    if len(plans) != sum(len(m.plans) for m in pop.PENSIONERS):
        raise SystemExit(f"STOPP: {len(plans)} beslutade planer – kör --phase start först")
    return sum((p.m_sek for p in plans), Decimal(0))


with read_only(eng) as s:
    if not pop.plan_population(s).already_added:
        raise SystemExit("STOPP: beståndet är inte tillagt – kör add_population.py först")
    numbers = policy_numbers(s)
    closed = cl.closed_month_ends(s)
    nov_closed = NOV_END in closed
    state = {"closed_month_ends": [d.isoformat() for d in closed]}
    if args.phase == "split":
        if nov_closed:
            raise SystemExit("STOPP: november är stängd – delningen från november ska göras före stängningen")
        body = {"requests": requests(numbers)}
        state["decided"] = decided(s, "split")
    elif not nov_closed:
        raise SystemExit("STOPP: november är inte stängd – fasen körs efter novembers stängning (Q5)")
    elif args.phase == "start":
        body = {"requests": requests(numbers)}
        state["decided"] = decided(s, "start")
    elif args.phase == "inputs":
        body = {"tax": [pop.tax_status(m) for m in pop.PENSIONERS],
                "accounts": [pop.payout_account(m) for m in pop.PENSIONERS]}
    else:
        m_total = december_m(s)
        body = {"capital": {"amount_sek": str(pop.capital_deposit(m_total)), "decided_on": pop.CAPITAL_DECIDED.isoformat(),
                            "document_ref": pop.CAPITAL_REF}, "december_m_total_sek": str(m_total)}
digest = vb.checksum({"decision": pop.DECISION, "phase": args.phase, **body})
summary = {"phase": args.phase, **body, "state": state, "review_checksum": digest}
write(f"pensioners_{args.phase}_preview", eng, summary)
print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
if not args.apply:
    print(f"GRANSKAT: kör med --apply --backup <mapp> --reviewed-checksum {digest} efter Karls OK")
    raise SystemExit(0)

require_backup(args.backup)
if args.reviewed_checksum != digest:
    raise SystemExit("Granskningssumman stämmer inte med underlaget – granska igen")
svc, ctx = service(eng), context()


def run(name: str, data: dict) -> dict:
    return svc.execute(name, ctx, data).output.payload


results = []
if args.phase in ("split", "start"):
    for data in body["requests"]:
        made = run("register_payout_request", data)
        if made["outcome"] != "in_time":
            raise SystemExit(f"STOPP: begäran {made['request_id']} har utfallet {made['outcome']}")
        with read_only(eng) as s:
            done = decided(s, args.phase).get(made["request_id"], False)
        if done:
            results.append({**made, "decision": "redan beslutad"})
            continue
        review = run("preview_payout_plan", {"request_id": made["request_id"]})
        operation = "split_payout_part" if args.phase == "split" else "decide_payout_plan"
        decision = run(operation, {"request_id": made["request_id"], "reviewed_checksum": review["review_checksum"],
                                   "reason": f"Kundens begäran ({pop.DECISION}, nytt startläge)"})
        results.append({**made, "preview": review, "decision": decision})
elif args.phase == "inputs":
    results = [run("register_tax_status", d) for d in body["tax"]] + \
              [run("register_payout_account", d) for d in body["accounts"]]
else:
    results = [run("register_company_capital", body["capital"])]
write(f"pensioners_{args.phase}", eng, {"review_checksum": digest, "results": results})
print(f"KÖRT: fasen {args.phase}, {len(results)} operationer (se loggen för nya och redan gjorda)")
