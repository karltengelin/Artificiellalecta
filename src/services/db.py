"""Databassessioner för tjänstelagret – en transaktion per operation.

    service = ServiceLayer(session_factory=database_session_factory())   # Lakebase via DATABASE_URL
    service = ServiceLayer(session_factory=session_factory_for(engine))  # valfri motor, t.ex. i tester
    service = agent_service_layer("forsakring")                          # agentens begränsade roll
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import TYPE_CHECKING, Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from services.errors import ServiceConfigError

if TYPE_CHECKING:
    from services.service import ServiceLayer

SessionFactory = Callable[[], AbstractContextManager[Session]]


def session_factory_for(engine: Engine) -> SessionFactory:
    """Session per anrop med commit vid framgång och rollback vid fel."""
    maker = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    @contextmanager
    def scope() -> Iterator[Session]:
        session = maker()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return scope


def database_session_factory(url_env: str = "DATABASE_URL") -> SessionFactory:
    """Lakebase via DATABASE_URL (utils.db). Motorn skapas först vid första operationen."""
    state: dict[str, SessionFactory] = {}

    def scope() -> AbstractContextManager[Session]:
        if "factory" not in state:
            from utils.db import make_engine

            state["factory"] = session_factory_for(make_engine(url_env=url_env))
        return state["factory"]()

    return scope


#: Agentteamens begränsade databasroller (harness.md §5.1) och deras anslutningar i .env.
#: Rollernas rättigheter sätts med scripts/setup/grant_agent_role.py.
AGENT_ROLES = {"forsakring": ("agent_forsakring", "AGENT_FORSAKRING_DATABASE_URL")}


def agent_service_layer(team: str = "forsakring", **kwargs: Any) -> ServiceLayer:
    """Tjänstelagret för ett agentteam: läsningar, förslag och loggrader går via teamets
    begränsade roll; provkörning av förslag via den betrodda anslutningen (DATABASE_URL).

    Godkännanden görs aldrig här – handläggaren använder ett vanligt ServiceLayer.
    """
    from services.service import ServiceLayer

    if team not in AGENT_ROLES:
        raise ServiceConfigError(f"Teamet '{team}' har ingen databasroll")
    role, url_env = AGENT_ROLES[team]
    return ServiceLayer(
        session_factory=database_session_factory(url_env),
        validation_session_factory=database_session_factory(),
        agent_role=role,
        **kwargs,
    )
