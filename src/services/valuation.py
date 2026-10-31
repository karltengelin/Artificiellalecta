"""Värderingsmotorns körning i betrodd kod: utdrag, grund, kurva och beräkning (A6, B-042).

Kontrakt: projekt/06_avdelningsfunktioner/VARDERINGSKONTRAKT.md §2–7. `compute_valuation` bygger
datautdraget S-04 (`services.valuation_extract`), slår upp värderingsgrunden, kurvan och årets
skatteavdrag och värderar varje försäkring med `skills.calculation.fta_valuation`. Ingenting
sparas här; operationerna i `services/operations/valuations.py` sparar körningen, och
diagnosskriptet `scripts/diagnostics/valuation_summary.py` skriver bara aggregat.

**Bas eller scenario (§2).** En basvärdering görs per kvartalsslut med den värderingsgrund
(SIM-V) och den kurva (FI-SIM) som gäller datumet; bara en basvärdering kan låsas. Ett scenario
får göras vid vilket månadsslut som helst och med uttryckligt angiven grund och kurva, även
en som inte gäller datumet. Det märks som scenario och blir aldrig bas.

**Skatt (§4 S).** s_y är årets kundbelastning för avkastningsskatt i `product_parameters`
(`customer_tax_rate`, PR-ITP1-023), som är 15 % × max(SLR, 0,5 %) – samma regel som grundens
`tax`. Ett s_y under grundens golv stoppar körningen.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from analytics.portfolio_snapshot import cohort_of
from models import ValuationBasis
from services import parameters
from services import valuation_bases as vb
from services.errors import ServiceError
from services.valuation_extract import (
    ExtractError,
    ValuationExtract,
    build_extract,
    month_end,
)
from skills.calculation import fta_valuation as fv

Purpose = Literal["base", "scenario"]
#: Källfilerna vars innehåll ingår i kodversionen
CODE_FILES = (
    "skills/calculation/actuarial_annuity.py",
    "skills/calculation/capital_rollforward.py",
    "skills/calculation/fta_valuation.py",
    "services/valuation_extract.py",
    "services/valuation.py",
)
SOURCE_NOTE = {
    "reconstructed_s04": "Rekonstruerat startbestånd S-04 (B-042 val L): garantidelar och kapital räknade ur "
                         "premiehistoriken. Ersätts när paket B finns och får inte lämnas som FI-underlag utan märkningen.",
    "ledger": "Bokförda värden",
}
QUANTITIES = {
    "capital_sek": "C: pensionskapital (retrospektivt), inte garanterat",
    "guarantee_sek_per_month": "G: garanterad pension per månad, summa av garantidelarna",
    "fta_sek": "FTA: kapitalvärdet av G på värderingsgrunden plus driftkostnader (prospektivt)",
    "expenses_sek": "K: därav kapitalvärdet av framtida driftkostnader",
    "surplus_sek": "VÅ: villkorad återbäring, max(0, C − FTA) per försäkring",
    "deficit_sek": "U: underskott till följd av garanti, max(0, FTA − C) per försäkring (PR-ITP1-028)",
}


class ValuationError(ServiceError):
    """Värderingen kan inte göras: underkänt utdrag, saknad grund eller kurva, felaktigt datum."""


def code_version(root: Path | None = None) -> str:
    """Motorns version och en hash av källkoden (radslut normaliserade), för kontrollfall K6."""
    root = root or Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for name in CODE_FILES:
        digest.update(name.encode())
        digest.update((root / name).read_bytes().replace(b"\r\n", b"\n"))
    return f"{fv.ENGINE_VERSION}+{digest.hexdigest()[:12]}"


def is_quarter_end(day: date) -> bool:
    return day.month in (3, 6, 9, 12) and day == month_end(day)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class BasisRef:
    """Den använda grunden eller kurvan: kod och kontrollsumma (fristående från sessionen)."""

    code: str
    checksum: str


@dataclass
class Computation:
    valuation_date: date
    purpose: Purpose
    extract: ValuationExtract
    basis: BasisRef
    curve: BasisRef
    tax_reduction: Decimal
    tax_parameter: str
    code_version: str
    values: list[fv.PolicyValue]
    totals: fv.Totals
    segments: dict[tuple[str, str], fv.Totals]
    checks: list[Check]
    result_checksum: str

    @property
    def checks_passed(self) -> bool:
        return all(c.passed for c in self.checks)


def _basis(session: Session, family: str, on: date, purpose: Purpose, code: str | None) -> ValuationBasis:
    if code is not None:
        if purpose == "base":
            raise ValuationError("En basvärdering använder grunden och kurvan som gäller datumet – ange ingen kod")
        if vb.family_of(code) != family:
            raise ValuationError(f"{code} hör inte till familjen {family}")
        row = session.scalar(select(ValuationBasis).where(ValuationBasis.code == code))
        if row is None or row.status != "adopted":
            raise ValuationError(f"{code} finns inte som antagen grund")
    else:
        row = vb.in_force(session, family, on)
        if row is None:
            raise ValuationError(f"Ingen antagen grund i {family} gäller {on}"
                                 + (" – ett scenario kan ange grunden uttryckligen" if purpose == "base" else ""))
    try:
        vb.verify_checksum(row)
    except vb.BasisError as exc:
        raise ValuationError(str(exc)) from exc
    return row


def _tax(session: Session, valuation_date: date, tax: dict[str, Any]) -> tuple[Decimal, str]:
    try:
        _, rate, _, label = parameters.capital_rates(session, [valuation_date])[valuation_date.replace(day=1)]
    except ServiceError as exc:
        raise ValuationError(f"Skatteavdraget s_y saknas: {exc}") from exc
    floor = Decimal(str(tax["rate"])) * Decimal(str(tax["slr_floor"]))
    if rate < floor:
        raise ValuationError(f"s_y {rate} ligger under grundens golv {floor} (15 % × 0,5 %)")
    return rate, label


def policy_inputs(extract: ValuationExtract) -> list[fv.PolicyInput]:
    """Utdragets försäkringar som värderingens indata (födelse dag 1 eller 2, se S-04)."""
    out = []
    for p in extract.policies:
        year, month = (int(x) for x in p.birth_month.split("-"))
        out.append(fv.PolicyInput(
            policy_id=p.policy_id, birth=date(year, month, 1 if p.born_on_first else 2), state=p.state,
            plan_start=p.plan.start, guarantee=sum((g.guarantee for g in p.guarantee_parts), Decimal(0)),
            capital=p.capital))
    return out


def compute_valuation(session: Session, valuation_date: date, purpose: Purpose = "base", *,
                      basis_code: str | None = None, curve_code: str | None = None) -> Computation:
    """Bygger utdraget och värderar beståndet. Sparar ingenting."""
    if valuation_date != month_end(valuation_date):
        raise ValuationError("Värderingsdatumet ska vara ett månadsslut")
    if purpose == "base" and not is_quarter_end(valuation_date):
        raise ValuationError("En basvärdering görs per kvartalsslut (§2); välj scenario för andra datum")
    basis = _basis(session, "SIM-V", valuation_date, purpose, basis_code)
    curve = _basis(session, basis.assumptions["curve_family"], valuation_date, purpose, curve_code)
    s_y, tax_label = _tax(session, valuation_date, basis.assumptions["tax"])
    try:
        extract = build_extract(session, valuation_date)
    except ExtractError as exc:
        raise ValuationError(f"Datautdraget kan inte byggas: {exc}") from exc
    if not extract.approved:
        failed = ", ".join(c.name for c in extract.checks if not c.passed)
        raise ValuationError(f"Datautdraget är underkänt ({failed}) – värderingen stoppas (§5.3)")

    model = fv.ValuationModel.from_assumptions(basis.assumptions, curve.assumptions, float(s_y))
    values = fv.value_policies(model, valuation_date, policy_inputs(extract))
    total = fv.totals(values)
    k1 = fv.k1_engine_check(model.mortality)
    checks = [
        Check("datautdrag godkänt", extract.approved, f"{len(extract.checks)} kontroller enligt §5.3"),
        Check("K1 motorn", k1.quantize(Decimal("0.01")) == Decimal("1000.00"),
              f"En premie på 1 000 kr på 0 %-kurva utan skatt och kostnader ger {k1} kr"),
        Check("K10 summakontroll", total.balances,
              f"VÅ − U = {total.surplus - total.deficit} kr och ΣC − FTA = {total.capital - total.fta} kr"),
        Check("antal försäkringar", total.policies == len(extract.policies),
              f"{total.policies} värderade av {len(extract.policies)} i utdraget"),
    ]
    payload = fv.results_payload(values, total)
    payload["inputs"] = {"extract": extract.checksum, "basis": basis.checksum, "curve": curve.checksum,
                         "tax_reduction": str(s_y)}
    return Computation(
        valuation_date=valuation_date, purpose=purpose, extract=extract,
        basis=BasisRef(basis.code, basis.checksum), curve=BasisRef(curve.code, curve.checksum),
        tax_reduction=s_y, tax_parameter=tax_label, code_version=code_version(), values=values, totals=total,
        segments=fv.by_segment(values, cohort_of), checks=checks, result_checksum=vb.checksum(payload))


__all__ = ["CODE_FILES", "QUANTITIES", "SOURCE_NOTE", "BasisRef", "Check", "Computation", "ValuationError", "code_version",
           "compute_valuation", "is_quarter_end", "policy_inputs"]
