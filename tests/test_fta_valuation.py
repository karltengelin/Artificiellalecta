"""FTA-värderingen som ren beräkning (A6, B-042) och kontrollfallen i VARDERINGSKONTRAKT.md §7.

K1–K4, K8 och K9 prövas här mot motorn; K5–K7 och K10 mot sparade körningar i
tests/test_valuation_runs.py. Oberoende kontroller räknar med egna explicita summor, utan
motorns svans och cache. Grunderna kommer ur antagandebibliotekets startgrunder.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.valuation_bases import START_BASES, normalize
from skills.calculation import actuarial_annuity as aa
from skills.calculation import fta_valuation as fv

RAW = {code: raw for code, _, raw, *_ in START_BASES}
SIM_G, _ = aa.basis_from_assumptions(normalize("guarantee", RAW["SIM-G-2026-01"]))
SIM_V = normalize("valuation", RAW["SIM-V-2026-01"])
CURVE = normalize("discount_curve", RAW["FI-SIM-2026-10"])
S_Y = 0.00354
T = date(2026, 9, 30)
BORN_40 = date(1986, 9, 2)  # 40 år vid värderingen
BORN_60 = date(1966, 9, 2)
NONE = fv.Expenses.none()


def one_premium(model: fv.ValuationModel, capital: Decimal = Decimal(0), premium: Decimal = Decimal(1000),
                birth: date = BORN_40, valuation: date = T) -> fv.PolicyValue:
    g, _ = aa.guarantee_part(SIM_G, birth, valuation, premium)
    start = aa.reference_start(birth, valuation)
    return fv.value_policies(model, valuation, [
        fv.PolicyInput("p", birth, "premium_paying", start, Decimal(repr(g)), capital)])[0]


def flat(rate: float, tax: float = 0.0, expenses: fv.Expenses = NONE) -> fv.ValuationModel:
    return fv.ValuationModel(SIM_G, aa.DiscountCurve.flat(rate, tax), expenses)


def explicit_annuity(birth: date, valuation: date, start: date, rate: float, payments: int | None = None,
                     growth: float = 1.0) -> float:
    """Oberoende summa Σ w_n · g^n · (1 + r)^(−n/12) utan svansformel, tills vikten saknar betydelse."""
    month, weight, total, n, made = aa.first_month_after(valuation), 1.0, 0.0, 0, 0
    while weight > 1e-18 and (payments is None or made < payments):
        n += 1
        if month >= start:
            total += weight * growth ** n * (1 + rate) ** (-n / 12)
            made += 1
        weight *= 1 - aa.monthly_q(SIM_G, birth, month)
        month = aa.add_months(month, 1)
    return total


class TestKontrollfall:
    def test_k1_premien_pa_nollkurva_ger_fta_lika_med_premien(self):
        value = one_premium(flat(0.0))
        assert value.fta.quantize(Decimal("0.01")) == Decimal("1000.00")
        assert abs(value.fta - 1000) < Decimal("0.000001")
        assert fv.k1_engine_check(SIM_G).quantize(Decimal("0.01")) == Decimal("1000.00")

    def test_k1_galler_med_ett_annat_alder_och_datum(self):
        value = one_premium(flat(0.0), birth=date(1961, 3, 1), valuation=date(2026, 12, 31))
        assert value.fta.quantize(Decimal("0.01")) == Decimal("1000.00")

    def test_k2_platt_kurva_tre_procent_ger_mindre_an_premien_och_stammer_oberoende(self):
        value = one_premium(flat(0.03))
        assert value.fta < 1000
        start = aa.reference_start(BORN_40, T)
        independent = float(value.guarantee) * explicit_annuity(BORN_40, T, start, 0.03)
        assert float(value.fta) == pytest.approx(independent, rel=1e-9)

    def test_m2_skatt_genom_diskontering_mot_explicit_skatteprojektion(self):
        """K2-varianten med skatt: diskontering med r − s mot en reserv som betalar skatt varje månad."""
        r, s = 0.03, S_Y
        birth, valuation = date(1960, 10, 2), T
        start, payments = aa.reference_start(birth, valuation), 120
        by_discount = aa.annuity_factor(SIM_G, birth, valuation, start, payments,
                                        curve=aa.DiscountCurve.flat(r, s))

        def projection(tau: float) -> float:
            # R_{n−1} = u·(b_n + τ·R_{n−1} + p_n·R_n): skatten τ på reserven under månaden, ränta r
            months, month = [], aa.first_month_after(valuation)
            while len([m for m in months if m >= start]) < payments:
                months.append(month)
                month = aa.add_months(month, 1)
            u, reserve = (1 + r) ** (-1 / 12), 0.0
            for m in reversed(months):
                p = 1 - aa.monthly_q(SIM_G, birth, m)
                reserve = u * ((1.0 if m >= start else 0.0) + p * reserve) / (1 - u * tau)
            return reserve

        exact_tau = (1 + r) ** (1 / 12) - (1 + r - s) ** (1 / 12)
        assert projection(exact_tau) == pytest.approx(by_discount, rel=1e-12)
        assert projection(s / 12) == pytest.approx(by_discount, rel=1e-3)  # s/12 per månad: avvikelse < 0,1 %

    def test_k3_underskott_nar_kapitalet_ar_mindre(self):
        # K3 förutsätter FTA enligt K2 över 500 kr. Vid 40 år ger 3 % ungefär 304 kr, så fallet räknas vid 60 år.
        value = one_premium(flat(0.03), capital=Decimal(500), birth=BORN_60)
        assert value.fta > 500
        assert (value.surplus, value.deficit) == (Decimal(0), value.fta - 500)

    def test_k4_villkorad_aterbaring_nar_kapitalet_ar_storre(self):
        value = one_premium(flat(0.03), capital=Decimal(2000), birth=BORN_60)
        assert value.fta > 500
        assert (value.surplus, value.deficit) == (2000 - value.fta, Decimal(0))

    @pytest.mark.parametrize("unexplained, status", [
        (Decimal("0.4"), "ok"), (Decimal("0.5"), "ok"), (Decimal("0.51"), "needs_human"), (Decimal("-0.6"), "needs_human")])
    def test_k8_oanalyserat_over_troskeln_kraver_manniska(self, unexplained, status):
        assert fv.unexplained_status(unexplained, Decimal(100)) == status

    def test_k9_leveranskontrollens_garantifall_via_kurvan(self):
        """Samma G och faktorer som LEVERANSKONTROLL.md §3 när kurvan är 0 % och skatten noll."""
        zero = aa.DiscountCurve.flat(0.0)
        born, t0, start = date(1960, 11, 1), date(2026, 10, 31), date(2026, 11, 1)
        assert aa.annuity_factor(SIM_G, born, t0, start, None, curve=zero) == pytest.approx(293.440405905, abs=5e-10)
        assert aa.annuity_factor(SIM_G, born, t0, start, 60, curve=zero) == pytest.approx(59.019956697, abs=5e-10)
        assert round(100_000 / aa.annuity_factor(SIM_G, born, t0, start, None, curve=zero), 2) == 340.78
        factor = aa.annuity_factor(SIM_G, date(2001, 11, 1), date(2026, 11, 30), date(2067, 11, 1), None, curve=zero)
        assert factor == pytest.approx(347.157063780, abs=5e-10)
        assert 1000 / factor == pytest.approx(2.880540552, abs=5e-10)


class TestKurvan:
    def test_interpolation_och_platt_extrapolation(self):
        curve = aa.DiscountCurve.from_assumptions(CURVE)
        assert (curve.spot(1), curve.spot(4), curve.spot(20), curve.spot(200)) == pytest.approx(
            (0.025, 0.0265, 0.030, 0.034))
        assert curve.spot(110) == pytest.approx(0.034)

    def test_diskonteringen_foljer_kontraktet(self):
        curve = aa.DiscountCurve.from_assumptions(CURVE, S_Y)
        assert curve.factor(12) == pytest.approx((1 + 0.025 - S_Y) ** -1)
        assert curve.factor(13) == pytest.approx((1 + 0.0255 - S_Y) ** (-13 / 12))  # ⌈13/12⌉ = 2 år
        assert curve.flat_from == 12 * 99 + 1  # löptiderna 100 och 150 har samma ränta

    def test_kurvan_ger_samma_som_oberoende_summa(self):
        curve = aa.DiscountCurve.from_assumptions(CURVE)
        start = aa.reference_start(BORN_40, T)
        by_engine = aa.annuity_factor(SIM_G, BORN_40, T, start, None, curve=curve)
        month, weight, total, n = aa.first_month_after(T), 1.0, 0.0, 0
        while weight > 1e-18:
            n += 1
            if month >= start:
                total += weight * (1 + curve.spot(-(-n // 12))) ** (-n / 12)
            weight *= 1 - aa.monthly_q(SIM_G, BORN_40, month)
            month = aa.add_months(month, 1)
        assert by_engine == pytest.approx(total, rel=1e-12)

    def test_icke_platt_slut_och_aldre_person_avslutas(self):
        curve = aa.DiscountCurve(((1, 0.02), (150, 0.04)))  # stiger hela vägen: platt först efter 150 år
        born = date(1940, 1, 2)
        value = aa.annuity_factor(SIM_G, born, T, aa.first_month_after(T), None, curve=curve)
        assert 0 < value < aa.annuity_factor(SIM_G, born, T, aa.first_month_after(T), None)

    def test_nettoranta_och_kurva_samtidigt_ar_fel(self):
        with pytest.raises(ValueError, match="antingen"):
            aa.annuity_factor(SIM_G, BORN_40, T, aa.reference_start(BORN_40, T), None,
                              net_interest_rate=0.01, curve=aa.DiscountCurve.flat(0.01))

    @pytest.mark.parametrize("points", [(), ((2, 0.01), (1, 0.02)), ((0, 0.01),)])
    def test_ogiltig_kurva(self, points):
        with pytest.raises(ValueError):
            aa.DiscountCurve(points)


class TestDriftkostnader:
    def test_kostnaden_ar_180_under_uppskov_och_240_under_utbetalning_med_uppraakning(self):
        e = fv.Expenses(180.0, 240.0, 0.02)
        value = one_premium(flat(0.03, expenses=e))
        start = aa.reference_start(BORN_40, T)
        first = aa.first_month_after(T)
        deferred = aa.months_between(first, start)
        g = 1.02 ** (1 / 12)
        independent = (180 / 12 * explicit_annuity(BORN_40, T, first, 0.03, deferred, g)
                       + 240 / 12 * explicit_annuity(BORN_40, T, start, 0.03, None, g))
        assert float(value.expenses) == pytest.approx(independent, rel=1e-9)
        assert value.fta == value.guarantee_value + value.expenses

    def test_utan_kostnader_ar_k_noll_och_med_hojs_fta(self):
        without, with_k = one_premium(flat(0.03)), one_premium(flat(0.03, expenses=fv.Expenses(180, 240, 0.02)))
        assert without.expenses == 0 and with_k.fta > without.fta
        assert with_k.guarantee_value == without.guarantee_value


class TestGrundenOchSummor:
    def test_modellen_ur_antagandebiblioteket(self):
        model = fv.ValuationModel.from_assumptions(SIM_V, CURVE, S_Y)
        assert model.expenses == fv.Expenses(180.0, 240.0, 0.02)
        assert model.curve.tax_reduction == S_Y and model.mortality == SIM_G

    def test_annan_plan_eller_option_stoppar(self):
        with pytest.raises(ValueError, match="referensplanen"):
            fv.ValuationModel.from_assumptions({**SIM_V, "option_adjustment": "annat"}, CURVE, S_Y)

    def test_summakontrollen_och_segment(self):
        model = fv.ValuationModel.from_assumptions(SIM_V, CURVE, S_Y)
        inputs = [fv.PolicyInput(f"p{i}", date(1960 + i, 5, 2), "premium_paying" if i % 3 else "paid_up",
                                 aa.reference_start(date(1960 + i, 5, 2), T), Decimal(i * 37) / 7,
                                 Decimal(i * 4321)) for i in range(1, 30)]
        values = fv.value_policies(model, T, inputs)
        total = fv.totals(values)
        assert total.balances and total.surplus > 0 and total.deficit > 0
        segments = fv.by_segment(values, lambda y: f"{y // 10 * 10}-tal")
        assert sum(s.policies for s in segments.values()) == 29
        assert sum((s.fta for s in segments.values()), Decimal(0)) == total.fta

    def test_samma_indata_ger_samma_kontrollsumma(self):
        from services.valuation_bases import checksum

        model = fv.ValuationModel.from_assumptions(SIM_V, CURVE, S_Y)
        inputs = [fv.PolicyInput("a", BORN_40, "premium_paying", aa.reference_start(BORN_40, T), Decimal(3), Decimal(9))]
        runs = [fv.value_policies(fv.ValuationModel.from_assumptions(SIM_V, CURVE, S_Y), T, inputs) for _ in range(2)]
        payloads = [checksum(fv.results_payload(v, fv.totals(v))) for v in runs]
        assert payloads[0] == payloads[1]
        assert fv.value_policies(model, T, inputs)[0].fta == runs[0][0].fta

    def test_plan_fore_varderingen_ar_fel(self):
        model = flat(0.0)
        with pytest.raises(ValueError, match="före"):
            fv.value_policies(model, T, [fv.PolicyInput("x", BORN_40, "premium_paying", date(2026, 9, 1),
                                                        Decimal(1), Decimal(0))])
