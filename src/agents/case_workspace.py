"""Ärendebunden dialog, varaktiga uppdrag och kontrollerad självständig handläggning.

Webb och arbetare använder samma adapter. Modellen får aldrig sessionsidentitet,
policyval, köbehörighet eller rätt att förklara en affärsändring genomförd.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from agents.case_policy import DEFAULT_POLICY, CasePolicy
from agents.ecosystem import Ecosystem, Limits
from agents.errors import HarnessError
from agents.loop import run_agent
from agents.profile import compile_profile
from agents.run import RunRequest, RunStatus
from agents.scope import case_and_scope
from agents.skills import SkillRegistry
from models import ApprovalRequestRecord, Case, CaseMessage, CaseWork, CaseWorkDay
from services import Actor, OperationContext, OperationKind, default_registry
from services.case_review import case_digest
from services.errors import ApprovalError, BlockedError, ConflictError
from services.operations.cases import _view

ACTIVE = {"queued", "running", "waiting_approval", "waiting_info", "reconciliation_required"}
STATUS_LABELS = {
    "queued": "Köat", "running": "Agenten arbetar", "waiting_approval": "Väntar på godkännande",
    "waiting_info": "Väntar på komplettering", "needs_human": "Behöver handläggare", "completed": "Klart",
    "cancelled": "Återtaget", "reconciliation_required": "Kräver avstämning",
}
log = logging.getLogger(__name__)


def _id():
    return uuid.uuid4().hex


def _message(session, work, role, author, body):
    session.add(CaseMessage(id=_id(), case_number=work.case_number, work_id=work.id,
                            role=role, author=author, body=body[:16000], created_at=datetime.now(UTC)))


class _GuardedService:
    """Återtaget uppdrag eller ändrat underlag stoppar nästa verktyg, även mitt i körning."""

    def __init__(self, service, workspace, work_id):
        self._service, self._workspace, self._work_id = service, workspace, work_id

    def __getattr__(self, name):
        return getattr(self._service, name)

    def execute(self, name, ctx, data):
        self._workspace.check_running(self._work_id)
        return self._service.execute(name, ctx, data)


@dataclass
class CaseWorkspace:
    session_factory: object
    trusted: object
    agent: object
    policy_path: Path = DEFAULT_POLICY
    journal_dir: Path | None = None

    @classmethod
    def build(cls, trusted, agent, **kwargs):
        if trusted._session_factory is None:
            raise HarnessError("Ärendedialog kräver databas")
        return cls(trusted._session_factory, trusted, agent, **kwargs)

    def view(self, case_number: str, actor: Actor) -> dict:
        if actor.type != "human":
            raise HarnessError("Ärendedialog kräver verifierad handläggare")
        self.trusted.execute("get_case", OperationContext(actor=actor), {"case_number": case_number})
        policy, version = CasePolicy.load(self.policy_path)
        with self.session_factory() as session:
            case = session.scalar(select(Case).where(Case.case_number == case_number))
            works = list(reversed(session.scalars(select(CaseWork).where(CaseWork.case_number == case_number)
                                   .order_by(CaseWork.created_at.desc(), CaseWork.id.desc()).limit(30)).all()))
            # Rå dialog efter avslut gallras separat; visa högst 100 meddelanden här.
            messages = session.scalars(select(CaseMessage).where(CaseMessage.case_number == case_number)
                                      .order_by(CaseMessage.created_at.desc(), CaseMessage.id.desc()).limit(100)).all()
            return {"works": [self._work_view(w) for w in works],
                    "messages": [{"role": m.role, "author": m.author, "body": m.body,
                                  "work_id": m.work_id} for m in reversed(messages)],
                    "policy": policy.snapshot(case.case_type, version), "status_labels": STATUS_LABELS,
                    "case_digest": case_digest(_view(session, case))}

    def amend(self, case_number, details, *, actor, expected_digest, reason):
        if actor.type != "human":
            raise HarnessError("Kompletteringen kräver verifierad handläggare")
        return self.trusted.execute("amend_salary_case", OperationContext(actor=actor, reason=reason,
                                    case_id=case_number),
                                    {"case_number": case_number, "details": details,
                                     "expected_digest": expected_digest})

    @staticmethod
    def _work_view(work):
        return {name: getattr(work, name) for name in (
            "id", "case_number", "mode", "status", "revision", "cancel_requested", "run_id", "result",
            "submitted_by", "policy", "allow_proposals", "instruction", "case_digest")}

    def submit(self, case_number, instruction, *, actor, key, mode="assist", allow_proposals=False):
        if actor.type != "human":
            raise HarnessError("Beställningen kräver verifierad handläggare")
        return self._submit(case_number, instruction, actor=actor, key=key, mode=mode,
                            allow_proposals=allow_proposals)

    def _submit(self, case_number, instruction, *, actor, key, mode="assist", allow_proposals=False):
        if mode not in {"assist", "handle"}:
            raise HarnessError("Ogiltig beställare eller arbetsform")
        instruction = instruction.strip()
        if not 1 <= len(instruction) <= 4000 or not 1 <= len(key) <= 100:
            raise HarnessError("Uppdraget ska vara 1–4 000 tecken och ha ett beställnings-id")
        policy, version = CasePolicy.load(self.policy_path)
        # Identitet binds till idempotensnyckeln, aldrig till modellens text.
        submission = f"{actor.type}:{actor.id}:{key}"
        try:
            with self.session_factory() as session:
                case = session.scalar(select(Case).where(Case.case_number == case_number).with_for_update())
                if case is None or case.status == "closed":
                    raise HarnessError("Ärendet saknas eller är stängt")
                existing = session.scalar(select(CaseWork).where(CaseWork.submission_key == submission))
                if existing:
                    if (existing.case_number, existing.instruction, existing.mode, existing.allow_proposals) != (
                            case_number, instruction, mode, allow_proposals or mode == "handle"):
                        raise ConflictError("Beställnings-id används redan för ett annat uppdrag")
                    return existing.id
                active = session.scalar(select(CaseWork).where(CaseWork.case_number == case_number,
                                                               CaseWork.status.in_(ACTIVE)))
                if active:
                    raise ConflictError("Avgör, komplettera eller ta tillbaka pågående uppdrag först")
                if session.scalar(select(ApprovalRequestRecord.id).where(
                    ApprovalRequestRecord.case_id == case_number, ApprovalRequestRecord.status == "pending"
                ).limit(1)):
                    raise ConflictError("Avgör tidigare förslag i ärendet först")
                work = CaseWork(
                    id=_id(), case_number=case_number, submission_key=submission, mode=mode,
                    instruction=instruction, submitted_by=actor.id, status="queued",
                    allow_proposals=allow_proposals or mode == "handle", case_digest=case_digest(_view(session, case)),
                    policy=policy.snapshot(case.case_type, version),
                    result={"limits_snapshot": Ecosystem.load().agent_limits("case_handler").model_dump()},
                    run_id=f"run-{_id()[:12]}", created_at=datetime.now(UTC),
                )
                session.add(work)
                session.flush()
                _message(session, work, "human" if actor.type == "human" else "system", actor.id, instruction)
                return work.id
        except IntegrityError as exc:
            raise ConflictError("En samtidig beställning registrerades; läs ärendet innan nytt försök") from exc

    def check_running(self, work_id):
        with self.session_factory() as session:
            work = session.get(CaseWork, work_id)
            case = session.scalar(select(Case).where(Case.case_number == work.case_number))
            if (work.status != "running" or work.cancel_requested or case.status == "closed"
                    or work.case_digest != case_digest(_view(session, case))):
                raise BlockedError("Uppdraget är återtaget eller ärendeunderlaget har ändrats")

    def _claim(self, work_id, now):
        # Budgetraden låses före ärendet av alla arbetare. Unik nyckel skyddar första insättningen.
        policy, version = CasePolicy.load(self.policy_path)
        with self.session_factory() as session:
            work = session.get(CaseWork, work_id)
            if work is None or work.status != "queued":
                return None
            local_day = now.astimezone(ZoneInfo(work.policy["schedule"]["timezone"])).date()
            budget_key = f"{local_day.isoformat()}:{work.policy['case_type']}"
            day = session.scalar(select(CaseWorkDay).where(CaseWorkDay.key == budget_key).with_for_update())
            if day is None:
                if session.bind.dialect.name == "postgresql":
                    from sqlalchemy.dialects.postgresql import insert
                else:
                    from sqlalchemy.dialects.sqlite import insert

                session.execute(insert(CaseWorkDay).values(key=budget_key, attempts=0, reserved_usd=0)
                                .on_conflict_do_nothing(index_elements=["key"]))
                day = session.scalar(select(CaseWorkDay).where(CaseWorkDay.key == budget_key).with_for_update())
            case = session.scalar(select(Case).where(Case.case_number == work.case_number).with_for_update())
            # CAS förhindrar två arbetare från att köra samma uppdrag.
            claimed = session.execute(update(CaseWork).where(CaseWork.id == work_id, CaseWork.status == "queued",
                                      CaseWork.cancel_requested.is_(False)).values(status="running"))
            if claimed.rowcount != 1:
                return None
            session.refresh(work)
            current = policy.snapshot(case.case_type, version)
            if current != work.policy or case.status == "closed" or case_digest(_view(session, case)) != work.case_digest:
                work.status = "needs_human"
                _message(session, work, "system", "harness", "Policy eller ärendeunderlag har ändrats. Beställ på nytt.")
                return None
            eco = Ecosystem.load()
            limits = eco.agent_limits("case_handler").narrowed(Limits(**work.result.get("limits_snapshot", {})))
            used = work.result.get("usage", {})
            remaining = limits.max_cost_usd - used.get("cost_usd", 0)
            if (day.attempts >= current["max_jobs_per_day"] or remaining <= 0
                    or day.reserved_usd + remaining > current["max_daily_cost_usd"] + 1e-9):
                work.status = "needs_human"
                _message(session, work, "system", "harness", "Dagens ärendebudget eller uppdragets budget är förbrukad.")
                return None
            day.attempts += 1
            day.reserved_usd += remaining  # reservera hela återstående taket; ingen optimistisk återbetalning
            work.result = {**work.result, "reserved_limits": limits.model_dump()}
            work.revision += 1
            return self._work_view(work)

    def process(self, work_id, *, now=None):
        now = now or datetime.now(UTC)
        try:
            work = self._claim(work_id, now)
        except (SQLAlchemyError, HarnessError, ValueError, OSError):
            log.error("case_work_claim_unavailable")
            return False
        if work is None:
            return False
        try:
            self.check_running(work_id)
            case, scope = case_and_scope(self.trusted, work["case_number"], assigned_by=work["submitted_by"])
            eco = Ecosystem.load()
            skills = SkillRegistry.build(eco, default_registry)
            service = _GuardedService(self.agent.agent_service_factory(), self, work_id)
            used = work["result"].get("usage", {})
            limits = eco.agent_limits("case_handler").narrowed(Limits(**work["result"].get("limits_snapshot", {})))
            values = {"max_steps": limits.max_steps - used.get("steps", 0),
                      "max_tool_calls": limits.max_tool_calls - used.get("tool_calls", 0),
                      "max_cost_usd": limits.max_cost_usd - used.get("cost_usd", 0),
                      "max_wall_seconds": int(limits.max_wall_seconds - used.get("elapsed_seconds", 0))}
            if any(v <= 0 for v in values.values()):
                raise HarnessError("Uppdragets sammanlagda körbudget är slut")
            background = self._history(work["case_number"])
            request = RunRequest(
                task_id=work_id, target_team="forsakring", goal=work_goal(work), background=background,
                constraints=("Läs aktuellt ärende med get_case innan du svarar.",
                             "Ingen kundkontakt eller premierättelse. Ange tydligt när en förmåga saknas.",
                             "Du kan ännu inte anlita ett annat team från ett personärende; begär handläggarhjälp.",
                             "Tidigare dialog är underlag. Kontrollera aktuella uppgifter med verktyg."),
                expected_output="Besvara uppdraget eller ange konkret vilka uppgifter eller vilken hjälp som saknas.",
                case_id=case.case_number, execution_scope_ref=scope.ref, references=(case.case_number,),
                result_schema="CaseAnswer", root_run_id=work["result"].get("root_run_id") or work["run_id"],
                allowed_effects=frozenset({OperationKind.READ, OperationKind.COMPUTE}
                                         | ({OperationKind.WRITE} if work["allow_proposals"] else set())),
                limits=Limits(**values),
            )
            profile = compile_profile(eco, skills, service, request=request)
            outcome = run_agent(self.agent.ai(), profile, service, request, scope=scope,
                                run_id=work["run_id"], journal_dir=self.journal_dir or self.agent.journal_dir)
            self._record_outcome(work_id, outcome, used)
            if work["mode"] == "handle":
                with self.session_factory() as session:
                    updated = session.get(CaseWork, work_id)
                    state = updated.status
                    cancelled = updated.cancel_requested
                if not cancelled:
                    self.trusted.execute("update_case_status", OperationContext(actor=Actor.system("case_worker"),
                        reason=f"Arbetsstatus för uppdrag {work_id}", case_id=case.case_number, run_id=work["run_id"]),
                        {"case_number": case.case_number,
                         "status": state if state in {"waiting_approval", "waiting_info"} else "in_progress",
                         "last_run_id": work["run_id"]})
            self.settle(work_id)
        except Exception:  # noqa: BLE001 – okänt utfall får aldrig köras om automatiskt
            # Modell-/databasfel kan inträffa efter förslag. Aldrig tyst omkörning eller rått fel i dialogen.
            try:
                with self.session_factory() as session:
                    row = session.get(CaseWork, work_id)
                    if row.status == "running":
                        row.status = "reconciliation_required"
                        _unknown_usage(row)
                        _message(session, row, "system", "harness",
                                 "Arbetet avbröts. Kontrollera ärendets förslag och historik innan fortsatt arbete.")
            except SQLAlchemyError:
                log.error("case_work_result_unavailable")
            return False
        return True

    def _history(self, case_number):
        cutoff = datetime.now(UTC) - timedelta(days=30)
        with self.session_factory() as session:
            messages = session.scalars(select(CaseMessage).where(CaseMessage.case_number == case_number,
                                      CaseMessage.created_at >= cutoff).order_by(CaseMessage.created_at.desc(),
                                      CaseMessage.id.desc()).limit(30)).all()
            text = "\n".join(f"{m.role}: {m.body}" for m in reversed(messages))
            return text[-20000:]

    def _record_outcome(self, work_id, outcome, used):
        result = outcome.result
        with self.session_factory() as session:
            row = session.scalar(select(CaseWork).where(CaseWork.id == work_id).with_for_update())
            usage = {"steps": outcome.steps + used.get("steps", 0),
                     "tool_calls": outcome.tool_calls + used.get("tool_calls", 0),
                     "cost_usd": result.cost_usd + used.get("cost_usd", 0),
                     "elapsed_seconds": outcome.elapsed_seconds + used.get("elapsed_seconds", 0)}
            row.result = {"run": result.model_dump(mode="json"), "usage": usage,
                          "limits_snapshot": row.result.get("limits_snapshot", {}),
                          "root_run_id": row.result.get("root_run_id") or row.run_id}
            row.revision += 1
            if row.status == "reconciliation_required":
                pass  # sent svar får inte undanröja en uttrycklig avstämningsspärr
            elif row.cancel_requested:
                row.status = "cancelled"
            elif result.status == RunStatus.WAITING_APPROVAL:
                row.status = "waiting_approval"
            elif result.status == RunStatus.COMPLETED and row.mode == "assist":
                state = (result.output or {}).get("result", {}).get("status")
                row.status = {"answered": "completed", "needs_information": "waiting_info"}.get(state, "needs_human")
            else:
                row.status = "reconciliation_required" if result.status == RunStatus.RECONCILIATION_REQUIRED else "needs_human"
                if result.status == RunStatus.COMPLETED:
                    state = (result.output or {}).get("result", {}).get("status")
                    if state == "needs_information":
                        row.status = "waiting_info"
            answer = (result.output or {}).get("result", {})
            text = result.summary
            if answer.get("questions"):
                text += "\n\nBehöver kompletteras:\n" + "\n".join(answer["questions"])
            if answer.get("limitations"):
                text += "\n\nBegränsningar:\n" + "\n".join(answer["limitations"])
            _message(session, row, "agent", "case_handler", text)

    def settle(self, work_id):
        """Fortsätt efter beslut med kvitton, inte genom att spela om modellens åtgärder."""
        with self.session_factory() as session:
            row = session.get(CaseWork, work_id)
            if row is None or row.status != "waiting_approval" or row.cancel_requested:
                return
            work = self._work_view(row)
        approvals = work["result"].get("run", {}).get("pending_approvals", [])
        if not approvals:
            return
        if (work["mode"] == "handle" and not work["policy"]["review_required"]
                and not work["result"].get("automatic_stopped")):
            for ident in approvals:
                proposal = self.trusted.approvals.get(ident)
                if proposal and proposal.status == "pending":
                    try:
                        self.trusted.complete_case_automatically(work_id, ident, policy_path=self.policy_path)
                    except (ApprovalError, ValueError):
                        with self.session_factory() as session:
                            row = session.get(CaseWork, work_id)
                            row.result = {**row.result, "automatic_stopped": True}
                            _message(session, row, "system", "harness",
                                     "Automatisk slutbehandling stoppades. Förslaget kräver mänsklig granskning.")
                        return
        outcomes = [self.trusted.approvals.get(ident) for ident in approvals]
        if any(p is None or p.status == "pending" for p in outcomes):
            return
        if any(p.status == "rejected" for p in outcomes):
            self._set_human(work_id, "Förslaget avslogs. Handläggaren behöver avgöra fortsatt arbete.")
            return
        try:
            self.trusted.finish_case_work(work_id, policy_path=self.policy_path)
        except ApprovalError:
            self._set_human(work_id, "Avslutet behöver kontrolleras: underlag eller policy har ändrats.")

    def _digest(self, work_id):
        with self.session_factory() as session:
            return session.get(CaseWork, work_id).case_digest

    def work_for_approval(self, approval_id):
        proposal = self.trusted.approvals.get(approval_id)
        if not proposal or not proposal.run_id:
            return None
        with self.session_factory() as session:
            return session.scalar(select(CaseWork.id).where(CaseWork.run_id == proposal.run_id,
                                                           CaseWork.case_number == proposal.case_id))

    def _set_human(self, work_id, text):
        with self.session_factory() as session:
            row = session.get(CaseWork, work_id)
            row.status = "needs_human"
            row.revision += 1
            _message(session, row, "system", "harness", text)

    def action(self, case_number, work_id, action, *, actor, revision, message=""):
        if actor.type != "human":
            raise HarnessError("Åtgärden kräver verifierad handläggare")
        pending = [p for p in self.trusted.approvals.list("pending") if p.case_id == case_number]
        with self.session_factory() as session:
            case = session.scalar(select(Case).where(Case.case_number == case_number).with_for_update())
            row = session.scalar(select(CaseWork).where(CaseWork.id == work_id,
                                 CaseWork.case_number == case_number).with_for_update())
            if row is None or row.revision != revision:
                raise ConflictError("Uppdraget har ändrats; läs ärendet igen")
            if action == "takeover":
                row.cancel_requested = True
                if row.status != "running":
                    row.status = "cancelled"
                _message(session, row, "system", actor.id,
                         "Handläggaren har tagit över. Pågående modellanrop kan avslutas; inga nya verktyg tillåts.")
            elif action == "continue":
                if row.status not in {"waiting_info", "needs_human"} or row.cancel_requested:
                    raise ConflictError("Uppdraget kan inte fortsättas i nuvarande läge")
                if not 1 <= len(message.strip()) <= 4000:
                    raise HarnessError("Skriv kompletteringen, högst 4 000 tecken")
                if case.status == "closed" or pending:
                    raise ConflictError("Avgör väntande förslag eller kontrollera det stängda ärendet först")
                if session.scalar(select(CaseWork.id).where(CaseWork.case_number == case_number,
                    CaseWork.id != row.id, CaseWork.status.in_(ACTIVE)).limit(1)):
                    raise ConflictError("Ett annat uppdrag pågår i ärendet")
                row.result = {**row.result, "last_clarification": message.strip()}
                row.case_digest = case_digest(_view(session, case))
                row.status = "queued"
                row.run_id = f"run-{_id()[:12]}"
                _message(session, row, "human", actor.id, message.strip())
            elif action == "reconcile":
                if row.status != "reconciliation_required" or not message.strip():
                    raise ConflictError("Avstämning kräver ett avbrutet uppdrag och motivering")
                own_pending = [p.id for p in pending if p.run_id == row.run_id]
                row.cancel_requested = False
                row.status = "waiting_approval" if own_pending else "needs_human"
                if own_pending:
                    row.result = {**row.result, "automatic_stopped": True,
                                  "run": {**row.result.get("run", {}), "pending_approvals": own_pending}}
                _message(session, row, "system", actor.id, "Avstämt: " + message.strip())
            else:
                raise HarnessError("Okänd åtgärd")
            row.revision += 1

    def tick(self, *, now=None, max_jobs=10):
        now = now or datetime.now(UTC)
        self.enqueue_daily(now=now)
        with self.session_factory() as session:
            waiting = list(session.scalars(select(CaseWork.id).where(CaseWork.status == "waiting_approval")))
            queued = list(session.scalars(select(CaseWork.id).where(CaseWork.status == "queued")
                                         .order_by(CaseWork.created_at).limit(max_jobs)))
        for ident in waiting:
            self.settle(ident)
        for ident in queued:
            self.process(ident, now=now)
        return len(queued)

    def enqueue_daily(self, *, now):
        if now.tzinfo is None:
            raise ValueError("Schemat kräver tidszon")
        now = now.astimezone(UTC)
        policy, _version = CasePolicy.load(self.policy_path)
        added = 0
        for case_type, rule in policy.case_types.items():
            schedule = rule.schedule
            local = now.astimezone(ZoneInfo(schedule.timezone))
            if not schedule.enabled or (local.hour, local.minute) < (schedule.hour, schedule.minute):
                continue
            with self.session_factory() as session:
                day = session.get(CaseWorkDay, f"{local.date().isoformat()}:{case_type}")
                queued = session.scalar(select(func.count()).select_from(CaseWork).where(CaseWork.status == "queued"))
                cost_limit = Ecosystem.load().agent_limits("case_handler").max_cost_usd
                remaining = rule.max_daily_cost_usd - (day.reserved_usd if day else 0)
                slots = min(rule.max_jobs_per_day - (day.attempts if day else 0),
                            int((remaining + 1e-9) / cost_limit)) - queued
                if slots <= 0:
                    continue
                # Tidigare dagliga uppdrag omprövas av handläggare; de får inte
                # blockera urvalet av nyinkomna ärenden vid varje pollning.
                previous_daily = exists().where(CaseWork.case_number == Case.case_number,
                    CaseWork.submission_key.startswith("system:daily_worker:", autoescape=True))
                active = exists().where(CaseWork.case_number == Case.case_number, CaseWork.status.in_(ACTIVE))
                pending = exists().where(ApprovalRequestRecord.case_id == Case.case_number,
                                         ApprovalRequestRecord.status == "pending")
                cases = session.scalars(select(Case).where(Case.case_type == case_type, Case.status == "open",
                    ~previous_daily, ~active, ~pending).order_by(Case.created_at, Case.case_number).limit(slots)).all()
                candidates = [(c.case_number, case_digest(_view(session, c))) for c in cases]
            for number, digest in candidates:
                # Samma underlag köas en gång även nästa dag. Ett fel kräver handläggaråtgärd.
                key = f"daily:{number}:{digest[:20]}"
                with self.session_factory() as session:
                    if session.scalar(select(CaseWork.id).where(CaseWork.submission_key == f"system:daily_worker:{key}")):
                        continue
                try:
                    self._submit(number, "Handlägg löneunderlaget och redovisa genomförandet eller behov av hjälp.",
                                 actor=Actor.system("daily_worker"), key=key, mode="handle")
                    added += 1
                except (ConflictError, HarnessError):
                    continue
        return added

    def mark_interrupted(self, work_id, *, actor, revision):
        """Uttrycklig operatörsåtgärd efter kontroll att den tidigare arbetaren stoppats."""
        if actor.type != "human":
            raise HarnessError("Avstämningen kräver en människa")
        with self.session_factory() as session:
            row = session.scalar(select(CaseWork).where(CaseWork.id == work_id).with_for_update())
            if row is None or row.status != "running" or row.revision != revision:
                raise ConflictError("Uppdraget körs inte eller har ändrats")
            row.cancel_requested = True
            row.status = "reconciliation_required"
            _unknown_usage(row)
            row.revision += 1
            _message(session, row, "system", actor.id, "Tidigare arbetare har stoppats; utfallet måste stämmas av.")


def work_goal(work):
    clarification = work["result"].get("last_clarification", "")
    extra = f"\nAktuellt förtydligande från handläggaren: {clarification}" if clarification else ""
    if work["mode"] == "assist":
        return f"Deluppdrag i ärende {work['case_number']}: {work.get('instruction', '')}{extra}"
    return (f"Handlägg ärende {work['case_number']} om löneunderlag. Läs ärendet och aktuellt bestånd, "
            "kontrollera underlaget och förhandsberäkna premien. Föreslå register_salary_report bara när "
            "indata exakt motsvarar ärendet. Saknas uppgifter: fråga handläggaren. "
            f"Beställarens uppdrag: {work.get('instruction', '')}{extra}")


def _unknown_usage(row):
    """Ett okänt utfall förbrukar reservationen; återstart återställer aldrig budget."""
    limits = row.result.get("reserved_limits", {})
    usage = {"steps": limits.get("max_steps", 12), "tool_calls": limits.get("max_tool_calls", 18),
             "cost_usd": limits.get("max_cost_usd", 0.5), "elapsed_seconds": limits.get("max_wall_seconds", 180)}
    row.result = {**row.result, "usage": usage, "usage_unknown": True}
