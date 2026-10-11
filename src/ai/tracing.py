"""Anropslogg för AI-lagret (02_system/ai_abstraktion.md §10).

Varje försök – lyckat, misslyckat eller överhoppat – blir en `CallRecord`.
Standard är en JSONL-fil under `logs/` (gitignorerad). Promptinnehåll loggas
bara om det uttryckligen slagits på (B-006).
"""

from __future__ import annotations

import os
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from ai.config import TracingConfig


class CallRecord(BaseModel):
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="milliseconds")
    )
    outcome: Literal["ok", "error", "skipped"]
    requested: str
    model_ref: str
    provider: str
    model: str
    run_id: str | None = None
    team: str | None = None
    agent: str | None = None
    step: str | None = None
    stop_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float | None = None
    latency_ms: float | None = None
    request_id: str | None = None
    key_env: str | None = None  # namnet på nyckelvariabeln, aldrig värdet
    fallback_from: list[str] = Field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    content: dict[str, Any] | None = None  # bara med log_content


class TraceSink(Protocol):
    def record(self, record: CallRecord) -> None: ...


class NullTraceSink:
    def record(self, record: CallRecord) -> None:
        pass


class MemoryTraceSink:
    """Samlar poster i minnet – för tester."""

    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    def record(self, record: CallRecord) -> None:
        self.records.append(record)


class JsonlTraceSink:
    """Trådsäker append-only JSONL-fil."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def record(self, record: CallRecord) -> None:
        line = record.model_dump_json(exclude_none=True)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


def project_root() -> Path:
    """Repo-roten när koden körs från källträdet, annars arbetskatalogen."""
    candidate = Path(__file__).resolve().parents[2]
    return candidate if (candidate / "pyproject.toml").exists() else Path.cwd()


def sink_from_config(
    config: TracingConfig, environ: Mapping[str, str] | None = None
) -> TraceSink:
    environ = os.environ if environ is None else environ
    if config.sink == "none":
        return NullTraceSink()
    path = Path(environ.get("AI_TRACE_FILE") or config.path)
    if not path.is_absolute():
        path = project_root() / path
    return JsonlTraceSink(path)


def log_content_enabled(config: TracingConfig, environ: Mapping[str, str] | None = None) -> bool:
    environ = os.environ if environ is None else environ
    override = (environ.get("AI_LOG_CONTENT") or "").strip().lower()
    if override:
        return override in ("1", "true", "yes", "ja")
    return config.log_content
