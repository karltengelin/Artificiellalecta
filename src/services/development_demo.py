"""Lokala testdubblar för GitHub och målmiljön, med varaktiga kvitton."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from hashlib import sha1, sha256
from pathlib import Path
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from services.change_requests import ReviewReferences
from services.errors import ConflictError

DEMO_REPOSITORY = "demo/artificiellalecta"
DEMO_BRANCH = "main"
REQUIRED_CHECKS = frozenset({"kodprov"})
Commit = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]


class OutcomeUnknown(RuntimeError):
    """Ett utfall kan ännu inte bekräftas från dess källa."""


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    reference: str
    passed: bool
    summary: str


class Candidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    pull_request: UUID
    repository: str = DEMO_REPOSITORY
    branch: str = DEMO_BRANCH
    base: Commit
    head: Commit
    diff: str
    references: ReviewReferences
    checks: tuple[Evidence, ...]

    @property
    def fingerprint(self) -> str:
        return sha256(self.model_dump_json().encode("utf-8")).hexdigest()

    def eligible(self, request_id: UUID) -> bool:
        passed = {check.name for check in self.checks if check.passed and check.reference}
        return (self.pull_request == request_id and self.repository == DEMO_REPOSITORY
                and self.branch == DEMO_BRANCH and self.head != self.base and bool(self.diff)
                and REQUIRED_CHECKS <= passed and all(check.passed for check in self.checks)
                and len({check.name for check in self.checks}) == len(self.checks))


class MergeReceipt(BaseModel):
    operation: str
    pull_request: UUID
    head: Commit
    evidence_hash: str
    version: Commit
    merged_at: datetime


class DeploymentReceipt(BaseModel):
    operation: str
    target: str
    version: Commit
    deployed_at: datetime


class TargetState(BaseModel):
    version: Commit
    ready: bool


class TargetCheck(BaseModel):
    target: str
    version: Commit | None
    passed: bool
    summary: str
    checked_at: datetime


def demo_target(request_id: UUID) -> str:
    return f"demo/{request_id}"


class DemoDelivery:
    """Simulerar två externa sanningskällor utan nätverk eller nycklar.

    Testdubblarna använder en separat SQLite-fil så att effekten kan bestå även
    om processen avbryts före ärendets lokala kvitto.
    """

    def __init__(self, demo_path: Path):
        self.path = demo_path.with_suffix(".delivery.db")

    @contextmanager
    def _transaction(self, *, write: bool = False, create: bool = False) -> Iterator[sqlite3.Connection]:
        mode = "rwc" if create else "rw"
        try:
            with closing(sqlite3.connect(f"{self.path.resolve().as_uri()}?mode={mode}", uri=True, timeout=5)) as connection:
                with connection:
                    if create:
                        connection.execute("CREATE TABLE IF NOT EXISTS delivery (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                    if write:
                        connection.execute("BEGIN IMMEDIATE")
                    yield connection
        except sqlite3.Error as exc:
            raise OutcomeUnknown("Testdubbeln kunde inte bekräfta utfallet.") from exc

    @staticmethod
    def _get(connection: sqlite3.Connection, key: str, model):
        row = connection.execute("SELECT value FROM delivery WHERE key = ?", (key,)).fetchone()
        return model.model_validate_json(row[0]) if row else None

    @staticmethod
    def _put(connection: sqlite3.Connection, key: str, value: BaseModel) -> None:
        connection.execute("INSERT OR REPLACE INTO delivery VALUES (?, ?)", (key, value.model_dump_json()))

    def stage(self, candidate: Candidate) -> None:
        with self._transaction(write=True, create=True) as connection:
            if self._get(connection, f"pr-merge/{candidate.pull_request}", MergeReceipt):
                raise ConflictError("Demons pull request är redan mergad.")
            self._put(connection, f"pr/{candidate.pull_request}", candidate)

    def candidate(self, request_id: UUID) -> Candidate | None:
        if not self.path.exists():
            return None
        with self._transaction() as connection:
            return self._get(connection, f"pr/{request_id}", Candidate)

    def lookup_merge(self, operation: str) -> MergeReceipt | None:
        with self._transaction() as connection:
            return self._get(connection, operation, MergeReceipt)

    def merge(self, operation: str, expected: Candidate) -> MergeReceipt:
        with self._transaction(write=True) as connection:
            receipt = self._get(connection, operation, MergeReceipt)
            if receipt is not None:
                return receipt
            key = f"pr-merge/{expected.pull_request}"
            if self._get(connection, key, MergeReceipt):
                raise ConflictError("Demons pull request mergades redan via ett annat försök.")
            current = self._get(connection, f"pr/{expected.pull_request}", Candidate)
            if current != expected or not expected.eligible(expected.pull_request):
                raise ConflictError("Kodversionen eller kontrollerna ändrades före merge.")
            # Simulerat Git-objekt-ID. Ingen ändring av ett riktigt repo.
            version = sha1(f"{operation}:{expected.head}".encode(), usedforsecurity=False).hexdigest()
            receipt = MergeReceipt(operation=operation, pull_request=expected.pull_request, head=expected.head,
                                   evidence_hash=expected.fingerprint, version=version, merged_at=datetime.now(UTC))
            self._put(connection, key, receipt)
            self._put(connection, operation, receipt)
            return receipt

    def lookup_deployment(self, operation: str) -> DeploymentReceipt | None:
        with self._transaction() as connection:
            return self._get(connection, operation, DeploymentReceipt)

    def deploy(self, operation: str, merged: MergeReceipt) -> DeploymentReceipt:
        with self._transaction(write=True) as connection:
            receipt = self._get(connection, operation, DeploymentReceipt)
            if receipt is not None:
                return receipt
            if self._get(connection, merged.operation, MergeReceipt) != merged:
                raise ConflictError("Målet saknar ett känt mergekvitto för versionen.")
            target = demo_target(merged.pull_request)
            self._put(connection, target, TargetState(version=merged.version, ready=True))
            observed = self._get(connection, target, TargetState)
            receipt = DeploymentReceipt(operation=operation, target=target, version=observed.version,
                                        deployed_at=datetime.now(UTC))
            self._put(connection, operation, receipt)
            return receipt

    def check_target(self, target: str) -> TargetCheck:
        with self._transaction() as connection:
            observed = self._get(connection, target, TargetState)
        ready = bool(observed and observed.ready)
        return TargetCheck(target=target, version=observed.version if observed else None, passed=ready,
                           summary="Demotjänsten svarar" if ready else "Demotjänsten svarar inte",
                           checked_at=datetime.now(UTC))
