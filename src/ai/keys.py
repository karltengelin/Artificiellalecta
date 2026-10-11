"""Val av API-nyckel per leverantör och team.

Konvention (02_system/ai_abstraktion.md §7): team-nyckeln heter
`<api_key_env>_<TEAM-ID I VERSALER>`, t.ex. `ANTHROPIC_API_KEY_KAPITAL`.
Saknas den används den gemensamma nyckeln `<api_key_env>`.

Nycklar lämnar aldrig denna modul och adaptrarna – de loggas inte och når
aldrig prompt eller agentkontext. Bara variabelns *namn* rapporteras vidare.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from ai.config import ProviderConfig
from ai.errors import MissingKeyError

try:
    # python-dotenv är en mjuk dep – om den finns laddar vi .env automatiskt
    # (samma mönster som utils/db.py)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def candidate_key_vars(provider: ProviderConfig, team: str | None) -> list[str]:
    """Miljövariabler som provas, i ordning."""
    if not provider.api_key_env:
        return []
    names = []
    if team:
        names.append(f"{provider.api_key_env}_{team.upper()}")
    names.append(provider.api_key_env)
    return names


def resolve_api_key(
    provider: ProviderConfig,
    team: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """Returnerar (nyckel, variabelnamn). Leverantörer utan nyckel ger (None, None)."""
    environ = os.environ if environ is None else environ
    names = candidate_key_vars(provider, team)
    if not names:
        return None, None
    for name in names:
        value = (environ.get(name) or "").strip()
        if value:
            return value, name
    raise MissingKeyError(
        f"Ingen API-nyckel för leverantören '{provider.name}'. "
        f"Sätt {' eller '.join(names)} i .env (se .env.example).",
        variables=names,
    )
