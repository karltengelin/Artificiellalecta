"""Paket B steg 3: AVK-SIM-2026-02 för novembers stängning genom A4:s väg (P1-PENSION-001 §7, Karls val S5).

Innehållet är exakt P6-MANAD-001 D5: AVK-SIM-2026-01:s historik 2023-01–2026-10 oförändrad plus november
2026 med +0,002, uttryckligen syntetiskt (`premium_month_inputs.november_returns`). Grunden föreslås med
`propose_valuation_basis` och antas med `adopt_valuation_basis` från 2026-11-01 med Karl som aktör;
AVK-SIM-2026-01 avslutas då 2026-10-31. Ingen grund ändras i övrigt.

Standard är granskning i en `READ ONLY`-transaktion: visar innehållets kontrollsumma och läget för koden.
Den skarpa körningen kräver backup, att november är slut (tidigast 2026-12-01, S6) och Karls separata OK.
Finns koden redan antagen med samma innehåll från 2026-11-01 sker ingenting; annat innehåll stoppar.

    python scripts/simulation/paket_b_steg3/adopt_avk.py                                   # granskning
    python scripts/simulation/paket_b_steg3/adopt_avk.py --apply --backup backups/<mapp> --reviewed-checksum <summa>

Databasen väljs med DATABASE_URL. Resultatet skrivs till huvudkatalogens `logs/simulation/paket-b-steg3/`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import (  # noqa: E402
    AVK_CODE,
    AVK_DECISION,
    AVK_RATE,
    EARLIEST,
    NOVEMBER,
    OUT,
    require_backup,
)

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--apply", action="store_true", help="Föreslå och anta grunden (annars bara granskning)")
parser.add_argument("--backup", type=Path, help="Backupmapp (manifest.json) tagen före steg 3")
parser.add_argument("--reviewed-checksum", help="Innehållets kontrollsumma ur granskningen")
args = parser.parse_args()

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from models import ValuationBasis  # noqa: E402
from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer  # noqa: E402
from services import valuation_bases as vb  # noqa: E402
from services.db import session_factory_for  # noqa: E402
from services.operations.common import today  # noqa: E402
from services.premium_month_inputs import november_returns  # noqa: E402
from utils.db import make_engine  # noqa: E402

engine = make_engine()
with engine.connect() as conn:
    if engine.dialect.name == "postgresql":
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    with Session(bind=conn) as s:
        old = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "AVK-SIM-2026-01"))
        if old is None or old.status != "adopted":
            raise SystemExit("AVK-SIM-2026-01 saknas eller är inte antagen – stopp")
        content = november_returns(old.assumptions, AVK_RATE)
        digest = vb.checksum(content)
        current = s.scalar(select(ValuationBasis).where(ValuationBasis.code == AVK_CODE))
        state = None if current is None else {"status": current.status, "checksum": current.checksum,
                                              "valid_from": current.valid_from, "decision_ref": current.decision_ref}
        later = [r.code for r in s.scalars(select(ValuationBasis).where(
            ValuationBasis.family == "AVK-SIM", ValuationBasis.status == "adopted",
            ValuationBasis.valid_from >= NOVEMBER))]
    conn.rollback()

summary = {"code": AVK_CODE, "content_checksum": digest, "supersedes": "AVK-SIM-2026-01",
           "previous_valid_to_after": "2026-10-31", "valid_from": NOVEMBER.isoformat(), "november_rate": str(AVK_RATE),
           "months": len(content["months"]), "existing": state, "adopted_from_november": later}
(OUT / f"adopt_avk_preview_{engine.dialect.name}.json").write_text(
    json.dumps({**summary, "assumptions": content}, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))

if current is not None:
    if current.checksum != digest:
        raise SystemExit(f"STOPP: {AVK_CODE} finns redan med annat innehåll ({current.checksum})")
    if current.status == "adopted" and current.valid_from == NOVEMBER:
        print(f"{AVK_CODE} är redan antagen med samma innehåll från {NOVEMBER} – ingen ny effekt")
        raise SystemExit(0)
    if current.status != "proposed":
        raise SystemExit(f"STOPP: {AVK_CODE} är {current.status} – avgörs manuellt")
if later and later != [AVK_CODE]:
    raise SystemExit(f"STOPP: en annan AVK-grund är redan antagen från november eller senare: {later}")
if not args.apply:
    print(f"GRANSKAT: kör med --apply --backup <mapp> --reviewed-checksum {digest} efter Karls OK "
          f"(tidigast {EARLIEST})")
    raise SystemExit(0)

require_backup(args.backup)
if args.reviewed_checksum != digest:
    raise SystemExit("Granskningssumman stämmer inte med innehållet – granska igen")
if today() < EARLIEST:
    raise SystemExit(f"November är inte slut och sista bankfilen inte läst – antas tidigast {EARLIEST} (S6)")
service = ServiceLayer(session_factory=session_factory_for(engine), rules=ProductRuleCatalog())
ctx = OperationContext(actor=Actor.human("karl"), reason="Paket B steg 3: AVK för novembers månadsstängning "
                                                         "(P1-PENSION-001 §7, S5; innehåll P6-MANAD-001 D5)")
if current is None:
    service.execute("propose_valuation_basis", ctx, {
        "code": AVK_CODE, "title": "Syntetisk avkastning för november 2026", "assumptions": content,
        "source_refs": "P6-MANAD-001 D5; P1-PENSION-001 S5", "supersedes_code": "AVK-SIM-2026-01"})
payload = service.execute("adopt_valuation_basis", ctx, {"code": AVK_CODE, "valid_from": NOVEMBER.isoformat(),
                                                         "decision_ref": AVK_DECISION}).output.model_dump(mode="json")
(OUT / f"adopt_avk_{engine.dialect.name}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                                                         encoding="utf-8")
print(f"ANTAGEN: {AVK_CODE} från {NOVEMBER} med kontrollsumma {digest}")
