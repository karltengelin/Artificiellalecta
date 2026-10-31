"""Aktuariell beräkningsmotor: dödlighet, annuitetsfaktor och garantidelar (A5, B-042).

Instruktion: 03_skills/beräkning/aktuariell-annuitet.md
Domänregler: 01_domän/aktuariell_grund.md §2–4; facit i projekt/04_produktregelverk/LEVERANSKONTROLL.md §3

Ren beräkning utan sidoeffekter. Dödlighetstabellen läses ur den låsta källfilen
01_domän/parametrar/DODLIGHET_SCB_2025.md och prövas mot sin dokumenterade kontrollsumma; en
ändrad tabell stoppar beräkningen. Grundens parametrar kommer ur antagandebiblioteket
(`valuation_bases`, schemat `Mortality` i services/valuation_bases.py).

Modell (aktuariell_grund.md §2–3):

    Q_x      = w × SCB_män_x + (1−w) × SCB_kvinnor_x          (promille / 1000)
    q(x, y)  = faktor × Q_x × (1 − förbättring)^max(0, y − basår),   x ≤ 100
    q(x)     = min(tak, 1 − exp(−mu100 × (1 + ökning)^(x−100))),       x > 100
    mu100    = −ln(1 − q(100, födelseår + 100))
    q_m      = 1 − (1 − q)^(1/12)

Ålder x är fyllda år vid månadens första dag och y månadens kalenderår. Annuitetsfaktorn vid
värdering t (ett månadsslut) summerar vikten för varje betalningsmånad: första månaden efter t
har vikten 1, senare månader produkten av månadsöverlevnaden för mellanliggande månader. Med
nettoränta i diskonteras rätten till slutet av sin månad. En livsvarig plan summeras tills
dödsrisken nått taket för alla senare åldrar; resten är en exakt geometrisk serie.

Talen är flyttal med dubbel precision; belopp avrundas av anroparen.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

#: Den låsta tabellens fil och kontrollsumma (LEVERANSKONTROLL.md §2: UTF-8 utan BOM, LF-radslut)
TABLE_PATH = Path(__file__).resolve().parents[3] / "01_domän" / "parametrar" / "DODLIGHET_SCB_2025.md"
TABLE_SHA256 = "d0b6872d317b975cdec57f09cd66afb65c5365000f3f5cc253889a785d31dd5d"
TABLE_ID = "SCB-2025-BE0101A"
MAX_TABLE_AGE = 100
#: Säkerhetsgräns för summeringen innan svansen är konstant (ålder i år)
MAX_SUM_AGE = 200


class TableError(ValueError):
    """Dödlighetstabellen saknas, är ändrad eller ofullständig."""


@lru_cache(maxsize=1)
def scb_table(path: Path = TABLE_PATH) -> dict[int, tuple[float, float]]:
    """Ålder → (män, kvinnor) i promille, efter kontroll av kontrollsumman."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TableError(f"Dödlighetstabellen kan inte läsas: {path}") from exc
    normalized = raw.removeprefix(b"\xef\xbb\xbf").replace(b"\r\n", b"\n")
    if hashlib.sha256(normalized).hexdigest() != TABLE_SHA256:
        raise TableError("Dödlighetstabellens kontrollsumma stämmer inte – tabellen har ändrats")
    rows = {int(a): (float(m), float(f)) for a, m, f in
            re.findall(r"^\| (\d+) \| ([\d.]+) \| ([\d.]+) \|$", normalized.decode("utf-8"), re.MULTILINE)}
    if sorted(rows) != list(range(MAX_TABLE_AGE + 1)):
        raise TableError("Dödlighetstabellen ska ha åldrarna 0–100")
    return rows


@dataclass(frozen=True)
class MortalityBasis:
    """En grunds dödlighet (schemat `Mortality` i antagandebiblioteket)."""

    male_weight: float
    improvement_per_year: float
    improvement_base_year: int
    risk_factor: float
    tail_from_age: int
    tail_intensity_growth: float
    tail_q_cap: float

    @classmethod
    def from_assumptions(cls, mortality: Mapping[str, Any]) -> MortalityBasis:
        if mortality.get("table") != TABLE_ID:
            raise TableError(f"Okänd dödlighetstabell {mortality.get('table')!r}; motorn känner {TABLE_ID}")
        if int(mortality["tail_from_age"]) != MAX_TABLE_AGE:
            raise TableError("Motorn stöder bara svans från ålder 100 (aktuariell_grund.md §2)")
        return cls(
            male_weight=float(Decimal(str(mortality["male_weight"]))),
            improvement_per_year=float(Decimal(str(mortality["improvement_per_year"]))),
            improvement_base_year=int(mortality["improvement_base_year"]),
            risk_factor=float(Decimal(str(mortality["risk_factor"]))),
            tail_from_age=int(mortality["tail_from_age"]),
            tail_intensity_growth=float(Decimal(str(mortality["tail_intensity_growth"]))),
            tail_q_cap=float(Decimal(str(mortality["tail_q_cap"]))),
        )

    def scaled(self, factor: float) -> MortalityBasis:
        """Samma grund med dödsrisken multiplicerad, t.ex. PR-028:s stress (0,80)."""
        return MortalityBasis(self.male_weight, self.improvement_per_year, self.improvement_base_year,
                              self.risk_factor * factor, self.tail_from_age, self.tail_intensity_growth,
                              self.tail_q_cap)


