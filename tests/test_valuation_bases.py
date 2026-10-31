"""Antagandebiblioteket (A4, B-042): startgrunder, kontrollsummor, förslag, antagande och åtkomst.

SQLite i minnet med demobeståndet; migrationen provas mot isolerad Postgres när den finns.
Läsdag 2026-11-02: PR-ITP1 v1.0 gäller, garantigrunderna 2026-11 gäller och SIM-V-2026-01 är kommande.
"""

from __future__ import annotations

import copy
from datetime import date

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.pool import StaticPool

from agents import compile_profile
from agents.ecosystem import Ecosystem
from agents.skills import SkillRegistry
from models import Base, ValuationBasis
from services import Actor, MemoryEventLog, OperationContext, ProductRuleCatalog, ServiceLayer, default_registry
from services import valuation_bases as vb
from services.db import session_factory_for
from services.errors import AccessDeniedError, BlockedError, ConflictError, InvalidInputError
from services.operations import common
from utils.demo_data import create_demo_database

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 11, 2)
KARL = OperationContext(actor=Actor.human("karl"), reason="Antagandeöversyn 2026")
AGENT = OperationContext(actor=Actor.agent("actuary_agent", team="aktuarie"), reason="Förslag ur erfarenhetsanalysen")


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


@pytest.fixture
def demo():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False, today=date(2026, 10, 27))
    yield session_factory_for(engine)
    engine.dispose()


@pytest.fixture
def service(demo):
    return ServiceLayer(session_factory=demo, events=MemoryEventLog(), rules=ProductRuleCatalog(today=TODAY))


def proposal(code="SIM-V-2027-01", **changes) -> dict:
    raw = next(r for c, _, r, *_ in vb.START_BASES if c == "SIM-V-2026-01")
    assumptions = copy.deepcopy(raw)
    assumptions["mortality"]["improvement_per_year"] = "0.017"
    assumptions["expenses"]["deferred_sek_per_year"] = "195"
    return {"code": code, "title": "Värderingsgrund 2027", "assumptions": assumptions,
            "source_refs": "Erfarenhetsanalys 2026", "supersedes_code": "SIM-V-2026-01", **changes}


