"""CSS-variabler för webben ur Digital klarhets tokenfil (B-034).

    css = render_web_tokens()          # innehållet i src/web/static/tokens.css

Handläggar-UI:ts stilark (`app.css`) använder bara dessa variabler, så att
webben inte får en egen, manuellt underhållen palett. Med ny tokenversion:
kör `python scripts/web/build_design_tokens.py` och committa filen –
`tests/test_design_web_css.py` fallerar annars.

Bara de ljusa webbvärdena tas med. `presentation_dark` och storlekarna för
rapport och presentation hör till andra kanaler.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TOKENS_PATH = Path(__file__).resolve().parent / "digital_clarity.tokens.json"
WEB_TOKENS_PATH = Path(__file__).resolve().parents[1] / "web" / "static" / "tokens.css"


def load_tokens(path: Path = TOKENS_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _name(*parts: str) -> str:
    return "--" + "-".join(part.replace("_", "-") for part in parts)


def _font_family(families: list[str]) -> str:
    generic = {"serif", "sans-serif", "monospace", "system-ui", "cursive", "fantasy"}
    return ", ".join(f if f in generic else f'"{f}"' for f in families)


def web_variables(tokens: dict[str, Any]) -> list[tuple[str, str]]:
    """Variabelnamn och värden i tokenfilens ordning."""
    out: list[tuple[str, str]] = []
    for key, value in tokens["color"].items():
        out.append((_name("color", key), value))
    for state, pair in tokens["status"].items():
        out.append((_name("status", state, "text"), pair["text"]))
        out.append((_name("status", state, "bg"), pair["background"]))
    typo = tokens["typography"]
    out.append(("--font-family", _font_family(typo["family"])))
    for key, value in typo["weight"].items():
        out.append((_name("font", "weight", key), str(value)))
    out.append(("--font-size-body", f"{typo['web_body_px']}px"))
    out.append(("--line-height-body", str(typo["body_line_height"])))
    for i, value in enumerate(tokens["spacing_px"], start=1):
        out.append((_name("space", str(i)), f"{value}px"))
    for key, value in tokens["radius_px"].items():
        out.append((_name("radius", key), f"{value}px"))
    focus = tokens["focus"]
    out.append(("--focus-color", f"var({_name(*focus['color_token'].split('.'))})"))
    out.append(("--focus-width", f"{focus['width_px']}px"))
    out.append(("--focus-offset", f"{focus['offset_px']}px"))
    return out


def render_web_tokens(tokens: dict[str, Any] | None = None) -> str:
    tokens = tokens or load_tokens()
    lines = [
        f"/* {tokens['name']} {tokens['version']} ({tokens['decision']}) – CSS-variabler för webben.",
        " * Genererad ur src/design/digital_clarity.tokens.json – ändra inte för hand.",
        " * Kör python scripts/web/build_design_tokens.py efter ändring i tokenfilen. */",
        ":root {",
        *(f"  {name}: {value};" for name, value in web_variables(tokens)),
        "}",
        "",
    ]
    return "\n".join(lines)
