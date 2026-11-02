"""Varaktig aktuariell dialog, källunderlag och spårbara analysleveranser."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")


class ActuarialDataset(Base):
    __tablename__ = "actuarial_datasets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[dict] = mapped_column(_JSON)
    checksum: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActuarialConversation(Base):
    __tablename__ = "actuarial_conversations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActuarialTurn(Base):
    __tablename__ = "actuarial_turns"
    __table_args__ = (
        UniqueConstraint("conversation_id", "submission_key", name="uq_actuarial_turn_submission"),
        CheckConstraint("status IN ('queued','running','completed','needs_human','failed','interrupted')",
                        name="ck_actuarial_turn_status"),
        Index("uq_actuarial_turn_active", "conversation_id", unique=True,
              postgresql_where=text("status IN ('queued','running')"),
              sqlite_where=text("status IN ('queued','running')")),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("actuarial_conversations.id"), index=True)
    submission_key: Mapped[str] = mapped_column(String(100))
    instruction: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    submitted_by: Mapped[str] = mapped_column(String(100))
    run_id: Mapped[str] = mapped_column(String(64), unique=True)
    result: Mapped[dict] = mapped_column(_JSON, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActuarialAnalysis(Base):
    __tablename__ = "actuarial_analyses"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("actuarial_conversations.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[dict] = mapped_column(_JSON)
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
