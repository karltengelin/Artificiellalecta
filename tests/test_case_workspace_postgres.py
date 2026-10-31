"""Migration och samtidighet mot isolerat Postgres-schema; aldrig beståndet."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect

from models import Base
from tests.case_work_helpers import (
    HUMAN,
    create,
    make_workspace,
    proposal,
    read_case,
    work,
)
from tests.conftest import seed_insurance
from tests.test_services_postgres import TEST_URL, isolated_schema
from utils.migration_case_work import NAMES, migrate_case_work

pytestmark = [pytest.mark.postgres, pytest.mark.skipif(not TEST_URL, reason="Isolerad Postgres saknas")]


def test_migrationen_ar_avgransad_idempotent_och_bevarar_data():
    with isolated_schema() as db:
        Base.metadata.create_all(db.engine, tables=[t for t in Base.metadata.sorted_tables if t.name not in NAMES])
        seed_insurance(db.session_factory)
        dry = migrate_case_work(db.engine)
        assert not dry.applied and not set(inspect(db.engine).get_table_names()) & NAMES
        done = migrate_case_work(db.engine, dry_run=False)
        assert done.applied and done.row_counts == dry.row_counts
        assert NAMES <= set(inspect(db.engine).get_table_names())
        assert migrate_case_work(db.engine, dry_run=False).already_applied


def test_tva_arbetare_kan_inte_hamta_samma_uppdrag(tmp_path):
    with isolated_schema() as db:
        Base.metadata.create_all(db.engine)
        seed_insurance(db.session_factory)
        env = make_workspace(db.session_factory, tmp_path)
        ident = env.workspace.submit(create(env), "Handlägg", actor=HUMAN, key="samtidig", mode="handle")
        with ThreadPoolExecutor(2) as pool:
            claims = list(pool.map(lambda _: env.workspace._claim(ident, datetime.now(UTC)), range(2)))
        assert sum(c is not None for c in claims) == 1


@pytest.mark.parametrize("automatic", [False, True])
def test_hela_kedjan_med_manskligt_eller_automatiskt_beslut(tmp_path, automatic):
    with isolated_schema() as db:
        Base.metadata.create_all(db.engine)
        seed_insurance(db.session_factory)
        env = make_workspace(db.session_factory, tmp_path, automatic=automatic)
        number = create(env)
        ident = env.workspace.submit(number, "Handlägg", actor=HUMAN, key="hela", mode="handle")
        env.fake.queue(read_case(number), proposal())
        assert env.workspace.process(ident)
        if not automatic:
            from services import OperationContext

            env.trusted.approve(env.trusted.approvals.list("pending")[0].id, OperationContext(actor=HUMAN))
            env.workspace.settle(ident)
        assert work(env, ident).status == "completed"


def test_schemat_aterkoar_inte_samma_underlag(tmp_path):
    with isolated_schema() as db:
        Base.metadata.create_all(db.engine)
        seed_insurance(db.session_factory)
        env = make_workspace(db.session_factory, tmp_path, scheduled=True)
        create(env)
        now = datetime(2026, 11, 2, 7, tzinfo=UTC)
        assert env.workspace.enqueue_daily(now=now) == 1
        assert env.workspace.enqueue_daily(now=now) == 0
