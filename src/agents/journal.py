"""Körjournal: vad agenten gjorde och varför (Fas 3b-6, harness.md §8).

En JSON-händelse per rad i `logs/agent_runs/<run_id>.jsonl` (gitignorerat). Varje rad
har schema_version, event_id, löpande seq, UTC-tid, run-id, rot- och fortsättnings-id,
team, agent, steg och typ.

Händelsetyper i v1: run_started, policy_resolved, model_returned, tool_denied,
tool_intent, tool_completed, approval_wait, approval_observed, run_ended.

Inga råa personuppgifter: indata och resultat sparas som sha256-hash. Fri text från
uppdraget eller modellen – mål, motiveringar, sammanfattning, anteckningar vid avslag –
sparas bara som hash och längd (`text_ref`), eftersom den kan innehålla namn och
födelsedatum som ingen maskering hittar säkert (röktestet 2026-10-24). Systemets egna
meddelanden (stoppskäl, felklasser) maskeras – långa sifferföljder och e-postadresser.
Leverantörstillstånd och nycklar journalförs aldrig. Fulltexten finns i resultatet till
den betrodda anroparen; råa uppgifter i tjänstelagrets händelselogg och godkännandekö,
som har egen åtkomst.

En skrivare per körning: filen skapas exklusivt, så två körningar kan inte skriva i
samma journal. Varje rad skrivs och synkas till disk innan motorn går vidare – kan
den inte sparas stoppar körningen före nästa handling (harness.md §6.4).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from agents.ecosystem import REPO_ROOT
from agents.errors import HarnessError

SCHEMA_VERSION = 1
DEFAULT_JOURNAL_DIR = REPO_ROOT / "logs" / "agent_runs"

_DIGITS = re.compile(r"\d{6,}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


class JournalError(HarnessError):
    """Journalen kunde inte skrivas eller läsas – stoppa före nästa handling."""


class Journal(Protocol):
    def append(self, type: str, **fields: Any) -> dict[str, Any]: ...


def mask(text: str | None) -> str | None:
    """Maskerar identifierare i fri text innan den journalförs."""
    if text is None:
        return None
    return _EMAIL.sub("[e-post]", _DIGITS.sub("[maskerat]", text))


def text_ref(text: str | None) -> dict[str, Any] | None:
    """Fri text som kan innehålla personuppgifter: bara hash och längd i journalen."""
    if text is None:
        return None
    return {"sha256": digest(text), "length": len(text)}


def digest(value: Any) -> str:
    """sha256 av kanonisk JSON – visar att samma underlag användes utan att lagra det."""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class _BaseJournal:
    def __init__(
        self, *, run_id: str, team: str, agent: str, root_run_id: str | None = None,
        continuation_of: str | None = None, parent_run_id: str | None = None,
    ) -> None:
        self.run_id = run_id
        self._common = {
            "run_id": run_id,
            "root_run_id": root_run_id or run_id,
            "parent_run_id": parent_run_id,
            "continuation_of": continuation_of,
            "team": team,
            "agent": agent,
        }
        self._seq = 0

    def _event(self, type: str, fields: dict[str, Any]) -> dict[str, Any]:
        self._seq += 1
        return {
            "schema_version": SCHEMA_VERSION,
            "event_id": uuid.uuid4().hex,
            "seq": self._seq,
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            **self._common,
            "step": fields.pop("step", None),
            "type": type,
            **fields,
        }


class MemoryJournal(_BaseJournal):
    """Journal i minnet – för tester."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.events: list[dict[str, Any]] = []

    def append(self, type: str, **fields: Any) -> dict[str, Any]:
        event = self._event(type, fields)
        json.dumps(event, ensure_ascii=False)  # samma krav som filjournalen: serialiserbart
        self.events.append(event)
        return event


class FileJournal(_BaseJournal):
    """JSONL-fil per körning, en skrivare, synkad till disk efter varje rad."""

    def __init__(self, directory: Path | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        directory = directory or DEFAULT_JOURNAL_DIR
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.run_id):
            raise JournalError(f"Ogiltigt run-id för journalfil: {self.run_id!r}")
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self.path = directory / f"{self.run_id}.jsonl"
            self._file = self.path.open("x", encoding="utf-8")  # exklusivt: en skrivare per körning
        except FileExistsError:
            raise JournalError(f"Journalen för {self.run_id} finns redan – en körning per run-id") from None
        except OSError as exc:
            raise JournalError(f"Journalen kunde inte skapas: {exc}") from exc

    def append(self, type: str, **fields: Any) -> dict[str, Any]:
        event = self._event(type, fields)
        try:
            self._file.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._file.flush()
            os.fsync(self._file.fileno())
        except (OSError, TypeError, ValueError) as exc:
            raise JournalError(f"Journalraden kunde inte sparas: {exc}") from exc
        return event

    def close(self) -> None:
        self._file.close()


def read_journal(path: Path) -> tuple[list[dict[str, Any]], bool]:
    """Händelserna i en journal och om sista raden är skadad (avbruten skrivning).

    En skadad rad skrivs aldrig om – den rapporteras, och den som läser stämmer av.
    """
    events: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                return events, True
            raise JournalError(f"Journalen {path} är skadad på rad {i + 1}") from None
    return events, False
