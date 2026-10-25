"""SQLAlchemy-modeller för flödesmotorn – flöden, steg och grindbeslut (Fas 3c 3c-2, B-035).

Se 02_system/databasschema.md §9i och 02_system/flaggskeppsflöde.md §6. Tabellerna hör
till harness (`src/agents/flows/`), inte till försäkringstjänstelagret (harness.md §4.3):
de skrivs bara av flödesmotorn, med operatören som aktör för grindbeslut och manuella steg.

`flows.version` är flödets version för optimistisk låsning: varje ändring görs med en
villkorlig UPDATE på den version som lästes, så att två klick inte tar samma steg.
`flow_gate_decisions` är append-only och binder hashen av det underlag beslutet gäller.

Stegens resultat är strukturerat underlag utan personuppgifter (agents.results); agenternas
körjournal ligger kvar i logs/agent_runs/ och länkas med `run_id` (val J).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")

FLOW_STATUSES = (
    "running", "waiting_gate", "waiting_manual", "waiting_approval",
    "completed", "rejected", "cancelled", "failed", "reconciliation_required",
)
#: Flöden som är avslutade – inget steg tas längre
FINISHED_FLOW_STATUSES = ("completed", "rejected", "cancelled", "failed")
STEP_KINDS = ("agent", "gate", "manual", "system")
STEP_STATUSES = (
    "pending", "running", "completed", "waiting", "rejected", "failed", "skipped", "reconciliation_required",
)
GATE_DECISIONS = ("approved", "rejected")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Flow(Base):
    """Ett flöde: en körning av en flödesdefinition, med aktuellt steg och version."""

    __tablename__ = "flows"
    __table_args__ = (
        # SUBSTR i stället för LIKE 'FLOW-%': procenttecknet dubbleras när DDL:en kompileras för psycopg2
        CheckConstraint("SUBSTR(flow_id, 1, 5) = 'FLOW-' AND LENGTH(flow_id) = 11", name="ck_flows_id"),
        CheckConstraint(_in("status", FLOW_STATUSES), name="ck_flows_status"),
        CheckConstraint("version >= 1", name="ck_flows_version"),
        CheckConstraint(
            f"({_in('status', FINISHED_FLOW_STATUSES)}) = (finished_at IS NOT NULL)", name="ck_flows_finished"
        ),
        Index("ix_flows_status", "status"),
    )

    flow_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    flow_type: Mapped[str] = mapped_column(String(60), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(60), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Flow {self.flow_id} {self.flow_type} {self.status} v{self.version}>"


class FlowStep(Base):
    """Ett steg i ett flöde, i definitionens ordning."""

    __tablename__ = "flow_steps"
    __table_args__ = (
        UniqueConstraint("flow_id", "step_key", name="uq_flow_steps_key"),
        UniqueConstraint("flow_id", "position", name="uq_flow_steps_position"),
        CheckConstraint(_in("kind", STEP_KINDS), name="ck_flow_steps_kind"),
        CheckConstraint(_in("status", STEP_STATUSES), name="ck_flow_steps_status"),
        CheckConstraint("position >= 1", name="ck_flow_steps_position"),
        CheckConstraint("status <> 'completed' OR result_hash IS NOT NULL", name="ck_flow_steps_completed_hash"),
        Index("ix_flow_steps_flow_id", "flow_id"),
        Index("ix_flow_steps_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flow_id: Mapped[str] = mapped_column(String(20), ForeignKey("flows.flow_id", ondelete="RESTRICT"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(60), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    team: Mapped[str | None] = mapped_column(String(40), nullable=True)
    agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)
    result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_refs: Mapped[list[str] | None] = mapped_column(_JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<FlowStep {self.flow_id}/{self.step_key} {self.kind} {self.status}>"


class FlowGateDecision(Base):
    """Ett grindbeslut. Append-only: ett nytt beslut är en ny rad, ingen rad ändras."""

    __tablename__ = "flow_gate_decisions"
    __table_args__ = (
        CheckConstraint(_in("decision", GATE_DECISIONS), name="ck_flow_gate_decisions_decision"),
        CheckConstraint("decision <> 'rejected' OR note IS NOT NULL", name="ck_flow_gate_decisions_note"),
        Index("ix_flow_gate_decisions_flow_id", "flow_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flow_id: Mapped[str] = mapped_column(String(20), ForeignKey("flows.flow_id", ondelete="RESTRICT"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(60), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(100), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    bound_steps: Mapped[list[str]] = mapped_column(_JSON, nullable=False)
    bound_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    def __repr__(self) -> str:
        return f"<FlowGateDecision {self.flow_id}/{self.step_key} {self.decision}>"
