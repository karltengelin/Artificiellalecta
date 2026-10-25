"""Produktparametrar som versionerad data (Fas 3c 3c-P1, B-035, databasschema §9h).

Premiemotorn med parametrar, tabellens villkor, uppslaget per premiemånad,
läsoperationen get_product_parameters och att hela demobeståndets premier räknas om
identiskt med de seedade parametrarna. Migrationen mot Postgres prövas sist.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from models import Base, BaseAmount, PremiumTransaction, ProductParameter
from services import Actor, AgentAccess, MemoryEventLog, OperationContext, ServiceLayer
from services.db import session_factory_for
from services.errors import BlockedError, NotFoundError
from services.parameters import (
    FALLBACK_LABEL,
    PREMIUM_FIELDS,
    add_missing_defaults,
    premium_parameters,
)
from skills.calculation.calculate_itp1_premium import (
    DEFAULT_PARAMETERS,
    PremiumParameters,
    calculate_itp1_premium,
)
from utils.demo_data import create_demo_database
from utils.migration_product_parameters import (
    compile_ddl,
    migrate_product_parameters,
    verify_premiums,
)

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

HUMAN = OperationContext(actor=Actor.human("karl"))
AGENT = OperationContext(actor=Actor.agent("case_handler", team="forsakring"), run_id="run-p1")
#: Fyller 66 i mars 2027 och 67 i mars 2028
BORN_1961 = date(1961, 3, 15)


def _new_age_end(session, value="67", valid_from=date(2027, 1, 1)):
    """Avslutar dagens premieålder och lägger en ny version från valid_from."""
    old = session.scalar(select(ProductParameter).where(ProductParameter.key == "premium_age_end"))
    old.valid_to = date(valid_from.year - 1, 12, 31)
    session.add(ProductParameter(
        key="premium_age_end", value=Decimal(value), unit="years", valid_from=valid_from,
        rule_id="PR-ITP1-013", rule_version="1.1", source_ref="K-SIM-ITP-2027", decision_ref="test",
        created_by="test",
    ))
    session.flush()


class TestPremiemotornMedParametrar:
    def test_standard_ar_paketets_varden(self):
        assert (DEFAULT_PARAMETERS.age_start, DEFAULT_PARAMETERS.age_end) == (25, 66)
        assert DEFAULT_PARAMETERS.rate_low == Decimal("0.045")

    def test_hojd_premiealder_ger_premie_ar_66(self):
        month = date(2027, 6, 1)  # 66 år och 3 månader
        before = calculate_itp1_premium(Decimal("40000"), Decimal("85000"), birth_date=BORN_1961, period_month=month)
        after = calculate_itp1_premium(
            Decimal("40000"), Decimal("85000"), birth_date=BORN_1961, period_month=month,
            parameters=PremiumParameters(age_end=67, versions={"premium_age_end": "PR-ITP1-013 v1.1"}),
        )
        assert (before.in_age_window, before.total_premium_sek) == (False, Decimal("0.00"))
        assert after.in_age_window is True and after.total_premium_sek == Decimal("1800.00")
        assert after.calculation_basis["age_window"] == [25, 67]
        assert after.calculation_basis["parameters"] == {"premium_age_end": "PR-ITP1-013 v1.1"}

    def test_standardberakningens_underlag_ar_oforandrat(self):
        basis = calculate_itp1_premium(Decimal("80000"), Decimal("83400")).calculation_basis
        assert "parameters" not in basis and "age_window" not in basis

    def test_annan_sats_och_brytpunkt(self):
        params = PremiumParameters(rate_low=Decimal("0.05"), breakpoint_low_ibb=Decimal("8"))
        r = calculate_itp1_premium(Decimal("30000"), Decimal("90000"), parameters=params)
        assert r.total_premium_sek == Decimal("1500.00")  # 5 % under 8 × 90 000 / 12 = 60 000


@pytest.fixture
def db(insurance_db):
    return insurance_db


def _rejected(db, **overrides) -> None:
    row = dict(
        key="premium_age_end", value=Decimal("67"), unit="years", valid_from=date(2027, 1, 1),
        rule_id="PR-ITP1-013", rule_version="1.1", source_ref="x", decision_ref="x", created_by="t",
    )
    with db.session_factory() as s:
        s.add(ProductParameter(**{**row, **overrides}))
        with pytest.raises(IntegrityError):
            s.flush()
        s.rollback()


class TestTabellen:
    def test_giltighet_borjar_en_manadsforsta(self, db):
        _rejected(db, valid_from=date(2027, 1, 15))

    def test_en_version_per_nyckel_och_giltighetsdag(self, db):
        _rejected(db, valid_from=date(2023, 1, 1))

    def test_okand_nyckel_nekas(self, db):
        _rejected(db, key="pension_age")

    def test_startvardena_laggs_inte_in_tva_ganger(self, db):
        with db.session_factory() as s:
            assert add_missing_defaults(s) == 0
            assert s.scalar(select(ProductParameter).where(ProductParameter.key == "premium_rate_high")).value == Decimal("0.3")


class TestUppslag:
    def test_seedade_varden_med_versioner(self, db):
        with db.session_factory() as s:
            p = premium_parameters(s, date(2026, 5, 17))
        assert p == DEFAULT_PARAMETERS
        assert p.versions["premium_age_end"] == "PR-ITP1-013 v1.0 från 2023-01-01"
        assert set(p.versions) == set(PREMIUM_FIELDS)
        assert str(p.breakpoint_high_ibb) == "30"  # inte 3E+1 i calculation_basis

    def test_ny_version_galler_fran_sin_manad(self, db):
        with db.session_factory() as s:
            _new_age_end(s)
            assert premium_parameters(s, date(2026, 12, 1)).age_end == 66
            p = premium_parameters(s, date(2027, 1, 1))
        assert p.age_end == 67 and p.versions["premium_age_end"] == "PR-ITP1-013 v1.1 från 2027-01-01"

    def test_aterkallad_version_raknas_inte(self, db):
        with db.session_factory() as s:
            _new_age_end(s)
            s.execute(update(ProductParameter).where(ProductParameter.valid_from == date(2027, 1, 1)).values(status="withdrawn"))
            with pytest.raises(NotFoundError, match="premium_age_end"):
                premium_parameters(s, date(2027, 1, 1))  # gamla versionen upphörde 2026-12-31

    def test_saknad_parameter_stoppar(self, db):
        with db.session_factory() as s:
            s.execute(update(ProductParameter).where(ProductParameter.key == "premium_rate_low").values(status="withdrawn"))
            with pytest.raises(NotFoundError, match="premium_rate_low"):
                premium_parameters(s, date(2026, 5, 1))

    def test_overlappande_versioner_stoppar(self, db):
        with db.session_factory() as s:
            s.add(ProductParameter(
                key="premium_age_end", value=Decimal("67"), unit="years", valid_from=date(2027, 1, 1),
                rule_id="PR-ITP1-013", rule_version="1.1", source_ref="x", decision_ref="x", created_by="t",
            ))
            s.flush()
            with pytest.raises(BlockedError, match="två giltiga versioner"):
                premium_parameters(s, date(2027, 2, 1))

    def test_alder_maste_vara_hela_ar(self, db):
        with db.session_factory() as s:
            _new_age_end(s, value="66.5")
            with pytest.raises(BlockedError, match="hela år"):
                premium_parameters(s, date(2027, 1, 1))

    def test_utan_tabell_galler_paketets_varden_markt(self):
        engine = create_engine("sqlite://", poolclass=StaticPool)
        tables = [t for t in Base.metadata.sorted_tables if t.name != "product_parameters"]
        Base.metadata.create_all(engine, tables=tables)
        with session_factory_for(engine)() as s:
            p = premium_parameters(s, date(2026, 5, 1))
        assert p == DEFAULT_PARAMETERS and p.versions == {"källa": FALLBACK_LABEL}


@pytest.fixture
def service(db):
    return ServiceLayer(session_factory=db.session_factory, events=MemoryEventLog())


class TestOperationerna:
    def test_agenten_far_lasa_parametrarna(self, service):
        assert service.decision("get_product_parameters").effective is AgentAccess.AGENT
        out = service.execute("get_product_parameters", AGENT, {"on_date": "2026-11-01"}).output
        assert out.table_present and out.effective["premium_age_end"] == Decimal("66")
        assert len(out.versions) == 6 and {v.state for v in out.versions} == {"gällande"}
        age_end = next(v for v in out.versions if v.key == "premium_age_end")
        assert (age_end.rule_id, age_end.source_ref) == ("PR-ITP1-013", "K-ITP-FIL")

    def test_kommande_version_syns(self, service, db):
        with db.session_factory() as s:
            _new_age_end(s)
            s.commit()
        out = service.execute("get_product_parameters", HUMAN, {"on_date": "2026-11-01"}).output
        states = {(v.key, v.valid_from): v.state for v in out.versions}
        assert states[("premium_age_end", date(2027, 1, 1))] == "kommande"
        assert out.effective["premium_age_end"] == Decimal("66")
        later = service.execute("get_product_parameters", HUMAN, {"on_date": "2027-01-01"}).output
        assert later.effective["premium_age_end"] == Decimal("67")

    def test_forhandsberakningen_foljer_parametern_for_manaden(self, service, db):
        with db.session_factory() as s:
            s.add(BaseAmount(year=2027, income_base_amount_sek=Decimal("85000")))
            _new_age_end(s)
            s.commit()
        args = {"monthly_salary_sek": "40000", "birth_date": BORN_1961.isoformat()}
        june_2027 = service.execute("calculate_premium_preview", AGENT, {**args, "period_month": "2027-06-01"}).output
        assert june_2027.in_age_window is True and june_2027.total_premium_sek == Decimal("1800.00")
        assert june_2027.calculation_basis["parameters"]["premium_age_end"] == "PR-ITP1-013 v1.1 från 2027-01-01"
        # 2026: personen är 65 – i fönstret oavsett version
        assert service.execute("calculate_premium_preview", AGENT, {**args, "period_month": "2026-06-01"}).output.in_age_window


class TestIdentiskaPremier:
    def test_hela_demobestandet_raknas_om_identiskt(self):
        engine = create_engine("sqlite://", poolclass=StaticPool)
        create_demo_database(engine)
        with session_factory_for(engine)() as s:
            check = verify_premiums(s)
        assert check.ok, check.mismatches[:3]
        assert check.checked > 50

    def test_avvikelse_upptacks(self):
        engine = create_engine("sqlite://", poolclass=StaticPool)
        create_demo_database(engine)
        with session_factory_for(engine)() as s:
            tx = s.scalars(select(PremiumTransaction).where(PremiumTransaction.transaction_type == "premium")).first()
            tx.amount_sek = Decimal(tx.amount_sek) + 1
            s.flush()
            check = verify_premiums(s)
        assert len(check.mismatches) == 1


class TestMigrationen:
    def test_kraver_postgres(self):
        with pytest.raises(RuntimeError, match="Postgres"):
            migrate_product_parameters(create_engine("sqlite://"))

    def test_ddl_galler_bara_tabellen(self):
        from sqlalchemy.dialects import postgresql

        statements = compile_ddl(postgresql.dialect())
        assert statements[0].startswith("CREATE TABLE product_parameters")
        assert "%%" not in " ".join(statements)


from tests.test_services_postgres import TEST_URL, isolated_schema  # noqa: E402


def _lakebase_like(schema) -> None:
    """Demobeståndet som Lakebase ser ut före migrationen: allt utom product_parameters."""
    create_demo_database(schema.engine)
    with schema.engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE product_parameters")


@pytest.mark.skipif(not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")
def test_migrationen_skapar_fyller_och_raknar_om_identiskt():
    with isolated_schema() as schema:
        _lakebase_like(schema)
        dry = migrate_product_parameters(schema.engine)  # torrkörning är standard
        assert not dry.applied and dry.check.ok and dry.check.checked > 50 and dry.seeded == 6
        assert "product_parameters" not in inspect(schema.engine).get_table_names()

        done = migrate_product_parameters(schema.engine, dry_run=False)
        assert done.applied and done.row_counts == dry.row_counts
        assert migrate_product_parameters(schema.engine, dry_run=False).already_applied
        with schema.session_factory() as s:
            assert premium_parameters(s, date(2026, 5, 1)) == DEFAULT_PARAMETERS
            assert len(s.scalars(select(ProductParameter)).all()) == 6


@pytest.mark.skipif(not TEST_URL, reason="SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")
def test_migrationen_rullas_tillbaka_vid_avvikande_premie():
    with isolated_schema() as schema:
        _lakebase_like(schema)
        with schema.engine.begin() as conn:
            conn.exec_driver_sql(
                "UPDATE premium_transactions SET amount_sek = amount_sek + 1 "
                "WHERE id = (SELECT id FROM premium_transactions WHERE transaction_type = 'premium' LIMIT 1)"
            )
        with pytest.raises(RuntimeError, match="räknas inte om identiskt"):
            migrate_product_parameters(schema.engine, dry_run=False)
        assert "product_parameters" not in inspect(schema.engine).get_table_names()
