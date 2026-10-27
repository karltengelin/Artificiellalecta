"""Pytest-markörer från samma katalog som körverktygets urval.

Postgres-proven körs bara efter ett aktivt val: RUN_POSTGRES_TESTS=1 i skalet eller
`run_tests.py --postgres`. Anslutningsadresserna i .env räcker inte (teststrategi.md).
"""

import os

import pytest

from testing.selection import ROOT, SelectionError, load_catalog, marker_matches

POSTGRES_OPT_IN = "RUN_POSTGRES_TESTS"
POSTGRES_SKIP = f"Postgres-prov körs bara med {POSTGRES_OPT_IN}=1 eller run_tests.py --postgres"


def postgres_enabled(environ=os.environ, root=ROOT) -> bool:
    """Det aktiva valet läses ur skalet; ett värde i .env vägras så att det inte blir standard."""
    env_file = root / ".env"
    if env_file.is_file():
        try:
            from dotenv import dotenv_values
        except ImportError:  # pragma: no cover
            dotenv_values = None
        if dotenv_values is not None and POSTGRES_OPT_IN in dotenv_values(env_file):
            raise pytest.UsageError(f"{POSTGRES_OPT_IN} hör inte hemma i .env – sätt den i skalet för en körning")
    return environ.get(POSTGRES_OPT_IN) == "1"


def pytest_configure(config):
    try:
        catalog = load_catalog()
    except SelectionError as exc:
        raise pytest.UsageError(str(exc)) from exc
    config._company_test_catalog = catalog
    config._company_run_postgres = postgres_enabled()
    for name, suite in catalog.suites.items():
        config.addinivalue_line("markers", f"suite_{name}: {suite.description} ({suite.status})")
    for name in catalog.markers:
        config.addinivalue_line("markers", f"{name}: testegenskap från tests/suites.toml")


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    catalog = config._company_test_catalog
    for item in items:
        path = item.path.resolve().relative_to(ROOT).as_posix()
        for name, suite in catalog.suites.items():
            if path in suite.tests:
                item.add_marker(getattr(pytest.mark, f"suite_{name}"))
        nodeid = path + ("::" + item.nodeid.split("::", 1)[1] if "::" in item.nodeid else "")
        for name, selectors in catalog.markers.items():
            if any(marker_matches(nodeid, selector) for selector in selectors):
                item.add_marker(getattr(pytest.mark, name))
                if name == "postgres" and not config._company_run_postgres:
                    item.add_marker(pytest.mark.skip(reason=POSTGRES_SKIP))
