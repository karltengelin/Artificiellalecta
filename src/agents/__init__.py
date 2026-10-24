"""Harness – motorn som gör en modell till en agent (Fas 3b, B-026). Design: 02_system/harness.md.

Byggt hittills:
  - körpolicyn `ecosystem.yaml` med strikt validering (3b-1)
  - uppdrag och resultat: RunRequest, RunResult (3b-1)
  - skill-kontrakt och skill-register runt tjänstelagrets operationer (3b-2)
  - effektiv profil med förklaringar och versionsbild (3b-1/3b-2)
  - dispatcher som prövar varje anrop, och resursmandat för personuppgifter (3b-3)
Agentloop, godkännandehantering i loopen och körjournal kommer i 3b-4–3b-6.

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
    "compile_profile",
    "scope_for_person",
]
