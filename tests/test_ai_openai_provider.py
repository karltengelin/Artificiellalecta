"""Tester för OpenAI-adaptern (Responses API) mot SDK:ns egna typer – inga nätverksanrop."""

from types import SimpleNamespace

import httpx2
import openai
import pytest
from openai.types.responses import Response

from ai.errors import AuthenticationError, InvalidRequestError, ProviderUnavailableError, RateLimitError
from ai.providers.base import ProviderRequest
from ai.providers.openai_provider import OpenAIProvider
from ai.types import Message, ProviderState, ToolCall, ToolResult, ToolSpec

REASONING = {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "krypterat"}
FUNCTION_CALL = {
    "type": "function_call",
    "id": "fc_1",
    "call_id": "call_1",
    "name": "get_income_base_amount",
    "arguments": '{"year": 2026}',
    "status": "completed",
}


def text_message(text, phase=None, msg_id="msg_1"):
    item = {
        "type": "message",
        "id": msg_id,
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }
    if phase:
        item["phase"] = phase
    return item


def openai_response(output, status="completed", incomplete_reason=None, model="gpt-6-luna"):
    return Response.model_validate(
        {
            "id": "resp_1",
            "object": "response",
            "created_at": 1760000000,
            "model": model,
            "output": output,
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "status": status,
            "incomplete_details": {"reason": incomplete_reason} if incomplete_reason else None,
            "usage": {
                "input_tokens": 100,
                "input_tokens_details": {"cached_tokens": 40, "cache_write_tokens": 10},
                "output_tokens": 50,
                "output_tokens_details": {"reasoning_tokens": 30},
                "total_tokens": 150,
            },
        }
    )


class StubResponses:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def stub_client(result):
    return SimpleNamespace(responses=StubResponses(result))


def request(**overrides) -> ProviderRequest:
    base = {"model": "gpt-6-luna", "messages": (Message.user("Hej"),)}
    base.update(overrides)
    return ProviderRequest(**base)


class TestForfragan:
    def test_grundforfragan_sparar_ingenting_hos_openai(self):
        client = stub_client(openai_response([text_message("Svar")]))
        OpenAIProvider(client).complete(request(system="Instruktion", max_output_tokens=500))
        (kwargs,) = client.responses.calls
        assert kwargs["store"] is False
        assert kwargs["include"] == ["reasoning.encrypted_content"]
        assert kwargs["instructions"] == "Instruktion"
        assert kwargs["max_output_tokens"] == 500
        assert kwargs["input"] == [{"role": "user", "content": "Hej"}]
        assert "reasoning" not in kwargs and "text" not in kwargs

    def test_verktyg_effort_och_schema(self):
        client = stub_client(openai_response([text_message("{}")]))
        tool = ToolSpec(name="t", description="d", parameters={"type": "object"})
        schema = {"type": "object", "properties": {}, "additionalProperties": False, "required": []}
        OpenAIProvider(client).complete(
            request(tools=(tool,), effort="low", output_schema=schema, output_schema_name="Bedomning")
        )
        kwargs = client.responses.calls[0]
        assert kwargs["tools"] == [
            {
                "type": "function",
                "name": "t",
                "description": "d",
                "parameters": {"type": "object"},
                "strict": False,
            }
        ]
        assert kwargs["reasoning"] == {"effort": "low"}
        assert kwargs["text"] == {
            "format": {"type": "json_schema", "name": "Bedomning", "schema": schema, "strict": True}
        }

    def test_verktygsresultat_och_aterskapade_anrop(self):
        client = stub_client(openai_response([text_message("ok")]))
        messages = (
            Message.user("Fråga"),
            Message.assistant("Tänker", (ToolCall(id="call_1", name="t", arguments={"år": 2026}),)),
            Message.from_tool_results([ToolResult(call_id="call_1", content="saknas", is_error=True)]),
        )
        OpenAIProvider(client).complete(request(messages=messages))
        sent = client.responses.calls[0]["input"]
        assert sent[1] == {"role": "assistant", "content": "Tänker"}
        assert sent[2] == {
            "type": "function_call", "call_id": "call_1", "name": "t", "arguments": '{"år": 2026}'
        }
        assert sent[3] == {"type": "function_call_output", "call_id": "call_1", "output": "Error: saknas"}


