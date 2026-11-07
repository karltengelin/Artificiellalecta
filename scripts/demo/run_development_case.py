"""Kör ett fiktivt ändringsärende med lokala testdubblar för kod, GitHub och införande."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from uuid import UUID, uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agents.development import CodingResult, CodingTask, EditProposal, TestEvidence, run_development_case  # noqa: E402
from services.change_releases import ChangeReleases  # noqa: E402
from services.change_requests import DEVELOPER, ChangeQueueRun, ChangeRequestDraft, ChangeRequests  # noqa: E402
from services.contract import Actor  # noqa: E402
from services.db import session_factory_for  # noqa: E402
from services.development_demo import Candidate, DemoDelivery, Evidence, OutcomeUnknown  # noqa: E402
from services.errors import ConflictError  # noqa: E402
from web.config import WebSettings  # noqa: E402
from web.database import demo_engine  # noqa: E402

FILE = "quote.sql"
SOURCE = "SELECT :price + :discount;\n"
DRAFT = ChangeRequestDraft(
    kind="defect", title="U3-demo · fel i fiktiv prisberäkning", affected_system="Fiktiv offert",
    need="Beräkna priset efter avdrag för rabatt i den fiktiva offerten.",
    acceptance="1000 − 200 ska ge 800. Utan rabatt ska priset vara oförändrat.",
)


def verify_quote(workspace: Path) -> TestEvidence:
    """Kör bara en ren SELECT över fiktiva tal i en egen minnesdatabas."""
    source = (workspace / FILE).read_text(encoding="utf-8")
    with closing(sqlite3.connect(":memory:")) as db:
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 16_000)
        db.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action == sqlite3.SQLITE_SELECT else sqlite3.SQLITE_DENY)
        db.set_progress_handler(lambda: 1, 1000)
        mismatches = []
        try:
            for price, discount, expected in ((1000, 200, 800), (1700, 0, 1700)):
                rows = db.execute(source, {"price": price, "discount": discount}).fetchall()
                if rows != [(expected,)]:
                    mismatches.append(f"Pris {price}, rabatt {discount}: väntade {expected}, fick {rows!r}.")
        except sqlite3.Error:
            return TestEvidence(passed=False, summary="Källfilen gav ingen tillåten SELECT-beräkning.")
    return TestEvidence(passed=not mismatches, summary=" ".join(mismatches) or "2 av 2 kontrollfall godkända.")


class ScriptedCoder:
    def propose(self, task: CodingTask, workspace: Path, timeout: float) -> EditProposal:
        # Första ändringen klarar rabatten men inte nollfallet. Rätta efter teståterkopplingen.
        corrected = "rabatt 0" in task.feedback.summary
        return EditProposal(
            plan="Pröva rabattberäkningen och kontrollera priset även utan rabatt.",
            path=FILE, before=":price + :discount",
            after=":price - :discount" if corrected else ":price - 200",
        )


def stage_candidate(delivery: DemoDelivery, result: CodingResult) -> None:
    """Betrodd demokod lämnar den faktiskt testade committen till GitHub-dubbeln."""
    refs = result.review()
    attempt = result.attempts[-1]
    delivery.stage(Candidate(
        pull_request=result.case_id, base=result.base_commit, head=result.head_commit,
        diff=attempt.diff, references=refs,
        checks=(Evidence(name="kodprov", reference=refs.test_ref, passed=attempt.tests.passed,
                         summary=attempt.tests.summary),),
    ))


def request_merge(store: ChangeRequests, delivery: DemoDelivery, operator: Actor, case_id: UUID) -> None:
    item = store.get(operator, case_id)
    if item is None or item.agent_run_id is None:
        raise ConflictError("Ärendet saknar en aktiv utvecklarkörning inom operatörens mandat.")
    releases = ChangeReleases(store, delivery)
    view = releases.read(operator, case_id)
    if view.approval is None:
        raise ConflictError("Granska och godkänn kodversionen på ärendet först.")
    scope = ChangeQueueRun(actor=DEVELOPER, run_id=item.agent_run_id, requested_by=operator.id,
                           allowed_requests={case_id})
    releases.advance("merge", scope, case_id, view.approval.id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-id", default="karl", help="Det lokala operatörskontot som ska se ärendet.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare-release", action="store_true", help="Lämna testad kod till den lokala GitHub-dubbeln.")
    mode.add_argument("--request-merge", type=UUID, metavar="ÄRENDE-ID",
                      help="Låt ärendets utvecklaragent begära merge av den godkända demoversionen.")
    args = parser.parse_args()
    settings = WebSettings(operator_id=args.operator_id)
    engine = demo_engine(settings.demo_path)
    try:
        store = ChangeRequests(session_factory_for(engine))
        operator = Actor.human(settings.operator_id)
        delivery = DemoDelivery(settings.demo_path)
        if args.request_merge:
            try:
                request_merge(store, delivery, operator, args.request_merge)
            except (ConflictError, OutcomeUnknown) as exc:
                print(exc, file=sys.stderr)
                return 1
            print(f"Mergat i demo · /central/utveckling/{args.request_merge}")
            return 0
        case_id = uuid4()
        store.create(operator, case_id, DRAFT)
        scope = ChangeQueueRun(actor=DEVELOPER, run_id=uuid4(), requested_by=settings.operator_id,
                               allowed_requests={case_id})
        (queued,) = store.list_new(scope)
        result = run_development_case(store, scope, queued.id, coder=ScriptedCoder(),
                                      files={FILE: SOURCE}, verify=verify_quote)
        item = store.get(operator, case_id)
        if args.prepare_release and item.status == "waiting_review":
            stage_candidate(delivery, result)
        print(f"Ändringsärende /central/utveckling/{case_id}")
        print(f"Körning {scope.run_id} · {result.outcome} · {item.status}")
        return int(item.status != "waiting_review")
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
