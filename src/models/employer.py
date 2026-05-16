"""SQLAlchemy-modell för försäkringstagare (arbetsgivare med ITP-avtal).

Se 02_system/databasschema.md §3 för fullständig dokumentation av tabellen.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .insured_person import InsuredPerson


class Employer(Base):
    """Försäkringstagare – en arbetsgivare som har tecknat ITP-avtal."""

    __tablename__ = "employers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'terminated', 'paused')",
            name="ck_employers_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    org_number: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    address_street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address_postal_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    address_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    collective_agreement: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="ITP",
        server_default="ITP",
    )
    affiliation_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )

    insured_persons: Mapped[list["InsuredPerson"]] = relationship(
        back_populates="employer",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Employer {self.org_number} {self.name!r}>"
