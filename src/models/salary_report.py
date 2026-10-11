"""SQLAlchemy-modell för löneunderlag – pensionsmedförande lön per månad (PR-ITP1-014).

Se 02_system/databasschema.md §8b. Append-only och versionerad: en rättelse är
en ny rad med `supersedes_id` mot versionen den ersätter; gällande underlag är
den högsta versionen. 0,00 är en rapporterad noll – ingen rad betyder att
rapport saknas. Skrivs av tjänstelagrets register_salary_report.

⚠️  Lön är personuppgift (B-006).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

#: Ursprung: arbetsgivarens rapport eller manuellt registrerat underlag
SALARY_REPORT_SOURCES = ("employer", "manual")


class SalaryReport(Base):
    """Löneunderlag för en försäkrad hos en arbetsgivare en kalendermånad (en version)."""

    __tablename__ = "salary_reports"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_salary_reports_version"),
        CheckConstraint(
            "(version = 1 AND supersedes_id IS NULL) OR (version > 1 AND supersedes_id IS NOT NULL)",
            name="ck_salary_reports_chain",
        ),
        CheckConstraint("pensionable_salary_sek >= 0", name="ck_salary_reports_salary"),
        CheckConstraint("source IN ('employer', 'manual')", name="ck_salary_reports_source"),
        CheckConstraint(
            "EXTRACT(DAY FROM period_month) = 1",
            name="ck_salary_reports_period_first_of_month",
        ).ddl_if(dialect="postgresql"),
        # Samma regel i testdatabasen (SQLite saknar EXTRACT)
        CheckConstraint(
            "CAST(strftime('%d', period_month) AS INTEGER) = 1",
            name="ck_salary_reports_period_first_of_month",
        ).ddl_if(dialect="sqlite"),
        Index(
            "uq_salary_reports_version",
            "insured_person_id", "employer_id", "period_month", "version",
            unique=True,
        ),
        Index("uq_salary_reports_supersedes", "supersedes_id", unique=True),
        # Samma rapport (avsändarens referens) registreras inte två gånger
        Index(
            "uq_salary_reports_source_reference",
            "employer_id", "source_reference",
            unique=True,
            postgresql_where="source_reference IS NOT NULL",
            sqlite_where=text("source_reference IS NOT NULL"),  # testdatabasen
        ),
        Index("ix_salary_reports_person_period", "insured_person_id", "period_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    insured_person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insured_persons.id", ondelete="RESTRICT"), nullable=False
    )
    employer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employers.id", ondelete="RESTRICT"), nullable=False
    )
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("salary_reports.id", ondelete="RESTRICT"), nullable=True
    )
    pensionable_salary_sek: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)

    def __repr__(self) -> str:
        return f"<SalaryReport {self.period_month:%Y-%m} v{self.version}>"
