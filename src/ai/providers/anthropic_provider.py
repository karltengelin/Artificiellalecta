"""Adapter mot Anthropics Messages API (officiella `anthropic`-SDK:n).

Översätter kanoniska meddelanden och verktyg till Messages API och tillbaka.
Leverantörsspecifikt som kapslas in här (02_system/ai_abstraktion.md §8):
- verktyg som `tools[].input_schema` (+ `strict`), resultat som `tool_result`-block
- strukturerade svar via `output_config.format`, resonemangsnivå via `output_config.effort`
- automatisk prompt caching via `cache_control` på anropsnivå
- server-side fallback (`fallbacks: "default"`, beta) för modeller som har det påslaget
- tänkande-block återspelas oförändrade inom samma leverantör
"""

from __future__ import annotations

from typing import Any

import anthropic

from ai.config import ProviderConfig
from ai.providers.base import ProviderRequest, ProviderResult, map_sdk_error
from ai.types import Message, ProviderState, StopReason, ToolCall, ToolSpec, Usage

PROVIDER_TYPE = "anthropic"

#: Beta-flagga för `fallbacks: "default"` (Anthropic väljer reservmodell per avböjandekategori).
SERVER_SIDE_FALLBACK_BETA = "server-side-fallback-2026-07-01"

_STOP_REASONS: dict[str, StopReason] = {
    "end_turn": "end_turn",
    "stop_sequence": "end_turn",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
    "refusal": "refusal",
}

#: Blocktyper som inte skickas tillbaka: `fallback` är bara en granskningsmarkör.
_NOT_REPLAYED = {"fallback"}


class AnthropicProvider:
    def __init__(self, client: Any, *, name: str = PROVIDER_TYPE) -> None:
        self._client = client
        self.name = name

    @classmethod
    def from_config(cls, config: ProviderConfig, api_key: str | None) -> AnthropicProvider:
        client = anthropic.Anthropic(
            api_key=api_key,
            base_url=config.base_url,
            max_retries=config.max_retries,
            timeout=config.timeout_seconds,
        )
        return cls(client, name=config.name)

    def complete(self, request: ProviderRequest) -> ProviderResult:
        kwargs = self._build_kwargs(request)
        try:
            if request.options.get("server_side_fallback"):
                response = self._client.beta.messages.create(
                    betas=[SERVER_SIDE_FALLBACK_BETA], fallbacks="default", **kwargs
                )
            else:
                response = self._client.messages.create(**kwargs)
        except anthropic.APIError as exc:
            raise map_sdk_error(exc, anthropic, provider=self.name, model=request.model) from exc
        return self._parse(response, request)

    # --- förfrågan ---------------------------------------------------------

    def _build_kwargs(self, request: ProviderRequest) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_output_tokens,
            "messages": [self._message(m) for m in request.messages],
        }
        if request.system:
            kwargs["system"] = request.system
        if request.tools:
            kwargs["tools"] = [self._tool(t) for t in request.tools]
        output_config: dict[str, Any] = {}
        if request.effort:
            output_config["effort"] = request.effort
        if request.output_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": request.output_schema}
        if output_config:
            kwargs["output_config"] = output_config
        if request.options.get("prompt_caching"):
            kwargs["cache_control"] = {"type": "ephemeral"}
        return kwargs

    @staticmethod
    def _tool(tool: ToolSpec) -> dict[str, Any]:
        spec: dict[str, Any] = {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
        }
        if tool.strict:
            spec["strict"] = True
        return spec

    @staticmethod
    def _message(message: Message) -> dict[str, Any]:
        if message.role == "user":
            if not message.tool_results:
                return {"role": "user", "content": message.text}
            # tool_result-block måste komma först i meddelandet, ev. text efter
            content: list[dict[str, Any]] = []
            for result in message.tool_results:
                block: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": result.call_id,
                    "content": result.content,
                }
                if result.is_error:
                    block["is_error"] = True
                content.append(block)
            if message.text:
                content.append({"type": "text", "text": message.text})
            return {"role": "user", "content": content}

        state = message.provider_state
        if state is not None and state.provider == PROVIDER_TYPE:
            # Tänkande-block får inte strippas eller ändras – skicka tillbaka som de kom
            blocks = [b for b in state.payload if b.get("type") not in _NOT_REPLAYED]
            if blocks:
                return {"role": "assistant", "content": blocks}

        content = []
        if message.text:
            content.append({"type": "text", "text": message.text})
        for call in message.tool_calls:
            content.append(
                {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
            )
        if not content:
            content.append({"type": "text", "text": "(inget innehåll)"})
        return {"role": "assistant", "content": content}

    # --- svar --------------------------------------------------------------

    def _parse(self, response: Any, request: ProviderRequest) -> ProviderResult:
        texts: list[str] = []
        tool_calls: list[ToolCall] = []
        payload: list[dict[str, Any]] = []
        for block in response.content:
            payload.append(block.to_dict(mode="json", exclude_none=True))
            if block.type == "text":
                texts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {}))
                )

        usage = response.usage
        cached = usage.cache_read_input_tokens or 0
        written = usage.cache_creation_input_tokens or 0
        details = getattr(usage, "output_tokens_details", None)
        return ProviderResult(
            text="".join(texts),
            tool_calls=tuple(tool_calls),
            stop_reason=_STOP_REASONS.get(response.stop_reason or "", "other"),
            usage=Usage(
                input_tokens=usage.input_tokens + cached + written,
                output_tokens=usage.output_tokens,
                cached_input_tokens=cached,
                cache_write_tokens=written,
                reasoning_tokens=getattr(details, "thinking_tokens", 0) or 0,
            ),
            model=response.model,
            request_id=getattr(response, "_request_id", None),
            provider_state=ProviderState(
                provider=PROVIDER_TYPE, model=request.model, payload=payload
            ),
        )
