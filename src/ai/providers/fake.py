"""Fejkleverantör för tester – skriptade svar, inga nätverksanrop.

Används för att testa agenter och flöden utan nyckel och utan kostnad:

    fake = FakeProvider([tool_call_result("calculate_itp1_premium", {...}),
                         text_result("Premien blir 1 575 kr.")])
    ai = AIClient(provider_overrides={"anthropic": fake, "openai": fake})

Alla förfrågningar sparas i `fake.requests` för kontroll i testet.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from ai.config import ProviderConfig
from ai.providers.base import ProviderRequest, ProviderResult
from ai.types import ToolCall, Usage

ScriptItem = ProviderResult | Exception | Callable[[ProviderRequest], ProviderResult]


class FakeProvider:
    def __init__(self, responses: Iterable[ScriptItem] = (), *, name: str = "fake") -> None:
        self._script: list[ScriptItem] = list(responses)
        self.requests: list[ProviderRequest] = []
        self.name = name

    @classmethod
    def from_config(cls, config: ProviderConfig, api_key: str | None) -> FakeProvider:
        return cls(name=config.name)

    def queue(self, *responses: ScriptItem) -> None:
        self._script.extend(responses)

    def complete(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        if not self._script:
            raise RuntimeError("FakeProvider: inga fler skriptade svar")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(request)
        return item


def text_result(
    text: str, *, model: str = "fake-model", input_tokens: int = 100, output_tokens: int = 20
) -> ProviderResult:
    return ProviderResult(
        text=text,
        tool_calls=(),
        stop_reason="end_turn",
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
        model=model,
    )


def tool_call_result(
    name: str,
    arguments: dict,
    *,
    call_id: str = "call_1",
    text: str = "",
    model: str = "fake-model",
) -> ProviderResult:
    return ProviderResult(
        text=text,
        tool_calls=(ToolCall(id=call_id, name=name, arguments=arguments),),
        stop_reason="tool_use",
        usage=Usage(input_tokens=100, output_tokens=20),
        model=model,
    )
