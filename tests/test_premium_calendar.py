"""Paket C – månadsprov från lokalt startbestånd till bank, återleverans och förfall."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (
    BankEvent,
    Case,
    Invoice,
    OperationEventRecord,
    PremiumTransaction,
    SalaryReport,
)
from services import (
    AccessDeniedError,
    Actor,
    OperationContext,
    ProductRuleCatalog,
    ServiceLayer,
)
from services.db import session_factory_for
from services.operations.common import business_day, today
from simulation import premium_calendar as cal
from simulation.premium_opening import DB, OPENING, digest
from simulation.premium_verification import verify

REVIEWER = Actor.human("test:handläggare")


def waiting(root, scenario):
    ident = cal.start(root, scenario)
    state = cal.advance(root, ident)
    assert state["status"] == "waiting_review"
    assert state["review"]["summary"]["valid"] == 2
    assert cal.status(root, ident)["review"] == state["review"]
    return state


def decide(root, state, verdict="approve", actor=REVIEWER, **options):
    return cal.advance(root, state["id"], revision=state["cursor"],
                       decision=(actor, verdict, state["review"]["review_digest"], "Kontrollerade provrader"), **options)


@pytest.mark.parametrize("scenario", cal.SCENARIOS)
def test_two_runs_match_frozen_month_and_followup(tmp_path, scenario, monkeypatch):
    attempts = []
    for _ in range(2):
        state = waiting(tmp_path, scenario)
        result = decide(tmp_path, state)
        assert result["status"] == "completed", result["reports"]
        november, december = result["reports"].values()
        assert november["failures"] == december["failures"] == []
        assert result["manifest"]["opening"]["sha256"] == digest(tmp_path / OPENING / DB)
        assert len([entry for entry in result["journal"] if entry["step"] == "monitor"]) == 34
        attempts.append([november["hash"], december["hash"]])
        if scenario == "duplicate":
            duplicate = result["bank_receipts"][1]
            assert duplicate["already_received"] == 1 and duplicate["new_events"] == 0
        if scenario == "partial":
            altered = deepcopy(november["observed"])
            altered["rows"][0]["allocated"] = "1203.02"
            assert any("AL-000001 allocated" in fail for fail in verify(altered, scenario))
            with monkeypatch.context() as patch:
                first_cent_wrong = list(cal.FACIT[scenario])
                first_cent_wrong[1] = "1203.02"
                patch.setitem(cal.FACIT, scenario, first_cent_wrong)
                assert any("AL-000001 allocated" in f for f in verify(november["observed"], scenario))
    assert attempts[0] == attempts[1]


def test_review_guards_and_rejection(tmp_path):
    state = waiting(tmp_path, "full")
    ident = state["id"]
    with pytest.raises(ValueError, match="handläggarbeslut"):
        decide(tmp_path, state, actor=Actor.agent("test"))
    with pytest.raises(ValueError, match="ändrats"):
        cal.advance(tmp_path, ident, revision=1, decision=(REVIEWER, "approve", "0" * 64, "Stale"))
    with cal.run_connection(tmp_path, ident) as (conn, _), Session(conn) as session:
        assert all(session.scalar(select(func.count()).select_from(m)) == 0 for m in
                   (SalaryReport, PremiumTransaction, Invoice, BankEvent))
        service = ServiceLayer(session_factory=session_factory_for(conn), rules=ProductRuleCatalog(today=cal.ISSUE))
        with pytest.raises(AccessDeniedError):
            service.execute("approve_salary_file", OperationContext(actor=Actor.agent("test"), reason="Prov"),
                            {"employer_org_number": cal.EMPLOYER, "file_reference": state["review"]["file_reference"],
                             "expected_digest": state["review"]["review_digest"]})
    result = decide(tmp_path, state, verdict="reject")
    assert result["status"] == "rejected"
    assert result["reports"]["decision"]["failures"] == []
    with pytest.raises(ValueError, match="äldre"):
        decide(tmp_path, state)


def test_concurrent_decisions_and_rollback_before_receipt(tmp_path, monkeypatch):
    state = waiting(tmp_path, "duplicate")
    ident = state["id"]
    with ThreadPoolExecutor(2) as pool:
        jobs = [pool.submit(decide, tmp_path, state, one=True) for _ in range(2)]
    assert sum(job.exception() is None for job in jobs) == 1
    assert sum(isinstance(job.exception(), ValueError) for job in jobs) == 1
    while True:
        before = cal.status(tmp_path, ident)
        if before["manifest"]["steps"][before["cursor"]][1] == "bank":
            break
        cal.advance(tmp_path, ident, one=True)
    original = cal._execute

    def interrupted(*args):
        original(*args)
        raise RuntimeError("Avbrott före kvittens")

    with monkeypatch.context() as patch:
        patch.setattr(cal, "_execute", interrupted)
        with pytest.raises(RuntimeError, match="Avbrott"):
            cal.advance(tmp_path, ident, one=True)
    with cal.run_connection(tmp_path, ident) as (conn, recovered), Session(conn) as session:
        assert recovered["cursor"] == before["cursor"]
        assert session.scalar(select(func.count()).select_from(BankEvent)) == 0
    result = cal.advance(tmp_path, ident)
    assert result["status"] == "completed"
    with cal.run_connection(tmp_path, ident) as (conn, _), Session(conn) as session:
        assert session.scalar(select(func.count()).select_from(BankEvent)) == 1
        events = session.scalars(select(OperationEventRecord).where(OperationEventRecord.operation == "import_bank_file")).all()
        assert len(events) == 2 and all(e.run_id.startswith(ident + "/") for e in events)
        assert session.scalar(select(func.count()).select_from(Case)) == 0


def test_business_days_are_local_to_each_call():
    barrier = Barrier(2)

    def read(day):
        with business_day(day):
            barrier.wait(timeout=5)
            return today()
    days = [date(2026, 11, 25), date(2026, 12, 29)]
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(read, days)) == days
    assert today() == date.today()


def test_rejects_changed_opening_and_foreign_database(tmp_path):
    state = waiting(tmp_path, "full")
    opening = tmp_path / OPENING / DB
    with opening.open("ab") as f:
        f.write(b"changed")
    with pytest.raises(ValueError, match="Startbild"):
        cal.advance(tmp_path, state["id"])
    with pytest.raises(ValueError, match="kontrollsumma"):
        cal.start(tmp_path, "full")
    with pytest.raises(ValueError):
        cal.advance(tmp_path, "postgresql://shared")


def test_unknown_domain_outcome_stops_calendar(tmp_path):
    state = waiting(tmp_path, "duplicate")
    ident = state["id"]
    state = decide(tmp_path, state, one=True)
    while "bank_receipts" not in state:
        state = cal.advance(tmp_path, ident, one=True)
    # En avsiktligt motstridig bankpost prövar återstartens avstämningsstopp.
    with cal.run_connection(tmp_path, ident, write=True) as (conn, _):
        conn.exec_driver_sql("UPDATE bank_events SET amount_sek = amount_sek + 1")
    with pytest.raises(ValueError, match="manuell avstämning"):
        cal.advance(tmp_path, ident)
    assert cal.status(tmp_path, ident)["cursor"] == state["cursor"]


def test_cli_publishes_reports_and_can_rebuild_them(tmp_path, monkeypatch, capsys):
    import json
    import sys

    from scripts.simulation import premium_calendar as cli

    monkeypatch.setattr(cli, "RUNS", tmp_path)
    monkeypatch.setattr(cli, "os_user", lambda: REVIEWER.id)
    monkeypatch.setattr(sys, "argv", ["premium_calendar.py", "start", "partial"])
    assert cli.main() == 0
    ident = capsys.readouterr().out.split()[0]
    state = cal.status(tmp_path, ident)
    monkeypatch.setattr(sys, "argv", ["premium_calendar.py", "approve", ident, "--revision", "1",
                                      "--digest", state["review"]["review_digest"], "--note", "Verifieringsprov"])
    assert cli.main() == 0
    directory = tmp_path / ident
    report = directory / "2026-11-30.md"
    november = report.read_bytes()
    assert "2 733,13" in november.decode("utf-8")
    assert "payment_overdue" in (directory / "2026-12-29.md").read_text(encoding="utf-8")
    assert "facit" not in json.loads((directory / "bank.json").read_text(encoding="utf-8"))
    assert (directory / "bank.facit.json").is_file()
    report.unlink()
    monkeypatch.setattr(sys, "argv", ["premium_calendar.py", "status", ident])
    assert cli.main() == 0 and report.read_bytes() == november
