"""Ekonomisk bevaring, jämförbarhet och offline-underlag för BI v1."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
import json

import pytest

from analytics.premium_impact import PremiumObservation, compare_ibb, render_markdown
from analytics.snapshot import load_snapshot

MONTH = date(2026, 6, 1)


def observation(**changes):
    return replace(PremiumObservation("tx-1", "person-1", "employer-1", "policy-1", "benefit-1", MONTH,
                                      Decimal("80000"), Decimal("10708.13"), date(1990, 1, 1)), **changes)


def compare(rows, **changes):
    return compare_ibb(rows, month=MONTH, baseline_ibb=Decimal("83400"),
                       scenario_ibb=changes.get("scenario_ibb", Decimal("85000")))


def test_hand_calculated_threshold_effect_and_reconciliation():
    report = compare([observation(), observation(transaction_id="tx-2", person_ref="person-2", benefit_ref="benefit-2",
                                                salary=Decimal("35000"), recorded_amount=Decimal("1575"))])
    # Brytpunkt +1 000: 30 %-premie ersätts av 4,5 %, skillnad −255 kr.
    assert report.baseline == Decimal("12283.13")
    assert report.difference == Decimal("-255.00")
    assert report.affected_people == 1
    assert report.reconciliation_difference == 0
    assert sum(s.difference for s in report.by_age) == report.difference
    assert sum(s.difference for s in report.by_employer) == report.difference


def test_multiple_policies_count_salary_once_and_preserve_paid_total():
    first = observation(recorded_amount=Decimal("6424.88"))
    second = observation(transaction_id="tx-2", policy_ref="policy-2", benefit_ref="benefit-2", recorded_amount=Decimal("4283.25"))
    report = compare([first, second])
    assert (report.source_policies, report.compared_groups, report.compared_people) == (2, 1, 1)
    assert report.baseline == report.comparable_recorded == Decimal("10708.13")
    assert report.difference == Decimal("-255")


def test_independent_employers_and_distinct_affected_people():
    report = compare([observation(), observation(transaction_id="tx-2", employer_ref="employer-2", benefit_ref="benefit-2")])
    assert report.compared_groups == 2
    assert report.affected_people == 1
    assert report.difference == Decimal("-510")


def test_higher_ibb_can_increase_premium_above_the_salary_cap():
    report = compare([observation(salary=Decimal("250000"), recorded_amount=Decimal("49258.13"))])
    # Taket ökar 4 000 kr: +1 200 i högdelen, −255 vid nedre brytpunkten.
    assert report.difference == Decimal("945.00")
    assert report.reconciliation_difference == 0


@pytest.mark.parametrize("changes, reason", [
    ({"salary": None}, "missing_salary_groups"),
    ({"salary": Decimal("-1")}, "invalid_salary_groups"),
    ({"salary": Decimal("Infinity")}, "invalid_salary_groups"),
    ({"birth_date": None}, "missing_birth_groups"),
    ({"employer_ref": ""}, "missing_identity_groups"),
])
def test_incomplete_data_is_not_assumed_to_be_zero(changes, reason):
    report = compare([observation(**changes)])
    assert report.compared_groups == 0
    assert report.quality == {reason: 1}
    assert report.recorded_by_status["paid"] == Decimal("10708.13")


def test_conflicting_salary_and_duplicates_block_whole_group():
    second = observation(transaction_id="tx-2", benefit_ref="benefit-2", salary=Decimal("90000"))
    assert compare([observation(), second]).quality == {"conflicting_salary_groups": 1}
    assert compare([observation(), observation(transaction_id="tx-2")]).quality == {"duplicate_groups": 1}
    assert compare([observation(), observation()]).quality == {"duplicate_groups": 1}


def test_zero_salary_cancelled_and_not_paid_are_separate():
    rows = [observation(salary=Decimal("0"), recorded_amount=Decimal("0")),
            observation(transaction_id="tx-2", person_ref="person-2", status="cancelled"),
            observation(transaction_id="tx-3", person_ref="person-3", status="invoiced")]
    report = compare(rows)
    assert report.compared_groups == 2
    assert report.quality == {"cancelled_rows": 1}
    assert report.recorded_by_status["paid"] == 0
    assert report.recorded_by_status["invoiced"] == Decimal("10708.13")


def test_age_window_and_observed_mismatch_are_visible():
    report = compare([observation(birth_date=date(1960, 6, 20))])
    assert report.baseline == report.scenario == 0  # 66-årsmånaden
    assert report.reconciliation_difference == Decimal("10708.13")
    assert report.affected_people == 0


def test_month_selection_and_unchanged_ibb():
    report = compare([observation(), observation(month=date(2026, 5, 1))], scenario_ibb=Decimal("83400"))
    assert report.source_rows == 1
    assert report.difference == 0


@pytest.mark.parametrize("ibb", [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")])
def test_invalid_scenario_rejected(ibb):
    with pytest.raises(ValueError):
        compare([observation()], scenario_ibb=ibb)


def test_output_is_aggregate_and_deterministic():
    report = compare([observation()])
    text = render_markdown(report, source="Test", attribution="Test")
    assert text == render_markdown(report, source="Test", attribution="Test")
    for value in ("person-1", "policy-1", "benefit-1", "employer-1", "tx-1", "1990-01-01"):
        assert value not in text
    assert "inte hela beståndet" in text


def test_empty_comparison_is_explicitly_inconclusive():
    text = render_markdown(compare([]), source="Test", attribution="Test")
    assert "Inga jämförbara underlag" in text
    assert "Nollbeloppen visar inte" in text


def write_snapshot(path):
    tables = {
        "insured_persons": [{"id": "p", "employer_id": "e", "personal_id_number": "199001010000",
                             "monthly_salary_sek": "90000"}],
        "policies": [{"id": "pol", "insured_person_id": "p"}],
        "policy_benefits": [{"id": "b", "policy_id": "pol", "benefit_type": "retirement_dc"}],
        "base_amounts": [{"year": 2026, "income_base_amount_sek": "83400"}],
        "premium_transactions": [{"id": "t", "benefit_id": "b", "transaction_type": "premium",
                                  "period_month": "2026-06-01", "pensionable_salary_sek": "80000",
                                  "amount_sek": "10708.13", "status": "paid"}],
    }
    (path / "manifest.json").write_text(json.dumps({"tables": list(tables), "row_counts": {k: len(v) for k, v in tables.items()},
                                                  "created_at": "2026-10-11T12:00:00+00:00"}), encoding="utf-8")
    for name, records in tables.items():
        (path / f"{name}.jsonl").write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


def test_snapshot_requires_explicit_attribution_and_preserves_historical_salary(tmp_path):
    write_snapshot(tmp_path)
    with pytest.raises(ValueError, match="arbetsgivare"):
        load_snapshot(tmp_path)
    records, ibb, stamp = load_snapshot(tmp_path, assume_current_employer=True)
    assert records[0].salary == Decimal("80000")
    assert ibb == {2026: Decimal("83400")}
    assert compare(records).difference == Decimal("-255")


def test_truncated_snapshot_is_rejected(tmp_path):
    write_snapshot(tmp_path)
    (tmp_path / "premium_transactions.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="Radantal"):
        load_snapshot(tmp_path, assume_current_employer=True)
