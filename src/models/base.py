"""Declarative base för alla SQLAlchemy-modeller.

All ORM-kod i projektet utgår från `Base` definierad här. Se 02_system/databasschema.md
för schemats dokumentation och BESLUTSLOGG B-018 (databas) samt B-014 (SQLAlchemy som ORM).
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
