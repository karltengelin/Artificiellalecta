"""Beståndsinsikt för en ändrad produktparameter (Fas 3c 3c-B, B-035, tjänstelager.md §9.5).

Den rena beräkningen med undertryckning (analytics/parameter_impact.py), operationen
estimate_parameter_change_impact mot demobeståndet med och utan den äldre kohorten,
att baslinjen följer product_parameters, att inga individuppgifter lämnas ut och att
agenten får anropa operationen.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from agents.ecosystem import Ecosystem
from analytics.parameter_impact import (
    COMPLEMENTARY,
    COMPUTED,
    HIDDEN,
    MIN_CELL,
    NOT_COMPUTED,
    PRIMARY,
    PersonBasis,
    estimate_impact,
)
from models import InsuredPerson, ProductParameter
from services import Actor, AgentAccess, OperationContext, ServiceLayer, default_registry
from services.db import session_factory_for
from services.errors import BlockedError, ConflictError, InvalidInputError
from services.operations import common
from services.parameters import monthly_premium_parameters, premium_parameters
from skills.calculation.calculate_itp1_premium import DEFAULT_PARAMETERS, PremiumParameters, is_in_age_window
from utils.demo_data import OLDER_COHORT, OLDER_COHORT_YEARS, PERSONS, create_demo_database, older_cohort

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 10, 25)
OPERATION = "estimate_parameter_change_impact"
ACTUARY = OperationContext(actor=Actor.agent("actuary_agent", team="aktuarie"), run_id="run-3c-b")
HUMAN = OperationContext(actor=Actor.human("karl"))
AGE_67 = {"key": "premium_age_end", "value": "67", "valid_from": "2027-01-01"}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


def demo_service(**kwargs):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False, **kwargs)
    factory = session_factory_for(engine)
    return ServiceLayer(session_factory=factory), factory


@pytest.fixture
def demo():
    return demo_service()


def estimate(service, ctx=ACTUARY, **data):
    return service.execute(OPERATION, ctx, {**AGE_67, **data}).output


def year(result, y: int):
    return next(row for row in result.years if row.year == y)


# --- den rena beräkningen ----------------------------------------------------------------------

MONTHS_2027_2029 = [date(y, m, 1) for y in (2027, 2028, 2029) for m in range(1, 13)]
BASE = {m: DEFAULT_PARAMETERS for m in MONTHS_2027_2029}
SCEN = {m: PremiumParameters(age_end=67) for m in MONTHS_2027_2029}
IBB = {2027: Decimal("83400"), 2028: Decimal("83400"), 2029: Decimal("83400")}
#: Unga försäkrade som betalar premie i båda – så att baslinjens celler inte är små
YOUNG = [PersonBasis(date(1990, 5, 1), Decimal("40000")) for _ in range(MIN_CELL)]


def turning_66_in(y: int, count: int, salary="40000") -> list[PersonBasis]:
    """Födda i januari: 66 i januari år y och 67 i januari år y+1 – tolv extra månader, bara år y."""
    return [PersonBasis(date(y - 66, 1, 10), Decimal(salary)) for _ in range(count)]


def run(persons, baseline=BASE, scenario=SCEN, **kwargs):
    return estimate_impact(persons, months=MONTHS_2027_2029, baseline=baseline, scenario=scenario, ibb=IBB, **kwargs)


class TestBerakningen:
    def test_tio_berorda_visas_med_tolv_extra_manader_var(self):
        result = run(YOUNG + turning_66_in(2027, MIN_CELL))
        cell = result.years[0]
        assert (cell.year, cell.status, cell.affected, cell.extra_months) == (2027, COMPUTED, 10, 120)
        # 4,5 % av 40 000 kr = 1 800 kr i månaden, 120 månader = 216 000 kr
        assert cell.extra_volume == Decimal("216000")
        assert cell.scenario_volume - cell.baseline_volume == Decimal("216000")
        assert (result.first_affected_year, result.affected_total, result.extra_months_total) == (2027, 10, 120)
        assert result.hidden_cells == ()

    def test_nio_berorda_doljs_och_totalen_med(self):
        result = run(YOUNG + turning_66_in(2027, MIN_CELL - 1))
        cell = result.years[0]
        assert (cell.status, cell.affected, cell.extra_months, cell.extra_volume, cell.scenario_volume) == (
            HIDDEN, None, None, None, None)
        assert cell.baseline_volume is not None  # baslinjen har tio betalande
        assert result.totals_status == HIDDEN
        assert (result.affected_total, result.extra_months_total, result.extra_volume_total) == (None, None, None)
        assert ("2027: berörda, extra premiemånader, extra premievolym och scenario", PRIMARY) in result.hidden_cells

    def test_ingen_berord_ar_noll_inte_dold(self):
        result = run(YOUNG)
        assert [(c.status, c.affected, c.extra_volume) for c in result.years] == [(COMPUTED, 0, Decimal("0"))] * 3
        assert (result.first_affected_year, result.affected_total) == (None, 0)

    def test_kompletterande_doljning_mot_totalen(self):
        """2029 har tre berörda och döljs; totalen minus 2027 och 2028 skulle annars ge 2029 exakt."""
        result = run(YOUNG + turning_66_in(2027, 12) + turning_66_in(2028, 11) + turning_66_in(2029, 3))
        statuses = {c.year: (c.status, c.affected) for c in result.years}
        assert statuses == {2027: (COMPUTED, 12), 2028: (HIDDEN, None), 2029: (HIDDEN, None)}
        reasons = dict(result.hidden_cells)
        assert reasons["2029: berörda, extra premiemånader, extra premievolym och scenario"] == PRIMARY
        assert reasons["2028: berörda, extra premiemånader, extra premievolym och scenario"] == COMPLEMENTARY
        assert result.affected_total == 26  # de dolda cellerna omfattar tillsammans 14 ≥ 10

    def test_sma_baslinjeceller_och_populationen_doljs(self):
        result = run(YOUNG[:3] + turning_66_in(2027, 3), excluded=2)
        assert (result.persons, result.excluded) == (None, None)
        assert all(c.baseline_volume is None and c.scenario_volume is None for c in result.years)
        assert ("Antal aktiva försäkrade i beräkningen", PRIMARY) in result.hidden_cells
        assert ("Antal aktiva som inte kunde beräknas", PRIMARY) in result.hidden_cells

    def test_manad_utan_parametrar_ar_ej_beraknad_aldrig_noll(self):
        baseline = {**BASE, date(2028, 3, 1): "Produktparametrar saknas för 2028-03"}
        result = run(YOUNG + turning_66_in(2027, 12), baseline=baseline)
        cell = year(result, 2028)
        assert cell.status == NOT_COMPUTED and "2028-03" in cell.note
        assert (cell.affected, cell.extra_months, cell.extra_volume, cell.baseline_volume) == (None, None, None, None)
        assert year(result, 2027).status == COMPUTED
        assert (result.totals_status, result.affected_total, result.extra_volume_total) == (NOT_COMPUTED, None, None)

    def test_kant_slutdatum_for_anstallningen_foljs(self):
        leaving = [PersonBasis(date(1961, 1, 10), Decimal("40000"), last_month=date(2027, 6, 1))
                   for _ in range(MIN_CELL)]
        assert run(YOUNG + leaving).years[0].extra_months == 60  # januari–juni 2027

    def test_lagre_premiealder_ger_negativ_volym(self):
        scenario = {m: PremiumParameters(age_end=65) for m in MONTHS_2027_2029}
        persons = YOUNG + [PersonBasis(date(1962, 1, 10), Decimal("40000")) for _ in range(MIN_CELL)]
        cell = year(run(persons, scenario=scenario), 2027)
        assert (cell.affected, cell.extra_months, cell.extra_volume) == (10, -120, Decimal("-216000"))


# --- operationen mot demobeståndet --------------------------------------------------------------


class TestDemobestandet:
    def test_med_kohorten_berors_nagon_fore_2045(self, demo):
        service, _ = demo
        result = estimate(service, horizon_years=18)
        assert result.first_affected_year == 2027  # före 2045, då dagens äldsta i Lakebase fyller 66
        assert (result.period_from, result.period_to) == (date(2027, 1, 1), date(2044, 12, 1))
        first = year(result, 2027)
        assert first.status == "beräknad" and first.affected_persons >= MIN_CELL
        assert first.extra_premium_months > 0 and first.extra_premium_volume_sek > 0
        assert year(result, 2028).affected_persons >= MIN_CELL
        assert result.totals_status == "beräknad" and result.affected_persons_total >= MIN_CELL
        assert result.active_persons == 2 + len(OLDER_COHORT)  # Anna, Bertil och kohorten
        assert (result.current_value, result.value) == (Decimal("66"), Decimal("67"))
        assert result.current_version == "PR-ITP1-013 v1.0 från 2023-01-01"

    def test_standardhorisonten_tio_ar_visar_kohortens_tre_ar(self, demo):
        service, _ = demo
        result = estimate(service)
        assert len(result.years) == 10 and all(row.status == "beräknad" for row in result.years)
        # från 2029 betalar bara Anna och Bertil i baslinjen – de cellerna döljs
        assert {c.cell for c in result.hidden_cells} == {f"{y}: premievolym i baslinjen och scenario" for y in range(2029, 2037)}
        berorda = {row.year: row.affected_persons for row in result.years if row.affected_persons}
        assert set(berorda) == {2027, 2028, 2029} and min(berorda.values()) >= MIN_CELL

    def test_utan_kohorten_berors_ingen_pa_tio_ar(self):
        service, _ = demo_service(with_older_cohort=False)
        result = estimate(service)
        assert result.first_affected_year is None
        assert all(row.affected_persons == 0 for row in result.years)
        assert result.active_persons is None  # två aktiva – färre än 10

    def test_en_ensam_berord_doljs(self):
        """Utan kohorten berörs bara Bertil (född 1972), 2038–2039 – cellerna och totalen döljs."""
        service, _ = demo_service(with_older_cohort=False)
        result = estimate(service, horizon_years=13)
        assert result.first_affected_year == 2038
        assert [year(result, y).status for y in (2038, 2039)] == ["dold", "dold"]
        assert year(result, 2038).affected_persons is None and year(result, 2038).extra_premium_volume_sek is None
        assert (result.totals_status, result.affected_persons_total, result.extra_premium_volume_total_sek) == (
            "dold", None, None)

    def test_antagandena_star_i_svaret(self, demo):
        text = " ".join(estimate(demo[0]).assumptions)
        for phrase in ("dagens månadslön", "ingen lönetillväxt", "Ingen avkastning", "product_parameters",
                       "83 400 kr", "färre än 10 individer", "ej beräknat"):
            assert phrase in text


class TestBaslinjenFoljerParametrarna:
    def test_hojd_premiesats_i_tabellen_hojer_baslinjen(self, demo):
        service, factory = demo
        before = year(estimate(service), 2027).baseline_premium_volume_sek
        with factory() as s:
            row = s.scalar(select(ProductParameter).where(ProductParameter.key == "premium_rate_low"))
            row.value = Decimal("0.05")
        after = year(estimate(service), 2027).baseline_premium_volume_sek
        assert after > before

    def test_schemalagd_version_ar_baslinje(self, demo):
        service, _ = demo
        service.execute("schedule_product_parameter_change", OperationContext(actor=Actor.human("karl"), reason="Test"), {
            **AGE_67, "rule_version": "1.1", "source_ref": "K-SIM-ITP-2027", "decision_ref": "test",
        })
        same = estimate(service)
        assert (same.current_value, same.current_version) == (Decimal("67"), "PR-ITP1-013 v1.1 från 2027-01-01")
        assert same.first_affected_year is None and same.extra_premium_volume_total_sek == 0
        higher = estimate(service, value="68")
        from_66 = estimate(demo_service()[0], value="68")
        assert (higher.current_value, from_66.current_value) == (Decimal("67"), Decimal("66"))
        assert 0 < higher.extra_premium_volume_total_sek < from_66.extra_premium_volume_total_sek

    def test_senare_schemalagd_version_gor_scenariot_tvetydigt(self, demo):
        service, _ = demo
        service.execute("schedule_product_parameter_change", OperationContext(actor=Actor.human("karl"), reason="Test"), {
            **AGE_67, "valid_from": "2028-01-01", "rule_version": "1.1", "source_ref": "K-SIM-ITP-2027",
            "decision_ref": "test",
        })
        with pytest.raises(ConflictError, match="schemalagd version.*2028-01-01"):
            estimate(service)

    def test_saknad_parameter_ger_ej_beraknade_ar(self, demo):
        service, factory = demo
        with factory() as s:
            row = s.scalar(select(ProductParameter).where(ProductParameter.key == "premium_rate_high"))
            row.valid_to = date(2027, 12, 31)  # ingen version från 2028
        result = estimate(service, horizon_years=3)
        assert [r.status for r in result.years] == ["beräknad", "ej beräknad", "ej beräknad"]
        assert year(result, 2028).affected_persons is None and "premium_rate_high" in year(result, 2028).note
        assert result.totals_status == "ej beräknad" and result.extra_premium_volume_total_sek is None

    def test_manadsuppslaget_ger_samma_som_premium_parameters(self, demo):
        _, factory = demo
        months = [date(2026, 11, 1), date(2027, 1, 1), date(2030, 6, 1)]
        with factory() as s:
            series = monthly_premium_parameters(s, months)
            assert all(series[m] == premium_parameters(s, m) for m in months)
            assert all(series[m].versions == premium_parameters(s, m).versions for m in months)


class TestIngaIndividuppgifter:
    def test_svaret_innehaller_inga_personuppgifter(self, demo):
        service, factory = demo
        result = estimate(service, horizon_years=18)
        text = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
        with factory() as s:
            people = s.scalars(select(InsuredPerson)).all()
        assert len(people) == len(PERSONS) + len(OLDER_COHORT)
        for p in people:
            for value in (p.personal_id_number, p.personal_id_number[:8], f"{p.first_name} {p.last_name}", p.email,
                          common.birth_date(p.personal_id_number).isoformat(), f"{p.monthly_salary_sek:.2f}"):
                assert value not in text

    def test_svarets_falt_ar_bara_aggregat(self):
        op = default_registry.get(OPERATION)
        fields = set(op.output_model.model_fields) | set(op.output_model.model_fields["years"].annotation.__args__[0].model_fields)
        for name in fields:
            assert not any(word in name for word in ("personal", "birth", "salary", "name", "email", "policy_number"))


class TestAtkomst:
    def test_agenten_far_anropa_operationen(self, demo):
        service, _ = demo
        op = default_registry.get(OPERATION)
        assert (op.kind.value, op.pii) == ("read", False)
        assert service.decision(OPERATION).effective == AgentAccess.AGENT
        assert OPERATION in [o.name for o in service.operations_for_agents()]
        result = service.execute(OPERATION, ACTUARY, AGE_67)
        assert result.output.first_affected_year == 2027

    def test_monterad_i_bestand_med_parametermandat(self):
        eco = Ecosystem.load()
        assert OPERATION not in eco.unmapped_operations(default_registry)
        assert eco.pod_of(OPERATION) == "bestand" and eco.entry(OPERATION).parameter_mandate
        assert eco.pods["bestand"].mountable_by == ("aktuarie",)

    def test_handlaggaren_far_samma_svar(self, demo):
        service, _ = demo
        assert estimate(service, HUMAN) == estimate(service)

    @pytest.mark.parametrize("data", [
        {"valid_from": "2027-01-15"}, {"horizon_years": 0}, {"horizon_years": 46}, {"key": "pension_age"},
    ])
    def test_ogiltig_indata(self, demo, data):
        with pytest.raises(InvalidInputError):
            estimate(demo[0], **data)

    @pytest.mark.parametrize("data,message", [
        ({"valid_from": "2026-10-01"}, "tidigast 2026-11-01"),
        ({"value": "66.5"}, "hela år"),
        ({"value": "25"}, "premieåldern inte ihop"),
        ({"key": "premium_rate_low", "value": "4.5"}, "andel mellan 0 och 1"),
    ])
    def test_orimlig_andring_stoppas(self, demo, data, message):
        with pytest.raises(BlockedError, match=message):
            estimate(demo[0], **data)


# --- den äldre kohorten ---------------------------------------------------------------------------


class TestAldreKohorten:
    def test_samma_personer_varje_gang(self):
        assert older_cohort() == OLDER_COHORT

    def test_fodda_1959_till_1962_med_giltiga_unika_personnummer(self):
        years = [p.birth_date.year for p in OLDER_COHORT]
        assert {y: years.count(y) for y in set(years)} == dict(OLDER_COHORT_YEARS)
        numbers = [p.personal_id_number for p in OLDER_COHORT]
        assert len(set(numbers)) == len(numbers) and not set(numbers) & {p[0] for p in PERSONS}
        assert all(common.valid_personal_id_number(n) for n in numbers)
        assert all(common.birth_date(p.personal_id_number) == p.birth_date for p in OLDER_COHORT)

    def test_aktiva_med_forsakring_och_premiehistorik_i_demobestandet(self, demo):
        _, factory = demo
        cohort = {p.personal_id_number for p in OLDER_COHORT}
        with factory() as s:
            people = [p for p in s.scalars(select(InsuredPerson)) if p.personal_id_number in cohort]
            assert len(people) == len(OLDER_COHORT)
            for person in people:
                assert person.status == "active" and person.monthly_salary_sek > 0
                (policy,) = person.policies
                assert [st.state for st in policy.states] == ["premium_paying"]
                (benefit,) = policy.benefits
                born = common.birth_date(person.personal_id_number)
                # premier bara i premieåldern – de äldsta har färre rader
                assert all(is_in_age_window(born, tx.period_month) for tx in benefit.premium_transactions)
            assert sum(len(p.policies[0].benefits[0].premium_transactions) for p in people) > 0
