"""Vaktar MASTER_CONTEXT §3.1 / B-009 / B-025: leverantörs-SDK:er får bara
importeras i AI-lagrets adaptrar (src/ai/providers/), aldrig i agent-,
skill- eller annan kod. Testet läser källkoden – det kör ingenting.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_DIR = REPO_ROOT / "src" / "ai" / "providers"
SDK_PACKAGES = {"anthropic", "openai"}


def _sdk_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        found += [n for n in names if n.split(".")[0] in SDK_PACKAGES]
    return found


def test_sdk_importeras_bara_i_ai_providers():
    violations = []
    for folder in ("src", "scripts"):
        for path in (REPO_ROOT / folder).rglob("*.py"):
            if ALLOWED_DIR in path.parents:
                continue
            for name in _sdk_imports(path):
                violations.append(f"{path.relative_to(REPO_ROOT)}: import {name}")
    assert not violations, (
        "Leverantörs-SDK importerad utanför src/ai/providers/ – gå via `from ai import ...`:\n"
        + "\n".join(violations)
    )


def test_adaptrarna_importerar_faktiskt_sdkerna():
    # Kontroll av själva testet: annars kunde det passera för att det inte hittar något
    assert _sdk_imports(ALLOWED_DIR / "anthropic_provider.py") == ["anthropic"]
    assert _sdk_imports(ALLOWED_DIR / "openai_provider.py") == ["openai"]
