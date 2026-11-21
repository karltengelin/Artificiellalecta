"""Skrivskyddad kontroll efter steg 4:s migration (paket B steg 4, P1-PENSION-001 §5 och §12).

Kontrollerar i en `READ ONLY`-transaktion (Postgres) med den betrodda anslutningen:

- att migrationen är införd: tabellerna `payout_requests`, `payout_plans` och `payout_splits` med
  modellens kolumner, ärendetyperna `payout_request` och `payout_review`, `ledger_guarantee_parts.plan_id`
  med villkor och index;
- att journalen är orörd: det ingående läget och varje stängd månad prövas mot sin sammanställning,
  ingen garantidel är planbaserad och inga planer, begäran eller delningar finns ännu (om inget beslutats);
- att ledger-utdraget per senast stängda månadsslut är godkänt;
- att ingen agentroll har rättigheter på de nya tabellerna eller journalen (bara Postgres);
- med `--backup`: att radantalen i alla tabeller är desamma som i backupen, utom `operation_events`.

Databasen väljs med DATABASE_URL. Resultatet skrivs till huvudkatalogens
`logs/simulation/paket-b-steg4/verify.json`. Ändrar ingenting.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import OUT, require_backup

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--backup", type=Path, help="Backupmappen (manifest.json) tagen före migrationen")
args = parser.parse_args()

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from models import LedgerGuaranteePart, PayoutPlan, PayoutRequest, PayoutSplit
from services import capital_ledger as cl
from services import month_close as mc
from services import payout_plans as pl
from services.ledger_extract import build_ledger_extract
from utils.db import make_engine
from utils.migration_payout_plans import applied_state, granted_to_agents
from utils.migration_premium_flow import (
    _agent_roles,
    _column_signature,
    _model_columns,
    _row_counts,
)

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail="") -> None:
    checks.append((name, bool(ok), str(detail)))
    print(f"  {'OK ' if ok else 'FEL'} {name}" + (f": {detail}" if detail else ""))


engine = make_engine()
with engine.connect() as conn:
    postgres = engine.dialect.name == "postgresql"
    if postgres:
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        state = applied_state(conn)
        check("migrationen införd", all(state.values()), ", ".join(k for k, v in state.items() if not v) or "alla delar")
        for model in (PayoutRequest, PayoutPlan, PayoutSplit, LedgerGuaranteePart):
            check(f"kolumner i {model.__tablename__}",
                  _column_signature(conn, model.__tablename__) == _model_columns(model.__table__, conn.dialect))
        granted = granted_to_agents(conn, _agent_roles(conn))
        check("inga agenträttigheter", not granted, ", ".join(granted))
    with Session(bind=conn) as session:
        check("tabellerna finns", pl.plans_present(session))
        opening = cl.opening_batch(session)
        cl.verify_opening(session, opening)
        check("ingående läge orört", True, f"{opening.period_end}, {opening.checksum[:12]}")
        closed = cl.closed_month_ends(session)
        for end in closed:
            mc.verify_month(session, cl.effective_batch(session, end))
        check("stängda månader orörda", True, ", ".join(str(e) for e in closed) or "ingen stängd")
        counts = {m.__tablename__: session.scalar(select(func.count()).select_from(m))
                  for m in (PayoutRequest, PayoutPlan, PayoutSplit)}
        planned = session.scalar(select(func.count()).select_from(LedgerGuaranteePart)
                                 .where(LedgerGuaranteePart.plan_kind == "plan"))
        check("inga planbaserade garantidelar utan plan", planned == 0 or counts["payout_plans"] > 0,
              f"{planned} planbaserade, {counts}")
        last = max([opening.period_end, *closed])
        extract = build_ledger_extract(session, last)
        check(f"ledger-utdraget per {last}", extract.approved,
              ", ".join(c.name for c in extract.checks if not c.passed))
        if args.backup is not None and postgres:
            manifest = json.loads(require_backup(args.backup).read_text(encoding="utf-8"))
            before = manifest["row_counts"]
            names = set(inspect(conn).get_table_names())
            after = _row_counts(conn, names)
            changed = {t: (before.get(t), after.get(t)) for t in names
                       if t != "operation_events" and before.get(t, 0) != after.get(t, 0)}
            check("radantal som i backupen", not changed, changed or "oförändrade utom operation_events")
    conn.rollback()

(OUT / "verify.json").write_text(json.dumps([{"check": n, "passed": ok, "detail": d} for n, ok, d in checks],
                                            indent=2, ensure_ascii=False), encoding="utf-8")
passed = sum(ok for _, ok, _ in checks)
print(f"{passed} av {len(checks)} kontroller godkända")
raise SystemExit(0 if passed == len(checks) else 1)
