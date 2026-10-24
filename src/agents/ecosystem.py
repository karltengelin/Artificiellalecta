"""Körpolicyn för agentekosystemet: ecosystem.yaml (Fas 3b-1, harness.md §3).

    from agents import Ecosystem
    eco = Ecosystem.load()          # validerar mot tjänstelagret, AI-lagret och instruktionerna
    eco.agent_limits("case_handler")

Filen är den enda källan för team, agenter, skill-poddar, nekanden och gränser.
Agentnivån för försäkringsoperationer (AGENT/APPROVAL/HUMAN_ONLY) står inte här
utan i tjänstelagrets åtkomstregister – policyn kan bara stänga, aldrig öppna.

Valideringen är strikt: okända fält, dubbla YAML-nycklar, okända poddar,
operationer och team, en agent med fler poddar eller sidoeffekter än sitt team,
och gränser över teamets eller de globala taken stoppar laddningen.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError

from agents.errors import EcosystemConfigError
from services.contract import OPERATION_NAME_PATTERN, OperationKind, OperationRegistry

DEFAULT_ECOSYSTEM_PATH = Path(__file__).with_name("ecosystem.yaml")
REPO_ROOT = Path(__file__).resolve().parents[2]
INSTRUCTION_DIR = Path("02_system/agenter")

#: Team-, podd- och agent-id: engelska snake_case (B-015), samma form som verktygsnamn.
ID_PATTERN = OPERATION_NAME_PATTERN

# Raden "| **Team** | Försäkring & kund (`forsakring`) – …" i agentens instruktion.
_TEAM_ROW = re.compile(r"^\|\s*\*\*Team\*\*\s*\|[^|\n]*\(`([a-z0-9_]+)`\)", re.MULTILINE)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Limits(_Strict):
    """Tak för en körning (harness.md §6.3). Ett fält som saknas ärvs från nivån ovanför."""

    max_steps: int | None = Field(default=None, gt=0)
    max_tool_calls: int | None = Field(default=None, gt=0)
    max_cost_usd: float | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    max_context_bytes: int | None = Field(default=None, gt=0)
    max_wall_seconds: int | None = Field(default=None, gt=0)

    def missing(self) -> list[str]:
        return [name for name in type(self).model_fields if getattr(self, name) is None]

    def exceeding(self, ceiling: Limits) -> list[str]:
        """Fält där den här nivån försöker gå över taket ovanför."""
        out = []
        for name in type(self).model_fields:
            own, top = getattr(self, name), getattr(ceiling, name)
            if own is not None and top is not None and own > top:
                out.append(f"{name} {own} > {top}")
        return out

    def narrowed(self, other: Limits) -> Limits:
        """Det strängaste av två nivåer, fält för fält – en lägre nivå kan bara sänka."""
        values = {}
        for name in type(self).model_fields:
            own, low = getattr(self, name), getattr(other, name)
            values[name] = own if low is None else low if own is None else min(own, low)
        return Limits(**values)


class Defaults(_Strict):
    deny_skills: tuple[str, ...] = ()
    allowed_effects: frozenset[OperationKind]
    require_execution_scope_for_pii: bool = True
    limits: Limits


class SkillEntry(_Strict):
    """En skill i en podd. I Fas 3b finns bara omslag runt tjänstelagrets operationer."""

    service_operation: str


class Pod(_Strict):
    owner_team: str
    mountable_by: tuple[str, ...]
    pii: bool
    allowed_effects: frozenset[OperationKind]
    skills: dict[str, SkillEntry] = Field(min_length=1)


class Team(_Strict):
    lead: str
    mandate: str = Field(min_length=1)
    pods: tuple[str, ...]
    allowed_effects: frozenset[OperationKind]
    deny_skills: tuple[str, ...] = ()
    delegates_to: tuple[str, ...] = ()
    limits: Limits = Limits()


class Agent(_Strict):
    name: str = Field(min_length=1)  # svenskt visningsnamn
    team: str
    instruction: str  # sökväg från repo-roten, under 02_system/agenter/
    model_role: str
    pods: tuple[str, ...]
    allowed_effects: frozenset[OperationKind]
    deny_skills: tuple[str, ...] = ()
    delegates_to: tuple[str, ...] = ()
    limits: Limits = Limits()


class Delegation(_Strict):
    """Delegering mellan team (Fas 3c). Valideras redan nu men används inte förrän den aktiveras."""

    enabled: bool = False
    max_depth: int = Field(gt=0)
    max_children: int = Field(ge=0)
    root_limits: Limits


class Ecosystem(_Strict):
    schema_version: Literal[1]
    policy_id: str = Field(min_length=1)
    team_ids: tuple[str, ...]
    defaults: Defaults
    pods: dict[str, Pod]
    teams: dict[str, Team]
    agents: dict[str, Agent]
    delegation: Delegation

    _source: Path | None = PrivateAttr(default=None)
    _checksum: str | None = PrivateAttr(default=None)

    # --- laddning ------------------------------------------------------------

    @classmethod
    def load(
        cls,
        path: Path | None = None,
        *,
        registry: OperationRegistry | None = None,
        roles: Iterable[str] | None = None,
        repo_root: Path | None = None,
    ) -> Ecosystem:
        """Läser och validerar policyn helt – mot tjänstelagrets register, AI-lagrets roller
        och agenternas instruktionsfiler. Standard: de riktiga registren i repot."""
        path = path or DEFAULT_ECOSYSTEM_PATH
        if not path.exists():
            raise EcosystemConfigError(f"Körpolicyn hittades inte: {path}")
        raw = path.read_bytes()
        eco = cls.from_yaml(raw.decode("utf-8"))
        eco._source = path
        eco._checksum = hashlib.sha256(raw).hexdigest()

        if registry is None:
            from services import default_registry  # registrerar operationerna

            registry = default_registry
        if roles is None:
            from ai import load_config

            roles = load_config().roles
        eco.validate_against_registry(registry)
        eco.validate_model_roles(roles)
        eco.validate_instructions(repo_root or REPO_ROOT)
        return eco

    @classmethod
    def from_yaml(cls, text: str) -> Ecosystem:
        try:
            data = yaml.load(text, Loader=_UniqueKeyLoader) or {}
        except yaml.YAMLError as exc:
            raise EcosystemConfigError(f"Körpolicyn är inte giltig YAML: {exc}") from exc
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> Ecosystem:
        """Validerar struktur och inre samband. Register, roller och filer prövas i load()."""
        try:
            eco = cls.model_validate(data)
        except ValidationError as exc:
            raise EcosystemConfigError(f"Ogiltig körpolicy: {exc}") from exc
        eco._validate_structure()
        return eco

    @property
    def checksum(self) -> str | None:
        """sha256 av filen som lästes – följer med i körningens versionsbild."""
        return self._checksum

    @property
    def source(self) -> Path | None:
        return self._source

    # --- uppslag -------------------------------------------------------------

    def pod_of(self, skill: str) -> str | None:
        for pod_name, pod in self.pods.items():
            if skill in pod.skills:
                return pod_name
        return None

    def skill_names(self) -> list[str]:
        return sorted(skill for pod in self.pods.values() for skill in pod.skills)

    def agent(self, agent_id: str) -> Agent:
        try:
            return self.agents[agent_id]
        except KeyError:
            raise EcosystemConfigError(f"Okänd agent: '{agent_id}'") from None

    def agent_limits(self, agent_id: str) -> Limits:
        """Globala tak, sänkta av teamet och sedan agenten."""
        agent = self.agent(agent_id)
        return self.defaults.limits.narrowed(self.teams[agent.team].limits).narrowed(agent.limits)

    # --- validering ------------------------------------------------------------

    def _validate_structure(self) -> None:
        errors: list[str] = []
        team_ids = set(self.team_ids)

        def check_ids(kind: str, names: Iterable[str]) -> None:
            for name in names:
                if not ID_PATTERN.match(name):
                    errors.append(f"{kind}-id '{name}' ska vara engelska snake_case, max 64 tecken")

        check_ids("Team", self.team_ids)
        check_ids("Podd", self.pods)
        check_ids("Agent", self.agents)
        if len(team_ids) != len(self.team_ids):
            errors.append("team_ids innehåller dubbletter")

        # external körs aldrig direkt av en agent (B-026 §5.3) – Fas 3b har ingen kanalgateway
        for where, effects in self._effect_sets():
            if OperationKind.EXTERNAL in effects:
                errors.append(f"{where}: external kan inte öppnas i körpolicyn (harness.md §4.3)")

        if missing := self.defaults.limits.missing():
            errors.append(f"defaults.limits saknar {', '.join(missing)}")
        if missing := self.delegation.root_limits.missing():
            # max_output_tokens och max_context_bytes gäller per agent, inte per rot
            missing = [m for m in missing if m not in ("max_output_tokens", "max_context_bytes")]
            if missing:
                errors.append(f"delegation.root_limits saknar {', '.join(missing)}")

        seen_skills: dict[str, str] = {}
        for pod_name, pod in self.pods.items():
            check_ids(f"Skill i podden '{pod_name}'", pod.skills)
            if pod.owner_team not in team_ids:
                errors.append(f"Podden '{pod_name}': okänt ägarteam '{pod.owner_team}'")
            for team in pod.mountable_by:
                if team not in team_ids:
                    errors.append(f"Podden '{pod_name}': okänt team '{team}' i mountable_by")
            for skill in pod.skills:
                if skill in seen_skills:
                    errors.append(
                        f"Skillen '{skill}' finns i både '{seen_skills[skill]}' och '{pod_name}' "
                        "– en skill hör till exakt en podd"
                    )
                seen_skills[skill] = pod_name

        operations: dict[str, str] = {}
        for pod_name, pod in self.pods.items():
            for skill, entry in pod.skills.items():
                if entry.service_operation in operations:
                    errors.append(
                        f"Operationen '{entry.service_operation}' är mappad två gånger "
                        f"('{operations[entry.service_operation]}' och '{skill}')"
                    )
                operations[entry.service_operation] = skill

        def check_denied(where: str, names: Iterable[str]) -> None:
            for name in names:
                if name not in seen_skills:
                    errors.append(f"{where}: nekar okänd skill '{name}' (stavfel?)")

        check_denied("defaults", self.defaults.deny_skills)

        for team_name, team in self.teams.items():
            where = f"Teamet '{team_name}'"
            if team_name not in team_ids:
                errors.append(f"{where} finns inte i team_ids")
            for pod_name in team.pods:
                pod = self.pods.get(pod_name)
                if pod is None:
                    errors.append(f"{where}: okänd podd '{pod_name}'")
                elif team_name not in pod.mountable_by:
                    errors.append(f"{where}: podden '{pod_name}' får inte monteras på teamet")
            for target in team.delegates_to:
                if target not in team_ids or target == team_name:
                    errors.append(f"{where}: ogiltigt delegeringsmål '{target}'")
            check_denied(where, team.deny_skills)
            if over := team.limits.exceeding(self.defaults.limits):
                errors.append(f"{where}: gränser över de globala taken ({'; '.join(over)})")
            lead = self.agents.get(team.lead)
            if lead is None:
                errors.append(f"{where}: ledande agent '{team.lead}' finns inte")
            elif lead.team != team_name:
                errors.append(f"{where}: ledande agent '{team.lead}' tillhör teamet '{lead.team}'")

        for agent_id, agent in self.agents.items():
            where = f"Agenten '{agent_id}'"
            team = self.teams.get(agent.team)
            if team is None:
                errors.append(f"{where}: teamet '{agent.team}' har ingen aktiv profil under teams")
                continue
            # En agent får en delmängd av teamets rättigheter – aldrig en union (harness.md §3.1)
            if extra := sorted(set(agent.pods) - set(team.pods)):
                errors.append(f"{where}: poddar utöver teamets: {', '.join(extra)}")
            if extra := sorted(e.value for e in agent.allowed_effects - team.allowed_effects):
                errors.append(f"{where}: sidoeffekter utöver teamets: {', '.join(extra)}")
            if extra := sorted(set(agent.delegates_to) - set(team.delegates_to)):
                errors.append(f"{where}: delegeringsmål utöver teamets: {', '.join(extra)}")
            check_denied(where, agent.deny_skills)
            team_limits = self.defaults.limits.narrowed(team.limits)
            if over := agent.limits.exceeding(team_limits):
                errors.append(f"{where}: gränser över teamets ({'; '.join(over)})")

        if errors:
            raise EcosystemConfigError("Ogiltig körpolicy:\n  - " + "\n  - ".join(errors))

    def _effect_sets(self) -> Iterable[tuple[str, frozenset[OperationKind]]]:
        yield "defaults", self.defaults.allowed_effects
        for name, pod in self.pods.items():
            yield f"Podden '{name}'", pod.allowed_effects
        for name, team in self.teams.items():
            yield f"Teamet '{name}'", team.allowed_effects
        for name, agent in self.agents.items():
            yield f"Agenten '{name}'", agent.allowed_effects

    def validate_against_registry(self, registry: OperationRegistry) -> None:
        """Varje mappning pekar på en verklig operation med förenlig sidoeffekt och PII.

        Ett omslag får aldrig klassa ned operationen: en PII-operation i en podd utan PII,
        eller en skrivning i en podd som bara får läsa, stoppar profilen.
        """
        errors: list[str] = []
        for pod_name, pod in self.pods.items():
            for skill, entry in pod.skills.items():
                if entry.service_operation not in registry:
                    errors.append(
                        f"'{pod_name}.{skill}': operationen '{entry.service_operation}' finns inte"
                    )
                    continue
                op = registry.get(entry.service_operation)
                if op.kind not in pod.allowed_effects:
                    errors.append(
                        f"'{pod_name}.{skill}': operationen är {op.kind.value}, podden tillåter "
                        f"{', '.join(sorted(e.value for e in pod.allowed_effects))}"
                    )
                if op.pii and not pod.pii:
                    errors.append(f"'{pod_name}.{skill}': operationen har personuppgifter, podden är utan PII")
        if errors:
            raise EcosystemConfigError("Körpolicyn stämmer inte med tjänstelagret:\n  - " + "\n  - ".join(errors))

    def unmapped_operations(self, registry: OperationRegistry) -> list[str]:
        """Operationer som ingen podd mappar – de är stängda för alla agenter."""
        mapped = {entry.service_operation for pod in self.pods.values() for entry in pod.skills.values()}
        return [name for name in registry.names() if name not in mapped]

    def validate_model_roles(self, roles: Iterable[str]) -> None:
        roles = set(roles)
        bad = [f"'{a}': {agent.model_role}" for a, agent in self.agents.items() if agent.model_role not in roles]
        if bad:
            raise EcosystemConfigError(
                f"Okänd modellroll ({', '.join(bad)}) – roller i AI-lagret: {', '.join(sorted(roles))}"
            )

    def validate_instructions(self, repo_root: Path) -> None:
        """Instruktionen finns under 02_system/agenter/ och anger samma team som policyn."""
        errors: list[str] = []
        base = (repo_root / INSTRUCTION_DIR).resolve()
        for agent_id, agent in self.agents.items():
            path = (repo_root / agent.instruction).resolve()
            if base not in path.parents:
                errors.append(f"'{agent_id}': instruktionen ska ligga i {INSTRUCTION_DIR.as_posix()}/")
                continue
            if not path.is_file():
                errors.append(f"'{agent_id}': instruktionen {agent.instruction} finns inte")
                continue
            match = _TEAM_ROW.search(path.read_text(encoding="utf-8"))
            if match is None:
                errors.append(f"'{agent_id}': instruktionen saknar raden **Team** med team-id")
            elif match.group(1) != agent.team:
                errors.append(
                    f"'{agent_id}': instruktionen anger teamet '{match.group(1)}', policyn '{agent.team}'"
                )
        if errors:
            raise EcosystemConfigError("Agentinstruktionerna stämmer inte:\n  - " + "\n  - ".join(errors))


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader som stoppar dubbla nycklar – PyYAML skriver annars tyst över den första."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    keys = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in keys:
            raise yaml.constructor.ConstructorError(
                None, None, f"dubbel nyckel '{key}'", key_node.start_mark
            )
        keys.add(key)
    return loader.construct_mapping(node, deep=deep)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)
