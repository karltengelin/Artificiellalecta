"""Röktest av AI-lagret mot riktiga API:er (02_system/ai_abstraktion.md §11).

Kör per leverantör, med billigaste modellen:
  1. textsvar
  2. strukturerat svar (validerat mot Pydantic-modell)
  3. verktygsloop i två varv – premiemotorn (`calculate_itp1_premium`) som verktyg
Har båda leverantörerna nycklar körs dessutom:
  4. korsleverantör – en verktygsloop som påbörjats hos den ena avslutas hos den andra
Med --deep körs också ett kort anrop mot rollen deep:s modeller (effort + server-side fallback).

Kostnad: några ören utan --deep. Nycklar läses ur .env och skrivs aldrig ut –
skriptet visar bara vilken nyckelvariabel som användes. Anropen loggas i
logs/ai_calls.jsonl.

Användning:
    python scripts/diagnostics/smoke_test_ai.py
    python scripts/diagnostics/smoke_test_ai.py --provider openai
    python scripts/diagnostics/smoke_test_ai.py --deep
"""

from __future__ import annotations

import argparse
import sys
import uuid
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pydantic import BaseModel, Field  # noqa: E402

from ai import (  # noqa: E402
    AIClient,
    AIError,
    Message,
    MissingKeyError,
    ModelResponse,
    ToolResult,
    ToolSpec,
)
from ai.keys import resolve_api_key  # noqa: E402
from skills.calculation.calculate_itp1_premium import calculate_itp1_premium  # noqa: E402

CHEAP_MODEL = {"anthropic": "anthropic:claude-haiku-4-5", "openai": "openai:gpt-6-luna"}
DEEP_MODEL = {"anthropic": "anthropic:claude-opus-5", "openai": "openai:gpt-6-astra"}

#: Inkomstbasbelopp enligt scripts/setup/seed_base_amounts.py (ITP1_regelverk.md §6)
IBB = {2023: 74300, 2024: 76200, 2025: 80600, 2026: 83400}


class PremiumInput(BaseModel):
    monthly_salary_sek: float = Field(description="Pensionsmedförande månadslön i kronor")
    year: int = Field(description="Premieår, 2023–2026")


class Classification(BaseModel):
    category: str = Field(description="En av: premie, utbetalning, ovrigt")
    urgent: bool


PREMIUM_TOOL = ToolSpec.from_model(
    "calculate_itp1_premium",
    "Beräknar månatlig ITP1-premie (ålderspension) för en månadslön ett visst år.",
    PremiumInput,
)
PREMIUM_QUESTION = (
    "Vad blir den månatliga ITP1-premien för en månadslön på 80 000 kr år 2026? "
    "Använd verktyget och svara med beloppet i kronor."
)
EXPECTED_PREMIUM = "10708"  # 2 345,63 + 30 % × 27 875 = 10 708,13 kr


def run_premium_tool(arguments: dict) -> str:
    data = PremiumInput.model_validate(arguments)
    result = calculate_itp1_premium(Decimal(str(data.monthly_salary_sek)), Decimal(IBB[data.year]))
    return f"{result.total_premium_sek} kr per månad"


def describe(response: ModelResponse) -> str:
    u = response.usage
    return (
        f"{response.model} | {u.input_tokens} in ({u.cached_input_tokens} cache) / "
        f"{u.output_tokens} ut | ${response.cost_usd:.5f} | {response.latency_ms:.0f} ms"
    )


def check(label: str, ok: bool, detail: str) -> bool:
    print(f"  {'OK ' if ok else 'FEL'} {label}: {detail}")
    return ok


def start_tool_loop(ai: AIClient, model: str) -> tuple[list[Message], ModelResponse]:
    """Första varvet: modellen ska begära verktyget. Returnerar historik inkl. verktygssvar."""
    messages = [Message.user(PREMIUM_QUESTION)]
    first = ai.complete(messages, model=model, tools=[PREMIUM_TOOL], step="tool_loop_1")
    messages.append(first.to_message())
    results = [ToolResult(call_id=c.id, content=run_premium_tool(c.arguments)) for c in first.tool_calls]
    if results:
        messages.append(Message.from_tool_results(results))
    return messages, first


