"""Hur en körning gick till – en sammanfattning av körjournalen för granskare och avancerade vyer.

    trace = read_run_trace(journal_dir, run_id)   # None när journalen saknas

Journalen (`logs/agent_runs/<run_id>.jsonl`) är källan; sammanfattningen tolkar inget utöver
det journalen säger. Den visar agent, modeller, verktygsanrop med nivå och utfall, steg,
kostnad och körpolicy – inga indata, svarstexter eller personuppgifter (journalen har bara hashar).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents.journal import read_journal


@dataclass(frozen=True)
class ToolUse:
    skill: str
    operation: str | None
    kind: str | None  # read, compute, write …
    level: str | None  # effektiv nivå i tjänstelagret: AGENT, APPROVAL …
    status: str  # done, error, denied, pending_approval, not_executed, unknown


@dataclass(frozen=True)
class RunTrace:
    run_id: str
    team: str | None
    agent: str | None
    model_role: str | None
    models: tuple[str, ...]  # i den ordning de svarade, utan upprepning
    fallback_from: tuple[str, ...]
    tools: tuple[ToolUse, ...]
    steps: int | None
    cost_usd: float | None
    elapsed_seconds: float | None
    status: str | None
    policy_id: str | None
    complete: bool  # journalen har run_ended och ingen skadad sista rad


def run_trace(run_id: str, events: list[dict[str, Any]], *, corrupt: bool = False) -> RunTrace:
    started = next((e for e in events if e.get("type") == "run_started"), {})
    ended = next((e for e in reversed(events) if e.get("type") == "run_ended"), None)
    models: list[str] = []
    fallback: list[str] = []
    tools: dict[str, dict[str, Any]] = {}
    for e in events:
        kind = e.get("type")
        if kind == "model_returned":
            if e.get("model_ref") and e["model_ref"] not in models:
                models.append(e["model_ref"])
            fallback += [m for m in e.get("fallback_from") or [] if m not in fallback]
        elif kind == "tool_intent":
            tools[e["tool_call_id"]] = {"skill": e["skill"], "operation": e.get("operation"), "kind": e.get("kind"),
                                        "level": e.get("effective"), "status": "unknown"}
        elif kind in ("tool_completed", "tool_denied", "approval_wait"):
            entry = tools.setdefault(e["tool_call_id"], {"skill": e["skill"], "operation": None, "kind": None,
                                                         "level": None, "status": "unknown"})
            entry["status"] = "pending_approval" if kind == "approval_wait" else e.get("status", "unknown")
    usage = (ended or {}).get("usage") or {}
    return RunTrace(
        run_id=run_id, team=started.get("team"), agent=started.get("agent"), model_role=started.get("model_role"),
        models=tuple(models), fallback_from=tuple(fallback), tools=tuple(ToolUse(**t) for t in tools.values()),
        steps=usage.get("steps"), cost_usd=usage.get("cost_usd"), elapsed_seconds=usage.get("elapsed_seconds"),
        status=(ended or {}).get("status"), policy_id=(started.get("versions") or {}).get("policy_id"),
        complete=ended is not None and not corrupt,
    )


def read_run_trace(journal_dir: Path, run_id: str | None) -> RunTrace | None:
    if run_id is None:
        return None
    path = journal_dir / f"{run_id}.jsonl"
    if not path.exists():
        return None
    events, corrupt = read_journal(path)
    return run_trace(run_id, events, corrupt=corrupt)
