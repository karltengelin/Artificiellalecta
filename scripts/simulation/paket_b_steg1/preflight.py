"""Skrivskyddad förkontroll i Lakebase före uttagsdelarnas migration (paket B steg 1, AGENTS.md §4.5).

Visar andra anslutningar till databasen (utom den egna), om uttagsdelarnas tabeller redan finns,
gamla uttagslägen i `policy_states`, antal ålderspensionsförmåner och agentrollernas nuvarande
rättigheter på de nya tabellerna. Allt i en `READ ONLY`-transaktion; skriver resultatet till
huvudkatalogens `logs/simulation/paket-b-steg1/preflight.json`. Ändrar ingenting.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from common import OUT  # noqa: E402  (lägger också src/ på sökvägen)

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.parse_args()

from sqlalchemy import inspect, text  # noqa: E402

from utils.db import make_engine  # noqa: E402
from utils.migration_payout_parts import TABLES  # noqa: E402

ROLES = ("agent_forsakring", "agent_aktuarie", "agent_compliance")

with make_engine().connect() as conn:
    conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    others = [dict(r._mapping) for r in conn.execute(text(
        "SELECT pid, usename, application_name, client_addr::text AS client_addr, state, "
        "backend_start::text AS backend_start, left(query, 80) AS query FROM pg_stat_activity "
        "WHERE datname = current_database() AND pid <> pg_backend_pid() AND backend_type = 'client backend'"
    ))]
    names = set(inspect(conn).get_table_names())
    present = [t for t in TABLES if t in names]
    legacy = conn.execute(text(
        "SELECT state, count(*) FROM policy_states WHERE state NOT IN ('premium_paying', 'paid_up') GROUP BY state"
    )).all()
    benefits = conn.execute(text(
        "SELECT benefit_type, count(*) FROM policy_benefits GROUP BY benefit_type")).all()
    roles = {r for (r,) in conn.execute(text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:r)"), {"r": list(ROLES)})}
    grants = {f"{role} på {table}": conn.execute(
        text("SELECT has_table_privilege(:r, CAST(:t AS regclass), 'SELECT')"), {"r": role, "t": table}).scalar_one()
        for role in sorted(roles) for table in present}
    conn.rollback()

result = {
    "read_at": datetime.now(UTC).isoformat(),
    "other_client_connections": others,
    "payout_tables_present": present,
    "legacy_states": {s: n for s, n in legacy},
    "benefits": {t: n for t, n in benefits},
    "agent_roles_found": sorted(roles),
    "agent_select_on_payout_tables": grants,
}
(OUT / "preflight.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
print("KLART: inga andra klientanslutningar" if not others else f"STOPP: {len(others)} andra klientanslutningar")
