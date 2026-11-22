"""Månadsrättens finansiering och debitering, ren beräkning (paket B steg 5, P1-PENSION-001 §11, Karls val W5–W8).

- **Fall 14:** C 100 953,83 kr efter kostnader och M 500 kr ger skuld 500 kr och C 100 453,83 kr.
- **Fall 35:** C 80, rätt 100 och bolagskonto 0 ger 80 ur C och 20 ej finansierat; rätten är bevarad.
- **Fall 32 och 33:** den tidsbegränsade delens sista rätt är max(M, C) – hela kapitalet betalas ut, och ett C
  under M fylls ut från bolagskontot (PR-ITP1-027).
- Debiteringen fördelas på delens kapitalspår i ören med största bråkrest och överstiger inget spår.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from skills.calculation.pension_claim import ClaimError, claim_funding, debit_tracks

D = Decimal


def test_fall_14_ratt_ur_kundkapitalet():
    f = claim_funding(D("500.00"), D("100953.83"), D("0.00"))
    assert (f.gross, f.from_capital, f.company_support, f.unfunded) == (D("500.00"), D("500.00"), D("0"), D("0"))
    assert D("100953.83") - f.from_capital == D("100453.83")
    assert not f.final_settlement


def test_fall_35_ej_finansierat_utan_bolagskonto():
    f = claim_funding(D("100.00"), D("80.00"), D("0.00"))
    assert (f.from_capital, f.company_support, f.unfunded) == (D("80.00"), D("0.00"), D("20.00"))
    assert f.gross == f.from_capital + f.company_support + f.unfunded


def test_bolagsstod_tacker_bristen_sa_langt_det_racker():
    assert claim_funding(D("100.00"), D("80.00"), D("50.00")).plain() == {
        "gross_sek": "100.00", "from_capital_sek": "80.00", "company_support_sek": "20.00", "unfunded_sek": "0.00",
        "final_settlement": False}
    partly = claim_funding(D("100.00"), D("80.00"), D("5.00"))
    assert (partly.company_support, partly.unfunded) == (D("5.00"), D("15.00"))


def test_fall_32_sista_ratten_betalar_ut_hela_kapitalet():
    f = claim_funding(D("100.00"), D("140.00"), D("0.00"), final=True)
    assert (f.gross, f.from_capital, f.unfunded, f.final_settlement) == (D("140.00"), D("140.00"), D("0"), True)
    assert D("140.00") - f.from_capital == 0  # C = 0 efter slutavräkningen


def test_fall_33_sista_ratten_med_c_under_m_fylls_ut():
    f = claim_funding(D("100.00"), D("80.00"), D("5000.00"), final=True)
    assert (f.gross, f.from_capital, f.company_support, f.unfunded) == (D("100.00"), D("80.00"), D("20.00"), D("0"))


def test_debiteringen_fordelas_i_oren_pa_sparen():
    shares = debit_tracks(D("1.00"), [D("1.00"), D("1.00"), D("1.00")])
    assert sum(shares) == D("1.00") and sorted(shares) == [D("0.33"), D("0.33"), D("0.34")]
    assert debit_tracks(D("2.00"), [D("2.00"), D("0.00")]) == [D("2.00"), D("0.00")]


@pytest.mark.parametrize("amount, capital, company", [
    (D("0.00"), D("1.00"), D("0.00")), (D("-1.00"), D("1.00"), D("0.00")), (D("1.001"), D("1.00"), D("0.00")),
    (D("1.00"), D("-0.01"), D("0.00")), (D("1.00"), D("1.00"), D("-1.00"))])
def test_ogiltiga_belopp_avvisas(amount, capital, company):
    with pytest.raises(ClaimError):
        claim_funding(amount, capital, company)


def test_debit_over_kapitalet_avvisas():
    with pytest.raises(ClaimError, match="överskrider"):
        debit_tracks(D("3.01"), [D("1.00"), D("2.00")])
