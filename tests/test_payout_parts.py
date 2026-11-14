"""Uttagsdelar och tre förlopp, paket B steg 1 (B-047, P1-PENSION-001 §4).

Modellens villkor, övergången från försäkringens uttagslägen (B-022) till uttagsdel 1,
läsningarnas skydd för agentroller, premiemottagaren per uttagsdel och demofilens uppgradering.
Migrationen mot Postgres provas i tests/test_migration_payout_parts.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from models import (
    Case,
    PayoutPart,
    PayoutPartState,
    Policy,
    PolicyBenefit,
    PolicyState,
)
from services import Actor, MemoryEventLog, OperationContext, ServiceLayer
from services.db import session_factory_for
from services.payout_parts import (
    NOT_READ_FOR_AGENT,
    PartView,
    parts_by_policy,
    payout_readable,
    receiving_parts,
    summary_state,
)
from services.payout_transition import apply_transition, plan_transition
from utils.demo_data import add_missing_demo_tables, create_demo_database

HUMAN = OperationContext(actor=Actor.human("karl"))
AGENT = OperationContext(actor=Actor.agent("case_handler", team="forsakring"), run_id="run-pb1")
TODAY = date(2026, 11, 14)


def _part(s, policy_id) -> PayoutPart:
    return s.scalar(select(PayoutPart).join(PolicyBenefit).where(PolicyBenefit.policy_id == policy_id))


def _legacy(s, policy_id, rows) -> None:
    """Ersätter försäkringens lägen med `rows` – gamla uttagslägen tillåts (som i en fil före steg 1)."""
    s.execute(text("PRAGMA ignore_check_constraints = ON"))
    for state in s.scalars(select(PolicyState).where(PolicyState.policy_id == policy_id)):
        s.delete(state)
    s.flush()
    for state, valid_from, valid_to in rows:
        s.add(PolicyState(policy_id=policy_id, state=state, valid_from=valid_from, valid_to=valid_to))
    s.flush()
    s.execute(text("PRAGMA ignore_check_constraints = OFF"))


@pytest.fixture
def old_db(insurance_db):
    """Testbeståndet som det såg ut före steg 1: inga uttagsdelar."""
    with insurance_db.session_factory() as s:
        for state in s.scalars(select(PayoutPartState)):
            s.delete(state)
        s.flush()
        for part in s.scalars(select(PayoutPart)):
            s.delete(part)
        s.commit()
    return insurance_db


class TestModellen:
    def test_hogst_tre_delar_och_delningens_falt(self, insurance_db):
        with insurance_db.session_factory() as s:
            part = _part(s, insurance_db.ids.policy)
            s.add(PayoutPart(benefit_id=part.benefit_id, part_number=4, split_from_part_id=part.id,
                             split_date=TODAY, split_share=Decimal("0.5"), share_of_origin=Decimal("0.5")))
            with pytest.raises(IntegrityError):
                s.flush()
            s.rollback()
        with insurance_db.session_factory() as s:
            part = _part(s, insurance_db.ids.policy)
            s.add(PayoutPart(benefit_id=part.benefit_id, part_number=2, share_of_origin=Decimal("0.5")))
            with pytest.raises(IntegrityError):  # del 2 utan delningens länk, dag och andel
                s.flush()
            s.rollback()
        with insurance_db.session_factory() as s:
            part = _part(s, insurance_db.ids.policy)
            s.add(PayoutPart(benefit_id=part.benefit_id, part_number=2, split_from_part_id=part.id,
                             split_date=TODAY, split_share=Decimal("0.05"), share_of_origin=Decimal("0.05")))
            with pytest.raises(IntegrityError):  # minsta delning 10 % (PR-ITP1-024)
                s.flush()
            s.rollback()

    def test_ett_oppet_lage_och_avslut_kraver_skal(self, insurance_db):
        with insurance_db.session_factory() as s:
            part = _part(s, insurance_db.ids.policy)
            s.add(PayoutPartState(payout_part_id=part.id, state="in_payout", valid_from=TODAY))
            with pytest.raises(IntegrityError):  # två öppna lägen
                s.flush()
            s.rollback()
        with insurance_db.session_factory() as s:
            part = _part(s, insurance_db.ids.policy)
            (first,) = part.states
            first.valid_to = date(2026, 10, 31)
            s.add(PayoutPartState(payout_part_id=part.id, state="ended", valid_from=TODAY, valid_to=None))
            with pytest.raises(IntegrityError):  # ended utan skäl
                s.flush()
            s.rollback()
        with insurance_db.session_factory() as s:
            part = _part(s, insurance_db.ids.policy)
            (first,) = part.states
            first.valid_to = date(2026, 10, 31)
            s.add(PayoutPartState(payout_part_id=part.id, state="planned", valid_from=TODAY))
            with pytest.raises(IntegrityError):  # en plan är inget läge
                s.flush()
            s.rollback()

    def test_premieforloppet_har_bara_tva_lagen(self, insurance_db):
        with insurance_db.session_factory() as s:
            current = s.scalar(select(PolicyState).where(PolicyState.valid_to.is_(None)))
            current.valid_to = date(2026, 10, 31)
            s.add(PolicyState(policy_id=current.policy_id, state="in_payout", valid_from=TODAY))
            with pytest.raises(IntegrityError):
                s.flush()
            s.rollback()


class TestOvergangen:
    def test_varje_forman_far_del_1_ej_startad_utan_annan_andring(self, old_db):
        with old_db.session_factory() as s:
            states_before = [(r.state, r.valid_from, r.valid_to) for r in s.scalars(select(PolicyState))]
            plan = plan_transition(s)
            assert (plan.benefits, plan.parts_to_create, plan.moved, plan.problems) == (1, 1, [], [])
            apply_transition(s, TODAY)
            s.commit()
        with old_db.session_factory() as s:
            part = _part(s, old_db.ids.policy)
            (state,) = part.states
            assert (part.part_number, part.share_of_origin) == (1, Decimal(1))
            assert (state.state, state.valid_from, state.valid_to) == ("not_started", date(2015, 1, 1), None)
            assert [(r.state, r.valid_from, r.valid_to) for r in s.scalars(select(PolicyState))] == states_before
            assert s.scalar(select(Case)) is None
            assert plan_transition(s).nothing_to_do  # idempotent

    def test_fribrev_fore_uttaget_oppnas_igen(self, old_db):
        with old_db.session_factory() as s:
            _legacy(s, old_db.ids.policy, [
                ("premium_paying", date(2015, 1, 1), date(2025, 12, 31)),
                ("paid_up", date(2026, 1, 1), date(2026, 5, 31)),
                ("in_payout", date(2026, 6, 1), date(2026, 8, 31)),
                ("payout_paused", date(2026, 9, 1), None),
            ])
            done = apply_transition(s, TODAY)
            s.commit()
        (moved,) = done.moved
        assert moved.premium_action == "reopen" and moved.case_number == "CASE-000001"
        with old_db.session_factory() as s:
            premium = sorted((r.state, r.valid_from, r.valid_to) for r in s.scalars(select(PolicyState)))
            assert premium == [("paid_up", date(2026, 1, 1), None),
                               ("premium_paying", date(2015, 1, 1), date(2025, 12, 31))]
            part = _part(s, old_db.ids.policy)
            assert sorted((r.state, r.valid_from, r.valid_to) for r in part.states) == [
                ("in_payout", date(2026, 6, 1), date(2026, 8, 31)),
                ("not_started", date(2015, 1, 1), date(2026, 5, 31)),
                ("paused", date(2026, 9, 1), None),
            ]
            case = s.scalar(select(Case))
            assert (case.case_type, case.status, case.channel, case.created_by) == (
                "payout_reconstruction", "open", "system", "system:payout_transition")
            assert case.policy_id == old_db.ids.policy and case.details["payout_part"] == 1
            assert "planversion" in case.details["missing"]
            assert plan_transition(s).nothing_to_do

    def test_premiebetalande_till_anstallningens_slut_blir_fribrev(self, old_db):
        # David Dahls mönster i demon: premiebetalande till anställningens slut, sedan uttag
        with old_db.session_factory() as s:
            _legacy(s, old_db.ids.policy, [
                ("premium_paying", date(2015, 1, 1), date(2025, 12, 31)),
                ("in_payout", date(2026, 1, 1), None),
            ])
            (moved,) = apply_transition(s, TODAY).moved
            s.commit()
        assert moved.premium_action == "paid_up"
        with old_db.session_factory() as s:
            current = s.scalar(select(PolicyState).where(PolicyState.valid_to.is_(None)))
            assert (current.state, current.valid_from) == ("paid_up", date(2026, 1, 1))

    def test_premieforlopp_utan_kant_slut_lamnas_utan_oppet_lage(self, old_db):
        with old_db.session_factory() as s:
            _legacy(s, old_db.ids.policy, [
                ("premium_paying", date(2015, 1, 1), date(2025, 6, 30)),
                ("in_payout", date(2025, 7, 1), None),
            ])
            (moved,) = apply_transition(s, TODAY).moved
            s.commit()
        assert moved.premium_action == "none" and "okänt" in moved.premium_course
        with old_db.session_factory() as s:
            assert s.scalar(select(PolicyState).where(PolicyState.valid_to.is_(None))) is None

    @pytest.mark.parametrize(("rows", "problem"), [
        ([("premium_paying", date(2015, 1, 1), date(2025, 12, 31)), ("terminated", date(2026, 1, 1), None)],
         "PB10"),
        ([("premium_paying", date(2015, 1, 1), date(2024, 12, 31)), ("in_payout", date(2025, 1, 1), date(2025, 12, 31)),
          ("paid_up", date(2026, 1, 1), None)], "inte sist"),
        ([("paid_up", date(2015, 1, 1), date(2025, 12, 31)), ("in_payout", date(2026, 1, 1), date(2026, 3, 31)),
          ("payout_paused", date(2026, 5, 1), None)], "glapp"),
        ([("paid_up", date(2015, 1, 1), date(2025, 11, 30)), ("in_payout", date(2026, 1, 1), None)],
         "slutar inte dagen före"),
    ])
    def test_tvetydiga_monster_stoppar_utan_att_skriva(self, old_db, rows, problem):
        with old_db.session_factory() as s:
            _legacy(s, old_db.ids.policy, rows)
            s.commit()
        with old_db.session_factory() as s:
            assert any(problem in p for p in plan_transition(s).problems)
            with pytest.raises(ValueError, match="stoppas"):
                apply_transition(s, TODAY)
            s.rollback()
            assert s.scalar(select(PayoutPart)) is None and s.scalar(select(Case)) is None


class TestLasningarna:
    def test_sammanfattat_lage(self):
        def view(state):
            return PartView(1, Decimal(1), state, None, None)

        assert summary_state([view("ended"), view("in_payout")]) == "in_payout"
        assert summary_state([view("not_started"), view("paused")]) == "paused"
        assert summary_state([view("ended"), view("not_started")]) == "not_started"
        assert summary_state([view("ended")]) == "ended"
        assert summary_state([]) is None and summary_state([view(None)]) is None

    def test_agentroll_utan_ratt_laser_inte_uttagsdelarna(self):
        assert payout_readable(HUMAN.actor) and payout_readable(Actor.system("payout_transition"))
        for team in ("forsakring", "aktuarie", "compliance", None):
            assert payout_readable(Actor.agent("x", team=team)) is False

    def test_oversikten_visar_delarna_for_handlaggaren_men_inte_agenten(self, insurance_db):
        service = ServiceLayer(session_factory=insurance_db.session_factory, events=MemoryEventLog())
        human = service.execute("get_insured_overview", HUMAN, {"policy_number": "AL-000001"}).output
        (policy,) = human.policies
        (part,) = policy.payout_parts
        assert (part.part_number, part.state, part.valid_from) == (1, "not_started", date(2015, 1, 1))
        assert human.payout_parts_note is None
        agent = service.execute("get_insured_overview", AGENT, {"policy_number": "AL-000001"}).output
        assert agent.policies[0].payout_parts is None and agent.payout_parts_note == NOT_READ_FOR_AGENT
        assert agent.policies[0].current_state.state == "paid_up"

    def test_laget_vid_en_dag(self, insurance_db):
        from tests.conftest import start_payout

        start_payout(insurance_db, insurance_db.ids.policy, date(2026, 6, 1))
        with insurance_db.session_factory() as s:
            policy = insurance_db.ids.policy
            assert parts_by_policy(s, [policy])[policy][0].state == "in_payout"
            assert parts_by_policy(s, [policy], on=date(2026, 5, 31))[policy][0].state == "not_started"
            assert parts_by_policy(s, []) == {}


class TestPremiemottagaren:
    def test_bara_delar_som_inte_startat_under_hela_manaden(self, insurance_db):
        from tests.conftest import start_payout

        start_payout(insurance_db, insurance_db.ids.policy, date(2026, 6, 15))
        benefit = insurance_db.ids.benefit
        with insurance_db.session_factory() as s:
            assert [p.part_number for p in receiving_parts(s, [benefit], date(2026, 5, 1), date(2026, 5, 31))[benefit]] == [1]
            assert receiving_parts(s, [benefit], date(2026, 6, 1), date(2026, 6, 30)) == {}  # startar i månaden
            assert receiving_parts(s, [benefit], date(2026, 7, 1), date(2026, 7, 31)) == {}

    def test_delad_ratt_ger_flera_mottagare(self, insurance_db):
        benefit = insurance_db.ids.benefit
        with insurance_db.session_factory() as s:
            first = _part(s, insurance_db.ids.policy)
            first.share_of_origin = Decimal("0.6")
            second = PayoutPart(benefit_id=benefit, part_number=2, share_of_origin=Decimal("0.4"),
                                split_from_part_id=first.id, split_date=date(2026, 1, 1), split_share=Decimal("0.4"))
            s.add(second)
            s.flush()
            s.add(PayoutPartState(payout_part_id=second.id, state="not_started", valid_from=date(2026, 1, 1)))
            s.flush()
            found = receiving_parts(s, [benefit], date(2026, 10, 1), date(2026, 10, 31))[benefit]
            assert [p.part_number for p in found] == [1, 2]


class TestDemon:
    def test_david_dahl_har_uttag_pa_del_1_och_rekonstruktionsarende(self):
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        create_demo_database(engine, today=TODAY, with_proposals=False)
        with session_factory_for(engine)() as s:
            benefits = s.scalars(select(PolicyBenefit)).all()
            parts = s.scalars(select(PayoutPart)).all()
            assert len(parts) == len(benefits) and {p.part_number for p in parts} == {1}
            (case,) = s.scalars(select(Case)).all()
            assert (case.case_number, case.case_type) == ("CASE-000001", "payout_reconstruction")
            policy = s.get(Policy, case.policy_id)
            current = s.scalar(select(PolicyState).where(PolicyState.policy_id == policy.id,
                                                         PolicyState.valid_to.is_(None)))
            assert (current.state, current.valid_from) == ("paid_up", date(2024, 5, 1))
            assert parts_by_policy(s, [policy.id])[policy.id][0].state == "in_payout"
            assert plan_transition(s).nothing_to_do

    def test_aldre_demofil_far_delarna(self):
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        create_demo_database(engine, today=TODAY, with_proposals=False, with_older_cohort=False)
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE payout_part_states"))
            conn.execute(text("DROP TABLE payout_parts"))
        add_missing_demo_tables(engine)
        with session_factory_for(engine)() as s:
            benefits = s.scalars(select(PolicyBenefit.id)).all()
            assert sorted(p.benefit_id for p in s.scalars(select(PayoutPart))) == sorted(benefits)
            assert plan_transition(s).nothing_to_do
        add_missing_demo_tables(engine)  # en andra gång gör ingenting
        with session_factory_for(engine)() as s:
            assert len(s.scalars(select(PayoutPart)).all()) == len(benefits)
