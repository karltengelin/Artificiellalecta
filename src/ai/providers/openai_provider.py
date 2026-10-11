"""Adapter mot OpenAIs Responses API (officiella `openai`-SDK:n).

Översätter kanoniska meddelanden och verktyg till Responses API och tillbaka.
Leverantörsspecifikt som kapslas in här (02_system/ai_abstraktion.md §8):
- verktyg som `function`-tools, resultat som `function_call_output`-items
- strukturerade svar via `text.format` (json_schema, strict), resonemang via `reasoning.effort`
- `store=False`: ingen konversation sparas hos OpenAI. Resonemangs-items
  återspelas i stället krypterat (`include=["reasoning.encrypted_content"]`)
"""

from __future__ import annotations

import json
from typing import Any

import openai

from ai.config import ProviderConfig
from ai.providers.base import ProviderRequest, ProviderResult, map_sdk_error
from ai.types import ProviderState, StopReason, ToolCall, ToolSpec, Usage

PROVIDER_TYPE = "openai"


class OpenAIProvider:
    def __init__(self, client: Any, *, name: str = PROVIDER_TYPE) -> None:
        self._client = client
        self.name = name

    @classmethod
    def from_config(cls, config: ProviderConfig, api_key: str | None) -> OpenAIProvider:
        client = openai.OpenAI(
            api_key=api_key,
            base_url=config.base_url,
            max_retries=config.max_retries,
            timeout=config.timeout_seconds,
        )
        return cls(client, name=config.name)

    def complete(self, request: ProviderRequest) -> ProviderResult:
        kwargs = self._build_kwargs(request)
        try:
            response = self._client.responses.create(**kwargs)
        except openai.APIError as exc:
            raise map_sdk_error(exc, openai, provider=self.name, model=request.model) from exc
        return self._parse(response, request)

    # --- förfrågan ---------------------------------------------------------

    def _build_kwargs(self, request: ProviderRequest) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": request.model,
            "input": self._input(request),
            "max_output_tokens": request.max_output_tokens,
            "store": False,
        }
        if request.system:
            kwargs["instructions"] = request.system
        if request.tools:
            kwargs["tools"] = [self._tool(t) for t in request.tools]
        if request.effort:
            kwargs["reasoning"] = {"effort": request.effort}
        if request.options.get("encrypted_reasoning", True):
            kwargs["include"] = ["reasoning.encrypted_content"]
        if request.output_schema is not None:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": request.output_schema_name,
                    "schema": request.output_schema,
                    "strict": True,
                }
            }
        return kwargs

    @staticmethod
    def _tool(tool: ToolSpec) -> dict[str, Any]:
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "strict": tool.strict,
        }

    @staticmethod
    def _input(request: ProviderRequest) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == "user":
                for result in message.tool_results:
                    output = f"Error: {result.content}" if result.is_error else result.content
                    items.append(
                        {"type": "function_call_output", "call_id": result.call_id, "output": output}
                    )
                if message.text:
                    items.append({"role": "user", "content": message.text})
                continue

            state = message.provider_state
            if (
                state is not None
                and state.provider == PROVIDER_TYPE
                and state.model == request.model
            ):
                # Alla output-items tillbaka, inklusive krypterade resonemangs-items
                items.extend(state.payload)
                continue

            if message.text:
                items.append({"role": "assistant", "content": message.text})
            for call in message.tool_calls:
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call.id,
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    }
                )
        return items

    # --- svar --------------------------------------------------------------

    def _parse(self, response: Any, request: ProviderRequest) -> ProviderResult:
        final_texts: list[str] = []
        other_texts: list[str] = []
        tool_calls: list[ToolCall] = []
        refused = False
        payload: list[dict[str, Any]] = []

        for item in response.output:
            payload.append(item.to_dict(mode="json", exclude_none=True))
            if item.type == "message":
                parts = []
                for part in item.content:
                    if part.type == "output_text":
                        parts.append(part.text)
                    elif part.type == "refusal":
                        refused = True
                        parts.append(part.refusal)
                # Mellanliggande kommentarer ("commentary") ingår inte i slutsvaret
                target = final_texts if getattr(item, "phase", None) == "final_answer" else other_texts
                target.append("".join(parts))
            elif item.type == "function_call":
                tool_calls.append(
                    ToolCall(id=item.call_id, name=item.name, arguments=_parse_arguments(item.arguments))
                )

        has_final = any(
            getattr(item, "phase", None) == "final_answer" for item in response.output
        )
        text = "\n\n".join(t for t in (final_texts if has_final else other_texts) if t)

        usage = response.usage
        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)
        return ProviderResult(
            text=text,
            tool_calls=tuple(tool_calls),
            stop_reason=_stop_reason(response, bool(tool_calls), refused),
            usage=Usage(
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
                cached_input_tokens=getattr(input_details, "cached_tokens", 0) or 0,
                cache_write_tokens=getattr(input_details, "cache_write_tokens", 0) or 0,
                reasoning_tokens=getattr(output_details, "reasoning_tokens", 0) or 0,
            ),
            model=response.model,
            request_id=getattr(response, "_request_id", None),
            provider_state=ProviderState(
                provider=PROVIDER_TYPE, model=request.model, payload=payload
            ),
        )


def _parse_arguments(raw: str) -> dict[str, Any]:
    """Ogiltig JSON blir ett fält som agent-runtime kan avvisa som verktygsfel."""
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_raw_arguments": raw}
    return value if isinstance(value, dict) else {"_raw_arguments": raw}


def _stop_reason(response: Any, has_tool_calls: bool, refused: bool) -> StopReason:
    if has_tool_calls:
        return "tool_use"
    if refused:
        return "refusal"
    if response.status == "incomplete":
        reason = getattr(response.incomplete_details, "reason", None)
        if reason == "max_output_tokens":
            return "max_tokens"
        if reason == "content_filter":
            return "refusal"
        return "other"
    return "end_turn" if response.status in ("completed", None) else "other"
