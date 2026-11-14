"""Delade provhjälpare för röktest med lokal demo eller isolerad svc_test."""

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from types import SimpleNamespace

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


@dataclass
class Report:
    checks: list[tuple[str, str, bool, str]] = field(default_factory=list)  # (slag, kontroll, ok, detalj)
    notes: list[str] = field(default_factory=list)
    cost: float = 0.0

    def check(self, kind: str, label: str, passed: bool, detail: str = "") -> bool:
        self.checks.append((kind, label, passed, detail))
        print(f"  [{'OK' if passed else 'FEL'}] {kind}: {label}" + (f" – {detail}" if detail else ""))
        return passed

    def note(self, text: str) -> None:
        self.notes.append(text)
        print(f"  [obs] {text}")

    @property
    def ok(self) -> bool:
        return all(passed for _, _, passed, _ in self.checks)


@contextmanager
def demo_database(born_from: int | None = None) -> Iterator[SimpleNamespace]:
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from services.db import session_factory_for
    from utils.demo_data import create_demo_database

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False, born_from=born_from)
    try:
        yield SimpleNamespace(label="demo (SQLite i minnet)", factory=session_factory_for(engine), team_factories={})
    finally:
        engine.dispose()


@contextmanager
def svc_test_database(teams: tuple[str, ...] = ("aktuarie", "compliance"),
                      born_from: int | None = None, build=None) -> Iterator[SimpleNamespace]:
    """Eget schema i den isolerade testdatabasen, med teamens rättigheter på testrollerna.

    `born_from` utelämnar demopersoner födda före året (se `create_demo_database`). `build(engine)`
    bygger schemat och beståndet i stället för `create_demo_database`, t.ex. via en migration.
    """
    from sqlalchemy import create_engine

    from services.db import session_factory_for
    from utils.agent_roles import ROLE_GRANTS
    from utils.demo_data import create_demo_database

    url = os.environ.get("SERVICES_TEST_POSTGRES_URL")
    if not url:
        raise SystemExit("SERVICES_TEST_POSTGRES_URL saknas i .env")
    if url == os.environ.get("DATABASE_URL"):
        raise SystemExit("SERVICES_TEST_POSTGRES_URL är DATABASE_URL – röktestet körs aldrig mot beståndet")
    shared = os.environ.get("SERVICES_TEST_AGENT_POSTGRES_URL")
    candidates = {team: os.environ.get(f"SERVICES_TEST_{team.upper()}_POSTGRES_URL") for team in teams}
    production = {os.environ.get(f"AGENT_{t.upper()}_DATABASE_URL") for t in ROLE_GRANTS} - {None}
    if production & ({shared, *candidates.values()} - {None}):
        raise SystemExit("En testrolls anslutning pekar på beståndet")

    name = f"rooktest_{uuid.uuid4().hex[:12]}"
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{name}"')
    engine = create_engine(url, connect_args={"options": f"-csearch_path={name}"})
    agent_engines = []
    try:
        if build is None:
            create_demo_database(engine, with_proposals=False, born_from=born_from)
        else:
            build(engine)
        team_factories, used = {}, set()
        for team, own in candidates.items():
            agent_url = own or shared
            if not agent_url:
                continue
            agent_engine = create_engine(agent_url, connect_args={"options": f"-csearch_path={name}"})
            agent_engines.append(agent_engine)
            with agent_engine.connect() as conn:
                login = conn.exec_driver_sql("SELECT current_user").scalar_one()
            if login in used:  # samma inloggning kan bara bära ett teams rättigheter i schemat
                continue
            used.add(login)
            with engine.begin() as conn:
                for statement in replace(ROLE_GRANTS[team], role=login).statements(name):
                    conn.exec_driver_sql(statement)
            team_factories[team] = session_factory_for(agent_engine)
        yield SimpleNamespace(label=f"svc_test, schema {name} (tas bort efteråt)", factory=session_factory_for(engine),
                              team_factories=team_factories)
    finally:
        for agent_engine in agent_engines:
            agent_engine.dispose()
        engine.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA "{name}" CASCADE')
        admin.dispose()