def smoke_provider(ai: AIClient, provider: str) -> tuple[bool, float]:
    model = CHEAP_MODEL[provider]
    print(f"\n== {provider} ({model})")
    ok = True
    cost = 0.0

    r = ai.complete([Message.user("Svara med exakt ett ord: Hej")], model=model, step="text")
    cost += r.cost_usd or 0
    ok &= check("textsvar", bool(r.text.strip()), f"{r.text.strip()!r} | {describe(r)}")

    r = ai.complete(
        [Message.user("Kunden skriver: 'Min pension har inte betalats ut, det är bråttom!' Klassificera.")],
        model=model,
        output_schema=Classification,
        step="structured",
    )
    cost += r.cost_usd or 0
    ok &= check("strukturerat svar", isinstance(r.parsed, Classification), f"{r.parsed} | {describe(r)}")

    messages, first = start_tool_loop(ai, model)
    cost += first.cost_usd or 0
    ok &= check(
        "verktygsanrop (varv 1)",
        first.stop_reason == "tool_use" and bool(first.tool_calls),
        f"{[(c.name, c.arguments) for c in first.tool_calls]} | {describe(first)}",
    )
    if first.tool_calls:
        second = ai.complete(messages, model=model, tools=[PREMIUM_TOOL], step="tool_loop_2")
        cost += second.cost_usd or 0
        answer = second.text.replace(" ", "").replace(" ", "")
        ok &= check(
            "slutsvar (varv 2)",
            EXPECTED_PREMIUM in answer,
            f"{second.text.strip()[:120]!r} | {describe(second)}",
        )
    return ok, cost


def smoke_cross_provider(ai: AIClient, start: str, finish: str) -> tuple[bool, float]:
    print(f"\n== korsleverantör: påbörjas hos {start}, avslutas hos {finish}")
    messages, first = start_tool_loop(ai, CHEAP_MODEL[start])
    cost = first.cost_usd or 0
    if not first.tool_calls:
        return check("verktygsanrop", False, "inget verktygsanrop i första varvet"), cost
    second = ai.complete(messages, model=CHEAP_MODEL[finish], tools=[PREMIUM_TOOL], step="cross_provider")
    cost += second.cost_usd or 0
    answer = second.text.replace(" ", "").replace(" ", "")
    return check("slutsvar", EXPECTED_PREMIUM in answer, f"{second.text.strip()[:120]!r} | {describe(second)}"), cost


def smoke_deep(ai: AIClient, provider: str) -> tuple[bool, float]:
    model = DEEP_MODEL[provider]
    print(f"\n== deep: {model} (effort low)")
    r = ai.complete(
        [Message.user("Vad står ITP1 för? Svara med en mening.")], model=model, effort="low", step="deep"
    )
    return check("textsvar", bool(r.text.strip()), f"{r.text.strip()[:120]!r} | {describe(r)}"), r.cost_usd or 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", choices=["anthropic", "openai"], help="Bara en leverantör")
    parser.add_argument("--deep", action="store_true", help="Även ett anrop mot deep-modellerna")
    args = parser.parse_args()

    ai = AIClient().bind(agent="smoke_test", run_id=f"smoke-{uuid.uuid4().hex[:8]}")
    available = []
    for provider in [args.provider] if args.provider else ["anthropic", "openai"]:
        try:
            _, key_env = resolve_api_key(ai.config.providers[provider])
            print(f"{provider}: nyckel hittad i {key_env}")
            available.append(provider)
        except MissingKeyError as exc:
            print(f"{provider}: hoppas över – {exc}")
    if not available:
        print("\nInga nycklar hittades. Lägg in dem i .env (se .env.example).")
        return 1

    all_ok = True
    total = 0.0
    try:
        for provider in available:
            ok, cost = smoke_provider(ai, provider)
            all_ok &= ok
            total += cost
        if len(available) == 2:
            for start, finish in (("openai", "anthropic"), ("anthropic", "openai")):
                ok, cost = smoke_cross_provider(ai, start, finish)
                all_ok &= ok
                total += cost
        if args.deep:
            for provider in available:
                ok, cost = smoke_deep(ai, provider)
                all_ok &= ok
                total += cost
    except AIError as exc:
        print(f"\nFEL: {type(exc).__name__}: {exc}")
        return 1

    print(f"\n{'Alla kontroller OK' if all_ok else 'Minst en kontroll misslyckades'} – "
          f"uppskattad kostnad ${total:.4f} (run_id {ai.context.run_id}, se logs/ai_calls.jsonl)")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
