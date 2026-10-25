"""Databasvalet för handläggar-UI:t och demobeståndet (src/web/database.py, src/utils/demo_data.py)."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from models import ApprovalRequestRecord, InsuredPerson, PremiumTransaction
from services import ProductRuleCatalog
from services.db import session_factory_for
from services.operations import common
from skills.calculation.calculate_itp1_premium import is_in_age_window
from utils.demo_data import OLDER_COHORT, PERSONS, create_demo_database
from web.config import WebConfigError
from web.database import demo_engine, svc_test_engine

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 10, 12)
#: De fyra personerna och den äldre kohorten (B-035 val K)
DEMO_PERSONS = len(PERSONS) + len(OLDER_COHORT)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


def memory_engine():
    return create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})


def counts(engine):
    with session_factory_for(engine)() as s:
        return (
            s.scalar(select(func.count()).select_from(InsuredPerson)),
            s.scalar(select(func.count()).select_from(PremiumTransaction)),
            s.scalar(select(func.count()).select_from(ApprovalRequestRecord)),
        )


def test_demobestandet_har_personer_premier_och_tva_forslag():
    engine = memory_engine()
    create_demo_database(engine, today=TODAY)
    persons, premiums, proposals = counts(engine)
    assert (len(PERSONS), len(OLDER_COHORT), persons) == (4, 31, DEMO_PERSONS)
    # Kohorten: en premie per månad 2025-01–2026-09 i premieåldern (de äldsta har passerat 66)
    months = [date(2025 + i // 12, i % 12 + 1, 1) for i in range(21)]
    cohort = sum(is_in_age_window(p.birth_date, m) for p in OLDER_COHORT for m in months)
    assert 0 < cohort < 31 * 21
    assert premiums == 21 + 21 + 12 + 4 + cohort
    assert proposals == 2


def test_demobestandet_skapas_bara_i_en_tom_databas():
    engine = memory_engine()
    create_demo_database(engine, today=TODAY, with_proposals=False)
    with pytest.raises(RuntimeError, match="redan tabeller"):
        create_demo_database(engine, today=TODAY)


def test_demofilen_skapas_en_gang_och_ateranvands(tmp_path):
    path = tmp_path / "demo.db"
    first = demo_engine(path)
    assert path.exists()
    with session_factory_for(first)() as s:
        s.add(ApprovalRequestRecord(id="x" * 32, operation="get_insured_overview", input={},
                                    proposed_by="test", status="rejected"))
    first.dispose()
    second = demo_engine(path)  # befintlig fil: inget nytt bestånd, inga tabeller skapas om
    assert counts(second)[0] == DEMO_PERSONS
    with session_factory_for(second)() as s:
        assert s.get(ApprovalRequestRecord, "x" * 32) is not None
    second.dispose()


def test_ny_tabell_laggs_till_i_befintlig_demofil(tmp_path):
    """En demofil från före Fas 5 får tabellen cases; beståndet och kön är kvar."""
    from sqlalchemy import inspect

    path = tmp_path / "demo.db"
    first = demo_engine(path)
    with first.begin() as conn:
        conn.exec_driver_sql("DROP TABLE cases")
    first.dispose()
    second = demo_engine(path)
    assert "cases" in inspect(second).get_table_names()
    assert counts(second)[0] == DEMO_PERSONS
    second.dispose()


def test_svc_test_kraver_isolerad_databas(monkeypatch):
    monkeypatch.delenv("SERVICES_TEST_POSTGRES_URL", raising=False)
    with pytest.raises(WebConfigError, match="saknas"):
        svc_test_engine()
    monkeypatch.setenv("SERVICES_TEST_POSTGRES_URL", "postgresql://samma")
    monkeypatch.setenv("DATABASE_URL", "postgresql://samma")
    with pytest.raises(WebConfigError, match="beståndet"):
        svc_test_engine()


def test_regelns_rubrik_lases_ur_regelfilen():
    rules = ProductRuleCatalog(today=TODAY)
    assert rules.title("PR-ITP1-013") == "premieperioder, anställning och fribrev"
    assert rules.title("PR-ITP1-999") is None


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("database,port", [("lakebase", 8765), ("svc_test", 8766), ("demo", 8767)])
def test_startkommandot_valjer_miljons_port_och_respekterar_overstyrning(monkeypatch, database, port):
    from web import __main__ as entry
    from web.config import WebSettings

    monkeypatch.setattr(entry.WebSettings, "from_env", lambda: WebSettings())
    monkeypatch.setattr(entry, "create_app", lambda **kwargs: kwargs["settings"])
    calls = []
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs)))
    for extra, expected in [([], port), (["--port", "8899"], 8899)]:
        monkeypatch.setattr(sys, "argv", ["web", "--db", database, *extra])
        entry.main()
        assert calls[-1][0].database == database
        assert calls[-1][1]["port"] == expected
        assert calls[-1][1]["host"] == "127.0.0.1"


@pytest.mark.skipif(os.name != "nt", reason="Windows-genvägar")
def test_installationen_ersatter_vanliga_genvagen_med_lakebase_och_skapar_separat_demo(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("shortcut", ROOT / "scripts/web/install_desktop_shortcut.py")
    shortcut = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shortcut)
    scripts = []

    def ps(script, capture=False):
        if capture:
            return str(tmp_path)
        scripts.append(script)

    monkeypatch.setattr(shortcut, "_ps", ps)
    monkeypatch.setattr(shortcut, "brand_mark_ico", lambda: b"icon")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["install_desktop_shortcut.py"])
    shortcut.main()
    assert len(scripts) == 2
    assert "Artificiellalecta – handläggare.lnk" in scripts[0]
    assert "-Db lakebase -Port 8765" in scripts[0]
    assert "Artificiellalecta – handläggare (DEMO).lnk" in scripts[1]
    assert "-Db demo -Port 8767" in scripts[1]
    scripts.clear()
    monkeypatch.setattr(sys, "argv", ["install_desktop_shortcut.py", "--dry-run"])
    shortcut.main()
    assert not scripts


POWERSHELL = shutil.which("powershell")


@pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell krävs")
@pytest.mark.parametrize(
    "scenario,args,actual,expected_code,expected_url,spawns",
    [
        ("existing", [], "lakebase", 0, "http://127.0.0.1:8765/", 0),
        ("existing", ["-Db", "demo"], "demo", 0, "http://127.0.0.1:8767/", 0),
        ("existing", ["-Db", "svc_test"], "svc_test", 0, "http://127.0.0.1:8766/", 0),
        ("existing", ["-Db", "demo", "-Port", "8899"], "demo", 0, "http://127.0.0.1:8899/", 0),
        ("existing", [], "demo", 1, None, 0),
        ("unknown", [], "lakebase", 1, None, 0),
        ("occupied", [], "lakebase", 1, None, 0),
        ("start", [], "lakebase", 0, "http://127.0.0.1:8765/", 1),
        ("start", ["-Db", "demo"], "demo", 0, "http://127.0.0.1:8767/", 1),
        ("start", [], "demo", 1, None, 1),
        ("exited", [], "lakebase", 1, None, 1),
    ],
)
def test_genvagen_verifierar_databas_fore_oppning(
    tmp_path, scenario, args, actual, expected_code, expected_url, spawns,
):
    """Kör det riktiga PS5-skriptet med simulerade HTTP-, process- och popupanrop."""
    harness = tmp_path / "launcher-test.ps1"
    harness.write_text(r'''
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$script:probes = 0
function Invoke-RestMethod {
    param($Uri, $TimeoutSec)
    $script:probes++
    if ($env:UI_SCENARIO -in @('occupied', 'exited') -or
        ($env:UI_SCENARIO -eq 'start' -and $script:probes -eq 1)) { throw 'not ready' }
    $app = if ($env:UI_SCENARIO -eq 'unknown') { 'other-app' } else { 'artificiellalecta-handlaggare' }
    return [pscustomobject]@{ application = $app; database = $env:UI_DATABASE }
}
function Get-NetTCPConnection {
    param($LocalPort, $State, $ErrorAction)
    if ($env:UI_SCENARIO -eq 'occupied') { return [pscustomobject]@{ LocalPort = $LocalPort } }
}
function Test-Path { param($Path) return $true }
function New-Object {
    param($ComObject)
    $popup = [pscustomobject]@{}
    $popup | Add-Member ScriptMethod Popup { param($message) [Console]::WriteLine('ERROR ' + $message); return 0 }
    return $popup
}
function Start-Process {
    param([Parameter(Position=0)]$FilePath, $ArgumentList, $WorkingDirectory, $WindowStyle, [switch]$PassThru)
    if ($PassThru) {
        [Console]::WriteLine('SPAWN ' + ($ArgumentList -join ' ') + ' ' + $WindowStyle)
        return [pscustomobject]@{ HasExited = ($env:UI_SCENARIO -eq 'exited') }
    }
    [Console]::WriteLine('OPEN ' + $FilePath)
}
$launcherArgs = @{}
$parsedArgs = ConvertFrom-Json $env:UI_ARGS
foreach ($property in $parsedArgs.PSObject.Properties) { $launcherArgs[$property.Name] = $property.Value }
& $env:UI_LAUNCHER @launcherArgs
exit $LASTEXITCODE
''', encoding="utf-8-sig")
    named_args = {key.lstrip("-"): value for key, value in zip(args[::2], args[1::2])}
    env = dict(os.environ, UI_SCENARIO=scenario, UI_DATABASE=actual, UI_ARGS=json.dumps(named_args),
               UI_LAUNCHER=str(ROOT / "scripts/web/open_ui.ps1"))
    result = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
                            check=False, env=env, capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == expected_code, result.stdout + result.stderr
    assert result.stdout.count("SPAWN ") == spawns, result.stdout + result.stderr
    if expected_url:
        assert "OPEN " + expected_url in result.stdout
    else:
        assert "OPEN " not in result.stdout
        assert "ERROR " in result.stdout
    if spawns:
        assert "Hidden" in result.stdout
