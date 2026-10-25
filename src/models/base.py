"""Declarative base för alla SQLAlchemy-modeller.

All ORM-kod i projektet utgår från `Base` definierad här. Se 02_system/databasschema.md
för schemats dokumentation och BESLUTSLOGG B-018 (databas) samt B-014 (SQLAlchemy som ORM).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import UUID, DateTime, func
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


@compiles(UUID, "sqlite")
def _uuid_as_text_in_sqlite(type_, compiler, **kw):
    """UUID-kolumner som text i SQLite (demo- och testdatabaserna); Postgres får sin egen UUID-typ.

    Typnamnet UUID ger NUMERIC-affinitet i SQLite: en hexsträng med bara siffror (eller siffror
    med ett 'e') lagras då som tal och kommer tillbaka som float – SQLAlchemy kan inte läsa den
    som UUID, och precisionen går förlorad. CHAR(32) är samma lagring som SQLAlchemys
    generiska Uuid använder i SQLite.
    """
    return "CHAR(32)"


class Base(DeclarativeBase):
    """Gemensam bas för alla modeller. Innehåller `created_at` och `updated_at`."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
