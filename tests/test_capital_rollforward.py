"""Pensionskapitalets månadsavräkning (A5, B-042) mot produktreglernas kontrollfall.

Kontrollfall: PR-ITP1-020/021/022/023 (avsnittet Kontrollfall) och fördelningen i ören i
PR-ITP1-011. Satserna prövas mot parameterregistret, så att koden och registret inte glider isär.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from skills.calculation.capital_rollforward import (
    CAPITAL_FEE_RATE,
    CUSTOMER_TAX_RATES,
    RollforwardError,
    allocate_cents,
    close_month,
    tax_rate,
)

REGISTER = Path(__file__).resolve().parents[1] / "01_domän" / "parametrar" / "PARAMETERREGISTER.md"
OCT_2026 = date(2026, 10, 1)


def d(value: str) -> Decimal:
    return Decimal(value)


class TestKontrollfall:
    def test_pr020_avkastning_avgift_och_skatt_pa_oppningsbas(self):
        line = close_month(OCT_2026, d("0.01"), {"a": d("100000")}, {}).lines["a"]
        assert (line.investment_return, line.fee, line.tax) == (d("1000.00"), d("16.67"), d("29.50"))
        assert line.closing == d("100953.83")

    def test_pr020_ny_premie_far_avkastning_forst_nasta_manad(self):
        first = close_month(OCT_2026, d("0.01"), {"a": d("100000")}, {"a": d("1000")}).lines["a"]
        assert first.investment_return == d("1000.00") and first.closing == d("101953.83")
        second = close_month(date(2026, 11, 1), d("0.01"), {"a": first.closing}, {}).lines["a"]
        assert second.investment_return == d("1019.54")

    def test_pr021_forlust_fordelas_efter_oppningskapital(self):
        month = close_month(OCT_2026, d("-0.10"), {"a": d("1000"), "b": d("2000")}, {})
        assert [month.lines[k].investment_return for k in "ab"] == [d("-100.00"), d("-200.00")]

    def test_pr022_noll_kapital_ger_ingen_avgift(self):
        line = close_month(OCT_2026, d("0.01"), {"a": d("0")}, {}).lines["a"]
        assert (line.fee, line.tax, line.closing) == (0, 0, 0)

    def test_pr022_hela_forlusten_avstar_avgift_och_skatt(self):
        line = close_month(OCT_2026, d("-1"), {"a": d("100000")}, {}).lines["a"]
        assert (line.investment_return, line.fee, line.tax, line.closing) == (d("-100000.00"), 0, 0, 0)
        assert (line.fee_waived, line.tax_waived) == (d("16.67"), d("29.50"))

    def test_pr023_skatten_kvarstar_vid_negativ_avkastning(self):
        line = close_month(OCT_2026, d("-0.05"), {"a": d("100000")}, {}).lines["a"]
        assert line.tax == d("29.50") and line.closing == d("94953.83")

    def test_pr023_saknad_arssats_blockerar(self):
        with pytest.raises(RollforwardError, match="2027"):
            tax_rate(2027)
        with pytest.raises(RollforwardError, match="2027"):
            close_month(date(2027, 1, 1), d("0.01"), {"a": d("100")}, {})

    def test_avrundning_halvt_uppat(self):
        line = close_month(date(2023, 2, 1), d("0"), {"a": d("10000")}, {}).lines["a"]
        assert line.tax == d("1.83")  # 10 000 × 0,00219/12 = 1,825


class TestFordelning:
    def test_pr011_lika_vikter_efter_ordning(self):
        assert allocate_cents(d("0.02"), [d("1"), d("1"), d("1")]) == [d("0.01"), d("0.01"), d("0.00")]

    def test_pr011_proportionellt(self):
        assert allocate_cents(d("90"), [d("30"), d("60")]) == [d("30.00"), d("60.00")]

    def test_kollektivets_resultat_i_oren_summerar_exakt(self):
        month = close_month(OCT_2026, d("0.5"), {k: d("0.01") for k in "abc"}, {})
        returns = [month.lines[k].investment_return for k in "abc"]
        assert returns == [d("0.01"), d("0.01"), d("0.00")] and sum(returns) == d("0.02")

    def test_forlust_fordelas_pa_magnitud(self):
        assert allocate_cents(d("-0.02"), [d("-0.005")] * 3) == [d("-0.01"), d("-0.01"), d("0.00")]

    def test_noll_fordelas_pa_noll(self):
        assert allocate_cents(d("0"), [d("0"), d("0")]) == [d("0.00"), d("0.00")]

    def test_ogiltig_fordelning(self):
        with pytest.raises(RollforwardError):
            allocate_cents(d("0.015"), [d("1")])
        with pytest.raises(RollforwardError):
            allocate_cents(d("1"), [d("-1")])
        with pytest.raises(RollforwardError):
            allocate_cents(d("1"), [d("0")])
        with pytest.raises(RollforwardError):
            close_month(OCT_2026, d("-1.5"), {"a": d("1")}, {})
        with pytest.raises(RollforwardError):
            close_month(OCT_2026, d("0"), {"a": d("-1")}, {})


class TestParameterregistret:
    def test_skattesatserna_stammer_med_registret(self):
        rows = re.findall(r"^\| (\d{4}) \|.*\| ([\d,]+) % \|$", REGISTER.read_text(encoding="utf-8"), re.MULTILINE)
        register = {int(year): Decimal(rate.replace(",", ".")) / 100 for year, rate in rows}
        assert register == CUSTOMER_TAX_RATES

    def test_kapitalavgiften_stammer_med_registret(self):
        text = REGISTER.read_text(encoding="utf-8")
        assert "| Kapitalavgift | 0,20 % nominellt per år" in text and CAPITAL_FEE_RATE == d("0.002")
