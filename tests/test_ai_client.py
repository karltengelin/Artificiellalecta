"""Tester för AIClient: rollupplösning, reservkedja, strukturerade svar och loggning.

Alla anrop går mot FakeProvider – inga nätverksanrop, ingen kostnad.
"""

from dataclasses import replace

import pytest
from pydantic import BaseModel

from ai import (
    AIClient,
    AIConfig,
    ConfigError,
    InvalidRequestError,
    Message,
    MissingKeyError,
    ProviderUnavailableError,
    StructuredOutputError,
    ToolResult,
    ToolSpec,
)
from ai.providers.fake import FakeProvider, text_result, tool_call_result
from ai.tracing import MemoryTraceSink


def make_config() -> AIConfig:
    price = {"input": 10.0, "output": 20.0}
    return AIConfig.from_dict(
        {
            "providers": {
                "alpha": {"type": "fake", "api_key_env": "ALPHA_KEY"},
                "beta": {"type": "fake", "api_key_env": "BETA_KEY"},
            },
            "models": {
                "alpha:big": {"price": price, "capabilities": {"effort": True}},
                "alpha:plain": {"price": price, "capabilities": {"tools": False, "structured_output": False}},
                "beta:big": {"price": price, "capabilities": {"effort": True}},
            },
            "roles": {
                "standard": {"model": "alpha:big", "fallbacks": ["beta:big"], "effort": "medium"},
                "plain": {"model": "alpha:plain", "fallbacks": ["beta:big"]},
            },
        }
    )


def make_client(alpha=None, beta=None, *, environ=None, sink=None) -> AIClient:
    overrides = {}
    if alpha is not None:
        overrides["alpha"] = alpha
    if beta is not None:
        overrides["beta"] = beta
    return AIClient(
        make_config(),
        sink=sink if sink is not None else MemoryTraceSink(),
        provider_overrides=overrides,
        environ=environ if environ is not None else {},
    )


class Bedomning(BaseModel):
    kraver_eskalering: bool
    motivering: str


class TestGrundanrop:
    def test_ask_ger_text_och_loggar_med_kontext(self):
        sink = MemoryTraceSink()
        alpha = FakeProvider([text_result("Hej", input_tokens=1000, output_tokens=500)])
        ai = make_client(alpha, sink=sink).bind(team="forsakring", agent="case_handler", run_id="r1")

        assert ai.ask("Säg hej") == "Hej"

        (record,) = sink.records
        assert record.outcome == "ok"
        assert (record.team, record.agent, record.run_id) == ("forsakring", "case_handler", "r1")
        assert record.model_ref == "alpha:big"
        # 1000 × 10 + 500 × 20 per miljon tokens
        assert record.cost_usd == pytest.approx(0.02)
        assert record.content is None  # inget innehåll loggas som standard (B-006)

    def test_rollens_effort_skickas_och_kan_overstyras(self):
        alpha = FakeProvider([text_result("a"), text_result("b")])
        ai = make_client(alpha)
        ai.ask("x")
        ai.ask("x", effort="high")
        assert [r.effort for r in alpha.requests] == ["medium", "high"]

    def test_effort_skickas_inte_till_modell_utan_stod(self):
        alpha = FakeProvider([text_result("a")])
        make_client(alpha).ask("x", model="alpha:plain", effort="high")
        assert alpha.requests[0].effort is None

    def test_systeminstruktion_och_tokengrans_nar_adaptern(self):
        alpha = FakeProvider([text_result("a")])
        make_client(alpha).ask("x", system="Du är handläggare.", max_output_tokens=123)
        request = alpha.requests[0]
        assert (request.system, request.max_output_tokens, request.model) == (
            "Du är handläggare.", 123, "big",
        )

    def test_innehallsloggning_kan_slas_pa_for_felsokning(self):
        sink = MemoryTraceSink()
        alpha = FakeProvider([text_result("Svar")])
        make_client(alpha, sink=sink, environ={"AI_LOG_CONTENT": "true"}).ask("Fråga")
        content = sink.records[0].content
        assert content["response_text"] == "Svar"
        assert content["messages"][0]["text"] == "Fråga"


