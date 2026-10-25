"""Harness – motorn som gör en modell till en agent (Fas 3b, B-026). Design: 02_system/harness.md.

Byggt hittills:
  - körpolicyn `ecosystem.yaml` med strikt validering (3b-1)
  - uppdrag och resultat: RunRequest, RunResult (3b-1)
  - skill-kontrakt och skill-register runt tjänstelagrets operationer (3b-2)
  - effektiv profil med förklaringar och versionsbild (3b-1/3b-2)
  - dispatcher som prövar varje anrop, och resursmandat för personuppgifter (3b-3)
  - agentloopen med kontextbygge, tak och stopp (3b-4)
  - länkad fortsättning efter godkännande (3b-5) och körjournal i JSONL (3b-6)
  - körning i ett ärende: mandat ur ärendet, uppdragsmall och status efteråt (Fas 5 F5-3)
  - teamen compliance och aktuarie: gatewayverktyg som skills, parametermandat,
    resultatscheman med bevis och uppdragsmallar för flaggskeppet (Fas 3c 3c-T)

    from agents import Dispatcher, Ecosystem, SkillRegistry, compile_profile
    from services import ServiceLayer, default_registry
    eco = Ecosystem.load()
    profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), ServiceLayer(),
                              agent_id="case_handler")
    print(profile.explain())
"""

from agents.assignments import (
    mandate_from_interpretation,
    request_for_impact,
    request_for_interpretation,
    run_assignment,
)
from agents.case_runs import CaseRun, record_run_status, request_for_case, run_case
from agents.continuation import Continuation, ContinuationNotReady, prepare_continuation
from agents.dispatcher import CallOutcome, CallStatus, Dispatcher, DispatchOutcome
from agents.ecosystem import Ecosystem, Limits
from agents.errors import (
    EcosystemConfigError,
    HarnessError,
    RunRequestError,
    ScopeError,
    SkillDeniedError,
    SkillInputError,
)
from agents.gateways import Gateways
from agents.journal import FileJournal, JournalError, MemoryJournal, read_journal
from agents.loop import RunOutcome, build_context, run_agent
from agents.profile import (
    EffectiveProfile,
    Outcome,
    SkillDecision,
    VersionSnapshot,
    compile_profile,
)
from agents.results import (
    RESULT_SCHEMAS,
    InterpretationProposal,
    PortfolioImpactResult,
    ProposedParameterChange,
    ResultError,
)
from agents.run import RunRequest, RunResult, RunStatus
from agents.scope import (
    ExecutionScope,
    ParameterChangeMandate,
    case_and_scope,
    scope_for_case,
    scope_for_person,
)
from agents.skills import GatewaySkill, ServiceSkill, SkillRegistry

__all__ = [
    "RESULT_SCHEMAS",
    "CallOutcome",
    "CallStatus",
    "CaseRun",
    "Continuation",
    "ContinuationNotReady",
    "DispatchOutcome",
    "Dispatcher",
    "Ecosystem",
    "EcosystemConfigError",
    "EffectiveProfile",
    "ExecutionScope",
    "FileJournal",
    "GatewaySkill",
    "Gateways",
    "HarnessError",
    "InterpretationProposal",
    "JournalError",
    "Limits",
    "MemoryJournal",
    "Outcome",
    "ParameterChangeMandate",
    "PortfolioImpactResult",
    "ProposedParameterChange",
    "ResultError",
    "RunOutcome",
    "RunRequest",
    "RunRequestError",
    "RunResult",
    "RunStatus",
    "ScopeError",
    "ServiceSkill",
    "SkillDecision",
    "SkillDeniedError",
    "SkillInputError",
    "SkillRegistry",
    "VersionSnapshot",
    "build_context",
    "mandate_from_interpretation",
    "case_and_scope",
    "compile_profile",
    "prepare_continuation",
    "read_journal",
    "record_run_status",
    "request_for_case",
    "request_for_impact",
    "request_for_interpretation",
    "run_assignment",
    "run_agent",
    "run_case",
    "scope_for_case",
    "scope_for_person",
]
