"""Leverantörsoberoende felhierarki för AI-lagret.

Adaptrarna i `ai.providers` översätter SDK-specifika undantag till dessa
klasser, så att agent- och skillkod aldrig behöver känna till `anthropic`-
eller `openai`-paketens felklasser. Se 02_system/ai_abstraktion.md §9.
"""

from __future__ import annotations


class AIError(Exception):
    """Basklass för alla fel från AI-lagret."""


class ConfigError(AIError):
    """Felaktig eller ofullständig konfiguration: okänd roll/modell, saknad nyckel m.m."""


class MissingKeyError(ConfigError):
    """Ingen API-nyckel hittades för en leverantör (och ev. team)."""

    def __init__(self, message: str, *, variables: list[str]) -> None:
        super().__init__(message)
        self.variables = variables


class StructuredOutputError(AIError):
    """Modellens svar gick inte att validera mot det begärda schemat.

    `stop_reason` är svarets slut, t.ex. `max_tokens` när svaret klipptes vid utdatataket.
    """

    def __init__(self, message: str, *, raw_text: str = "", stop_reason: str | None = None) -> None:
        super().__init__(message)
        self.raw_text = raw_text
        self.stop_reason = stop_reason


class ProviderError(AIError):
    """Ett anrop till en leverantör misslyckades.

    `fallback_eligible` anger om klienten får pröva nästa modell i rollens
    reservkedja. Det gäller fel som beror på leverantörens tillstånd
    (överbelastning, kvot, nätverk) – inte fel i själva anropet.
    """

    fallback_eligible: bool = False

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        model: str = "",
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.status_code = status_code
        self.request_id = request_id


class AuthenticationError(ProviderError):
    """Ogiltig eller obehörig API-nyckel (401/403)."""


class InvalidRequestError(ProviderError):
    """Leverantören avvisade anropet (400/404/413/422 m.fl.)."""


class RateLimitError(ProviderError):
    """För många anrop eller slut på kvot (429)."""

    fallback_eligible = True


class ProviderUnavailableError(ProviderError):
    """Leverantören är tillfälligt otillgänglig: 5xx, överbelastning, nätverk, timeout."""

    fallback_eligible = True
