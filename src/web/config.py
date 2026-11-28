"""Inställningar för handläggar-UI:t – läses ur miljön (och `.env`).

| Variabel          | Standard | Innehåll                                                       |
|-------------------|----------|----------------------------------------------------------------|
| `HANDLAGGARE_ID`  | `karl`   | Handläggarens id – aktören `Actor.human(id)` i händelseloggen  |
| `HANDLAGGARE_DB`  | `demo`   | `demo` (lokal SQLite), `svc_test` (isolerad Postgres) eller    |
|                   |          | `lakebase` (beståndet via `DATABASE_URL` – bara uttryckligen)  |

Lakebase-beståndet väljs aldrig av sig självt: `DATABASE_URL` finns i `.env`
men används bara med `HANDLAGGARE_DB=lakebase`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from web.development_github import DEFAULT_REPOSITORY, REPOSITORY_PATTERN

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Databaser UI:t kan köras mot, med etikett för sidhuvudet.
DATABASES = {
    "demo": "DEMO – lokal övningsdata",
    "svc_test": "TEST – separat testbestånd",
    "lakebase": "Lakebase – gemensamt bestånd",
}

DEFAULT_PORTS = {"lakebase": 8765, "svc_test": 8766, "demo": 8767}
SWITCHABLE_DATABASES = {
    "lakebase": "Lakebase – gemensamt bestånd (Postgres)",
    "demo": "Demo – lokal övningsdata (SQLite)",
}

_HANDLER_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,99}$")


class WebConfigError(ValueError):
    """Ogiltig inställning för handläggar-UI:t."""


@dataclass(frozen=True)
class WebSettings:
    handler_id: str = "karl"
    database: str = "demo"
    demo_path: Path = REPO_ROOT / "data" / "handlaggare_demo.db"  # *.db är gitignorerat
    #: Värdar som får anropa UI:t (Host-huvudet) – skydd mot DNS-rebinding
    allowed_hosts: tuple[str, ...] = field(default=("127.0.0.1", "localhost"))
    operator_manifest: Path | None = None
    operator_dataset_id: str | None = None
    operator_id: str = "karl"
    operator_password_hash: str | None = field(default=None, repr=False)
    handler_login_id: str = "handlaggare"
    handler_password_hash: str | None = field(default=None, repr=False)
    # Webbstarter från miljön använder plattformsinloggning. Explicita äldre
    # appinstanser kan fortfarande använda den avgränsade operatörsinloggningen.
    portal_login: bool = False
    actuary_workspace: bool = False
    company_orchestrator: bool = False
    development_github_repository: str = DEFAULT_REPOSITORY
    development_github_token: str | None = field(default=None, repr=False)
    #: Simulerad affärsdag för en lokal provkörning (paket B steg 8, Z13): visas i sidhuvudet och sätts per
    #: förfrågan av `python -m web --affarsdag`. Aldrig mot Lakebase.
    business_day: date | None = None
    #: Demodatabasens schema lämnas som det är (inga tabeller läggs till) – för prov utan steg 4–7 (Z13)
    keep_schema: bool = False

    def __post_init__(self) -> None:
        if not _HANDLER_ID.match(self.handler_id):
            raise WebConfigError(
                f"Ogiltigt HANDLAGGARE_ID '{self.handler_id}' – små bokstäver, siffror, _ . -, högst 100 tecken"
            )
        if self.database not in DATABASES:
            raise WebConfigError(
                f"Okänd databas '{self.database}' – välj {', '.join(DATABASES)} (HANDLAGGARE_DB)"
            )
        if (self.business_day is not None or self.keep_schema) and self.database != "demo":
            raise WebConfigError("Simulerad affärsdag och oförändrat schema gäller bara den lokala demodatabasen")
        if self.operator_dataset_id is not None and not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,100}", self.operator_dataset_id):
            raise WebConfigError("OPERATOR_DATASET_ID ska vara en kort datasetreferens utan personuppgifter")
        if not _HANDLER_ID.fullmatch(self.operator_id):
            raise WebConfigError("Ogiltigt OPERATOR_ID – små bokstäver, siffror, _ . -, högst 100 tecken")
        if not _HANDLER_ID.fullmatch(self.handler_login_id):
            raise WebConfigError("Ogiltigt HANDLAGGARE_LOGIN_ID – små bokstäver, siffror, _ . -, högst 100 tecken")
        if self.handler_password_hash and self.handler_login_id == self.operator_id:
            raise WebConfigError("Handläggare och operatör måste ha olika inloggningsnamn")
        if not re.fullmatch(REPOSITORY_PATTERN, self.development_github_repository):
            raise WebConfigError("DEVELOPMENT_GITHUB_REPOSITORY ska anges som ägare/repo")
        from web.operator_auth import validate_password_hash

        try:
            validate_password_hash(self.operator_password_hash)
            validate_password_hash(self.handler_password_hash, variable="HANDLAGGARE_PASSWORD_HASH")
        except ValueError as exc:
            raise WebConfigError(str(exc)) from None

    @property
    def dataset_ref(self) -> str:
        return self.operator_dataset_id or f"{self.database}:current"

    @property
    def database_label(self) -> str:
        return DATABASES[self.database]

    @property
    def is_production(self) -> bool:
        """Sant mot Lakebase-beståndet – UI:t visar då en tydlig varning."""
        return self.database == "lakebase"

    @classmethod
    def from_env(cls) -> WebSettings:
        if load_dotenv is not None:
            load_dotenv()
        return cls(
            handler_id=os.environ.get("HANDLAGGARE_ID", "karl").strip() or "karl",
            database=os.environ.get("HANDLAGGARE_DB", "demo").strip() or "demo",
            operator_manifest=Path(os.environ["OPERATOR_TELEMETRY_MANIFEST"]) if os.environ.get("OPERATOR_TELEMETRY_MANIFEST") else None,
            operator_dataset_id=os.environ.get("OPERATOR_DATASET_ID") or None,
            operator_id=os.environ.get("OPERATOR_ID", "karl").strip() or "karl",
            operator_password_hash=os.environ.get("OPERATOR_PASSWORD_HASH") or None,
            handler_login_id=os.environ.get("HANDLAGGARE_LOGIN_ID", "handlaggare").strip() or "handlaggare",
            handler_password_hash=os.environ.get("HANDLAGGARE_PASSWORD_HASH") or None,
            portal_login=True,
            actuary_workspace=_enabled("WEB_ACTUARY_WORKSPACE"),
            company_orchestrator=_enabled("WEB_COMPANY_ORCHESTRATOR"),
            development_github_repository=os.environ.get("DEVELOPMENT_GITHUB_REPOSITORY", DEFAULT_REPOSITORY).strip(),
            development_github_token=(os.environ.get("DEVELOPMENT_GITHUB_TOKEN") or "").strip() or None,
        )


def _enabled(variable: str) -> bool:
    value = (os.environ.get(variable) or "").strip().lower()
    if value not in {"", "0", "1", "false", "true"}:
        raise WebConfigError(f"{variable} måste vara true eller false")
    return value in {"1", "true"}
