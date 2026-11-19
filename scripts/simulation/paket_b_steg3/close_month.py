"""Paket B steg 3: månadsstängning för sparandet (B-047, P1-PENSION-001 §7, PR-ITP1-020 steg 1–4 och 8).

Standard är granskning: räknar månadens stängning (eller rättelse av en stängd månad) i en `READ ONLY`-
transaktion med kontrollerna och granskningssumman (`review_checksum`). Ingenting skrivs. Den skarpa
körningen bokar med operationen `close_policy_month` som Karl, med den granskade summan; minsta avvikelse
rullar tillbaka allt, och samma innehåll igen ger ingen ny effekt (fall 16).

Förutsättningar: `migrate_month_close.py` är körd, AVK för månaden är antagen (`adopt_avk.py`), månaden är
slut och föregående månad stängd. I Lakebase kräver den skarpa körningen backup, samordning enligt AGENTS.md
§4.5 och Karls separata OK.

    python scripts/simulation/paket_b_steg3/close_month.py                                    # granskning, november
    python scripts/simulation/paket_b_steg3/close_month.py --apply --backup backups/<mapp> --reviewed-checksum <summa>

Databasen väljs med DATABASE_URL. Resultatet skrivs till huvudkatalogens
`logs/simulation/paket-b-steg3/close_month*_<månad>_<dialekt>.json`.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from common import NOVEMBER, OUT, require_backup  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--month", type=date.fromisoformat, default=NOVEMBER, help="Pensionsmånaden (ÅÅÅÅ-MM-01)")
parser.add_argument("--apply", action="store_true", help="Boka stängningen (annars bara granskning)")
parser.add_argument("--backup", type=Path, help="Backupmapp (manifest.json) tagen före steg 3")
parser.add_argument("--reviewed-checksum", help="review_checksum ur granskningen")
args = parser.parse_args()

from sqlalchemy.orm import Session  # noqa: E402

from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer  # noqa: E402
from services import month_close as mc  # noqa: E402
from services.db import session_factory_for  # noqa: E402
from services.operations.common import today  # noqa: E402
from utils.db import make_engine  # noqa: E402

engine = make_engine()
tag = f"{args.month:%Y-%m}_{engine.dialect.name}"
if not args.apply:
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        with Session(bind=conn) as session:
            try:
                plan = mc.plan_month(session, args.month, today())
            except mc.CloseError as exc:
                raise SystemExit(f"STOPP: {exc}") from exc
            summary = plan.summary()
        conn.rollback()
    (OUT / f"close_month_preview_{tag}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str),
                                                         encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("controls", "premiums")}, indent=2,
                     ensure_ascii=False, default=str))
    print(json.dumps({k: v for k, v in summary.get("premiums", {}).items() if k != "additions"}, indent=2,
                     ensure_ascii=False, default=str))
    for c in summary["controls"]:
        print(f"  {'OK ' if c['passed'] else 'FEL'} {c['step']}: {c['detail']}")
    if summary["status"] == "closed":
        print(f"Månaden är redan stängd med samma innehåll ({summary['review_checksum']}) – ingen ny effekt")
    elif summary["passed"]:
        print("GRANSKAT: kör med --apply --backup <mapp> --reviewed-checksum " + summary["review_checksum"]
              + " efter Karls OK")
    else:
        print("STOPP: stängningen har hinder eller avvikande kontroller")
    raise SystemExit(0)

require_backup(args.backup)
if not args.reviewed_checksum:
    raise SystemExit("Ange --reviewed-checksum ur granskningen")
service = ServiceLayer(session_factory=session_factory_for(engine), rules=ProductRuleCatalog())
ctx = OperationContext(actor=Actor.human("karl"), reason=f"Paket B steg 3: månadsstängning för sparandet "
                                                         f"{args.month:%Y-%m} (P1-PENSION-001 §7)")
result = service.execute("close_policy_month", ctx, {"month": args.month.isoformat(),
                                                     "reviewed_checksum": args.reviewed_checksum})
payload = result.output.payload
(OUT / f"close_month_{tag}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                                             encoding="utf-8")
print(json.dumps({k: v for k, v in payload.items() if k not in ("controls", "premiums")}, indent=2,
                 ensure_ascii=False, default=str))
print("BOKAT" if payload["created"] else "Redan bokat med samma innehåll – ingen ny effekt")
