"""Urvalet får varken tappa testfiler, beroenden eller ännu otestade målområden."""

import shutil
import subprocess
from dataclasses import replace
from types import SimpleNamespace

import pytest

from testing import cli, pytest_plugin
from testing.selection import (
    ROOT,
    SelectionError,
    changed_plan,
    expand_suites,
    full_plan,
    git_changes,
    load_catalog,
    marker_matches,
    relative_path,
    suite_plan,
    validate_catalog,
)


@pytest.fixture
def small(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    for name in ("a", "b"):
        (tests / f"test_{name}.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    (tests / "test_c.py").write_text("def test_local(): pass\ndef test_pg(): pass\n", encoding="utf-8")
    (tests / "suites.toml").write_text('''
version = 1
[suites.a]
description = "Kärna"
status = "active"
tests = ["tests/test_a.py"]
dependents = ["b"]
[suites.b]
description = "Användare av kärnan"
status = "partial"
tests = ["tests/test_b.py", "tests/test_c.py"]
dependents = []
[suites.future]
description = "Ännu obyggd motor"
status = "planned"
tests = []
dependents = []
[markers]
postgres = ["tests/test_c.py::test_pg"]
security = ["tests/test_a.py"]
[[rules]]
paths = ["src/a/**", "01_domän/**"]
suites = ["a"]
[[rules]]
paths = ["src/future/**"]
suites = ["future"]
[[rules]]
paths = ["tests/conftest.py", "pyproject.toml"]
full = true
[[rules]]
paths = ["README.md"]
documentation = true
''', encoding="utf-8")
    return tmp_path, load_catalog(tmp_path)


def test_repo_katalogen_klassificerar_alla_testfiler_och_markerar_malbilden():
    catalog = load_catalog()
    for name in ("pensions", "payments", "economy", "risk", "simulation", "orchestration", "compliance", "communication"):
        assert catalog.suites[name].status == "planned"
        assert not catalog.suites[name].tests
    assert catalog.suites["reporting"].status == "partial"
    assert set(full_plan(catalog).tests) == set(catalog.tests)


def test_rapportandring_valjer_bara_rapporttester():
    catalog = load_catalog()
    plan = changed_plan(catalog, ["src/reporting/template.py"])
    assert plan.suites == ("reporting",)
    assert plan.tests == tuple(sorted(catalog.suites["reporting"].tests))
    assert not plan.full


def test_premiemotorn_tar_med_indirekta_anvandare():
    plan = changed_plan(load_catalog(), ["src/skills/calculation/calculate_itp1_premium.py"])
    assert {"premiums", "services", "agents", "web", "insights", "data", "tooling"} <= set(plan.suites)
    assert "tests/test_services_write_ops.py" in plan.tests
    assert "tests/test_ai_openai_provider.py" not in plan.tests


def test_bestandsberakning_tar_med_operationen_och_dess_anvandare():
    plan = changed_plan(load_catalog(), ["src/analytics/parameter_impact.py"])
    assert {"insights", "services", "agents", "web", "tooling"} <= set(plan.suites)
    assert "tests/test_portfolio_impact.py" in plan.tests
    assert "tests/test_reporting_template.py" not in plan.tests


def test_andringsurvalet_utvidgas_transitivt_och_dedupliceras(small):
    _, catalog = small
    plan = changed_plan(catalog, ["src/a/core.py", "src/a/core.py", "tests/test_b.py"])
    assert plan.suites == ("a", "b")
    assert plan.tests == catalog.tests
    assert any("Efter beroenden: a, b" == r for r in plan.reasons)


def test_uttrycklig_grupp_kan_koras_med_eller_utan_beroenden(small):
    _, catalog = small
    assert suite_plan(catalog, ["a"]).tests == ("tests/test_a.py",)
    assert suite_plan(catalog, ["a"], dependents=True).tests == catalog.tests


def test_cykel_i_beroenden_ger_ett_andligt_urval(small):
    _, catalog = small
    suites = {**catalog.suites, "b": replace(catalog.suites["b"], dependents=("a",))}
    assert expand_suites(replace(catalog, suites=suites), {"a"}) == ("a", "b")


@pytest.mark.parametrize("path", ["src/ny_motor.py", "ny_konfiguration.json", "pyproject.toml", "tests/conftest.py"])
def test_okanda_och_gemensamma_andringar_valjer_hela_sviten(small, path):
    _, catalog = small
    plan = changed_plan(catalog, [path])
    assert plan.full and plan.tests == catalog.tests


def test_forklarande_dokumentation_ger_inget_testresultat(small):
    _, catalog = small
    plan = changed_plan(catalog, ["README.md"])
    assert not plan.tests and not plan.full


def test_produktregel_i_markdown_ar_systemindata(small):
    _, catalog = small
    assert changed_plan(catalog, ["01_domän/produktregler/regel.md"]).tests == catalog.tests


def test_andrad_testfil_valjs_direkt_utan_att_kora_hela_omradet(small):
    _, catalog = small
    assert changed_plan(catalog, ["tests/test_a.py"]).tests == ("tests/test_a.py",)


@pytest.mark.parametrize("paths", [["src/future/motor.py"], ["src/future/motor.py", "okand.json"]])
def test_framtida_motor_utan_tester_stoppar_aven_med_brett_urval(small, paths):
    _, catalog = small
    with pytest.raises(SelectionError, match="ännu utan tester"):
        changed_plan(catalog, paths)


def test_tom_framtida_grupp_kan_inte_godkannas(small):
    _, catalog = small
    with pytest.raises(SelectionError, match="ännu utan tester"):
        suite_plan(catalog, ["future"])
    with pytest.raises(SelectionError, match="Okänd testgrupp"):
        suite_plan(catalog, ["stavfel"])


def test_ny_testfil_kraver_klassificering(small):
    root, catalog = small
    (root / "tests/test_new.py").write_text("def test_new(): pass\n", encoding="utf-8")
    with pytest.raises(SelectionError, match="omappade tester"):
        validate_catalog(catalog, root)


def test_delade_testhjalpare_kraver_brett_urval(small):
    root, catalog = small
    (root / "tests/test_b.py").write_text("from tests.test_a import test_ok\n", encoding="utf-8")
    with pytest.raises(SelectionError, match="Delad testhjälpare"):
        validate_catalog(catalog, root)
    broad = changed_plan(load_catalog(), ["tests/test_agents_loop.py"])
    assert broad.full and "tests/test_web_cases.py" in broad.tests


def test_saknad_testfil_och_ogiltig_markorselektor_stoppar(small):
    root, catalog = small
    bad = replace(catalog, markers={"postgres": ("tests/test_c.py::test_gammalt_namn",)})
    with pytest.raises(SelectionError, match="okänt test"):
        validate_catalog(bad, root)
    (root / "tests/test_a.py").unlink()
    with pytest.raises(SelectionError, match="Saknad"):
        validate_catalog(catalog, root)


@pytest.mark.parametrize("path", ["../outside.py", "C:/outside.py", "/outside.py", ""])
def test_urvalet_accepterar_bara_reporelativa_vagar(path):
    with pytest.raises(SelectionError):
        relative_path(path)


def test_windowsvag_normaliseras():
    assert relative_path(r"src\a\core.py") == "src/a/core.py"


def test_markorer_foljer_testfall_aven_vid_parametrisering(small, monkeypatch, pytestconfig):
    root, catalog = small
    monkeypatch.setattr(pytest_plugin, "ROOT", root)
    pytestconfig.addinivalue_line("markers", "suite_b: testgrupp i den isolerade katalogen")
    local = SimpleNamespace(path=root / "tests/test_c.py", nodeid="tests/test_c.py::test_local", marks=[])
    remote = SimpleNamespace(path=root / "tests/test_c.py", nodeid="tests/test_c.py::test_pg[x]", marks=[])
    for item in (local, remote):
        item.add_marker = lambda marker, item=item: item.marks.append(marker.name)
    pytest_plugin.pytest_collection_modifyitems(SimpleNamespace(_company_test_catalog=catalog), [local, remote])
    assert local.marks == ["suite_b"]
    assert remote.marks == ["suite_b", "postgres"]
    assert not marker_matches("tests/test_c.py::test_pg_extra", "tests/test_c.py::test_pg")


def test_git_tar_med_committat_stageat_ostageat_nytt_och_omnamning(tmp_path):
    if not shutil.which("git"):
        pytest.skip("Git krävs för ändringsurval")
    root = tmp_path / "repo"
    root.mkdir()

    def git(*args):
        return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                               "-c", "core.autocrlf=false", *args], cwd=root, check=True,
                              capture_output=True).stdout.decode("utf-8").strip()

    git("init", "-q")
    (root / "first.py").write_text("start\n")
    (root / "old.py").write_text("old\n")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    (root / "first.py").write_text("committed\n")
    git("add", ".")
    git("commit", "-qm", "change")
    git("mv", "old.py", "moved.py")
    (root / "staged.py").write_text("staged\n")
    git("add", "staged.py")
    (root / "first.py").write_text("dirty\n")
    (root / "new.py").write_text("untracked\n")
    assert git_changes(root, base) == ["first.py", "moved.py", "new.py", "old.py", "staged.py"]
    with pytest.raises(SelectionError, match="Git-urvalet misslyckades"):
        git_changes(root, "missing-ref")
    with pytest.raises(SelectionError, match="Ogiltig Git-bas"):
        git_changes(root, "--output=oops")


