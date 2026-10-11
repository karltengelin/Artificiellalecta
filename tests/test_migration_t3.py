"""Migrationen för Fas 1f T3 (scripts/migrations/migrate_t3_schema.py, databasschema.md §12).

Här prövas DDL:en och skydden utan databas. Själva migrationen från det gamla
schemat körs mot Postgres i tests/test_services_postgres.py – SQLite kan inte
lägga till constraints med ALTER TABLE.
"""

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from models import PremiumTransaction
from utils.migration_t3 import compile_ddl, migrate_t3, schema_state


def test_ddl_i_korordning_harledd_ur_modellerna():
    statements = compile_ddl(postgresql.dialect())
    assert statements[0].startswith("CREATE TABLE salary_reports")
    assert "CONSTRAINT ck_salary_reports_period_first_of_month CHECK (EXTRACT(DAY FROM period_month) = 1)" in statements[0]
    assert "strftime" not in statements[0]  # SQLite-varianten hör inte hemma i Postgres
    assert statements[1:5] == [
        "CREATE INDEX ix_salary_reports_person_period ON salary_reports (insured_person_id, period_month)",
        (
            "CREATE UNIQUE INDEX uq_salary_reports_source_reference ON salary_reports (employer_id, source_reference) "
            "WHERE source_reference IS NOT NULL"
        ),
        "CREATE UNIQUE INDEX uq_salary_reports_supersedes ON salary_reports (supersedes_id)",
        (
            "CREATE UNIQUE INDEX uq_salary_reports_version ON salary_reports "
            "(insured_person_id, employer_id, period_month, version)"
        ),
    ]
    assert statements[5:] == [
        "ALTER TABLE premium_transactions ADD COLUMN corrects_transaction_id UUID",
        (
            "ALTER TABLE premium_transactions ADD FOREIGN KEY(corrects_transaction_id) "
            "REFERENCES premium_transactions (id) ON DELETE RESTRICT"
        ),
        (
            "ALTER TABLE premium_transactions ADD CONSTRAINT ck_premium_transactions_correction_type "
            "CHECK (corrects_transaction_id IS NULL OR transaction_type = 'adjustment')"
        ),
        "CREATE INDEX ix_premium_transactions_corrects_transaction_id ON premium_transactions (corrects_transaction_id)",
    ]


def test_ingen_ddl_andrar_eller_tar_bort_befintliga_rader():
    statements = compile_ddl(postgresql.dialect())
    for statement in statements:
        assert not statement.upper().startswith(("UPDATE", "DELETE", "DROP", "TRUNCATE", "INSERT"))
    # Den nya kolumnen är nullbar utan standardvärde – befintliga rader skrivs inte om
    (add_column,) = [s for s in statements if "ADD COLUMN" in s]
    assert "NOT NULL" not in add_column and "DEFAULT" not in add_column


def test_ddl_genereringen_andrar_inte_modellernas_metadata():
    # SQLAlchemys AddConstraint markerar constraint-objektet så att CREATE TABLE hoppar över det –
    # migrationen får inte påverka create_all i samma process (t.ex. testdatabaserna)
    compile_ddl(postgresql.dialect())
    create = str(CreateTable(PremiumTransaction.__table__).compile(dialect=postgresql.dialect()))
    assert "CONSTRAINT ck_premium_transactions_correction_type CHECK" in create
    assert "FOREIGN KEY(corrects_transaction_id) REFERENCES premium_transactions (id)" in create


def test_migrationen_vagrar_annat_an_postgres(insurance_db):
    with pytest.raises(RuntimeError, match="Postgres"):
        migrate_t3(insurance_db.engine, dry_run=True)


def test_testdatabasen_har_redan_det_nya_schemat(insurance_db):
    with insurance_db.engine.connect() as conn:
        assert schema_state(conn) == (True, True)
