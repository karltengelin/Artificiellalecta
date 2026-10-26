"""Idempotent lokal läsprojektion av uttryckligt anslutna loggkällor (OC-2).

Manifestet är betrodd driftkonfiguration, aldrig HTTP-indata. Indexet lagrar
bara tillåtna metadata, inga prompter, feltexter, ärenden eller artefaktinnehåll.
SDK-omförsök saknar full täckning i dagens AI-logg: ingen summa märks komplett.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TEAM_NAMES = {
    "forsakring": "Försäkring", "compliance": "Compliance", "aktuarie": "Aktuarie",
    "kapital": "Kapitalförvaltning", "ekonomi": "Ekonomi", "kommunikation": "Kommunikation",
    "utveckling": "Utveckling",
}
STATUSES = {
    "completed": "Körsegment avslutat", "waiting_approval": "Väntar på godkännande",
    "needs_compliance": "Behöver compliance", "needs_human": "Behöver operatör",
    "blocked": "Blockerat", "failed": "Fel", "limit_reached": "Tak nått",
    "reconciliation_required": "Kräver avstämning", "running": "Senast startat – aktivt läge ej verifierat",
}


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    path: str
    kind: Literal["calls", "journal"]
    environment_id: Literal["demo", "svc_test", "lakebase"] | None = None
    dataset_ref: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_.:-]{1,100}$")

    @model_validator(mode="after")
    def scope_pair(self):
        if (self.environment_id is None) != (self.dataset_ref is None):
            raise ValueError("Miljö och dataset ska anges tillsammans")
        return self


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    sources: tuple[Source, ...] = Field(max_length=20)


class Entry(BaseModel):
    """Endast dessa fält får passera till den lokala projektionen."""
    timestamp: datetime
    schema_version: Literal[1] = 1
    event_id: str | None = Field(default=None, max_length=100)
    attempt_id: str | None = Field(default=None, max_length=100)
    seq: int | None = Field(default=None, gt=0)
    type: str | None = Field(default=None, max_length=64)
    outcome: Literal["ok", "error", "skipped"] | None = None
    # Representationsgräns för trasiga loggar, inte ett verkställt kostnadstak.
    cost_usd: Decimal | None = Field(default=None, ge=0, le=1000000, allow_inf_nan=False)
    team: str | None = Field(default=None, max_length=64)
    model_ref: str | None = Field(default=None, max_length=150)
    run_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    task_id: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, max_length=64)
    price_version: str | None = Field(default=None, max_length=100)

    @field_validator("timestamp")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("Tidszon krävs")
        return value.astimezone(UTC)


@dataclass
class CostRow:
    team: str
    model: str
    task: str
    known: Decimal = Decimal(0)
    unknown: int = 0
    attempts: int = 0


@dataclass
class Telemetry:
    checked_at: datetime
    known: Decimal | None = None
    unknown: int | None = None
    attempts: int = 0
    unallocated_known: Decimal | None = None
    unallocated_unknown: int = 0
    rows: list[CostRow] = field(default_factory=list)
    runs: dict[str, dict[str, int]] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    sources: int = 0
    coverage: str = "missing"
    last_event_at: datetime | None = None
    freshness: str = "missing"
    last_success_at: datetime | None = None


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def read_telemetry(manifest_path: Path | None, *, environment_id: str, dataset_ref: str,
                   period: tuple[date, date], known_models: set[str], now: datetime | None = None) -> Telemetry:
    now = now or datetime.now(UTC)
    result = Telemetry(checked_at=now)
    if manifest_path is None:
        result.issues.append("Ingen loggkälla är ansluten. Kostnad och körläge är okända, inte noll.")
        return result
    try:
        if manifest_path.stat().st_size > 65536:
            raise ValueError("Manifestet är för stort")
        manifest = Manifest.model_validate_json(manifest_path.read_bytes())
        root = manifest_path.resolve().parent
        # Indexet är härlett och lokalt. Aldrig en migration mot Lakebase.
        with closing(sqlite3.connect(root / "operator_index.db", timeout=10)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, source TEXT, hash TEXT, data TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS quarantined (source TEXT PRIMARY KEY)")
            db.execute("CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, scope TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS checks (source TEXT PRIMARY KEY, last_success TEXT)")
            active: set[str] = set()
            total_bytes = 0
            declarations: dict[str, tuple] = {}
            for source in manifest.sources:
                scope = (source.kind, source.environment_id, source.dataset_ref)
                if source.source_id in declarations and declarations[source.source_id] != scope:
                    db.execute("INSERT OR IGNORE INTO quarantined VALUES (?)", (source.source_id,))
                declarations[source.source_id] = scope
                active.add(source.source_id)
                old_scope = db.execute("SELECT scope FROM sources WHERE id=?", (source.source_id,)).fetchone()
                if old_scope and old_scope[0] != json.dumps(scope):
                    db.execute("INSERT OR IGNORE INTO quarantined VALUES (?)", (source.source_id,))
                db.execute("INSERT OR IGNORE INTO sources VALUES (?, ?)", (source.source_id, json.dumps(scope)))
                try:
                    path = (root / source.path).resolve()
                    if not path.is_relative_to(root) or path.is_symlink() or path.suffix != ".jsonl":
                        raise ValueError("Otillåten loggsökväg")
                    if path.stat().st_size > 16 * 1024 * 1024:
                        raise ValueError("Källan är för stor")
                    raw = path.read_bytes()
                    total_bytes += len(raw)
                    if total_bytes > 64 * 1024 * 1024:
                        raise ValueError("För stort sammanlagt underlag")
                    offset = 0
                    expected_seq = 1
                    for line_number, line in enumerate(raw.splitlines(keepends=True), 1):
                        position = offset
                        offset += len(line)
                        if not line.strip():
                            continue
                        try:
                            if len(line) > 1024 * 1024 or line_number > 100000:
                                raise ValueError("Logggräns nådd")
                            original = json.loads(line)
                            entry = Entry.model_validate(original)
                            if entry.timestamp > now:
                                raise ValueError("Framtida loggtid")
                            for key in ("environment_id", "dataset_ref"):
                                if original.get(key) is not None and original[key] != getattr(source, key):
                                    raise ValueError("Källans miljö motsäger manifestet")
                            if source.kind == "calls" and entry.outcome is None:
                                raise ValueError("Försöksutfall saknas")
                            if source.kind == "journal":
                                if not entry.event_id or not entry.run_id or entry.seq != expected_seq:
                                    raise ValueError("Journalidentitet eller sekvenslucka")
                                expected_seq += 1
                            stable = (f"{source.environment_id}:{source.dataset_ref}:attempt:{entry.attempt_id}"
                                      if source.kind == "calls" and entry.attempt_id else
                                      f"{source.environment_id}:{source.dataset_ref}:journal:{entry.event_id}"
                                      if source.kind == "journal" else f"{source.source_id}:{position}")
                            identity = _digest(stable)
                            fingerprint = hashlib.sha256(line.rstrip(b"\r\n")).hexdigest()
                            old = db.execute("SELECT source, hash FROM entries WHERE id=?", (identity,)).fetchone()
                            if old and old[1] != fingerprint:
                                for conflict in (old[0], source.source_id):
                                    db.execute("INSERT OR IGNORE INTO quarantined VALUES (?)", (conflict,))
                                continue
                            # Fri uppdragstext kan innehålla PII; visa en stabil hashreferens.
                            safe = entry.model_dump(mode="json", exclude={"task_id", "event_id", "attempt_id", "price_version"})
                            safe["task_ref"] = "UPP-" + _digest(entry.task_id)[:10] if entry.task_id else None
                            safe["team"] = entry.team if entry.team in TEAM_NAMES else None
                            safe["model_ref"] = entry.model_ref if entry.model_ref in known_models else None
                            safe["status"] = entry.status if entry.status in STATUSES else None
                            safe["type"] = entry.type if entry.type in {"run_started", "run_ended"} else None
                            safe.update(kind=source.kind, environment_id=source.environment_id, dataset_ref=source.dataset_ref)
                            db.execute("INSERT OR IGNORE INTO entries VALUES (?, ?, ?, ?)",
                                       (identity, source.source_id, fingerprint, json.dumps(safe)))
                        except (ValueError, TypeError):
                            result.issues.append("En loggrad eller journalsekvens kunde inte verifieras; täckningen är ofullständig.")
                    result.sources += 1
                    db.execute("INSERT OR REPLACE INTO checks VALUES (?, ?)", (source.source_id, now.isoformat()))
                except (OSError, ValueError):
                    result.issues.append("En deklarerad loggkälla kunde inte läsas säkert; tidigare indexposter är endast känt delunderlag.")
            quarantined = {r[0] for r in db.execute("SELECT source FROM quarantined")}
            if quarantined & active:
                result.issues.append("Motstridigt innehåll eller miljö för samma källidentitet: källan är i karantän.")
            rows = [json.loads(data) for source, data in db.execute("SELECT source, data FROM entries")
                    if source in active and source not in quarantined]
            checks = {source: datetime.fromisoformat(when) for source, when in db.execute("SELECT source, last_success FROM checks")}
    except (OSError, ValueError, sqlite3.Error):
        result.issues = ["Loggmanifest eller lokalt index kunde inte verifieras. Inga kostnadstotaler visas."]
        return result

    groups: dict[tuple[str, str, str], CostRow] = {}
    run_states: dict[str, tuple[datetime, str, str]] = {}
    tasks = {}
    for item in rows:
        if item["kind"] == "journal" and item["type"] == "run_started" and item["task_ref"]:
            tasks[(item["environment_id"], item["dataset_ref"], item["run_id"])] = item["task_ref"]
    start = datetime.combine(period[0], datetime.min.time(), UTC)
    end = datetime.combine(period[1], datetime.min.time(), UTC)
    for item in rows:
        timestamp = datetime.fromisoformat(item["timestamp"])
        scoped = item["environment_id"] == environment_id and item["dataset_ref"] == dataset_ref
        if not start <= timestamp < end:
            continue
        if item["kind"] == "journal" and scoped and item["team"]:
            status = item["status"] if item["type"] == "run_ended" else "running" if item["type"] == "run_started" else None
            if status in STATUSES and (item["run_id"] not in run_states or timestamp >= run_states[item["run_id"]][0]):
                run_states[item["run_id"]] = (timestamp, item["team"], status)
            continue
        if item["kind"] != "calls" or not (scoped or item["environment_id"] is None):
            continue
        amount = Decimal(str(item["cost_usd"])) if item["cost_usd"] is not None else None
        if not scoped:
            result.unallocated_known = (result.unallocated_known or Decimal(0)) + (amount or Decimal(0))
            result.unallocated_unknown += amount is None
            continue
        result.known = (result.known or Decimal(0)) + (amount or Decimal(0))
        result.unknown = (result.unknown or 0) + (amount is None)
        result.attempts += 1
        result.last_event_at = max(result.last_event_at or timestamp, timestamp)
        team = TEAM_NAMES.get(item["team"], "Team saknas")
        model = item["model_ref"] or "Modell saknas i aktuell katalog"
        task = tasks.get((environment_id, dataset_ref, item["run_id"]), "Uppdragskoppling saknas")
        row = groups.setdefault((team, model, task), CostRow(team, model, task))
        row.known += amount or Decimal(0)
        row.unknown += amount is None
        row.attempts += 1
    result.rows = sorted(groups.values(), key=lambda r: (-r.known, r.team, r.model, r.task))
    for _, team, status in run_states.values():
        states = result.runs.setdefault(team, {})
        states[STATUSES[status]] = states.get(STATUSES[status], 0) + 1
    result.coverage = "partial" if result.known is not None else "missing"
    relevant = {s.source_id for s in manifest.sources if s.environment_id == environment_id and
                s.dataset_ref == dataset_ref and s.source_id not in quarantined}
    if relevant and relevant <= checks.keys():
        result.last_success_at = min(checks[s] for s in relevant)
        result.freshness = "stale" if (now - result.last_success_at).total_seconds() > 900 else "fresh"
    result.issues = list(dict.fromkeys(result.issues))
    return result
