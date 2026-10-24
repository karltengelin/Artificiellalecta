"""Fortsättning efter godkännande (Fas 3b-5, harness.md §6.4, §7 steg 8).

En körning som väntar på godkännande slutar som `waiting_approval` – ingen modell
står och väntar. När handläggaren har avgjort förslagen startar operatören en
**länkad fortsättning**: ett nytt segment med eget run-id och `continuation_of`.

    events, corrupt = read_journal(path)
    cont = prepare_continuation(request, events, trusted_service, skills, corrupt=corrupt)
    profile = compile_profile(eco, skills, agent_service, request=cont.request)
    run_agent(ai, profile, agent_service, cont.request, scope=scope, continuation=cont)

Regler:
- Förslagens utfall läses via den betrodda anslutningen (agentrollen får inte läsa kön).
  Så länge något förslag väntar startar ingen fortsättning.
- Den avgjorda operationen anropas aldrig igen: ett godkännande har redan verkställts av
  tjänstelagret, och ett avslag följs inte av ett likadant förslag. Fortsättningen nekar
  därför skillen för varje avgjord operation.
- Budgeten nollställs inte. Taken är rotkörningens, minus det som alla tidigare segment
  förbrukat (modellsteg, verktygsanrop, kostnad och aktiv tid).
- Rå konversationshistorik återanvänds inte: fortsättningen bygger ny kontext ur
  uppdraget och de avgjorda förslagen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.ecosystem import Limits
from agents.errors import HarnessError, RunRequestError
from agents.journal import JournalError
from agents.run import RunRequest, RunStatus
from agents.skills import SkillRegistry
from services import ServiceLayer

#: Tak som förbrukas över segmenten. Utdata per anrop och kontextstorlek gäller per segment.
CUMULATIVE = ("max_steps", "max_tool_calls", "max_cost_usd", "max_wall_seconds")
_USAGE = {"max_steps": "steps", "max_tool_calls": "tool_calls", "max_cost_usd": "cost_usd",
          "max_wall_seconds": "elapsed_seconds"}


class ContinuationNotReady(HarnessError):
    """Något förslag väntar fortfarande på handläggaren."""


@dataclass(frozen=True)
class ApprovalObservation:
    approval_id: str
    operation: str
    status: str  # approved / rejected
    decided_by: str | None
    decided_at: str | None
    note: str | None


@dataclass(frozen=True)
class Continuation:
    request: RunRequest  # uppdraget med kvarvarande budget och nekade avgjorda operationer
    continuation_of: str
    root_run_id: str
    root_limits: Limits
    consumed: dict[str, float]  # förbrukat av alla tidigare segment
    observations: tuple[ApprovalObservation, ...]

    def note(self) -> str:
        """Text till fortsättningens första meddelande."""
        intro = (
            f"Detta är en fortsättning av körning {self.continuation_of}. Handläggaren har avgjort "
            "dina tidigare förslag. Gör inte om dem:"
        )
        lines = [intro]
        for o in self.observations:
            if o.status == "approved":
                lines.append(f"- {o.approval_id} ({o.operation}): godkänt av {o.decided_by} – ändringen är genomförd.")
            else:
                why = f": {o.note}" if o.note else ""
                lines.append(
                    f"- {o.approval_id} ({o.operation}): avslaget av {o.decided_by}{why}. "
                    "Föreslå inte samma sak igen utan nytt underlag."
                )
        return "\n".join(lines)


def prepare_continuation(
    request: RunRequest,
    previous: list[dict[str, Any]],
    trusted: ServiceLayer,
    skills: SkillRegistry,
    *,
    corrupt: bool = False,
) -> Continuation:
    """Prövar att den förra körningen kan fortsättas och bygger fortsättningens uppdrag."""
    if corrupt:
        raise JournalError("Den förra journalen har en skadad sista rad – stäm av innan fortsättning")
    started = _one(previous, "run_started")
    ended = _one(previous, "run_ended")
    if started.get("task_id") != request.task_id or started.get("team") != request.target_team:
        raise RunRequestError("Fortsättningen gäller inte samma uppdrag och team som den förra körningen")
    if ended.get("status") != RunStatus.WAITING_APPROVAL.value:
        raise RunRequestError(f"Den förra körningen slutade som {ended.get('status')!r}, inte waiting_approval")

    run_id = started["run_id"]
    observations = []
    for approval_id in ended.get("pending_approvals") or []:
        approval = trusted.approvals.get(approval_id)
        if approval is None:
            raise HarnessError(f"Förslaget {approval_id} finns inte i godkännandekön")
        if approval.run_id != run_id or approval.proposed_by != started.get("agent"):
            raise HarnessError(f"Förslaget {approval_id} hör inte till körningen {run_id}")
        if approval.status == "pending":
            raise ContinuationNotReady(f"Förslaget {approval_id} väntar fortfarande på handläggaren")
        observations.append(ApprovalObservation(
            approval_id=approval.id, operation=approval.operation, status=approval.status,
            decided_by=approval.decided_by, decided_at=approval.decided_at, note=approval.decision_note,
        ))
    if not observations:
        raise RunRequestError("Den förra körningen har inga förslag att fortsätta från")

    root_limits = Limits(**started["root_limits"])
    consumed = {key: ended["root_usage"][_USAGE[key]] for key in CUMULATIVE}
    remaining = {}
    for key in CUMULATIVE:
        left = getattr(root_limits, key) - consumed[key]
        if left <= 0:
            raise RunRequestError(f"Rotkörningens budget är förbrukad ({key})")
        remaining[key] = int(left) if isinstance(getattr(root_limits, key), int) else round(left, 6)
        if remaining[key] <= 0:
            raise RunRequestError(f"Rotkörningens budget är förbrukad ({key})")
    limits = Limits(**remaining).narrowed(request.limits)

    decided_ops = {o.operation for o in observations}
    denied = {s.name for s in skills if s.operation.name in decided_ops}
    cont_request = request.model_copy(update={
        "limits": limits,
        "deny_skills": tuple(sorted(set(request.deny_skills) | denied)),
        "root_run_id": started.get("root_run_id") or run_id,
        "continuation_of": run_id,
    })
    return Continuation(
        request=cont_request, continuation_of=run_id, root_run_id=cont_request.root_run_id,
        root_limits=root_limits, consumed=consumed, observations=tuple(observations),
    )


def _one(events: list[dict[str, Any]], type: str) -> dict[str, Any]:
    found = [e for e in events if e.get("type") == type]
    if len(found) != 1:
        raise JournalError(f"Den förra journalen har {len(found)} händelser av typen {type}, väntat 1")
    return found[0]
