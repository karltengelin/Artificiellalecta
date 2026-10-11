"""Databassessioner för tjänstelagret – en transaktion per operation.

    service = ServiceLayer(session_factory=database_session_factory())   # Lakebase via DATABASE_URL
    service = ServiceLayer(session_factory=session_factory_for(engine))  # valfri motor, t.ex. i tester
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

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


def database_session_factory() -> SessionFactory:
    """Lakebase via DATABASE_URL (utils.db). Motorn skapas först vid första operationen."""
    state: dict[str, SessionFactory] = {}

    def scope() -> AbstractContextManager[Session]:
        if "factory" not in state:
            from utils.db import make_engine

            state["factory"] = session_factory_for(make_engine())
        return state["factory"]()

    return scope
