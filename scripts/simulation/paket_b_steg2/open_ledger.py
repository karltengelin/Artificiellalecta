"""Paket B steg 2: kapitaljournalens ingående läge från S-04 per 2026-10-31 (B-047, P1-PENSION-001 §6.2, §12 punkt 3).

Standard är granskning: bygger S-04 per 2026-10-31 och planerar övergången i en `READ ONLY`-transaktion,
med kontrollerna och granskningssumman (`review_checksum`). Ingenting skrivs. Den skarpa körningen bokar
det ingående läget med operationen `open_capital_ledger` som Karl, med den granskade summan; minsta
avvikelse rullar tillbaka allt, och samma innehåll igen ger ingen ny effekt.

Förutsättningar: `migrate_capital_ledger.py` är körd. Den väntade utdragshashen är den P6-MANAD-001 frös
(`023946…3fefa`); en annan hash stoppar. I Lakebase kräver den skarpa körningen backup, samordning enligt
AGENTS.md §4.5 och Karls separata OK.

    python scripts/simulation/paket_b_steg2/open_ledger.py                                   # granskning
    python scripts/simulation/paket_b_steg2/open_ledger.py --apply --backup backups/<mapp> --reviewed-checksum <summa>

Databasen väljs med DATABASE_URL, som i övriga skript. Resultatet skrivs till huvudkatalogens
`logs/simulation/paket-b-steg2/open_ledger*_<dialekt>.json`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import OUT  # noqa: E402  (lägger också src/ på sökvägen)

#: S-04 per 2026-10-31 som P6-MANAD-001 frös i Lakebase (AVSTAMD_FTA_MANAD_DESIGNSTOPP.md §3.3)
FROZEN_EXTRACT = "023946257ca8e184028d9727e52756cc9ec541fe9c5922dcd2f9b9b8c053fefa"

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--apply", action="store_true", help="Boka det ingående läget (annars bara granskning)")
parser.add_argument("--backup", type=Path, help="Backupmapp (manifest.json) tagen före övergången")
parser.add_argument("--reviewed-checksum", help="review_checksum ur granskningen")
parser.add_argument("--expected-extract-checksum", default=FROZEN_EXTRACT,
                    help="Väntad S-04-hash per 2026-10-31 (standard: P6-MANAD-001:s frysta)")
args = parser.parse_args()

from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer  # noqa: E402
from services import capital_ledger as cl  # noqa: E402
from services.db import session_factory_for  # noqa: E402
from utils.db import make_engine  # noqa: E402

engine = make_engine()
if not args.apply:
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        from sqlalchemy.orm import Session

        with Session(bind=conn) as session:
            if not cl.journal_present(session):
                raise SystemExit("Kapitaljournalen är inte införd – kör migrate_capital_ledger.py först")
            batch = cl.opening_batch(session)
            if batch is not None:
                print(f"Det ingående läget är redan bokat: verifikation {batch.id}, summa {batch.checksum}")
                raise SystemExit(0)
            plan = cl.plan_opening(session, args.expected_extract_checksum)
            summary = plan.summary()
        conn.rollback()
    (OUT / f"open_ledger_preview_{engine.dialect.name}.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str),
                                                  encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "controls"}, indent=2, ensure_ascii=False, default=str))
    for c in summary["controls"]:
        print(f"  {'OK ' if c['passed'] else 'FEL'} {c['step']}: {c['detail']}")
    print("GRANSKAT: kör med --apply --backup <mapp> --reviewed-checksum " + summary["review_checksum"]
          + " efter Karls OK" if summary["passed"] else "STOPP: övergången har hinder eller avvikande kontroller")
    raise SystemExit(0)

manifest = args.backup / "manifest.json" if args.backup else None
if manifest is None or not manifest.is_file():
    raise SystemExit("Ange --backup med en backupmapp från scripts/maintenance/backup_database.py (manifest.json saknas)")
if not args.reviewed_checksum:
    raise SystemExit("Ange --reviewed-checksum ur granskningen")
service = ServiceLayer(session_factory=session_factory_for(engine), rules=ProductRuleCatalog())
ctx = OperationContext(actor=Actor.human("karl"), reason="Paket B steg 2: kapitaljournalens ingående läge från S-04 "
                                                         "per 2026-10-31 (P1-PENSION-001 §6.2)")
result = service.execute("open_capital_ledger", ctx, {"reviewed_checksum": args.reviewed_checksum,
                                                      "expected_extract_checksum": args.expected_extract_checksum})
payload = result.output.payload
(OUT / f"open_ledger_{engine.dialect.name}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(json.dumps({k: v for k, v in payload.items() if k != "controls"}, indent=2, ensure_ascii=False, default=str))
print("BOKAT" if payload["created"] else "Redan bokat med samma innehåll – ingen ny effekt")
