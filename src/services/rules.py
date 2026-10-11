"""Läser produktreglernas granskningsstatus ur 01_domän/produktregler/.

Formatet ägs av delprojekt 4 (projekt/04_produktregelverk/ARBETSSATT.md):
regelns rubrikblock innehåller `**Granskningsstatus:** utkast|godkänd|ersatt`.
Allt annat – saknad fil, saknat fält, okänt värde – räknas som ej godkänt.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path

_STATUS_PATTERN = re.compile(r"\*\*Granskningsstatus:\*\*\s*([^|\n]+)", re.IGNORECASE)


class RuleStatus(StrEnum):
    UTKAST = "utkast"
    GODKAND = "godkänd"
    ERSATT = "ersatt"
    OKAND = "okänd"  # filen eller fältet saknas, eller okänt värde


def default_rules_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "01_domän" / "produktregler"


class ProductRuleCatalog:
    """Slår upp granskningsstatus per regel-id. Läser varje fil en gång."""

    def __init__(self, rules_dir: Path | None = None) -> None:
        self.rules_dir = rules_dir or default_rules_dir()
        self._cache: dict[str, RuleStatus] = {}

    def status(self, rule_id: str) -> RuleStatus:
        if rule_id not in self._cache:
            self._cache[rule_id] = self._read_status(rule_id)
        return self._cache[rule_id]

    def refresh(self) -> None:
        """Läs om filerna, t.ex. efter att en regel godkänts."""
        self._cache.clear()

    def _read_status(self, rule_id: str) -> RuleStatus:
        path = self._find(rule_id)
        if path is None:
            return RuleStatus.OKAND
        match = _STATUS_PATTERN.search(path.read_text(encoding="utf-8"))
        if not match:
            return RuleStatus.OKAND
        value = match.group(1).strip().strip("*").strip().lower()
        try:
            return RuleStatus(value)
        except ValueError:
            return RuleStatus.OKAND

    def _find(self, rule_id: str) -> Path | None:
        if not self.rules_dir.is_dir():
            return None
        for path in sorted(self.rules_dir.glob("*.md")):
            # "PR-ITP1-001-premietrappa.md" eller "PR-ITP1-001.md" – men inte "PR-ITP1-0010-…"
            if path.stem == rule_id or path.stem.startswith(f"{rule_id}-"):
                return path
        return None
