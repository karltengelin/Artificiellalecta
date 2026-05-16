"""Databasanslutning för SQLAlchemy.

Läser `DATABASE_URL` från miljövariabler (eller `.env` om `python-dotenv` finns).
Exponerar en engine och en sessionsfabrik som övriga skript och agenter kan
använda. Inga credentials hårdkodas (B-014, projektets generella regel).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

try:
    # python-dotenv är en mjuk dep – om den finns laddar vi .env automatiskt
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL saknas. Lägg in den i .env (se .env.example för mall)."
        )
    return url


def make_engine(echo: bool = False) -> Engine:
    """Skapar en SQLAlchemy-engine. `echo=True` loggar all SQL till stdout."""
    return create_engine(_get_database_url(), echo=echo, future=True)


def make_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Returnerar en sessionsfabrik. Skapar default-engine om ingen ges."""
    if engine is None:
        engine = make_engine()
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Context manager för en session med automatisk commit/rollback."""
    SessionLocal = make_session_factory(engine)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
