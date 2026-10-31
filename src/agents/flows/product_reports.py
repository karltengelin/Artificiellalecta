"""Produktrapporterna för aktuariens teamyta – en tunn adapter runt flödesmotorn (A2, B-042).

    console = ProductReportConsole.build(session_factory, trusted=service, actuary_service=aktuarie, ai=ai,
                                         renderer=render_report, environment_id="demo", dataset_ref="demo:current")
    view = console.start(2026, "", actor)                    # sammanfattning och rapport, stannar vid granskningen
    flow = console.flow(view.flow_id)                         # grindens hash: flow.gate_hashes["review"]
    view = console.decide(view.flow_id, flow.version, actor, decision="approved",
                          seen_hash=flow.gate_hashes["review"], note=None)
    pdf = console.delivery(view.flow_id, "rapport.pdf")

Samma regler som `QuestionConsole`: bara en inloggad operatör startar, granskar och avbryter;
miljö, dataset och körbild binds här; en körning åt gången i processen. Webbvyerna byggs i A3.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from agents.deliveries import DeliveryStore
from agents.ecosystem import Ecosystem
from agents.flows.console import FlowBusyError
from agents.flows.definitions.company_question import Renderer
from agents.flows.definitions.product_report import FLOW_TYPE, TEAM, ProductReportOrder, product_report_definition
from agents.flows.engine import AgentRuntime, FlowEngine, FlowView
from agents.flows.questions import STATUS_TEXT, policy_ref
from agents.flows.store import FlowError
from agents.journal import DEFAULT_JOURNAL_DIR
from agents.skills import SkillRegistry
from agents.trace import RunTrace, read_run_trace
from ai import AIClient
from services import Actor, ServiceLayer, default_registry
from services.operations import common
from services.operations.product_report_data import FIRST_YEAR


@dataclass(frozen=True)
class ProductReportView:
    flow_id: str
    year: int
    note: str
    requested_by: str
    created_at: datetime
    finished_at: datetime | None
    status: str
    status_text: str
    current_step: str | None
    steps: tuple[tuple[str, str, str], ...]  # (nyckel, rubrik, status)
    summarized: bool
    run_id: str | None
    cost_usd: float | None
    delivery_version: int | None
    review: str  # not_reviewed | approved | rejected
    reviewed_by: str | None
    accepted: bool
    error: str | None
    supersedes: str | None


def report_view(flow: FlowView) -> ProductReportView:
    order = ProductReportOrder.model_validate(flow.input)
    by_key = {s.key: s for s in flow.steps}
    summary, render, deliver = by_key["summary"], by_key["render"], by_key["deliver"]
    decision = next((d for d in flow.decisions if d.step_key == "review"), None)
    output = (summary.result or {}).get("output") or {}
    run = (summary.result or {}).get("run") or {}
    delivery = (render.result or {}).get("delivery") if render.status == "completed" else None
    return ProductReportView(
        flow_id=flow.flow_id, year=order.year, note=order.note, requested_by=flow.created_by,
        created_at=flow.created_at, finished_at=flow.finished_at, status=flow.status,
        status_text=STATUS_TEXT.get(flow.status, flow.status), current_step=flow.current_step,
        steps=tuple((s.key, s.title, s.status) for s in flow.steps), summarized=output.get("result") is not None,
        run_id=summary.run_id, cost_usd=run.get("cost_usd"), delivery_version=delivery["version"] if delivery else None,
        review=decision.decision if decision else "not_reviewed", reviewed_by=decision.decided_by if decision else None,
        accepted=deliver.status == "completed",
        error=next((s.error for s in flow.steps if s.error), None) or (flow.note if flow.status == "failed" else None),
        supersedes=order.supersedes,
    )


@dataclass
class ProductReportConsole:
    engine: FlowEngine
    store: DeliveryStore
    environment_id: str
    dataset_ref: str
    policy_ref: str
    journal_dir: Path = DEFAULT_JOURNAL_DIR
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @classmethod
    def build(cls, session_factory, *, trusted: ServiceLayer, actuary_service: ServiceLayer, ai: AIClient,
              renderer: Renderer, environment_id: str, dataset_ref: str, deliveries_dir: Path | None = None,
              journal_dir: Path | None = None) -> ProductReportConsole:
        """`actuary_service` är aktuarieteamets tjänstelager (rollen agent_aktuarie i Postgres)."""
        if ai is None or renderer is None:
            raise ValueError("AI-klient och renderare måste anges uttryckligen")
        eco = Ecosystem.load()
        store = DeliveryStore(deliveries_dir)
        journal_dir = journal_dir or DEFAULT_JOURNAL_DIR
        runtime = AgentRuntime(ai=ai, ecosystem=eco, skills=SkillRegistry.build(eco, default_registry),
                               service=actuary_service, journal_dir=journal_dir, team_services={TEAM: actuary_service})
        engine = FlowEngine(session_factory, [product_report_definition(renderer, store, journal_dir=journal_dir)],
                            runtime=runtime, trusted=trusted)
        return cls(engine=engine, store=store, environment_id=environment_id, dataset_ref=dataset_ref,
                   policy_ref=policy_ref(eco, ai), journal_dir=journal_dir)

    def years(self) -> list[int]:
        """Valbara år, senaste först: från första året med premiehistorik till innevarande."""
        return list(range(common.today().year, FIRST_YEAR - 1, -1))

    def list(self) -> list[ProductReportView]:
        return [report_view(f) for f in self.engine.list(flow_types=(FLOW_TYPE,))]

    def get(self, flow_id: str) -> ProductReportView:
        return report_view(self.flow(flow_id))

    def flow(self, flow_id: str) -> FlowView:
        flow = self.engine.get(flow_id)
        if flow.flow_type != FLOW_TYPE:
            raise FlowError(f"{flow_id} är ingen produktrapport")
        return flow

    def trace(self, flow_id: str) -> RunTrace | None:
        return read_run_trace(self.journal_dir, self.flow(flow_id).step("summary").run_id)

    def delivery(self, flow_id: str, name: str) -> bytes:
        render = self.flow(flow_id).step("render")
        if render.status != "completed":
            raise FlowError(f"{flow_id} har ingen rapport ännu")
        receipt = render.result["delivery"]
        if name not in receipt["files"]:
            raise FlowError(f"Okänd leveransfil: {name}")
        return self.store.read(flow_id, receipt["version"], name, receipt["files"][name])

    def start(self, year: int, note: str, actor: Actor, *, supersedes: str | None = None) -> ProductReportView:
        """Startar rapporten och kör sammanfattning och rendering fram till granskningen."""
        self._require_human(actor)
        if year not in self.years():
            raise FlowError(f"Välj ett år från {FIRST_YEAR} till {common.today().year}")
        if supersedes is not None and self.get(supersedes).status != "rejected":
            raise FlowError("Bara en avslagen rapport kan ersättas")
        order = ProductReportOrder(year=year, note=note, environment_id=self.environment_id,
                                   dataset_ref=self.dataset_ref, policy_ref=self.policy_ref, supersedes=supersedes)
        with self._running():
            flow = self.engine.start(FLOW_TYPE, order.model_dump(mode="json"), actor=actor)
            return report_view(self._advance(flow, actor))

    def decide(self, flow_id: str, version: int, actor: Actor, *, decision: str, seen_hash: str,
               note: str | None) -> ProductReportView:
        self._require_human(actor)
        self.flow(flow_id)
        with self._running():
            flow = self.engine.decide_gate(flow_id, expected_version=version, actor=actor, decision=decision,
                                           seen_hash=seen_hash, note=note)
            return report_view(self._advance(flow, actor))

    def cancel(self, flow_id: str, version: int, actor: Actor, note: str) -> ProductReportView:
        self._require_human(actor)
        self.flow(flow_id)
        return report_view(self.engine.cancel(flow_id, expected_version=version, actor=actor, note=note))

    def _advance(self, flow: FlowView, actor: Actor) -> FlowView:
        while flow.status == "running":
            flow = self.engine.run_next(flow.flow_id, expected_version=flow.version, actor=actor)
        return flow

    @contextmanager
    def _running(self):
        if not self._lock.acquire(blocking=False):
            raise FlowBusyError("En produktrapport körs redan – vänta tills den är klar")
        try:
            yield
        finally:
            self._lock.release()

    @staticmethod
    def _require_human(actor: Actor) -> None:
        if actor.type != "human":
            raise FlowError("Produktrapporter startas, granskas och avbryts av en inloggad operatör")
