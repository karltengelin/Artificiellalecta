"""Protokollet mellan klienten och leverantörsadaptrarna."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Protocol

from ai.errors import (
    AuthenticationError,
    InvalidRequestError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
)
from ai.types import Effort, Message, ProviderState, StopReason, ToolCall, ToolSpec, Usage


@dataclass(frozen=True)
class ProviderRequest:
    """En färdigupplöst förfrågan till en specifik modell hos en leverantör."""

    model: str  # leverantörens modell-ID
    messages: tuple[Message, ...]
    system: str | None = None
    tools: tuple[ToolSpec, ...] = ()
    output_schema: dict[str, Any] | None = None  # strikt JSON Schema
    output_schema_name: str = "response"
    max_output_tokens: int = 16000
    effort: Effort | None = None  # redan filtrerad mot modellens förmågor
    options: Mapping[str, Any] = field(default_factory=dict)  # ModelSpec.options


@dataclass(frozen=True)
class ProviderResult:
    text: str
    tool_calls: tuple[ToolCall, ...]
    stop_reason: StopReason
    usage: Usage
    model: str  # modell-ID enligt leverantörens svar
    request_id: str | None = None
    provider_state: ProviderState | None = None


class Provider(Protocol):
    def complete(self, request: ProviderRequest) -> ProviderResult: ...


def map_sdk_error(
    exc: Exception, sdk: ModuleType, *, provider: str, model: str
) -> ProviderError:
    """Översätter ett SDK-undantag till den kanoniska felhierarkin.

    `anthropic`- och `openai`-paketen har samma namn på sina felklasser, så
    samma översättning fungerar för båda. SDK:erna har då redan gjort sina
    egna omförsök (max_retries) för 408/409/429/5xx och nätverksfel.
    """
    status = getattr(exc, "status_code", None)
    kwargs = {
        "provider": provider,
        "model": model,
        "status_code": status,
        "request_id": getattr(exc, "request_id", None),
    }
    message = str(exc)
    if isinstance(exc, (sdk.AuthenticationError, sdk.PermissionDeniedError)):
        return AuthenticationError(message, **kwargs)
    if isinstance(exc, sdk.RateLimitError):
        return RateLimitError(message, **kwargs)
    if isinstance(exc, sdk.APIConnectionError):  # inklusive timeout
        return ProviderUnavailableError(message, **kwargs)
    if isinstance(exc, sdk.APIStatusError):
        if status is not None and status >= 500:
            return ProviderUnavailableError(message, **kwargs)
        return InvalidRequestError(message, **kwargs)
    return ProviderError(message, **kwargs)
