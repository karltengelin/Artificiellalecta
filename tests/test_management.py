"""Oberoende facit för ledningsmått, originalförsök, miljöer och integritet."""

import json
import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from management.telemetry import read_telemetry
from models import InsuredPerson, Policy, PolicyBenefit, PremiumTransaction
from services import Actor, MemoryEventLog, OperationContext, ServiceLayer
from services.errors import AccessDeniedError, InvalidInputError
from services.operations import common

TODAY = date(2026, 10, 26)
NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)
PERIOD = (date(2026, 10, 1), date(2026, 11, 1))


@pytest.fixture
def company(insurance_db, monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)
    with insurance_db.session_factory() as s:
        for i in range(9):
            person = InsuredPerson(personal_id_number=f"19800101{i:04d}", first_name="Hemligt namn", last_name="Test",
                                   employer_id=insurance_db.ids.employer, employment_start_date=date(2020, 1, 1))
            s.add(person); s.flush()
            policy = Policy(policy_number=f"AL-{i + 20:06d}", insured_person_id=person.id,
                            signed_date=date(2020, 1, 1), start_date=date(2020, 1, 1))
            s.add(policy); s.flush()
            benefit = PolicyBenefit(policy_id=policy.id, benefit_type="retirement_dc", start_date=date(2020, 1, 1))
            s.add(benefit); s.flush()
            s.add(PremiumTransaction(benefit_id=benefit.id, period_month=date(2025, 11, 1),
                                     amount_sek=Decimal(100), status="paid", paid_date=date(2025, 11, 3)))
        s.add(PremiumTransaction(benefit_id=insurance_db.ids.benefit, period_month=date(2025, 11, 1),
                                 transaction_type="adjustment", amount_sek=Decimal(-50), status="paid", paid_date=date(2025, 11, 4)))
        s.add(PremiumTransaction(benefit_id=insurance_db.ids.benefit, period_month=date(2025, 11, 1),
                                 transaction_type="fee", amount_sek=Decimal(-200), status="paid", paid_date=date(2025, 11, 4)))
        s.commit()
    return ServiceLayer(session_factory=insurance_db.session_factory, events=MemoryEventLog())


def metric(service, month="2025-11-01"):
    return service.execute("get_company_metrics", OperationContext(actor=Actor.human("karl")), {"month": month}).output


def test_company_metrics_counts_unique_people_and_signed_adjustments_excluding_fees(company):
    result = metric(company)
    assert result.insured_count == 10
    assert result.paid_sek == Decimal("10850.00")
    assert result.period_to == date(2025, 12, 1)
    assert "Hemligt namn" not in result.model_dump_json()


def test_small_cells_missing_paid_date_and_complete_zero_are_distinct(company, insurance_db):
    assert metric(company, "2025-12-01").paid_state == "suppressed"
    assert metric(company, "2026-10-01").paid_sek == 0
    with insurance_db.session_factory() as s:
        row = s.scalar(select(PremiumTransaction).where(
            PremiumTransaction.status == "paid", PremiumTransaction.transaction_type == "premium"))
        row.paid_date = None
        s.commit()
    result = metric(company)
    assert result.paid_state == "failed" and result.paid_sek is None


def test_metrics_do_not_open_an_agent_tool_or_arbitrary_population(company):
    with pytest.raises(AccessDeniedError):
        company.execute("get_company_metrics", OperationContext(actor=Actor.agent("test")), {"month": "2025-11-01"})
    with pytest.raises(InvalidInputError):
        metric(company, "2024-01-01")
    with pytest.raises(InvalidInputError):
        company.execute("get_company_metrics", OperationContext(actor=Actor.human("karl")),
                        {"month": "2025-11-01", "personal_id_number": "198001010000"})


def manifest(tmp_path, *, allocated=True, sources=None):
    source = {"source_id": "fixture", "path": "calls.jsonl", "kind": "calls"}
    if allocated: source.update(environment_id="demo", dataset_ref="demo:current")
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"schema_version": 1, "sources": sources or [source]}), encoding="utf-8")
    return path


def calls(tmp_path, costs, *, path="calls.jsonl"):
    rows = [{"timestamp": "2026-10-25T10:00:00Z", "outcome": "error" if i == 1 else "ok",
                 "run_id": f"run{i}", "team": "compliance", "model_ref": "fake:fixture", "cost_usd": cost,
                 "content": {"prompt": "PERSONUPPGIFT"}, "error_message": "hemlig anslutning"}
            for i, cost in enumerate(costs)]
    (tmp_path / path).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return rows


def telemetry(path, **kwargs):
    return read_telemetry(path, environment_id="demo", dataset_ref="demo:current", period=PERIOD,
                          known_models={"fake:fixture"}, now=kwargs.pop("now", NOW), **kwargs)


def test_cost_original_attempts_are_idempotent_and_unknown_is_not_free(tmp_path):
    calls(tmp_path, ["0.10", "0.02", "0.03", "0.04", "0.05", None])
    path = manifest(tmp_path)
    for _ in range(2):
        result = telemetry(path)
        assert result.known == Decimal("0.24") and result.unknown == 1 and result.attempts == 6
        assert result.coverage == "partial"
    with sqlite3.connect(tmp_path / "operator_index.db") as db:
        stored = "".join(r[0] for r in db.execute("SELECT data FROM entries"))
    assert "PERSONUPPGIFT" not in stored and "hemlig anslutning" not in stored


