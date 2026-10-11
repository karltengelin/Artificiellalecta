"""Backup och återställning av hela databasen till/från filer.

En backup är en mapp med en JSONL-fil per tabell plus `manifest.json`
(tidpunkt, tabeller, antal rader). Den är oberoende av databasleverantör –
samma backup kan läsas in i Lakebase eller i en testdatabas.

Backupen läser tabellerna som de faktiskt ser ut i databasen, inte som
modellerna beskriver dem – så att den fungerar även när koden ligger före
databasen, t.ex. inför en migration.

Återställning görs bara till tomma tabeller, så att inget skrivs över. Rader
som pekar på en annan rad i samma tabell (rättelser, nya versioner) läses in
efter den rad de pekar på.
Skripten: scripts/maintenance/backup_database.py och scripts/maintenance/restore_database.py.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Table, func, insert, inspect, select
from sqlalchemy import column as sa_column
from sqlalchemy import table as sa_table
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


def _live_queries(conn) -> list[tuple[str, Any]]:
    """En SELECT per tabell i databasen, i modellernas beroendeordning.

    Kolumner som finns i modellen läses med modellens typ (UUID, JSON, Decimal);
    kolumner och tabeller som bara finns i databasen läses otypat.
    """
    inspector = inspect(conn)
    live = set(inspector.get_table_names())
    models = {t.name: t for t in Base.metadata.sorted_tables}
    names = [n for n in models if n in live] + sorted(live - set(models))
    queries = []
    for name in names:
        model = models.get(name)
        source = model if model is not None else sa_table(name)
        columns = [
            model.c[c["name"]] if model is not None and c["name"] in model.c else sa_column(c["name"])
            for c in inspector.get_columns(name)
        ]
        queries.append((name, select(*columns).select_from(source)))
    return queries


def backup_database(engine: Engine, target_root: Path) -> Path:
    """Skriver alla tabeller till en ny tidsstämplad mapp under target_root."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = target_root / stamp
    target.mkdir(parents=True, exist_ok=False)
    counts: dict[str, int] = {}
    with engine.connect() as conn:
        for name, query in _live_queries(conn):
            rows = 0
            with (target / f"{name}.jsonl").open("w", encoding="utf-8") as f:
                for row in conn.execute(query).mappings():
                    f.write(json.dumps({k: _to_json(v) for k, v in row.items()}, ensure_ascii=False) + "\n")
                    rows += 1
            counts[name] = rows
    manifest = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "tables": list(counts),
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
                value = Decimal(str(value))
            elif python_type is uuid.UUID:
                value = uuid.UUID(value)
        out[column.name] = value
    return out


def _self_reference_order(table: Table, rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Rader i omgångar där varje rad bara pekar på rader i tidigare omgångar (samma tabell)."""
    columns = [fk.parent.name for fk in table.foreign_keys if fk.column.table is table]
    if not columns or not rows:
        return [rows] if rows else []
    key = table.primary_key.columns.values()[0].name
    done: set = set()
    left = rows
    batches = []
    while left:
        ready = [r for r in left if all(r.get(c) is None or r[c] in done for c in columns)]
        if not ready:
            raise RuntimeError(f"{table.name}: rader pekar på rader som saknas i backupen")
        batches.append(ready)
        done.update(r[key] for r in ready)
        left = [r for r in left if r[key] not in done]
    return batches


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
            for batch in _self_reference_order(table, rows):
                conn.execute(insert(table), batch)
            restored[name] = len(rows)
    return restored
