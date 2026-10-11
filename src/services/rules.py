"""Läser produktreglernas status ur 01_domän/produktregler/.

Formatet ägs av delprojekt 4. Två format stöds:

- **Regelpaket (PR-ITP1 v1.0 och senare):** varje regelfil har
  `**Status:** Specificerad …`, och hela paketet införs med ett samlat beslut
  (projekt/04_produktregelverk/PAKET_BESLUTSFORSLAG.md). Paketet räknas som
  godkänt när paketets README har raden `**Införandebeslut:** B-nnn` och dagen
  i `**Gäller från:** ÅÅÅÅ-MM-DD` (om angiven) har kommit. Ett infört paket med
  senare giltighetsdag är `kommande` – reglerna gäller inte än.
- **Äldre format:** `**Granskningsstatus:** utkast|godkänd|ersatt` per regel.

En enskild regel som är `ersatt` är alltid ej godkänd. Allt som inte går att
läsa – saknad fil, saknat fält, okänt värde – räknas som ej godkänt.

Tre saker hålls isär (tjänstelager.md §4): godkänd specifikation (status),
giltighet för en händelse (`Gäller från`) och teknisk implementation (vilka
operationer som anger regeln). `describe()` ger regelstatus och filversion
vid en verkställighet – det som skrivs i händelseloggen.
"""

from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from pathlib import Path

_REVIEW_STATUS = re.compile(r"\*\*Granskningsstatus:\*\*\s*([^|\n]+)", re.IGNORECASE)
_FILE_STATUS = re.compile(r"\*\*Status:\*\*\s*([^|\n.;]+)", re.IGNORECASE)
_FILE_VERSION = re.compile(r"\*\*(?:Filversion|Version):\*\*\s*([0-9][0-9.]*)", re.IGNORECASE)
_ADOPTION = re.compile(r"\*\*Införandebeslut:\*\*\s*(B-\d{3,})", re.IGNORECASE)
_VALID_FROM = re.compile(r"\*\*Gäller från:\*\*\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
_PACKAGE = re.compile(r"\*\*Paket:\*\*\s*([^|\n]+?)\s*(?:\||$)", re.IGNORECASE | re.MULTILINE)


class RuleStatus(StrEnum):
    UTKAST = "utkast"
    SPECIFICERAD = "specificerad"  # färdig specifikation, ännu inte införd
    KOMMANDE = "kommande"  # införd, men giltighetsdagen har inte kommit
    GODKAND = "godkänd"  # godkänd regel eller regel i ett infört och giltigt paket
    ERSATT = "ersatt"
    OKAND = "okänd"  # filen eller fältet saknas, eller okänt värde


def default_rules_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "01_domän" / "produktregler"


class ProductRuleCatalog:
    """Slår upp status per regel-id. Läser varje fil en gång.

    today: dagen giltigheten prövas mot (standard: dagens datum) – sätts i tester.
    """

    def __init__(self, rules_dir: Path | None = None, today: date | None = None) -> None:
        self.rules_dir = rules_dir or default_rules_dir()
        self._today = today
        self._cache: dict[str, RuleStatus] = {}
        self._readme: str | None = None

    # --- paketet ------------------------------------------------------------

    def _readme_text(self) -> str:
        if self._readme is None:
            readme = self.rules_dir / "README.md"
            self._readme = readme.read_text(encoding="utf-8") if readme.exists() else ""
        return self._readme

    @property
    def today(self) -> date:
        return self._today or date.today()

    @property
    def adoption_decision(self) -> str | None:
        """B-numret för paketets införandebeslut, om paketet är infört."""
        match = _ADOPTION.search(self._readme_text())
        return match.group(1) if match else None

    @property
    def valid_from(self) -> date | None:
        """Paketets giltighetsdag enligt införandebeslutet, om angiven."""
        if not self.adoption_decision:
            return None
        match = _VALID_FROM.search(self._readme_text())
        return date.fromisoformat(match.group(1)) if match else None

    @property
    def package(self) -> str | None:
        """Paketets namn och version, t.ex. 'PR-ITP1 v1.0'."""
        match = _PACKAGE.search(self._readme_text())
        return match.group(1).strip() if match else None

    # --- regler -------------------------------------------------------------

    def status(self, rule_id: str) -> RuleStatus:
        if rule_id not in self._cache:
            self._cache[rule_id] = self._read_status(rule_id)
        return self._cache[rule_id]

    def label(self, rule_id: str) -> str:
        """Status med giltighetsdag när regeln är införd men inte gäller än."""
        status = self.status(rule_id)
        if status == RuleStatus.KOMMANDE and self.valid_from:
            return f"{status.value}, gäller från {self.valid_from.isoformat()}"
        return status.value

    def version(self, rule_id: str) -> str | None:
        path = self._find(rule_id)
        match = _FILE_VERSION.search(path.read_text(encoding="utf-8")) if path else None
        return match.group(1) if match else None

    def describe(self, rule_ids: tuple[str, ...] | list[str]) -> str:
        """Regelstatus vid en verkställighet, t.ex. för händelseloggen."""
        rules = ", ".join(
            f"{rule_id}" + (f" v{v}" if (v := self.version(rule_id)) else "") + f" {self.label(rule_id)}"
            for rule_id in rule_ids
        )
        package = self.package
        if package is None:
            return f"Regelstatus: {rules}"
        if self.adoption_decision:
            adopted = f"infört {self.adoption_decision}" + (
                f", gäller från {self.valid_from.isoformat()}" if self.valid_from else ""
            )
        else:
            adopted = "ej infört"
        return f"Regelstatus: {rules}; paket {package} {adopted}"

    def refresh(self) -> None:
        """Läs om filerna, t.ex. efter att en regel eller ett paket godkänts."""
        self._cache.clear()
        self._readme = None

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
            if self.valid_from and self.valid_from > self.today:
                return RuleStatus.KOMMANDE
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
