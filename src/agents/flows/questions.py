"""Bolagsfrågorna för centralen och teamytan – en tunn adapter runt flödesmotorn (OC-3a, B-041).

    console = QuestionConsole.build(session_factory, trusted=service, actuary_service=aktuarie, ai=ai,
                                    renderer=render_report, environment_id="demo", dataset_ref="demo:current")
    view = console.start(date(2026, 9, 1), "", actor)        # svar och rapport, stannar vid granskningen
    flow = console.flow(view.flow_id)                         # grindens hash: flow.gate_hashes["review"]
    view = console.decide(view.flow_id, flow.version, actor, decision="approved",
                          seen_hash=flow.gate_hashes["review"], note=None)
    pdf = console.delivery(view.flow_id, "rapport.pdf")

Webben rör varken modeller, sessioner eller filvägar: den anropar den här adaptern (underlagets
§10.2). Aktören ska komma ur en verifierad operatörssession (val H–I); adaptern godtar aldrig en
agent. Miljö, dataset och körbild binds här, inte av formuläret. En körning åt gången i processen,
som i `FlowConsole`; motorns villkorliga uppdatering på versionen skyddar mellan processer.
"""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from agents.deliveries import DeliveryStore
from agents.ecosystem import Ecosystem
from agents.flows.console import FlowBusyError
from agents.flows.definitions.company_question import (
    FLOW_TYPE,
    TEAM,
    CompanyQuestion,
    Renderer,
    closed_months,
    company_question_definition,
)
from agents.flows.engine import AgentRuntime, FlowEngine, FlowView
from agents.flows.store import FlowError
from agents.journal import DEFAULT_JOURNAL_DIR
from agents.skills import SkillRegistry
from ai import AIClient
from services import Actor, ServiceLayer, default_registry
from services.operations import common

STATUS_TEXT = {
    "running": "Pågår",
    "waiting_gate": "Väntar på granskning",
    "completed": "Levererad",
    "rejected": "Avslagen",
    "failed": "Misslyckades",
    "cancelled": "Avbruten",
    "reconciliation_required": "Behöver avstämning",
}
UNAVAILABLE_REASON = "Ingen granskad förmåga för beståndsfrågor ännu – välj aktuarieteamet"


@dataclass(frozen=True)
class TeamChoice:
    team: str
    name: str
    available: bool
    reason: str | None


@dataclass(frozen=True)
class AssignmentView:
    """Ett uppdrag som centralen och teamytan visar likadant (val K)."""

    flow_id: str
    task_id: str
    team: str
    question_type: str
    month: date
    note: str
    requested_by: str
    created_at: datetime
    finished_at: datetime | None
    status: str
    status_text: str
    current_step: str | None
    steps: tuple[tuple[str, str, str], ...]  # (nyckel, rubrik, status)
    answer_status: str | None
    run_id: str | None
    cost_usd: float | None
    delivery_version: int | None
    review: str  # not_reviewed | approved | rejected
    reviewed_by: str | None
    reviewed_at: datetime | None
    accepted: bool
    error: str | None
    supersedes: str | None


def assignment_view(flow: FlowView) -> AssignmentView:
    q = CompanyQuestion.model_validate(flow.input)
    by_key = {s.key: s for s in flow.steps}
    answer, render, deliver = by_key["answer"], by_key["render"], by_key["deliver"]
    decision = next((d for d in flow.decisions if d.step_key == "review"), None)
    output = (answer.result or {}).get("output") or {}
    run = (answer.result or {}).get("run") or {}
    delivery = (render.result or {}).get("delivery") if render.status == "completed" else None
    return AssignmentView(
        flow_id=flow.flow_id, task_id=f"task-{flow.flow_id}", team=TEAM, question_type=q.question_type,
        month=q.month, note=q.note, requested_by=flow.created_by, created_at=flow.created_at,
        finished_at=flow.finished_at, status=flow.status, status_text=STATUS_TEXT.get(flow.status, flow.status),
        current_step=flow.current_step, steps=tuple((s.key, s.title, s.status) for s in flow.steps),
        answer_status=(output.get("result") or {}).get("status"), run_id=answer.run_id,
        cost_usd=run.get("cost_usd"), delivery_version=delivery["version"] if delivery else None,
        review=decision.decision if decision else "not_reviewed",
        reviewed_by=decision.decided_by if decision else None, reviewed_at=decision.decided_at if decision else None,
        accepted=deliver.status == "completed",
        error=next((s.error for s in flow.steps if s.error), None) or (flow.note if flow.status == "failed" else None),
        supersedes=q.supersedes,
    )


