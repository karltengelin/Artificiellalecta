"""Skrivskyddad kontroll i Lakebase efter uttagsdelarnas migration (paket B steg 1, B-047, B-048).

Kontrollerar med den betrodda anslutningen i en `READ ONLY`-transaktion:
- tabellerna `payout_parts` och `payout_part_states` och de två bytta villkoren;
- exakt uttagsdel 1 per ålderspensionsförmån, andel 1 och utan delningsfält, med ett öppet
  läge `not_started` från förmånens start – utan ekonomisk effekt;
- inga gamla uttagslägen i `policy_states` och inga nya ärenden;
- radantalen i övriga tabeller lika med backupens manifest (`--backup`);
- att en ny torrkörning av migrationen ger `already_applied`.

Med `--grants` prövas också agentrollerna med sina egna anslutningar (B-048):
`agent_forsakring` och `agent_aktuarie` läser båda tabellerna och nekas INSERT, UPDATE och
DELETE; `agent_compliance` nekas SELECT. Varje rollprov körs i en transaktion som rullas tillbaka.
Resultatet skrivs till huvudkatalogens `logs/simulation/paket-b-steg1/verify*.json`.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from common import OUT  # noqa: E402  (lägger också src/ på sökvägen)

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--backup", type=Path, required=True, help="Backupmappen (manifest.json) tagen före migrationen")
parser.add_argument("--grants", action="store_true", help="Pröva även agentrollernas anslutningar")
args = parser.parse_args()

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from services.db import AGENT_ROLES  # noqa: E402
from utils.db import make_engine  # noqa: E402
from utils.migration_payout_parts import TABLES, check_definitions, migrate_payout_parts, stale_checks  # noqa: E402

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail="") -> None:
    checks.append((name, bool(ok), str(detail)))


before = json.loads((args.backup / "manifest.json").read_text(encoding="utf-8"))["row_counts"]
engine = make_engine()
with engine.connect() as conn:
    conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    names = set(inspect(conn).get_table_names())
    check("tabellerna finns", set(TABLES) <= names, sorted(set(TABLES) & names))
    definitions = check_definitions(conn)
    check("villkoren har modellens värden", not stale_checks(definitions), definitions)
    q = lambda sql: conn.execute(text(sql)).scalar_one()  # noqa: E731
    benefits = q("SELECT count(*) FROM policy_benefits WHERE benefit_type = 'retirement_dc'")
    check("en del 1 per ålderspensionsförmån", q(
        "SELECT count(*) FROM payout_parts p JOIN policy_benefits b ON b.id = p.benefit_id "
        "WHERE p.part_number = 1 AND p.share_of_origin = 1 AND p.split_from_part_id IS NULL "
        "AND p.split_date IS NULL AND p.split_share IS NULL AND b.benefit_type = 'retirement_dc'") == benefits
        == q("SELECT count(*) FROM payout_parts") == q("SELECT count(DISTINCT benefit_id) FROM payout_parts"), benefits)
    check("ett öppet not_started från förmånens start per del", q(
        "SELECT count(*) FROM payout_part_states s JOIN payout_parts p ON p.id = s.payout_part_id "
        "JOIN policy_benefits b ON b.id = p.benefit_id WHERE s.state = 'not_started' AND s.valid_to IS NULL "
        "AND s.end_reason IS NULL AND s.valid_from = b.start_date") == benefits == q("SELECT count(*) FROM payout_part_states"))
    check("inga gamla uttagslägen", q(
        "SELECT count(*) FROM policy_states WHERE state NOT IN ('premium_paying', 'paid_up')") == 0)
    check("inga rekonstruktionsärenden", q("SELECT count(*) FROM cases WHERE case_type = 'payout_reconstruction'") == 0)
    after = {t: q(f'SELECT count(*) FROM "{t}"') for t in before}
    check("radantalen lika med backupen", after == before,
          {t: (before[t], after[t]) for t in before if before[t] != after[t]})
    conn.rollback()
check("ny torrkörning: already_applied", migrate_payout_parts(engine).already_applied)

roles = {}
if args.grants:
    from dotenv import load_dotenv

    load_dotenv()
    for team, (role, url_env) in AGENT_ROLES.items():
        url = os.environ.get(url_env)
        if not url:
            check(f"{role}: anslutning finns", False, f"{url_env} saknas")
            continue
        allowed = team in ("forsakring", "aktuarie")
        role_engine = create_engine(url)
        outcome = {}
        for table in TABLES:
            for verb, sql in (("SELECT", f"SELECT count(*) FROM {table}"),
                              ("UPDATE", f"UPDATE {table} SET updated_at = updated_at WHERE false"),
                              ("DELETE", f"DELETE FROM {table} WHERE false"),
                              ("INSERT", f"INSERT INTO {table} SELECT * FROM {table} WHERE false")):
                with role_engine.connect() as conn:
                    try:
                        value = conn.execute(text(sql))
                        outcome[f"{verb} {table}"] = value.scalar_one() if verb == "SELECT" else "tillåten"
                    except Exception as exc:  # noqa: BLE001 – nekad rättighet är väntat utfall
                        outcome[f"{verb} {table}"] = "nekad" if "permission denied" in str(exc) else f"fel: {exc}"
                    finally:
                        conn.rollback()
        if allowed:
            # Läsningarnas egen fråga med rollens rättigheter (aktuarien har bara id och policy_id på
            # policy_benefits); ingen operation anropas, så inga loggrader skrivs
            from sqlalchemy.orm import Session

            from services.payout_parts import parts_by_policy, summary_state

            with Session(role_engine) as session:
                ids = list(session.execute(text("SELECT id FROM policies")).scalars())
                found = parts_by_policy(session, ids)
                summary = {s: sum(summary_state(v) == s for v in found.values()) for s in ("not_started", "in_payout")}
                session.rollback()
            outcome["parts_by_policy"] = summary
            check(f"{role}: parts_by_policy läser alla försäkringar", summary["not_started"] == len(ids), summary)
        role_engine.dispose()
        roles[role] = outcome
        selects = [outcome[f"SELECT {t}"] for t in TABLES]
        writes = [outcome[f"{v} {t}"] for t in TABLES for v in ("UPDATE", "DELETE", "INSERT")]
        if allowed:
            check(f"{role} läser båda tabellerna", all(isinstance(s, int) for s in selects), selects)
        else:
            check(f"{role} nekas SELECT", all(s == "nekad" for s in selects), selects)
        check(f"{role} nekas skrivning", all(w == "nekad" for w in writes), writes)

result = {"checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks], "roles": roles}
(OUT / ("verify_grants.json" if args.grants else "verify.json")).write_text(
    json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
for name, ok, detail in checks:
    print(("OK   " if ok else "FEL  ") + name + ("" if ok else f" – {detail}"))
passed = sum(ok for _, ok, _ in checks)
print(f"{passed} av {len(checks)} kontroller")
raise SystemExit(0 if passed == len(checks) else 1)
