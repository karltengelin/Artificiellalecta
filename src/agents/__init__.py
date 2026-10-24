"""Harness – motorn som gör en modell till en agent (Fas 3b, B-026). Design: 02_system/harness.md.

Byggt hittills:
  - körpolicyn `ecosystem.yaml` med strikt validering (3b-1)
  - uppdrag och resultat: RunRequest, RunResult (3b-1)
  - skill-kontrakt och skill-register runt tjänstelagrets operationer (3b-2)
  - effektiv profil med förklaringar och versionsbild (3b-1/3b-2)
  - dispatcher som prövar varje anrop, och resursmandat för personuppgifter (3b-3)
  - agentloopen med kontextbygge, tak och stopp (3b-4)
Godkännandets fortsättning och körjournalen kommer i 3b-5–3b-6.

    from agents import Dispatcher, Ecosystem, SkillRegistry, compile_profile
    from services import ServiceLayer, default_registry
    eco = Ecosystem.load()
    profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), ServiceLayer(),
                              agent_id="case_handler")
    print(profile.explain())
"""

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
from agents.loop import RunOutcome, build_context, run_agent
from agents.profile import (
    EffectiveProfile,
    Outcome,
    SkillDecision,
    VersionSnapshot,
    compile_profile,
)
from agents.run import RunRequest, RunResult, RunStatus
from agents.scope import ExecutionScope, scope_for_person
from agents.skills import ServiceSkill, SkillRegistry

__all__ = [
    "CallOutcome",
    "CallStatus",
    "DispatchOutcome",
    "Dispatcher",
    "Ecosystem",
    "EcosystemConfigError",
    "EffectiveProfile",
    "ExecutionScope",
    "HarnessError",
    "Limits",
    "Outcome",
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
    "compile_profile",
    "run_agent",
    "scope_for_person",
]
