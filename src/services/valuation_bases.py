"""Antagandebiblioteket: scheman, kontrollsumma och startgrunder (A4, B-042).

Innehållet i en grund (`assumptions`) prövas mot schemat för grundens ändamål och lagras som
JSON i normaliserad form; kontrollsumman är SHA-256 av den kanoniska JSON-texten. Samma text
ger alltid samma summa, så en ändrad rad upptäcks när den läses (`verify_checksum`).

Startgrunderna följer 01_domän/parametrar/PARAMETERREGISTER.md (SIM-G/B/R-2026-01 och
SIM-HIST-2023-01, B-031) och värderingskontraktet A1 §4 med M1–M5 fastställda 2026-10-31
(SIM-V-2026-01 och kurvan FI-SIM-2026-10, B-042). Tal är simuleringsval, inte kalibrerade
branschvärden; kurvan är syntetisk.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models import ValuationBasis
from models.valuation_basis import BASIS_FAMILIES


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Mortality(_Strict):
    """Unisexdödlighet enligt aktuariell_grund.md §2."""

    table: Literal["SCB-2025-BE0101A"] = Field(description="Låst SCB-tabell (DODLIGHET_SCB_2025.md)")
    male_weight: Decimal = Field(ge=0, le=1, description="Andel män i unisexvikten")
    improvement_per_year: Decimal = Field(ge=0, le=Decimal("0.1"), description="Lägre dödsrisk per kalenderår")
    improvement_base_year: int = Field(ge=2000, le=2100)
    risk_factor: Decimal = Field(gt=0, le=2, description="Multiplikator på dödsrisken; 0,80 = marginal")
    tail_from_age: int = Field(ge=90, le=110)
    tail_intensity_growth: Decimal = Field(ge=0, le=1, description="Årlig ökning av dödsintensiteten i svansen")
    tail_q_cap: Decimal = Field(gt=0, lt=1)


class GuaranteeAssumptions(_Strict):
    """Garanti-, historik- och utbetalningsgrund: nettoränta och dödlighet."""

    net_interest_rate: Decimal = Field(ge=-1, le=Decimal("0.1"))
    mortality: Mortality


class RiskAssumptions(_Strict):
    """Riskgrund för arvsvinst: aktuell dödlighet utan marginal."""

    mortality: Mortality


class CurvePoint(_Strict):
    term_years: int = Field(ge=1, le=200)
    spot_rate: Decimal = Field(ge=Decimal("-0.05"), le=Decimal("0.2"))


class CurveAssumptions(_Strict):
    """Diskonteringskurva: årliga spoträntor, linjär interpolation och konstant efter sista löptiden."""

    synthetic: bool = Field(description="Syntetisk sandboxkurva, inte FI:s publicerade")
    construction: str = Field(min_length=1, max_length=300)
    interpolation: Literal["linear"] = "linear"
    extrapolation: Literal["flat"] = "flat"
    points: list[CurvePoint] = Field(min_length=2)

    @field_validator("points")
    @classmethod
    def _increasing(cls, points: list[CurvePoint]) -> list[CurvePoint]:
        terms = [p.term_years for p in points]
        if terms != sorted(set(terms)):
            raise ValueError("Löptiderna ska vara strikt stigande")
        return points


class MonthlyReturn(_Strict):
    month: date = Field(description="Månadsförsta")
    rate: Decimal = Field(ge=-1, le=1, description="Avkastning under månaden, t.ex. 0.012 = 1,2 %")


class ReturnSeriesAssumptions(_Strict):
    """Deklarerad månadsavkastning för rekonstruktionen av pensionskapitalet (S-04, PR-ITP1-021).

    Avkastningen är efter direkta placeringskostnader men före kapitalavgiften och
    avkastningsskattebelastningen, som dras separat (PR-ITP1-022/023).
    """

    synthetic: bool = Field(description="Syntetisk bana, inte kapitalförvaltningens leverans")
    description: str = Field(min_length=1, max_length=500)
    definition: Literal["after_direct_costs_before_fee_and_tax"] = "after_direct_costs_before_fee_and_tax"
    months: list[MonthlyReturn] = Field(min_length=1)

    @field_validator("months")
    @classmethod
    def _consecutive(cls, months: list[MonthlyReturn]) -> list[MonthlyReturn]:
        for previous, current in zip(months, months[1:]):
            expected = date(previous.month.year + (previous.month.month == 12), previous.month.month % 12 + 1, 1)
            if current.month != expected:
                raise ValueError(f"Månaderna ska vara i följd: {current.month} efter {previous.month}")
        if any(m.month.day != 1 for m in months):
            raise ValueError("Varje månad anges med månadsförsta")
        return months


class Tax(_Strict):
    rate: Decimal = Field(ge=0, le=1, description="Skattesats på schablonintäkten")
    slr_floor: Decimal = Field(ge=0, le=Decimal("0.1"))
    method: Literal["discount_reduction"] = Field(description="Diskontera med r − s_y (A1 M2)")


class Expenses(_Strict):
    deferred_sek_per_year: Decimal = Field(ge=0)
    payout_sek_per_year: Decimal = Field(ge=0)
    indexation: Decimal = Field(ge=0, le=Decimal("0.2"))


class ValuationAssumptions(_Strict):
    """Värderingsgrund för FTA (VARDERINGSKONTRAKT.md §4)."""

    curve_family: Literal["FI-SIM"] = Field(description="Kurvan som gäller värderingsdatumet i familjen")
    tax: Tax
    mortality: Mortality
    expenses: Expenses
    reference_plan: Literal["lifelong_from_66"] = Field(description="Ej påbörjade försäkringar: livsvarigt från 66")
    option_adjustment: Literal["none"] = Field(description="Ingen optionsjustering i v1 (A1 M5)")


SCHEMAS: dict[str, type[_Strict]] = {
    "guarantee": GuaranteeAssumptions,
    "payout": GuaranteeAssumptions,
    "risk": RiskAssumptions,
    "valuation": ValuationAssumptions,
    "discount_curve": CurveAssumptions,
    "return_series": ReturnSeriesAssumptions,
}


class BasisError(ValueError):
    """Grundens innehåll stämmer inte med schemat eller kontrollsumman."""


def normalize(purpose: str, assumptions: dict[str, Any]) -> dict[str, Any]:
    """Antagandena prövade mot ändamålets schema, i normaliserad JSON-form."""
    try:
        return SCHEMAS[purpose].model_validate(assumptions).model_dump(mode="json")
    except ValidationError as exc:
        raise BasisError(f"Antagandena stämmer inte med schemat för {purpose}: {exc}") from exc


def checksum(assumptions: dict[str, Any]) -> str:
    text = json.dumps(assumptions, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_checksum(row: ValuationBasis) -> None:
    if checksum(row.assumptions) != row.checksum:
        raise BasisError(f"Kontrollsumman för {row.code} stämmer inte – innehållet har ändrats")


def family_of(code: str) -> str:
    """Familjen ur koden: SIM-V-2026-01 → SIM-V, FI-SIM-2026-10 → FI-SIM."""
    family = next((f for f in sorted(BASIS_FAMILIES, key=len, reverse=True) if code.startswith(f + "-")), None)
    if family is None:
        raise BasisError(f"Okänd familj i {code} (kända: {', '.join(BASIS_FAMILIES)})")
    return family


def in_force(session: Session, family: str, on: date) -> ValuationBasis | None:
    """Den antagna grunden i familjen som gäller dagen `on`, om någon."""
    return session.scalar(select(ValuationBasis).where(
        ValuationBasis.family == family, ValuationBasis.status == "adopted", ValuationBasis.valid_from <= on,
        or_(ValuationBasis.valid_to.is_(None), ValuationBasis.valid_to >= on),
    ))


# --- startgrunder ------------------------------------------------------------------------------

_SCB = dict(table="SCB-2025-BE0101A", male_weight="0.5", improvement_per_year="0.015", improvement_base_year=2025,
            tail_from_age=100, tail_intensity_growth="0.10", tail_q_cap="0.995")
_GUARANTEE_MORTALITY = {**_SCB, "risk_factor": "0.80"}
_CURVE_M1 = [(1, "0.0250"), (2, "0.0255"), (3, "0.0260"), (5, "0.0270"), (7, "0.0278"), (10, "0.0286"),
             (15, "0.0294"), (20, "0.0300"), (30, "0.0315"), (40, "0.0325"), (50, "0.0332"), (60, "0.0336"),
             (80, "0.0339"), (100, "0.0340"), (150, "0.0340")]

#: (kod, titel, antaganden, giltig från, giltig till, beslut, källor)
START_BASES: tuple[tuple[str, str, dict[str, Any], date, date | None, str, str], ...] = (
    ("SIM-HIST-2023-01", "Historikgrund för omgenererad mockhistorik",
     {"net_interest_rate": "0", "mortality": _GUARANTEE_MORTALITY}, date(2023, 1, 1), date(2026, 10, 31),
     "B-031", "PARAMETERREGISTER.md; aktuariell_grund.md"),
    ("SIM-G-2026-01", "Garantitariff för nya garantidelar",
     {"net_interest_rate": "0", "mortality": _GUARANTEE_MORTALITY}, date(2026, 11, 1), None,
     "B-031", "PARAMETERREGISTER.md; aktuariell_grund.md §2–4; B-027"),
    ("SIM-B-2026-01", "Utbetalningsgrund",
     {"net_interest_rate": "0", "mortality": _GUARANTEE_MORTALITY}, date(2026, 11, 1), None,
     "B-031", "PARAMETERREGISTER.md; aktuariell_grund.md §3, §5"),
    ("SIM-R-2026-01", "Riskgrund för arvsvinst",
     {"mortality": {**_SCB, "risk_factor": "1"}}, date(2026, 11, 1), None,
     "B-031", "PARAMETERREGISTER.md; PR-ITP1-011"),
    ("FI-SIM-2026-10", "Syntetisk diskonteringskurva, startkurva",
     {"synthetic": True, "construction": "Syntetisk startkurva enligt A1 M1: 2,5 % (1 år), 3,0 % (20 år), "
                                         "mot 3,4 % på lång sikt. Inte FI:s publicerade kurva.",
      "points": [{"term_years": t, "spot_rate": r} for t, r in _CURVE_M1]},
     date(2026, 10, 31), None, "B-042; A1 M1 fastställt 2026-10-31", "VARDERINGSKONTRAKT.md §4 R; FFFS 2019:21 4 kap."),
    ("SIM-V-2026-01", "Värderingsgrund för FTA (garanterat åtagande)",
     {"curve_family": "FI-SIM", "tax": {"rate": "0.15", "slr_floor": "0.005", "method": "discount_reduction"},
      "mortality": _GUARANTEE_MORTALITY,
      "expenses": {"deferred_sek_per_year": "180", "payout_sek_per_year": "240", "indexation": "0.02"},
      "reference_plan": "lifelong_from_66", "option_adjustment": "none"},
     date(2026, 12, 31), None, "B-042; A1 M2–M5 fastställda 2026-10-31",
     "VARDERINGSKONTRAKT.md §4; PR-ITP1-023; Alecta FTR §4"),
)
#: AVK-SIM-2026-01: syntetisk varierande bana 2023-01–2026-10 i procent per månad (operatörens val 2026-10-31).
#: Helår: 2023 +7,07 %, 2024 +9,20 %, 2025 +4,84 %; 2026 januari–oktober +2,09 %.
_RETURN_PATH = {
    2023: "2.10 -1.20 0.40 0.90 0.30 1.40 1.30 -0.80 -1.80 -1.50 3.30 2.60",
    2024: "0.80 1.60 1.90 -1.60 1.70 1.20 0.60 0.50 1.10 -0.40 1.80 -0.30",
    2025: "1.90 -0.50 -2.40 -3.10 2.80 1.30 1.40 0.70 1.10 1.20 -0.30 0.80",
    2026: "1.10 0.60 -1.40 0.90 -0.70 0.40 1.20 -0.50 0.30 0.20",
}
START_BASES += (
    ("AVK-SIM-2026-01", "Syntetisk avkastningsserie för rekonstruerat startbestånd",
     {"synthetic": True,
      "description": "Syntetisk varierande bana 2023-01–2026-10 för en traditionell portfölj, ungefär 55 % räntor, "
                     "35 % aktier och 10 % kassa. Inte kapitalförvaltningens leverans.",
      "months": [{"month": date(y, m + 1, 1).isoformat(), "rate": str(Decimal(r) / 100)}
                 for y, rates in _RETURN_PATH.items() for m, r in enumerate(rates.split())]},
     date(2023, 1, 1), None, "Operatörens val 2026-10-31: syntetisk varierande bana (A5)",
     "AKTUARIETEAM_PLAN.md §3.5; VARDERINGSKONTRAKT.md §5.2; PR-ITP1-021"),
)
SEED_ACTOR = "system:seed"


def default_rows() -> list[ValuationBasis]:
    """Startgrunderna som antagna rader – för migrationen och demo-/testdatabaserna."""
    rows = []
    for code, title, raw, valid_from, valid_to, decision, sources in START_BASES:
        family = family_of(code)
        purpose = BASIS_FAMILIES[family]
        assumptions = normalize(purpose, raw)
        rows.append(ValuationBasis(
            code=code, family=family, purpose=purpose, title=title, assumptions=assumptions,
            checksum=checksum(assumptions), source_refs=sources, status="adopted", valid_from=valid_from,
            valid_to=valid_to, decision_ref=decision, proposal_reason="Startgrund", created_by=SEED_ACTOR,
            adopted_by=SEED_ACTOR,
        ))
    return rows


def add_missing_defaults(session: Session) -> int:
    """Lägger in de startgrunder som saknas (på kod). Antal tillagda."""
    existing = set(session.scalars(select(ValuationBasis.code)))
    rows = [r for r in default_rows() if r.code not in existing]
    session.add_all(rows)
    return len(rows)


__all__ = [
    "SCHEMAS", "START_BASES", "BasisError", "CurveAssumptions", "GuaranteeAssumptions", "ReturnSeriesAssumptions",
    "RiskAssumptions",
    "ValuationAssumptions", "add_missing_defaults", "checksum", "default_rows", "family_of", "in_force",
    "normalize", "verify_checksum",
]
