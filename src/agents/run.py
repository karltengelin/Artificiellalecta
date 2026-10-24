"""Uppdrag och resultat för en agentkörning (harness.md §6.1, §10.1).

`RunRequest` fylls av betrodd kod – handläggar-UI:t, ett flöde eller ett skript –
aldrig av modellen. Identitet, team, scope och gränser kommer härifrån; uppdragets
text kan inte överstyra dem. Ett uppdrag kan bara skärpa: neka fler skills,
smalna av sidoeffekterna och sänka gränserna.

`RunResult` är det strukturerade svaret. Texten i `summary` är ingen beslutstoken:
"utfört" bevisas av tjänstelagrets resultat och körjournalen, inte av modellens ord.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agents.ecosystem import Limits
from services.contract import OperationKind


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RunRequest(_Strict):
    schema_version: Literal[1] = 1
    task_id: str = Field(min_length=1)
    target_team: str
    agent: str | None = None  # None = teamets ledande agent (teamets ytterdörr, B-026 §3.2)
    goal: str = Field(min_length=1)
    background: str = ""
    constraints: tuple[str, ...] = ()
    expected_output: str | None = None
    references: tuple[str, ...] = ()
    case_id: str | None = None
    # Resursmandat för personuppgifter: vilka personer/försäkringar körningen får röra.
    # Referensen löses av betrodd kod (3b-3); utan den visas inga PII-verktyg.
    execution_scope_ref: str | None = None
    root_run_id: str | None = None
    parent_run_id: str | None = None
    continuation_of: str | None = None  # körningen detta segment fortsätter (3b-5)
    flow_id: str | None = None
    flow_step_id: str | None = None
    depth: int = Field(default=0, ge=0)
    budget_reservation_usd: float | None = Field(default=None, gt=0)
    # Skärpningar – kan aldrig öppna något
    deny_skills: tuple[str, ...] = ()
    allowed_effects: frozenset[OperationKind] | None = None  # None = ingen extra avsmalning
    limits: Limits = Limits()


class RunStatus(StrEnum):
    COMPLETED = "completed"
    WAITING_APPROVAL = "waiting_approval"  # affärsändringen är inte gjord – människan avgör
    NEEDS_COMPLIANCE = "needs_compliance"
    NEEDS_HUMAN = "needs_human"
    BLOCKED = "blocked"
    FAILED = "failed"
    LIMIT_REACHED = "limit_reached"
    RECONCILIATION_REQUIRED = "reconciliation_required"  # utfall okänt – stäm av, kör inte om


class RunResult(_Strict):
    schema_version: Literal[1] = 1
    task_id: str
    run_id: str
    status: RunStatus
    summary: str = ""
    evidence_refs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    proposals: tuple[str, ...] = ()
    pending_approvals: tuple[str, ...] = ()  # approval-id i tjänstelagrets kö
    cost_usd: float = Field(default=0.0, ge=0)
