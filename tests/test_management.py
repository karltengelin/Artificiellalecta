"""Oberoende facit för ledningsmått, originalförsök, miljöer och integritet."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select

from management.metrics import DEFINITIONS, observation
from management.telemetry import read_telemetry
from models import Base, InsuredPerson, Policy, PolicyBenefit, PremiumTransaction
from services import Actor, MemoryEventLog, OperationContext, ServiceLayer
from services.db import session_factory_for
from services.errors import InvalidInputError
from services.operations import common
from utils.demo_data import create_demo_database

TODAY = date(2026, 10, 27)
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


def test_metrics_reject_arbitrary_population_and_old_period(company):
    with pytest.raises(InvalidInputError):
        metric(company, "2024-01-01")
    with pytest.raises(InvalidInputError):
        company.execute("get_company_metrics", OperationContext(actor=Actor.human("karl")),
                        {"month": "2025-11-01", "personal_id_number": "198001010000"})


@pytest.fixture
def demo_company(monkeypatch):
    """Orört demobestånd, inklusive äldre kohort; ingen extern databas eller agentkörning."""
    monkeypatch.setattr(common, "today", lambda: TODAY)
    engine = create_engine("sqlite://")
    create_demo_database(engine, with_proposals=False, today=TODAY)
    factory = session_factory_for(engine)
    yield ServiceLayer(session_factory=factory, events=MemoryEventLog())
    engine.dispose()


@pytest.mark.parametrize("month, expected", [
    ("2025-11-01", "145971.41"),
    ("2025-12-01", "145971.41"),
    ("2026-08-01", "124541.34"),
    ("2026-09-01", "0.00"),
])
def test_demo_stock_has_fixed_contract_values(demo_company, month, expected):
    # Fast facit: 4 grundpersoner + 31 i kohorten, alla statusar räknas.
    # Beloppen har kontrollräknats separat ur löner, IBB, satser och åldersfönster,
    # inte hämtats från måttoperationen eller en SUM-fråga i testet.
    result = metric(demo_company, month)
    assert result.insured_count == 35 and not result.insured_suppressed
    assert result.paid_state == "available" and result.paid_sek == Decimal(expected)
    assert result.as_of_date == TODAY
    assert result.period_from == date.fromisoformat(month)
    assert result.read_at.utcoffset().total_seconds() == 0


@pytest.mark.parametrize("month", ["2025-11-01", "2026-10-01"])
def test_operation_accepts_both_ends_of_twelve_month_window(company, month):
    assert metric(company, month).period_from == date.fromisoformat(month)


@pytest.mark.parametrize("month", ["2025-10-01", "2026-11-01", "2026-09-02", "2026-13-01", "invalid"])
def test_operation_rejects_outside_window_and_non_month_inputs(company, month):
    with pytest.raises(InvalidInputError):
        metric(company, month)


def test_paid_date_controls_half_open_period_and_only_paid_rows_count(company, insurance_db):
    with insurance_db.session_factory() as s:
        for paid_date, amount, status in [
            (date(2025, 11, 1), "25", "paid"),
            (date(2025, 11, 30), "-10", "paid"),
            (date(2025, 12, 1), "300", "paid"),
            (date(2025, 11, 15), "9999", "invoiced"),
        ]:
            s.add(PremiumTransaction(
                benefit_id=insurance_db.ids.benefit, period_month=date(2025, 10, 1),
                transaction_type="adjustment", amount_sek=Decimal(amount), status=status, paid_date=paid_date,
            ))
    result = metric(company)
    assert result.paid_state == "available" and result.paid_sek == Decimal("10865.00")


@pytest.mark.parametrize("population", [1, 9])
def test_small_total_population_hides_count_and_even_empty_payment_cell(insurance_db, monkeypatch, population):
    monkeypatch.setattr(common, "today", lambda: TODAY)
    with insurance_db.session_factory() as s:
        for i in range(population - 1):
            s.add(InsuredPerson(
                personal_id_number=f"19800101{i:04d}", first_name="Test", last_name="Test",
                employer_id=insurance_db.ids.employer, employment_start_date=date(2020, 1, 1),
            ))
    service = ServiceLayer(session_factory=insurance_db.session_factory, events=MemoryEventLog())
    result = metric(service, "2026-10-01")
    assert result.insured_count is None and result.insured_suppressed
    assert result.paid_state == "suppressed" and result.paid_sek is None


def test_nine_distinct_payers_are_suppressed_despite_more_transaction_rows(company, insurance_db):
    with insurance_db.session_factory() as s:
        row = s.scalar(select(PremiumTransaction).where(PremiumTransaction.amount_sek == 100).limit(1))
        row.paid_date = date(2025, 12, 1)
    result = metric(company)
    assert result.insured_count == 10
    assert result.paid_state == "suppressed" and result.paid_sek is None


def test_readable_empty_database_has_available_zeros(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)
    engine = create_engine("sqlite://")
    try:
        Base.metadata.create_all(engine)
        service = ServiceLayer(session_factory=session_factory_for(engine), events=MemoryEventLog())
        result = metric(service)
        assert result.insured_count == 0 and not result.insured_suppressed
        assert result.paid_state == "available" and result.paid_sek == Decimal("0.00")
    finally:
        engine.dispose()


def test_net_zero_with_ten_payers_is_available_and_fee_without_date_is_excluded(company, insurance_db):
    with insurance_db.session_factory() as s:
        s.add(PremiumTransaction(
            benefit_id=insurance_db.ids.benefit, period_month=date(2025, 11, 1),
            transaction_type="adjustment", amount_sek=Decimal("-10850.00"),
            status="paid", paid_date=date(2025, 11, 20),
        ))
        fee = s.scalar(select(PremiumTransaction).where(PremiumTransaction.transaction_type == "fee").limit(1))
        fee.paid_date = None
    result = metric(company)
    assert result.paid_state == "available" and result.paid_sek == Decimal("0.00")


def test_failed_payment_control_takes_precedence_over_suppression(insurance_db, monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)
    with insurance_db.session_factory() as s:
        row = s.scalar(select(PremiumTransaction).where(PremiumTransaction.transaction_type == "premium").limit(1))
        row.paid_date = None
    service = ServiceLayer(session_factory=insurance_db.session_factory, events=MemoryEventLog())
    result = metric(service)
    assert result.insured_suppressed and result.insured_count is None
    assert result.paid_state == "failed" and result.paid_sek is None


def test_month_window_and_period_end_cross_year_boundary(company, monkeypatch):
    monkeypatch.setattr(common, "today", lambda: date(2027, 1, 15))
    assert metric(company, "2026-02-01").period_from == date(2026, 2, 1)
    assert metric(company, "2026-12-01").period_to == date(2027, 1, 1)
    assert metric(company, "2027-01-01").period_to == date(2027, 2, 1)
    with pytest.raises(InvalidInputError):
        metric(company, "2026-01-01")


@pytest.mark.parametrize("transaction_type", ["premium", "adjustment"])
@pytest.mark.parametrize("invalid_date", [None, date(2026, 10, 28)])
def test_bad_paid_date_fails_even_an_unrelated_empty_period(company, insurance_db, transaction_type, invalid_date):
    with insurance_db.session_factory() as s:
        row = s.scalar(select(PremiumTransaction).where(
            PremiumTransaction.transaction_type == transaction_type,
            PremiumTransaction.period_month == date(2025, 12, 1),
        ))
        row.paid_date = invalid_date
    result = metric(company, "2026-10-01")
    assert result.insured_count == 10 and not result.insured_suppressed
    assert result.paid_state == "failed" and result.paid_sek is None


def test_failed_source_is_not_a_successful_zero_or_automatic_demo_fallback(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)

    @contextmanager
    def unreadable_source():
        raise RuntimeError("test-source-unavailable")
        yield  # Förblir en kontexthanterare; ger aldrig någon session.

    service = ServiceLayer(session_factory=unreadable_source, events=MemoryEventLog())
    with pytest.raises(RuntimeError, match="test-source-unavailable"):
        metric(service)


def test_definitions_and_observations_keep_version_date_and_failure_states():
    assert {DEFINITIONS[key].definition_version for key in (
        "insured_registered_count", "premium_paid_recorded_sek",
    )} == {"1.0"}
    for state, quality, value in [
        ("available", "provisional", Decimal("0.00")),
        ("suppressed", "provisional", None),
        ("missing", "failed", None),
        ("missing", "unknown", None),
    ]:
        result = observation(
            "premium_paid_recorded_sek", environment_id="demo", dataset_ref="demo:contract-fixture",
            now=NOW, period=PERIOD, availability=state, quality=quality, value=value, note="Kontraktsprov",
        )
        assert result.availability == state and result.quality == quality and result.value == value
        assert result.period_from == PERIOD[0] and result.period_to == PERIOD[1]
        assert result.definition_version == "1.0"


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
