"""Visa och kör avgränsade tester, lokalt som standard."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from testing.selection import (
    ROOT,
    SelectionError,
    changed_plan,
    env_file,
    full_plan,
    git_changes,
    load_catalog,
    suite_plan,
)
from testing.pytest_plugin import POSTGRES_OPT_IN

POSTGRES_ENV = (
    "SERVICES_TEST_POSTGRES_URL",
    "SERVICES_TEST_AGENT_POSTGRES_URL",
    "SERVICES_TEST_AKTUARIE_POSTGRES_URL",
    "SERVICES_TEST_COMPLIANCE_POSTGRES_URL",
)
# Rollproven och de anslutningar som räcker för dem (teamroll eller den gemensamma agentrollen).
ROLE_ENV = {
    "tests/test_agents_postgres_role.py": ("SERVICES_TEST_AGENT_POSTGRES_URL",),
    "tests/test_agents_postgres_aktuarie.py": ("SERVICES_TEST_AKTUARIE_POSTGRES_URL", "SERVICES_TEST_AGENT_POSTGRES_URL"),
    "tests/test_agents_postgres_compliance.py": ("SERVICES_TEST_COMPLIANCE_POSTGRES_URL",
                                                 "SERVICES_TEST_AGENT_POSTGRES_URL"),
}


POSTGRES_WARNING = ("Obs: ändringen berör Postgres-prov som inte körs lokalt. "
                    "Kör med --postgres innan ändringen levereras (teststrategi.md, Miljöer).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--list", action="store_true", help="Visa grupper och ännu otestade områden")
    modes.add_argument("--check", action="store_true", help="Kontrollera att alla testfiler är klassificerade")
    modes.add_argument("--suite", action="append", help="Välj grupp; kan upprepas")
    modes.add_argument("--all", action="store_true", help="Hela den befintliga sviten")
    modes.add_argument("--changed", action="store_true", help="Välj efter Git-ändringar och beroenden")
    parser.add_argument("--base", default="origin/main", help="Bas för --changed (ingen fetch görs)")
    parser.add_argument("--dependents", action="store_true", help="Ta med beroenden även vid --suite")
    parser.add_argument("--run", action="store_true", help="Kör valt urval; annars visas bara planen")
    parser.add_argument("--postgres", action="store_true", help="Tillåt prov mot konfigurerad isolerad Postgres")
    args = parser.parse_args(argv)
    if args.dependents and not args.suite:
        parser.error("--dependents används med --suite; --changed tar alltid med beroenden")
    if (args.run or args.postgres) and (args.list or args.check):
        parser.error("--list/--check kör inga tester och kan inte kombineras med --run/--postgres")
    try:
        catalog = load_catalog()
        if args.list:
            for name, suite in catalog.suites.items():
                state = "ännu utan tester" if suite.status == "planned" else suite.status
                print(f"{name:16} {state:18} {len(suite.tests):2} filer  {suite.description}")
            return 0
        if args.check:
            print(f"OK: {len(catalog.tests)} testfiler klassificerade; markörer och beroenden giltiga.")
            return 0
        if args.all:
            plan = full_plan(catalog)
        elif args.suite:
            plan = suite_plan(catalog, args.suite, dependents=args.dependents)
        else:
            paths = git_changes(ROOT, args.base)
            plan = changed_plan(catalog, paths)
            print(f"Git-bas: {args.base}; {len(paths)} ändrade sökvägar (inklusive arbetskopian).")
        print("Urval: " + ("hela befintliga sviten" if plan.full else ", ".join(plan.suites) or "direkta testfiler/dokumentation"))
        for reason in plan.reasons:
            print("  " + reason)
        print(f"Valda testfiler: {len(plan.tests)}")
        for path in plan.tests:
            print("  " + path)
        print("Miljö: " + ("Postgres tillåten; befintliga anslutningskontroller gäller" if args.postgres
                            else "lokalt; Postgres-proven är bortvalda"))
        if plan.postgres:
            print(f"Postgres-prov som ändringen berör: {len(plan.postgres)}")
            for selector in plan.postgres:
                print("  " + selector)
            if not args.postgres:
                print(POSTGRES_WARNING)
        planned = [name for name, suite in catalog.suites.items() if suite.status == "planned"]
        print("Målområden ännu utan tester: " + ", ".join(planned))
        if not plan.tests:
            print("Inga tester valda eller körda. Detta är inget godkänt testresultat.")
            return 0
        if not args.run:
            print("Planering klar; inga tester körda. Lägg till --run för att köra.")
            return 0
        env = dict(os.environ)
        tests = set(plan.tests)
        if not args.postgres:
            # Tomma värden hindrar också load_dotenv(override=False) från att återaktivera testerna.
            env.update(dict.fromkeys((*POSTGRES_ENV, POSTGRES_OPT_IN), ""))
        else:
            from dotenv import dotenv_values
            found = env_file(ROOT)
            values = dotenv_values(found) if found else {}
            env = {**{k: v for k, v in values.items() if v is not None}, **env}
            env[POSTGRES_OPT_IN] = "1"
            # De berörda Postgres-proven körs även om deras fil inte ingår i de valda grupperna.
            tests |= {selector.split("::")[0] for selector in plan.postgres}
            if not env.get("SERVICES_TEST_POSTGRES_URL"):
                raise SelectionError("--postgres kräver SERVICES_TEST_POSTGRES_URL till en isolerad testdatabas")
            for path, names in ROLE_ENV.items():
                if path in tests and not any(env.get(name) for name in names):
                    raise SelectionError(f"Rollproven i {path} kräver också {' eller '.join(names)}")
        command = [sys.executable, "-m", "pytest", "-q", "-ra", *sorted(tests)]
        if not args.postgres:
            command += ["-m", "not postgres"]
        sys.stdout.flush()
        code = subprocess.run(command, cwd=ROOT, env=env, check=False).returncode
        if plan.postgres and not args.postgres:
            print(POSTGRES_WARNING)
        return code
    except SelectionError as exc:
        print(f"Testurval stoppat: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
