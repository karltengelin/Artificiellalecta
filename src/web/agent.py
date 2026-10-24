"""Handläggaragenten i UI:t (Fas 5 F5-4, B-033 val D och H).

Handläggaren startar agenten med en knapp på ärendet. Körningen går synkront i
trådpoolen (lokalt, en användare). Varje körning bygger ett nytt agenttjänstelager,
en ny körpolicy och ett nytt skill-register, så att regelstatus och policy är aktuella
(harness.md §3.5). Modellklienten skapas först vid första körningen – UI:t startar
utan API-nycklar.

Agentens databasroll per databasläge:

| Läge       | Agentens tjänstelager                                                     |
|------------|---------------------------------------------------------------------------|
| `demo`     | Samma SQLite-databas, **simulerad** roll (B-033 val H) – märkt i UI:t     |
| `svc_test` | Samma testschema, **simulerad** roll – märkt i UI:t                       |
| `lakebase` | Den riktiga rollen `agent_forsakring` (`services.db.agent_service_layer`) |

Mandat och ärendets status går alltid via handläggarens tjänstelager (`trusted`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from agents import CaseRun, Ecosystem, SkillRegistry, run_case
from ai import AIClient
from services import ServiceLayer, default_registry


@dataclass
class CaseAgent:
    agent_service_factory: Callable[[], ServiceLayer]
    simulated_role: bool
    ai_factory: Callable[[], AIClient] = AIClient
    journal_dir: Path | None = None  # standard logs/agent_runs/
    _ai: AIClient | None = field(default=None, init=False, repr=False)

    @property
    def role_label(self) -> str:
        if self.simulated_role:
            return "simulerad databasroll (demo- och testdatabas)"
        return "databasrollen agent_forsakring"

    def ai(self) -> AIClient:
        if self._ai is None:
            self._ai = self.ai_factory()
        return self._ai

    def run(self, trusted: ServiceLayer, case_number: str, *, assigned_by: str) -> CaseRun:
        eco = Ecosystem.load()
        skills = SkillRegistry.build(eco, default_registry)
        return run_case(
            self.ai(), eco, skills, self.agent_service_factory(), trusted, case_number,
            assigned_by=assigned_by, journal_dir=self.journal_dir,
        )
