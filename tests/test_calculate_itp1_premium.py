"""Tester för premiemotorn (Fas 1c/1e).

Handräknade exempel med IBB 2026 = 83 400 kr:
    brytpunkt låg  = 7,5 × 83 400 / 12 = 52 125,00 kr/mån
    brytpunkt hög  = 30  × 83 400 / 12 = 208 500,00 kr/mån
"""

from datetime import date
from decimal import Decimal

import pytest

from skills.calculation.calculate_itp1_premium import (
    calculate_itp1_premium,
    is_in_age_window,
)

IBB_2026 = Decimal("83400")


class TestPremieTrappan:
    def test_lon_under_brytpunkten(self):
        # 35 000 × 0,045 = 1 575,00
        r = calculate_itp1_premium(Decimal("35000"), IBB_2026)
        assert r.total_premium_sek == Decimal("1575.00")
        assert r.amount_high_sek == Decimal("0.00")

    def test_lon_exakt_pa_brytpunkten(self):
        # 52 125 × 0,045 = 2 345,625 → 2 345,63 (half up)
        r = calculate_itp1_premium(Decimal("52125"), IBB_2026)
        assert r.total_premium_sek == Decimal("2345.63")
        assert r.amount_high_sek == Decimal("0.00")

    def test_lon_over_brytpunkten(self):
        # 2 345,63 + 0,30 × (80 000 − 52 125) = 2 345,63 + 8 362,50 = 10 708,13
        r = calculate_itp1_premium(Decimal("80000"), IBB_2026)
        assert r.amount_low_sek == Decimal("2345.63")
        assert r.amount_high_sek == Decimal("8362.50")
        assert r.total_premium_sek == Decimal("10708.13")

    def test_lon_over_taket_30_ibb(self):
        # Taket: 0,30 × (208 500 − 52 125) = 46 912,50; totalt 49 258,13
        r = calculate_itp1_premium(Decimal("250000"), IBB_2026)
        assert r.total_premium_sek == Decimal("49258.13")

    def test_nollon_ger_nollpremie(self):
        r = calculate_itp1_premium(Decimal("0"), IBB_2026)
        assert r.total_premium_sek == Decimal("0.00")

    def test_komponenter_summerar_till_total(self):
        r = calculate_itp1_premium(Decimal("123456.78"), IBB_2026)
        assert r.amount_low_sek + r.amount_high_sek == r.total_premium_sek

    def test_annat_ibb_ar_ger_andra_brytpunkter(self):
        # IBB 2025 = 80 600 → brytpunkt 50 375; lön 52 125 ligger nu ÖVER den
        r = calculate_itp1_premium(Decimal("52125"), Decimal("80600"))
        assert r.amount_high_sek > 0


class TestAldersfonster:
    BIRTH = date(1998, 8, 15)

    def test_manaden_25_arsdagen_infaller_ger_premie(self):
        assert is_in_age_window(self.BIRTH, date(2023, 8, 1)) is True

    def test_manaden_innan_25_ger_ingen_premie(self):
        assert is_in_age_window(self.BIRTH, date(2023, 7, 1)) is False

    def test_manaden_innan_66_ger_premie(self):
        assert is_in_age_window(self.BIRTH, date(2064, 7, 1)) is True

    def test_manaden_66_arsdagen_infaller_ger_ingen_premie(self):
        assert is_in_age_window(self.BIRTH, date(2064, 8, 1)) is False

    def test_utanfor_fonstret_ger_nollpremie_med_basis(self):
        r = calculate_itp1_premium(
            Decimal("40000"), IBB_2026,
            birth_date=date(2005, 3, 1), period_month=date(2026, 6, 1),
        )
        assert r.in_age_window is False
        assert r.total_premium_sek == Decimal("0.00")

    def test_i_fonstret_beraknar_normalt(self):
        r = calculate_itp1_premium(
            Decimal("40000"), IBB_2026,
            birth_date=date(1990, 1, 1), period_month=date(2026, 6, 1),
        )
        assert r.in_age_window is True
        assert r.total_premium_sek == Decimal("1800.00")


class TestFelhantering:
    def test_negativ_lon(self):
        with pytest.raises(ValueError):
            calculate_itp1_premium(Decimal("-1"), IBB_2026)

    def test_ogiltigt_ibb(self):
        with pytest.raises(ValueError):
            calculate_itp1_premium(Decimal("30000"), Decimal("0"))

    def test_birth_date_utan_period(self):
        with pytest.raises(ValueError):
            calculate_itp1_premium(
                Decimal("30000"), IBB_2026, birth_date=date(1990, 1, 1)
            )


class TestSparbarhet:
    def test_calculation_basis_innehaller_alla_parametrar(self):
        r = calculate_itp1_premium(Decimal("80000"), IBB_2026)
        b = r.calculation_basis
        assert b["ibb"] == "83400"
        assert b["breakpoint_low"] == "52125.00"
        assert b["breakpoint_high"] == "208500.00"
        assert b["rate_low"] == "0.045"
        assert b["rate_high"] == "0.30"
        # Premien ska kunna räknas om ur basis (databasschema §8)
        assert Decimal(b["amount_low"]) + Decimal(b["amount_high"]) == r.total_premium_sek
