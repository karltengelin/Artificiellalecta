"""Genererar handläggar-UI:ts CSS-variabler ur Digital klarhets tokenfil (B-034).

Skriver src/web/static/tokens.css ur src/design/digital_clarity.tokens.json.
Kör efter varje ändring i tokenfilen. tests/test_design_web_css.py fallerar
om filen inte är aktuell. Ingen databas och inga modellanrop.

Användning (från repo-roten, i .venv):
    python scripts/web/build_design_tokens.py           # skriver filen
    python scripts/web/build_design_tokens.py --check   # felkod 1 om filen inte är aktuell
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from design.web_css import WEB_TOKENS_PATH, render_web_tokens  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Jämför bara, skriv inte")
    args = parser.parse_args()

    content = render_web_tokens()
    current = WEB_TOKENS_PATH.read_text(encoding="utf-8") if WEB_TOKENS_PATH.exists() else None
    if args.check:
        if current != content:
            print(f"{WEB_TOKENS_PATH} är inte aktuell – kör python scripts/web/build_design_tokens.py")
            sys.exit(1)
        print(f"{WEB_TOKENS_PATH} är aktuell")
        return
    WEB_TOKENS_PATH.write_text(content, encoding="utf-8", newline="\n")
    print(f"Skrev {WEB_TOKENS_PATH}")


if __name__ == "__main__":
    main()
