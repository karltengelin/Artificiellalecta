"""Kör ett fiktivt U3-ärende med lokal kodardubbel och spara underlaget för boarden."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agents.development import CodingTask, EditProposal, TestEvidence, run_development_case  # noqa: E402
from services.change_requests import DEVELOPER, ChangeQueueRun, ChangeRequestDraft, ChangeRequests  # noqa: E402
from services.contract import Actor  # noqa: E402
from services.db import session_factory_for  # noqa: E402
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-id", default="karl", help="Det lokala operatörskontot som ska se ärendet.")
    args = parser.parse_args()
    settings = WebSettings(operator_id=args.operator_id)
    engine = demo_engine(settings.demo_path)
    try:
        store = ChangeRequests(session_factory_for(engine))
        case_id = uuid4()
        store.create(Actor.human(settings.operator_id), case_id, DRAFT)
        scope = ChangeQueueRun(actor=DEVELOPER, run_id=uuid4(), requested_by=settings.operator_id,
                               allowed_requests={case_id})
        (queued,) = store.list_new(scope)
        result = run_development_case(store, scope, queued.id, coder=ScriptedCoder(),
                                      files={FILE: SOURCE}, verify=verify_quote)
        item = store.get(Actor.human(settings.operator_id), case_id)
        print(f"Ändringsärende /central/utveckling/{case_id}")
        print(f"Körning {scope.run_id} · {result.outcome} · {item.status}")
        return int(item.status != "waiting_review")
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