def _table_q(basis: MortalityBasis, age: int, year: int) -> float:
    male, female = scb_table()[age]
    base = (basis.male_weight * male + (1 - basis.male_weight) * female) / 1000
    years = max(0, year - basis.improvement_base_year)
    return basis.risk_factor * base * (1 - basis.improvement_per_year) ** years


def annual_q(basis: MortalityBasis, age: int, year: int, birth_year: int) -> float:
    """Årlig dödsrisk för ålder `age` (fyllda år) under kalenderåret `year`."""
    if age < 0:
        raise ValueError("Negativ ålder")
    if age <= basis.tail_from_age:
        return _table_q(basis, age, year)
    q100 = _table_q(basis, basis.tail_from_age, birth_year + basis.tail_from_age)
    mu = -math.log(1 - q100) * (1 + basis.tail_intensity_growth) ** (age - basis.tail_from_age)
    return min(basis.tail_q_cap, 1 - math.exp(-mu))


def monthly_q(basis: MortalityBasis, birth: date, month: date) -> float:
    """Dödsrisk under månaden som börjar `month`, med ålder vid månadens första dag."""
    return 1 - (1 - annual_q(basis, age_on(birth, month), month.year, birth.year)) ** (1 / 12)


def age_on(birth: date, day: date) -> int:
    """Fyllda år på dagen `day`."""
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))


def add_months(month: date, n: int) -> date:
    index = month.year * 12 + month.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


def first_month_after(valuation: date) -> date:
    """Första månaden efter värderingen vid ett månadsslut."""
    return add_months(valuation.replace(day=1), 1)


def _capped_from(basis: MortalityBasis, birth: date) -> int | None:
    """Åldern från vilken årsrisken ligger på taket för alla senare åldrar, om den nås."""
    for age in range(basis.tail_from_age + 1, MAX_SUM_AGE):
        if annual_q(basis, age, birth.year + age, birth.year) >= basis.tail_q_cap:
            return age
    return None


def annuity_factor(
    basis: MortalityBasis,
    birth: date,
    valuation: date,
    start: date,
    payments: int | None,
    *,
    paused: Iterable[date] = (),
    net_interest_rate: float = 0.0,
) -> float:
    """A(t, D): summan av vikter (och diskontering) för planens betalningsmånader.

    `valuation` är ett månadsslut, `start` första betalningsmånaden (månadsförsta, efter
    värderingen). `payments` är antalet betalningsmånader, None för livsvarig plan. `paused`
    är månader utan betalning; överlevnaden under dem ingår ändå i senare vikter.
    """
    first = first_month_after(valuation)
    if start.day != 1 or start < first:
        raise ValueError("Första betalningsmånaden ska vara en månadsförsta efter värderingen")
    if payments is not None and payments <= 0:
        raise ValueError("Antalet betalningsmånader ska vara positivt")
    skip = set(paused)
    v = (1 + net_interest_rate) ** (-1 / 12)
    capped = _capped_from(basis, birth) if payments is None else None
    if payments is None and capped is None:
        raise ValueError("Svansen når inte taket – en livsvarig faktor kan inte avslutas exakt")

    total, weight, month, made, k = 0.0, 1.0, first, 0, 0
    while True:
        if month >= start and month not in skip:
            if payments is None and capped is not None and age_on(birth, month) >= capped and not any(m >= month for m in skip):
                # Konstant månadsöverlevnad p från och med nu: Σ w·(p·v)^j = w / (1 − p·v)
                p = 1 - monthly_q(basis, birth, month)
                total += weight * v ** (k + 1) / (1 - p * v)
                return total
            total += weight * v ** (k + 1)
            made += 1
            if payments is not None and made == payments:
                return total
        weight *= 1 - monthly_q(basis, birth, month)
        month, k = add_months(month, 1), k + 1
        if age_on(birth, month) > MAX_SUM_AGE:
            raise ValueError("Summeringen nådde säkerhetsgränsen utan att avslutas")


def reference_start(birth: date, received: date, pension_age: int = 66) -> date:
    """Referensplanens första månad: 66-årsmånaden, eller tidigast månaden efter mottagningen."""
    birthday_month = date(birth.year + pension_age, birth.month, 1)
    return max(birthday_month, first_month_after(received))


def guarantee_part(
    basis: MortalityBasis, birth: date, received_month_end: date, net_premium: Decimal,
    *, net_interest_rate: float = 0.0, pension_age: int = 66,
) -> tuple[float, float]:
    """(G_j, A_g) för en mottagen nettopremie: G_j = P_j / A_g(t_j, livsvarigt från referensstart)."""
    start = reference_start(birth, received_month_end, pension_age)
    factor = annuity_factor(basis, birth, received_month_end, start, None, net_interest_rate=net_interest_rate)
    return float(net_premium) / factor, factor


def basis_from_assumptions(assumptions: Mapping[str, Any]) -> tuple[MortalityBasis, float]:
    """Dödlighet och nettoränta ur en garanti-, historik- eller utbetalningsgrund."""
    return (MortalityBasis.from_assumptions(assumptions["mortality"]),
            float(Decimal(str(assumptions.get("net_interest_rate", "0")))))