class TestStartgrunder:
    def test_gallande_kommande_och_upphorda(self, service):
        out = service.execute("list_valuation_bases", KARL, {}).output
        states = {b.code: b.state for b in out.bases}
        assert states == {"SIM-HIST-2023-01": "upphörd", "SIM-G-2026-01": "gällande", "SIM-B-2026-01": "gällande",
                          "SIM-R-2026-01": "gällande", "FI-SIM-2026-10": "gällande", "SIM-V-2026-01": "kommande",
                          "AVK-SIM-2026-01": "gällande"}
        assert out.in_force == {"FI-SIM": "FI-SIM-2026-10", "SIM-B": "SIM-B-2026-01", "SIM-G": "SIM-G-2026-01",
                                "SIM-R": "SIM-R-2026-01", "AVK-SIM": "AVK-SIM-2026-01"}
        assert all(b.checksum_ok for b in out.bases)

    def test_historisk_dag_visar_historikgrunden(self, service):
        out = service.execute("list_valuation_bases", KARL, {"on_date": "2025-06-30", "family": "SIM-HIST"}).output
        assert out.in_force == {"SIM-HIST": "SIM-HIST-2023-01"}

    def test_vardering_enligt_kontraktet(self, service):
        basis = service.execute("get_valuation_basis", KARL, {"code": "SIM-V-2026-01"}).output
        a = basis.assumptions
        assert (a["tax"]["rate"], a["mortality"]["risk_factor"], a["expenses"]["payout_sek_per_year"]) == ("0.15", "0.80", "240")
        assert basis.decision_ref.startswith("B-042") and basis.valid_from == date(2026, 12, 31)
        curve = service.execute("get_valuation_basis", KARL, {"code": "FI-SIM-2026-10"}).output.assumptions
        rates = {p["term_years"]: p["spot_rate"] for p in curve["points"]}
        assert curve["synthetic"] and (rates[1], rates[20], rates[150]) == ("0.0250", "0.0300", "0.0340")

    def test_avkastningsserien(self, service):
        series = service.execute("get_valuation_basis", KARL, {"code": "AVK-SIM-2026-01"}).output.assumptions
        months = series["months"]
        assert series["synthetic"] and len(months) == 46
        assert (months[0]["month"], months[-1]["month"]) == ("2023-01-01", "2026-10-01")
        from decimal import Decimal
        growth = Decimal(1)
        for m in months[:12]:
            growth *= 1 + Decimal(m["rate"])
        assert f"{(growth - 1) * 100:.2f}" == "7.07"  # helåret 2023 enligt kommentaren i START_BASES

    def test_avkastningsserien_ska_vara_i_foljd(self):
        with pytest.raises(vb.BasisError, match="i följd"):
            vb.normalize("return_series", {"synthetic": True, "description": "x", "months": [
                {"month": "2023-01-01", "rate": "0.01"}, {"month": "2023-03-01", "rate": "0.01"}]})

    def test_kontrollsumman_ar_deterministisk(self):
        first, second = vb.default_rows(), vb.default_rows()
        assert [r.checksum for r in first] == [r.checksum for r in second]
        assert len({r.code for r in first}) == len(vb.START_BASES)

    def test_andrat_innehall_stoppar_lasningen(self, service, demo):
        with demo() as s:
            row = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "SIM-V-2026-01"))
            row.assumptions = {**row.assumptions, "option_adjustment": "annat"}
            s.commit()
        with pytest.raises(BlockedError, match="Kontrollsumman"):
            service.execute("get_valuation_basis", KARL, {"code": "SIM-V-2026-01"})
        listing = service.execute("list_valuation_bases", KARL, {"family": "SIM-V"}).output
        assert listing.bases[0].checksum_ok is False

    def test_gallande_grund_slas_upp_per_dag(self, demo):
        with demo() as s:
            assert vb.in_force(s, "SIM-G", date(2026, 11, 1)).code == "SIM-G-2026-01"
            assert vb.in_force(s, "SIM-G", date(2026, 10, 31)) is None
            assert vb.in_force(s, "SIM-V", date(2026, 12, 31)).code == "SIM-V-2026-01"


