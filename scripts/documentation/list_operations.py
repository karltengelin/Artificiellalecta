"""Genererar förteckningen över tjänstelagrets operationer (Fas 1f, T4).

Skriver 02_system/tjänstelager_operationer.md: varje registrerad operation med
typ, produktregler, PII, nivå i åtkomstregistret, effektiv nivå och skälen till
skärpningen. Effektiv nivå kommer från ServiceLayer.decision() – samma logik
som åtkomstkontrollen. Kräver ingen databasanslutning och inga modellanrop.

Kör efter ändringar i operationer, åtkomstregistret eller produktreglernas
status. tests/test_services_listing.py fallerar om filen inte är aktuell.

Användning (från repo-roten, i .venv):
    python scripts/documentation/list_operations.py           # skriver filen
    python scripts/documentation/list_operations.py --check   # felkod 1 om filen inte är aktuell
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from services import MemoryEventLog, ServiceLayer  # noqa: E402
from services.listing import DEFAULT_PATH, render_operations  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Jämför bara, skriv inte")
    parser.add_argument("--output", type=Path, default=DEFAULT_PATH, help="Målfil")
    args = parser.parse_args()

    content = render_operations(ServiceLayer(events=MemoryEventLog()))
    current = args.output.read_text(encoding="utf-8") if args.output.exists() else None
    if args.check:
        if current != content:
            print(f"{args.output} är inte aktuell – kör python scripts/documentation/list_operations.py")
            sys.exit(1)
        print(f"{args.output} är aktuell")
        return
    args.output.write_text(content, encoding="utf-8", newline="\n")
    print(f"Skrev {args.output}" + (" (oförändrad)" if current == content else ""))


if __name__ == "__main__":
    main()
