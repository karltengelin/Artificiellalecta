"""Starta eller följ ett uttryckligt U6-prov med enbart lokala testdubblar."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO_ROOT / "src"), str(REPO_ROOT)]

from pydantic import ValidationError

from agents.development import run_development_case
from agents.development_sandbox import QUOTE_BEFORE, QUOTE_FILE, QuoteSandbox
from scripts.demo.run_development_case import (
    DRAFT,
    ScriptedCoder,
    stage_candidate,
    verify_quote,
)
from services.change_releases import QUOTE_POLICY, ChangeReleases, SandboxGrant
from services.change_requests import DEVELOPER, ChangeQueueRun, ChangeRequests
from services.contract import Actor
from services.db import session_factory_for
from services.development_demo import DemoDelivery, OutcomeUnknown, demo_target
from services.errors import AccessDeniedError, ConflictError
from web.database import demo_engine


def prepare(directory: Path, store: ChangeRequests, delivery: DemoDelivery, operator: Actor) -> tuple[SandboxGrant, ChangeQueueRun]:
    case_id = uuid4()
    scope = ChangeQueueRun(actor=DEVELOPER, run_id=uuid4(), requested_by=operator.id, allowed_requests={case_id})
    store.create(operator, case_id, DRAFT)
    result = run_development_case(
        store, scope, case_id, coder=ScriptedCoder(), files={QUOTE_FILE: QUOTE_BEFORE.decode()},
        verify=verify_quote, directory=directory / "runs", snapshot=directory / "source.git",
    )
    if result.outcome != "tests_passed" or store.get(operator, case_id).status != "waiting_review":
        raise ConflictError(f"Ärende {case_id} saknar testad kod och behöver mänsklig granskning.")
    grant = SandboxGrant(policy=QUOTE_POLICY, instance=uuid4(), location=str(directory), operator=operator.id,
                         request_id=case_id, run_id=scope.run_id, base=result.base_commit, target=demo_target(case_id))
    stage_candidate(delivery, result)
    with (directory / "sandbox.json").open("x", encoding="utf-8") as manifest:
        manifest.write(grant.model_dump_json(indent=2))
    return grant, scope


def report(releases: ChangeReleases, operator: Actor, grant: SandboxGrant) -> None:
    item = releases.requests.get(operator, grant.request_id)
    view = releases.read(operator, item.id, preview=True)
    bundle = view.preview or (view.approval.bundle if view.approval else None)
    print(json.dumps({
        "case": str(item.id), "status": item.status, "policy_error": view.policy_error, "pending": view.pending,
        "decision": {"id": view.approval.id, "actor": view.approval.actor_id,
                     "policy": view.approval.grant.policy if view.approval.grant else None} if view.approval else None,
        "review": view.preview.fingerprint if view.preview else None,
        "candidate": bundle.candidate.model_dump(mode="json") if bundle else None,
        "preview_error": view.preview_error,
        "merge": view.merge.model_dump(mode="json") if view.merge else None,
        "deployment": view.deployment.model_dump(mode="json") if view.deployment else None,
        "check": view.check.model_dump(mode="json") if view.check else None,
    }, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True, help="Egen lokal katalog för provet.")
    actions = parser.add_subparsers(dest="action", required=True)
    start = actions.add_parser("start")
    start.add_argument("--policy", choices=[QUOTE_POLICY], required=True)
    start.add_argument("--operator-id", required=True)
    review = actions.add_parser("review")
    review.add_argument("--seen", required=True, help="Fingeravtrycket från status efter mänsklig granskning.")
    for action in ("status", "merge", "deploy", "verify"):
        actions.add_parser(action)
    args = parser.parse_args(argv)

    directory = args.directory.resolve()
    demo_path = directory / "case.db"
    engine = None
    try:
        if args.action == "start":
            directory.mkdir()
            operator = Actor.human(args.operator_id)
        else:
            grant = SandboxGrant.model_validate_json((directory / "sandbox.json").read_bytes())
            if str(directory) != grant.location or not demo_path.is_file() or demo_path.resolve() != demo_path:
                raise ConflictError("Provets ursprungliga lokala ärendedatabas krävs.")
            operator = Actor.human(grant.operator)
        engine = demo_engine(demo_path)
        store = ChangeRequests(session_factory_for(engine))
        delivery = DemoDelivery(demo_path)
        if args.action == "start":
            grant, scope = prepare(directory, store, delivery, operator)
        releases = ChangeReleases(store, delivery, sandbox=QuoteSandbox(directory, grant, verify_quote))

        if args.action == "start":
            approval = releases.approve_sandbox(scope, grant.request_id)
            if approval is not None:
                releases.advance("merge", scope, grant.request_id, approval)
        elif args.action == "review":
            releases.approve(operator, grant.request_id, args.seen)
        elif args.action != "status":
            view = releases.read(operator, grant.request_id)
            if view.approval is None:
                raise ConflictError("Ärendet väntar på ett granskningsbeslut.")
            releases.advance(args.action, operator, grant.request_id, view.approval.id)
        report(releases, operator, grant)
        return 0
    except (AccessDeniedError, ConflictError, OutcomeUnknown, OSError, ValidationError) as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
