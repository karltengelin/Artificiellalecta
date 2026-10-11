"""Konfiguration av AI-lagret: leverantörer, modeller, roller och loggning.

Standardkonfigurationen ligger i `ai_config.yaml` bredvid denna fil och kan
ersättas via miljövariabeln `AI_CONFIG_FILE`. En rolls primärmodell kan
överstyras med `AI_ROLE_<ROLL>=leverantör:modell` (jämförande utvärdering,
B-009). Se 02_system/ai_abstraktion.md §6.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from ai.errors import ConfigError
from ai.types import Effort, Usage

DEFAULT_CONFIG_PATH = Path(__file__).with_name("ai_config.yaml")


class Price(BaseModel):
    """Pris i USD per 1M tokens. Cachepriser faller tillbaka på inputpriset."""

    input: float
    output: float
    cached_input: float | None = None
    cache_write: float | None = None

    def cost_usd(self, usage: Usage) -> float:
        cached = usage.cached_input_tokens
        written = usage.cache_write_tokens
        uncached = max(usage.input_tokens - cached - written, 0)
        total = (
            uncached * self.input
            + cached * (self.cached_input if self.cached_input is not None else self.input)
            + written * (self.cache_write if self.cache_write is not None else self.input)
            + usage.output_tokens * self.output
        )
        return round(total / 1_000_000, 6)


class Capabilities(BaseModel):
    """Vad modellen klarar – avgör om en förfrågan kan skickas till den."""

    tools: bool = True
    structured_output: bool = True
    effort: bool = False


class ModelSpec(BaseModel):
    ref: str  # "anthropic:claude-opus-5"
    provider: str  # nyckel under providers:
    model: str  # leverantörens modell-ID
    price: Price
    capabilities: Capabilities = Field(default_factory=Capabilities)
    options: dict[str, Any] = Field(default_factory=dict)  # adapterspecifika flaggor


class ProviderConfig(BaseModel):
    name: str
    type: Literal["anthropic", "openai", "fake"]
    api_key_env: str | None = None  # gemensam nyckel; team-nyckel = <api_key_env>_<TEAM>
    base_url: str | None = None
    max_retries: int = 2
    timeout_seconds: float = 300.0


class RoleSpec(BaseModel):
    model: str
    fallbacks: list[str] = Field(default_factory=list)
    effort: Effort | None = None
    max_output_tokens: int | None = None


class Defaults(BaseModel):
    role: str = "standard"
    max_output_tokens: int = 16000


class TracingConfig(BaseModel):
    sink: Literal["jsonl", "none"] = "jsonl"
    path: str = "logs/ai_calls.jsonl"
    log_content: bool = False


@dataclass(frozen=True)
class Resolution:
    """Resultatet av att slå upp en modellreferens."""

    requested: str
    chain: tuple[ModelSpec, ...]  # primär först, därefter reserver
    effort: Effort | None
    max_output_tokens: int


class AIConfig(BaseModel):
    providers: dict[str, ProviderConfig]
    models: dict[str, ModelSpec]
    roles: dict[str, RoleSpec]
    defaults: Defaults = Field(default_factory=Defaults)
    tracing: TracingConfig = Field(default_factory=TracingConfig)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AIConfig:
        """Bygger konfigurationen ur YAML-strukturen och validerar referenser."""
        try:
            providers = {
                name: ProviderConfig(name=name, **(spec or {}))
                for name, spec in (data.get("providers") or {}).items()
            }
            models = {}
            for ref, spec in (data.get("models") or {}).items():
                provider, sep, model = ref.partition(":")
                if not sep or not provider or not model:
                    raise ConfigError(
                        f"Modellreferensen '{ref}' ska ha formen leverantör:modell"
                    )
                models[ref] = ModelSpec(ref=ref, provider=provider, model=model, **(spec or {}))
            config = cls(
                providers=providers,
                models=models,
                roles={
                    name: RoleSpec(**(spec or {}))
                    for name, spec in (data.get("roles") or {}).items()
                },
                defaults=Defaults(**(data.get("defaults") or {})),
                tracing=TracingConfig(**(data.get("tracing") or {})),
            )
        except ValidationError as exc:
            raise ConfigError(f"Ogiltig AI-konfiguration: {exc}") from exc
        config._validate_references()
        return config

    def _validate_references(self) -> None:
        for spec in self.models.values():
            if spec.provider not in self.providers:
                raise ConfigError(
                    f"Modellen '{spec.ref}' hänvisar till okänd leverantör '{spec.provider}'"
                )
        for name, role in self.roles.items():
            for ref in (role.model, *role.fallbacks):
                if ref not in self.models:
                    raise ConfigError(f"Rollen '{name}' hänvisar till okänd modell '{ref}'")
        if self.defaults.role not in self.roles:
            raise ConfigError(f"Standardrollen '{self.defaults.role}' finns inte under roles")

    def resolve(
        self, ref: str | None = None, environ: Mapping[str, str] | None = None
    ) -> Resolution:
        """Slår upp en roll (t.ex. "deep") eller en explicit "leverantör:modell"."""
        environ = os.environ if environ is None else environ
        requested = ref or self.defaults.role

        if requested in self.roles:
            role = self.roles[requested]
            primary = environ.get(f"AI_ROLE_{requested.upper()}", "").strip() or role.model
            refs = [primary, *(f for f in role.fallbacks if f != primary)]
            effort = role.effort
            max_tokens = role.max_output_tokens or self.defaults.max_output_tokens
        elif requested in self.models:
            refs = [requested]
            effort = None
            max_tokens = self.defaults.max_output_tokens
        else:
            raise ConfigError(
                f"Okänd modellroll eller modell: '{requested}'. "
                f"Roller: {', '.join(sorted(self.roles))}. "
                f"Modeller: {', '.join(sorted(self.models))}"
            )

        unknown = [r for r in refs if r not in self.models]
        if unknown:
            raise ConfigError(
                f"Modellen '{unknown[0]}' finns inte under models: i AI-konfigurationen"
            )
        return Resolution(
            requested=requested,
            chain=tuple(self.models[r] for r in refs),
            effort=effort,
            max_output_tokens=max_tokens,
        )


def load_config(
    path: str | Path | None = None, environ: Mapping[str, str] | None = None
) -> AIConfig:
    """Läser konfigurationen från fil (argument > AI_CONFIG_FILE > standardfilen)."""
    environ = os.environ if environ is None else environ
    config_path = Path(path or environ.get("AI_CONFIG_FILE") or DEFAULT_CONFIG_PATH)
    if not config_path.exists():
        raise ConfigError(f"AI-konfigurationen hittades inte: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AIConfig.from_dict(data)
