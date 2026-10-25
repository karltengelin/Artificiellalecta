"""Pytest-markörer från samma katalog som körverktygets urval."""

import pytest

from testing.selection import ROOT, SelectionError, load_catalog, marker_matches


def pytest_configure(config):
    try:
        catalog = load_catalog()
    except SelectionError as exc:
        raise pytest.UsageError(str(exc)) from exc
    config._company_test_catalog = catalog
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
