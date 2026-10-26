"""Compliance-teamets begränsade databasroll mot en riktig Postgres (3c-V, harness.md §5.1).

Rättigheterna i `utils.agent_roles.COMPLIANCE` ska räcka för parameterläsningen och
förhandsberäkningen, med loggrad för nekade försök, och inget mer: ingen individdata,
inga förslag i kön och inga ändringar. Aktiveringsförslaget i parameterflödet läggs
av motorn med den betrodda anslutningen, aldrig med teamets roll.

Rollen `agent_compliance` skapas av operatören. Finns SERVICES_TEST_COMPLIANCE_POSTGRES_URL
provas den; annars ges samma rättigheter till rollen i SERVICES_TEST_AGENT_POSTGRES_URL,
bara i det isolerade schemat, som tas bort efteråt. Beståndet rörs aldrig.
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
    RunStatus,
    SkillRegistry,
    request_for_interpretation,
    run_assignment,
)
from agents.gateways import DraftGateway, RegulatoryGateway
from models import OperationEventRecord
from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer, default_registry
from services.db import session_factory_for
from services.operations import common
from tests.flow_helpers import SOURCE, flow_client
from tests.test_services_postgres import TEST_URL, isolated_schema
from utils.agent_roles import (
    COMPLIANCE,
    RETURNING_COLUMNS,
    current_column_privileges,
    current_privileges,
    inspect_role,
)
from utils.demo_data import create_demo_database

COMPLIANCE_URL = os.environ.get("SERVICES_TEST_COMPLIANCE_POSTGRES_URL") or os.environ.get(
    "SERVICES_TEST_AGENT_POSTGRES_URL"
)

pytestmark = pytest.mark.skipif(
    not (TEST_URL and COMPLIANCE_URL),
    reason="SERVICES_TEST_POSTGRES_URL och en agentroll i testdatabasen behövs för rollproven",
)

TODAY = date(2026, 11, 15)
AGENT = OperationContext(actor=Actor.agent("compliance_agent", team="compliance"), run_id="run-comp")
PROPOSAL = {"key": "premium_age_end", "value": "67", "valid_from": "2027-01-01", "rule_version": "1.1",
            "source_ref": SOURCE, "decision_ref": "test"}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


@pytest.fixture(scope="module")
def db():
    for env in ("AGENT_COMPLIANCE_DATABASE_URL", "AGENT_AKTUARIE_DATABASE_URL", "AGENT_FORSAKRING_DATABASE_URL"):
        if COMPLIANCE_URL == os.environ.get(env):
            pytest.fail(f"Testrollens anslutning får inte vara {env} (beståndet)")
    with isolated_schema() as schema:
        create_demo_database(schema.engine, with_proposals=False)
        agent_engine = create_engine(COMPLIANCE_URL, connect_args={"options": f"-csearch_path={schema.name}"})
        with agent_engine.connect() as conn:
            login = conn.exec_driver_sql("SELECT current_user").scalar_one()
        schema.grants = replace(COMPLIANCE, role=login)
        with schema.engine.begin() as conn:
            for statement in schema.grants.statements(schema.name):
                conn.exec_driver_sql(statement)
        schema.agent_engine = agent_engine
        schema.agent_factory = session_factory_for(agent_engine)
        try:
            yield schema
        finally:
            agent_engine.dispose()


def compliance_service(db) -> ServiceLayer:
    """Som services.db.agent_service_layer("compliance"), men mot testschemat."""
    return ServiceLayer(
        session_factory=db.agent_factory, validation_session_factory=db.session_factory,
        agent_role="agent_compliance", rules=ProductRuleCatalog(today=TODAY),
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
        **{t: ["SELECT"] for t in COMPLIANCE.select},
        "operation_events": ["INSERT"],
    }
    assert columns == {f"operation_events.{c}": ["SELECT"] for c in RETURNING_COLUMNS}


def test_parametrarna_las_med_compliance_roll(db):
    out = compliance_service(db).execute("get_product_parameters", AGENT, {"on_date": "2026-12-31"}).output
    assert {v.key for v in out.versions} >= {"premium_age_start", "premium_age_end"}


def test_forhandsberakningen_med_compliance_roll(db):
    out = compliance_service(db).execute(
        "calculate_premium_preview", AGENT, {"monthly_salary_sek": "45000", "period_month": "2026-10-01"}).output
    assert out.total_premium_sek == 2025


def test_nekat_forsok_loggas_med_compliance_roll(db):
    before = events(db)
    with pytest.raises(Exception, match="endast handläggare"):
        compliance_service(db).execute("withdraw_product_parameter_change", replace(AGENT, reason="Försök"),
                                       {"key": "premium_age_end", "valid_from": "2027-01-01"})
    assert events(db) == before + 1


def test_compliance_kan_inte_lagga_forslag_i_kon(db):
    """Aktiveringsförslaget läggs av flödesmotorn med den betrodda anslutningen, inte av teamet."""
    with pytest.raises(Exception, match="permission denied"):
        compliance_service(db).execute("schedule_product_parameter_change", replace(AGENT, reason="Försök"),
                                       PROPOSAL)


def test_hela_tolkningen_med_compliance_roll(db, tmp_path):
    eco = Ecosystem.load()
    skills = SkillRegistry.build(eco, default_registry)
    gateways = Gateways(regulatory=RegulatoryGateway(), drafts=DraftGateway(tmp_path / "utkast"))
    outcome = run_assignment(
        flow_client(), eco, skills, compliance_service(db), request_for_interpretation(SOURCE),
        gateways=gateways, run_id="run-comp-pg", journal_dir=tmp_path / "runs",
    )
    assert outcome.result.status == RunStatus.COMPLETED, outcome.result.uncertainties
    assert outcome.result.output["schema"] == "InterpretationProposal"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM insured_persons",
        "SELECT * FROM policies",
        "SELECT * FROM salary_reports",
        "SELECT * FROM premium_transactions",
        "SELECT * FROM cases",
        "SELECT * FROM approval_requests",
        "SELECT * FROM operation_events",
        "SELECT * FROM flows",
        "INSERT INTO approval_requests (id) VALUES ('x')",
        "INSERT INTO product_parameters (key) VALUES ('premium_age_end')",
        "UPDATE product_parameters SET value = 68",
        "DELETE FROM operation_events",
        "SELECT * FROM product_parameters FOR UPDATE",
        "CREATE TABLE compliance_egen (id int)",
    ],
)
def test_compliance_roll_nekas_allt_annat(db, sql):
    with db.agent_engine.connect() as conn, pytest.raises(Exception, match="permission denied"):
        conn.exec_driver_sql(sql)