class TestForslagOchAntagande:
    def test_forslag_antas_och_avslutar_foregaende(self, service):
        proposed = service.execute("propose_valuation_basis", KARL, proposal()).output
        assert (proposed.status, proposed.state, proposed.valid_from) == ("proposed", "förslag", None)
        assert proposed.proposal_reason == "Antagandeöversyn 2026" and proposed.created_by == "karl"
        adopted = service.execute("adopt_valuation_basis", KARL, {
            "code": "SIM-V-2027-01", "valid_from": "2027-03-31", "decision_ref": "Styrelsebeslut 2027-02-15"}).output
        assert (adopted.status, adopted.adopted_by, adopted.state) == ("adopted", "karl", "kommande")
        old = service.execute("get_valuation_basis", KARL, {"code": "SIM-V-2026-01"}).output
        assert old.valid_to == date(2027, 3, 30)
        out = service.execute("list_valuation_bases", KARL, {"on_date": "2027-03-31"}).output
        assert out.in_force["SIM-V"] == "SIM-V-2027-01"

    def test_innehallet_provas_mot_schemat(self, service):
        bad = proposal()
        bad["assumptions"]["tax"]["rate"] = "1.5"
        with pytest.raises(InvalidInputError, match="schemat"):
            service.execute("propose_valuation_basis", KARL, bad)
        with pytest.raises(InvalidInputError, match="schemat"):
            service.execute("propose_valuation_basis", KARL, proposal(assumptions={"curve_family": "FI-SIM"}))

    def test_kod_och_familj(self, service):
        with pytest.raises(ConflictError, match="finns redan"):
            service.execute("propose_valuation_basis", KARL, proposal(code="SIM-V-2026-01"))
        with pytest.raises(InvalidInputError, match="hör till SIM-G"):
            service.execute("propose_valuation_basis", KARL, proposal(supersedes_code="SIM-G-2026-01"))
        with pytest.raises(InvalidInputError):
            service.execute("propose_valuation_basis", KARL, proposal(code="SIM-X-2027-01"))

    def test_garantigrund_galler_bara_framat(self, service):
        raw = next(r for c, _, r, *_ in vb.START_BASES if c == "SIM-G-2026-01")
        service.execute("propose_valuation_basis", KARL, {
            "code": "SIM-G-2027-01", "title": "Ny garantitariff", "assumptions": raw, "source_refs": "Test"})
        with pytest.raises(BlockedError, match="bara framåt"):
            service.execute("adopt_valuation_basis", KARL, {
                "code": "SIM-G-2027-01", "valid_from": "2026-11-02", "decision_ref": "Styrelsebeslut"})
        adopted = service.execute("adopt_valuation_basis", KARL, {
            "code": "SIM-G-2027-01", "valid_from": "2027-01-01", "decision_ref": "Styrelsebeslut"}).output
        assert adopted.valid_from == date(2027, 1, 1)
        old = service.execute("get_valuation_basis", KARL, {"code": "SIM-G-2026-01"}).output
        assert old.valid_to == date(2026, 12, 31) and old.checksum == vb.default_rows()[1].checksum

    def test_ingen_grund_fore_den_gallande(self, service):
        service.execute("propose_valuation_basis", KARL, proposal())
        with pytest.raises(ConflictError, match="gäller redan"):
            service.execute("adopt_valuation_basis", KARL, {
                "code": "SIM-V-2027-01", "valid_from": "2026-12-31", "decision_ref": "Styrelsebeslut"})

    def test_avslag_och_bara_forslag_kan_antas(self, service):
        service.execute("propose_valuation_basis", KARL, proposal())
        rejected = service.execute("reject_valuation_basis", KARL, {"code": "SIM-V-2027-01", "note": "Underlaget räcker inte"}).output
        assert (rejected.status, rejected.review_note) == ("rejected", "Underlaget räcker inte")
        with pytest.raises(BlockedError, match="bara förslag"):
            service.execute("adopt_valuation_basis", KARL, {
                "code": "SIM-V-2027-01", "valid_from": "2027-03-31", "decision_ref": "Styrelsebeslut"})
        with pytest.raises(BlockedError, match="inget förslag"):
            service.execute("reject_valuation_basis", KARL, {"code": "SIM-V-2026-01", "note": "Fel"})


class TestAtkomst:
    def test_agenten_laser_men_antar_aldrig(self, service):
        assert service.execute("list_valuation_bases", AGENT, {}).output.in_force
        assert service.execute("get_valuation_basis", AGENT, {"code": "SIM-V-2026-01"}).output.code == "SIM-V-2026-01"
        for op, data in (("adopt_valuation_basis", {"code": "SIM-V-2026-01", "valid_from": "2027-01-01",
                                                    "decision_ref": "B-042"}),
                         ("reject_valuation_basis", {"code": "SIM-V-2026-01", "note": "Nej"})):
            with pytest.raises(AccessDeniedError):
                service.execute(op, AGENT, data)

    def test_agentens_forslag_vantar_pa_godkannande(self, service, demo):
        result = service.execute("propose_valuation_basis", AGENT, proposal())
        assert result.pending and result.approval_id
        with demo() as s:
            assert s.scalar(select(ValuationBasis).where(ValuationBasis.code == "SIM-V-2027-01")) is None

    def test_fore_regelpaketet_ar_forslaget_endast_handlaggare(self, demo):
        before = ServiceLayer(session_factory=demo, events=MemoryEventLog(),
                              rules=ProductRuleCatalog(today=date(2026, 10, 31)))
        with pytest.raises(AccessDeniedError):
            before.execute("propose_valuation_basis", AGENT, proposal())

    def test_aktuarien_ser_bara_lasverktygen(self, service):
        eco = Ecosystem.load()
        profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), service, agent_id="actuary_agent")
        visible = {d.skill for d in profile.visible()}
        assert {"list_valuation_bases", "get_valuation_basis"} <= visible
        assert not visible & {"propose_valuation_basis", "adopt_valuation_basis", "reject_valuation_basis"}


