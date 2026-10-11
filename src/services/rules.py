"""Läser produktreglernas status ur 01_domän/produktregler/.

Formatet ägs av delprojekt 4. Två format stöds:

- **Regelpaket (PR-ITP1 v1.0 och senare):** varje regelfil har
  `**Status:** Specificerad …`, och hela paketet införs med ett samlat beslut
  (projekt/04_produktregelverk/PAKET_BESLUTSFORSLAG.md). Paketet räknas som
  godkänt när paketets README har raden `**Införandebeslut:** B-nnn`.
- **Äldre format:** `**Granskningsstatus:** utkast|godkänd|ersatt` per regel.

En enskild regel som är `ersatt` är alltid ej godkänd. Allt som inte går att
läsa – saknad fil, saknat fält, okänt värde – räknas som ej godkänt.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path

_REVIEW_STATUS = re.compile(r"\*\*Granskningsstatus:\*\*\s*([^|\n]+)", re.IGNORECASE)
_FILE_STATUS = re.compile(r"\*\*Status:\*\*\s*([^|\n.;]+)", re.IGNORECASE)
_ADOPTION = re.compile(r"\*\*Införandebeslut:\*\*\s*(B-\d{3,})", re.IGNORECASE)


class RuleStatus(StrEnum):
    UTKAST = "utkast"
    SPECIFICERAD = "specificerad"  # färdig specifikation, ännu inte införd
    GODKAND = "godkänd"  # godkänd regel eller regel i ett infört paket
    ERSATT = "ersatt"
    OKAND = "okänd"  # filen eller fältet saknas, eller okänt värde


def default_rules_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "01_domän" / "produktregler"


class ProductRuleCatalog:
    """Slår upp status per regel-id. Läser varje fil en gång."""

    def __init__(self, rules_dir: Path | None = None) -> None:
        self.rules_dir = rules_dir or default_rules_dir()
        self._cache: dict[str, RuleStatus] = {}
        self._adoption: str | None | bool = False  # False = inte läst än

    @property
    def adoption_decision(self) -> str | None:
        """B-numret för paketets införandebeslut, om paketet är infört."""
        if self._adoption is False:
            readme = self.rules_dir / "README.md"
            match = _ADOPTION.search(readme.read_text(encoding="utf-8")) if readme.exists() else None
            self._adoption = match.group(1) if match else None
        return self._adoption  # type: ignore[return-value]

    def status(self, rule_id: str) -> RuleStatus:
        if rule_id not in self._cache:
            self._cache[rule_id] = self._read_status(rule_id)
        return self._cache[rule_id]

    def refresh(self) -> None:
        """Läs om filerna, t.ex. efter att en regel eller ett paket godkänts."""
        self._cache.clear()
        self._adoption = False

    def _read_status(self, rule_id: str) -> RuleStatus:
        path = self._find(rule_id)
        if path is None:
            return RuleStatus.OKAND
        text = path.read_text(encoding="utf-8")

        review = _REVIEW_STATUS.search(text)
        if review:  # äldre format: status per regel
            return _parse(review.group(1))

        file_status = _FILE_STATUS.search(text)
        if not file_status:
            return RuleStatus.OKAND
        status = _parse(file_status.group(1))
        if status == RuleStatus.ERSATT:
            return status
        if status == RuleStatus.SPECIFICERAD and self.adoption_decision:
            return RuleStatus.GODKAND
        return status

    def _find(self, rule_id: str) -> Path | None:
        if not self.rules_dir.is_dir():
            return None
        for path in sorted(self.rules_dir.glob("*.md")):
            # "PR-ITP1-001-premietrappa.md" eller "PR-ITP1-001.md" – men inte "PR-ITP1-0010-…"
            if path.stem == rule_id or path.stem.startswith(f"{rule_id}-"):
                return path
        return None


def _parse(value: str) -> RuleStatus:
    word = value.strip().strip("*").strip().split()[0].lower() if value.strip() else ""
    if word.startswith("specificerad"):
        return RuleStatus.SPECIFICERAD
    try:
        return RuleStatus(word)
    except ValueError:
        return RuleStatus.OKAND
