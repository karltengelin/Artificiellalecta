"""SQLAlchemy-modell för försäkrade (anställda som omfattas av ITP1).

Se 02_system/databasschema.md §4 för fullständig dokumentation av tabellen.

⚠️  Tabellen innehåller personuppgifter (personnummer, namn, kontakt).
    Skills som läser/skriver mot den måste deklareras med behörighetslista (B-006).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .employer import Employer


class InsuredPerson(Base):
    """Försäkrad – en anställd som omfattas av ITP1 ålderspension."""

    __tablename__ = "insured_persons"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'terminated', 'retired', 'deceased')",
            name="ck_insured_persons_status",
        ),
        CheckConstraint(
            "employment_rate IS NULL OR (employment_rate >= 0 AND employment_rate <= 100)",
            name="ck_insured_persons_employment_rate",
        ),
        CheckConstraint(
            "monthly_salary_sek IS NULL OR monthly_salary_sek >= 0",
            name="ck_insured_persons_monthly_salary",
        ),
        Index("ix_insured_persons_employer_status", "employer_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    personal_id_number: Mapped[str] = mapped_column(
        String(12), nullable=False, unique=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    employer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    employment_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    employment_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    monthly_salary_sek: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    employment_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    itp1_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )

    employer: Mapped["Employer"] = relationship(back_populates="insured_persons")

    def __repr__(self) -> str:
        # PNR redigeras i repr för att inte slumpa ut PII i loggar
        masked_pnr = (
            f"{self.personal_id_number[:8]}-XXXX" if self.personal_id_number else "?"
        )
        return f"<InsuredPerson {masked_pnr} {self.last_name!r}>"