class TestSvar:
    def test_verktygsanrop_och_tokens(self):
        response = openai_response([REASONING, FUNCTION_CALL])
        result = OpenAIProvider(stub_client(response)).complete(request())
        assert result.stop_reason == "tool_use"
        assert result.tool_calls == (
            ToolCall(id="call_1", name="get_income_base_amount", arguments={"year": 2026}),
        )
        assert (result.usage.input_tokens, result.usage.cached_input_tokens) == (100, 40)
        assert result.usage.cache_write_tokens == 10
        assert result.usage.reasoning_tokens == 30
        assert [i["type"] for i in result.provider_state.payload] == ["reasoning", "function_call"]
        assert result.provider_state.payload[0]["encrypted_content"] == "krypterat"

    def test_kommentarer_ingar_inte_i_slutsvaret(self):
        response = openai_response(
            [
                text_message("Jag kollar...", phase="commentary", msg_id="m1"),
                text_message('{"ok": true}', phase="final_answer", msg_id="m2"),
            ]
        )
        result = OpenAIProvider(stub_client(response)).complete(request())
        assert result.text == '{"ok": true}'
        assert result.stop_reason == "end_turn"

    def test_avbrutet_vid_tokengrans(self):
        response = openai_response(
            [text_message("Halv")], status="incomplete", incomplete_reason="max_output_tokens"
        )
        assert OpenAIProvider(stub_client(response)).complete(request()).stop_reason == "max_tokens"

    def test_refusal(self):
        response = openai_response(
            [
                {
                    "type": "message",
                    "id": "msg_1",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "refusal", "refusal": "Kan inte hjälpa till."}],
                }
            ]
        )
        result = OpenAIProvider(stub_client(response)).complete(request())
        assert (result.stop_reason, result.text) == ("refusal", "Kan inte hjälpa till.")

    def test_ogiltig_argument_json_blir_raw_falt(self):
        bad = {**FUNCTION_CALL, "arguments": "{inte json"}
        result = OpenAIProvider(stub_client(openai_response([bad]))).complete(request())
        assert result.tool_calls[0].arguments == {"_raw_arguments": "{inte json"}


class TestAterspelning:
    def test_samma_modell_far_tillbaka_alla_items(self):
        first = OpenAIProvider(stub_client(openai_response([REASONING, FUNCTION_CALL]))).complete(request())
        history = (
            Message.user("Hej"),
            Message(role="assistant", tool_calls=first.tool_calls, provider_state=first.provider_state),
            Message.from_tool_results([ToolResult(call_id="call_1", content="83400")]),
        )
        client = stub_client(openai_response([text_message("ok")]))
        OpenAIProvider(client).complete(request(messages=history))
        sent = client.responses.calls[0]["input"]
        assert [i.get("type") for i in sent[1:3]] == ["reasoning", "function_call"]
        assert sent[1]["encrypted_content"] == "krypterat"
        assert sent[3]["type"] == "function_call_output"

    def test_annan_modell_far_kanonisk_aterskapning(self):
        state = ProviderState(provider="openai", model="gpt-6-astra", payload=[REASONING])
        history = (
            Message.user("Hej"),
            Message(role="assistant", text="Svar", provider_state=state),
            Message.user("Mer"),
        )
        client = stub_client(openai_response([text_message("ok")]))
        OpenAIProvider(client).complete(request(messages=history))
        assert client.responses.calls[0]["input"][1] == {"role": "assistant", "content": "Svar"}


def _status_error(cls, status):
    req = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    return cls("fel", response=httpx2.Response(status, request=req), body=None)


class TestFelmappning:
    @pytest.mark.parametrize(
        ("sdk_error", "expected"),
        [
            (_status_error(openai.AuthenticationError, 401), AuthenticationError),
            (_status_error(openai.BadRequestError, 400), InvalidRequestError),
            (_status_error(openai.RateLimitError, 429), RateLimitError),
            (_status_error(openai.InternalServerError, 503), ProviderUnavailableError),
            (
                openai.APIConnectionError(request=httpx2.Request("POST", "https://api.openai.com")),
                ProviderUnavailableError,
            ),
        ],
    )
    def test_sdk_fel_blir_kanoniska(self, sdk_error, expected):
        with pytest.raises(expected) as info:
            OpenAIProvider(stub_client(sdk_error)).complete(request())
        assert info.value.provider == "openai"
