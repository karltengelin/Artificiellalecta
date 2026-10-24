"""Ger ett agentteams begränsade databasroll sina rättigheter (harness.md §5.1).

Rollen skapas av operatören i Databricks (inloggning med lösenord, ingen superuser,
inga medlemskap). Skriptet ansluter med DATABASE_URL (app_backend, tabellernas ägare)
och ger exakt rättigheterna i src/utils/agent_roles.py: SELECT på försäkringstabellerna,
INSERT på godkännandekön och händelseloggen (plus SELECT på deras tidsstämpelkolumner,
som INSERT … RETURNING kräver), ingenting annat.

Standard är torrkörning: förkontroller, nuvarande rättigheter och SQL som skulle köras.
Inget ändras utan --apply. Ändrar databasens rättigheter – samordna enligt AGENTS.md §4.5.

Användning (från repo-roten, i .venv):
    python scripts/setup/grant_agent_role.py                 # torrkörning, team forsakring
    python scripts/setup/grant_agent_role.py --apply         # kör GRANT i en transaktion
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from utils.agent_roles import (
    ROLE_GRANTS,
    current_column_privileges,
    current_privileges,
    inspect_role,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--team", default="forsakring", choices=sorted(ROLE_GRANTS))
    parser.add_argument("--schema", default="public")
    parser.add_argument("--apply", action="store_true", help="Kör GRANT (annars bara torrkörning)")
    args = parser.parse_args()

    from utils.db import make_engine

    grants = ROLE_GRANTS[args.team]
    engine = make_engine()
    with engine.connect() as conn:
        print(f"Ansluten som {conn.exec_driver_sql('SELECT current_user').scalar_one()}, roll: {grants.role}")
        problems = inspect_role(conn, grants, args.schema)
        print(f"Nuvarande rättigheter: {current_privileges(conn, grants.role, args.schema) or '(inga)'}")
    if problems:
        print("Stoppar – förkontrollen hittade problem:")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)

    statements = grants.statements(args.schema)
    print("SQL:" if args.apply else "SQL som skulle köras (torrkörning):")
    for statement in statements:
        print(f"  {statement};")
    if not args.apply:
        print("Inget ändrat. Kör med --apply för att verkställa.")
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.exec_driver_sql(statement)
    with engine.connect() as conn:
        print(f"Rättigheter efter: {current_privileges(conn, grants.role, args.schema)}")
        print(f"Kolumnrättigheter: {current_column_privileges(conn, grants.role, args.schema)}")


if __name__ == "__main__":
    main()
