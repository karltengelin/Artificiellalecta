"""Agentteamskatalogen som operatören och orkestratören använder i demo."""

from agents.ecosystem import Ecosystem
from management.telemetry import TEAM_NAMES
from services.change_requests import DEVELOPER

PILOT_INTAKE = {
    "compliance": "Tar emot ett mål och handtaget till en fiktiv bevakningskälla. Lämnar tolkning och regelutkast.",
    "aktuarie": "Tar emot en granskningsbunden parameterändring för premieanalys. Lämnar skyddade aggregat.",
    "utveckling": "Efter operatörens regelbeslut kan centralen lämna ett ändringsärende till projekt 11 och läsa dess kvitton.",
}
DEVELOPMENT_MANDATE = (
    "Utreder systemändringar, arbetar med kod i avgränsade arbetsytor och lämnar ändringsförslag och testbevis "
    "för mänsklig granskning. I demo används projekt 11:s separata kodkörning och lokala leveranskvitton."
)


def team_catalog(ecosystem: Ecosystem) -> dict:
    entries = {}
    for team_id in ecosystem.team_ids:
        team = ecosystem.teams.get(team_id)
        profiles = [
            {"id": agent_id, "name": agent.name, "description": agent.description or team.mandate,
             "lead": agent_id == team.lead, "runtime": "harness"}
            for agent_id, agent in ecosystem.agents.items() if agent.team == team_id
        ]
        if team_id == DEVELOPER.team and DEVELOPER.id not in ecosystem.agents:
            profiles.append({"id": DEVELOPER.id, "name": "Utvecklaragent", "description": DEVELOPMENT_MANDATE,
                             "lead": False, "runtime": "project_11_demo"})
        mandate = team.mandate if team else DEVELOPMENT_MANDATE if profiles else "Inväntar agentprofil."
        entries[team_id] = {
            "name": TEAM_NAMES.get(team_id, team_id),
            "mandate": mandate,
            "lead": team.lead if team else None,
            "agent_count": len(profiles),
            "agents": profiles,
            "company_intake": PILOT_INTAKE.get(team_id),
        }
    return entries