def test_cli_visar_plan_utan_att_kora_och_nekar_otestat_omrade(small, monkeypatch, capsys):
    _, catalog = small
    monkeypatch.setattr(cli, "load_catalog", lambda: catalog)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: pytest.fail("Inget ska köras"))
    assert cli.main(["--suite", "a"]) == 0
    assert "inga tester körda" in capsys.readouterr().out
    assert cli.main(["--suite", "future", "--run"]) == 2
    assert "ännu utan tester" in capsys.readouterr().err


def test_cli_lokal_korning_stanger_postgres_och_bevarar_pytests_felkod(small, monkeypatch):
    _, catalog = small
    monkeypatch.setattr(cli, "load_catalog", lambda: catalog)
    monkeypatch.setenv("SERVICES_TEST_POSTGRES_URL", "configured-but-not-used")
    monkeypatch.setenv("SERVICES_TEST_AGENT_POSTGRES_URL", "configured-but-not-used")
    recorded = []

    def run(command, **kwargs):
        recorded.append((command, kwargs))
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(cli.subprocess, "run", run)
    assert cli.main(["--all", "--run"]) == 1
    command, kwargs = recorded[0]
    assert command[-2:] == ["-m", "not postgres"]
    assert not kwargs["env"]["SERVICES_TEST_POSTGRES_URL"]
    assert not kwargs["env"]["SERVICES_TEST_AGENT_POSTGRES_URL"]
    assert kwargs["cwd"] == ROOT
