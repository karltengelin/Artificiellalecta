"""En uttryckligt startad kodkörning mot ett förhandsgodkänt demoärende."""

from __future__ import annotations

import difflib
import os
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from agents.ecosystem import REPO_ROOT
from agents.journal import FileJournal, digest, text_ref
from services.change_requests import ChangeQueueRun, ChangeRequests, ReviewReferences
from services.errors import AccessDeniedError, ConflictError

MAX_ATTEMPTS = 2
MAX_SECONDS = 120
DEFAULT_RUN_DIR = REPO_ROOT / "logs" / "development_runs"
EditText = Annotated[str, StringConstraints(min_length=1, max_length=8000)]


class CodingError(RuntimeError):
    """Kodaren eller körmiljön kunde inte leverera inom mandatet."""


class EditProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    plan: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    path: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    before: EditText
    after: EditText


class TestEvidence(BaseModel):
    passed: bool
    summary: str


class CodingTask(BaseModel):
    case_id: UUID
    goal: str
    acceptance: str | None
    base_commit: str
    files: dict[str, str]
    feedback: TestEvidence


class Coder(Protocol):
    def propose(self, task: CodingTask, workspace: Path, timeout: float) -> EditProposal: ...


class CodingAttempt(BaseModel):
    plan: str
    diff: str
    tests: TestEvidence


class CodingResult(BaseModel):
    schema_version: Literal[1] = 1
    run_id: UUID
    case_id: UUID
    base_commit: str | None = None
    head_commit: str | None = None
    branch: str
    baseline: TestEvidence | None = None
    attempts: tuple[CodingAttempt, ...] = ()
    outcome: Literal["tests_passed", "needs_human", "limit_reached", "blocked", "superseded"]

    def review(self) -> ReviewReferences:
        if self.outcome != "tests_passed":
            raise CodingError("Körningen saknar godkänt testbevis.")
        attempt = self.attempts[-1]
        code = {"base_commit": self.base_commit, "diff": attempt.diff}
        if self.head_commit is not None:
            code["head_commit"] = self.head_commit
        code_hash = digest(code)
        test_hash = digest({"code_hash": code_hash, "tests": attempt.tests.model_dump()})
        return ReviewReferences(code_ref=f"{self.run_id}/diff sha256:{code_hash}",
                                test_ref=f"{self.run_id}/tests sha256:{test_hash}")


def _remaining(deadline: float) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("Kodkörningens tidsbudget är förbrukad.")
    return remaining


def _git_bytes(workspace: Path, deadline: float, *args: str) -> bytes:
    # Eget repo utan remotes, användarinställningar, mallar eller ärvda Git-variabler.
    env = {name: os.environ[name] for name in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP")
           if name in os.environ}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_NO_REPLACE_OBJECTS="1")
    try:
        result = subprocess.run(["git", *args], cwd=workspace, env=env, capture_output=True, check=False,
                                timeout=_remaining(deadline))
    except OSError as exc:
        raise CodingError("Git kunde inte startas i kodmiljön.") from exc
    if result.returncode:
        raise CodingError("Kodbaskopian kunde inte skapas i kodmiljön.")
    return result.stdout


def _git(workspace: Path, deadline: float, *args: str) -> str:
    return _git_bytes(workspace, deadline, *args).decode("utf-8").strip()


def committed_diff(workspace: Path, deadline: float, base: str, head: str) -> str:
    return _git_bytes(workspace, deadline, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                      "--full-index", "--color=never", base, head, "--").decode("utf-8")


