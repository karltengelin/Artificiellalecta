"""Röktest av delegering compliance → aktuarie mot en riktig modell (Fas 3c 3c-1, B-039).

Compliance-agenten får ett uppdrag som tillåter delegering till aktuarieteamet och ska be
aktuarien om en aktuariell bedömning av den fiktiva källan K-SIM-ITP-2027. Hela kedjan körs:
körpolicy, profiler, delegeringsverktyget, barnkörningen med aktuariens eget tjänstelager,
gemensam rotbudget och båda körjournalerna. Demobeståndet i en SQLite-databas i minnet,
teamens roller simulerade som i handläggar-UI:ts demoläge. Inget skrivs i Lakebase, inga
förslag och inga utskick; utkast hamnar i logs/agent_artifacts/.

Utan --run görs inga modellanrop. Med --run används som standard leverantörens billigaste
modell för rollen deep (testet gäller mekaniken, inte tolkningens kvalitet); --deep använder
de konfigurerade modellerna. Taket är 1,00 USD för compliance och rotbudgeten i körpolicyn.
Nycklar läses ur .env och skrivs aldrig ut.

Användning (från repo-roten, i .venv):
    python scripts/diagnostics/smoke_test_delegation.py                       # ingen kostnad
    python scripts/diagnostics/smoke_test_delegation.py --run --provider anthropic
    python scripts/diagnostics/smoke_test_delegation.py --run --deep          # båda, riktiga deep-modeller
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

CHEAP_MODEL = {"anthropic": "anthropic:claude-haiku-4-5", "openai": "openai:gpt-6-luna"}
SOURCE = "K-SIM-ITP-2027"
GOAL = (
    f"Källan {SOURCE} föreslår en ändrad premieålder. Be aktuarieteamet om en kort aktuariell bedömning: "
    "vilka beräkningsregler och parametrar i den aktuariella grunden och parameterregistret som berörs, och "
    "en exempelpremie enligt gällande parametrar för en lön på 45 000 kr i månaden. Sammanfatta sedan svaret "
    "och ange vad som kommer från aktuarien. Skriv inget utkast och föreslå inga ändringar."
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="store_true", help="Gör riktiga modellanrop")
    parser.add_argument("--provider", choices=sorted(CHEAP_MODEL), help="Bara en leverantör")
    parser.add_argument("--deep", action="store_true", help="Använd de konfigurerade deep-modellerna")
    args = parser.parse_args()

    from ai import AIClient, MissingKeyError
    from ai.keys import resolve_api_key

    providers = [args.provider] if args.provider else sorted(CHEAP_MODEL)
    probe = AIClient()
    available = []
    for provider in providers:
        try:
            for team in ("compliance", "aktuarie"):
                resolve_api_key(probe.config.providers[provider], team)
            print(f"{provider}: nycklar hittade för compliance och aktuarie")
            available.append(provider)
        except MissingKeyError as exc:
            print(f"{provider}: hoppas över – {exc}")
    if not available:
        print("\nInga nycklar hittades. Lägg in ANTHROPIC_API_KEY och/eller OPENAI_API_KEY i .env.")
        return 1

    models = "konfigurerade deep-modeller" if args.deep else ", ".join(CHEAP_MODEL[p] for p in available)
    print(f"\nPlan: compliance delegerar till aktuarien, demobeståndet i minnet, modeller: {models}")
    if not args.run:
        print("Inga modellanrop gjorda. Kör med --run för att genomföra röktestet.")
        return 0

    all_ok, total = True, 0.0
    for provider in available:
        environ = dict(os.environ)
        if not args.deep:
            environ["AI_ROLE_DEEP"] = CHEAP_MODEL[provider]
        run_id = f"smoke-del-{provider}-{uuid.uuid4().hex[:8]}"
        print(f"\n== {provider}, körning {run_id}")
        checks, cost = run_once(AIClient(environ=environ), run_id)
        for label, passed, detail in checks:
            print(f"  [{'OK' if passed else 'FEL'}] {label}" + (f" – {detail}" if detail else ""))
        print(f"  Rotens kostnad {cost:.4f} USD. Journal: logs/agent_runs/{run_id}.jsonl")
        all_ok &= all(passed for _, passed, _ in checks)
        total += cost

    print(f"\nTotalt {total:.4f} USD. {'Alla kontroller gick igenom.' if all_ok else 'Minst en kontroll fallerade.'}")
    return 0 if all_ok else 1


def run_once(ai, run_id: str) -> tuple[list[tuple[str, bool, str]], float]:
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from agents import Ecosystem, Limits, RunRequest, RunStatus, SkillRegistry, compile_profile, read_journal, run_agent
    from agents.delegation import DelegationRuntime
    from agents.journal import DEFAULT_JOURNAL_DIR
    from services import MemoryEventLog, ServiceLayer, default_registry
    from services.db import session_factory_for
    from utils.demo_data import create_demo_database

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False)
    db = session_factory_for(engine)

    def team_service(role: str) -> ServiceLayer:
        return ServiceLayer(session_factory=db, validation_session_factory=db, events=MemoryEventLog(),
                            agent_role=role)

    compliance, actuary = team_service("agent_compliance"), team_service("agent_aktuarie")
    eco = Ecosystem.load()
    skills = SkillRegistry.build(eco, default_registry)
    runtime = DelegationRuntime(ai, eco, skills, compliance, team_services={"aktuarie": actuary})
    request = RunRequest(task_id=f"task-{run_id}", target_team="compliance", goal=GOAL, references=(SOURCE,),
                         delegation_targets=("aktuarie",), limits=Limits(max_cost_usd=1.0))
    profile = compile_profile(eco, skills, compliance, request=request)
    outcome = run_agent(ai, profile, compliance, request, run_id=run_id, delegation=runtime)

    parent, _ = read_journal(DEFAULT_JOURNAL_DIR / f"{run_id}.jsonl")
    started = [e for e in parent if e["type"] == "delegation_started"]
    returned = [e for e in parent if e["type"] == "delegation_returned" and not e.get("reused")]
    children = [read_journal(DEFAULT_JOURNAL_DIR / f"{e['child_run_id']}.jsonl")[0] for e in started]
    child_ok = bool(children) and all(
        c[0]["parent_run_id"] == run_id and c[0]["root_run_id"] == run_id and c[0]["team"] == "aktuarie"
        and c[0]["depth"] == 1 for c in children
    )
    child_tools = [{t["skill"] for t in c[1]["tools"]} for c in children]
    child_calls = sum(1 for c in children for e in c if e["type"] == "tool_completed")
    ended = next(e for e in parent if e["type"] == "run_ended")
    root = (ended.get("delegation") or {}).get("root_usage") or {}
    limits = eco.delegation.root_limits
    within = bool(root) and root["cost_usd"] <= limits.max_cost_usd and root["steps"] <= limits.max_steps
    checks = [
        ("Föräldern slutförd", outcome.result.status == RunStatus.COMPLETED, outcome.result.status.value),
        ("Minst ett delegerat uppdrag till aktuarien", len(started) >= 1, f"{len(started)} st"),
        ("Barnet slutfört", bool(returned) and all(e["status"] == "completed" for e in returned),
         ", ".join(e["status"] for e in returned)),
        ("Barnets journal bär förälder, rot och djup", child_ok, ""),
        ("Barnet saknar delegering och beståndsinsikt",
         all("delegate_to_team" not in t and "estimate_parameter_change_impact" not in t for t in child_tools), ""),
        ("Barnet använde sina verktyg", child_calls >= 1, f"{child_calls} anrop"),
        ("Inga förslag i kön", not outcome.result.pending_approvals, ""),
        ("Rotens förbrukning inom rotbudgeten", within, f"{root.get('steps')} steg, {root.get('cost_usd')} USD"),
    ]
    return checks, float(root.get("cost_usd", outcome.result.cost_usd))


if __name__ == "__main__":
    sys.exit(main())
