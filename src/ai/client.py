"""AIClient – gränssnittet agent- och skillkod använder (02_system/ai_abstraktion.md §5).

Klienten löser upp en modellroll till en kedja av modeller (primär + reserver),
väljer nyckel efter teamkontext, anropar rätt adapter, validerar strukturerade
svar, beräknar kostnad och loggar varje försök.
"""

from __future__ import annotations

import copy
import os
import threading
import time
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ai.config import AIConfig, ModelSpec, Resolution, load_config
from ai.errors import ConfigError, MissingKeyError, ProviderError, StructuredOutputError
from ai.keys import resolve_api_key
from ai.providers import Provider, ProviderRequest, ProviderResult, create_provider
from ai.schema import schema_name, strict_json_schema
from ai.tracing import CallRecord, TraceSink, log_content_enabled, sink_from_config
from ai.types import CallContext, Effort, Message, ModelResponse, ToolSpec

T = TypeVar("T", bound=BaseModel)


class AIClient:
    def __init__(
        self,
        config: AIConfig | None = None,
        *,
        sink: TraceSink | None = None,
        context: CallContext | None = None,
        provider_overrides: Mapping[str, Provider] | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        """
        provider_overrides: leverantörsnamn -> färdig adapter (t.ex. FakeProvider i tester).
        environ: miljövariabler för nycklar och överstyrningar (standard: os.environ).
        """
        self._environ = os.environ if environ is None else environ
        self.config = config or load_config(environ=self._environ)
        self._sink = sink if sink is not None else sink_from_config(self.config.tracing, self._environ)
        self._log_content = log_content_enabled(self.config.tracing, self._environ)
        self.context = context or CallContext()
        self._overrides = dict(provider_overrides or {})
        self._providers: dict[tuple[str, str | None], tuple[Provider, str | None]] = {}
        self._lock = threading.Lock()

    def bind(
        self,
        *,
        team: str | None = None,
        agent: str | None = None,
        run_id: str | None = None,
        step: str | None = None,
    ) -> AIClient:
        """Ny klient med utökad kontext. Delar konfiguration, logg och leverantörscache."""
        clone = copy.copy(self)
        clone.context = self.context.merged(team=team, agent=agent, run_id=run_id, step=step)
        return clone

    # --- publika anrop -----------------------------------------------------

    def ask(
        self,
        prompt: str,
        *,
        system: str | None = None,
        model: str | None = None,
        effort: Effort | None = None,
        max_output_tokens: int | None = None,
        step: str | None = None,
    ) -> str:
        """Enkel fråga, textsvar."""
        return self.complete(
            [Message.user(prompt)],
            system=system,
            model=model,
            effort=effort,
            max_output_tokens=max_output_tokens,
            step=step,
        ).text

    def ask_structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str | None = None,
        model: str | None = None,
        effort: Effort | None = None,
        max_output_tokens: int | None = None,
        step: str | None = None,
    ) -> T:
        """Enkel fråga, svar validerat mot en Pydantic-modell."""
        response = self.complete(
            [Message.user(prompt)],
            system=system,
            model=model,
            output_schema=schema,
            effort=effort,
            max_output_tokens=max_output_tokens,
            step=step,
        )
        if response.parsed is None:
            raise StructuredOutputError(
                f"Inget strukturerat svar från {response.model_ref} "
                f"(stop_reason={response.stop_reason})",
                raw_text=response.text,
            )
        return response.parsed

    def complete(
        self,
        messages: Sequence[Message],
        *,
        system: str | None = None,
        model: str | None = None,
        tools: Sequence[ToolSpec] | None = None,
        output_schema: type[BaseModel] | None = None,
        effort: Effort | None = None,
        max_output_tokens: int | None = None,
        step: str | None = None,
    ) -> ModelResponse:
        """Fullt anrop: historik, verktyg och/eller strukturerat svar.

        model: roll ("fast"/"standard"/"deep") eller "leverantör:modell".
        Standard är konfigurationens standardroll.
        """
        if not messages:
            raise ValueError("complete() kräver minst ett meddelande")
        resolution = self.config.resolve(model, self._environ)
        context = self.context.merged(step=step)
        schema = strict_json_schema(output_schema) if output_schema is not None else None

        tried: list[str] = []
        errors: list[Exception] = []
        for spec in resolution.chain:
            missing = self._missing_capability(spec, tools, output_schema)
            if missing:
                self._trace_skip(spec, resolution, context, tried, f"saknar stöd för {missing}")
                errors.append(ConfigError(f"{spec.ref} saknar stöd för {missing}"))
                tried.append(spec.ref)
                continue
            try:
                provider, key_env = self._provider_for(spec, context.team)
            except MissingKeyError as exc:
                self._trace_skip(spec, resolution, context, tried, str(exc), error_type="MissingKeyError")
                errors.append(exc)
                tried.append(spec.ref)
                continue

            request = ProviderRequest(
                model=spec.model,
                messages=tuple(messages),
                system=system,
                tools=tuple(tools or ()),
                output_schema=schema,
                output_schema_name=schema_name(output_schema) if output_schema else "response",
                max_output_tokens=max_output_tokens or resolution.max_output_tokens,
                effort=(effort or resolution.effort) if spec.capabilities.effort else None,
                options=spec.options,
            )
            started = time.perf_counter()
            try:
                result = provider.complete(request)
            except ProviderError as exc:
                self._trace_error(spec, resolution, context, tried, key_env, exc, started)
                if not exc.fallback_eligible:
                    raise
                errors.append(exc)
                tried.append(spec.ref)
                continue

            response = self._build_response(result, spec, resolution, started, tried)
            self._trace_ok(response, context, key_env, system, messages)
            if output_schema is not None and response.stop_reason not in ("tool_use", "refusal"):
                response = response.model_copy(
                    update={"parsed": self._parse_structured(response, output_schema)}
                )
            return response

        raise self._exhausted_error(resolution, errors)

    # --- interna hjälpare --------------------------------------------------

    @staticmethod
    def _missing_capability(
        spec: ModelSpec, tools: Sequence[ToolSpec] | None, output_schema: type[BaseModel] | None
    ) -> str | None:
        if tools and not spec.capabilities.tools:
            return "verktyg"
        if output_schema is not None and not spec.capabilities.structured_output:
            return "strukturerade svar"
        return None

    def _provider_for(self, spec: ModelSpec, team: str | None) -> tuple[Provider, str | None]:
        if spec.provider in self._overrides:
            return self._overrides[spec.provider], None
        cache_key = (spec.provider, team)
        with self._lock:
            if cache_key in self._providers:
                return self._providers[cache_key]
        provider_config = self.config.providers[spec.provider]
        api_key, key_env = resolve_api_key(provider_config, team, self._environ)
        provider = create_provider(provider_config, api_key)
        with self._lock:
            return self._providers.setdefault(cache_key, (provider, key_env))

    @staticmethod
    def _build_response(
        result: ProviderResult,
        spec: ModelSpec,
        resolution: Resolution,
        started: float,
        tried: list[str],
    ) -> ModelResponse:
        return ModelResponse(
            text=result.text,
            tool_calls=result.tool_calls,
            stop_reason=result.stop_reason,
            usage=result.usage,
            cost_usd=spec.price.cost_usd(result.usage),
            provider=spec.provider,
            model=result.model,
            model_ref=spec.ref,
            requested=resolution.requested,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            request_id=result.request_id,
            fallback_from=tuple(tried),
            provider_state=result.provider_state,
        )

    @staticmethod
    def _parse_structured(response: ModelResponse, schema: type[BaseModel]) -> BaseModel:
        try:
            return schema.model_validate_json(response.text)
        except ValidationError as exc:
            raise StructuredOutputError(
                f"Svaret från {response.model_ref} validerar inte mot {schema.__name__}: {exc}",
                raw_text=response.text,
            ) from exc

    @staticmethod
    def _exhausted_error(resolution: Resolution, errors: list[Exception]) -> Exception:
        provider_errors = [e for e in errors if isinstance(e, ProviderError)]
        if provider_errors:
            return provider_errors[-1]
        missing = [e for e in errors if isinstance(e, MissingKeyError)]
        if missing:
            variables = [v for e in missing for v in e.variables]
            return MissingKeyError(
                f"Ingen API-nyckel för någon modell i '{resolution.requested}'. "
                f"Sätt minst en av: {', '.join(dict.fromkeys(variables))} i .env (se .env.example).",
                variables=variables,
            )
        return ConfigError(
            f"Ingen modell i '{resolution.requested}' kan ta emot förfrågan: "
            + "; ".join(str(e) for e in errors)
        )

    # --- spårbarhet --------------------------------------------------------

    def _base_record(
        self, spec: ModelSpec, resolution: Resolution, context: CallContext, tried: list[str]
    ) -> dict[str, Any]:
        return {
            "requested": resolution.requested,
            "model_ref": spec.ref,
            "provider": spec.provider,
            "model": spec.model,
            "run_id": context.run_id,
            "team": context.team,
            "agent": context.agent,
            "step": context.step,
            "fallback_from": list(tried),
        }

    def _trace_skip(
        self,
        spec: ModelSpec,
        resolution: Resolution,
        context: CallContext,
        tried: list[str],
        reason: str,
        error_type: str = "Unsupported",
    ) -> None:
        self._sink.record(
            CallRecord(
                outcome="skipped",
                error_type=error_type,
                error_message=reason[:500],
                **self._base_record(spec, resolution, context, tried),
            )
        )

    def _trace_error(
        self,
        spec: ModelSpec,
        resolution: Resolution,
        context: CallContext,
        tried: list[str],
        key_env: str | None,
        exc: ProviderError,
        started: float,
    ) -> None:
        self._sink.record(
            CallRecord(
                outcome="error",
                error_type=type(exc).__name__,
                error_message=str(exc)[:500],
                request_id=exc.request_id,
                key_env=key_env,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                **self._base_record(spec, resolution, context, tried),
            )
        )

    def _trace_ok(
        self,
        response: ModelResponse,
        context: CallContext,
        key_env: str | None,
        system: str | None,
        messages: Sequence[Message],
    ) -> None:
        content = None
        if self._log_content:
            content = {
                "system": system,
                "messages": [m.model_dump(exclude={"provider_state"}) for m in messages],
                "response_text": response.text,
                "tool_calls": [c.model_dump() for c in response.tool_calls],
            }
        usage = response.usage
        self._sink.record(
            CallRecord(
                outcome="ok",
                requested=response.requested,
                model_ref=response.model_ref,
                provider=response.provider,
                model=response.model,
                run_id=context.run_id,
                team=context.team,
                agent=context.agent,
                step=context.step,
                stop_reason=response.stop_reason,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_input_tokens=usage.cached_input_tokens,
                cache_write_tokens=usage.cache_write_tokens,
                reasoning_tokens=usage.reasoning_tokens,
                cost_usd=response.cost_usd,
                latency_ms=response.latency_ms,
                request_id=response.request_id,
                key_env=key_env,
                fallback_from=list(response.fallback_from),
                content=content,
            )
        )


_default_client: AIClient | None = None
_default_lock = threading.Lock()


def get_client() -> AIClient:
    """Delad standardklient (konfiguration ur ai_config.yaml / AI_CONFIG_FILE)."""
    global _default_client
    with _default_lock:
        if _default_client is None:
            _default_client = AIClient()
        return _default_client


def reset_client() -> None:
    """Glömmer standardklienten, t.ex. efter ändrad konfiguration eller i tester."""
    global _default_client
    with _default_lock:
        _default_client = None
