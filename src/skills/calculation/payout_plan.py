"""Uttagsplanens kalender, pensionsbelopp och garantiomräkning (paket B steg 4, B-047 punkt 3, Karls val V1–V11).

Domänregler: PR-ITP1-003–009 och 024–025, UTTAG_GEMENSAMT och aktuariell_grund.md §3–5.
Ren beräkning utan sidoeffekter; tjänstelagret (`services.payout_plans`) läser journal och grunder.

**Kalendern.** En plan har första rätt (originalstart), form och, för tidsbegränsad plan, antal
rättigheter N. Pauser är halvöppna intervall `[första pausmånad, återstartsmånad)`. Varje månad med
rätt förbrukas en gång (PR-ITP1-006); pausmånader förbrukar inget och flyttar den tidsbegränsade
planens kalenderslut (PR-ITP1-004). Livsvarig plan har inget slut.

**Beloppet (PR-ITP1-009, aktuariell_grund.md §5).**

    M = max(round_half_up(max(G, B)), ceil_öre(ΣG_j), tidigare bindande golv)

Det bindande golvet gäller livsvarig del under de första 60 rättigheterna för oförändrad plan: en paus
eller återstart återställer det inte, men en verklig förlängning till livsvarig ger ny nivå (PR-ITP1-007).

**Garantiomräkning (PR-ITP1-008).** Per garantidel på sin historiska grund:
`V_j = G_j × A_gj(gammal plan)` och `G_j_ny = V_j / A_gj(ny plan)`. Vid delning delas G_j
proportionellt utan ny värdering. Fall 12: G_j = 10, A = 200 → 160 ger V_j = 2 000 och G_j_ny = 12,5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from skills.calculation.actuarial_annuity import add_months, first_month_after

CENT = Decimal("0.01")
#: Minsta antal rättigheter i tidsbegränsad plan (PR-ITP1-006)
MIN_PAYMENTS = 60
#: Livsvarig dels försiktiga beloppsgolv gäller de första 60 rättigheterna (PR-ITP1-009)
FLOOR_RIGHTS = 60
PENSION_AGE = 66
FORMS = ("lifelong", "fixed_term")


class PlanError(ValueError):
    """Planen eller ändringen är inte tillåten enligt produktreglerna."""


def sixty_six_month(birth: date, pension_age: int = PENSION_AGE) -> date:
    """66-årsmånaden: månaden personen fyller 66 (PR-ITP1-025)."""
    return date(birth.year + pension_age, birth.month, 1)


def deadline_for(change_month: date) -> date:
    """Fristen: sista kalenderdagen i månaden före ändringsmånaden (UTTAG_GEMENSAMT)."""
    first = change_month.replace(day=1)
    return date.fromordinal(first.toordinal() - 1)


def next_possible_month(received: date) -> date:
    """Första ändringsmånad som en begäran mottagen `received` är i tid för."""
    return add_months(received.replace(day=1), 1)


@dataclass(frozen=True)
class Schedule:
    """Planens rättighetskalender: första rätt, N (None = livsvarig) och pauser."""

    first_right: date
    payments: int | None
    pauses: tuple[tuple[date, date], ...] = field(default=())

    def __post_init__(self) -> None:
        if self.first_right.day != 1:
            raise PlanError("Första rätt ska vara en månadsförsta")
        if self.payments is not None and self.payments <= 0:
            raise PlanError("Antalet rättigheter ska vara positivt")
        previous_end = None
        for first, resume in self.pauses:
            if first.day != 1 or resume.day != 1 or resume <= first:
                raise PlanError("En paus är minst en hel månad: första pausmånad före återstartsmånaden")
            if first <= self.first_right:
                raise PlanError("En paus börjar efter första rätt (PR-ITP1-004)")
            if previous_end is not None and first < previous_end:
                raise PlanError("Pauserna överlappar")
            previous_end = resume

    @property
    def form(self) -> str:
        return "lifelong" if self.payments is None else "fixed_term"

    def paused(self, month: date) -> bool:
        return any(first <= month < resume for first, resume in self.pauses)

    def _rights(self, until: date | None = None):
        """Rättighetsmånaderna i ordning, till och med `until` (måste anges för livsvarig plan)."""
        month, made = self.first_right, 0
        while (self.payments is None or made < self.payments) and (until is None or month <= until):
            if not self.paused(month):
                made += 1
                yield month
            month = add_months(month, 1)

    def rights_before(self, month: date) -> int:
        """Förbrukade rättigheter före månaden `month`."""
        month = month.replace(day=1)
        if month <= self.first_right:
            return 0
        return sum(1 for _ in self._rights(add_months(month, -1)))

    def has_right(self, month: date) -> bool:
        month = month.replace(day=1)
        if month < self.first_right or self.paused(month):
            return False
        return self.payments is None or self.rights_before(month) < self.payments

    @property
    def end_month(self) -> date | None:
        """Sista rättens månad, None för livsvarig plan (PR-ITP1-006)."""
        if self.payments is None:
            return None
        return list(self._rights())[-1]

    def remaining_from(self, month: date) -> int | None:
        """Rättigheter kvar från och med `month`; None för livsvarig plan."""
        return None if self.payments is None else self.payments - self.rights_before(month)

    def factor_arguments(self, valuation: date) -> dict:
        """Argument till `annuity_factor` för planens återstående rätt efter värderingen `valuation`."""
        start = max(self.first_right, first_month_after(valuation))
        remaining = self.remaining_from(start)
        if remaining is not None and remaining <= 0:
            raise PlanError("Planen har inga rättigheter kvar efter värderingen")
        last = self.end_month
        paused = [m for first, resume in self.pauses for m in _months(first, resume)
                  if m >= start and (last is None or m <= last)]
        return {"start": start, "payments": remaining, "paused": paused}

    def plain(self) -> dict:
        return {"first_right": self.first_right.isoformat(), "form": self.form, "payments": self.payments,
                "pauses": [{"first": f.isoformat(), "resume": r.isoformat()} for f, r in self.pauses],
                "end_month": self.end_month.isoformat() if self.end_month else None}

    @classmethod
    def from_plain(cls, data: dict) -> Schedule:
        return cls(date.fromisoformat(data["first_right"]), data.get("payments"),
                   tuple((date.fromisoformat(p["first"]), date.fromisoformat(p["resume"]))
                         for p in data.get("pauses", [])))


def _months(first: date, end: date) -> list[date]:
    out, month = [], first
    while month < end:
        out.append(month)
        month = add_months(month, 1)
    return out


# --- ändringar ------------------------------------------------------------------------------------


def start_plan(first_right: date, payments: int | None, birth: date, *, current: Schedule | None,
               change_month: date) -> Schedule:
    """Första start, uppskov eller ändrad framtida start för en ej startad del (PR-ITP1-003, -006, -025)."""
    if first_right < sixty_six_month(birth):
        raise PlanError("Uttag före 66 år (PR-ITP1-002) ingår inte i första versionen (PB1)")
    if current is not None and current.first_right < change_month:
        raise PlanError("Delen har redan haft sin första rätt; efter start används paus eller förlängning "
                        "(PR-ITP1-003)")
    if first_right < change_month:
        raise PlanError("Första rätt kan inte ligga före ändringsmånaden")
    if payments is not None and payments < MIN_PAYMENTS:
        raise PlanError(f"Tidsbegränsad plan kräver minst {MIN_PAYMENTS} rättigheter (PR-ITP1-006); N = {payments} avslås")
    return Schedule(first_right, payments)


def pause_plan(current: Schedule, first: date, resume: date) -> Schedule:
    """Paus av en påbörjad hel uttagsdel med bestämd återstart (PR-ITP1-004, -005).

    En ny pausplan ersätter uttryckligen tidigare pauser som ännu inte börjat; redan inledda pauser står kvar.
    """
    if first <= current.first_right:
        raise PlanError("Bara en påbörjad del kan pausas (PR-ITP1-004)")
    if not current.has_right(first) and not current.paused(first):
        raise PlanError("Efter den sista förbrukade rätten finns ingen pågående rätt att pausa (PR-ITP1-004)")
    kept = tuple(p for p in current.pauses if p[0] < first)
    if kept and kept[-1][1] > first:
        raise PlanError("Pausen överlappar en redan inledd paus – ändra återstarten i stället")
    return Schedule(current.first_right, current.payments, (*kept, (first, resume)))


def extend_plan(current: Schedule, new_payments: int | None, change_month: date) -> Schedule:
    """Förlängning av en påbörjad tidsbegränsad del, eller övergång till livsvarig (PR-ITP1-007)."""
    if current.payments is None:
        raise PlanError("En livsvarig del kan inte göras tidsbegränsad (PR-ITP1-007)")
    consumed = current.rights_before(change_month)
    if consumed >= current.payments:
        raise PlanError(f"Alla {current.payments} rättigheter är förbrukade – förlängningen kom för sent (PR-ITP1-007)")
    if new_payments is not None and new_payments <= current.payments:
        raise PlanError("Nytt antal rättigheter ska vara större än det tidigare; förkortning avslås (PR-ITP1-007)")
    return Schedule(current.first_right, new_payments, current.pauses)


# --- belopp och garanti ---------------------------------------------------------------------------


def round_cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, ROUND_HALF_UP)


def ceil_cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, ROUND_CEILING)


def amount_floor(schedule: Schedule, change: str, effective: date, previous_m: Decimal | None,
                 previous_form: str | None) -> Decimal | None:
    """Tidigare bindande golv för livsvarig del (PR-ITP1-009).

    Under de första 60 rättigheterna för oförändrad livsvarig plan behålls minst senaste beslutade
    brutto. Paus och återstart återställer inte golvet; första start och en förlängning från
    tidsbegränsad till livsvarig ger ny nivå (PR-ITP1-007).
    """
    if schedule.form != "lifelong" or previous_m is None or previous_form != "lifelong":
        return None
    if change in ("start", "extend"):
        return None
    if schedule.rights_before(effective) >= FLOOR_RIGHTS:
        return None
    return previous_m


def pension_amount(guarantee: Decimal, capital_amount: Decimal, floor: Decimal | None = None) -> dict:
    """M i ören: max(round_half_up(max(G, B)), ceil_öre(G), golv). Fall 9–11."""
    candidate = round_cents(max(guarantee, capital_amount))
    guarantee_floor = ceil_cents(guarantee)
    m = max(candidate, guarantee_floor, floor or Decimal(0))
    binding = ("floor" if floor is not None and m == floor and floor > max(candidate, guarantee_floor)
               else "guarantee" if m == guarantee_floor and guarantee_floor > candidate
               else "candidate")
    return {"m_sek": m, "candidate_sek": candidate, "guarantee_floor_sek": guarantee_floor,
            "previous_floor_sek": floor, "binding": binding}


def recalculated(guarantee: Decimal, factor_old: Decimal, factor_new: Decimal) -> tuple[Decimal, Decimal]:
    """Värdebevarande omräkning av en garantidel på samma grund: (V_j, G_j_ny). Fall 12."""
    if factor_old <= 0 or factor_new <= 0:
        raise PlanError("Annuitetsfaktorn ska vara positiv")
    value = guarantee * factor_old
    return value, value / factor_new


def split_share_valid(share: Decimal) -> bool:
    """Ny och kvarvarande del minst 10 % av den delade delen (PR-ITP1-024)."""
    return Decimal("0.1") <= share <= Decimal("0.9")


__all__ = [
    "CENT", "FLOOR_RIGHTS", "FORMS", "MIN_PAYMENTS", "PENSION_AGE", "PlanError", "Schedule", "amount_floor",
    "ceil_cents", "deadline_for", "extend_plan", "next_possible_month", "pause_plan", "pension_amount",
    "recalculated", "round_cents", "sixty_six_month", "split_share_valid", "start_plan",
]
