"""IBB-känslighet på lagrade löneunderlag, utan ändring av beståndet.

En trappa per person/arbetsgivare/månad (PR-001/015). Saknat eller
motstridigt underlag utesluts uttryckligt. Belopp som redan bokförts
hålls skilda från omberäknad bas och hypotetiskt scenario.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Mapping

from skills.calculation.calculate_itp1_premium import calculate_itp1_premium

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class PremiumObservation:
    transaction_id: str
    person_ref: str
    employer_ref: str
    policy_ref: str
    benefit_ref: str
    month: date
    salary: Decimal | None
    recorded_amount: Decimal
    birth_date: date | None
    status: str = "paid"


@dataclass(frozen=True)
class Segment:
    key: str
    groups: int
    affected: int
    baseline: Decimal
    scenario: Decimal

    @property
    def difference(self) -> Decimal:
        return self.scenario - self.baseline


@dataclass(frozen=True)
class ImpactReport:
    month: date
    baseline_ibb: Decimal
    scenario_ibb: Decimal
    source_rows: int
    source_people: int
    source_policies: int
    compared_groups: int
    compared_people: int
    affected_people: int
    recorded_by_status: Mapping[str, Decimal]
    comparable_recorded: Decimal
    baseline: Decimal
    scenario: Decimal
    quality: Mapping[str, int]
    by_employer: tuple[Segment, ...]
    by_age: tuple[Segment, ...]

    @property
    def difference(self) -> Decimal:
        return self.scenario - self.baseline

    @property
    def reconciliation_difference(self) -> Decimal:
        return self.comparable_recorded - self.baseline


def _age_band(birth: date, month: date) -> str:
    age = month.year - birth.year - ((month.month, month.day) < (birth.month, birth.day))
    if age < 25:
        return "under 25"
    if age >= 66:
        return "66+"
    start = max(25, (age // 10) * 10)
    return f"{start}–{min(65, (age // 10) * 10 + 9)}"


def compare_ibb(
    observations: Iterable[PremiumObservation], *, month: date,
    baseline_ibb: Decimal, scenario_ibb: Decimal,
) -> ImpactReport:
    """Jämför en månad med oförändrad lön och ålder. Ingen årsprognos.

    Arbetsgivarreferensen måste ha en dokumenterad källa/assumption hos
    anroparen. Flera försäkringar får dela samma fulla löneunderlag men
    samma förmån får inte ha två ordinarie premier i samma månad.
    """
    if month.day != 1:
        raise ValueError("Analysmånad ska vara månadens första dag")
    for value in (baseline_ibb, scenario_ibb):
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise ValueError("IBB ska vara positiv, ändlig Decimal")
    rows = [r for r in observations if r.month == month]
    quality: Counter[str] = Counter()
    amounts: dict[str, Decimal] = defaultdict(lambda: ZERO)
    grouped: dict[tuple[str, str], list[PremiumObservation]] = defaultdict(list)
    for row in rows:
        if row.status not in {"paid", "invoiced", "pending", "cancelled"}:
            raise ValueError("Okänd transaktionsstatus")
        if not row.recorded_amount.is_finite():
            raise ValueError("Lagrade belopp måste vara ändliga")
        amounts[row.status] += row.recorded_amount
        if row.status == "cancelled":
            quality["cancelled_rows"] += 1
            continue
        grouped[(row.person_ref, row.employer_ref)].append(row)
    ids = Counter(r.transaction_id for r in rows)
    employer_data: dict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)
    age_data: dict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)
    included: set[str] = set()
    affected: set[str] = set()
    baseline = scenario = recorded = ZERO
    count = 0
    for (person, employer), group in sorted(grouped.items()):
        reason = None
        if not person or not employer or any(not r.transaction_id or not r.policy_ref or not r.benefit_ref for r in group):
            reason = "missing_identity_groups"
        elif any(ids[r.transaction_id] != 1 for r in group) or len({r.benefit_ref for r in group}) != len(group):
            reason = "duplicate_groups"
        elif any(r.salary is None for r in group):
            reason = "missing_salary_groups"
        elif any(not r.salary.is_finite() or r.salary < 0 for r in group):
            reason = "invalid_salary_groups"
        elif len({r.salary for r in group}) != 1:
            reason = "conflicting_salary_groups"
        elif any(r.birth_date is None for r in group):
            reason = "missing_birth_groups"
        elif len({r.birth_date for r in group}) != 1:
            reason = "conflicting_birth_groups"
        if reason:
            quality[reason] += 1
            continue
        row = group[0]
        args = {"birth_date": row.birth_date, "period_month": month}
        old = calculate_itp1_premium(row.salary, baseline_ibb, **args).total_premium_sek
        new = calculate_itp1_premium(row.salary, scenario_ibb, **args).total_premium_sek
        if any(r.recorded_amount < 0 for r in group):
            quality["negative_premium_groups"] += 1
            continue
        recorded += sum((r.recorded_amount for r in group), ZERO)
        baseline += old
        scenario += new
        count += 1
        included.add(person)
        if old != new:
            affected.add(person)
        employer_data[employer].append((old, new))
        age_data[_age_band(row.birth_date, month)].append((old, new))

    def segments(data: dict) -> tuple[Segment, ...]:
        return tuple(Segment(key, len(values), sum(a != b for a, b in values),
                             sum((a for a, _ in values), ZERO),
                             sum((b for _, b in values), ZERO))
                     for key, values in sorted(data.items()))

    return ImpactReport(
        month, baseline_ibb, scenario_ibb, len(rows),
        len({r.person_ref for r in rows}), len({r.policy_ref for r in rows}),
        count, len(included), len(affected), dict(sorted(amounts.items())),
        recorded, baseline, scenario, dict(sorted(quality.items())),
        segments(employer_data), segments(age_data),
    )


def render_markdown(report: ImpactReport, *, source: str, attribution: str) -> str:
    """Aggregat utan personnr, namn, födelsedatum eller transaktions-ID."""
    def money(value: Decimal) -> str:
        return f"{value:,.2f}".replace(",", " ").replace(".", ",")
    lines = ["# Premieanalys – hypotetiskt IBB-scenario", "",
             f"- Underlag: {source}", f"- Arbetsgivarkoppling: {attribution}",
             f"- Analysmånad: {report.month:%Y-%m}",
             f"- IBB i bas: {money(report.baseline_ibb)} kr; scenario: {money(report.scenario_ibb)} kr.",
             "", "Lön och ålder hålls oförändrade. Scenariot ändrar inga produktregler,",
             "premier eller rättigheter. Beloppen är månadspremier, inte årsprognos,",
             "pensionskapital, garanti eller faktisk inbetalning.", "",
             "## Underlag och jämförbarhet", "",
             f"Urvalet innehåller {report.source_rows} ordinarie premierader, "
             f"{report.source_people} personer och {report.source_policies} försäkringar.",
             "Detta är personer/försäkringar med premierader i urvalet, inte hela beståndet.",
             f"Jämförda löneunderlag: {report.compared_groups}; personer: {report.compared_people}; "
             f"berörda personer: {report.affected_people}.", "",
             "| Belopp för jämförbara underlag | SEK |", "|---|---:|",
             f"| Lagrad ordinarie premie, exklusive makulerat | {money(report.comparable_recorded)} |",
             f"| Omberäknad bas | {money(report.baseline)} |",
             f"| Scenario | {money(report.scenario)} |",
             f"| Scenario minus omberäknad bas | {money(report.difference)} |",
             f"| Lagrad premie minus omberäknad bas | {money(report.reconciliation_difference)} |", "",
             "Lagrad premie och omberäknad bas kan skilja sig. Skillnaden är en",
             "avstämningssignal som behöver utredas, inte ett automatiskt rättelsebeslut.", "",
             "## Lagrade belopp i hela urvalet", "",
             "| Status | SEK |", "|---|---:|"]
    lines.extend(f"| {key} | {money(value)} |" for key, value in report.recorded_by_status.items())
    lines += ["", "Endast paid är markerat som betalt. Rättelser, avgifter och andra",
              "transaktionstyper ingår inte; detta är inte en full kapitalavstämning.", "",
              "## Datakvalitet", ""]
    if report.quality:
        lines += ["| Kontroll | Antal |", "|---|---:|"]
        lines.extend(f"| {key} | {value} |" for key, value in report.quality.items())
    else:
        lines.append("Inga uteslutningar enligt analysens kontroller. Detta verifierar inte ITP-tillhörighet.")
    lines += ["", "Gruppfel räknas en gång per person/arbetsgivare/månad med första",
              "blockerande skäl. cancelled_rows avser rader som inte jämförs."]
    if report.compared_groups == 0:
        lines += ["", "**Inga jämförbara underlag. Nollbeloppen visar inte att IBB-ändringen saknar effekt.**"]
    for title, segments in (("Arbetsgivarsegment", report.by_employer), ("Ålder vid månadens början", report.by_age)):
        lines += ["", f"## {title}", "", "| Segment | Underlag | Berörda underlag | Bas SEK | Scenario SEK | Skillnad SEK |",
                  "|---|---:|---:|---:|---:|---:|"]
        # Stabilt alias för arbetsgivare: inga råa kund-/arbetsgivar-ID i rapporten.
        for index, segment in enumerate(segments, 1):
            label = f"Arbetsgivare {index}" if title == "Arbetsgivarsegment" else segment.key
            lines.append(f"| {label} | {segment.groups} | {segment.affected} | {money(segment.baseline)} | "
                         f"{money(segment.scenario)} | {money(segment.difference)} |")
    lines += ["", "Rapporten är ett internt analysunderlag. Aggregat med små grupper är",
              "inte automatiskt anonymiserade; agent-/kundexponering kräver separat åtkomstbedömning."]
    return "\n".join(lines) + "\n"
