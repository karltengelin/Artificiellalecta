"""SQLAlchemy-modell för ärenden – handläggaragentens arbetsenhet och mandat (Fas 5, B-033).

Se 02_system/databasschema.md §9g. Raden har ärendets aktuella status och utfall;
historiken står i operation_events via case_id (= case_number), eftersom varje
ändring går genom en tjänsteoperation. Typens uppgifter ligger i `details` och
valideras per typ i tjänstelagret.

⚠️  `details` kan innehålla lön och fri text – personuppgifter (B-006).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# none_as_null: None blir SQL NULL och stoppas av NOT NULL, inte JSON-värdet null
_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")

CASE_TYPES = ("salary_report",)
CASE_STATUSES = ("open", "in_progress", "waiting_approval", "waiting_info", "closed")
CASE_OUTCOMES = ("approved", "rejected", "supplement_requested", "manual_review", "no_action")
CASE_CHANNELS = ("manual", "employer_file", "customer_portal", "chatbot")
#: Utfall som kräver en anteckning vid stängning (PR-ITP1-031: avslag och manuell prövning motiveras)
OUTCOMES_REQUIRING_NOTE = ("rejected", "manual_review")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Case(Base):
    """Ett ärende: något som kommit in och ska handläggas."""

    __tablename__ = "cases"
    __table_args__ = (
        # SUBSTR i stället för LIKE 'CASE-%': procenttecknet dubbleras när DDL:en kompileras för psycopg2
        CheckConstraint("SUBSTR(case_number, 1, 5) = 'CASE-' AND LENGTH(case_number) = 11", name="ck_cases_number"),
        CheckConstraint(_in("case_type", CASE_TYPES), name="ck_cases_type"),
        CheckConstraint(_in("status", CASE_STATUSES), name="ck_cases_status"),
        CheckConstraint(f"outcome IS NULL OR {_in('outcome', CASE_OUTCOMES)}", name="ck_cases_outcome"),
        CheckConstraint(_in("channel", CASE_CHANNELS), name="ck_cases_channel"),
        CheckConstraint("insured_person_id IS NOT NULL OR employer_id IS NOT NULL", name="ck_cases_subject"),
        CheckConstraint(
            "(status = 'closed' AND outcome IS NOT NULL AND closed_by IS NOT NULL AND closed_at IS NOT NULL)"
            " OR (status <> 'closed' AND outcome IS NULL AND closed_by IS NULL AND closed_at IS NULL)",
            name="ck_cases_closed",
        ),
        CheckConstraint(
            f"outcome IS NULL OR NOT {_in('outcome', OUTCOMES_REQUIRING_NOTE)} OR closing_note IS NOT NULL",
            name="ck_cases_closing_note",
        ),
        CheckConstraint(
            "period_month IS NULL OR EXTRACT(DAY FROM period_month) = 1",
            name="ck_cases_period_first_of_month",
        ).ddl_if(dialect="postgresql"),
        # Samma regel i testdatabasen (SQLite saknar EXTRACT)
        CheckConstraint(
            "period_month IS NULL OR CAST(strftime('%d', period_month) AS INTEGER) = 1",
            name="ck_cases_period_first_of_month",
        ).ddl_if(dialect="sqlite"),
        Index("ix_cases_status", "status"),
        Index("ix_cases_case_type", "case_type"),
        Index("ix_cases_insured_person_id", "insured_person_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    case_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    insured_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insured_persons.id", ondelete="RESTRICT"), nullable=True
    )
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policies.id", ondelete="RESTRICT"), nullable=True
    )
    employer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employers.id", ondelete="RESTRICT"), nullable=True
    )
    period_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    closed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closing_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Case {self.case_number} {self.case_type} {self.status}>"
