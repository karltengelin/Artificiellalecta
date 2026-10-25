"""Flödesdefinitioner som kod (Fas 3c 3c-2, flaggskeppsflöde.md §6, harness.md §10.3).

En definition bestämmer ordningen, vad varje steg gör och vilka resultat en grind binder.
Modellen bestämmer aldrig nästa steg. Fyra slags steg:

- `AgentStep`: ett team kör ett uppdrag genom harness. Uppdraget byggs av betrodd kod ur
  flödets indata och tidigare resultat; ett parametermandat kan byggas på samma sätt.
- `GateStep`: operatören godkänner eller avslår. Beslutet binder hashen av de angivna
  stegens resultat; ändras ett av dem blir grinden inaktuell. Ett godkännande kan bära
  uppgifter enligt grindens `decision_model` (t.ex. regelns version och giltighet), och
  `check` prövar godkännandet mot tidigare resultat innan beslutet sparas (3c-3).
- `ManualStep`: operatören gör något utanför systemet (t.ex. för in regeltext) och
  markerar det klart med uppgifter enligt stegets modell, t.ex. en commit-referens.
- `SystemStep`: betrodd kod, t.ex. att lägga ett förslag i tjänstelagrets godkännandekö
  eller verifiera resultatet. Ett förslag i kön låter steget vänta tills det är avgjort;
  grinden ersätter aldrig godkännandet av en APPROVAL-operation (harness.md §4.2).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from agents.errors import HarnessError
from agents.run import RunRequest
from agents.scope import ParameterChangeMandate
from services.contract import OPERATION_NAME_PATTERN


@dataclass(frozen=True)
class FlowContext:
    """Det betrodd kod ser när ett steg byggs: flödets indata och tidigare stegs resultat."""

    flow_id: str
    input: Mapping[str, Any]
    results: Mapping[str, Mapping[str, Any]]
    run_ids: Mapping[str, str] = field(default_factory=dict)

    def result(self, step_key: str) -> Mapping[str, Any]:
        try:
            return self.results[step_key]
        except KeyError:
            raise HarnessError(f"Steget '{step_key}' har inget resultat ännu") from None


@dataclass(frozen=True)
class AgentStep:
    key: str
    title: str
    team: str
    request: Callable[[FlowContext], RunRequest]
    mandate: Callable[[FlowContext], ParameterChangeMandate] | None = None
    kind = "agent"


@dataclass(frozen=True)
class GateStep:
    key: str
    title: str
    binds: tuple[str, ...]
    decision_model: type[BaseModel] | None = None  # uppgifter ett godkännande bär
    # prövar ett godkännande mot tidigare resultat (uppgifterna, eller None utan modell); FlowError stoppar
    check: Callable[[FlowContext, BaseModel | None], None] | None = None
    kind = "gate"


@dataclass(frozen=True)
class ManualStep:
    key: str
    title: str
    input_model: type[BaseModel]
    kind = "manual"


@dataclass(frozen=True)
class SystemOutcome:
    """Resultatet av ett systemsteg. Med `approval_id` väntar steget på godkännandekön."""

    result: dict[str, Any]
    approval_id: str | None = None


@dataclass(frozen=True)
class SystemStep:
    key: str
    title: str
    run: Callable[[FlowContext, Any], SystemOutcome]  # (kontext, motorns tjänster) -> utfall
    kind = "system"


Step = AgentStep | GateStep | ManualStep | SystemStep


@dataclass(frozen=True)
class FlowDefinition:
    flow_type: str
    version: str
    title: str
    input_model: type[BaseModel]
    steps: tuple[Step, ...]

    def __post_init__(self) -> None:
        errors: list[str] = []
        if not OPERATION_NAME_PATTERN.match(self.flow_type):
            errors.append(f"flödestypen '{self.flow_type}' ska vara engelska snake_case")
        if not self.steps:
            errors.append("en definition har minst ett steg")
        seen: list[str] = []
        for step in self.steps:
            if not OPERATION_NAME_PATTERN.match(step.key):
                errors.append(f"stegnyckeln '{step.key}' ska vara engelska snake_case")
            if step.key in seen:
                errors.append(f"stegnyckeln '{step.key}' finns två gånger")
            if isinstance(step, GateStep):
                if not step.binds:
                    errors.append(f"grinden '{step.key}' binder inget resultat")
                for bound in step.binds:
                    earlier = next((s for s in self.steps[: len(seen)] if s.key == bound), None)
                    if earlier is None:
                        errors.append(f"grinden '{step.key}' binder '{bound}', som inte är ett tidigare steg")
                    elif isinstance(earlier, GateStep):
                        errors.append(f"grinden '{step.key}' binder grinden '{bound}' – bind stegens resultat")
            seen.append(step.key)
        if errors:
            raise HarnessError(f"Ogiltig flödesdefinition '{self.flow_type}': " + "; ".join(errors))

    def step(self, key: str) -> Step:
        for step in self.steps:
            if step.key == key:
                return step
        raise HarnessError(f"Flödet '{self.flow_type}' har inget steg '{key}'")

    def after(self, key: str) -> Step | None:
        keys = [s.key for s in self.steps]
        index = keys.index(key) + 1
        return self.steps[index] if index < len(self.steps) else None
