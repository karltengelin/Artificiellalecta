"""Paket B steg 9 punkt 8: AVK-SIM-2026-03 för decembers stängning (B-057 Q5).

Innehållet är AVK-SIM-2026-02:s serie oförändrad plus december 2026 med en uttryckligen syntetisk
avkastning (`--rate`, standard +0,002 som i november). Satsen bekräftas av Karl vid körningen. Grunden
föreslås med `propose_valuation_basis` och antas med `adopt_valuation_basis` från 2026-12-01 med Karl som
aktör. AVK-SIM-2026-02 avslutas då 2026-11-30.

Standard är granskning i en `READ ONLY`-transaktion. Den visar innehållets kontrollsumma och läget för
koden. Den skarpa körningen kräver:

- backup;
- att december är slut (tidigast 2027-01-01);
- Karls separata OK.

Finns koden redan antagen med samma innehåll sker ingenting; annat innehåll stoppar.

    python scripts/simulation/paket_b_steg9/adopt_avk_december.py --rate 0.002                   # granskning
    python scripts/simulation/paket_b_steg9/adopt_avk_december.py --rate 0.002 --apply --backup backups/<mapp> --reviewed-checksum <summa>

Databasen väljs med DATABASE_URL. Resultatet skrivs till huvudkatalogens `logs/simulation/paket-b-steg9/`.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from common import (
    DECEMBER,
    DECEMBER_EARLIEST,
    context,
    engine,
    read_only,
    require_backup,
    service,
    write,
)

CODE, PREVIOUS = "AVK-SIM-2026-03", "AVK-SIM-2026-02"

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--rate", type=Decimal, default=Decimal("0.002"), help="Decembers syntetiska avkastning")
parser.add_argument("--apply", action="store_true", help="Föreslå och anta grunden (annars bara granskning)")
parser.add_argument("--backup", type=Path, help="Backupmapp (manifest.json) tagen före punkten")
parser.add_argument("--reviewed-checksum", help="Innehållets kontrollsumma ur granskningen")
args = parser.parse_args()

from sqlalchemy import select

from models import ValuationBasis
from services import valuation_bases as vb
from services.operations.common import today

eng = engine()
with read_only(eng) as s:
    old = s.scalar(select(ValuationBasis).where(ValuationBasis.code == PREVIOUS))
    if old is None or old.status != "adopted":
        raise SystemExit(f"{PREVIOUS} saknas eller är inte antagen – stopp (novembers AVK först)")
    base = vb.normalize("return_series", old.assumptions)
    if date.fromisoformat(base["months"][-1]["month"]) != date(2026, 11, 1):
        raise SystemExit(f"STOPP: {PREVIOUS} slutar inte i november 2026")
    content = vb.normalize("return_series", {
        **base, "description": f"Syntetisk S-04-bana, historik bevarad; december enligt B-057 (sats {args.rate}).",
        "months": [*base["months"], {"month": DECEMBER.isoformat(), "rate": str(args.rate)}]})
    digest = vb.checksum(content)
    current = s.scalar(select(ValuationBasis).where(ValuationBasis.code == CODE))
    state = None if current is None else {"status": current.status, "checksum": current.checksum,
                                          "valid_from": current.valid_from}

summary = {"code": CODE, "supersedes": PREVIOUS, "valid_from": DECEMBER.isoformat(), "december_rate": str(args.rate),
           "months": len(content["months"]), "content_checksum": digest, "existing": state}
write("adopt_avk_december_preview", eng, {**summary, "assumptions": content})
print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
if current is not None:
    if current.checksum != digest:
        raise SystemExit(f"STOPP: {CODE} finns redan med annat innehåll ({current.checksum})")
    if current.status == "adopted":
        print(f"{CODE} är redan antagen med samma innehåll – ingen ny effekt")
        raise SystemExit(0)
if not args.apply:
    print(f"GRANSKAT: kör med --rate {args.rate} --apply --backup <mapp> --reviewed-checksum {digest} efter Karls OK "
          f"(tidigast {DECEMBER_EARLIEST})")
    raise SystemExit(0)

require_backup(args.backup)
if args.reviewed_checksum != digest:
    raise SystemExit("Granskningssumman stämmer inte med innehållet – granska igen")
if today() < DECEMBER_EARLIEST:
    raise SystemExit(f"December är inte slut – grunden antas tidigast {DECEMBER_EARLIEST}")
svc, ctx = service(eng), context("Paket B steg 9: AVK för decembers stängning (B-057 Q5)")
if current is None:
    svc.execute("propose_valuation_basis", ctx, {
        "code": CODE, "title": "Syntetisk avkastning för december 2026", "assumptions": content,
        "source_refs": "B-057 Q5; P1-PENSION-001 §12.1", "supersedes_code": PREVIOUS})
payload = svc.execute("adopt_valuation_basis", ctx, {"code": CODE, "valid_from": DECEMBER.isoformat(),
                                                    "decision_ref": f"B-057 Q5 (paket B steg 9), sats {args.rate}"}
                      ).output.model_dump(mode="json")
write("adopt_avk_december", eng, payload)
print(f"ANTAGEN: {CODE} från {DECEMBER} med kontrollsumma {digest}")