def test_identical_real_attempts_survive_but_declared_file_copies_do_not_double_count(tmp_path):
    rows = calls(tmp_path, ["0.10", "0.10"])
    rows[1] = rows[0]
    raw = "".join(json.dumps(r) + "\n" for r in rows)
    (tmp_path / "calls.jsonl").write_text(raw, encoding="utf-8")
    (tmp_path / "copy.jsonl").write_text(raw, encoding="utf-8")
    src = {"source_id": "original", "path": "calls.jsonl", "kind": "calls", "environment_id": "demo", "dataset_ref": "demo:current"}
    path = manifest(tmp_path, sources=[src, {**src, "path": "copy.jsonl"}])
    assert telemetry(path).known == Decimal("0.20")


def test_modified_original_is_quarantined_across_imports(tmp_path):
    calls(tmp_path, ["0.10"])
    path = manifest(tmp_path)
    assert telemetry(path).known == Decimal("0.10")
    calls(tmp_path, ["0.90"])
    result = telemetry(path)
    assert result.known is None and any("karantän" in issue for issue in result.issues)


def test_unallocated_other_environment_and_missing_file_are_not_zero(tmp_path):
    calls(tmp_path, ["0.10", None])
    result = telemetry(manifest(tmp_path, allocated=False))
    assert result.known is None and result.unallocated_known == Decimal("0.10")
    path = manifest(tmp_path, sources=[{"source_id": "other", "path": "calls.jsonl", "kind": "calls",
                                          "environment_id": "lakebase", "dataset_ref": "lakebase:current"}])
    assert telemetry(path).known is None
    (tmp_path / "calls.jsonl").unlink()
    result = telemetry(path)
    assert result.known is None and result.issues


def test_journal_cumulative_cost_is_not_added_and_task_text_never_reaches_projection(tmp_path):
    calls(tmp_path, ["0.10", "0.02", "0.03", "0.04", "0.05"])
    journal = [
        {"schema_version": 1, "event_id": "j1", "seq": 1, "type": "run_started", "timestamp": "2026-10-25T10:00:00Z",
         "run_id": "run0", "root_run_id": "run0", "team": "compliance", "task_id": "PERSONUPPGIFT"},
        {"schema_version": 1, "event_id": "j2", "seq": 2, "type": "run_ended", "timestamp": "2026-10-25T10:01:00Z",
         "run_id": "run0", "root_run_id": "run0", "team": "compliance", "status": "waiting_approval",
         "usage": {"cost_usd": "0.24"}, "root_usage": {"cost_usd": "999.00"}},
    ]
    (tmp_path / "journal.jsonl").write_text("".join(json.dumps(row) + "\n" for row in journal), encoding="utf-8")
    sources = [{"source_id": "calls", "path": "calls.jsonl", "kind": "calls", "environment_id": "demo", "dataset_ref": "demo:current"},
               {"source_id": "journal", "path": "journal.jsonl", "kind": "journal", "environment_id": "demo", "dataset_ref": "demo:current"}]
    result = telemetry(manifest(tmp_path, sources=sources))
    assert result.known == Decimal("0.24")
    assert result.runs["compliance"] == {"Väntar på godkännande": 1}
    assert any(row.task.startswith("UPP-") for row in result.rows)
    assert "PERSONUPPGIFT" not in str(result)


def test_empty_source_is_unknown_and_missing_old_source_becomes_stale(tmp_path):
    (tmp_path / "calls.jsonl").write_text("", encoding="utf-8")
    path = manifest(tmp_path)
    assert telemetry(path).known is None
    calls(tmp_path, ["0.10"])
    assert telemetry(path).freshness == "fresh"
    (tmp_path / "calls.jsonl").unlink()
    result = telemetry(path, now=datetime(2026, 10, 26, 12, 16, tzinfo=UTC))
    assert result.known == Decimal("0.10") and result.freshness == "stale"


def test_source_scope_cannot_change_silently_between_imports(tmp_path):
    calls(tmp_path, ["0.10"])
    path = manifest(tmp_path)
    assert telemetry(path).known == Decimal("0.10")
    manifest(tmp_path, allocated=False)
    result = telemetry(path)
    assert result.known is None and result.unallocated_known is None
    assert any("karantän" in issue for issue in result.issues)


def test_corrupt_row_unsafe_path_and_wrong_schema_are_visible_gaps(tmp_path):
    calls(tmp_path, ["0.10"])
    with (tmp_path / "calls.jsonl").open("a", encoding="utf-8") as file: file.write('{"broken"\n')
    result = telemetry(manifest(tmp_path))
    assert result.known == Decimal("0.10") and result.issues
    path = manifest(tmp_path, sources=[{"source_id": "outside", "path": "../outside.jsonl", "kind": "calls"}])
    assert telemetry(path).issues
    path.write_text('{"schema_version": 2, "sources": []}', encoding="utf-8")
    assert telemetry(path).known is None
