"""Leverantörsadaptrar – det enda stället i kodbasen som importerar AI-SDK:er.

Adaptrarna importeras först när de behövs, så att ett saknat SDK bara ger
fel om leverantören faktiskt används.
"""

from __future__ import annotations

import importlib

from ai.config import ProviderConfig
from ai.providers.base import Provider, ProviderRequest, ProviderResult

_ADAPTERS = {
    "anthropic": ("ai.providers.anthropic_provider", "AnthropicProvider"),
    "openai": ("ai.providers.openai_provider", "OpenAIProvider"),
    "fake": ("ai.providers.fake", "FakeProvider"),
}


def create_provider(config: ProviderConfig, api_key: str | None) -> Provider:
    module_name, class_name = _ADAPTERS[config.type]
    adapter = getattr(importlib.import_module(module_name), class_name)
    return adapter.from_config(config, api_key)


__all__ = ["Provider", "ProviderRequest", "ProviderResult", "create_provider"]
