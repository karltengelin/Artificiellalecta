"""Demokörning av handläggaragenten mot det fiktiva demobeståndet (Fas 3b-8, harness.md §11.2).

Används av röktestet `scripts/diagnostics/smoke_test_agent.py` med en riktig modell och
av testerna med FakeProvider. Hela kedjan körs: körpolicy, profil, resursmandat,
agentloop, dispatcher, tjänstelager och körjournal.

Avgränsning enligt §11.2: syntetiska data (demobeståndet i en SQLite-databas i minnet),
bara läsning och beräkning, lågt utdata- och kostnadstak, inga skrivningar och inga
utskick. Agentens databasroll simuleras här – SQLite har inga roller; rollens
rättigheter är provade mot Postgres i tests/test_agents_postgres_role.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from agents.ecosystem import Ecosystem, Limits
from agents.loop import RunOutcome, run_agent
from agents.profile import compile_profile
from agents.run import RunRequest, RunStatus
from agents.scope import scope_for_person
from agents.skills import SkillRegistry
from ai import AIClient
from services import MemoryEventLog, OperationKind, ServiceLayer, default_registry
from services.db import session_factory_for
from utils.demo_data import create_demo_database

DEMO_PERSON = "198505151236"  # Anna Andersson i demobeståndet, lön 45 000 kr
EXPECTED_PREMIUM = "2025"  # 45 000 kr × 4,5 % – under 7,5 IBB/12 år 2026

DEMO_LIMITS = Limits(max_steps=6, max_tool_calls=8, max_cost_usd=0.10, max_output_tokens=1000)


@dataclass(frozen=True)
class DemoResult:
    outcome: RunOutcome
    checks: tuple[tuple[str, bool, str], ...]  # (kontroll, ok, detalj)
    proposals: int  # förslag i godkännandekön efter körningen – ska vara 0

    @property
    def ok(self) -> bool:
        return all(passed for _, passed, _ in self.checks)


def demo_run(ai: AIClient, *, journal_dir: Path | None = None, run_id: str | None = None) -> DemoResult:
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False)
    factory = session_factory_for(engine)
    trusted = ServiceLayer(session_factory=factory, events=MemoryEventLog())
    agent_service = ServiceLayer(
        session_factory=factory, validation_session_factory=factory, agent_role="agent_forsakring",
        events=MemoryEventLog(),
    )
    scope = scope_for_person(
        trusted, ref="demo-scope", personal_id_number=DEMO_PERSON,
        from_month=date(2025, 10, 1), to_month=date(2026, 9, 1), assigned_by="smoke_test",
    )
    request = RunRequest(
        task_id="demo-smoke",
        target_team="forsakring",
        goal=(
            f"Anna Andersson ({DEMO_PERSON}) är tilldelad dig. Hämta hennes översikt och löneunderlag för "
            "september 2026 och förhandsberäkna ITP1-premien för en månadslön på 45 000 kr i september 2026. "
            "Svara med premien i kronor och vilka underlag du använde."
        ),
        constraints=("Bara läsning och beräkning – ändra ingenting", "Ingen kundkontakt"),
        execution_scope_ref="demo-scope",
        allowed_effects=frozenset({OperationKind.READ, OperationKind.COMPUTE}),
        limits=DEMO_LIMITS,
    )
    eco = Ecosystem.load()
    profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), agent_service, request=request)
    outcome = run_agent(ai, profile, agent_service, request, scope=scope, run_id=run_id, journal_dir=journal_dir)

    result = outcome.result
    used = {ref.split(":", 1)[1] for ref in result.evidence_refs}
    answer = result.summary.replace(" ", "").replace(" ", "").replace(" ", "")
    proposals = len(trusted.approvals.list())
    checks = (
        ("slutstatus", result.status == RunStatus.COMPLETED, f"{result.status.value}: {result.summary[:160]!r}"),
        ("premieberäkning via verktyg", "calculate_premium_preview" in used, ", ".join(sorted(used)) or "inga"),
        ("läsning ur beståndet", bool(used & {"get_insured_overview", "get_salary_reports"}), ""),
        ("premien i svaret", EXPECTED_PREMIUM in answer, f"väntat {EXPECTED_PREMIUM} kr"),
        ("inga förslag eller ändringar", proposals == 0, f"{proposals} förslag i kön"),
        ("inom budget", result.cost_usd <= DEMO_LIMITS.max_cost_usd, f"{result.cost_usd:.4f} USD"),
    )
    return DemoResult(outcome=outcome, checks=checks, proposals=proposals)
