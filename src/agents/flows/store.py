"""Lagring för flödesmotorn: flödesnummer, hashar och den villkorliga versionsuppdateringen (3c-2).

Tabellerna i databasschema.md §9i. Alla ändringar av ett flöde går genom `bump`, som är en
villkorlig UPDATE på den version som lästes: två samtidiga klick ger en uppdatering och
en konflikt, aldrig två körningar av samma steg.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from agents.errors import HarnessError
from models import Flow, FlowGateDecision, FlowStep


class FlowError(HarnessError):
    """Flödet tillåter inte åtgärden i sitt nuvarande läge."""


class FlowConflictError(FlowError):
    """Flödet har ändrats sedan det lästes (fel version) – läs om och försök igen."""


def canonical_hash(value: Any) -> str:
    """sha256 av kanonisk JSON: sorterade nycklar, inga mellanslag, UTF-8."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def bound_hash(steps: dict[str, FlowStep], keys: tuple[str, ...] | list[str]) -> str | None:
    """Hashen en grind binder: stegens nycklar och resultathashar i grindens ordning.

    None om något av stegen saknar ett färdigt resultat.
    """
    pairs = []
    for key in keys:
        step = steps.get(key)
        if step is None or step.status != "completed" or step.result_hash is None:
            return None
        pairs.append([key, step.result_hash])
    return canonical_hash(pairs)


def next_flow_id(session: Session) -> str:
    """Nästa FLOW-NNNNNN. Krockar två samtidiga starter stoppar primärnyckeln den ena."""
    highest = session.scalar(select(func.max(Flow.flow_id)))
    number = int(highest.removeprefix("FLOW-")) + 1 if highest else 1
    return f"FLOW-{number:06d}"


def load(session: Session, flow_id: str) -> tuple[Flow, list[FlowStep], list[FlowGateDecision]]:
    flow = session.get(Flow, flow_id)
    if flow is None:
        raise FlowError(f"Inget flöde {flow_id}")
    steps = list(session.scalars(select(FlowStep).where(FlowStep.flow_id == flow_id).order_by(FlowStep.position)))
    decisions = list(session.scalars(
        select(FlowGateDecision).where(FlowGateDecision.flow_id == flow_id).order_by(FlowGateDecision.created_at)
    ))
    return flow, steps, decisions


def bump(session: Session, flow: Flow, expected_version: int, **values: Any) -> int:
    """Villkorlig UPDATE på flödets version. Ny version, eller FlowConflictError."""
    result = session.execute(
        update(Flow)
        .where(Flow.flow_id == flow.flow_id, Flow.version == expected_version)
        .values(version=expected_version + 1, **values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise FlowConflictError(
            f"Flödet {flow.flow_id} har ändrats sedan version {expected_version} – läs om flödet och försök igen"
        )
    session.expire(flow)
    return expected_version + 1
