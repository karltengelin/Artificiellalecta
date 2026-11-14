"""Aggregerat bestånds- och premieunderlag för aktuariens tjänster (A2, B-042).

Lokala prov med SQLite och demobestånd.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from analytics.portfolio_snapshot import (
    COMPLEMENTARY,
    PRIMARY,
    birth_year,
    cohort_of,
    suppress_counts,
    suppress_sets,
)
from services import (
    Actor,
    MemoryEventLog,
    OperationContext,
    ServiceLayer,
)
from services.db import session_factory_for
from services.errors import InvalidInputError
from services.operations import common
from services.payout_parts import NOT_READ_FOR_AGENT
from utils.demo_data import create_demo_database

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 10, 27)
AGENT = OperationContext(actor=Actor.agent("actuary_agent", team="aktuarie"))
HUMAN_CTX = OperationContext(actor=Actor.human("karl"))


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


@pytest.fixture
def demo():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False, today=TODAY)
    yield session_factory_for(engine)
    engine.dispose()


@pytest.fixture
def service(demo):
    return ServiceLayer(session_factory=demo, events=MemoryEventLog())


def read(service, op, year=2025, ctx=AGENT):
    return service.execute(op, ctx, {"year": year}).output


class TestAggregat:
    def test_bestandet_summerar_och_saknar_personuppgifter(self, service):
        s = read(service, "get_portfolio_snapshot", 2026)
        shown = sum(c.policies or 0 for c in s.by_state)
        # Aktuarieagentens roll läser inte uttagsdelarna (P1-PENSION-001 §12): pensionscellerna är ej lästa
        assert s.payout_states_read is False
        not_read = {c.key for c in s.by_state if c.hidden_reason == NOT_READ_FOR_AGENT}
        assert not_read == {"in_payout", "payout_paused", "terminated"}
        hidden = [c for c in s.by_state if c.policies is None and c.key not in not_read]
        # De dolda lägena omfattar tillsammans minst tio försäkringar, så ingen kan räknas fram ur totalen
        assert s.policies_total == 35 and (not hidden or s.policies_total - shown >= 10)
        assert {c.hidden_reason for c in hidden} <= {PRIMARY, COMPLEMENTARY}

    def test_mansklig_lasare_ser_pensionsforloppet(self, service):
        s = read(service, "get_portfolio_snapshot", 2026, ctx=HUMAN_CTX)
        assert s.payout_states_read is True
        assert NOT_READ_FOR_AGENT not in {c.hidden_reason for c in s.by_state}
        assert s.as_of_date == TODAY and s.min_cell_size == 10
        raw = s.model_dump_json()
        assert not any(ch.isdigit() and len(ch) == 12 for ch in raw.split('"'))  # inga personnummer
        assert "first_name" not in raw and "salary" not in raw

    def test_kohorter_doljs_med_kompletterande_doljning(self, service):
        cells = {c.key: c for c in read(service, "get_portfolio_snapshot", 2026).by_cohort}
        hidden = [c for c in cells.values() if c.policies is None]
        assert hidden and {c.hidden_reason for c in hidden} <= {PRIMARY, COMPLEMENTARY}
        in_force = read(service, "get_portfolio_snapshot", 2026).policies_in_force
        assert in_force - sum(c.policies or 0 for c in cells.values()) >= 10

    def test_premier_per_manad_stammer_med_ledningsmattet(self, service):
        flows = read(service, "get_premium_flows", 2025)
        assert [m.month.month for m in flows.months] == list(range(1, 13)) and flows.period_to == date(2026, 1, 1)
        november = next(m for m in flows.months if m.month == date(2025, 11, 1))
        metrics = service.execute("get_company_metrics", AGENT, {"month": "2025-11-01"}).output
        assert november.paid_sek == metrics.paid_sek
        assert flows.total_paid_sek == sum(m.paid_sek for m in flows.months)
        assert flows.transfers_in_sek is None and "Flytt" in flows.transfers_note

    def test_innevarande_manad_ingar_inte(self, service):
        flows = read(service, "get_premium_flows", 2026)
        assert flows.months[-1].month == date(2026, 9, 1) and flows.period_to == date(2026, 10, 1)

    def test_litet_bestand_doljs(self, insurance_db):
        small = ServiceLayer(session_factory=insurance_db.session_factory, events=MemoryEventLog())
        s = read(small, "get_portfolio_snapshot", 2026)
        assert s.policies_total is None and s.insured_in_force is None
        flows = read(small, "get_premium_flows", 2025)
        assert flows.total_state == "suppressed" and flows.total_paid_sek is None
        assert all(m.paid_sek is None or m.persons == 0 for m in flows.months)

    @pytest.mark.parametrize("year", [2027, 2022])
    def test_bara_ar_med_historik(self, service, year):
        with pytest.raises(InvalidInputError):
            read(service, "get_portfolio_snapshot", year)

    def test_agenten_far_inte_bredda_urvalet(self, service):
        with pytest.raises(InvalidInputError):
            service.execute("get_premium_flows", AGENT, {"year": 2025, "employer": "all"})

    def test_doljning_och_fodelsear(self):
        assert suppress_counts({"a": 0, "b": 5, "c": 12, "d": 30}) == {"b": PRIMARY, "c": COMPLEMENTARY}
        assert suppress_counts({"a": 15, "b": 20}) == {}
        months = {date(2025, 1, 1): {1, 2, 3}, date(2025, 2, 1): set(range(1, 12))}
        assert suppress_sets(months) == {date(2025, 1, 1): PRIMARY, date(2025, 2, 1): COMPLEMENTARY}
        assert (birth_year("196203150123"), birth_year("19620375012x"), birth_year("196213150123")) == (1962, None, None)
        assert birth_year("196203750123") == 1962  # samordningsnummer
        assert (cohort_of(1962), cohort_of(None)) == ("1960–1969", "okänt")