class TestReservkedja:
    def test_driftstorning_byter_till_reservmodell(self):
        sink = MemoryTraceSink()
        alpha = FakeProvider([ProviderUnavailableError("529 overloaded", provider="alpha")])
        beta = FakeProvider([text_result("från beta")])
        response = make_client(alpha, beta, sink=sink).complete([Message.user("x")])

        assert response.text == "från beta"
        assert response.model_ref == "beta:big"
        assert response.fallback_from == ("alpha:big",)
        assert [r.outcome for r in sink.records] == ["error", "ok"]
        assert sink.records[1].fallback_from == ["alpha:big"]

    def test_fel_i_anropet_byter_inte_modell(self):
        alpha = FakeProvider([InvalidRequestError("400 bad request", provider="alpha")])
        beta = FakeProvider([text_result("ska inte nås")])
        with pytest.raises(InvalidRequestError):
            make_client(alpha, beta).ask("x")
        assert beta.requests == []

    def test_saknad_nyckel_hoppar_till_reserv(self):
        # alpha har ingen override och ingen nyckel i miljön -> hoppas över
        sink = MemoryTraceSink()
        beta = FakeProvider([text_result("från beta")])
        response = make_client(beta=beta, sink=sink, environ={}).complete([Message.user("x")])

        assert response.model_ref == "beta:big"
        skipped = sink.records[0]
        assert (skipped.outcome, skipped.error_type) == ("skipped", "MissingKeyError")
        assert "ALPHA_KEY" in skipped.error_message

    def test_inga_nycklar_alls_ger_samlat_fel(self):
        with pytest.raises(MissingKeyError) as info:
            make_client(environ={}).ask("x")
        assert info.value.variables == ["ALPHA_KEY", "BETA_KEY"]

    def test_alla_modeller_nere_ger_sista_felet(self):
        alpha = FakeProvider([ProviderUnavailableError("nere", provider="alpha")])
        beta = FakeProvider([ProviderUnavailableError("också nere", provider="beta")])
        with pytest.raises(ProviderUnavailableError, match="också nere"):
            make_client(alpha, beta).ask("x")

    def test_modell_utan_verktygsstod_hoppas_over(self):
        alpha = FakeProvider([text_result("ska inte nås")])
        beta = FakeProvider([text_result("ok")])
        tool = ToolSpec(name="t", description="d", parameters={"type": "object", "properties": {}})
        response = make_client(alpha, beta).complete([Message.user("x")], model="plain", tools=[tool])
        assert response.model_ref == "beta:big"
        assert alpha.requests == []

    def test_explicit_modell_utan_stod_ger_configerror(self):
        tool = ToolSpec(name="t", description="d", parameters={"type": "object", "properties": {}})
        with pytest.raises(ConfigError, match="verktyg"):
            make_client(FakeProvider()).complete([Message.user("x")], model="alpha:plain", tools=[tool])


class TestStruktureradeSvar:
    def test_svaret_valideras_till_pydantic_instans(self):
        alpha = FakeProvider([text_result('{"kraver_eskalering": true, "motivering": "Oklart"}')])
        result = make_client(alpha).ask_structured("Bedöm", Bedomning)
        assert result == Bedomning(kraver_eskalering=True, motivering="Oklart")
        schema = alpha.requests[0].output_schema
        assert schema["additionalProperties"] is False
        assert alpha.requests[0].output_schema_name == "Bedomning"

    def test_ogiltigt_svar_ger_structuredoutputerror(self):
        alpha = FakeProvider([text_result('{"kraver_eskalering": "kanske"}')])
        with pytest.raises(StructuredOutputError) as info:
            make_client(alpha).ask_structured("Bedöm", Bedomning)
        assert "kanske" in info.value.raw_text

    def test_avbojt_svar_ger_structuredoutputerror_i_ask_structured(self):
        refusal = replace(text_result(""), stop_reason="refusal")
        with pytest.raises(StructuredOutputError, match="refusal"):
            make_client(FakeProvider([refusal])).ask_structured("x", Bedomning)


class TestVerktygsloop:
    def test_tva_varv_med_verktygsanrop(self):
        alpha = FakeProvider(
            [
                tool_call_result("get_income_base_amount", {"year": 2026}, call_id="c1"),
                text_result("IBB 2026 är 83 400 kr."),
            ]
        )
        ai = make_client(alpha)
        tool = ToolSpec(
            name="get_income_base_amount",
            description="Hämtar inkomstbasbeloppet för ett år",
            parameters={"type": "object", "properties": {"year": {"type": "integer"}}},
        )
        messages = [Message.user("Vad är IBB 2026?")]

        first = ai.complete(messages, tools=[tool])
        assert first.stop_reason == "tool_use"
        messages.append(first.to_message())
        call = first.tool_calls[0]
        messages.append(Message.from_tool_results([ToolResult(call_id=call.id, content="83400")]))

        second = ai.complete(messages, tools=[tool])
        assert second.text == "IBB 2026 är 83 400 kr."

        sent = alpha.requests[1].messages
        assert [m.role for m in sent] == ["user", "assistant", "user"]
        assert sent[1].tool_calls[0].arguments == {"year": 2026}
        assert sent[2].tool_results[0].content == "83400"


class TestBind:
    def test_bind_andrar_inte_ursprungsklienten(self):
        ai = make_client(FakeProvider())
        bound = ai.bind(team="kapital")
        assert ai.context.team is None
        assert bound.context.team == "kapital"
        assert bound.config is ai.config

    def test_tomt_meddelande_avvisas(self):
        with pytest.raises(ValueError):
            make_client(FakeProvider()).complete([])
