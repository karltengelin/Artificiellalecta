"""Körpolicyns skills i skillkatalogen (Fas 3b-7, agentekosystem.md §5.1).

Varje skill i `src/agents/ecosystem.yaml` hör till exakt en podd. Tabellen visar podd,
operation eller gatewayverktyg (3c-T), typ, PII, nivån i tjänstelagrets åtkomstregister och vilka agenter som har
podden monterad utan att skillen är nekad – så att behörigheten går att granska i
katalogen, inte bara i YAML-filen.

Registrets nivå visas, inte effektiv nivå: den senare beror på dagens datum och
produktreglernas status och står i `02_system/tjänstelager_operationer.md`. Tabellen
är därför stabil mellan dagar. Verktyg med personuppgifter visas för en agent först
med resursmandat och teamets databasroll (`harness.md` §5.1).

Tabellen skrivs mellan markeringarna i `03_skills/skillkatalog.md` med
`python scripts/documentation/list_skills.py`; tests/test_agents_listing.py fallerar
om den inte är aktuell.
"""

from __future__ import annotations

from pathlib import Path

from agents.ecosystem import Ecosystem
from agents.gateways.tools import GATEWAY_TOOLS
from services import AccessRegister, OperationRegistry

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "03_skills" / "skillkatalog.md"
START = "<!-- list_skills.py: start – genererad, ändra inte för hand -->"
END = "<!-- list_skills.py: slut -->"


def authorized_agents(ecosystem: Ecosystem, skill: str) -> list[str]:
    """Agenter som har skillens podd monterad och där varken defaults, team eller agent nekar den."""
    pod = ecosystem.pod_of(skill)
    out = []
    for agent_id, agent in sorted(ecosystem.agents.items()):
        team = ecosystem.teams[agent.team]
        denied = set(ecosystem.defaults.deny_skills) | set(team.deny_skills) | set(agent.deny_skills)
        if pod in agent.pods and skill not in denied:
            out.append(agent_id)
    return out


def render_skill_table(ecosystem: Ecosystem, registry: OperationRegistry, register: AccessRegister) -> str:
    lines = [
        "| Skill | Podd | Operation eller gatewayverktyg | Typ | PII | Åtkomstregistret | Behöriga agenter |",
        "|---|---|---|---|---|---|---|",
    ]
    for skill in ecosystem.skill_names():
        pod = ecosystem.pod_of(skill)
        entry = ecosystem.pods[pod].skills[skill]
        if entry.gateway_tool is not None:
            tool = GATEWAY_TOOLS[entry.gateway_tool]
            target, kind, pii, level = f"gateway `{tool.name}`", tool.side_effect, tool.pii, "– (gatewayens policy)"
        else:
            op = registry.get(entry.service_operation)
            registered = register.levels.get(op.name)
            target, kind, pii = f"`{op.name}`", op.kind.value, op.pii
            level = registered.value if registered else "saknas (HUMAN_ONLY)"
        if entry.parameter_mandate:
            level += ", kräver godkänt parameterförslag"
        agents = ", ".join(
            f"{a} ({ecosystem.agents[a].name})" for a in authorized_agents(ecosystem, skill)
        ) or "–"
        lines.append(
            f"| `{skill}` | `{pod}` | {target} | {kind} | {'Ja' if pii else 'Nej'} | {level} | {agents} |"
        )
    unmapped = ecosystem.unmapped_operations(registry)
    lines += [
        "",
        f"Operationer utan poddmappning – stängda för alla agenter: {', '.join(f'`{n}`' for n in unmapped) or '–'}.",
    ]
    return "\n".join(lines)


def updated_catalog(current: str, table: str) -> str:
    """Katalogen med tabellen mellan markeringarna utbytt."""
    if current.count(START) != 1 or current.count(END) != 1:
        raise ValueError(f"Skillkatalogen saknar markeringarna {START!r} och {END!r}")
    before, rest = current.split(START)
    _, after = rest.split(END)
    return f"{before}{START}\n{table}\n{END}{after}"
