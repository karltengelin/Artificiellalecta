"""Skill-kontrakt och skill-register (Fas 3b-2, harness.md §4.1, agentekosystem.md §5.2).

En skill mot försäkringssystemet är ett tunt omslag runt en operation i
tjänstelagret. Omslaget tillför bara poddtillhörighet, verktygsschema och
resultatprojektion. Namn på operation, sidoeffekt, produktregler, PII och
agentnivå kommer från operationen själv – de kopieras aldrig hit.

Modellens verktygsschema är ett genererat omslag:

    {"data": <operationens indatamodell>, "reason": <kort motivering>}

Aktör, run-id, ärende, session och godkännare ingår aldrig i schemat. De sätts
av betrodd kod i OperationContext. Okända fält nekas här, även på nivåer där
operationens egen Pydantic-modell skulle ignorera dem.

Anropet går alltid via `ServiceLayer.execute` – aldrig direkt till `op.func` –
så att åtkomstregistret, regelgolven, godkännandekön och händelseloggen gäller
exakt som för handläggar-UI:t.

En skill kan också vara ett omslag runt ett gatewayverktyg (`GatewaySkill`, 3c-T):
läsning av regeldokument och utkast i körningens arbetsyta (harness.md §5.2). Samma
omslag och samma strikta prövning av argumenten; gatewayen nekar själv otillåten
användning, och team och run-id kommer från betrodd kontext.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from agents.ecosystem import Ecosystem
from agents.errors import HarnessError, SkillDeniedError, SkillInputError
from agents.gateways.tools import GATEWAY_TOOLS, GatewayContext, GatewayTool
from ai import ToolSpec
from ai.schema import strict_json_schema
from services import (
    Operation,
    OperationContext,
    OperationKind,
    OperationRegistry,
    OperationResult,
    ServiceLayer,
)

PROPOSE_NOTE = (
    " Du kan bara föreslå den här ändringen: förslaget läggs i handläggarens godkännandekö "
    "och ingenting ändras förrän en handläggare har godkänt det."
)
PENDING_NOTE = "Förslaget ligger i handläggarens godkännandekö. Ingenting är ändrat ännu."


@dataclass(frozen=True)
class ServiceSkill:
    """En skill som anropar en operation i tjänstelagret."""

    name: str
    pod: str
    operation: Operation
    action_model: type[BaseModel]

    source = "service"

    @classmethod
    def wrap(cls, name: str, pod: str, op: Operation) -> ServiceSkill:
        return cls(name=name, pod=pod, operation=op, action_model=_action_model(name, op.input_model, op.kind))

    @property
    def target(self) -> str:
        """Operationen i tjänstelagret som skillen anropar."""
        return self.operation.name

    @property
    def kind(self) -> OperationKind:
        return self.operation.kind

    @property
    def pii(self) -> bool:
        return self.operation.pii

    def tool_spec(self, *, proposes: bool = False) -> ToolSpec:
        """Verktyget som modellen ser. `proposes` när tjänstelagret ger agenten nivån APPROVAL."""
        description = self.operation.description + (PROPOSE_NOTE if proposes else "")
        return ToolSpec.from_model(self.name, description, self.action_model)

    def parse(self, arguments: dict[str, Any]) -> BaseModel:
        """Validerar modellens argument mot omslaget. Okända fält på alla nivåer nekas."""
        return _parse(self.name, self.action_model, arguments)

    def invoke(
        self, service: ServiceLayer, ctx: OperationContext, arguments: dict[str, Any]
    ) -> OperationResult:
        """Validerar och kör operationen som agenten i `ctx`.

        Förutsätter att dispatchern redan har prövat skillen mot agentens profil
        (EffectiveProfile.require) – tjänstelagret prövar dessutom själv nivå och golv.
        """
        return self.execute(service, ctx, self.parse(arguments))

    def execute(self, service: ServiceLayer, ctx: OperationContext, action: BaseModel) -> OperationResult:
        """Kör ett redan validerat anrop (från `parse`) som agenten i `ctx`."""
        if not ctx.actor.is_agent:
            raise HarnessError(
                "Skills anropas bara för agenter – handläggare och skript använder tjänstelagret direkt"
            )
        return service.execute(self.operation.name, replace(ctx, reason=action.reason), action.data)

    @staticmethod
    def result_payload(result: OperationResult) -> dict[str, Any]:
        """Det modellen får tillbaka – utfört med utdata, eller väntande med approval-id."""
        if result.pending:
            return {"status": "pending_approval", "approval_id": result.approval_id, "note": PENDING_NOTE}
        output = result.output.model_dump(mode="json") if result.output is not None else None
        return {"status": "done", "output": output}


@dataclass(frozen=True)
class GatewaySkill:
    """En skill som anropar ett gatewayverktyg (regelverk, dokument) – utanför tjänstelagret."""

    name: str
    pod: str
    tool: GatewayTool
    action_model: type[BaseModel]

    source = "gateway"
    pii = False  # gatewayerna i 3c-G är utan personuppgifter; ecosystem.yaml prövar mot verktyget

    @classmethod
    def wrap(cls, name: str, pod: str, tool: GatewayTool) -> GatewaySkill:
        kind = OperationKind(tool.side_effect)
        return cls(name=name, pod=pod, tool=tool, action_model=_action_model(name, tool.input_model, kind))

    @property
    def target(self) -> str:
        return self.tool.name

    @property
    def kind(self) -> OperationKind:
        return OperationKind(self.tool.side_effect)

    def tool_spec(self, *, proposes: bool = False) -> ToolSpec:
        return ToolSpec.from_model(self.name, self.tool.description, self.action_model)

    def parse(self, arguments: dict[str, Any]) -> BaseModel:
        return _parse(self.name, self.action_model, arguments)

    def execute(self, ctx: GatewayContext, action: BaseModel) -> BaseModel:
        """Kör ett validerat anrop. GatewayError går vidare till dispatchern."""
        return self.tool.call(ctx, action.data)

    @staticmethod
    def result_payload(output: BaseModel) -> dict[str, Any]:
        return {"status": "done", "output": output.model_dump(mode="json")}


Skill = ServiceSkill | GatewaySkill


class SkillRegistry:
    """Alla skills som körpolicyn mappar, byggda mot tjänstelagrets operationsregister.

    Ingen jokerteckenmappning: en ny operation blir en skill först när den har en
    rad i en podd i ecosystem.yaml (och en rad i åtkomstregistret för att bli öppen).
    """

    def __init__(self, skills: dict[str, Skill]) -> None:
        self._skills = dict(skills)

    @classmethod
    def build(cls, ecosystem: Ecosystem, registry: OperationRegistry) -> SkillRegistry:
        ecosystem.validate_against_registry(registry)
        skills = {}
        for pod_name, pod in ecosystem.pods.items():
            for skill, entry in pod.skills.items():
                if entry.gateway_tool is not None:
                    skills[skill] = GatewaySkill.wrap(skill, pod_name, GATEWAY_TOOLS[entry.gateway_tool])
                else:
                    skills[skill] = ServiceSkill.wrap(skill, pod_name, registry.get(entry.service_operation))
        return cls(skills)

    def get(self, name: str) -> Skill:
        try:
            return self._skills[name]
        except KeyError:
            raise SkillDeniedError(f"Okänd skill: '{name}'", skill=name, reasons=("finns inte",)) from None

    def names(self) -> list[str]:
        return sorted(self._skills)

    def __contains__(self, name: str) -> bool:
        return name in self._skills

    def __iter__(self) -> Iterator[Skill]:
        return iter(self._skills[name] for name in self.names())

    def __len__(self) -> int:
        return len(self._skills)


def _parse(name: str, action_model: type[BaseModel], arguments: dict[str, Any]) -> BaseModel:
    if not isinstance(arguments, dict):
        raise SkillInputError(f"'{name}': argumenten ska vara ett objekt")
    schema = strict_json_schema(action_model)
    unknown = _unknown_fields(arguments, schema, schema.get("$defs", {}), "")
    if unknown:
        raise SkillInputError(f"'{name}': okända fält {', '.join(unknown)}", security=True)
    try:
        return action_model.model_validate(arguments)
    except ValidationError as exc:
        raise SkillInputError(f"'{name}': ogiltiga argument: {exc}") from exc


def _action_model(name: str, input_model: type[BaseModel], kind: OperationKind) -> type[BaseModel]:
    """Omslaget {data, reason}. Motivering krävs när operationen ändrar data."""
    if kind.changes_state:
        reason: Any = (str, Field(min_length=1, description="Kort motivering till ändringen"))
    else:
        reason = (str | None, Field(default=None, description="Valfri kort motivering"))
    title = "".join(part.capitalize() for part in name.split("_")) + "Action"
    return create_model(
        title,
        __config__=ConfigDict(extra="forbid"),
        # Ingen description bredvid $ref – OpenAI:s strikta läge godtar inga syskonnyckelord
        data=(input_model, ...),
        reason=reason,
    )


def _unknown_fields(value: Any, schema: dict[str, Any], defs: dict[str, Any], path: str) -> list[str]:
    """Fält i `value` som schemat inte känner till (schemat är strikt, se ai.schema)."""
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        return _unknown_fields(value, defs.get(ref.removeprefix("#/$defs/"), {}), defs, path)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            results = [_unknown_fields(value, branch, defs, path) for branch in schema[key]]
            return [] if any(not r for r in results) else results[0]
    unknown: list[str] = []
    for branch in schema.get("allOf", ()):
        unknown += _unknown_fields(value, branch, defs, path)
    if isinstance(value, dict) and "properties" in schema:
        props = schema["properties"]
        for key, item in value.items():
            where = f"{path}.{key}" if path else str(key)
            if key not in props:
                unknown.append(where)
            else:
                unknown += _unknown_fields(item, props[key], defs, where)
    elif isinstance(value, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value):
            unknown += _unknown_fields(item, schema["items"], defs, f"{path}[{i}]")
    return unknown
