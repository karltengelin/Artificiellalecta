"""Pensionskapitalets månadsavräkning (A5, B-042) mot produktreglernas kontrollfall.

Kontrollfall: PR-ITP1-020/021/022/023 (avsnittet Kontrollfall) och fördelningen i ören i
PR-ITP1-011, med 2026 års satser. Startraderna i `product_parameters` prövas mot
parameterregistret, så att tabellen och registret inte glider isär, och uppslaget per månad
prövas mot SQLite.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from models import Base, ProductParameter
from services import parameters
from services.db import session_factory_for
from services.errors import NotFoundError
from skills.calculation.capital_rollforward import RollforwardError, allocate_cents
from skills.calculation.capital_rollforward import close_month as _close_month

REGISTER = Path(__file__).resolve().parents[1] / "01_domän" / "parametrar" / "PARAMETERREGISTER.md"
OCT_2026 = date(2026, 10, 1)
FEE, TAX_2026, TAX_2023 = Decimal("0.002"), Decimal("0.00354"), Decimal("0.00219")


def close_month(month, rate, openings, premiums, *, tax_rate=TAX_2026):
    return _close_month(month, rate, openings, premiums, fee_rate=FEE, tax_rate=tax_rate)


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

    def test_ogiltig_sats(self):
        with pytest.raises(RollforwardError, match="andelar"):
            close_month(OCT_2026, d("0.01"), {"a": d("100")}, {}, tax_rate=d("1.2"))

    def test_avrundning_halvt_uppat(self):
        line = close_month(date(2023, 2, 1), d("0"), {"a": d("10000")}, {}, tax_rate=TAX_2023).lines["a"]
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
    def test_skattebelastningen_ar_registrets_per_ar(self):
        rows = re.findall(r"^\| (\d{4}) \|.*\| ([\d,]+) % \|$", REGISTER.read_text(encoding="utf-8"), re.MULTILINE)
        register = {int(year): Decimal(rate.replace(",", ".")) / 100 for year, rate in rows}
        taxes = [p for p in parameters.DEFAULTS if p.key == "customer_tax_rate"]
        assert {p.valid_from.year: p.value for p in taxes} == register
        for p in taxes:
            assert (p.valid_from, p.valid_to) == (date(p.valid_from.year, 1, 1), date(p.valid_from.year, 12, 31))

    def test_kapitalavgiften_ar_registrets(self):
        text = REGISTER.read_text(encoding="utf-8")
        fee = next(p for p in parameters.DEFAULTS if p.key == "capital_fee_rate")
        assert "| Kapitalavgift | 0,20 % nominellt per år" in text and fee.value == FEE and fee.valid_to is None


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = session_factory_for(engine)
    with factory() as s:
        parameters.add_missing_defaults(s)
        s.commit()
    yield factory
    engine.dispose()


class TestUppslag:
    def test_satserna_per_manad(self, factory):
        with factory() as s:
            rates = parameters.capital_rates(s, [date(2023, 12, 1), date(2024, 1, 1), date(2026, 10, 1)])
        assert {m: r[:2] for m, r in rates.items()} == {
            date(2023, 12, 1): (FEE, TAX_2023), date(2024, 1, 1): (FEE, d("0.00372")), date(2026, 10, 1): (FEE, TAX_2026)}
        assert rates[date(2024, 1, 1)][3] == "PR-ITP1-023 v1.0 från 2024-01-01"

    def test_saknat_ar_blockerar(self, factory):
        # PR-023: ett år utan beslutad sats stoppar, inte föregående års sats automatiskt
        with factory() as s, pytest.raises(NotFoundError, match="2027-01: customer_tax_rate"):
            parameters.capital_rates(s, [date(2026, 12, 1), date(2027, 1, 1)])

    def test_aterkallad_version_galler_inte(self, factory):
        with factory() as s:
            s.scalar(select(ProductParameter).where(ProductParameter.key == "capital_fee_rate")).status = "withdrawn"
            s.flush()
            with pytest.raises(NotFoundError, match="capital_fee_rate"):
                parameters.capital_rates(s, [date(2026, 10, 1)])
