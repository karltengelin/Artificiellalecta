"""Harness – motorn som gör en modell till en agent (Fas 3b, B-026). Design: 02_system/harness.md.

Byggt hittills:
  - körpolicyn `ecosystem.yaml` med strikt validering (3b-1)
  - uppdrag och resultat: RunRequest, RunResult (3b-1)
  - skill-kontrakt och skill-register runt tjänstelagrets operationer (3b-2)
  - effektiv profil med förklaringar och versionsbild (3b-1/3b-2)
Agentloop, dispatcher med resurskontroll, godkännandehantering och körjournal
kommer i 3b-3–3b-6.

    from agents import Ecosystem, SkillRegistry, compile_profile
    from services import ServiceLayer, default_registry
    eco = Ecosystem.load()
    profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), ServiceLayer(),
                              agent_id="case_handler")
    print(profile.explain())
"""

from agents.ecosystem import Ecosystem, Limits
from agents.errors import (
    EcosystemConfigError,
    HarnessError,
    RunRequestError,
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
from agents.skills import ServiceSkill, SkillRegistry

__all__ = [
    "Ecosystem",
    "EcosystemConfigError",
    "EffectiveProfile",
    "HarnessError",
    "Limits",
    "Outcome",
    "RunRequest",
    "RunRequestError",
    "RunResult",
    "RunStatus",
    "ServiceSkill",
    "SkillDecision",
    "SkillDeniedError",
    "SkillInputError",
    "SkillRegistry",
    "VersionSnapshot",
    "compile_profile",
]
