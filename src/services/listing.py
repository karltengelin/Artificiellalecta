"""Förteckning över tjänstelagrets operationer (tjänstelager.md §4, Fas 1f T4).

Visar för varje registrerad operation typ, produktregler, PII, nivån i
åtkomstregistret, effektiv nivå och skälen till skärpningen – så att
agentgränserna går att granska på ett ställe. Effektiv nivå hämtas från
`ServiceLayer.decision()`, så förteckningen och åtkomstkontrollen kan inte
skilja sig åt.

Deterministisk: sorterad på operationsnamn, inget genereringsdatum. Skapas
med `scripts/list_operations.py`; tests/test_services_listing.py fallerar
om filen inte stämmer med koden, registret och regelstatusen.
"""

from __future__ import annotations

from pathlib import Path

from services.service import ServiceLayer

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "02_system" / "tjänstelager_operationer.md"

_HEADER = """\
# Tjänstelagrets operationer

> **Genererad – ändra inte för hand.** Skapas med `python scripts/list_operations.py`
> ur operationsregistret, åtkomstregistret (`src/services/access_register.yaml`) och
> produktreglernas status (`01_domän/produktregler/`). Kontrolleras av
> `tests/test_services_listing.py`. Design och nivåer: [tjänstelager.md](tjänstelager.md) §4.

**Effektiv nivå** är den strängaste av registrets nivå och golven: saknas i registret →
`HUMAN_ONLY`; `external` → minst `APPROVAL`; `write`/`external` vars produktregel inte är
godkänd och giltig → `HUMAN_ONLY`. Handläggare får alltid utföra alla operationer (B-017).
"""


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def render_operations(service: ServiceLayer) -> str:
    rules = service.rules
    package = rules.package or "okänt paket"
    if rules.adoption_decision:
        adoption = f"infört ({rules.adoption_decision}" + (
            f", gäller från {rules.valid_from.isoformat()})" if rules.valid_from else ")"
        )
    else:
        adoption = "inte infört"

    lines = [
        _HEADER,
        f"**Regelpaket:** {package} – {adoption}.",
        "",
        "| Operation | Beskrivning | Typ | Produktregler | PII | Register | Effektiv | Skäl till skärpning |",
        "|-----------|-------------|-----|---------------|-----|----------|----------|---------------------|",
    ]
    for op in service.registry:  # sorterat på namn
        decision = service.decision(op.name)
        rule_cells = ", ".join(f"{rule_id} ({rules.label(rule_id)})" for rule_id in op.rules) or "–"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{op.name}`",
                    _cell(op.description),
                    f"`{op.kind.value}`",
                    _cell(rule_cells),
                    "Ja" if op.pii else "Nej",
                    f"`{decision.registered.value}`" if decision.registered else "saknas",
                    f"`{decision.effective.value}`",
                    _cell("; ".join(decision.reasons)) or "–",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"
