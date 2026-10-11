"""Operationskontraktet: hur en operation i tjänstelagret deklareras (tjänstelager.md §3).

    @operation(
        name="register_salary_change",
        description="Registrerar ny pensionsmedförande månadslön från ett visst datum.",
        kind=OperationKind.WRITE,
        rules=["PR-ITP1-001"],
        pii=True,
    )
    def register_salary_change(ctx: OperationContext, data: SalaryChange) -> SalaryChangeResult:
        ...

Vad agenter får göra med operationen står inte här utan i åtkomstregistret
(access_register.yaml, se access.py).
"""

from __future__ import annotations

import re
import typing
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from services.errors import ServiceConfigError, UnknownOperationError

#: Operationsnamn blir verktygsnamn för agenter – samma krav som i AI-lagret.
OPERATION_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class OperationKind(StrEnum):
    """Vad operationen gör – samma klasser som sidoeffektsklasserna i B-026."""

    READ = "read"
    COMPUTE = "compute"
    WRITE = "write"
    EXTERNAL = "external"

    @property
    def changes_state(self) -> bool:
        return self in (OperationKind.WRITE, OperationKind.EXTERNAL)


class AgentAccess(StrEnum):
    """Vad en agent får göra med en operation (tjänstelager.md §4)."""

    AGENT = "AGENT"  # utföra direkt
    APPROVAL = "APPROVAL"  # föreslå – en handläggare godkänner
    HUMAN_ONLY = "HUMAN_ONLY"  # ingenting – endast handläggare

    @property
    def strictness(self) -> int:
        return _STRICTNESS[self]


_STRICTNESS = {AgentAccess.AGENT: 0, AgentAccess.APPROVAL: 1, AgentAccess.HUMAN_ONLY: 2}


def strictest(*levels: AgentAccess) -> AgentAccess:
    return max(levels, key=lambda level: level.strictness)


class Actor(BaseModel):
    """Vem som anropar tjänstelagret."""

    model_config = ConfigDict(frozen=True)

    type: Literal["human", "agent", "system"]
    id: str
    team: str | None = None  # agentens team (B-026)

    @classmethod
    def human(cls, id: str) -> Actor:
        return cls(type="human", id=id)

    @classmethod
    def agent(cls, id: str, team: str | None = None) -> Actor:
        return cls(type="agent", id=id, team=team)

    @classmethod
    def system(cls, id: str) -> Actor:
        return cls(type="system", id=id)

    @property
    def is_agent(self) -> bool:
        return self.type == "agent"


@dataclass(frozen=True)
class OperationContext:
    """Följer med varje anrop (tjänstelager.md §5).

    `session` sätts av tjänstelagret när operationen körs – anroparen anger den inte.
    """

    actor: Actor
    reason: str | None = None  # obligatorisk för write/external
    run_id: str | None = None  # agentkörning (körjournal, AI-lagrets anropslogg)
    case_id: str | None = None  # ärende (delprojekt 1)
    session: Any = None


@dataclass(frozen=True)
class Operation:
    name: str
    description: str
    kind: OperationKind
    input_model: type[BaseModel]
    output_model: type[BaseModel] | None
    rules: tuple[str, ...]
    pii: bool
    func: Callable[[OperationContext, BaseModel], Any]


class OperationRegistry:
    """Alla operationer som tjänstelagret känner till."""

    def __init__(self) -> None:
        self._operations: dict[str, Operation] = {}

    def add(self, op: Operation) -> None:
        if op.name in self._operations:
            raise ServiceConfigError(f"Operationen '{op.name}' är redan registrerad")
        self._operations[op.name] = op

    def get(self, name: str) -> Operation:
        try:
            return self._operations[name]
        except KeyError:
            raise UnknownOperationError(f"Okänd operation: '{name}'") from None

    def names(self) -> list[str]:
        return sorted(self._operations)

    def __contains__(self, name: str) -> bool:
        return name in self._operations

    def __iter__(self) -> Iterator[Operation]:
        return iter(self._operations[name] for name in self.names())

    def __len__(self) -> int:
        return len(self._operations)


#: Standardregistret – operationsmodulerna registrerar sig här när de importeras.
default_registry = OperationRegistry()


def operation(
    *,
    name: str,
    description: str,
    kind: OperationKind,
    rules: list[str] | tuple[str, ...] = (),
    pii: bool = False,
    registry: OperationRegistry | None = None,
) -> Callable[[Callable], Callable]:
    """Registrerar en funktion `fn(ctx, data: InputModel) -> OutputModel` som operation."""
    if not OPERATION_NAME_PATTERN.match(name):
        raise ServiceConfigError(
            f"Ogiltigt operationsnamn '{name}' – engelska snake_case, max 64 tecken"
        )

    def decorator(func: Callable) -> Callable:
        hints = typing.get_type_hints(func)
        params = [p for p in func.__code__.co_varnames[: func.__code__.co_argcount]]
        if len(params) != 2:
            raise ServiceConfigError(f"Operationen '{name}' ska ta exakt (ctx, data)")
        input_model = hints.get(params[1])
        if not (isinstance(input_model, type) and issubclass(input_model, BaseModel)):
            raise ServiceConfigError(
                f"Operationen '{name}': indata ska annoteras med en Pydantic-modell"
            )
        output_model = hints.get("return")
        if not (isinstance(output_model, type) and issubclass(output_model, BaseModel)):
            output_model = None
        (registry if registry is not None else default_registry).add(
            Operation(
                name=name,
                description=description,
                kind=OperationKind(kind),
                input_model=input_model,
                output_model=output_model,
                rules=tuple(rules),
                pii=pii,
                func=func,
            )
        )
        return func

    return decorator
