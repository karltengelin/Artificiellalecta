"""Tester för Anthropic-adaptern mot SDK:ns egna typer – inga nätverksanrop."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from anthropic.types import Message as AnthropicMessage
from anthropic.types.beta import BetaMessage

from ai.errors import (
    AuthenticationError,
    InvalidRequestError,
    ProviderUnavailableError,
    RateLimitError,
)
from ai.providers.anthropic_provider import SERVER_SIDE_FALLBACK_BETA, AnthropicProvider
from ai.providers.base import ProviderRequest
from ai.types import Message, ProviderState, ToolCall, ToolResult, ToolSpec

USAGE = {
    "input_tokens": 100,
    "output_tokens": 50,
    "cache_read_input_tokens": 300,
    "cache_creation_input_tokens": 20,
}


def anthropic_message(content, stop_reason="end_turn", model="claude-sonnet-5"):
    return AnthropicMessage.model_validate(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": content,
            "stop_reason": stop_reason,
            "usage": USAGE,
        }
    )


class StubEndpoint:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def stub_client(result):
    return SimpleNamespace(
        messages=StubEndpoint(result), beta=SimpleNamespace(messages=StubEndpoint(result))
    )


def request(**overrides) -> ProviderRequest:
    base = {"model": "claude-sonnet-5", "messages": (Message.user("Hej"),)}
    base.update(overrides)
    return ProviderRequest(**base)


class TestForfragan:
    def test_grundforfragan(self):
        client = stub_client(anthropic_message([{"type": "text", "text": "Svar"}]))
        AnthropicProvider(client).complete(request(system="Instruktion", max_output_tokens=500))
        (kwargs,) = client.messages.calls
        assert kwargs["model"] == "claude-sonnet-5"
        assert kwargs["max_tokens"] == 500
        assert kwargs["system"] == "Instruktion"
        assert kwargs["messages"] == [{"role": "user", "content": "Hej"}]
        assert "output_config" not in kwargs and "cache_control" not in kwargs

    def test_verktyg_effort_schema_och_cache(self):
        client = stub_client(anthropic_message([{"type": "text", "text": "{}"}]))
        tool = ToolSpec(name="t", description="d", parameters={"type": "object"}, strict=True)
        schema = {"type": "object", "properties": {}, "additionalProperties": False, "required": []}
        AnthropicProvider(client).complete(
            request(tools=(tool,), effort="high", output_schema=schema, options={"prompt_caching": True})
        )
        kwargs = client.messages.calls[0]
        assert kwargs["tools"] == [
            {"name": "t", "description": "d", "input_schema": {"type": "object"}, "strict": True}
        ]
        assert kwargs["output_config"] == {
            "effort": "high",
            "format": {"type": "json_schema", "schema": schema},
        }
        assert kwargs["cache_control"] == {"type": "ephemeral"}

    def test_server_side_fallback_anvander_beta(self):
        client = stub_client(anthropic_message([{"type": "text", "text": "ok"}]))
        AnthropicProvider(client).complete(request(options={"server_side_fallback": True}))
        assert client.messages.calls == []
        kwargs = client.beta.messages.calls[0]
        assert kwargs["betas"] == [SERVER_SIDE_FALLBACK_BETA]
        assert kwargs["fallbacks"] == "default"

    def test_verktygsresultat_blir_tool_result_block(self):
        client = stub_client(anthropic_message([{"type": "text", "text": "ok"}]))
        messages = (
            Message.user("Fråga"),
            Message.assistant("", (ToolCall(id="tu_1", name="t", arguments={"a": 1}),)),
            Message.from_tool_results(
                [ToolResult(call_id="tu_1", content="fel", is_error=True)]
            ),
        )
        AnthropicProvider(client).complete(request(messages=messages))
        sent = client.messages.calls[0]["messages"]
        assert sent[1] == {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "tu_1", "name": "t", "input": {"a": 1}}],
        }
        assert sent[2] == {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "tu_1", "content": "fel", "is_error": True}
            ],
        }


class TestSvar:
    def test_text_verktygsanrop_och_tokens(self):
        response = anthropic_message(
            [
                {"type": "thinking", "thinking": "", "signature": "sig"},
                {"type": "text", "text": "Jag räknar."},
                {"type": "tool_use", "id": "tu_1", "name": "calc", "input": {"lon": 35000}},
            ],
            stop_reason="tool_use",
        )
        result = AnthropicProvider(stub_client(response)).complete(request())
        assert result.text == "Jag räknar."
        assert result.tool_calls == (ToolCall(id="tu_1", name="calc", arguments={"lon": 35000}),)
        assert result.stop_reason == "tool_use"
        # input_tokens = okachade + lästa ur cache + skrivna till cache
        assert result.usage.input_tokens == 420
        assert (result.usage.cached_input_tokens, result.usage.cache_write_tokens) == (300, 20)
        assert result.provider_state.provider == "anthropic"
        assert [b["type"] for b in result.provider_state.payload] == ["thinking", "text", "tool_use"]

    def test_avbojt_svar(self):
        result = AnthropicProvider(stub_client(anthropic_message([], stop_reason="refusal"))).complete(
            request()
        )
        assert (result.stop_reason, result.text) == ("refusal", "")


class TestAterspelning:
    def test_eget_state_skickas_tillbaka_oforandrat_utan_fallback_markor(self):
        raw = BetaMessage.model_validate(
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-4-8",
                "content": [
                    {
                        "type": "fallback",
                        "from": {"model": "claude-opus-5"},
                        "to": {"model": "claude-opus-4-8"},
                        "trigger": {"type": "refusal", "category": "cyber"},
                    },
                    {"type": "thinking", "thinking": "", "signature": "sig"},
                    {"type": "text", "text": "Svar"},
                ],
                "stop_reason": "end_turn",
                "usage": USAGE,
            }
        )
        first = AnthropicProvider(stub_client(raw)).complete(request(model="claude-opus-5"))
        history = (
            Message.user("Hej"),
            Message(role="assistant", text=first.text, provider_state=first.provider_state),
            Message.user("Mer"),
        )

        client = stub_client(anthropic_message([{"type": "text", "text": "ok"}]))
        AnthropicProvider(client).complete(request(messages=history))
        assistant = client.messages.calls[0]["messages"][1]
        assert [b["type"] for b in assistant["content"]] == ["thinking", "text"]
        assert assistant["content"][0]["signature"] == "sig"

    def test_annan_leverantors_state_aterskapas_ur_kanoniska_falt(self):
        foreign = ProviderState(provider="openai", model="gpt-6-luna", payload=[{"type": "reasoning"}])
        history = (
            Message.user("Hej"),
            Message(role="assistant", text="Svar", provider_state=foreign),
            Message.user("Mer"),
        )
        client = stub_client(anthropic_message([{"type": "text", "text": "ok"}]))
        AnthropicProvider(client).complete(request(messages=history))
        assert client.messages.calls[0]["messages"][1] == {
            "role": "assistant",
            "content": [{"type": "text", "text": "Svar"}],
        }


def _status_error(cls, status):
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("fel", response=httpx2.Response(status, request=req), body=None)


class TestFelmappning:
    @pytest.mark.parametrize(
        ("sdk_error", "expected"),
        [
            (_status_error(anthropic.AuthenticationError, 401), AuthenticationError),
            (_status_error(anthropic.PermissionDeniedError, 403), AuthenticationError),
            (_status_error(anthropic.BadRequestError, 400), InvalidRequestError),
            (_status_error(anthropic.NotFoundError, 404), InvalidRequestError),
            (_status_error(anthropic.RateLimitError, 429), RateLimitError),
            (_status_error(anthropic.InternalServerError, 500), ProviderUnavailableError),
            (_status_error(anthropic.APIStatusError, 529), ProviderUnavailableError),
            (
                anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api.anthropic.com")),
                ProviderUnavailableError,
            ),
        ],
    )
    def test_sdk_fel_blir_kanoniska(self, sdk_error, expected):
        with pytest.raises(expected) as info:
            AnthropicProvider(stub_client(sdk_error)).complete(request())
        assert info.value.provider == "anthropic"
        assert info.value.model == "claude-sonnet-5"
