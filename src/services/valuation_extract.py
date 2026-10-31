"""Datautdrag för värderingen och rekonstruerat startbestånd S-04 (A5, B-042 val L).

Kontrakt: projekt/06_avdelningsfunktioner/VARDERINGSKONTRAKT.md §5. Utdraget byggs i betrodd
kod ur beståndet och antagandebiblioteket och lämnar inga personuppgifter: försäkringens
interna id, födelsemånad och om personen är född den första (det enda av födelsedagen som
påverkar åldern vid månadens första dag, aktuariell_grund.md §2).

- **Garantidelar:** varje betalmarkerad premie eller positiv justering är en egen del med
  `G_j = P_j / A_g(t_j, livsvarigt från 66)`, värderad vid mottagningsmånadens slut på den
  garantigrund som gäller då: SIM-HIST-2023-01 till och med 2026-10, SIM-G-2026-01 därefter.
- **Pensionskapital:** `C` rullas fram från 2023-01 med `skills.calculation.capital_rollforward`
  och avkastningsserien AVK-SIM i antagandebiblioteket. Premien tillförs vid
  mottagningsmånadens slut. Kapital före 2023 finns inte i beståndet och räknas inte.
- **Ej beräknat:** försäkringar med påbörjat uttag (PR-009) eller negativ premierad (rättelse
  enligt PR-019) listas med orsak och ingår inte i kollektivet.

Kontrollerna i §5.3 körs alltid; ett utdrag med en underkänd kontroll har `approved = False` och
får inte värderas. Utdragets kontrollsumma är SHA-256 av dess kanoniska JSON, så samma bestånd,
grunder och kod ger samma summa (kontrollfall K6).
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from analytics.portfolio_snapshot import birth_date
from models import (
    InsuredPerson,
    Policy,
    PolicyBenefit,
    PolicyState,
    PremiumTransaction,
    ValuationBasis,
)
from services import valuation_bases as vb
from skills.calculation import actuarial_annuity as aa
from skills.calculation.capital_rollforward import Month, RollforwardError, close_month

SOURCE = "reconstructed_s04"
#: Första månaden med premiehistorik i beståndet (omgenererad mockhistorik, PARAMETERREGISTER.md)
FIRST_MONTH = date(2023, 1, 1)
GUARANTEE_FAMILIES = ("SIM-HIST", "SIM-G")
RETURN_FAMILY = "AVK-SIM"
PREMIUM_TYPES = ("premium", "adjustment")
CALCULATED_STATES = ("premium_paying", "paid_up")
NOT_CALCULATED = {
    "in_payout": "Påbörjat uttag: pensionsbelopp och utbetalt kapital enligt PR-009 rekonstrueras inte i S-04",
    "payout_paused": "Pausat uttag: pensionsbelopp och utbetalt kapital enligt PR-009 rekonstrueras inte i S-04",
    "terminated": "Avslutad försäkring med premier: slutavräkningen (PR-027) rekonstrueras inte i S-04",
    "negative": "Negativ premierad: återtag enligt PR-019 rekonstrueras inte i S-04",
}
#: Antal decimaler för garantidelar och faktorer i utdraget (hög precision, avrundas först i rapportering)
PRECISION = Decimal("1e-10")


class ExtractError(ValueError):
    """Utdraget kan inte byggas, t.ex. saknad grund eller avkastning."""


class GuaranteePart(BaseModel):
    premium_id: str = Field(description="Premieradens id: spåret per ursprunglig premie (PR-020)")
    period_month: date
    received_month: date
    premium: Decimal
    basis: str
    factor: Decimal = Field(description="A_g vid mottagningsmånadens slut, referensplanen")
    guarantee: Decimal = Field(description="G_j, kronor per månad")


class Plan(BaseModel):
    kind: Literal["reference_lifelong"] = Field(description="Ej påbörjad: livsvarigt från 66-årsmånaden")
    start: date


class CapitalFlows(BaseModel):
    premiums: Decimal
    returns: Decimal
    fees: Decimal
    taxes: Decimal


class ExtractPolicy(BaseModel):
    policy_id: str
    birth_month: str = Field(description="Födelseår och månad, ÅÅÅÅ-MM")
    born_on_first: bool = Field(description="Född den första i månaden; styr åldern vid månadens första dag")
    state: str
    plan: Plan
    guarantee_parts: list[GuaranteePart]
    capital: Decimal
    flows: CapitalFlows
    source: str = SOURCE


class NotCalculated(BaseModel):
    policy_id: str
    reason: str


class MonthTotals(BaseModel):
    month: date
    rate: Decimal
    opening: Decimal
    returns: Decimal
    fees: Decimal
    taxes: Decimal
    fees_waived: Decimal
    taxes_waived: Decimal
    premiums: Decimal
    closing: Decimal


class QualityCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class ValuationExtract(BaseModel):
    valuation_date: date
    source: str = SOURCE
    bases: dict[str, str] = Field(description="Använda grunder och deras kontrollsummor")
    policies: list[ExtractPolicy]
    not_calculated: list[NotCalculated]
    outside_population: int = Field(description="Försäkringar utan garantidel och kapital vid datumet")
    months: list[MonthTotals]
    checks: list[QualityCheck]
    approved: bool
    checksum: str = ""


def month_end(month: date) -> date:
    return month.replace(day=calendar.monthrange(month.year, month.month)[1])


def _months(first: date, last: date) -> list[date]:
    months, month = [], first
    while month <= last:
        months.append(month)
        month = aa.add_months(month, 1)
    return months


def _adopted(session: Session, family: str) -> list[ValuationBasis]:
    rows = list(session.scalars(select(ValuationBasis).where(
        ValuationBasis.family == family, ValuationBasis.status == "adopted").order_by(ValuationBasis.valid_from)))
    for row in rows:
        try:
            vb.verify_checksum(row)
        except vb.BasisError as exc:
            raise ExtractError(str(exc)) from exc
    return rows


@dataclass
class _Guarantee:
    """Garantigrunderna och deras dödlighet, med faktorerna sparade per födelse och mottagning."""

    rows: list[ValuationBasis]

    def __post_init__(self) -> None:
        self.models = {r.code: aa.basis_from_assumptions(r.assumptions) for r in self.rows}
        self.factors: dict[tuple, float] = {}

    def basis_on(self, day: date) -> ValuationBasis:
        found = [r for r in self.rows if r.valid_from <= day and (r.valid_to is None or r.valid_to >= day)]
        if len(found) != 1:
            raise ExtractError(f"{len(found)} garantigrunder gäller {day} – exakt en krävs")
        return found[0]

    def part(self, born: date, received: date, premium: Decimal) -> tuple[str, float, float]:
        end = month_end(received)
        row = self.basis_on(end)
        key = (row.code, born, end)
        if key not in self.factors:
            mortality, rate = self.models[row.code]
            self.factors[key] = aa.guarantee_part(mortality, born, end, Decimal(1), net_interest_rate=rate)[1]
        factor = self.factors[key]
        return row.code, factor, float(premium) / factor


def _returns(session: Session, valuation_date: date, months: list[date]) -> tuple[ValuationBasis, dict[date, Decimal]]:
    row = vb.in_force(session, RETURN_FAMILY, valuation_date)
    if row is None:
        raise ExtractError(f"Ingen avkastningsserie i {RETURN_FAMILY} gäller {valuation_date}")
    _adopted(session, RETURN_FAMILY)  # prövar kontrollsummorna
    rates = {date.fromisoformat(m["month"]): Decimal(m["rate"]) for m in row.assumptions["months"]}
    missing = [m for m in months if m not in rates]
    if missing:
        raise ExtractError(f"Avkastning saknas för {', '.join(f'{m:%Y-%m}' for m in missing)} i {row.code} "
                           "(PR-021: saknad avkastning blockerar)")
    return row, rates


def _q(x: Decimal) -> Decimal:
    return x.quantize(PRECISION)


def build_extract(session: Session, valuation_date: date) -> ValuationExtract:
    """Bygger utdraget per ett månadsslut med rekonstruerade garantidelar och kapital (S-04)."""
    if valuation_date != month_end(valuation_date):
        raise ExtractError("Värderingsdatumet ska vara ett månadsslut")
    if valuation_date < month_end(FIRST_MONTH):
        raise ExtractError(f"Premiehistoriken börjar {FIRST_MONTH:%Y-%m}")
    months = _months(FIRST_MONTH, valuation_date.replace(day=1))
    guarantee = _Guarantee([r for f in GUARANTEE_FAMILIES for r in _adopted(session, f)])
    return_row, rates = _returns(session, valuation_date, months)

    states = defaultdict(list)
    for policy_id, state in session.execute(select(PolicyState.policy_id, PolicyState.state).where(
            PolicyState.valid_from <= valuation_date,
            (PolicyState.valid_to.is_(None)) | (PolicyState.valid_to >= valuation_date))):
        states[policy_id].append(state)
    policies = session.execute(
        select(Policy.id, InsuredPerson.personal_id_number)
        .join(InsuredPerson, InsuredPerson.id == Policy.insured_person_id)
        .where(Policy.start_date <= valuation_date).order_by(Policy.id)
    ).all()
    paid = and_(PremiumTransaction.status == "paid", PremiumTransaction.transaction_type.in_(PREMIUM_TYPES),
                PremiumTransaction.paid_date <= valuation_date)
    premiums = defaultdict(list)
    for policy_id, tx_id, period, paid_date, amount in session.execute(
            select(Policy.id, PremiumTransaction.id, PremiumTransaction.period_month, PremiumTransaction.paid_date,
                   PremiumTransaction.amount_sek)
            .select_from(PremiumTransaction).join(PolicyBenefit).join(Policy).where(paid)
            .order_by(PremiumTransaction.paid_date, PremiumTransaction.id)):
        premiums[policy_id].append((str(tx_id), period, paid_date.replace(day=1), amount))

    problems: dict[str, list[str]] = defaultdict(list)
    calculated, not_calculated, parts_of, outside = {}, [], {}, 0
    for policy_id, pnr in policies:
        key = str(policy_id)
        rows = premiums.get(policy_id, [])
        found = states.get(policy_id, [])
        born = birth_date(pnr)
        if born is None:
            problems["fullständiga uppgifter"].append(f"{key}: födelsedatum saknas")
            continue
        if len(found) != 1:
            problems["fullständiga uppgifter"].append(f"{key}: {'inget läge' if not found else 'motstridiga lägen'}")
            continue
        state = found[0]
        if any(r[2] < FIRST_MONTH for r in rows):
            problems["premiehistorik"].append(f"{key}: premie mottagen före {FIRST_MONTH:%Y-%m}")
            continue
        if state not in CALCULATED_STATES:
            if rows:
                not_calculated.append(NotCalculated(policy_id=key, reason=NOT_CALCULATED.get(state, state)))
            else:
                outside += 1
            continue
        if any(r[3] < 0 for r in rows):
            not_calculated.append(NotCalculated(policy_id=key, reason=NOT_CALCULATED["negative"]))
            continue
        # Bara födelsemånaden och om dagen är den första påverkar åldern vid månadsförsta
        model_birth = born if born.day == 1 else born.replace(day=2)
        parts = []
        for tx_id, period, received, amount in rows:
            if amount == 0:
                continue
            code, factor, g = guarantee.part(model_birth, received, amount)
            parts.append(GuaranteePart(premium_id=tx_id, period_month=period, received_month=received,
                                       premium=amount, basis=code, factor=_q(Decimal(repr(factor))),
                                       guarantee=_q(Decimal(repr(g)))))
        parts_of[key] = parts
        calculated[key] = (born, model_birth, state)

    try:
        ledger = _roll(months, rates, parts_of)
    except RollforwardError as exc:
        raise ExtractError(str(exc)) from exc
    closing = ledger[-1].lines if ledger else {}

    out = []
    for key, (born, model_birth, state) in calculated.items():
        parts = parts_of[key]
        line_c = closing[key].closing if key in closing else Decimal(0)
        if not parts and line_c == 0:
            outside += 1
            continue
        flows = CapitalFlows(**{name: sum((getattr(m.lines[key], attr) for m in ledger if key in m.lines), Decimal(0))
                                for name, attr in (("premiums", "premiums"), ("returns", "investment_return"),
                                                   ("fees", "fee"), ("taxes", "tax"))})
        start = aa.reference_start(model_birth, valuation_date)
        out.append(ExtractPolicy(policy_id=key, birth_month=f"{born:%Y-%m}", born_on_first=born.day == 1,
                                 state=state, plan=Plan(kind="reference_lifelong", start=start),
                                 guarantee_parts=parts, capital=line_c, flows=flows))

    totals = [MonthTotals(month=m.month, rate=m.rate, opening=m.total("opening"),
                          returns=m.total("investment_return"), fees=m.total("fee"), taxes=m.total("tax"),
                          fees_waived=m.total("fee_waived"), taxes_waived=m.total("tax_waived"),
                          premiums=m.total("premiums"), closing=m.total("closing")) for m in ledger]
    used = {r.code: r.checksum for r in guarantee.rows if any(p.basis == r.code for x in out for p in x.guarantee_parts)}
    used[return_row.code] = return_row.checksum
    problem_count = sum(len(items) for items in problems.values())
    checks = _checks(session, valuation_date, out, not_calculated, totals, problems, guarantee, paid,
                     len(out) + len(not_calculated) + outside + problem_count)
    extract = ValuationExtract(valuation_date=valuation_date, bases=dict(sorted(used.items())), policies=out,
                               not_calculated=not_calculated, outside_population=outside, months=totals,
                               checks=checks, approved=all(c.passed for c in checks))
    extract.checksum = extract_checksum(extract)
    return extract


def _roll(months: list[date], rates: dict[date, Decimal], parts_of: dict[str, list[GuaranteePart]]) -> list[Month]:
    added: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for key, parts in parts_of.items():
        for part in parts:
            added[part.received_month][key] += part.premium
    ledger, openings = [], {}
    for month in months:
        result = close_month(month, rates[month], openings, added.get(month, {}))
        ledger.append(result)
        openings = {k: line.closing for k, line in result.lines.items()}
    return ledger


def _checks(session, valuation_date, out, not_calculated, totals, problems, guarantee, paid, accounted):
    db_policies = session.scalar(select(func.count()).select_from(Policy).where(Policy.start_date <= valuation_date))
    checks = [QualityCheck(
        name="antal försäkringar", passed=accounted == db_policies,
        detail=f"{len(out)} i utdraget, {len(not_calculated)} ej beräknade och {accounted - len(out) - len(not_calculated)} "
               f"utan garanti och kapital eller med fel, mot {db_policies} försäkringar i beståndet")]
    db_count, db_sum = session.execute(select(func.count(), func.coalesce(func.sum(PremiumTransaction.amount_sek), 0))
                                       .select_from(PremiumTransaction).where(paid)).one()
    excluded = {n.policy_id for n in not_calculated}
    in_extract = sum((p.premium for x in out for p in x.guarantee_parts), Decimal(0))
    parts = sum(len(x.guarantee_parts) for x in out)
    excl_count, excl_sum = 0, Decimal(0)
    if excluded:
        for policy_id, amount in session.execute(
                select(Policy.id, PremiumTransaction.amount_sek).select_from(PremiumTransaction)
                .join(PolicyBenefit).join(Policy).where(paid)):
            if str(policy_id) in excluded:
                excl_count, excl_sum = excl_count + 1, excl_sum + amount
    checks.append(QualityCheck(
        name="premiesumma", passed=(parts + excl_count, in_extract + excl_sum) == (db_count, Decimal(db_sum)),
        detail=f"{parts} garantidelar {in_extract} kr och {excl_count} rader {excl_sum} kr ej beräknade, "
               f"mot {db_count} betalmarkerade rader {db_sum} kr i beståndet"))
    checks.append(QualityCheck(
        name="fullständiga uppgifter", passed=not problems.get("fullständiga uppgifter"),
        detail="; ".join(problems.get("fullständiga uppgifter", [])[:5]) or "Alla försäkringar har födelsedag och ett läge"))
    checks.append(QualityCheck(
        name="premiehistorik", passed=not problems.get("premiehistorik"),
        detail="; ".join(problems.get("premiehistorik", [])[:5]) or f"Alla premier mottagna från {FIRST_MONTH:%Y-%m}"))
    negative = [x.policy_id for x in out if x.capital < 0 or any(p.guarantee < 0 for p in x.guarantee_parts)]
    checks.append(QualityCheck(name="inga negativa belopp", passed=not negative,
                               detail=", ".join(negative[:5]) or "Inget negativt C eller G_j"))
    known = {r.code for r in guarantee.rows}
    unknown = sorted({p.basis for x in out for p in x.guarantee_parts} - known)
    checks.append(QualityCheck(name="kända grunder", passed=not unknown,
                               detail=", ".join(unknown) or "Varje garantidel har en antagen grund med kontrollsumma"))
    bad = [t.month for t in totals if t.opening + t.returns - t.fees - t.taxes + t.premiums != t.closing]
    linked = all(a.closing == b.opening for a, b in pairwise(totals))
    final = sum((x.capital for x in out), Decimal(0))
    ok = not bad and linked and (not totals or final == totals[-1].closing)
    checks.append(QualityCheck(
        name="kapitalavstämning", passed=ok,
        detail=f"Månaderna stämmer och ΣC = {final} kr" if ok else f"Avvikelse {', '.join(f'{m:%Y-%m}' for m in bad)}"))
    return checks


def extract_checksum(extract: ValuationExtract) -> str:
    return vb.checksum(extract.model_dump(mode="json", exclude={"checksum"}))
