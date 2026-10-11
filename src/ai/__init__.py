"""Modellagnostiskt AI-abstraktionslager (B-009, B-025).

Agent- och skillkod importerar bara härifrån – aldrig från `ai.providers`
eller direkt från `anthropic`/`openai`. Specifikation:
02_system/ai_abstraktion.md.

    from ai import get_client
    ai = get_client().bind(team="forsakring", agent="handlaggaragent", run_id=run_id)
    svar = ai.ask("Sammanfatta ärendet ...", model="standard")
"""

from ai.client import AIClient, get_client, reset_client
from ai.config import AIConfig, load_config
from ai.errors import (
    AIError,
    AuthenticationError,
    ConfigError,
    InvalidRequestError,
    MissingKeyError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
    StructuredOutputError,
)
from ai.types import (
    CallContext,
    Effort,
    Message,
    ModelResponse,
    StopReason,
    ToolCall,
    ToolResult,
    ToolSpec,
    Usage,
)

__all__ = [
    "AIClient",
    "AIConfig",
    "AIError",
    "AuthenticationError",
    "CallContext",
    "ConfigError",
    "Effort",
    "InvalidRequestError",
    "Message",
    "MissingKeyError",
    "ModelResponse",
    "ProviderError",
    "ProviderUnavailableError",
    "RateLimitError",
    "StopReason",
    "StructuredOutputError",
    "ToolCall",
    "ToolResult",
    "ToolSpec",
    "Usage",
    "get_client",
    "load_config",
    "reset_client",
]
