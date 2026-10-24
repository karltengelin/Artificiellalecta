"""Strikta JSON-scheman ur Pydantic-modeller.

Båda leverantörernas strikta lägen (strukturerade svar och strikta verktyg)
kräver att varje objekt har `additionalProperties: false` och att alla
egenskaper står i `required`. Valfria fält uttrycks i stället som nullbara
(Pydantic genererar `anyOf: [..., {type: null}]` för `X | None`).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

# Nyckelord som inte tillför något i strikt läge och som inte alla
# leverantörer accepterar. Egenskaper med dessa namn påverkas inte.
_DROPPED_KEYWORDS = {"title", "default"}

# Nyckelord vars värde är en mappning namn -> schema (namnen ska bevaras).
_SCHEMA_MAPS = {"properties", "$defs", "definitions", "patternProperties"}

# Värdegränser som Anthropics strikta läge inte godtar ("For 'number' type, property
# 'minimum' is not supported"). De tas bort ur schemat och skrivs i beskrivningen, så
# att modellen ändå ser dem. Anroparen validerar mot Pydantic-modellen – schemat är
# ingen valideringsgräns (harness: ServiceSkill.parse).
_UNSUPPORTED_CONSTRAINTS = {
    "minimum": "minst {}",
    "exclusiveMinimum": "större än {}",
    "maximum": "högst {}",
    "exclusiveMaximum": "mindre än {}",
    "multipleOf": "jämn multipel av {}",
    "minLength": "minst {} tecken",
    "maxLength": "högst {} tecken",
    "maxItems": "högst {} element",
    "uniqueItems": None,
}
# minItems godtas bara som 0 eller 1
_MIN_ITEMS_SUPPORTED = {0, 1}


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Returnerar modellens JSON Schema i strikt form."""
    return _strictify(model.model_json_schema())


def schema_name(model: type[BaseModel]) -> str:
    """Namn på schemat som leverantörerna accepterar (ASCII, max 64 tecken)."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", model.__name__)[:64] or "response"


def _strictify(node: Any) -> Any:
    if isinstance(node, list):
        return [_strictify(item) for item in node]
    if not isinstance(node, dict):
        return node

    out: dict[str, Any] = {}
    hints: list[str] = []
    for key, value in node.items():
        if key in _DROPPED_KEYWORDS:
            continue
        if key in _UNSUPPORTED_CONSTRAINTS and not isinstance(value, (dict, list)):
            if _UNSUPPORTED_CONSTRAINTS[key]:
                hints.append(_UNSUPPORTED_CONSTRAINTS[key].format(value))
            continue
        if key == "minItems" and value not in _MIN_ITEMS_SUPPORTED:
            hints.append(f"minst {value} element")
            out[key] = 1
            continue
        if key in _SCHEMA_MAPS and isinstance(value, dict):
            out[key] = {name: _strictify(sub) for name, sub in value.items()}
        else:
            out[key] = _strictify(value)

    if hints:
        text = ", ".join(hints)
        out["description"] = f"{out['description']} ({text})" if out.get("description") else text.capitalize()

    if "properties" in out:
        out["additionalProperties"] = False
        out["required"] = list(out["properties"])
    return out
