"""Aktuarieteamets begränsade databasroll mot en riktig Postgres (B-035 val I, harness.md §5.1).

Rättigheterna i `utils.agent_roles.AKTUARIE` ska räcka för beståndsinsikten och
parameterläsningen, med loggrad, och inget mer: inga löner, premier, ärenden eller
arbetsgivare, inga förslag i kön och inga ändringar.

Rollen `agent_aktuarie` skapas av operatören. Finns SERVICES_TEST_AKTUARIE_POSTGRES_URL
provas den; annars ges samma rättigheter till rollen i SERVICES_TEST_AGENT_POSTGRES_URL,
bara i det isolerade schemat. Demobeståndet med den äldre kohorten skapas i ett eget
schema i testdatabasen och tas bort efteråt; beståndet rörs aldrig.
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import date

import pytest
from sqlalchemy import create_engine, func, select

from agents import (
    Ecosystem,
    Gateways,
    ParameterChangeMandate,
    RunStatus,
    SkillRegistry,
    request_for_impact,
    run_assignment,
)
from agents.gateways import DraftGateway, RegulatoryGateway
from models import OperationEventRecord
from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer, default_registry
from services.db import session_factory_for
from services.operations import common
from tests.flow_helpers import flow_client
from tests.test_services_postgres import TEST_URL, isolated_schema
from utils.agent_roles import (
    AKTUARIE,
    RETURNING_COLUMNS,
    current_column_privileges,
    current_privileges,
    inspect_role,
)
from utils.demo_data import create_demo_database

AKTUARIE_URL = os.environ.get("SERVICES_TEST_AKTUARIE_POSTGRES_URL") or os.environ.get(
    "SERVICES_TEST_AGENT_POSTGRES_URL"
)

pytestmark = pytest.mark.skipif(
    not (TEST_URL and AKTUARIE_URL),
    reason="SERVICES_TEST_POSTGRES_URL och en agentroll i testdatabasen behövs för rollproven",
)

TODAY = date(2026, 11, 15)
ACTUARY = OperationContext(actor=Actor.agent("actuary_agent", team="aktuarie"), run_id="run-akt")
ESTIMATE = {"key": "premium_age_end", "value": "67", "valid_from": "2027-01-01", "horizon_years": 10}
MANDATE = ParameterChangeMandate(ref="pc-pg", key="premium_age_end", value=67,
                                 valid_from=date(2027, 1, 1), horizon_years=10)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


@pytest.fixture(scope="module")
def db():
    for env in ("AGENT_AKTUARIE_DATABASE_URL", "AGENT_FORSAKRING_DATABASE_URL"):
        if AKTUARIE_URL == os.environ.get(env):
            pytest.fail(f"Testrollens anslutning får inte vara {env} (beståndet)")
    with isolated_schema() as schema:
        create_demo_database(schema.engine, with_proposals=False)
        agent_engine = create_engine(AKTUARIE_URL, connect_args={"options": f"-csearch_path={schema.name}"})
        with agent_engine.connect() as conn:
            login = conn.exec_driver_sql("SELECT current_user").scalar_one()
        schema.grants = replace(AKTUARIE, role=login)
        with schema.engine.begin() as conn:
            for statement in schema.grants.statements(schema.name):
                conn.exec_driver_sql(statement)
        schema.agent_engine = agent_engine
        schema.agent_factory = session_factory_for(agent_engine)
        try:
            yield schema
        finally:
            agent_engine.dispose()


def actuary_service(db) -> ServiceLayer:
    """Som services.db.agent_service_layer("aktuarie"), men mot testschemat."""
    return ServiceLayer(
        session_factory=db.agent_factory, validation_session_factory=db.session_factory,
        agent_role="agent_aktuarie", rules=ProductRuleCatalog(today=TODAY),
    )


def events(db) -> int:
    with db.session_factory() as s:
        return s.scalar(select(func.count()).select_from(OperationEventRecord))


def test_forkontrollen_godkanner_rollen_och_rattigheterna_ar_exakta(db):
    role = db.grants.role
    with db.engine.connect() as conn:
        assert inspect_role(conn, db.grants, db.name) == []
        privileges = current_privileges(conn, role, db.name)
        columns = current_column_privileges(conn, role, db.name)
    assert privileges == {
        **{t: ["SELECT"] for t in AKTUARIE.select},
        "operation_events": ["INSERT"],
    }
    assert columns == {
        **{f"operation_events.{c}": ["SELECT"] for c in RETURNING_COLUMNS},
        **{f"{t}.{c}": ["SELECT"] for t, cols in AKTUARIE.columns for c in cols},
    }


def test_ledningsaggregatet_med_aktuariens_roll(db):
    """OC-3a val D: kolumnrätterna räcker för get_company_metrics, utan lön eller beräkningsunderlag."""
    out = actuary_service(db).execute("get_company_metrics", ACTUARY, {"month": "2026-09-01"}).output
    assert out.paid_state in {"available", "suppressed"}
    assert out.insured_count is not None and out.insured_count >= 10


def test_bestandsinsikten_med_aktuariens_roll(db):
    before = events(db)
    out = actuary_service(db).execute("estimate_parameter_change_impact", ACTUARY, ESTIMATE).output
    assert out.first_affected_year == 2027
    assert out.years[0].affected_persons >= 10
    assert events(db) == before  # läsning utan personuppgifter loggas inte


def test_nekat_forsok_loggas_med_aktuariens_roll(db):
    """Därför INSERT på händelseloggen: ett nej till en HUMAN_ONLY-operation skrivs som agentens rad."""
    before = events(db)
    with pytest.raises(Exception, match="endast handläggare"):
        actuary_service(db).execute("withdraw_product_parameter_change", replace(ACTUARY, reason="Försök"),
                                    {"key": "premium_age_end", "valid_from": "2027-01-01"})
    assert events(db) == before + 1


def test_parametrarna_las_med_aktuariens_roll(db):
    out = actuary_service(db).execute("get_product_parameters", ACTUARY, {"on_date": "2026-12-31"}).output
    assert {v.key for v in out.versions} >= {"premium_age_start", "premium_age_end"}


def test_hela_insiktskorningen_med_aktuariens_roll(db, tmp_path):
    eco = Ecosystem.load()
    skills = SkillRegistry.build(eco, default_registry)
    gateways = Gateways(regulatory=RegulatoryGateway(), drafts=DraftGateway(tmp_path / "utkast"))
    outcome = run_assignment(
        flow_client(interpretation_responses=[]), eco, skills, actuary_service(db),
        request_for_impact(MANDATE), parameter_change=MANDATE, gateways=gateways, run_id="run-akt-pg",
        journal_dir=tmp_path / "runs",
    )
    assert outcome.result.status == RunStatus.COMPLETED, outcome.result.uncertainties
    assert outcome.result.output["evidence"]["estimate"]["first_affected_year"] == 2027


def test_aktuarien_kan_inte_lagga_forslag_i_kon(db):
    """Körpolicyn ger aldrig aktuarien skrivande verktyg; databasen nekar ändå."""
    proposal = OperationContext(actor=Actor.agent("actuary_agent", team="aktuarie"), run_id="run-akt",
                                reason="Försök")
    data = {"key": "premium_age_end", "value": "67", "valid_from": "2027-01-01", "rule_version": "1.1",
            "source_ref": "K-SIM-ITP-2027", "decision_ref": "test"}
    with pytest.raises(Exception, match="permission denied"):
        actuary_service(db).execute("schedule_product_parameter_change", proposal, data)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM salary_reports",
        "SELECT * FROM premium_transactions",
        "SELECT pensionable_salary_sek FROM premium_transactions",
        "SELECT calculation_basis FROM premium_transactions",
        "SELECT benefit_type FROM policy_benefits",
        "SELECT * FROM employers",
        "SELECT * FROM cases",
        "SELECT * FROM policy_benefits",
        "SELECT * FROM approval_requests",
        "SELECT * FROM operation_events",
        "SELECT * FROM flows",
        "INSERT INTO approval_requests (id) VALUES ('x')",
        "UPDATE product_parameters SET value = 68",
        "DELETE FROM product_parameters",
        "UPDATE insured_persons SET monthly_salary_sek = 1",
        "DELETE FROM operation_events",
        "SELECT * FROM product_parameters FOR UPDATE",
        "TRUNCATE base_amounts",
        "CREATE TABLE aktuarie_egen (id int)",
    ],
)
def test_aktuariens_roll_nekas_allt_annat(db, sql):
    with db.agent_engine.connect() as conn, pytest.raises(Exception, match="permission denied"):
        conn.exec_driver_sql(sql)
