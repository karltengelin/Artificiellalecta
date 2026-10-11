"""Backup och återställning av hela databasen till/från filer.

En backup är en mapp med en JSONL-fil per tabell plus `manifest.json`
(tidpunkt, tabeller, antal rader). Den är oberoende av databasleverantör –
samma backup kan läsas in i Lakebase eller i en testdatabas.

Återställning görs bara till tomma tabeller, så att inget skrivs över.
Skripten: scripts/backup_database.py och scripts/restore_database.py.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Table, func, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.sql.sqltypes import JSON

from models import Base

MANIFEST = "manifest.json"


def _to_json(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Decimal, uuid.UUID)):
        return str(value)
    return value


def backup_database(engine: Engine, target_root: Path) -> Path:
    """Skriver alla tabeller till en ny tidsstämplad mapp under target_root."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = target_root / stamp
    target.mkdir(parents=True, exist_ok=False)
    counts: dict[str, int] = {}
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            rows = 0
            with (target / f"{table.name}.jsonl").open("w", encoding="utf-8") as f:
                for row in conn.execute(select(table)).mappings():
                    f.write(json.dumps({k: _to_json(v) for k, v in row.items()}, ensure_ascii=False) + "\n")
                    rows += 1
            counts[table.name] = rows
    manifest = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "tables": [t.name for t in Base.metadata.sorted_tables],
        "row_counts": counts,
    }
    (target / MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return target


def _from_json(table: Table, record: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for column in table.columns:
        if column.name not in record:
            continue
        value = record[column.name]
        if value is not None and not isinstance(column.type, JSON):
            try:
                python_type = column.type.python_type
            except NotImplementedError:
                python_type = None
            if python_type is datetime:
                value = datetime.fromisoformat(value)
            elif python_type is date:
                value = date.fromisoformat(value)
            elif python_type is Decimal:
                value = Decimal(value)
            elif python_type is uuid.UUID:
                value = uuid.UUID(value)
        out[column.name] = value
    return out


def restore_database(engine: Engine, source: Path) -> dict[str, int]:
    """Läser in en backup till en databas där tabellerna är tomma. Skapar saknade tabeller."""
    manifest = json.loads((source / MANIFEST).read_text(encoding="utf-8"))
    Base.metadata.create_all(engine)
    tables = {t.name: t for t in Base.metadata.sorted_tables}
    restored: dict[str, int] = {}
    with engine.begin() as conn:
        not_empty = [
            name for name in manifest["tables"]
            if name in tables and conn.execute(select(func.count()).select_from(tables[name])).scalar()
        ]
        if not_empty:
            raise RuntimeError(
                f"Återställning avbruten – tabellerna är inte tomma: {', '.join(not_empty)}"
            )
        for name in manifest["tables"]:  # sparad i beroendeordning (föräldrar först)
            table = tables.get(name)
            path = source / f"{name}.jsonl"
            if table is None or not path.exists():
                continue
            rows = [
                _from_json(table, json.loads(line))
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if rows:
                conn.execute(insert(table), rows)
            restored[name] = len(rows)
    return restored
