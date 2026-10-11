"""Körverktygen går att starta efter flytt utan att ansluta till externa system."""

import csv
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((ROOT / "scripts").rglob("*.py"))


def run_script(path, *args, cwd):
    env = dict(os.environ)
    env["DATABASE_URL"] = "not-a-database-url"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-B", str(path), *args], check=False, cwd=cwd, env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_help_works_from_another_directory_without_database(script, tmp_path):
    result = run_script(script, "--help", cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "usage:" in result.stdout


def test_mock_generation_and_csv_validation_from_moved_entrypoints(tmp_path):
    output = tmp_path / "mock"
    generated = run_script(
        ROOT / "scripts/demo/generate_mock_data.py", "--employers", "2", "--employees", "10",
        "--out-dir", str(output), cwd=tmp_path,
    )
    assert generated.returncode == 0, generated.stdout + generated.stderr
    with (output / "employers.csv").open(encoding="utf-8") as fh:
        employers = list(csv.DictReader(fh))
    with (output / "insured_persons.csv").open(encoding="utf-8") as fh:
        people = list(csv.DictReader(fh))
    assert len(employers) == 2
    assert people
    assert {row["employer_id"] for row in people} <= {row["id"] for row in employers}
    checked = run_script(
        ROOT / "scripts/demo/seed_mock_data.py", "--dry-run",
        "--employers-csv", str(output / "employers.csv"),
        "--insured-csv", str(output / "insured_persons.csv"), cwd=tmp_path,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr


def test_analysis_entrypoint_uses_shared_calculator(tmp_path):
    result = run_script(
        ROOT / "scripts/analysis/analyze_premium_impact.py", "--scenario-ibb", "85000", cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "syntetiska" in result.stdout
    assert "| Scenario minus omberäknad bas | 690,00 |" in result.stdout


def test_documentation_entrypoint_matches_generated_inventory(tmp_path):
    result = run_script(ROOT / "scripts/documentation/list_operations.py", "--check", cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
