"""Värderingskörningar i tjänstelagret (A6, B-042): körning, lagring, lås, åtkomst och migration.

Kontrollfallen K5–K7 och K10 i VARDERINGSKONTRAKT.md §7 prövas här mot sparade körningar; K1–K4,
K8 och K9 i tests/test_fta_valuation.py. SQLite i minnet med demobeståndet. SIM-V-2026-01 och
FI-SIM-2026-10 gäller i testet från 2026-03-31, så att basvärderingar per 2026-06-30 och 2026-09-30
går att göra; i startgrunderna gäller de först från 2026-12-31 och 2026-10-31.
Läsdag 2026-11-02: PR-ITP1 v1.0 gäller.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

import pytest
from sqlalchemy import create_engine, delete, inspect, select
from sqlalchemy.pool import StaticPool

from agents import compile_profile
from agents.ecosystem import Ecosystem
from agents.skills import SkillRegistry
from analytics.portfolio_snapshot import MIN_CELL
from models import (
    Base,
    PolicyState,
    ProductParameter,
    ValuationBasis,
    ValuationExtractRecord,
    ValuationResult,
    ValuationRun,
)
from services import (
    Actor,
    MemoryEventLog,
    OperationContext,
    ProductRuleCatalog,
    ServiceLayer,
    default_registry,
)
from services.db import session_factory_for
from services.errors import AccessDeniedError, BlockedError, InvalidInputError
from services.operations import common
from services.operations.valuations import opening_balance
from services.service import ResultStatus
from services.valuation import compute_valuation
from utils.demo_data import create_demo_database

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 11, 2)
Q2, Q3 = date(2026, 6, 30), date(2026, 9, 30)
KARL = OperationContext(actor=Actor.human("karl"), reason="Kvartalsvärdering")
SYSTEM = OperationContext(actor=Actor.system("flow:valuation_close"), reason="Systemsteg i valuation_close")
AGENT = OperationContext(actor=Actor.agent("actuary_agent", team="aktuarie"), run_id="run-akt")
SCENARIO = {"purpose": "scenario", "basis_code": "SIM-V-2026-01", "curve_code": "FI-SIM-2026-10"}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


def _demo(earlier_bases: bool):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False, today=date(2026, 10, 27))
    factory = session_factory_for(engine)
    if earlier_bases:
        with factory() as s:
            for row in s.scalars(select(ValuationBasis).where(ValuationBasis.code.in_(("SIM-V-2026-01", "FI-SIM-2026-10")))):
                row.valid_from = date(2026, 3, 31)  # kontrollsumman gäller innehållet, inte giltigheten
            s.commit()
    return engine, factory


@pytest.fixture
def demo():
    engine, factory = _demo(earlier_bases=True)
    yield factory
    engine.dispose()


@pytest.fixture
def startgrunder():
    engine, factory = _demo(earlier_bases=False)
    yield factory
    engine.dispose()


def layer(factory) -> ServiceLayer:
    return ServiceLayer(session_factory=factory, events=MemoryEventLog(), rules=ProductRuleCatalog(today=TODAY))


@pytest.fixture
def service(demo):
    return layer(demo)


def run(service, day=Q3, ctx=SYSTEM, **extra):
    return service.execute("run_valuation", ctx, {"valuation_date": day.isoformat(), **extra}).output


class TestKorning:
    def test_basvarderingen_sparas_som_utkast_med_kontrollsummor(self, service, demo):
        out = run(service)
        assert (out.status, out.purpose, out.version, out.source) == ("draft", "base", 1, "reconstructed_s04")
        assert (out.basis_code, out.curve_code, str(out.tax_reduction)) == ("SIM-V-2026-01", "FI-SIM-2026-10", "0.00354")
        assert out.checks_passed and {c.name for c in out.checks} >= {"K1 motorn", "K10 summakontroll"}
        assert out.code_version.startswith("fta-1.0+") and len(out.result_checksum) == 64
        assert out.created_by == "flow:valuation_close" and "S-04" in out.source_note
        with demo() as s:
            extract = s.scalar(select(ValuationExtractRecord))
            assert extract.checksum == out.extract_checksum and extract.approved
            assert extract.policies == len(extract.content["policies"]) == out.policies

    def test_k6_samma_utdrag_grund_och_kod_ger_samma_resultat_och_hashar(self, service, demo):
        first, second = run(service), run(service)
        assert (first.version, second.version) == (1, 2)
        same = ("extract_checksum", "basis_checksum", "curve_checksum", "code_version", "result_checksum", "fta_sek",
                "surplus_sek", "deficit_sek")
        assert {k: getattr(first, k) for k in same} == {k: getattr(second, k) for k in same}
        with demo() as s:
            assert len(s.scalars(select(ValuationExtractRecord)).all()) == 1  # samma utdrag sparas en gång

    def test_k10_summakontroll_pa_hela_bestandet(self, service, demo):
        out = run(service)
        assert out.balance_check == "stämmer på öret"
        assert out.surplus_sek - out.deficit_sek == out.capital_sek - out.fta_sek
        with demo() as s:
            stored = s.scalar(select(ValuationRun))
            assert stored.surplus_sek - stored.deficit_sek == stored.capital_sek - stored.fta_sek
            c = compute_valuation(s, Q3)
            assert c.totals.balances and c.totals.policies == stored.policies
            assert sum((v.surplus - v.deficit for v in c.values), 0) == c.totals.capital - c.totals.fta

    def test_k7_sma_celler_doljs_aven_kompletterande(self, service, demo):
        run(service)
        with demo() as s:
            rows = s.scalars(select(ValuationResult)).all()
            c = compute_valuation(s, Q3)
        counts = {k: t.policies for k, t in c.segments.items()}
        hidden = [r for r in rows if r.hidden_reason]
        assert all(r.policies is None and r.fta_sek is None and r.surplus_sek is None for r in hidden)
        assert all(r.hidden_reason for r in rows if 0 < counts[(r.state, r.cohort)] < MIN_CELL)
        assert not hidden or sum(counts[(r.state, r.cohort)] for r in hidden) >= MIN_CELL

    def test_ej_beraknade_fall_listas_per_orsak(self, service):
        out = run(service)
        assert out.not_calculated and all("PR-009" in n.reason for n in out.not_calculated)
        assert all(n.policies is None or n.policies >= MIN_CELL for n in out.not_calculated)

    def test_basvardering_kraver_kvartalsslut_men_scenario_far_annat_manadsslut(self, service):
        with pytest.raises(BlockedError, match="kvartalsslut"):
            run(service, date(2026, 8, 31))
        out = run(service, date(2026, 8, 31), purpose="scenario")
        assert out.purpose == "scenario" and "aldrig bas" in out.purpose_note

    def test_utan_gallande_grund_stoppar_basen_men_scenariot_anger_grunden(self, startgrunder):
        service = layer(startgrunder)
        with pytest.raises(BlockedError, match="Ingen antagen grund i SIM-V"):
            run(service)
        out = run(service, **SCENARIO)
        assert (out.purpose, out.basis_code, out.checks_passed) == ("scenario", "SIM-V-2026-01", True)

    def test_bas_med_uttrycklig_grund_ar_fel(self, service):
        with pytest.raises(InvalidInputError, match="gäller datumet"):
            run(service, basis_code="SIM-V-2026-01")

    def test_underkant_utdrag_stoppar_vardering(self, service, demo):
        with demo() as s:
            s.execute(delete(PolicyState).where(PolicyState.id == s.scalar(select(PolicyState.id).limit(1))))
            s.commit()
        with pytest.raises(BlockedError, match="underkänt"):
            run(service)

    def test_saknad_skattesats_stoppar(self, service, demo):
        with demo() as s:
            s.execute(delete(ProductParameter).where(ProductParameter.key == "customer_tax_rate",
                                                     ProductParameter.valid_from == date(2026, 1, 1)))
            s.commit()
        with pytest.raises(BlockedError, match="s_y saknas"):
            run(service)

    def test_motivering_kravs(self, service):
        with pytest.raises(Exception, match="motivering"):
            run(service, ctx=replace(SYSTEM, reason=None))


class TestLas:
    def test_las_och_rattelse_ersatter_foregaende(self, service):
        first = run(service)
        locked = service.execute("lock_valuation", KARL, {"run_id": str(first.run_id)}).output
        assert (locked.status, locked.locked_by, locked.lock_note) == ("locked", "karl", "Kvartalsvärdering")
        second = run(service)
        relocked = service.execute("lock_valuation", replace(KARL, reason="Rättelse"), {"run_id": str(second.run_id)}).output
        assert relocked.supersedes_run_id == first.run_id
        old = service.execute("get_valuation_run", KARL, {"run_id": str(first.run_id)}).output
        assert old.status == "superseded"

    def test_last_eller_ersatt_korning_kan_inte_lasas_igen(self, service):
        first = run(service)
        service.execute("lock_valuation", KARL, {"run_id": str(first.run_id)})
        with pytest.raises(BlockedError, match="bara ett utkast"):
            service.execute("lock_valuation", KARL, {"run_id": str(first.run_id)})

    def test_scenario_kan_aldrig_lasas(self, service):
        out = run(service, **SCENARIO)
        with pytest.raises(BlockedError, match="aldrig bas"):
            service.execute("lock_valuation", KARL, {"run_id": str(out.run_id)})

    def test_andrat_utdrag_stoppar_laset(self, service, demo):
        out = run(service)
        with demo() as s:
            row = s.scalar(select(ValuationExtractRecord))
            content = json.loads(json.dumps(row.content))
            content["policies"][0]["capital"] = "1.00"
            row.content = content
            s.commit()
        with pytest.raises(BlockedError, match="Datautdragets kontrollsumma"):
            service.execute("lock_valuation", KARL, {"run_id": str(out.run_id)})

    def test_andrad_grund_stoppar_laset(self, service, demo):
        out = run(service)
        with demo() as s:
            row = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "SIM-V-2026-01"))
            row.assumptions = {**row.assumptions, "option_adjustment": "annat"}
            s.commit()
        with pytest.raises(BlockedError, match="SIM-V-2026-01 stämmer inte"):
            service.execute("lock_valuation", KARL, {"run_id": str(out.run_id)})

    def test_k5_ib_i_period_tva_ar_ub_i_period_ett(self, service, demo):
        q2 = run(service, Q2)
        service.execute("lock_valuation", KARL, {"run_id": str(q2.run_id)})
        q3 = run(service, Q3)
        service.execute("lock_valuation", KARL, {"run_id": str(q3.run_id)})
        with demo() as s:
            ib = opening_balance(s, Q3)
            assert ib.id == q2.run_id and ib.fta_sek.quantize(q2.fta_sek) == q2.fta_sek
            assert opening_balance(s, date(2026, 12, 31)).id == q3.run_id
            assert opening_balance(s, Q2) is None
            assert compute_valuation(s, Q2).result_checksum == ib.result_checksum  # samma UB vid omräkning


class TestAtkomst:
    def test_agenten_laser_bara_aggregat(self, service, demo):
        out = run(service)
        listing = service.execute("list_valuation_runs", AGENT, {"valuation_date": Q3.isoformat()}).output
        assert [r.run_id for r in listing.runs] == [out.run_id]
        detail = service.execute("get_valuation_run", AGENT, {"run_id": str(out.run_id)}).output
        text = detail.model_dump_json()
        with demo() as s:
            extract = s.scalar(select(ValuationExtractRecord)).content
        assert not any(p["policy_id"] in text for p in extract["policies"])
        assert "birth_month" not in text and "guarantee_parts" not in text
        assert set(detail.quantities) >= {"fta_sek", "surplus_sek", "deficit_sek"}

    def test_agenten_kan_bara_foresla_korning_och_aldrig_lasa(self, service):
        proposed = service.execute("run_valuation", replace(AGENT, reason="Kvartal"), {"valuation_date": Q3.isoformat()})
        assert proposed.status == ResultStatus.PENDING_APPROVAL
        out = run(service)
        with pytest.raises(AccessDeniedError, match="endast handläggare"):
            service.execute("lock_valuation", replace(AGENT, reason="Lås"), {"run_id": str(out.run_id)})

    def test_aktuariens_profil_har_bara_lasverktygen(self, service):
        eco = Ecosystem.load()
        profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), service, agent_id="actuary_agent")
        tools = {d.skill for d in profile.visible()}
        assert {"list_valuation_runs", "get_valuation_run"} <= tools
        assert not tools & {"run_valuation", "lock_valuation"}

    def test_operationerna_i_registret(self, service):
        levels = {n: service.decision(n).effective.value for n in
                  ("run_valuation", "list_valuation_runs", "get_valuation_run", "lock_valuation")}
        assert levels == {"run_valuation": "APPROVAL", "list_valuation_runs": "AGENT", "get_valuation_run": "AGENT",
                          "lock_valuation": "HUMAN_ONLY"}


class TestMigration:
    def test_migrationen_kraver_postgres(self):
        from utils.migration_valuation_runs import migrate_valuation_runs

        with pytest.raises(RuntimeError, match="Postgres"):
            migrate_valuation_runs(create_engine("sqlite://"))

    def test_ddl_galler_bara_de_tre_tabellerna(self):
        from sqlalchemy.dialects import postgresql

        from utils.migration_valuation_runs import TABLES, compile_ddl

        statements = compile_ddl(postgresql.dialect())
        assert [s.split()[2] for s in statements if s.startswith("CREATE TABLE")] == list(TABLES)
        assert any("uq_valuation_runs_one_locked" in s and "WHERE" in s for s in statements)
        runs = next(s for s in statements if s.startswith("CREATE TABLE valuation_runs"))
        assert "ck_valuation_runs_scenario_never_locked CHECK" in runs and "REFERENCES valuation_extracts" in runs

    def test_migrationen_mot_postgres(self):
        from tests.conftest import seed_insurance
        from tests.test_services_postgres import TEST_URL, isolated_schema
        from utils.migration_valuation_runs import TABLES, migrate_valuation_runs

        if not TEST_URL:
            pytest.skip("SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")
        not_in_lakebase = {*TABLES, "portfolios", "portfolio_holdings", "trades"}
        with isolated_schema() as lakebase_like:
            tables = [t for t in Base.metadata.sorted_tables if t.name not in not_in_lakebase]
            Base.metadata.create_all(lakebase_like.engine, tables=[t for t in tables if t.name != "valuation_bases"])
            with pytest.raises(RuntimeError, match="valuation_bases"):
                migrate_valuation_runs(lakebase_like.engine)
            Base.metadata.create_all(lakebase_like.engine, tables=tables)
            seed_insurance(lakebase_like.session_factory)
            dry = migrate_valuation_runs(lakebase_like.engine)
            assert not dry.applied and not set(TABLES) & set(inspect(lakebase_like.engine).get_table_names())
            done = migrate_valuation_runs(lakebase_like.engine, dry_run=False)
            assert done.applied and done.row_counts == dry.row_counts
            assert migrate_valuation_runs(lakebase_like.engine, dry_run=False).already_applied
            columns = {t: {c["name"] for c in inspect(lakebase_like.engine).get_columns(t)} for t in TABLES}
            assert columns == {t: {c.name for c in Base.metadata.tables[t].columns} for t in TABLES}
            with lakebase_like.engine.begin() as conn:
                conn.exec_driver_sql("DROP TABLE valuation_results")
            with pytest.raises(RuntimeError, match="Bara"):
                migrate_valuation_runs(lakebase_like.engine)
