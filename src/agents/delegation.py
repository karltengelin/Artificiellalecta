"""Delegering mellan team (Fas 3c 3c-1, B-039, harness.md §10.1–10.2, agentekosystem.md §6.1).

En ledande agent kan mitt i sin körning ge ett annat team ett avgränsat uppdrag med
verktyget `delegate_to_team`. Harness kör då mottagarteamets ledande agent som en
**barnkörning** och lämnar tillbaka dess strukturerade svar som verktygsresultat.

    runtime = DelegationRuntime(ai, eco, skills, service, team_services={"aktuarie": aktuarie_service})
    outcome = run_assignment(ai, eco, skills, service, request, delegation=runtime)

Regler (B-039):
- **Egen identitet.** Barnet kör som mottagarens ledande agent med egen profil, egna poddar,
  eget tjänstelager (teamets databasroll) och egen modellroll. Det ärver ingenting av föräldern.
- **Inga nya mandat.** Barnet får inget resursmandat och inget parametermandat i första
  leveransen; modellen kan aldrig skapa ett. Mandatkrävande verktyg är därför dolda för barnet.
- **Referenser är pekare.** De prövas mot ett format och får inte likna personuppgifter.
  Barnet läser dem bara om dess egna verktyg tillåter det.
- **Gemensam rotbudget.** Barnets tak är mottagarprofilens, avsmalnat av vad som återstår av
  körpolicyns `delegation.root_limits`. Barnets förbrukning bokförs i rotens budgetbok,
  inte i förälderns egna tak. Djup, antal barn och cykler prövas före start.
- **Idempotens.** Samma beställning (samma innehåll) i samma rot ger samma svar utan ny körning.
- **Spridd väntan.** Ett barn som slutar `waiting_approval`, `needs_human` eller
  `reconciliation_required` stoppar föräldern med samma status. Ingen modell står och väntar.
- **Synkront.** Barnet körs inom förälderns verktygsanrop. Ett oväntat fel i barnet ger
  `reconciliation_required`; ingenting körs om automatiskt.

Händelserna `delegation_requested`, `delegation_denied`, `delegation_started` och
`delegation_returned` skrivs i förälderns körjournal; barnet har sin egen journal med
`parent_run_id` och `root_run_id`.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from agents.dispatcher import DelegationOutcome
from agents.ecosystem import Ecosystem, Limits
from agents.errors import EcosystemConfigError, HarnessError, RunRequestError
from agents.gateways import Gateways
from agents.journal import Journal, digest, mask, text_ref
from agents.profile import compile_profile
from agents.results import RESULT_SCHEMAS
from agents.run import DelegationInput, RunRequest, RunResult, RunStatus
from agents.skills import SkillRegistry
from ai import AIClient
from services import ServiceLayer

#: Läggs alltid till barnets begränsningar – betrodd text, inte modellens
TRUSTED_CONSTRAINTS = (
    "Inga kundpersonuppgifter",
    "Svaret går till det beställande teamet: ange underlag, antaganden och osäkerheter",
)
MAX_CONSTRAINT_LENGTH = 300

#: Handtag och id:n – inga mellanslag, ingen sökväg uppåt
REFERENCE_PATTERN = re.compile(r"^[0-9A-Za-zÅÄÖåäö][0-9A-Za-zÅÄÖåäö._:\-]{0,79}$")
#: Personnummer eller samordningsnummer, med eller utan sekel och skiljetecken
PERSONAL_NUMBER = re.compile(r"(?<!\d)(?:19|20)?\d{6}[-+ ]?\d{4}(?!\d)")

#: Barnets slutstatus som stoppar föräldern med samma status (B-039 val I)
STOPPING = frozenset({RunStatus.WAITING_APPROVAL, RunStatus.NEEDS_HUMAN, RunStatus.RECONCILIATION_REQUIRED})

#: Tak som förbrukas över hela roten, och motsvarande förbrukningsnyckel
CUMULATIVE = {"max_steps": "steps", "max_tool_calls": "tool_calls", "max_cost_usd": "cost_usd",
              "max_wall_seconds": "elapsed_seconds"}


class DelegationDenied(HarnessError):
    """Beställningen prövades och nekades innan något barn startade.

    `security` = säkerhetsgräns (otillåtet mål, cykel, djup, personuppgifter) – föräldern blockeras.
    Annars ett vanligt nej (antal barn, budget, okänt schema) som modellen kan ta hänsyn till.
    """

    def __init__(self, message: str, *, security: bool, kind: str) -> None:
        super().__init__(message)
        self.security = security
        self.kind = kind


@dataclass(frozen=True)
class DelegationRuntime:
    """Det barnkörningar behöver: AI-lagret, körpolicyn, skills och teamens tjänstelager.

    `team_services` ger varje team sitt eget tjänstelager (teamets databasroll, harness.md §5.1);
    team som saknas där kör med `service`. `journal_factory` används i tester för journaler i minnet.
    """

    ai: AIClient
    ecosystem: Ecosystem
    skills: SkillRegistry
    service: ServiceLayer
    team_services: dict[str, ServiceLayer] = field(default_factory=dict)
    gateways: Gateways | None = None
    journal_dir: Path | None = None
    journal_factory: Callable[..., Journal] | None = None

    def service_for(self, team: str) -> ServiceLayer:
        return self.team_services.get(team, self.service)


@dataclass
class RootLedger:
    """Budgetbok för en rot: förbrukning före segmentet, barnens förbrukning och antal barn."""

    limits: Limits
    base: dict[str, float] = field(default_factory=dict)  # tidigare segment (fortsättning), per förbrukningsnyckel
    children: dict[str, float] = field(default_factory=lambda: dict.fromkeys(CUMULATIVE.values(), 0.0))
    started: int = 0
    by_request: dict[str, DelegationOutcome] = field(default_factory=dict)

    def usage(self, parent: dict[str, float]) -> dict[str, float]:
        """Rotens samlade förbrukning: tidigare segment, förälderns segment och alla barn."""
        return {key: round(self.base.get(key, 0) + parent.get(key, 0) + self.children[key], 6)
                for key in CUMULATIVE.values()}

    def remaining(self, parent: dict[str, float]) -> dict[str, float]:
        used = self.usage(parent)
        return {limit: getattr(self.limits, limit) - used[key] for limit, key in CUMULATIVE.items()}

    def exhausted(self, parent: dict[str, float]) -> str | None:
        for limit, left in self.remaining(parent).items():
            if left <= 0:
                return f"rotbudgeten för delegeringen är förbrukad ({limit} {getattr(self.limits, limit)})"
        return None

    def charge(self, usage: dict[str, float]) -> None:
        for key in self.children:
            self.children[key] = round(self.children[key] + usage.get(key, 0), 6)


class Delegator:
    """Prövar och kör förälderns beställningar. En per körning; budgetboken delas inom roten."""

    def __init__(
        self,
        runtime: DelegationRuntime,
        ledger: RootLedger,
        *,
        parent_request: RunRequest,
        parent_run_id: str,
        parent_team: str,
        targets: tuple[str, ...],
        parent_usage: Callable[[], dict[str, float]],
        pause: Callable[[float], None],
        observe: Callable[..., Any],
        chain: tuple[str, ...] = (),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.runtime = runtime
        self.ledger = ledger
        self.parent_request = parent_request
        self.parent_run_id = parent_run_id
        self.parent_team = parent_team
        self.targets = targets
        self.chain = (*chain, parent_team)  # aktiva team i kedjan – inget får förekomma två gånger
        self._parent_usage = parent_usage
        self._pause = pause
        self._observe = observe
        self._clock = clock

    @property
    def root_run_id(self) -> str:
        return self.parent_request.root_run_id or self.parent_run_id

    def root_usage(self) -> dict[str, float]:
        return self.ledger.usage(self._parent_usage())

    def exhausted(self) -> str | None:
        """Skäl att inte göra fler modellanrop i föräldern – rotbudgeten är slut."""
        return self.ledger.exhausted(self._parent_usage())

    def delegate(self, call_id: str, data: DelegationInput) -> DelegationOutcome:
        task_id = f"del-{self.parent_run_id}-{call_id}"
        request_hash = digest(data.model_dump(mode="json"))
        self._observe(
            "delegation_requested", tool_call_id=call_id, task_id=task_id, target_team=data.target_team,
            request_hash=request_hash, goal=text_ref(data.goal), reference_count=len(data.references),
        )
        previous = self.ledger.by_request.get(request_hash)
        if previous is not None:
            self._observe("delegation_returned", task_id=previous.task_id, child_run_id=previous.child_run_id,
                          status=previous.child_status, reused=True, root_usage=self.root_usage())
            return replace(previous, reused=True)

        try:
            self._check(data)
            limits = self._child_limits(data.target_team)
            request = self._child_request(task_id, data, limits)
            service = self.runtime.service_for(data.target_team)
            profile = compile_profile(self.runtime.ecosystem, self.runtime.skills, service, request=request)
        except DelegationDenied as exc:
            return self._denied(task_id, exc)
        except (RunRequestError, EcosystemConfigError) as exc:
            return self._denied(task_id, DelegationDenied(str(exc), security=True, kind="profile"))

        child_run_id = f"run-{uuid.uuid4().hex[:12]}"
        self.ledger.started += 1
        self._observe("delegation_started", task_id=task_id, child_run_id=child_run_id,
                      target_team=data.target_team, agent=profile.agent_id, depth=request.depth,
                      limits=limits.model_dump(exclude_none=True))
        started = self._clock()
        try:
            outcome = self._run_child(profile, service, request, child_run_id)
            usage = {"steps": outcome.steps, "tool_calls": outcome.tool_calls,
                     "cost_usd": outcome.result.cost_usd, "elapsed_seconds": outcome.elapsed_seconds}
            result = outcome.result
        except Exception as exc:  # noqa: BLE001 – barnets utfall är okänt; inget körs om
            # Okänd förbrukning räknas inte som noll: hela reservationen står kvar (harness.md §6.3)
            usage = {key: getattr(limits, limit) for limit, key in CUMULATIVE.items()}
            result = RunResult(
                task_id=task_id, run_id=child_run_id, status=RunStatus.RECONCILIATION_REQUIRED,
                summary="Det delegerade uppdraget avbröts oväntat – stäm av innan fortsatt arbete.",
                uncertainties=(f"{type(exc).__name__}",),
            )
        finally:
            self._pause(self._clock() - started)
        self.ledger.charge(usage)
        self._observe("delegation_returned", task_id=task_id, child_run_id=child_run_id,
                      status=result.status.value, usage=usage, root_usage=self.root_usage(), reused=False)
        delegated = _outcome(task_id, data.target_team, result)
        self.ledger.by_request[request_hash] = delegated
        return delegated

    # --- prövning ----------------------------------------------------------------

    def _check(self, data: DelegationInput) -> None:
        eco = self.runtime.ecosystem
        target = data.target_team
        if not eco.delegation.enabled:
            raise DelegationDenied("Delegering är avstängd i körpolicyn", security=True, kind="disabled")
        if target not in self.targets:
            raise DelegationDenied(
                f"'{target}' är inte ett tillåtet delegeringsmål i uppdraget "
                f"(tillåtna: {', '.join(self.targets) or 'inga'})", security=True, kind="target",
            )
        if target in self.chain:
            raise DelegationDenied(f"Teamet '{target}' finns redan i kedjan – cykel", security=True, kind="cycle")
        if self.parent_request.depth + 1 > eco.delegation.max_depth:
            raise DelegationDenied(f"Djupgränsen {eco.delegation.max_depth} nås", security=True, kind="depth")
        texts = [data.goal, data.background, *data.constraints, data.expected_output or "", *data.references]
        if any(PERSONAL_NUMBER.search(text) for text in texts):
            raise DelegationDenied("Uppdraget ser ut att innehålla ett personnummer", security=True, kind="pii")
        if bad := [r for r in data.references if not REFERENCE_PATTERN.match(r)]:
            raise DelegationDenied(
                f"Ogiltiga referenser: {', '.join(mask(r) for r in bad)} – ange handtag och id:n",
                security=True, kind="reference",
            )
        if any(len(c) > MAX_CONSTRAINT_LENGTH for c in data.constraints):
            raise DelegationDenied(
                f"En begränsning är längre än {MAX_CONSTRAINT_LENGTH} tecken", security=False, kind="input"
            )
        if data.result_schema is not None and data.result_schema not in RESULT_SCHEMAS:
            raise DelegationDenied(
                f"Okänt resultatschema '{data.result_schema}' (kända: {', '.join(RESULT_SCHEMAS)})",
                security=False, kind="input",
            )
        if self.ledger.started >= eco.delegation.max_children:
            raise DelegationDenied(
                f"Högst {eco.delegation.max_children} delegerade uppdrag per rot", security=False, kind="children"
            )

    def _child_limits(self, target: str) -> Limits:
        """Mottagarprofilens tak, avsmalnat av vad som återstår av rotbudgeten (B-039 val F)."""
        eco = self.runtime.ecosystem
        agent_limits = eco.agent_limits(eco.teams[target].lead)
        remaining = self.ledger.remaining(self._parent_usage())
        if any(left <= 0 or (limit != "max_cost_usd" and left < 1) for limit, left in remaining.items()):
            raise DelegationDenied("Rotbudgeten räcker inte till ett delegerat uppdrag", security=False, kind="budget")
        left = {limit: int(value) if limit != "max_cost_usd" else round(value, 6) for limit, value in remaining.items()}
        return agent_limits.narrowed(Limits(**left))

    def _child_request(self, task_id: str, data: DelegationInput, limits: Limits) -> RunRequest:
        parent = self.parent_request
        return RunRequest(
            task_id=task_id,
            target_team=data.target_team,
            goal=data.goal,
            background=data.background,
            constraints=(*TRUSTED_CONSTRAINTS, f"Uppdraget är beställt av teamet {self.parent_team}",
                         *data.constraints),
            expected_output=data.expected_output,
            result_schema=data.result_schema,
            references=tuple(data.references),
            root_run_id=self.root_run_id,
            parent_run_id=self.parent_run_id,
            flow_id=parent.flow_id,
            flow_step_id=parent.flow_step_id,
            depth=parent.depth + 1,
            limits=limits,
            # Inga mandat och inga egna delegeringsmål för barnet i första leveransen (B-039 val B, C)
        )

    def _run_child(self, profile, service: ServiceLayer, request: RunRequest, run_id: str):
        from agents.loop import run_agent  # loopen importerar dispatchern, som definierar kontraktet

        journal = None
        if self.runtime.journal_factory is not None:
            journal = self.runtime.journal_factory(
                run_id=run_id, team=profile.team, agent=profile.agent_id, root_run_id=request.root_run_id,
                parent_run_id=request.parent_run_id,
            )
        return run_agent(
            self.runtime.ai, profile, service, request, gateways=self.runtime.gateways, run_id=run_id,
            journal=journal, journal_dir=self.runtime.journal_dir,
        )

    def _denied(self, task_id: str, exc: DelegationDenied) -> DelegationOutcome:
        self._observe("delegation_denied", task_id=task_id, kind=exc.kind, security=exc.security,
                      reasons=[mask(str(exc))])
        return DelegationOutcome(
            task_id=task_id, call_status="denied" if exc.security else "error",
            payload={"status": "denied" if exc.security else "error", "message": str(exc)},
            reasons=(str(exc),), error_type=None if exc.security else f"Delegation:{exc.kind}",
        )


def _outcome(task_id: str, target: str, result: RunResult) -> DelegationOutcome:
    """Barnets resultat som verktygssvar till föräldern (B-039 val G) – aldrig en beslutstoken."""
    view = {
        "task_id": task_id, "team": target, "run_id": result.run_id, "status": result.status.value,
        "summary": result.summary, "output": result.output, "assumptions": list(result.assumptions),
        "uncertainties": list(result.uncertainties), "evidence_refs": list(result.evidence_refs),
        "pending_approvals": list(result.pending_approvals), "cost_usd": result.cost_usd,
    }
    common = {"task_id": task_id, "child_run_id": result.run_id, "child_status": result.status.value,
              "pending_approvals": result.pending_approvals}
    if result.status == RunStatus.COMPLETED:
        return DelegationOutcome(call_status="done", payload={"status": "done", "output": view}, **common)
    if result.status in STOPPING:
        message = f"Teamet {target} slutade som {result.status.value} – körningen stannar här."
        return DelegationOutcome(call_status="stopped", stop=result.status,
                                 payload={"status": result.status.value, "message": message, "output": view},
                                 reasons=(message,), **common)
    message = f"Teamet {target} avslutade utan färdigt svar ({result.status.value})."
    return DelegationOutcome(call_status="error", payload={"status": "error", "message": message, "output": view},
                             reasons=(message,), error_type=f"Delegation:{result.status.value}", **common)
