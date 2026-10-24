"""Effektiv profil: vilka verktyg en agent får i en körning, och varför (harness.md §3.1–3.5).

    from agents import Ecosystem, SkillRegistry, compile_profile
    from services import ServiceLayer, default_registry
    eco = Ecosystem.load()
    service = ServiceLayer()                       # ny vid varje körstart – regelstatus cachas
    profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), service, request=req)
    profile.tool_specs()                           # det modellen får se
    print(profile.explain())                       # även varför ett verktyg saknas

En skill är öppen bara om varje villkor håller – ett nej vinner alltid:
  1. podden är monterad på teamet och finns i agentens poddar
  2. skillen är inte nekad globalt, för teamet, agenten eller uppdraget
  3. sidoeffekten finns i snittet av defaults, podd, team, agent och uppdrag
  4. personuppgifter: uppdraget har execution_scope och PII-podden har sin databasroll
  5. tjänstelagrets effektiva nivå (register + golv) är inte HUMAN_ONLY
Nivån AGENT ger "utföra", APPROVAL ger "föreslå". Profilen listar samtliga skäl
när en skill är dold, inte bara det första.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from agents.ecosystem import REPO_ROOT, Ecosystem, Limits
from agents.errors import RunRequestError, SkillDeniedError
from agents.run import RunRequest
from agents.skills import ServiceSkill, SkillRegistry
from ai import ToolSpec
from services import AgentAccess, OperationKind, ServiceLayer

#: Resurskontrollen i kod finns (agents.scope, prövas av dispatchern). Men harness.md §5.1
#: kräver dessutom en egen, minimal databasroll och prov mot isolerad Postgres innan första
#: PII-podden aktiveras – det sätter operatören upp. Till dess visas inga PII-verktyg.
#: Ändras genom granskad commit, inte genom konfiguration.
PII_DATABASE_ROLE_READY = False


class Outcome(StrEnum):
    EXECUTE = "execute"  # agenten får utföra
    PROPOSE = "propose"  # agenten får föreslå – handläggaren godkänner
    HIDDEN = "hidden"  # verktyget visas inte och kan inte anropas


@dataclass(frozen=True)
class SkillDecision:
    skill: str
    pod: str
    operation: str
    kind: OperationKind
    pii: bool
    service_level: AgentAccess  # tjänstelagrets effektiva nivå vid kompileringen
    outcome: Outcome
    reasons: tuple[str, ...]  # varför dold (tomt när öppen)

    @property
    def visible(self) -> bool:
        return self.outcome != Outcome.HIDDEN


@dataclass(frozen=True)
class VersionSnapshot:
    """Kontrollsummor för det profilen bygger på – följer med körjournalen (3b-6)."""

    policy_id: str
    ecosystem_sha256: str | None
    access_register_sha256: str | None
    instruction_sha256: str
    product_rules_sha256: str
    rules_date: date


@dataclass(frozen=True)
class EffectiveProfile:
    agent_id: str
    agent_name: str
    team: str
    model_role: str
    instruction: str
    limits: Limits
    decisions: tuple[SkillDecision, ...]
    unmapped_operations: tuple[str, ...]  # operationer som ingen podd mappar – stängda
    execution_scope_ref: str | None  # uppdragets resursmandat – dispatchern kräver samma scope
    snapshot: VersionSnapshot
    _skills: SkillRegistry

    def visible(self) -> list[SkillDecision]:
        return [d for d in self.decisions if d.visible]

    def decision(self, skill: str) -> SkillDecision:
        for d in self.decisions:
            if d.skill == skill:
                return d
        raise SkillDeniedError(f"Okänd skill: '{skill}'", skill=skill, reasons=("finns inte",))

    def tool_specs(self) -> list[ToolSpec]:
        return [
            self._skills.get(d.skill).tool_spec(proposes=d.outcome == Outcome.PROPOSE)
            for d in self.visible()
        ]

    def require(self, skill: str) -> ServiceSkill:
        """Skillen om den är öppen i profilen – annars SkillDeniedError med alla skäl.

        Prövas vid varje anrop, även för ett namn modellen har hittat på eller ett
        verktyg den sett tidigare (harness.md §3.1).
        """
        d = self.decision(skill)
        if not d.visible:
            raise SkillDeniedError(
                f"Skillen '{skill}' är inte öppen för '{self.agent_id}': {'; '.join(d.reasons)}",
                skill=skill,
                reasons=d.reasons,
            )
        return self._skills.get(skill)

    def explain(self) -> str:
        """Läsbar sammanställning för operatören."""
        lim = self.limits
        lines = [
            f"Agent: {self.agent_id} ({self.agent_name}), team {self.team}, modellroll {self.model_role}",
            f"Instruktion: {self.instruction}",
            f"Policy: {self.snapshot.policy_id}, regelstatus per {self.snapshot.rules_date.isoformat()}",
            (
                f"Gränser: {lim.max_steps} modellsteg, {lim.max_tool_calls} verktygsanrop, "
                f"{lim.max_cost_usd:.2f} USD, {lim.max_output_tokens} utdatatokens per anrop, "
                f"{lim.max_context_bytes} byte kontext, {lim.max_wall_seconds} s aktiv tid"
            ),
            "",
            "Öppna verktyg:",
        ]
        visible = self.visible()
        if not visible:
            lines.append("  (inga)")
        for d in visible:
            verb = "utföra" if d.outcome == Outcome.EXECUTE else "föreslå (godkännande)"
            lines.append(f"  {d.skill:<30} {d.pod:<10} {d.kind.value:<8} {verb}")
        lines += ["", "Dolda verktyg:"]
        hidden = [d for d in self.decisions if not d.visible]
        if not hidden:
            lines.append("  (inga)")
        for d in hidden:
            lines.append(f"  {d.skill:<30} {d.pod:<10} {d.kind.value:<8} tjänstelagret: {d.service_level.value}")
            lines += [f"      - {reason}" for reason in d.reasons]
        lines += ["", "Operationer utan poddmappning (stängda för alla agenter):"]
        lines.append("  " + (", ".join(self.unmapped_operations) or "(inga)"))
        return "\n".join(lines)


def compile_profile(
    ecosystem: Ecosystem,
    skills: SkillRegistry,
    service: ServiceLayer,
    *,
    agent_id: str | None = None,
    request: RunRequest | None = None,
) -> EffectiveProfile:
    """Räknar fram agentens effektiva profil just nu.

    Med `request` gäller uppdragets skärpningar och teamets ytterdörr: uppdraget går
    till teamets ledande agent. Utan `request` visas profilen utan uppdrag – då finns
    inget execution_scope och inga PII-verktyg.

    Tjänstelagrets nivå läses färskt via `service.decision()`. Skapa en ny ServiceLayer
    (och därmed ProductRuleCatalog) vid körstart, så att regelstatus och datum är aktuella.
    """
    agent_id = _resolve_agent(ecosystem, agent_id, request)
    agent = ecosystem.agent(agent_id)
    team = ecosystem.teams[agent.team]
    limits = ecosystem.agent_limits(agent_id)

    run_denied: set[str] = set()
    run_effects: frozenset[OperationKind] | None = None
    if request is not None:
        if over := request.limits.exceeding(limits):
            raise RunRequestError(f"Uppdraget får bara sänka gränserna ({'; '.join(over)})")
        limits = limits.narrowed(request.limits)
        if unknown := sorted(set(request.deny_skills) - set(skills.names())):
            raise RunRequestError(f"Uppdraget nekar okända skills: {', '.join(unknown)}")
        run_denied = set(request.deny_skills)
        run_effects = request.allowed_effects

    has_scope = request is not None and request.execution_scope_ref is not None
    decisions = []
    for skill in skills:
        pod = ecosystem.pods[skill.pod]
        reasons: list[str] = []

        if skill.pod not in team.pods:
            reasons.append(f"podden '{skill.pod}' är inte monterad på teamet '{agent.team}'")
        elif skill.pod not in agent.pods:
            reasons.append(f"podden '{skill.pod}' finns inte i agentens poddar")

        for where, denied in (
            ("globalt", ecosystem.defaults.deny_skills),
            (f"för teamet '{agent.team}'", team.deny_skills),
            ("för agenten", agent.deny_skills),
            ("i uppdraget", run_denied),
        ):
            if skill.name in denied:
                reasons.append(f"nekad {where}")

        for where, effects in (
            ("globalt", ecosystem.defaults.allowed_effects),
            (f"i podden '{skill.pod}'", pod.allowed_effects),
            (f"för teamet '{agent.team}'", team.allowed_effects),
            ("för agenten", agent.allowed_effects),
            ("i uppdraget", run_effects),
        ):
            if effects is not None and skill.kind not in effects:
                reasons.append(f"sidoeffekten {skill.kind.value} är inte tillåten {where}")

        if skill.pii or pod.pii:
            if ecosystem.defaults.require_execution_scope_for_pii and not has_scope:
                reasons.append("personuppgifter kräver execution_scope i uppdraget")
            if not PII_DATABASE_ROLE_READY:
                reasons.append(
                    "personuppgifter: egen databasroll och Postgres-prov för PII-podden saknas (harness.md §5.1)"
                )

        decision = service.decision(skill.operation.name)
        if decision.effective == AgentAccess.HUMAN_ONLY:
            detail = "; ".join(decision.reasons) or "HUMAN_ONLY i åtkomstregistret"
            reasons.append(f"endast handläggare i tjänstelagret ({detail})")

        if reasons:
            outcome = Outcome.HIDDEN
        elif decision.effective == AgentAccess.APPROVAL:
            outcome = Outcome.PROPOSE
        else:
            outcome = Outcome.EXECUTE
        decisions.append(
            SkillDecision(
                skill=skill.name,
                pod=skill.pod,
                operation=skill.operation.name,
                kind=skill.kind,
                pii=skill.pii or pod.pii,
                service_level=decision.effective,
                outcome=outcome,
                reasons=tuple(reasons),
            )
        )

    return EffectiveProfile(
        agent_id=agent_id,
        agent_name=agent.name,
        team=agent.team,
        model_role=agent.model_role,
        instruction=agent.instruction,
        limits=limits,
        decisions=tuple(decisions),
        unmapped_operations=tuple(ecosystem.unmapped_operations(service.registry)),
        snapshot=_snapshot(ecosystem, agent.instruction, service),
        execution_scope_ref=request.execution_scope_ref if request is not None else None,
        _skills=skills,
    )


def _resolve_agent(ecosystem: Ecosystem, agent_id: str | None, request: RunRequest | None) -> str:
    if request is None:
        if agent_id is None:
            raise RunRequestError("Ange agent_id eller ett uppdrag")
        ecosystem.agent(agent_id)
        return agent_id
    team = ecosystem.teams.get(request.target_team)
    if team is None:
        raise RunRequestError(f"Teamet '{request.target_team}' har ingen aktiv profil")
    chosen = request.agent or team.lead
    if agent_id is not None and agent_id != chosen:
        raise RunRequestError(f"Uppdraget gäller '{chosen}', inte '{agent_id}'")
    if chosen != team.lead:
        # Teamets ytterdörr (B-026 §3.2): uppdrag går till ledande agent, som själv
        # beställer av specialister när delegering finns (Fas 3c)
        raise RunRequestError(
            f"Uppdrag till teamet '{request.target_team}' går till ledande agent '{team.lead}', inte '{chosen}'"
        )
    return chosen


def _snapshot(ecosystem: Ecosystem, instruction: str, service: ServiceLayer) -> VersionSnapshot:
    register_path = service.register.path
    return VersionSnapshot(
        policy_id=ecosystem.policy_id,
        ecosystem_sha256=ecosystem.checksum,
        access_register_sha256=_file_sha256(register_path) if register_path else None,
        instruction_sha256=_file_sha256(REPO_ROOT / instruction),
        product_rules_sha256=_dir_sha256(service.rules.rules_dir),
        rules_date=service.rules.today,
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dir_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()
