"""Versionerad lagring för den lokala uppdragskön. Ett anspråk per uppdrag."""

from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, select, update
from sqlalchemy.dialects.sqlite import insert

from services.errors import AccessDeniedError, ConflictError, NotFoundError
from utils.checksums import canonical_hash

missions = Table(
    "company_missions", MetaData(),
    Column("id", String(32), primary_key=True),
    Column("owner", String(100), nullable=False, index=True),
    Column("environment", String(20), nullable=False),
    Column("dataset", String(100), nullable=False),
    Column("created", String(32), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("state", JSON, nullable=False),
)


def now():
    return datetime.now(UTC).isoformat(timespec="seconds")


def require_operator(actor):
    if actor.type != "human":
        raise AccessDeniedError("Bolagsuppdrag kräver en verifierad operatör",
                                operation="company_mission", actor_id=actor.id)


class MissionStore:
    def __init__(self, factory, *, dataset):
        self.factory = factory
        self.dataset = dataset

    def initialize(self):
        with self.factory() as session:
            connection = session.connection()
            if connection.dialect.name != "sqlite":
                raise ValueError("Bolagspiloten kräver lokal SQLite")
            missions.metadata.create_all(connection)

    def create(self, ident, actor, state):
        require_operator(actor)
        with self.factory() as session:
            session.execute(insert(missions).values(
                id=ident, owner=actor.id, environment="demo", dataset=self.dataset,
                created=now(), revision=1, state=state,
            ).on_conflict_do_nothing(index_elements=[missions.c.id]))
            existing = self.load(session, ident, actor)
            if existing["state"]["briefs"][0] != state["briefs"][0]:
                raise ConflictError("Beställningsnyckeln hör till en annan beställning")
            return existing

    def list(self, actor):
        require_operator(actor)
        with self.factory() as session:
            return list(session.execute(select(missions).where(
                missions.c.owner == actor.id, missions.c.environment == "demo", missions.c.dataset == self.dataset,
            ).order_by(missions.c.created.desc(), missions.c.id.desc()).limit(100)).mappings())

    def load(self, session, ident, actor):
        require_operator(actor)
        row = session.execute(select(missions).where(
            missions.c.id == ident, missions.c.owner == actor.id,
            missions.c.environment == "demo", missions.c.dataset == self.dataset,
        )).mappings().one_or_none()
        if row is None:
            raise NotFoundError("Bolagsuppdraget finns inte i denna miljö")
        return row

    def get(self, ident, actor):
        with self.factory() as session:
            return self.load(session, ident, actor)

    @contextmanager
    def edit(self, ident, actor, *, revision=None, claim=None, replay=None):
        with self.factory() as session:
            row = self.load(session, ident, actor)
            state = row["state"]
            if revision is not None and row["revision"] != revision and not (replay and replay(state)):
                raise ConflictError("Uppdraget har ändrats. Läs om sidan")
            if claim is not None and state["claim"] != claim:
                raise ConflictError("Körningen äger inte längre uppdraget")
            before = canonical_hash(state)
            yield state
            if canonical_hash(state) == before:
                return
            changed = session.execute(update(missions).where(
                missions.c.id == ident, missions.c.revision == row["revision"],
            ).values(state=state, revision=row["revision"] + 1))
            if changed.rowcount != 1:
                raise ConflictError("Uppdraget ändrades samtidigt. Läs om sidan")
