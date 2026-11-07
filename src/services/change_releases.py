"""Granskad merge och verifierat införande av ett ändringsärende i demo."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select

from services.change_requests import (
    PENDING_RELEASE,
    ChangeQueueRun,
    ChangeRequests,
    ReviewReferences,
    change_release_events,
    change_request_events,
)
from services.contract import Actor
from services.development_demo import (
    Candidate,
    DemoDelivery,
    DeploymentReceipt,
    MergeReceipt,
    OutcomeUnknown,
    TargetCheck,
    demo_target,
)
from services.errors import ConflictError

Stage = Literal["merge", "deploy", "verify"]
ReleaseCaller = Actor | ChangeQueueRun
STEPS = {"merge": ("waiting_review", "merged"), "deploy": ("merged", "deployed"),
         "verify": ("deployed", "verified")}


class ReviewBundle(BaseModel):
    submission: int
    candidate: Candidate

    @property
    def fingerprint(self) -> str:
        return sha256(self.model_dump_json().encode("utf-8")).hexdigest()


class ReleaseAttempt(BaseModel):
    approval_id: int
    run_id: UUID | None = None


@dataclass(frozen=True)
class Approval:
    id: int
    actor_id: str
    occurred_at: str
    bundle: ReviewBundle


@dataclass(frozen=True)
class ReleaseView:
    approval: Approval | None
    merge: MergeReceipt | None
    deployment: DeploymentReceipt | None
    check: TargetCheck | None
    pending: str | None
    stopped: bool
    preview: ReviewBundle | None = None
    preview_error: str | None = None

    @property
    def approved(self) -> bool:
        return bool(self.approval and not self.stopped and self.preview == self.approval.bundle)


class ChangeReleases:
    def __init__(self, requests: ChangeRequests, delivery: DemoDelivery):
        self.requests = requests
        self.delivery = delivery

    def read(self, actor: Actor, request_id: UUID, *, preview: bool = False) -> ReleaseView | None:
        owner = self.requests._requester(actor)
        with self.requests._session_factory() as session:
            row = self.requests._find(session, owner, request_id)
            if row is None:
                return None
            view = self._read_state(session, request_id)
            if not preview or row["status"] != "waiting_review":
                return view
            try:
                bundle = self._candidate(session, request_id)
            except (ConflictError, OutcomeUnknown) as exc:
                return replace(view, preview_error=str(exc))
            return replace(view, preview=bundle)

    def approve(self, actor: Actor, request_id: UUID, seen: str) -> bool:
        owner = self.requests._requester(actor)
        with self.requests._session_factory() as session:
            row = self.requests._find(session, owner, request_id)
            if row is None:
                return False
            view = self._read_state(session, request_id)
            if row["status"] != "waiting_review" or view.pending:
                raise ConflictError("Ärendet måste vänta på granskning utan pågående merge.")
            bundle = self._candidate(session, request_id)
            if bundle is None or seen != bundle.fingerprint:
                raise ConflictError("Granskningsunderlaget har ändrats. Öppna ärendet och granska det på nytt.")
            if view.stopped or view.approval is None or view.approval.bundle != bundle:
                self._record(session, request_id, owner, "approved", bundle)
            return True

    def advance(self, stage: Stage, caller: ReleaseCaller, request_id: UUID, approval_id: int) -> bool:
        """Spara avsikten före ett externt anrop. Nästa transaktion stämmer av under skrivlås."""
        previous, current = STEPS[stage]
        with self.requests._session_factory() as session:
            row, actor_id = self._authorize(session, stage, caller, request_id)
            if row is None:
                return False
            view = self._read_state(session, request_id)
            self._check_approval(view, approval_id)
            if self._receipt(view, stage):
                return True
            if row["status"] != previous:
                raise ConflictError("Föregående införandesteg måste vara klart.")
            if stage == "verify":
                return self._verify(session, request_id, actor_id, view)
            if view.pending is None:
                if stage == "merge":
                    self._check_candidate(session, request_id, view.approval)
                attempt = ReleaseAttempt(approval_id=approval_id,
                                         run_id=caller.run_id if isinstance(caller, ChangeQueueRun) else None)
                self._record(session, request_id, actor_id, f"{stage}_pending", attempt)

        with self.requests._session_factory() as session:
            # BEGIN IMMEDIATE serialiserar försök mellan processer. Kvittona i
            # testdubblarna ligger i en egen databas och kan överleva en rollback här.
            row, actor_id = self._authorize(session, stage, caller, request_id)
            if row is None:
                return False
            view = self._read_state(session, request_id)
            self._check_approval(view, approval_id)
            if self._receipt(view, stage):
                return True
            if row["status"] != previous or view.pending != f"{stage}_pending":
                raise ConflictError("Införandesteget har ändrats. Öppna ärendet igen.")
            operation = f"{stage}/{request_id}/{approval_id}"
            if stage == "merge":
                receipt = self._merge(session, operation, request_id, view.approval)
            else:
                receipt = self._deploy(operation, view.merge)
            if receipt is None:
                self._record(session, request_id, actor_id, "stopped", ReleaseAttempt(approval_id=approval_id))
            else:
                self._record(session, request_id, actor_id, stage, receipt)
                self.requests._set_status(session, request_id, actor_id, previous, current)
                return True
        raise ConflictError("Ingen merge hittades vid avstämning. Kodversionen eller testbevisen kräver ett nytt beslut.")

    def _merge(self, session, operation: str, request_id: UUID, approval: Approval) -> MergeReceipt | None:
        candidate = approval.bundle.candidate
        receipt = self.delivery.lookup_merge(operation)
        if receipt is None:
            try:
                self._check_candidate(session, request_id, approval)
            except ConflictError:
                return None  # Bekräftat att försöket saknar effekt och behöver ny granskning.
            receipt = self.delivery.merge(operation, candidate)
        if (receipt.operation != operation or receipt.pull_request != request_id or receipt.head != candidate.head
                or receipt.evidence_hash != candidate.fingerprint):
            raise OutcomeUnknown("Mergebeskedet stämmer inte med det godkända försöket.")
        return receipt

    def _deploy(self, operation: str, merged: MergeReceipt) -> DeploymentReceipt:
        receipt = self.delivery.lookup_deployment(operation)
        if receipt is None:
            receipt = self.delivery.deploy(operation, merged)
        if (receipt.operation != operation or receipt.target != demo_target(merged.pull_request)
                or receipt.version != merged.version):
            raise OutcomeUnknown("Införandekvittot stämmer inte med den mergade versionen.")
        return receipt

    def _authorize(self, session, stage: Stage, caller: ReleaseCaller, request_id: UUID):
        if isinstance(caller, ChangeQueueRun):
            row = self.requests._agent_row(session, caller, request_id)
            if stage != "merge" or row["agent_run_id"] != str(caller.run_id):
                self.requests._deny(caller)
            return row, caller.actor.id
        owner = self.requests._requester(caller)
        return self.requests._find(session, owner, request_id), owner

    @staticmethod
    def _receipt(view: ReleaseView, stage: Stage):
        if stage == "merge":
            return view.merge
        if stage == "deploy":
            return view.deployment
        return view.check if view.check and view.check.passed else None

    @staticmethod
    def _check_approval(view: ReleaseView, approval_id: int) -> None:
        if view.approval is None or view.approval.id != approval_id or view.stopped:
            raise ConflictError("Steget kräver ett aktuellt mänskligt beslut om kodversion och testbevis.")

    def _candidate(self, session, request_id: UUID) -> ReviewBundle | None:
        candidate = self.delivery.candidate(request_id)
        if candidate is None:
            return None
        events = change_request_events
        submission = session.execute(
            select(events.c.id, events.c.previous, events.c.current).where(
                events.c.request_id == str(request_id), events.c.action == "review",
            ).order_by(events.c.id.desc()).limit(1)
        ).one_or_none()
        if submission is None or candidate.references != ReviewReferences(
            code_ref=submission.previous, test_ref=submission.current,
        ):
            raise ConflictError("Demons pull request behöver matcha det inlämnade granskningsunderlaget.")
        if not candidate.eligible(request_id):
            raise ConflictError("Repo, målbranch eller obligatoriska kodprov uppfyller inte demots mergevillkor.")
        return ReviewBundle(submission=submission.id, candidate=candidate)

    def _check_candidate(self, session, request_id: UUID, approval: Approval) -> None:
        if self._candidate(session, request_id) != approval.bundle:
            raise ConflictError("Kodversionen eller testbevisen har ändrats och kräver ett nytt beslut.")

    def _verify(self, session, request_id: UUID, actor_id: str, view: ReleaseView) -> bool:
        target = view.deployment.target
        expected = view.deployment.version
        observed = self.delivery.check_target(target)
        matches = observed.target == target and observed.version == expected
        check = observed if matches else observed.model_copy(update={
            "passed": False, "summary": "Observerad miljö eller version stämmer inte med införandekvittot.",
        })
        self._record(session, request_id, actor_id, "verify", check)
        if check.passed:
            self.requests._set_status(session, request_id, actor_id, "deployed", "verified")
        return True

    @staticmethod
    def _record(session, request_id: UUID, actor_id: str, action: str, payload: BaseModel) -> None:
        session.execute(change_release_events.insert().values(
            request_id=str(request_id), actor_id=actor_id, occurred_at=datetime.now(UTC).isoformat(),
            action=action, payload=payload.model_dump(mode="json"),
        ))

    @staticmethod
    def _read_state(session, request_id: UUID) -> ReleaseView:
        events = change_release_events
        history = session.execute(select(events).where(events.c.request_id == str(request_id))
                                  .order_by(events.c.id)).mappings().all()
        latest = {event["action"]: event for event in history}
        approved = latest.get("approved")
        stopped = latest.get("stopped")
        action = history[-1]["action"] if history else None
        return ReleaseView(
            approval=Approval(approved["id"], approved["actor_id"], approved["occurred_at"],
                              ReviewBundle.model_validate(approved["payload"])) if approved else None,
            merge=MergeReceipt.model_validate(latest["merge"]["payload"]) if "merge" in latest else None,
            deployment=DeploymentReceipt.model_validate(latest["deploy"]["payload"]) if "deploy" in latest else None,
            check=TargetCheck.model_validate(latest["verify"]["payload"]) if "verify" in latest else None,
            pending=action if action in PENDING_RELEASE else None,
            stopped=bool(stopped and approved and stopped["id"] > approved["id"]),
        )
