"""FTA-värdering per försäkring: garanterat åtagande, villkorad återbäring och underskott (A6, B-042).

Instruktion: 03_skills/beräkning/fta-vardering.md
Kontrakt: projekt/06_avdelningsfunktioner/VARDERINGSKONTRAKT.md §3–4 och kontrollfallen i §7

Ren beräkning utan databas. För försäkring i vid värderingsdatum t:

    FTA_i = Σ_j G_ij × a_V(t, D_i) + K_i(t)
    VÅ_i  = max(0, C_i − FTA_i)
    U_i   = max(0, FTA_i − C_i)

- `a_V` är annuitetsfaktorn på värderingsgrunden: SIM-V:s dödlighet och spotkurvan med
  avdrag för avkastningsskatt, `v(t, n) = (1 + r_⌈n/12⌉ − s_y)^(−n/12)`
  (`actuarial_annuity.DiscountCurve`). Alla garantidelar i v1 har samma plan D_i
  (referensplanen livsvarigt från 66), så summan av G_ij multipliceras med en faktor.
- `K_i` är kapitalvärdet av driftkostnaderna: 180 kr per år under uppskov och 240 kr under
  utbetalning (SIM-V `expenses`), en tolftedel per månad med samma vikter och diskontering som
  pensionen. Kostnaden räknas upp med indexeringen per år, månadsvis: månad n efter värderingen
  får `(1 + i)^(n/12)`, så nivån 180 kr gäller vid värderingsdatumet.

Beloppen räknas i dubbel precision och lagras med sex decimaler (`AMOUNT`); öresavrundning görs
först i rapporteringen. Med lagrade belopp gäller VÅ_i − U_i = C_i − FTA_i exakt, och därmed
summakontrollen K10 på öret.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from skills.calculation import actuarial_annuity as aa

#: Motorns version. Höjs vid ändrad metod; kodversionen i en körning lägger till källkodens hash.
ENGINE_VERSION = "fta-1.0"
#: Lagringsprecision för belopp (kronor)
AMOUNT = Decimal("0.000001")
#: Tröskeln för oanalyserat i förändringsanalysen (B-042 punkt 1, guardrail 5): 0,5 % av FTA
UNEXPLAINED_THRESHOLD = Decimal("0.005")


@dataclass(frozen=True)
class Expenses:
    deferred_per_year: float
    payout_per_year: float
    indexation: float

    @classmethod
    def none(cls) -> Expenses:
        return cls(0.0, 0.0, 0.0)


@dataclass(frozen=True)
class ValuationModel:
    """Värderingsgrundens beräkningsdelar: dödlighet, kurva med skatteavdrag och driftkostnad."""

    mortality: aa.MortalityBasis
    curve: aa.DiscountCurve
    expenses: Expenses

    @classmethod
    def from_assumptions(cls, valuation: Mapping[str, Any], curve: Mapping[str, Any],
                         tax_reduction: float) -> ValuationModel:
        """Ur SIM-V:s och FI-SIM:s antaganden i antagandebiblioteket och årets s_y."""
        if valuation.get("reference_plan") != "lifelong_from_66" or valuation.get("option_adjustment") != "none":
            raise ValueError("Motorn v1 stöder bara referensplanen livsvarigt från 66 och ingen optionsjustering")
        if valuation["tax"]["method"] != "discount_reduction":
            raise ValueError("Motorn v1 stöder bara skatt genom diskontering med r − s_y")
        e = valuation["expenses"]
        return cls(
            mortality=aa.MortalityBasis.from_assumptions(valuation["mortality"]),
            curve=aa.DiscountCurve.from_assumptions(curve, tax_reduction),
            expenses=Expenses(float(Decimal(str(e["deferred_sek_per_year"]))),
                              float(Decimal(str(e["payout_sek_per_year"]))), float(Decimal(str(e["indexation"])))),
        )


@dataclass(frozen=True)
class PolicyInput:
    """En försäkring ur datautdraget: bara det värderingen behöver."""

    policy_id: str
    birth: date  # modellens födelsedag: rätt månad, dag 1 eller 2 (S-04)
    state: str
    plan_start: date
    guarantee: Decimal  # Σ_j G_ij, kronor per månad
    capital: Decimal  # C_i


@dataclass(frozen=True)
class PolicyValue:
    policy_id: str
    state: str
    birth_year: int
    capital: Decimal
    guarantee: Decimal
    factor: float  # a_V(t, D_i)
    guarantee_value: Decimal  # Σ G × a_V
    expenses: Decimal  # K_i
    fta: Decimal
    surplus: Decimal  # VÅ_i
    deficit: Decimal  # U_i


def _amount(x: float | Decimal) -> Decimal:
    return (x if isinstance(x, Decimal) else Decimal(repr(x))).quantize(AMOUNT)


def split(fta: Decimal, capital: Decimal) -> tuple[Decimal, Decimal]:
    """(VÅ, U) = (max(0, C − FTA), max(0, FTA − C))."""
    return max(Decimal(0), capital - fta), max(Decimal(0), fta - capital)


class _Factors:
    """a_V och K per (födelse, planstart) – samma för alla försäkringar med samma ålder och plan."""

    def __init__(self, model: ValuationModel, valuation: date) -> None:
        self.model, self.valuation = model, valuation
        self.first = aa.first_month_after(valuation)
        self._cache: dict[tuple[date, date], tuple[float, float]] = {}

    def __call__(self, birth: date, start: date) -> tuple[float, float]:
        key = (birth, start)
        if key not in self._cache:
            self._cache[key] = (self.annuity(birth, start), self.expenses(birth, start))
        return self._cache[key]

    def annuity(self, birth: date, start: date) -> float:
        return aa.annuity_factor(self.model.mortality, birth, self.valuation, start, None, curve=self.model.curve)

    def expenses(self, birth: date, start: date) -> float:
        e = self.model.expenses
        if not (e.deferred_per_year or e.payout_per_year):
            return 0.0
        growth = (1 + e.indexation) ** (1 / 12)
        common = dict(curve=self.model.curve, growth=growth)
        deferred = aa.months_between(self.first, start)
        value = 0.0
        if deferred > 0 and e.deferred_per_year:
            value += e.deferred_per_year / 12 * aa.annuity_factor(
                self.model.mortality, birth, self.valuation, self.first, deferred, **common)
        if e.payout_per_year:
            value += e.payout_per_year / 12 * aa.annuity_factor(
                self.model.mortality, birth, self.valuation, start, None, **common)
        return value


def value_policies(model: ValuationModel, valuation: date, policies: Iterable[PolicyInput]) -> list[PolicyValue]:
    """FTA, VÅ och U per försäkring vid ett månadsslut."""
    factors = _Factors(model, valuation)
    out = []
    for p in policies:
        if p.plan_start < factors.first:
            raise ValueError(f"{p.policy_id}: planens start ligger före första månaden efter värderingen")
        a_v, k = factors(p.birth, p.plan_start)
        guarantee_value = _amount(float(p.guarantee) * a_v)
        expenses = _amount(k)
        fta = guarantee_value + expenses
        surplus, deficit = split(fta, p.capital)
        out.append(PolicyValue(policy_id=p.policy_id, state=p.state, birth_year=p.birth.year, capital=p.capital,
                               guarantee=p.guarantee, factor=a_v, guarantee_value=guarantee_value, expenses=expenses,
                               fta=fta, surplus=surplus, deficit=deficit))
    return out


AMOUNT_FIELDS = ("capital", "guarantee", "guarantee_value", "expenses", "fta", "surplus", "deficit")


@dataclass
class Totals:
    policies: int = 0
    capital: Decimal = Decimal(0)
    guarantee: Decimal = Decimal(0)
    guarantee_value: Decimal = Decimal(0)
    expenses: Decimal = Decimal(0)
    fta: Decimal = Decimal(0)
    surplus: Decimal = Decimal(0)
    deficit: Decimal = Decimal(0)

    def add(self, v: PolicyValue) -> None:
        self.policies += 1
        for name in AMOUNT_FIELDS:
            setattr(self, name, getattr(self, name) + getattr(v, name))

    @property
    def balances(self) -> bool:
        """Kontrollfall K10: VÅ − U = ΣC − FTA, exakt med lagrade belopp."""
        return self.surplus - self.deficit == self.capital - self.fta


def totals(values: Iterable[PolicyValue]) -> Totals:
    t = Totals()
    for v in values:
        t.add(v)
    return t


def by_segment(values: Iterable[PolicyValue], cohort_of) -> dict[tuple[str, str], Totals]:
    """Summor per läge × födelsekohort (`cohort_of(födelseår)` ger etiketten)."""
    cells: dict[tuple[str, str], Totals] = defaultdict(Totals)
    for v in values:
        cells[(v.state, cohort_of(v.birth_year))].add(v)
    return dict(sorted(cells.items()))


def results_payload(values: Iterable[PolicyValue], total: Totals) -> dict[str, Any]:
    """Det resultatets kontrollsumma räknas på: alla försäkringar och totalerna (kontrollfall K6)."""
    return {
        "policies": [[v.policy_id, str(v.fta), str(v.expenses), str(v.surplus), str(v.deficit)]
                     for v in sorted(values, key=lambda v: v.policy_id)],
        "totals": {"policies": total.policies, **{name: str(getattr(total, name)) for name in AMOUNT_FIELDS}},
    }


# --- kontrollfall ------------------------------------------------------------------------------

def k1_engine_check(mortality: aa.MortalityBasis, received: date = date(2026, 9, 30),
                    birth: date = date(1986, 9, 2), premium: Decimal = Decimal(1000)) -> Decimal:
    """Kontrollfall K1: en premie på 0 %-kurva utan skatt och kostnader värderas till premien.

    Garantidelen räknas med garantins väg (konstant nettoränta 0 %) och värderas med
    värderingsvägen (kurva 0 %) på samma dödlighet. Ger FTA i kronor med full precision.
    """
    g, _ = aa.guarantee_part(mortality, birth, received, premium)
    model = ValuationModel(mortality, aa.DiscountCurve.flat(0.0), Expenses.none())
    value = value_policies(model, received, [PolicyInput(
        "K1", birth, "premium_paying", aa.reference_start(birth, received), Decimal(repr(g)), Decimal(0))])[0]
    return value.fta


def unexplained_status(unexplained: Decimal, fta: Decimal) -> str:
    """`needs_human` när oanalyserat överstiger tröskeln av FTA (kontrollfall K8), annars `ok`."""
    if fta == 0:
        return "needs_human" if unexplained else "ok"
    return "needs_human" if abs(unexplained) / abs(fta) > UNEXPLAINED_THRESHOLD else "ok"


__all__ = [
    "AMOUNT", "ENGINE_VERSION", "UNEXPLAINED_THRESHOLD", "Expenses", "PolicyInput", "PolicyValue", "Totals",
    "ValuationModel", "by_segment", "k1_engine_check", "results_payload", "split", "totals",
    "unexplained_status", "value_policies",
]
