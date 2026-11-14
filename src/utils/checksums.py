"""Kanonisk SHA-256 utan beroende på tjänstelager, modeller eller databas."""

import hashlib
import json
from typing import Any


def checksum(content: dict[str, Any]) -> str:
    text = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_hash(value: Any) -> str:
    """Kontrollsumma för uppdragsunderlag, kompatibel med tidigare sparade beslut."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
