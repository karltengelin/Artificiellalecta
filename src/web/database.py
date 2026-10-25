"""Databasval för handläggar-UI:t – bygger tjänstelagret mot rätt databas.

Den enda modulen i `web` som rör SQLAlchemy, och bara för att skapa motorn.
All läsning och skrivning går sedan genom `ServiceLayer` (en transaktion per
anrop, händelselogg och godkännandekö i databasen).

| Val        | Databas                                                     | Tabeller                              |
|------------|-------------------------------------------------------------|---------------------------------------|
| `demo`     | SQLite-fil (`data/handlaggare_demo.db`, gitignorerad)       | Skapas med demobeståndet om filen saknas; nya tabeller läggs till |
| `svc_test` | Schemat `handlaggare_ui` i `SERVICES_TEST_POSTGRES_URL`     | Skapas med demobeståndet om schemat är tomt; nya tabeller läggs till |
| `lakebase` | Beståndet via `DATABASE_URL`                                | Skapas aldrig – schemat ändras bara med migrationsskript |
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine

from agents.flows.console import FlowConsole
from services import ServiceLayer
from services.db import session_factory_for
from web.agent import CaseAgent
from web.config import WebConfigError, WebSettings

SVC_TEST_SCHEMA = "handlaggare_ui"


def build_service(settings: WebSettings) -> ServiceLayer:
    return build_services(settings)[0]


def build_services(settings: WebSettings) -> tuple[ServiceLayer, CaseAgent, FlowConsole | None]:
    """Handläggarens tjänstelager, handläggaragenten (Fas 5 F5-4) och flödena (Fas 3c 3c-3) mot samma databas.

    Flödena finns bara i demo och `svc_test`: i Lakebase är `migrate_flows.py` inte körd, och
    riktiga modellanrop hör till 3c-V.
    """
    engine = build_engine(settings)
    session_factory = session_factory_for(engine)
    service = ServiceLayer(session_factory=session_factory)
    if settings.database == "lakebase":
        from services.db import agent_service_layer

        agent = CaseAgent(agent_service_factory=agent_service_layer, simulated_role=False)
        flows = None
    else:
        # Demo- och testdatabasen: samma anslutning, rollen simuleras (B-033 val H)
        agent = CaseAgent(
            agent_service_factory=lambda: ServiceLayer(
                session_factory=session_factory, validation_session_factory=session_factory,
                agent_role="agent_forsakring",
            ),
            simulated_role=True,
        )
        flows = FlowConsole.for_demo_database(session_factory)
    return service, agent, flows


def build_engine(settings: WebSettings) -> Engine:
    if settings.database == "demo":
        return demo_engine(settings.demo_path)
    if settings.database == "svc_test":
        return svc_test_engine()
    return lakebase_engine()


def demo_engine(path: Path) -> Engine:
    """Lokal SQLite-fil. Transaktionerna köas (BEGIN IMMEDIATE), som i tests/conftest.py."""
    from utils.demo_data import create_demo_database

    created = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 15})

    @event.listens_for(engine, "connect")
    def _autocommit_driver(dbapi_connection, _record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _begin_immediate(connection):
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    if created:
        create_demo_database(engine)
    else:
        add_missing_tables(engine)
    return engine


def add_missing_tables(engine: Engine) -> None:
    """Nya tabeller (t.ex. `cases`, Fas 5) i en befintlig demo- eller testdatabas. Används aldrig
    mot Lakebase – där gäller migrationsskripten."""
    from utils.demo_data import add_missing_demo_tables

    add_missing_demo_tables(engine)


def svc_test_engine() -> Engine:
    """Ett eget schema i den isolerade testdatabasen – aldrig Lakebase-beståndet."""
    from utils.demo_data import create_demo_database

    url = os.environ.get("SERVICES_TEST_POSTGRES_URL")
    if not url:
        raise WebConfigError("SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad testdatabas att köra mot")
    if url == os.environ.get("DATABASE_URL"):
        raise WebConfigError("SERVICES_TEST_POSTGRES_URL är samma som DATABASE_URL – vägrar köra mot beståndet")
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{SVC_TEST_SCHEMA}"')
    admin.dispose()
    # pool_pre_ping: serverlös Postgres stänger vilande anslutningar
    engine = create_engine(
        url, pool_pre_ping=True, connect_args={"options": f"-csearch_path={SVC_TEST_SCHEMA}"}
    )
    if not inspect(engine).get_table_names():
        create_demo_database(engine)
    else:
        add_missing_tables(engine)
    return engine


def lakebase_engine() -> Engine:
    """Beståndet. Inga tabeller skapas och inget seedas härifrån."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise WebConfigError("DATABASE_URL saknas – lägg in Lakebase-anslutningen i .env")
    return create_engine(url, pool_pre_ping=True)
