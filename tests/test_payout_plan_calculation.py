"""Uttagsplanens rena beräkning (paket B steg 4, Karls val V1–V11): kalender, frist, belopp och omräkning.

Verifieringsfallen ur P1-PENSION-001 §11 som inte kräver databas: 3–6 och 8–12, samt kalenderdelen av 1, 2
och 7. Hela flödet med journal och stängning provas i test_payout_plans.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from services.capital_ledger import Track
from services.payout_plans import split_amounts, split_guarantee
from skills.calculation import payout_plan as pp
from utils.bank_calendar import next_bank_day

BIRTH = date(1960, 11, 2)  # fyller 66 i november 2026
NOV26 = date(2026, 11, 1)


def m(year: int, month: int) -> date:
    return date(year, month, 1)


class TestKalender:
    def test_fall_1_standardstart_vid_66(self):
        start = pp.sixty_six_month(BIRTH)
        plan = pp.Schedule(start, None)
        assert start == NOV26 and plan.has_right(NOV26) and not plan.has_right(m(2026, 10))
        assert next_bank_day(m(2026, 12)) == date(2026, 12, 1)  # betalning för november
        assert plan.end_month is None and plan.form == "lifelong"

    def test_fall_2_uppskov_till_72_utan_mellanliggande_ratt(self):
        plan = pp.start_plan(m(2032, 11), None, BIRTH, current=None, change_month=NOV26)
        assert not any(plan.has_right(m(y, mo)) for y in range(2026, 2033) for mo in range(1, 13) if m(y, mo) < m(2032, 11))
        assert plan.has_right(m(2032, 11)) and plan.rights_before(m(2032, 11)) == 0
        # Ingen maxålder: uppskov till 80 godkänns också (PR-ITP1-003)
        assert pp.start_plan(m(2040, 11), None, BIRTH, current=None, change_month=NOV26).first_right == m(2040, 11)

    def test_fall_3_sen_begaran_ger_nasta_mojliga_manad(self):
        assert pp.deadline_for(m(2026, 12)) == date(2026, 11, 30)
        received = date(2026, 12, 1)
        assert received > pp.deadline_for(m(2026, 12))
        assert pp.next_possible_month(received) == m(2027, 1)
        assert pp.next_possible_month(date(2026, 11, 30)) == m(2026, 12)

    def test_fall_4_tidsbegransad_60_och_59(self):
        plan = pp.start_plan(NOV26, 60, BIRTH, current=None, change_month=NOV26)
        assert plan.end_month == m(2031, 10)
        assert plan.remaining_from(NOV26) == 60 and not plan.has_right(m(2031, 11))
        with pytest.raises(pp.PlanError, match="minst 60"):
            pp.start_plan(NOV26, 59, BIRTH, current=None, change_month=NOV26)

    def test_fall_5_paus_efter_12_av_60(self):
        plan = pp.Schedule(NOV26, 60)
        assert plan.rights_before(m(2027, 11)) == 12
        paused = pp.pause_plan(plan, m(2027, 11), m(2028, 2))
        assert not paused.has_right(m(2027, 12)) and paused.has_right(m(2028, 2))
        assert paused.remaining_from(m(2028, 2)) == 48
        assert paused.end_month == m(2032, 1)
        # Pausmånaderna förbrukar inget: annuitetsfaktorn utesluter dem
        args = paused.factor_arguments(date(2027, 10, 31))
        assert args["payments"] == 48 and args["paused"] == [m(2027, 11), m(2027, 12), m(2028, 1)]

    def test_paus_kraver_paborjad_del_och_aterstående_ratt(self):
        with pytest.raises(pp.PlanError, match="påbörjad"):
            pp.pause_plan(pp.Schedule(m(2027, 1), 60), m(2027, 1), m(2027, 3))
        with pytest.raises(pp.PlanError, match="sista"):
            pp.pause_plan(pp.Schedule(NOV26, 60), m(2031, 11), m(2032, 1))

    def test_fall_6_forlangning_och_for_sen_forlangning(self):
        plan = pp.Schedule(NOV26, 60)
        longer = pp.extend_plan(plan, 120, m(2027, 11))
        assert longer.remaining_from(m(2027, 11)) == 108 and longer.first_right == NOV26
        with pytest.raises(pp.PlanError, match="för sent"):
            pp.extend_plan(plan, 120, m(2031, 11))
        with pytest.raises(pp.PlanError, match="förkortning"):
            pp.extend_plan(plan, 48, m(2027, 11))
        with pytest.raises(pp.PlanError, match="livsvarig"):
            pp.extend_plan(pp.Schedule(NOV26, None), 120, m(2027, 11))
        assert pp.extend_plan(plan, None, m(2027, 11)).form == "lifelong"

    def test_fall_8_uttag_fore_66_blockeras(self):
        with pytest.raises(pp.PlanError, match="PB1"):
            pp.start_plan(m(2026, 10), None, BIRTH, current=None, change_month=m(2026, 10))

    def test_start_efter_forsta_ratt_avslas(self):
        with pytest.raises(pp.PlanError, match="paus eller förlängning"):
            pp.start_plan(m(2027, 6), None, BIRTH, current=pp.Schedule(NOV26, None), change_month=m(2027, 1))


class TestBelopp:
    def test_fall_9_max_inte_summa(self):
        assert pp.pension_amount(Decimal(100), Decimal(130))["m_sek"] == Decimal("130.00")
        result = pp.pension_amount(Decimal(100), Decimal(80))
        assert result["m_sek"] == Decimal("100.00") and result["binding"] == "candidate"

    def test_fall_10_golv_for_livsvarig_under_60_rattigheter(self):
        lifelong = pp.Schedule(NOV26, None)
        at_20 = date(2028, 6, 1)  # rätt nr 20
        assert lifelong.rights_before(at_20) == 19
        floor = pp.amount_floor(lifelong, "pause", at_20, Decimal("130.00"), "lifelong")
        result = pp.pension_amount(Decimal(100), Decimal(120), floor)
        assert result["m_sek"] == Decimal("130.00") and result["binding"] == "floor"
        fixed = pp.Schedule(NOV26, 120)
        assert pp.amount_floor(fixed, "pause", at_20, Decimal("130.00"), "fixed_term") is None
        assert pp.pension_amount(Decimal(100), Decimal(120))["m_sek"] == Decimal("120.00")
        # En verklig förlängning till livsvarig ger ny nivå; efter 60 rättigheter gäller inget golv
        assert pp.amount_floor(lifelong, "extend", at_20, Decimal("130.00"), "lifelong") is None
        assert pp.amount_floor(lifelong, "pause", m(2031, 11), Decimal("130.00"), "lifelong") is None

    def test_fall_11_garantigolvet_avrundas_uppat(self):
        assert pp.pension_amount(Decimal("123.4567"), Decimal(100))["m_sek"] == Decimal("123.46")
        # Golvet avrundas uppåt även när vanlig avrundning skulle ge ett öre mindre
        result = pp.pension_amount(Decimal("123.4512"), Decimal(100))
        assert result["m_sek"] == Decimal("123.46") and result["binding"] == "guarantee"

    def test_fall_12_vardebevarande_omrakning(self):
        value, g_new = pp.recalculated(Decimal(10), Decimal(200), Decimal(160))
        assert value == Decimal(2000) and g_new == Decimal("12.5")


class TestDelning:
    def test_fall_7_30_70(self):
        tracks = [Track(None, None, "", "", Decimal("60000.00")), Track(None, None, "", "", Decimal("40000.00"))]
        target, moves = split_amounts(tracks, Decimal("0.3"))
        assert target == Decimal("30000.00") and moves == [Decimal("18000.00"), Decimal("12000.00")]
        assert sum(t.balance for t in tracks) - target == Decimal("70000.00")
        keep, new = split_guarantee(Decimal("123.4567890123"), Decimal("0.3"))
        assert keep + new == Decimal("123.4567890123") and new == Decimal("37.0370367037")

    def test_fall_7_andel_under_10_procent_avslas(self):
        assert not pp.split_share_valid(Decimal("0.05")) and not pp.split_share_valid(Decimal("0.95"))
        assert pp.split_share_valid(Decimal("0.1")) and pp.split_share_valid(Decimal("0.9"))

    def test_oresfordelning_bevarar_summan(self):
        tracks = [Track(None, None, "", "", Decimal(v)) for v in ("33.33", "33.33", "33.34")]
        target, moves = split_amounts(tracks, Decimal("0.5"))
        assert target == Decimal("50.00") and sum(moves) == target


class TestKalenderVarden:
    def test_ogiltiga_scheman(self):
        with pytest.raises(pp.PlanError):
            pp.Schedule(date(2026, 11, 2), None)
        with pytest.raises(pp.PlanError):
            pp.Schedule(NOV26, 60, ((m(2027, 3), m(2027, 2)),))
        with pytest.raises(pp.PlanError, match="överlappar"):
            pp.Schedule(NOV26, 60, ((m(2027, 3), m(2027, 6)), (m(2027, 5), m(2027, 8))))

    def test_plain_tur_och_retur(self):
        plan = pp.pause_plan(pp.Schedule(NOV26, 60), m(2027, 11), m(2028, 2))
        assert pp.Schedule.from_plain(plan.plain()) == plan