def _apply_proposal(workspace: Path, files: Mapping[str, str], proposal: EditProposal) -> str:
    original = files.get(proposal.path)
    if original is None:
        raise CodingError("Ändringen ligger utanför tillåtna källfiler.")
    if original.count(proposal.before) != 1 or proposal.before == proposal.after:
        raise CodingError("Ändringen kan inte bindas entydigt till basversionen.")
    changed = original.replace(proposal.before, proposal.after, 1)
    path = workspace / proposal.path
    path.write_text(changed, encoding="utf-8", newline="\n")
    diff = list(difflib.unified_diff(original.splitlines(keepends=True), changed.splitlines(keepends=True),
                                    fromfile=f"a/{proposal.path}", tofile=f"b/{proposal.path}"))
    # difflib behöver en separat markör för ändrade rader utan avslutande radbrytning.
    return "".join(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n" for line in diff)


def run_development_case(
    store: ChangeRequests,
    scope: ChangeQueueRun,
    case_id: UUID,
    *,
    coder: Coder,
    files: Mapping[str, str],
    verify: Callable[[Path], TestEvidence],
    directory: Path = DEFAULT_RUN_DIR,
    snapshot: Path | None = None,
) -> CodingResult:
    """Kör en fiktiv källsnapshot. Startaren äger underlag, filmandat och testfunktion."""
    for name in files:
        path = PurePosixPath(name)
        if path.as_posix() != name or any(
            not part or part.startswith(".") or not part.replace("_", "").replace("-", "").replace(".", "").isalnum()
            for part in path.parts
        ) or path.is_absolute():
            raise ValueError("Källsnapshoten innehåller en ogiltig sökväg.")
    journal = FileJournal(directory, run_id=str(scope.run_id), team="utveckling", agent=scope.actor.id)
    try:
        return _run(store, scope, case_id, coder, dict(files), verify, journal, snapshot)
    finally:
        journal.close()


def _run(store: ChangeRequests, scope: ChangeQueueRun, case_id: UUID, coder: Coder,
         files: dict[str, str], verify: Callable[[Path], TestEvidence], journal: FileJournal,
         snapshot: Path | None) -> CodingResult:
    deadline = monotonic() + MAX_SECONDS
    branch = f"demo/{scope.run_id}"
    journal.append("run_started", case_id=str(case_id), max_attempts=MAX_ATTEMPTS, max_seconds=MAX_SECONDS)
    try:
        case = store.claim(scope, case_id)
    except (AccessDeniedError, ConflictError):
        journal.append("run_ended", outcome="claim_denied")
        raise
    journal.append("development_claimed", case_id=str(case_id))
    attempts = []
    base_commit = head_commit = baseline = None
    outcome = "needs_human"
    try:
        with TemporaryDirectory(prefix="development-") as folder:
            workspace = Path(folder)
            for name, source in files.items():
                path = workspace / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8", newline="\n")
            _git(workspace, deadline, "init", "--template=", "--initial-branch", branch)
            _git(workspace, deadline, "add", "--", *files)
            _git(workspace, deadline, "-c", "user.name=U3 demo", "-c", "user.email=demo@example.invalid",
                 "commit", "--no-gpg-sign", "-m", "Fiktiv basversion")
            base_commit = _git(workspace, deadline, "rev-parse", "HEAD")
            store.check_claim(scope, case_id)
            feedback = baseline = verify(workspace)
            journal.append("development_baseline", base_commit=base_commit, passed=baseline.passed)
            for attempt_number in range(1, MAX_ATTEMPTS + 1):
                if feedback.passed:
                    break
                store.check_claim(scope, case_id)
                task = CodingTask(case_id=case_id, goal=case.draft.need, acceptance=case.draft.acceptance,
                                  base_commit=base_commit, files=files, feedback=feedback)
                journal.append("development_edit_requested", attempt=attempt_number, task_hash=digest(task.model_dump()))
                proposal = coder.propose(task, workspace, _remaining(deadline))
                _remaining(deadline)
                store.check_claim(scope, case_id)
                diff = _apply_proposal(workspace, files, proposal)
                feedback = verify(workspace)
                attempts.append(CodingAttempt(plan=proposal.plan, diff=diff, tests=feedback))
                journal.append("development_tested", attempt=attempt_number, passed=feedback.passed,
                               plan=text_ref(proposal.plan), diff_hash=digest(diff), tests_hash=digest(feedback.model_dump()))
                _remaining(deadline)
                if feedback.passed:
                    _git(workspace, deadline, "add", "--", proposal.path)
                    _git(workspace, deadline, "-c", "user.name=Demo", "-c", "user.email=demo@example.invalid",
                         "commit", "--no-gpg-sign", "-m", "Testad fiktiv ändring")
                    head_commit = _git(workspace, deadline, "rev-parse", "HEAD")
                    if snapshot is not None:
                        _git(workspace, deadline, "clone", "--bare", "--no-local", "--template=", "--",
                             str(workspace), str(snapshot))
                        _git(snapshot, deadline, "remote", "remove", "origin")
                        actual_diff = committed_diff(snapshot, deadline, base_commit, head_commit)
                        attempts[-1] = attempts[-1].model_copy(update={"diff": actual_diff})
                        journal.append("development_snapshot", head_commit=head_commit, diff_hash=digest(actual_diff))
                    outcome = "tests_passed"
                    break
                (workspace / proposal.path).write_text(files[proposal.path], encoding="utf-8", newline="\n")
            else:
                outcome = "limit_reached"
    except (TimeoutError, subprocess.TimeoutExpired):
        outcome = "limit_reached"
    except ConflictError:
        outcome = "superseded"
    except (CodingError, OSError, ValidationError) as exc:
        journal.append("development_blocked", error_type=type(exc).__name__)
        outcome = "blocked"

    result = CodingResult(run_id=scope.run_id, case_id=case_id, branch=branch, base_commit=base_commit,
                          head_commit=head_commit,
                          baseline=baseline, attempts=tuple(attempts), outcome=outcome)
    artifact_dir = journal.path.with_suffix("")
    artifact_dir.mkdir()
    with (artifact_dir / "result.json").open("x", encoding="utf-8") as artifact:
        artifact.write(result.model_dump_json(indent=2))
        artifact.flush()
        os.fsync(artifact.fileno())

    if result.outcome == "tests_passed":
        review = result.review()
        journal.append("development_handoff_requested", **review.model_dump())
        try:
            store.handoff(scope, case_id, review)
        except ConflictError:
            journal.append("run_ended", outcome="superseded")
            return result
    journal.append("run_ended", outcome=result.outcome)
    return result
