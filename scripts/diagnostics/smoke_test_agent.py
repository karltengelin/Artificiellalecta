"""Röktest av handläggaragenten mot en riktig modell (Fas 3b-8, harness.md §11.2).

Kör hela harness-kedjan – körpolicy, profil, resursmandat, agentloop, dispatcher,
tjänstelager och körjournal – mot det fiktiva demobeståndet i en SQLite-databas i
minnet. Bara läsning och beräkning: agenten hämtar en försäkrads översikt och
löneunderlag och förhandsberäknar premien. Inget skrivs i Lakebase, inga förslag,
inga utskick.

Utan --run görs inga modellanrop: skriptet visar vilka nycklar som finns och vad som
skulle köras. Med --run kostar det några ören per leverantör (tak 0,10 USD per körning).
Rollen standard pekas om till leverantörens billigaste modell för testet. Nycklar läses
ur .env och skrivs aldrig ut. Körjournalen hamnar i logs/agent_runs/, anropsloggen i
logs/ai_calls.jsonl.

Användning (från repo-roten, i .venv):
    python scripts/diagnostics/smoke_test_agent.py                      # ingen kostnad
    python scripts/diagnostics/smoke_test_agent.py --run                # båda leverantörerna
    python scripts/diagnostics/smoke_test_agent.py --run --provider anthropic
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="store_true", help="Gör riktiga modellanrop (kostar några ören)")
    parser.add_argument("--provider", choices=sorted(CHEAP_MODEL), help="Bara en leverantör")
    args = parser.parse_args()

    from agents.demo import DEMO_LIMITS, demo_run
    from ai import AIClient, MissingKeyError
    from ai.keys import resolve_api_key

    providers = [args.provider] if args.provider else sorted(CHEAP_MODEL)
    probe = AIClient()
    available = []
    for provider in providers:
        try:
            _, key_env = resolve_api_key(probe.config.providers[provider], "forsakring")
            print(f"{provider}: nyckel hittad i {key_env}")
            available.append(provider)
        except MissingKeyError as exc:
            print(f"{provider}: hoppas över – {exc}")
    if not available:
        print("\nInga nycklar hittades. Lägg in ANTHROPIC_API_KEY och/eller OPENAI_API_KEY i .env.")
        return 1

    print(
        f"\nPlan: handläggaragenten, demobeståndet, bara läsning och beräkning, högst {DEMO_LIMITS.max_steps} "
        f"modellsteg och {DEMO_LIMITS.max_cost_usd:.2f} USD per körning, modell per leverantör: "
        + ", ".join(CHEAP_MODEL[p] for p in available)
    )
    if not args.run:
        print("Inga modellanrop gjorda. Kör med --run för att genomföra röktestet.")
        return 0

    all_ok = True
    total = 0.0
    for provider in available:
        environ = {**os.environ, "AI_ROLE_STANDARD": CHEAP_MODEL[provider]}
        ai = AIClient(environ=environ)
        run_id = f"smoke-{provider}-{uuid.uuid4().hex[:8]}"
        print(f"\n== {provider} ({CHEAP_MODEL[provider]}), körning {run_id}")
        result = demo_run(ai, run_id=run_id)
        outcome = result.outcome
        for label, passed, detail in result.checks:
            print(f"  [{'OK' if passed else 'FEL'}] {label}" + (f" – {detail}" if detail else ""))
        print(f"  {outcome.steps} modellsteg, {outcome.tool_calls} verktygsanrop, {outcome.result.cost_usd:.4f} USD")
        print(f"  Journal: logs/agent_runs/{run_id}.jsonl")
        all_ok &= result.ok
        total += outcome.result.cost_usd

    print(f"\nTotalt {total:.4f} USD. {'Alla kontroller gick igenom.' if all_ok else 'Minst en kontroll fallerade.'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
