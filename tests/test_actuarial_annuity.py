"""Aktuariella beräkningsmotorn (A5, B-042) mot leveranskontrollens facit.

Facit: projekt/04_produktregelverk/LEVERANSKONTROLL.md §3, beräknat fristående 2026-10-11 med
samma låsta SCB-tabell och SIM-grund. Grunderna kommer ur antagandebibliotekets startgrunder.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.valuation_bases import START_BASES, normalize
from skills.calculation import actuarial_annuity as aa
from skills.calculation.actuarial_annuity import (
    MortalityBasis,
    TableError,
    age_on,
    annual_q,
    annuity_factor,
    basis_from_assumptions,
    guarantee_part,
    monthly_q,
    reference_start,
)

RAW = {code: raw for code, _, raw, *_ in START_BASES}
SIM_G, _ = basis_from_assumptions(normalize("guarantee", RAW["SIM-G-2026-01"]))
SIM_R = MortalityBasis.from_assumptions(normalize("risk", RAW["SIM-R-2026-01"])["mortality"])
BORN = date(1960, 11, 1)
T0, START = date(2026, 10, 31), date(2026, 11, 1)
T1, LATER = date(2027, 10, 31), date(2027, 11, 1)


class TestFacit:
    def test_dodsrisker(self):
        assert annual_q(SIM_R, 66, 2026, 1960) * 100 == pytest.approx(0.710185, abs=5e-7)
        assert monthly_q(SIM_G, BORN, START) * 100 == pytest.approx(0.0474694047, abs=5e-11)

    @pytest.mark.parametrize("valuation, start, payments, paused, facit", [
        (T0, START, 60, (), 59.019956697),
        (T0, START, None, (), 293.440405905),
        (T1, LATER, 48, (), 47.316383622),
        (T1, LATER, 108, (), 103.923811079),
        (T1, date(2028, 2, 1), 48, (), 47.223338160),
        (T1, LATER, 48, (LATER, date(2027, 12, 1), date(2028, 1, 1)), 47.223338160),  # pausen som skippade månader
    ])
    def test_annuitetsfaktorer(self, valuation, start, payments, paused, facit):
        assert annuity_factor(SIM_G, BORN, valuation, start, payments, paused=paused) == pytest.approx(facit, abs=5e-10)

    def test_stress_med_omraknad_svans(self):
        assert annuity_factor(SIM_G.scaled(0.8), BORN, T0, START, None) == pytest.approx(316.675957776, abs=5e-10)

    def test_garantibelopp_och_bevarat_garantivarde(self):
        g60 = 100_000 / annuity_factor(SIM_G, BORN, T0, START, 60)
        assert round(g60, 2) == 1694.34
        assert round(100_000 / annuity_factor(SIM_G, BORN, T0, START, None), 2) == 340.78
        v_g = g60 * annuity_factor(SIM_G, BORN, T1, LATER, 48)
        assert round(v_g, 2) == 80170.14
        assert round(v_g / annuity_factor(SIM_G, BORN, T1, LATER, 108), 2) == 771.43

    def test_garantidel_med_vantetid(self):
        g, factor = guarantee_part(SIM_G, date(2001, 11, 1), date(2026, 11, 30), Decimal(1000))
        assert factor == pytest.approx(347.157063780, abs=5e-10)
        assert g == pytest.approx(2.880540552, abs=5e-10)


class TestRegler:
    def test_alder_ar_fyllda_ar_vid_manadens_forsta_dag(self):
        assert (age_on(BORN, START), age_on(date(1960, 11, 15), START)) == (66, 65)

    def test_referensstart(self):
        assert reference_start(BORN, date(2026, 6, 30)) == date(2026, 11, 1)
        assert reference_start(date(1958, 3, 10), date(2026, 6, 30)) == date(2026, 7, 1)  # 66-årsmånaden passerad

    def test_forsta_manaden_har_vikten_ett_och_faktorn_ar_mindre_an_antalet(self):
        assert annuity_factor(SIM_G, BORN, T0, START, 1) == 1.0
        assert 0 < annuity_factor(SIM_G, BORN, T0, START, 60) < 60

    def test_ranta_sanker_faktorn(self):
        assert annuity_factor(SIM_G, BORN, T0, START, 60, net_interest_rate=0.03) < 59.019956697

    def test_svansen_nar_taket(self):
        assert annual_q(SIM_G, 150, 2110, 1960) == pytest.approx(0.995)
        assert annual_q(SIM_G, 101, 2061, 1960) > annual_q(SIM_G, 100, 2060, 1960)

    @pytest.mark.parametrize("valuation, start, payments", [
        (T0, date(2026, 10, 1), 12), (T0, date(2026, 11, 15), 12), (T0, START, 0)])
    def test_ogiltig_plan(self, valuation, start, payments):
        with pytest.raises(ValueError):
            annuity_factor(SIM_G, BORN, valuation, start, payments)

    def test_okand_tabell_och_andrad_fil(self, tmp_path):
        with pytest.raises(TableError, match="Okänd"):
            MortalityBasis.from_assumptions({**RAW["SIM-G-2026-01"]["mortality"], "table": "annan"})
        changed = tmp_path / "tabell.md"
        changed.write_bytes(aa.TABLE_PATH.read_bytes().replace(b"| 66 |", b"| 66 | ", 1))
        with pytest.raises(TableError, match="kontrollsumma"):
            aa.scb_table.__wrapped__(changed)
