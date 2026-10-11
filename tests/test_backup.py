"""Backup och återställning: allt som skrivs ut ska kunna läsas in igen oförändrat."""

import json

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from models import Base, PolicyState, PremiumTransaction
from utils.backup import backup_database, restore_database

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")


def empty_engine():
    return create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})


def counts(engine):
    with engine.connect() as conn:
        return {t.name: conn.execute(select(func.count()).select_from(t)).scalar() for t in Base.metadata.sorted_tables}


def test_backup_och_aterstallning_ger_samma_data(insurance_db, tmp_path):
    folder = backup_database(insurance_db.engine, tmp_path)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["row_counts"] == counts(insurance_db.engine)

    target = empty_engine()
    restored = restore_database(target, folder)
    assert restored == {k: v for k, v in manifest["row_counts"].items()}
    assert counts(target) == counts(insurance_db.engine)

    with target.connect() as conn:
        amounts = sorted(conn.execute(select(PremiumTransaction.amount_sek)).scalars())
        states = conn.execute(select(PolicyState.state).order_by(PolicyState.valid_from)).scalars().all()
    with insurance_db.engine.connect() as conn:
        assert amounts == sorted(conn.execute(select(PremiumTransaction.amount_sek)).scalars())
    assert states == ["premium_paying", "paid_up"]


def test_aterstallning_vagrar_skriva_over_data(insurance_db, tmp_path):
    folder = backup_database(insurance_db.engine, tmp_path)
    with pytest.raises(RuntimeError, match="inte tomma"):
        restore_database(insurance_db.engine, folder)
