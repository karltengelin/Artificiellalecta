"""Agentkörning i ett ärende (Fas 5 F5-3, B-033).

    run = run_case(ai, eco, skills, agent_service, trusted, "CASE-000001", assigned_by="karl")
    run.outcome.result.status      # t.ex. waiting_approval
    run.case_status                # ärendets status efter körningen

Ärendet är agentens arbetsenhet och mandat:
  1. Mandatet byggs ur ärendet av betrodd kod (`case_and_scope`): ärendets försäkrade,
     dess försäkringar, arbetsgivaren och 24 månader till och med ärendets månad.
  2. Uppdraget byggs ur en mall per ärendetyp – mål, begränsningar och förväntat resultat.
     Uppdragstexten innehåller ärendenumret, inga personuppgifter; agenten läser
     ärendets uppgifter med `get_case`.
  3. Körningen går genom samma loop, dispatcher och journal som alla agentkörningar.
     `RunRequest.case_id` och mandatets ärende måste stämma, och tjänstelagret stoppar
     anrop som gäller ett annat ärende.
  4. Efter körningen skriver harness ärendets status som systemaktör via den betrodda
     anslutningen: `waiting_approval` när ett förslag väntar, annars `in_progress`, och
     `last_run_id`. Modellen ändrar aldrig ärendets status och stänger aldrig ärenden.

`agent_service` är agentens tjänstelager (services.db.agent_service_layer, begränsad roll);
`trusted` är handläggarens/systemets (app_backend). Mandat och status går via `trusted`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from agents.ecosystem import Ecosystem, Limits
from agents.errors import HarnessError
from agents.journal import Journal
from agents.loop import RunOutcome, run_agent
from agents.profile import compile_profile
from agents.run import RunRequest, RunStatus
from agents.scope import ExecutionScope, case_and_scope
from agents.skills import SkillRegistry
from ai import AIClient
from services import Actor, OperationContext, ServiceLayer

#: Agentteamet som handlägger varje ärendetyp
CASE_TEAMS = {"salary_report": "forsakring"}


@dataclass(frozen=True)
class CaseTemplate:
    title: str
    goal: str
    constraints: tuple[str, ...]
    expected_output: str


TEMPLATES = {
    "salary_report": CaseTemplate(
        title="inrapporterat löneunderlag",
        goal=(
            "Kontrollera det inrapporterade löneunderlaget. Läs ärendet med get_case, den försäkrades översikt, "
            "tidigare löneunderlag och premiehistorik för månaden, och förhandsberäkna premien. Föreslå "
            "registrering med register_salary_report om underlaget är komplett och inte krockar med befintliga "
            "uppgifter; annars beskriv vad som saknas eller krockar."
        ),
        constraints=(
            "Arbeta bara i det här ärendet",
            "Ingen premierättelse och ingen kundkontakt",
            "Saknat löneunderlag är inte noll lön (PR-ITP1-014)",
        ),
        expected_output=(
            "Kort bedömning med underlag: vad som rapporterats, vad som redan finns, förhandsberäknad premie och "
            "förslag eller vad som saknas"
        ),
    ),
}


@dataclass(frozen=True)
class CaseRun:
    case_number: str
    request: RunRequest
    scope: ExecutionScope
    outcome: RunOutcome
    case_status: str


def request_for_case(
    case, scope: ExecutionScope, *, limits: Limits | None = None, task_id: str | None = None
) -> RunRequest:
    """Uppdraget ur ärendets typ. `case` är tjänstelagrets CaseView."""
    template = TEMPLATES.get(case.case_type)
    team = CASE_TEAMS.get(case.case_type)
    if template is None or team is None:
        raise HarnessError(f"Ingen agent handlägger ärendetypen {case.case_type!r}")
    if scope.case_id != case.case_number:
        raise HarnessError("Mandatet gäller ett annat ärende")
    return RunRequest(
        task_id=task_id or f"task-{case.case_number}-{uuid.uuid4().hex[:8]}",
        target_team=team,
        goal=f"Ärende {case.case_number} ({template.title}). {template.goal}",
        constraints=template.constraints,
        expected_output=template.expected_output,
        references=(case.case_number,),
        case_id=case.case_number,
        execution_scope_ref=scope.ref,
        limits=limits or Limits(),
    )


def record_run_status(trusted: ServiceLayer, case_number: str, outcome: RunOutcome) -> str:
    """Ärendets status efter körningen, skriven som systemaktör."""
    result = outcome.result
    status = "waiting_approval" if result.status == RunStatus.WAITING_APPROVAL else "in_progress"
    ctx = OperationContext(
        actor=Actor.system("harness"),
        reason=f"Agentkörning {result.run_id} slutade som {result.status.value}",
        run_id=result.run_id,
        case_id=case_number,
    )
    trusted.execute(
        "update_case_status", ctx, {"case_number": case_number, "status": status, "last_run_id": result.run_id}
    )
    return status


def run_case(
    ai: AIClient,
    ecosystem: Ecosystem,
    skills: SkillRegistry,
    agent_service: ServiceLayer,
    trusted: ServiceLayer,
    case_number: str,
    *,
    assigned_by: str,
    limits: Limits | None = None,
    run_id: str | None = None,
    journal: Journal | None = None,
    journal_dir: Path | None = None,
) -> CaseRun:
    """Kör handläggaragenten i ärendet och skriver ärendets status efteråt."""
    case, scope = case_and_scope(trusted, case_number, assigned_by=assigned_by)
    request = request_for_case(case, scope, limits=limits)
    profile = compile_profile(ecosystem, skills, agent_service, request=request)
    outcome = run_agent(
        ai, profile, agent_service, request, scope=scope, run_id=run_id, journal=journal, journal_dir=journal_dir
    )
    status = record_run_status(trusted, case_number, outcome)
    return CaseRun(case_number=case_number, request=request, scope=scope, outcome=outcome, case_status=status)
