"""Startar handläggar-UI:t (Fas 4) lokalt på http://127.0.0.1:8765.

Tunn ingång till `src/web/__main__.py`. Databasen väljs med --db eller
HANDLAGGARE_DB: demo (lokal SQLite, standard), svc_test (isolerad Postgres) eller
lakebase (beståndet – bara uttryckligen). Handläggarens id: HANDLAGGARE_ID.

    python scripts/web/start_ui.py
    python scripts/web/start_ui.py --db svc_test --port 8766
    python scripts/web/start_ui.py --reset-demo
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from web.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