class TestMigration:
    def test_migrationen_kraver_postgres(self):
        from utils.migration_valuation_bases import migrate_valuation_bases

        with pytest.raises(RuntimeError, match="Postgres"):
            migrate_valuation_bases(create_engine("sqlite://"))

    def test_ddl_galler_bara_tabellen(self):
        from sqlalchemy.dialects import postgresql

        from utils.migration_valuation_bases import compile_ddl

        statements = compile_ddl(postgresql.dialect())
        assert [s.split()[2] for s in statements if s.startswith("CREATE TABLE")] == ["valuation_bases"]
        assert any("uq_valuation_bases_one_open" in s and "WHERE" in s for s in statements)

    def test_uppgraderingen_byter_bara_villkoren(self):
        from sqlalchemy.dialects import postgresql

        from utils.migration_valuation_bases import compile_upgrade

        statements = compile_upgrade(postgresql.dialect(), ["ck_valuation_bases_family"])
        assert statements[0] == "ALTER TABLE valuation_bases DROP CONSTRAINT IF EXISTS ck_valuation_bases_family"
        assert statements[1].startswith("ALTER TABLE valuation_bases ADD CONSTRAINT ck_valuation_bases_family")
        assert "'AVK-SIM'" in statements[1] and len(statements) == 2

    def test_migrationen_mot_postgres(self):
        from tests.conftest import seed_insurance
        from tests.test_services_postgres import TEST_URL, isolated_schema
        from utils.migration_valuation_bases import migrate_valuation_bases

        if not TEST_URL:
            pytest.skip("SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")
        not_in_lakebase = {"valuation_bases", "portfolios", "portfolio_holdings", "trades"}
        with isolated_schema() as lakebase_like:
            tables = [t for t in Base.metadata.sorted_tables if t.name not in not_in_lakebase]
            Base.metadata.create_all(lakebase_like.engine, tables=tables)
            seed_insurance(lakebase_like.session_factory)
            dry = migrate_valuation_bases(lakebase_like.engine)
            assert not dry.applied and "valuation_bases" not in inspect(lakebase_like.engine).get_table_names()
            done = migrate_valuation_bases(lakebase_like.engine, dry_run=False)
            assert done.applied and done.row_counts == dry.row_counts
            assert migrate_valuation_bases(lakebase_like.engine, dry_run=False).already_applied
            with lakebase_like.session_factory() as s:
                rows = list(s.scalars(select(ValuationBasis)))
                assert sorted(r.code for r in rows) == sorted(c for c, *_ in vb.START_BASES)
                for row in rows:
                    vb.verify_checksum(row)  # JSONB ger samma kanoniska text

            # A4-läget i Lakebase: villkoret utan AVK-SIM och utan avkastningsserien – uppgraderingen fyller på
            with lakebase_like.engine.begin() as conn:
                conn.exec_driver_sql("DELETE FROM valuation_bases WHERE family = 'AVK-SIM'")
                conn.exec_driver_sql("ALTER TABLE valuation_bases DROP CONSTRAINT ck_valuation_bases_family")
                conn.exec_driver_sql("ALTER TABLE valuation_bases ADD CONSTRAINT ck_valuation_bases_family CHECK "
                                     "(family IN ('SIM-G', 'SIM-HIST', 'SIM-B', 'SIM-R', 'SIM-V', 'FI-SIM'))")
            dry = migrate_valuation_bases(lakebase_like.engine)
            assert dry.upgrade and not dry.applied and dry.seeded == ["AVK-SIM-2026-01"]
            assert len(dry.statements) == 4  # familj och ändamål: DROP + ADD
            done = migrate_valuation_bases(lakebase_like.engine, dry_run=False)
            assert done.applied and done.row_counts == dry.row_counts
            assert migrate_valuation_bases(lakebase_like.engine, dry_run=False).already_applied
            with lakebase_like.session_factory() as s:
                avk = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "AVK-SIM-2026-01"))
                vb.verify_checksum(avk)
