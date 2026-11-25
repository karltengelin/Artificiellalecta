"""Webbkontrollen för handläggarsidan Pensioner och utbetalningar (paket B steg 8, B-056, Karls val Z13).

Paket C:s pensionsscenario körs dag för dag genom sidan i stället för genom kalendern, på **lokala
SQLite-kopior** av körningens startbild – aldrig mot Lakebase eller testbeståndet. Facit är kalenderns
öresutfall (`simulation.pension_calendar.EXPECTED`).

    python scripts/simulation/paket_b_steg8/web_check.py copy KÄLLA.sqlite KOPIA.sqlite [--without-steps]
    python scripts/simulation/paket_b_steg8/web_check.py serve KOPIA.sqlite --day 2026-12-15 [--port 8768]
    python scripts/simulation/paket_b_steg8/web_check.py receipt BANKFIL.json --day 2027-01-04 --seed N
    python scripts/simulation/paket_b_steg8/web_check.py facit KOPIA.sqlite

- `copy` kopierar en bild; `--without-steps` tar bort steg 4–7:s tabeller (som Lakebase före migrationerna).
- `serve` startar handläggar-UI:t mot kopian med simulerad affärsdag. Operatörsinloggningen får ett eget
  lokalt testlösenord som skapas första gången och sparas i `logs/simulation/paket_b_steg8/web/` (gitignorerat);
  det skrivs aldrig ut. Med `--without-steps` på bilden används `--behall-schema`.
- `receipt` gör bankens kvittofil ur den nedladdade bankfilen med motpartssimulatorn.
- `facit` läser kopians utfall och jämför med facit; avvikelse ger slutkod 1.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import sqlite3
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

WORK = ROOT / "logs" / "simulation" / "paket_b_steg8" / "web"
PASSWORD = WORK / "operator-test-password.txt"
STEP_TABLES = ("death_reports", "death_settlements", "pension_claim_reversals", "estate_authorities",
               "payout_receipts", "payout_order_lines", "payout_orders", "payout_files", "payout_accounts",
               "tax_statuses", "pension_claim_fundings", "pension_claims", "payout_amounts", "payout_splits",
               "payout_plans", "payout_requests")


def _local(path: Path) -> Path:
    path = path.resolve()
    if path.suffix not in {".sqlite", ".db"}:
        raise SystemExit(f"{path} är ingen lokal SQLite-fil")
    return path


def copy(args) -> None:
    source, target = _local(args.source), _local(args.target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if args.without_steps:
        with sqlite3.connect(target) as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            for table in STEP_TABLES:
                conn.execute(f"DROP TABLE IF EXISTS {table}")
    print(f"{target}{'  (utan steg 4–7)' if args.without_steps else ''}")


def serve(args) -> None:
    image = _local(args.image)
    WORK.mkdir(parents=True, exist_ok=True)
    if not PASSWORD.exists():
        PASSWORD.write_text(secrets.token_urlsafe(18), encoding="utf-8")
    from argon2 import PasswordHasher

    os.environ.update({"HANDLAGGARE_DB": "demo", "OPERATOR_ID": "karl",
                       "OPERATOR_PASSWORD_HASH": PasswordHasher().hash(PASSWORD.read_text(encoding="utf-8").strip())})
    argv = ["web", "--db", "demo", "--demo-fil", str(image), "--affarsdag", args.day, "--port", str(args.port)]
    if args.keep_schema:
        argv.append("--behall-schema")
    sys.argv = argv
    from web.__main__ import main

    main()


def receipt(args) -> None:
    from simulation.counterparties import payout_receipt_file

    bank_file = json.loads(args.bank_file.read_text(encoding="utf-8"))
    simulated = payout_receipt_file(bank_file, None, bank_date=date.fromisoformat(args.day), seed=args.seed)
    target = args.bank_file.with_name(args.bank_file.stem + "-kvitton.json")
    target.write_text(json.dumps({**simulated.payload, "_label": simulated.label}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(target)


def facit(args) -> int:
    from sqlalchemy import create_engine, select

    from models import LedgerCapitalEntry, PayoutOrder, PayoutPart, Policy, PolicyBenefit
    from services import death_reports as dr
    from services import payout_orders as po
    from services import pension_claims as pc
    from services.db import session_factory_for
    from simulation.pension_calendar import EXPECTED, PAYMENT_DAY

    engine = create_engine(f"sqlite:///{_local(args.image)}")
    with session_factory_for(engine)() as s:
        [order] = s.scalars(select(PayoutOrder)).all()
        inheritance: dict[str, Decimal] = {}
        balances: dict[str, Decimal] = {}
        for number, entry in s.execute(
                select(Policy.policy_number, LedgerCapitalEntry).join(PolicyBenefit, PolicyBenefit.policy_id == Policy.id)
                .join(PayoutPart, PayoutPart.benefit_id == PolicyBenefit.id)
                .join(LedgerCapitalEntry, LedgerCapitalEntry.payout_part_id == PayoutPart.id)
                .where(LedgerCapitalEntry.account == "customer_capital")):
            balances[number] = balances.get(number, Decimal("0.00")) + entry.amount_sek
            if entry.reason == "pool_out":
                inheritance[number] = inheritance.get(number, Decimal("0.00")) + entry.amount_sek
        month = PAYMENT_DAY.replace(day=1)
        actual = {
            "gross": str(order.gross_sek), "tax": str(order.tax_sek), "net": str(order.net_sek),
            "payment_liability": str(pc.account_balance(s, pc.LIABILITY, month)),
            "tax_liability": str(pc.account_balance(s, po.TAX_LIABILITY, month)),
            "inheritance": {k: str(v) for k, v in sorted(inheritance.items())},
            "balances": {k: str(v) for k, v in sorted(balances.items())},
            "pool": str(sum(inheritance.values(), Decimal("0.00"))),
            "pool_closing": str(pc.account_balance(s, dr.POOL, month)),
        }
    expected = {**EXPECTED, "pool_closing": "0.00"}
    failures = [f"{k}: väntat {expected[k]}, fick {actual[k]}" for k in expected if actual[k] != expected[k]]
    print(json.dumps({"actual": actual, "expected": expected, "failures": failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    c = commands.add_parser("copy")
    c.add_argument("source", type=Path)
    c.add_argument("target", type=Path)
    c.add_argument("--without-steps", action="store_true")
    s = commands.add_parser("serve")
    s.add_argument("image", type=Path)
    s.add_argument("--day", required=True)
    s.add_argument("--port", type=int, default=8768)
    s.add_argument("--keep-schema", action="store_true")
    r = commands.add_parser("receipt")
    r.add_argument("bank_file", type=Path)
    r.add_argument("--day", required=True)
    r.add_argument("--seed", type=int, required=True)
    f = commands.add_parser("facit")
    f.add_argument("image", type=Path)
    args = parser.parse_args()
    if args.command == "copy":
        copy(args)
    elif args.command == "serve":
        serve(args)
    elif args.command == "receipt":
        receipt(args)
    else:
        return facit(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
