"""Flödesmotorn (Fas 3c 3c-2, B-035, flaggskeppsflöde.md §6, harness.md §10.3–10.4).

    engine = FlowEngine(session_factory, [definition], runtime=runtime, trusted=service)
    flow = engine.start("rule_change_parameter", {"source_handle": source_handle}, actor=operator)
    flow = engine.run_next(flow.flow_id, expected_version=flow.version, actor=operator)   # agentsteg
    flow = engine.decide_gate(flow.flow_id, expected_version=flow.version, actor=operator,
                              decision="approved", seen_hash=flow.gate_hashes["g1"])

Regler:
- Definitionen bestämmer ordningen (agents.flows.definition); modellen bestämmer aldrig nästa steg.
- Varje åtgärd tar flödets `version` som operatören såg och gör en villkorlig UPDATE på den.
  Två klick på *Kör nästa steg* ger en körning och en konflikt.
- Ett steg tas i en transaktion (status `running`, run-id), körs utanför den och
  registreras i en ny. Ett agentsteg körs genom harness med `flow_id` och `flow_step_id`.
- En grind binder hashen av de stegresultat den gäller (`seen_hash` ska vara den hash
  operatören såg). Innan ett senare steg tas räknas varje godkänd grind om; ändrat underlag
  stoppar flödet. Ett avslag stoppar flödet som `rejected` – ett nytt försök är ett nytt flöde.
- Grindbeslut, manuella steg, avstämning och avbrott görs bara av en människa.
- Ett systemsteg som lägger ett förslag i tjänstelagrets godkännandekö väntar tills
  förslaget är avgjort i `/godkannanden`. Grinden ersätter aldrig det godkännandet.
- Ingen automatisk återupptagning. Ett steg som var `running` när motorn startade om blir
  `reconciliation_required` (`mark_interrupted`), och operatören avgör om det körs igen.
- Fel som kan ha hänt efter en sidoeffekt (ett oväntat undantag under körningen) ger också
  `reconciliation_required`; ett kontrollerat avslut som inte är klart ger `failed`.

Flödestabellerna skrivs med den betrodda anslutningen (`session_factory`); agenterna kör
med sitt teams tjänstelager (`AgentRuntime.service_for`).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from agents.assignments import run_assignment
from agents.ecosystem import Ecosystem
from agents.flows.definition import (
    AgentStep,
    FlowContext,
    FlowDefinition,
    GateStep,
    ManualStep,
    Step,
    SystemOutcome,
)
from agents.flows.store import (
    FlowConflictError,
    FlowError,
    bound_hash,
    bump,
    canonical_hash,
    load,
    next_flow_id,
)
from agents.gateways import Gateways
from agents.run import RunResult, RunStatus
from agents.skills import SkillRegistry
from ai import AIClient
from models import Flow, FlowGateDecision, FlowStep
from models.flow import FINISHED_FLOW_STATUSES
from services import Actor, ServiceLayer

#: Flödets status när ett steg av slaget står på tur
STATUS_FOR_KIND = {"agent": "running", "system": "running", "gate": "waiting_gate", "manual": "waiting_manual"}


@dataclass(frozen=True)
class AgentRuntime:
    """Det agentstegen körs med: AI-lagret, körpolicyn och agenternas tjänstelager.

    `team_services` ger ett team sitt eget tjänstelager (teamets databasroll, harness.md §5.1);
    team som saknas där kör med `service`.
    """

    ai: AIClient
    ecosystem: Ecosystem
    skills: SkillRegistry
    service: ServiceLayer
    gateways: Gateways | None = None
    journal_dir: Path | None = None
    team_services: dict[str, ServiceLayer] = field(default_factory=dict)

    def service_for(self, team: str) -> ServiceLayer:
        return self.team_services.get(team, self.service)


@dataclass(frozen=True)
class StepView:
    key: str
    position: int
    kind: str
    title: str
    status: str
    team: str | None
    agent: str | None
    run_id: str | None
    result: dict[str, Any] | None
    result_hash: str | None
    approval_id: str | None
    artifact_refs: tuple[str, ...]
    started_at: datetime | None
    finished_at: datetime | None
    completed_by: str | None
    error: str | None


@dataclass(frozen=True)
class GateDecisionView:
    step_key: str
    decision: str
    decided_by: str
    note: str | None
    bound_steps: tuple[str, ...]
    bound_hash: str
    decided_at: datetime


@dataclass(frozen=True)
class FlowView:
    flow_id: str
    flow_type: str
    definition_version: str
    status: str
    version: int
    current_step: str | None
    input: dict[str, Any]
    created_by: str
    created_at: datetime
    finished_at: datetime | None
    note: str | None
    steps: tuple[StepView, ...]
    decisions: tuple[GateDecisionView, ...]
    gate_hashes: dict[str, str | None] = field(default_factory=dict)  # grind -> hash av underlaget nu
    stale_gates: tuple[str, ...] = ()  # godkända grindar vars underlag har ändrats

    def step(self, key: str) -> StepView:
        for step in self.steps:
            if step.key == key:
                return step
        raise FlowError(f"Flödet {self.flow_id} har inget steg '{key}'")

    @property
    def finished(self) -> bool:
        return self.status in FINISHED_FLOW_STATUSES


class FlowEngine:
    def __init__(
        self,
        session_factory,
        definitions: Iterable[FlowDefinition],
        *,
        runtime: AgentRuntime | None = None,
        trusted: ServiceLayer | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """`session_factory` är den betrodda anslutningen; `trusted` tjänstelagret för systemsteg och kön."""
        self._session_factory = session_factory
        self.definitions = {d.flow_type: d for d in definitions}
        self.runtime = runtime
        self.trusted = trusted
        self._now = clock

    # --- läsning ----------------------------------------------------------------------------------

    def get(self, flow_id: str) -> FlowView:
        with self._session_factory() as s:
            return self._view(*load(s, flow_id))

    def list(self, status: str | None = None, *, flow_types: Iterable[str] | None = None) -> list[FlowView]:
        with self._session_factory() as s:
            query = select(Flow.flow_id).order_by(Flow.flow_id.desc())
            if status is not None:
                query = query.where(Flow.status == status)
            if flow_types is not None:
                query = query.where(Flow.flow_type.in_(tuple(flow_types)))
            return [self._view(*load(s, flow_id)) for flow_id in s.scalars(query)]

    # --- start ------------------------------------------------------------------------------------

    def start(self, flow_type: str, data: dict[str, Any], *, actor: Actor) -> FlowView:
        """Startar ett flöde. Bara en människa eller betrodd systemkod – aldrig en agent."""
        if actor.is_agent:
            raise FlowError("Ett flöde startas av operatören, inte av en agent")
        definition = self._definition(flow_type)
        try:
            validated = definition.input_model.model_validate(data)
        except ValidationError as exc:
            raise FlowError(f"Ogiltig indata till flödet '{flow_type}': {exc}") from exc
        first = definition.steps[0]
        try:
            with self._session_factory() as s:
                flow_id = next_flow_id(s)
                s.add(Flow(
                    flow_id=flow_id, flow_type=flow_type, definition_version=definition.version,
                    status=STATUS_FOR_KIND[first.kind], input=validated.model_dump(mode="json"),
                    current_step=first.key, version=1, created_by=actor.id,
                ))
                s.flush()
                for position, step in enumerate(definition.steps, start=1):
                    s.add(FlowStep(
                        flow_id=flow_id, step_key=step.key, position=position, kind=step.kind, title=step.title,
                        team=getattr(step, "team", None), status="pending",
                    ))
        except IntegrityError as exc:
            raise FlowConflictError("Ett annat flöde startades samtidigt – försök igen") from exc
        return self.get(flow_id)

    # --- agent- och systemsteg ---------------------------------------------------------------------

    def run_next(self, flow_id: str, *, expected_version: int, actor: Actor) -> FlowView:
        """Kör flödets nästa agent- eller systemsteg, eller prövar ett väntande förslag i kön."""
        self._require_operator(actor)
        approval = self._awaited_approval(flow_id)
        with self._session_factory() as s:
            flow, steps, decisions = load(s, flow_id)
            self._check_version(flow, expected_version)
            definition = self._definition(flow.flow_type)
            if flow.definition_version != definition.version:
                raise FlowError(
                    f"Flödet använder definition v{flow.definition_version}, men tillgänglig version är "
                    f"v{definition.version}. Stäm av det äldre flödet innan ett nytt startas"
                )
            if flow.status == "waiting_approval":
                return self._observe_approval(s, flow, steps, expected_version, approval)
            if flow.status != "running":
                raise FlowError(f"Flödet {flow_id} är {flow.status} – inget steg att köra")
            step_def = definition.step(flow.current_step)
            if step_def.kind not in ("agent", "system"):
                raise FlowError(f"Steget '{step_def.key}' är {step_def.kind} och körs inte av motorn")
            self._check_gates_fresh(flow, steps, decisions)
            row = self._row(steps, step_def.key)
            if row.status != "pending":
                raise FlowError(f"Steget '{row.step_key}' är {row.status}")
            row.status = "running"
            row.started_at = self._now()
            if isinstance(step_def, AgentStep):
                row.run_id = f"run-{uuid.uuid4().hex[:12]}"
                row.agent = self._runtime().ecosystem.teams[step_def.team].lead
            run_id, step_id = row.run_id, str(row.id)
            version = bump(s, flow, expected_version)
            ctx = self._context(flow, steps)

        try:
            if isinstance(step_def, AgentStep):
                outcome: RunResult | SystemOutcome = self._run_agent(step_def, ctx, step_id, run_id)
            else:
                outcome = step_def.run(ctx, self.trusted)
        except Exception as exc:  # noqa: BLE001 – utfallet är okänt; operatören stämmer av
            return self._interrupted(flow_id, step_def.key, version, f"{type(exc).__name__}: {exc}"[:500])

        with self._session_factory() as s:
            flow, steps, _ = load(s, flow_id)
            row = self._row(steps, step_def.key)
            if isinstance(outcome, SystemOutcome):
                self._record_system(s, flow, steps, row, outcome, version, actor)
            else:
                self._record_agent(s, flow, steps, row, outcome, version)
        return self.get(flow_id)

    def _run_agent(self, step: AgentStep, ctx: FlowContext, step_id: str, run_id: str) -> RunResult:
        runtime = self._runtime()
        request = step.request(ctx)
        if request.target_team != step.team:
            raise FlowError(f"Steget '{step.key}' gäller teamet {step.team}, uppdraget {request.target_team}")
        request = request.model_copy(update={"flow_id": ctx.flow_id, "flow_step_id": step_id})
        mandate = step.mandate(ctx) if step.mandate is not None else None
        outcome = run_assignment(
            runtime.ai, runtime.ecosystem, runtime.skills, runtime.service_for(step.team), request,
            parameter_change=mandate, gateways=runtime.gateways, run_id=run_id, journal_dir=runtime.journal_dir,
        )
        if request.result_schema is not None and outcome.result.status == RunStatus.COMPLETED and outcome.result.output is None:
            return outcome.result.model_copy(update={"status": RunStatus.NEEDS_HUMAN})
        return outcome.result

    def _record_agent(self, s, flow: Flow, steps: list[FlowStep], row: FlowStep, result: RunResult, version: int) -> None:
        row.finished_at = self._now()
        run = {
            "run_id": result.run_id, "status": result.status.value, "summary": result.summary,
            "cost_usd": result.cost_usd, "evidence_refs": list(result.evidence_refs),
            "uncertainties": list(result.uncertainties),
        }
        if result.status != RunStatus.COMPLETED:
            row.status = "failed"
            row.result = {"run": run, "output": None}
            row.error = f"Körningen slutade som {result.status.value}: {result.summary}"
            bump(s, flow, version, status="failed", finished_at=self._now(),
                 note=f"Steget '{row.step_key}' lyckades inte – starta ett nytt flöde efter avstämning")
            return
        output = result.output
        drafts = (output or {}).get("evidence", {}).get("drafts", [])
        self._complete(row, {"run": run, "output": output}, completed_by=None)
        row.artifact_refs = [d["reference"] for d in drafts]
        self._advance(s, flow, row.step_key, version)

    def _record_system(
        self, s, flow: Flow, steps: list[FlowStep], row: FlowStep, outcome: SystemOutcome, version: int, actor: Actor
    ) -> None:
        if outcome.error is not None:
            row.status = "failed"
            row.finished_at = self._now()
            row.result = outcome.result
            row.error = outcome.error[:500]
            bump(s, flow, version, status="failed", finished_at=self._now(),
                 note=f"Steget '{row.step_key}' misslyckades – starta ett nytt flöde")
            return
        if outcome.approval_id is not None:
            row.status = "waiting"
            row.approval_id = outcome.approval_id
            row.result = outcome.result
            bump(s, flow, version, status="waiting_approval")
            return
        row.finished_at = self._now()
        self._complete(row, outcome.result, completed_by=actor.id)
        self._advance(s, flow, row.step_key, version)

    def _awaited_approval(self, flow_id: str):
        """Förslaget ett väntande flöde väntar på, läst innan flödets transaktion öppnas.

        Kön läses med tjänstelagrets egen anslutning. Inom flödets transaktion skulle den
        vänta på flödets eget skrivlås i en SQLite-fil (demodatabasen, BEGIN IMMEDIATE).
        """
        with self._session_factory() as s:
            flow, steps, _ = load(s, flow_id)
            if flow.status != "waiting_approval":
                return None
            approval_id = self._row(steps, flow.current_step).approval_id
        return self._trusted().approvals.get(approval_id)

    def _observe_approval(self, s, flow: Flow, steps: list[FlowStep], version: int, approval) -> FlowView:
        row = self._row(steps, flow.current_step)
        if approval is None or approval.id != row.approval_id:
            raise FlowError(f"Förslaget {row.approval_id} finns inte i godkännandekön")
        if approval.status == "pending":
            raise FlowError(f"Förslaget {row.approval_id} väntar på godkännande i /godkannanden")
        decided = {"approval_id": approval.id, "operation": approval.operation, "status": approval.status,
                   "decided_by": approval.decided_by, "decided_at": approval.decided_at,
                   "note": approval.decision_note}
        row.finished_at = self._now()
        if approval.status == "rejected":
            row.status = "rejected"
            row.result = {**(row.result or {}), "approval": decided}
            bump(s, flow, version, status="rejected", finished_at=self._now(),
                 note=f"Förslaget {approval.id} avslogs av {approval.decided_by}")
        else:
            self._complete(row, {**(row.result or {}), "approval": decided}, completed_by=approval.decided_by)
            self._advance(s, flow, row.step_key, version)
        s.flush()
        return self._view(*load(s, flow.flow_id))

    # --- grindar och manuella steg -----------------------------------------------------------------

    def decide_gate(
        self,
        flow_id: str,
        *,
        expected_version: int,
        actor: Actor,
        decision: Literal["approved", "rejected"],
        seen_hash: str,
        note: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> FlowView:
        """Operatörens grindbeslut, bundet till hashen av underlaget hen såg.

        `details`: uppgifterna ett godkännande bär enligt grindens `decision_model`. De sparas
        i grindens resultat; ett avslag bär inga uppgifter.
        """
        self._require_human(actor, "Grindbeslut")
        if decision not in ("approved", "rejected"):
            raise FlowError("Beslutet är approved eller rejected")
        if decision == "rejected" and not (note or "").strip():
            raise FlowError("Ett avslag kräver en anteckning")
        with self._session_factory() as s:
            flow, steps, decisions = load(s, flow_id)
            self._check_version(flow, expected_version)
            if flow.status != "waiting_gate":
                raise FlowError(f"Flödet {flow_id} väntar inte på ett grindbeslut ({flow.status})")
            gate = self._definition(flow.flow_type).step(flow.current_step)
            assert isinstance(gate, GateStep)
            self._check_gates_fresh(flow, steps, decisions)
            current = bound_hash({st.step_key: st for st in steps}, gate.binds)
            if current is None:
                raise FlowError(f"Grinden '{gate.key}' saknar färdigt underlag")
            if seen_hash != current:
                raise FlowConflictError(
                    f"Underlaget för grinden '{gate.key}' har ändrats sedan det visades – granska det igen"
                )
            decided = None
            if decision == "approved":
                decided = self._gate_details(gate, self._context(flow, steps), details)
            s.add(FlowGateDecision(
                flow_id=flow_id, step_key=gate.key, decision=decision, decided_by=actor.id,
                note=(note or "").strip() or None, bound_steps=list(gate.binds), bound_hash=current,
            ))
            row = self._row(steps, gate.key)
            row.finished_at = self._now()
            if decision == "rejected":
                row.status = "rejected"
                row.completed_by = actor.id
                row.result = {"decision": decision, "bound_hash": current, "note": note}
                bump(s, flow, expected_version, status="rejected", finished_at=self._now(),
                     note=f"Grinden '{gate.key}' avslogs av {actor.id}")
            else:
                result = {"decision": decision, "bound_hash": current, "note": note}
                if decided is not None:
                    result["details"] = decided
                self._complete(row, result, completed_by=actor.id)
                self._advance(s, flow, gate.key, expected_version)
        return self.get(flow_id)

    @staticmethod
    def _gate_details(gate: GateStep, ctx: FlowContext, details: dict[str, Any] | None) -> dict[str, Any] | None:
        """Godkännandets uppgifter, validerade mot grindens modell och prövade mot tidigare resultat."""
        validated = None
        if gate.decision_model is None:
            if details:
                raise FlowError(f"Grinden '{gate.key}' tar inga uppgifter med beslutet")
        else:
            try:
                validated = gate.decision_model.model_validate(details or {})
            except ValidationError as exc:
                raise FlowError(f"Ogiltiga uppgifter i beslutet för grinden '{gate.key}': {exc}") from exc
        if gate.check is not None:
            gate.check(ctx, validated)
        return validated.model_dump(mode="json") if validated is not None else None

    def complete_manual(self, flow_id: str, *, expected_version: int, actor: Actor, data: dict[str, Any]) -> FlowView:
        """Operatören markerar ett manuellt steg klart med stegets uppgifter (t.ex. commit-referens)."""
        self._require_human(actor, "Ett manuellt steg")
        with self._session_factory() as s:
            flow, steps, decisions = load(s, flow_id)
            self._check_version(flow, expected_version)
            if flow.status != "waiting_manual":
                raise FlowError(f"Flödet {flow_id} väntar inte på ett manuellt steg ({flow.status})")
            step = self._definition(flow.flow_type).step(flow.current_step)
            assert isinstance(step, ManualStep)
            self._check_gates_fresh(flow, steps, decisions)
            try:
                validated = step.input_model.model_validate(data)
            except ValidationError as exc:
                raise FlowError(f"Ogiltiga uppgifter för steget '{step.key}': {exc}") from exc
            row = self._row(steps, step.key)
            row.started_at = row.started_at or self._now()
            row.finished_at = self._now()
            self._complete(row, validated.model_dump(mode="json"), completed_by=actor.id)
            self._advance(s, flow, step.key, expected_version)
        return self.get(flow_id)

    # --- avbrott och avstämning -------------------------------------------------------------------

    def cancel(self, flow_id: str, *, expected_version: int, actor: Actor, note: str) -> FlowView:
        self._require_human(actor, "Att avbryta ett flöde")
        if not note.strip():
            raise FlowError("Ett avbrott kräver en anteckning")
        with self._session_factory() as s:
            flow, steps, _ = load(s, flow_id)
            self._check_version(flow, expected_version)
            if flow.status in FINISHED_FLOW_STATUSES:
                raise FlowError(f"Flödet {flow_id} är redan {flow.status}")
            if any(st.status == "running" for st in steps):
                raise FlowError("Ett steg körs – vänta tills det är klart eller stäm av det först")
            for st in steps:
                if st.status in ("pending", "waiting", "reconciliation_required"):
                    st.status = "skipped"
            bump(s, flow, expected_version, status="cancelled", finished_at=self._now(),
                 note=f"Avbrutet av {actor.id}: {note.strip()}")
        return self.get(flow_id)

    def mark_interrupted(self) -> list[str]:
        """Steg som står som `running` när motorn startar blir `reconciliation_required`.

        Anropas när ingen körning pågår (t.ex. när UI:t startar). Inget körs om automatiskt.
        """
        marked = []
        with self._session_factory() as s:
            for row in s.scalars(select(FlowStep).where(FlowStep.status == "running")):
                flow = s.get(Flow, row.flow_id)
                row.status = "reconciliation_required"
                row.error = "Steget pågick när motorn startade om – utfallet är okänt"
                bump(s, flow, flow.version, status="reconciliation_required")
                marked.append(row.flow_id)
        return marked

    def resolve_reconciliation(
        self, flow_id: str, *, expected_version: int, actor: Actor, retry: bool, note: str
    ) -> FlowView:
        """Operatörens avstämning: kör steget igen (`retry`) eller avsluta flödet som misslyckat."""
        self._require_human(actor, "Avstämning")
        if not note.strip():
            raise FlowError("Avstämningen kräver en anteckning om vad som kontrollerats")
        with self._session_factory() as s:
            flow, steps, _ = load(s, flow_id)
            self._check_version(flow, expected_version)
            if flow.status != "reconciliation_required":
                raise FlowError(f"Flödet {flow_id} behöver ingen avstämning ({flow.status})")
            row = self._row(steps, flow.current_step)
            row.error = f"{row.error or ''} Avstämt av {actor.id}: {note.strip()}".strip()
            if retry:
                row.status, row.started_at, row.run_id = "pending", None, None
                bump(s, flow, expected_version, status="running")
            else:
                row.status, row.finished_at = "failed", self._now()
                bump(s, flow, expected_version, status="failed", finished_at=self._now(),
                     note=f"Avstämt av {actor.id} som misslyckat: {note.strip()}")
        return self.get(flow_id)

    # --- interna hjälpare -----------------------------------------------------------------------------

    def _interrupted(self, flow_id: str, step_key: str, version: int, error: str) -> FlowView:
        with self._session_factory() as s:
            flow, steps, _ = load(s, flow_id)
            row = self._row(steps, step_key)
            row.status = "reconciliation_required"
            row.error = f"Körningen avbröts oväntat ({error}) – stäm av körjournalen och kön"
            bump(s, flow, version, status="reconciliation_required")
        return self.get(flow_id)

    def _complete(self, row: FlowStep, result: dict[str, Any], *, completed_by: str | None) -> None:
        row.status = "completed"
        row.result = result
        row.result_hash = canonical_hash(result)
        row.completed_by = completed_by

    def _advance(self, s, flow: Flow, done_key: str, version: int) -> int:
        nxt = self._definition(flow.flow_type).after(done_key)
        if nxt is None:
            return bump(s, flow, version, status="completed", current_step=None, finished_at=self._now())
        return bump(s, flow, version, status=STATUS_FOR_KIND[nxt.kind], current_step=nxt.key)

    def _check_gates_fresh(self, flow: Flow, steps: list[FlowStep], decisions: list[FlowGateDecision]) -> None:
        stale = _stale_gates(steps, decisions)
        if stale:
            raise FlowError(
                f"Underlaget för grind {', '.join(stale)} har ändrats efter beslutet – flödet stannar; "
                "starta ett nytt flöde"
            )

    def _context(self, flow: Flow, steps: list[FlowStep]) -> FlowContext:
        return FlowContext(
            flow_id=flow.flow_id, input=dict(flow.input),
            results={st.step_key: st.result for st in steps if st.status == "completed" and st.result is not None},
            run_ids={st.step_key: st.run_id for st in steps if st.run_id},
        )

    def _definition(self, flow_type: str) -> FlowDefinition:
        try:
            return self.definitions[flow_type]
        except KeyError:
            raise FlowError(f"Okänd flödestyp '{flow_type}'") from None

    def _runtime(self) -> AgentRuntime:
        if self.runtime is None:
            raise FlowError("Motorn saknar AgentRuntime – agentsteg kan inte köras")
        return self.runtime

    def _trusted(self) -> ServiceLayer:
        if self.trusted is None:
            raise FlowError("Motorn saknar det betrodda tjänstelagret")
        return self.trusted

    @staticmethod
    def _row(steps: list[FlowStep], key: str) -> FlowStep:
        for st in steps:
            if st.step_key == key:
                return st
        raise FlowError(f"Steget '{key}' finns inte i flödet")

    @staticmethod
    def _check_version(flow: Flow, expected: int) -> None:
        if flow.version != expected:
            raise FlowConflictError(
                f"Flödet {flow.flow_id} är version {flow.version}, inte {expected} – läs om flödet och försök igen"
            )

    @staticmethod
    def _require_operator(actor: Actor) -> None:
        if actor.is_agent:
            raise FlowError("Flödets steg tas av operatören eller betrodd systemkod, inte av en agent")

    @staticmethod
    def _require_human(actor: Actor, what: str) -> None:
        if actor.type != "human":
            raise FlowError(f"{what} görs av en människa")

    def _view(self, flow: Flow, steps: list[FlowStep], decisions: list[FlowGateDecision]) -> FlowView:
        definition = self.definitions.get(flow.flow_type)
        by_key = {st.step_key: st for st in steps}
        gate_hashes = {}
        if definition is not None:
            for step in definition.steps:
                if isinstance(step, GateStep):
                    gate_hashes[step.key] = bound_hash(by_key, step.binds)
        return FlowView(
            flow_id=flow.flow_id, flow_type=flow.flow_type, definition_version=flow.definition_version,
            status=flow.status, version=flow.version, current_step=flow.current_step, input=dict(flow.input),
            created_by=flow.created_by, created_at=flow.created_at, finished_at=flow.finished_at, note=flow.note,
            steps=tuple(_step_view(st) for st in steps),
            decisions=tuple(
                GateDecisionView(d.step_key, d.decision, d.decided_by, d.note, tuple(d.bound_steps), d.bound_hash,
                                 d.created_at)
                for d in decisions
            ),
            gate_hashes=gate_hashes,
            stale_gates=tuple(_stale_gates(steps, decisions)),
        )


def _stale_gates(steps: list[FlowStep], decisions: list[FlowGateDecision]) -> list[str]:
    """Godkända grindar vars bundna underlag inte längre har samma hash."""
    by_key = {st.step_key: st for st in steps}
    return sorted({
        d.step_key for d in decisions
        if d.decision == "approved" and bound_hash(by_key, d.bound_steps) != d.bound_hash
    })


def _step_view(st: FlowStep) -> StepView:
    return StepView(
        key=st.step_key, position=st.position, kind=st.kind, title=st.title, status=st.status, team=st.team,
        agent=st.agent, run_id=st.run_id, result=st.result, result_hash=st.result_hash, approval_id=st.approval_id,
        artifact_refs=tuple(st.artifact_refs or ()), started_at=st.started_at, finished_at=st.finished_at,
        completed_by=st.completed_by, error=st.error,
    )


__all__ = [
    "AgentRuntime",
    "FlowConflictError",
    "FlowEngine",
    "FlowError",
    "FlowView",
    "GateDecisionView",
    "Step",
    "StepView",
]