@dataclass
class QuestionConsole:
    engine: FlowEngine
    store: DeliveryStore
    ecosystem: Ecosystem
    environment_id: str
    dataset_ref: str
    policy_ref: str
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @classmethod
    def build(
        cls,
        session_factory,
        *,
        trusted: ServiceLayer,
        actuary_service: ServiceLayer,
        ai: AIClient,
        renderer: Renderer,
        environment_id: str,
        dataset_ref: str,
        deliveries_dir: Path | None = None,
        journal_dir: Path | None = None,
    ) -> QuestionConsole:
        """`actuary_service` är aktuarieteamets tjänstelager (rollen agent_aktuarie i Postgres)."""
        if ai is None or renderer is None:
            raise ValueError("AI-klient och renderare måste anges uttryckligen")
        eco = Ecosystem.load()
        store = DeliveryStore(deliveries_dir)
        runtime = AgentRuntime(
            ai=ai, ecosystem=eco, skills=SkillRegistry.build(eco, default_registry), service=actuary_service,
            journal_dir=journal_dir or DEFAULT_JOURNAL_DIR, team_services={TEAM: actuary_service},
        )
        engine = FlowEngine(session_factory, [company_question_definition(renderer, store)],
                            runtime=runtime, trusted=trusted)
        return cls(engine=engine, store=store, ecosystem=eco, environment_id=environment_id,
                   dataset_ref=dataset_ref, policy_ref=policy_ref(eco, ai))

    # --- läsning ----------------------------------------------------------------------------------

    def months(self) -> list[date]:
        return closed_months(common.today())

    def teams(self) -> list[TeamChoice]:
        """Alla team; bara aktuarien kan ta emot frågan (val B, OC-0 §6.1). Inget modellanrop."""
        return [
            TeamChoice(team=key, name=self.ecosystem.agents[t.lead].name if t.lead in self.ecosystem.agents else key,
                       available=key == TEAM, reason=None if key == TEAM else UNAVAILABLE_REASON)
            for key, t in self.ecosystem.teams.items()
        ]

    def list(self, team: str | None = None) -> list[AssignmentView]:
        if team not in (None, TEAM):
            return []
        return [assignment_view(f) for f in self.engine.list(flow_types=(FLOW_TYPE,))]

    def get(self, flow_id: str) -> AssignmentView:
        return assignment_view(self.flow(flow_id))

    def flow(self, flow_id: str) -> FlowView:
        """Hela flödet för detaljsidan och granskningen (grindens hash i `gate_hashes['review']`)."""
        flow = self.engine.get(flow_id)
        if flow.flow_type != FLOW_TYPE:
            raise FlowError(f"{flow_id} är ingen bolagsfråga")
        return flow

    def delivery(self, flow_id: str, name: str) -> bytes:
        """En leveransfil, kontrollerad mot kontrollsumman flödet har bundit."""
        render = self.flow(flow_id).step("render")
        if render.status != "completed":
            raise FlowError(f"{flow_id} har ingen rapport ännu")
        receipt = render.result["delivery"]
        if name not in receipt["files"]:
            raise FlowError(f"Okänd leveransfil: {name}")
        return self.store.read(flow_id, receipt["version"], name, receipt["files"][name])

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    # --- åtgärder ---------------------------------------------------------------------------------

    def start(self, month: date, note: str, actor: Actor, *, supersedes: str | None = None) -> AssignmentView:
        """Startar uppdraget och kör svar och rapport fram till granskningen (val J)."""
        self._require_human(actor)
        if month not in self.months():
            raise FlowError("Välj en avslutad månad bland de elva senaste")
        if supersedes is not None and self.get(supersedes).status != "rejected":
            raise FlowError("Bara ett avslaget uppdrag kan ersättas")
        question = CompanyQuestion(month=month, note=note, environment_id=self.environment_id,
                                   dataset_ref=self.dataset_ref, policy_ref=self.policy_ref, supersedes=supersedes)
        with self._running():
            flow = self.engine.start(FLOW_TYPE, question.model_dump(mode="json"), actor=actor)
            return assignment_view(self._advance(flow, actor))

    def decide(self, flow_id: str, version: int, actor: Actor, *, decision: str, seen_hash: str,
               note: str | None) -> AssignmentView:
        """Granskningsbeslutet. Ett godkännande kör leveranssteget direkt."""
        self._require_human(actor)
        self.flow(flow_id)
        with self._running():
            flow = self.engine.decide_gate(flow_id, expected_version=version, actor=actor, decision=decision,
                                           seen_hash=seen_hash, note=note)
            return assignment_view(self._advance(flow, actor))

    def cancel(self, flow_id: str, version: int, actor: Actor, note: str) -> AssignmentView:
        self._require_human(actor)
        self.flow(flow_id)
        return assignment_view(self.engine.cancel(flow_id, expected_version=version, actor=actor, note=note))

    def reconcile(self, flow_id: str, version: int, actor: Actor, *, retry: bool, note: str) -> AssignmentView:
        self._require_human(actor)
        self.flow(flow_id)
        with self._running():
            flow = self.engine.resolve_reconciliation(flow_id, expected_version=version, actor=actor,
                                                      retry=retry, note=note)
            return assignment_view(self._advance(flow, actor))

    def _advance(self, flow: FlowView, actor: Actor) -> FlowView:
        """Kör agent- och systemsteg tills flödet väntar, är klart eller har stannat."""
        while flow.status == "running":
            flow = self.engine.run_next(flow.flow_id, expected_version=flow.version, actor=actor)
        return flow

    @contextmanager
    def _running(self):
        if not self._lock.acquire(blocking=False):
            raise FlowBusyError("En bolagsfråga körs redan – vänta tills den är klar")
        try:
            yield
        finally:
            self._lock.release()

    @staticmethod
    def _require_human(actor: Actor) -> None:
        if actor.type != "human":
            raise FlowError("Bolagsfrågor startas, granskas och avbryts av en inloggad operatör")


def policy_ref(ecosystem: Ecosystem, ai: AIClient) -> str:
    """Hashbunden körbild av dagens körpolicy och modellroller, utan hemligheter (OC-0 §6.2 före OC-5)."""
    roles = {name: getattr(spec, "model", None) for name, spec in ai.config.roles.items()}
    raw = json.dumps({"ecosystem": ecosystem.checksum, "roles": roles}, sort_keys=True).encode("utf-8")
    return f"korbild:{hashlib.sha256(raw).hexdigest()[:16]}"
