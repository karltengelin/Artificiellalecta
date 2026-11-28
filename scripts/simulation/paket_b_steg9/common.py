"""Gemensamt för körskripten för paket B steg 9 i Lakebase: nytt startläge med pensionärer (B-057, P1-PENSION-001 §12.1).

Skripten importerar verksamhetskoden ur `src/` i den checkout de ligger i. Utdata skrivs till
huvudkatalogens `logs/simulation/paket-b-steg9/`, även när skriptet körs från en worktree.

Ordningen i Lakebase (Q5). Varje skrivande punkt kräver Karls separata OK i chatten och en färsk backup
(`scripts/maintenance/backup_database.py`):

1. backup;
2. migrationerna för steg 4–7 (`scripts/migrations/migrate_payout_plans.py`, `migrate_pension_claims.py`,
   `migrate_payout_orders.py`, `migrate_death_reports.py`), var och en torrkörd först;
3. `add_population.py` – de 35 nya personerna med fribrev och startpremie;
4. `reopen_ledger.py` – journalens nya ingående läge per 2026-10-31;
5. `pensioners.py --phase split` – Karin Sjöbergs delning i november;
6. tidigast 2026-12-01: `paket_b_steg3/adopt_avk.py` och `paket_b_steg3/close_month.py` (november);
7. `pensioners.py --phase start`, `--phase inputs` och `--phase capital` – planerna, skatt, konto och
   bolagsinsättningen;
8. tidigast 2027-01-01: `adopt_avk_december.py` och `paket_b_steg3/close_month.py --month 2026-12-01`;
   därefter bankfilen på pensionssidan (steg 8);
9. `verify.py` (skrivskyddad) efter varje punkt.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))


def _main_checkout() -> Path:
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO_ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent


OUT = _main_checkout() / "logs" / "simulation" / "paket-b-steg9"
OUT.mkdir(parents=True, exist_ok=True)

NOVEMBER, NOV_END = date(2026, 11, 1), date(2026, 11, 30)
DECEMBER, DEC_END = date(2026, 12, 1), date(2026, 12, 31)
#: Decembers AVK och stängning tidigast när december är slut
DECEMBER_EARLIEST = date(2027, 1, 1)
REASON = "Paket B steg 9: nytt startläge med pensionärer (B-057, P1-PENSION-001 §12.1)"


def require_backup(path: Path | None) -> Path:
    manifest = path / "manifest.json" if path else None
    if manifest is None or not manifest.is_file():
        raise SystemExit("Ange --backup med en backupmapp från scripts/maintenance/backup_database.py "
                         "(manifest.json saknas)")
    return manifest


def engine():
    from utils.db import make_engine

    return make_engine()


@contextmanager
def read_only(eng):
    """En session i en `READ ONLY`-transaktion som alltid rullas tillbaka."""
    from sqlalchemy.orm import Session

    with eng.connect() as conn:
        if eng.dialect.name == "postgresql":
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        with Session(bind=conn) as session:
            yield session
        conn.rollback()


def service(eng):
    from services import ProductRuleCatalog, ServiceLayer
    from services.db import session_factory_for

    return ServiceLayer(session_factory=session_factory_for(eng), rules=ProductRuleCatalog())


def context(reason: str = REASON):
    from services import Actor, OperationContext

    return OperationContext(actor=Actor.human("karl"), reason=reason)


def write(name: str, eng, data) -> Path:
    path = OUT / f"{name}_{eng.dialect.name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    print(OUT)
