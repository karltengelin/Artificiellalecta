"""SQLAlchemy-modell för basbelopp per år (parametertabell).

Se 02_system/databasschema.md §7. Premiemotorn läser basbelopp härifrån –
aldrig hårdkodade i beräkningskod (01_domän/ITP1_regelverk.md §6).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class BaseAmount(Base):
    """Basbelopp för ett kalenderår."""

    __tablename__ = "base_amounts"
    __table_args__ = (
        CheckConstraint(
            "income_base_amount_sek > 0",
            name="ck_base_amounts_ibb_positive",
        ),
        CheckConstraint(
            "price_base_amount_sek IS NULL OR price_base_amount_sek > 0",
            name="ck_base_amounts_pbb_positive",
        ),
    )

    year: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    income_base_amount_sek: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    price_base_amount_sek: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<BaseAmount {self.year} IBB={self.income_base_amount_sek}>"
