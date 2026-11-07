"""Betrodd kontroll av det avgränsade offertprovet i U6."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from subprocess import TimeoutExpired
from tempfile import TemporaryDirectory
from time import monotonic

from pydantic import ValidationError

from agents.development import (
    CodingError,
    CodingResult,
    TestEvidence,
    _git,
    _git_bytes,
    committed_diff,
)
from services.change_releases import SandboxGrant
from services.development_demo import Candidate, DemoDelivery, Evidence, OutcomeUnknown
from services.errors import ConflictError

QUOTE_FILE = "quote.sql"
QUOTE_BEFORE = b"SELECT :price + :discount;\n"
QUOTE_AFTER = b"SELECT :price - :discount;\n"


@dataclass(frozen=True)
class QuoteSandbox:
    directory: Path
    grant: SandboxGrant
    verify_quote: Callable[[Path], TestEvidence]

    def check_delivery(self, delivery: DemoDelivery) -> None:
        path = self.directory.resolve() / "case.delivery.db"
        if (str(path.parent) != self.grant.location or type(delivery) is not DemoDelivery
                or delivery.path.resolve() != path):
            raise OutcomeUnknown("Försöket kräver sandlådans egen lokala målmiljö.")

    def check_candidate(self, candidate: Candidate) -> None:
        grant = self.grant
        repo = self.directory / "source.git"
        deadline = monotonic() + 15
        ref = f"refs/heads/demo/{grant.run_id}"
        try:
            if (_git(repo, deadline, "rev-parse", "--is-bare-repository") != "true"
                    or Path(_git(repo, deadline, "rev-parse", "--absolute-git-dir")).resolve() != repo
                    or _git(repo, deadline, "remote")):
                raise ConflictError("Git-kopian tillhör inte det lokala offertprovet.")
            head = _git(repo, deadline, "rev-parse", ref)
            if (not candidate.eligible(grant.request_id) or candidate.base != grant.base
                    or candidate.head != head or _git(repo, deadline, "show", "-s", "--format=%P", head) != grant.base):
                raise ConflictError("Ärendets commit eller simulerade Git-mål matchar inte sandlådan.")
            for commit, expected in ((grant.base, QUOTE_BEFORE), (head, QUOTE_AFTER)):
                tree = _git(repo, deadline, "ls-tree", "-r", "-t", "--full-tree", commit)
                if (len(tree.splitlines()) != 1 or not tree.startswith("100644 blob ")
                        or not tree.endswith(f"\t{QUOTE_FILE}")
                        or _git_bytes(repo, deadline, "cat-file", "blob", f"{commit}:{QUOTE_FILE}") != expected):
                    raise ConflictError("Diffen ligger utanför den tillåtna ändringen av quote.sql.")
            diff = committed_diff(repo, deadline, grant.base, head)
            if diff != candidate.diff:
                raise ConflictError("Granskningsdiffen matchar inte den committade ändringen.")
            result_path = self.directory / "runs" / str(grant.run_id) / "result.json"
            result = CodingResult.model_validate_json(result_path.read_bytes())
            if not result.attempts:
                raise ConflictError("Sandlådan saknar ett obligatoriskt testbevis.")
            refs = result.review()
        except (CodingError, OSError, TimeoutError, TimeoutExpired, UnicodeError, ValidationError) as exc:
            raise ConflictError("Betrodd kod kunde inte verifiera sandlådans Git- eller provunderlag.") from exc

        try:
            with TemporaryDirectory(prefix="u6-quote-proof-") as folder:
                (Path(folder) / QUOTE_FILE).write_bytes(QUOTE_AFTER)  # Exakt jämförd mot blobben ovan.
                proof = self.verify_quote(Path(folder))
        except OSError as exc:
            raise ConflictError("Det obligatoriska kodprovet kunde inte köras.") from exc
        expected_check = Evidence(name="kodprov", reference=refs.test_ref, passed=proof.passed, summary=proof.summary)
        if (result.case_id != grant.request_id or result.run_id != grant.run_id or result.base_commit != grant.base
                or result.head_commit != head or result.attempts[-1].diff != diff or result.attempts[-1].tests != proof
                or not proof.passed or candidate.references != refs or candidate.checks != (expected_check,)):
            raise ConflictError("Obligatoriskt testbevis matchar inte sandlådans kod och provresultat.")
