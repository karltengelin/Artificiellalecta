"""SQLAlchemy-modell för produktparametrar som versionerad data (Fas 3c, B-035).

Se 02_system/databasschema.md §9h. Varje rad är en version av en parameter som
styr premieberäkningen – premieålder, premiesatser och brytpunkter – med
giltighetsintervall, produktregel, källa och beslut. Tjänstelagret slår upp den
version som gäller för premiemånaden (services/parameters.py) och skickar den
till premiemotorn. Om en version är kommande, gällande eller upphörd härleds av
datumen; `status` säger bara om versionen dragits tillbaka.

Inga personuppgifter.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

#: Kända parametrar och deras enhet. Nya nycklar kräver ändring här och i premiemotorn.
PARAMETER_UNITS = {
    "premium_age_start": "years",
    "premium_age_end": "years",
    "premium_rate_low": "rate",
    "premium_rate_high": "rate",
    "premium_breakpoint_low_ibb": "ibb",
    "premium_breakpoint_high_ibb": "ibb",
}
PARAMETER_STATUSES = ("valid", "withdrawn")


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class ProductParameter(Base):
    """En version av en produktparameter med giltighetsintervall."""

    __tablename__ = "product_parameters"
    __table_args__ = (
        UniqueConstraint("key", "valid_from", name="uq_product_parameters_key_valid_from"),
        CheckConstraint(_in("key", PARAMETER_UNITS), name="ck_product_parameters_key"),
        CheckConstraint(_in("unit", sorted(set(PARAMETER_UNITS.values()))), name="ck_product_parameters_unit"),
        CheckConstraint(_in("status", PARAMETER_STATUSES), name="ck_product_parameters_status"),
        CheckConstraint("value >= 0", name="ck_product_parameters_value"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_product_parameters_interval"),
        CheckConstraint(
            "EXTRACT(DAY FROM valid_from) = 1", name="ck_product_parameters_first_of_month"
        ).ddl_if(dialect="postgresql"),
        # Samma regel i testdatabasen (SQLite saknar EXTRACT)
        CheckConstraint(
            "CAST(strftime('%d', valid_from) AS INTEGER) = 1", name="ck_product_parameters_first_of_month"
        ).ddl_if(dialect="sqlite"),
        Index("ix_product_parameters_key", "key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    rule_id: Mapped[str] = mapped_column(String(20), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(10), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(60), nullable=False)
    decision_ref: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="valid")
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)

    def __repr__(self) -> str:
        return f"<ProductParameter {self.key}={self.value} från {self.valid_from}>"
