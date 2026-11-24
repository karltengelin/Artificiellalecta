"""Preliminär skatt på ett bankuppdrag (paket B steg 6, PR-ITP1-026, Karls val X3–X5): fall 18–20 och gränserna."""

from __future__ import annotations

from decimal import Decimal

import pytest

from skills.calculation.payout_tax import (
    TaxBlocked,
    TaxError,
    TaxRule,
    whole_kronor,
    withholding,
)

D = Decimal
SIDE = TaxRule("side_income")
YEAR = D("12000.00")


def test_fall_18_sidoinkomst_30_procent():
    result = withholding(D("1000.00"), SIDE, YEAR)
    assert (result.tax, result.net, result.method) == (D("300.00"), D("700.00"), "percent")


def test_fall_19_hela_kronor_oretalet_bortfaller():
    result = withholding(D("333.33"), SIDE, YEAR)
    assert (result.tax, result.net) == (D("99.00"), D("234.33"))


@pytest.mark.parametrize("gross, year_total, tax, method", [
    ("99.99", "12000.00", "0.00", "below_100"),
    ("100.00", "1200.00", "30.00", "percent"),  # exakt 100 kr omfattas inte av gränsen
    ("500.00", "999.99", "0.00", "below_1000"),
    ("500.00", "1000.00", "150.00", "percent"),  # exakt 1 000 kr omfattas inte av gränsen
])
def test_fall_20_granserna(gross, year_total, tax, method):
    result = withholding(D(gross), SIDE, D(year_total))
    assert (result.tax, result.method) == (D(tax), method)
    assert result.net == D(gross) - D(tax)


def test_granserna_galler_inte_sink():
    result = withholding(D("50.00"), TaxRule("sink", D("0.25")), D("50.00"))
    assert (result.tax, result.method) == (D("12.00"), "percent")


def test_frivilligt_hogre_sidoavdrag():
    assert withholding(D("1000.00"), TaxRule("side_income", D("0.45")), YEAR).tax == D("450.00")


def test_lagre_sidoavdrag_an_30_procent_avvisas():
    with pytest.raises(TaxError, match="30 %"):
        withholding(D("1000.00"), TaxRule("side_income", D("0.20")), YEAR)


def test_individuellt_beslut_med_belopp_eller_procent():
    fixed = withholding(D("1000.00"), TaxRule("individual_decision", fixed_amount=D("250.75")), YEAR)
    assert (fixed.tax, fixed.method) == (D("250.00"), "fixed")
    capped = withholding(D("200.00"), TaxRule("individual_decision", fixed_amount=D("500.00")), YEAR)
    assert (capped.tax, capped.net) == (D("200.00"), D("0.00"))  # nettot blir aldrig negativt
    rate = withholding(D("1000.00"), TaxRule("individual_decision", D("0.12")), YEAR)
    assert rate.tax == D("120.00")


def test_x4_huvudinkomst_blockeras_utan_tabell():
    with pytest.raises(TaxBlocked) as exc:
        withholding(D("1000.00"), TaxRule("main_income"), YEAR)
    assert exc.value.reason == "table_missing"


@pytest.mark.parametrize("gross", ["0.00", "-1.00", "10.001"])
def test_bruttot_ska_vara_positivt_i_hela_oren(gross):
    with pytest.raises(TaxError):
        withholding(D(gross), SIDE, YEAR)


def test_okant_slag_avvisas():
    with pytest.raises(TaxError, match="Okänt"):
        withholding(D("1000.00"), TaxRule("pension_table"), YEAR)


def test_hela_kronor_avrundar_aldrig_uppat():
    assert whole_kronor(D("99.999")) == D("99.00") and whole_kronor(D("100.00")) == D("100.00")


def test_underlaget_redovisas():
    plain = withholding(D("1000.00"), SIDE, YEAR).plain()
    assert plain["tax_kind"] == "side_income" and plain["expected_year_total_sek"] == "12000.00"
    assert plain["gross_sek"] == "1000.00" and plain["tax_method"] == "percent"
