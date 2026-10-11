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


def test_backup_laser_databasens_faktiska_schema(tmp_path):
    # T.ex. Lakebase före en migration: en modelltabell saknas och en annan saknar en ny kolumn
    engine = empty_engine()
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE base_amounts (year INTEGER PRIMARY KEY, income_base_amount_sek NUMERIC)")
        conn.exec_driver_sql("INSERT INTO base_amounts VALUES (2026, 83400)")
    folder = backup_database(engine, tmp_path)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["tables"] == ["base_amounts"]
    assert manifest["row_counts"] == {"base_amounts": 1}


def test_aterstallning_lagger_in_rattelser_efter_det_de_pekar_pa(insurance_db, tmp_path):
    from datetime import date
    from decimal import Decimal

    from sqlalchemy import event

    from models import SalaryReport

    with insurance_db.session_factory() as s:
        original = s.scalars(select(PremiumTransaction).where(PremiumTransaction.transaction_type == "premium")).first()
        s.add(PremiumTransaction(benefit_id=original.benefit_id, period_month=original.period_month,
                                 transaction_type="adjustment", amount_sek=Decimal("10"),
                                 corrects_transaction_id=original.id))
        first = SalaryReport(insured_person_id=insurance_db.ids.person, employer_id=insurance_db.ids.employer,
                             period_month=date(2025, 6, 1), version=1, pensionable_salary_sek=Decimal(1),
                             source="manual", received_date=date(2025, 7, 1))
        s.add(first)
        s.flush()
        s.add(SalaryReport(insured_person_id=insurance_db.ids.person, employer_id=insurance_db.ids.employer,
                           period_month=date(2025, 6, 1), version=2, supersedes_id=first.id,
                           pensionable_salary_sek=Decimal(2), source="manual", received_date=date(2025, 7, 2)))
    folder = backup_database(insurance_db.engine, tmp_path)
    for name in ("premium_transactions", "salary_reports"):  # värsta ordningen: pekarna först
        path = folder / f"{name}.jsonl"
        path.write_text("\n".join(reversed(path.read_text(encoding="utf-8").splitlines())) + "\n", encoding="utf-8")

    target = empty_engine()

    @event.listens_for(target, "connect")
    def _foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    restored = restore_database(target, folder)
    assert (restored["premium_transactions"], restored["salary_reports"]) == (6, 2)
    assert counts(target) == counts(insurance_db.engine)
