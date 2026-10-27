"""Flödena för handläggar-UI:t – en tunn adapter runt flödesmotorn (Fas 3c 3c-3, B-035).

Webben (`src/web/routes/flows.py`) rör varken modeller, sessioner eller operationsmoduler.
Den anropar den här adaptern, som håller motorn med definitionerna, agenternas körmiljö och
det betrodda tjänstelagret. Aktören är alltid handläggaren; motorn kräver en människa för
grindbeslut, manuella steg, avstämning och avbrott.

    console = FlowConsole.build(session_factory, trusted=service, agent_service=agent_service, ai=ai,
                                team_services={"aktuarie": agent_service_layer("aktuarie")})
    console.mark_interrupted()                        # när UI:t startar
    flow = console.start(source_handle, actor)
    flow = console.run_next(flow.flow_id, flow.version, actor)

- **En körning åt gången** i processen (lokalt, en handläggare – val F): *Kör nästa steg* körs
  synkront, och ett andra klick under en pågående körning stoppas här innan motorn ens läser
  flödet. Motorns villkorliga UPDATE på versionen skyddar också mellan processer.
- **Modellen:** anroparen måste ange AI-klienten uttryckligen. Ingen testmodell,
  scenariokälla eller ändrad regelgiltighet väljs automatiskt (B-037).
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.ecosystem import Ecosystem
from agents.flows.definitions import DEFINITIONS
from agents.flows.engine import AgentRuntime, FlowEngine, FlowView
from agents.flows.store import FlowError
from agents.gateways import (
    DraftGateway,
    Gateways,
    ListRegulatoryDocumentsInput,
    RegulatoryGateway,
)
from agents.gateways.regulatory import DocumentInfo
from agents.journal import DEFAULT_JOURNAL_DIR
from agents.skills import SkillRegistry
from ai import AIClient
from services import Actor, ServiceLayer, default_registry

#: Dokumentslag i regelverksgatewayen som kan starta ett flöde
SOURCE_KINDS = ("bevakning",)


class FlowBusyError(FlowError):
    """Ett steg körs redan i den här processen."""


@dataclass
class FlowConsole:
    engine: FlowEngine
    regulatory: RegulatoryGateway
    drafts: DraftGateway
    journal_dir: Path
    model_label: str
    simulated_role: bool
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @classmethod
    def build(
        cls,
        session_factory,
        *,
        trusted: ServiceLayer,
        agent_service: ServiceLayer,
        team_services: dict[str, ServiceLayer] | None = None,
        simulated_role: bool = True,
        ai: AIClient,
        journal_dir: Path | None = None,
        drafts_dir: Path | None = None,
        regulatory: RegulatoryGateway | None = None,
    ) -> FlowConsole:
        """Bygg en adapter med uttrycklig modellklient och oförändrade tjänstelager."""
        if ai is None:
            raise ValueError("En AI-klient måste anges för agentstegen")
        eco = Ecosystem.load()
        regulatory = regulatory or RegulatoryGateway()
        drafts = DraftGateway(drafts_dir) if drafts_dir else DraftGateway()
        journal_dir = journal_dir or DEFAULT_JOURNAL_DIR
        runtime = AgentRuntime(
            ai=ai, ecosystem=eco,
            skills=SkillRegistry.build(eco, default_registry), service=agent_service,
            gateways=Gateways(regulatory=regulatory, drafts=drafts), journal_dir=journal_dir,
            team_services=dict(team_services or {}),
        )
        engine = FlowEngine(session_factory, DEFINITIONS, runtime=runtime, trusted=trusted)
        return cls(engine=engine, regulatory=regulatory, drafts=drafts, journal_dir=journal_dir,
                   model_label="konfigurerad AI-klient", simulated_role=simulated_role)

    # --- läsning ----------------------------------------------------------------------------------

    def list(self) -> list[FlowView]:
        """Flödena den här konsolen driver – bolagsfrågor (OC-3a) har sin egen adapter."""
        return self.engine.list(flow_types=self.engine.definitions)

    def get(self, flow_id: str) -> FlowView:
        return self.engine.get(flow_id)

    def sources(self) -> list[DocumentInfo]:
        """Källor att starta från, utan något förvalt scenario."""
        documents = [d for kind in SOURCE_KINDS
                     for d in self.regulatory.list_documents(ListRegulatoryDocumentsInput(kind=kind)).documents]
        return documents

    def draft(self, flow_id: str, step_key: str, name: str) -> str:
        """Ett utkast som steget har skrivit – bara utkast i stegets egna referenser."""
        step = self.get(flow_id).step(step_key)
        if step.run_id is None or f"utkast:{step.team}/{step.run_id}/{name}" not in step.artifact_refs:
            raise FlowError(f"Utkastet {name} hör inte till steget '{step_key}' i {flow_id}")
        return self.drafts.read_draft(step.team, step.run_id, name)

    def journal(self, flow_id: str, step_key: str) -> list[dict[str, Any]]:
        """Körjournalen för ett agentsteg (logs/agent_runs/, val J). Den har inga råa personuppgifter."""
        step = self.get(flow_id).step(step_key)
        if step.run_id is None:
            raise FlowError(f"Steget '{step_key}' i {flow_id} har ingen körning")
        path = self.journal_dir / f"{step.run_id}.jsonl"
        if not path.exists():
            raise FlowError(f"Körjournalen {path.name} finns inte i {self.journal_dir}")
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    # --- åtgärder -----------------------------------------------------------------------------------

    def start(self, source_handle: str, actor: Actor) -> FlowView:
        if source_handle not in {source.handle for source in self.sources()}:
            raise FlowError("Källan finns inte bland tillgängliga bevakningsunderlag")
        return self.engine.start("rule_change_parameter", {"source_handle": source_handle}, actor=actor)

    def run_next(self, flow_id: str, version: int, actor: Actor) -> FlowView:
        if not self._lock.acquire(blocking=False):
            raise FlowBusyError("Ett steg körs redan – vänta tills det är klart")
        try:
            return self.engine.run_next(flow_id, expected_version=version, actor=actor)
        finally:
            self._lock.release()

    def decide(
        self, flow_id: str, version: int, actor: Actor, *, decision: str, seen_hash: str, note: str | None,
        details: dict[str, Any] | None = None,
    ) -> FlowView:
        return self.engine.decide_gate(flow_id, expected_version=version, actor=actor, decision=decision,
                                       seen_hash=seen_hash, note=note, details=details)

    def complete_manual(self, flow_id: str, version: int, actor: Actor, data: dict[str, Any]) -> FlowView:
        return self.engine.complete_manual(flow_id, expected_version=version, actor=actor, data=data)

    def cancel(self, flow_id: str, version: int, actor: Actor, note: str) -> FlowView:
        return self.engine.cancel(flow_id, expected_version=version, actor=actor, note=note)

    def reconcile(self, flow_id: str, version: int, actor: Actor, *, retry: bool, note: str) -> FlowView:
        return self.engine.resolve_reconciliation(flow_id, expected_version=version, actor=actor, retry=retry,
                                                  note=note)

    def mark_interrupted(self) -> list[str]:
        """Steg som stod som `running` när UI:t startade blir `reconciliation_required`."""
        return self.engine.mark_interrupted()
