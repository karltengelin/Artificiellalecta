"""Svenska bankdagar och fakturans förfallodag (utils/bank_calendar.py, P1-PREMIE-001 §4.4)."""

from datetime import date, timedelta

import pytest

from utils.bank_calendar import easter_sunday, invoice_due_date, is_bank_day, next_bank_day, non_bank_days


@pytest.mark.parametrize(
    ("year", "easter"),
    [(2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2026, date(2026, 4, 5)),
     (2027, date(2027, 3, 28)), (2038, date(2038, 4, 25))],
)
def test_paskdagen(year, easter):
    assert easter_sunday(year) == easter


def test_rorliga_helgdagar_2026():
    days = non_bank_days(2026)
    assert days[date(2026, 4, 3)] == "långfredagen"
    assert days[date(2026, 4, 6)] == "annandag påsk"
    assert days[date(2026, 5, 14)] == "Kristi himmelsfärdsdag"
    assert days[date(2026, 6, 19)] == "midsommarafton"
    assert days[date(2026, 6, 20)] == "midsommardagen"
    assert days[date(2026, 10, 31)] == "alla helgons dag"


def test_aftnar_ar_inga_bankdagar():
    for day in (date(2026, 6, 19), date(2026, 12, 24), date(2026, 12, 31)):
        assert day.weekday() < 5
        assert not is_bank_day(day)


def test_vanlig_vardag_och_helg():
    assert is_bank_day(date(2026, 11, 9))  # måndag
    assert not is_bank_day(date(2026, 11, 7))  # lördag
    assert not is_bank_day(date(2026, 11, 8))  # söndag


def test_nasta_bankdag():
    assert next_bank_day(date(2026, 11, 9)) == date(2026, 11, 9)
    assert next_bank_day(date(2026, 11, 7)) == date(2026, 11, 9)
    assert next_bank_day(date(2026, 12, 24)) == date(2026, 12, 28)
    assert next_bank_day(date(2026, 12, 31)) == date(2027, 1, 4)  # nyårsdagen fredag, sedan helg


def test_forfallodag_flyttas_over_julen():
    """Fall 16 i P1-PREMIE-001 §7."""
    assert invoice_due_date(date(2026, 11, 25)) == date(2026, 12, 28)


def test_forfallodag_pa_bankdag_flyttas_inte():
    assert invoice_due_date(date(2026, 11, 30)) == date(2026, 12, 30)


def test_forfallodag_ar_alltid_bankdag_och_minst_30_dagar_bort():
    start = date(2026, 1, 1)
    for offset in range(800):
        invoiced = start + timedelta(days=offset)
        due = invoice_due_date(invoiced)
        assert is_bank_day(due)
        assert 30 <= (due - invoiced).days <= 35
