"""Beståndsöversikt och premieflöden för produktrapporten (A2, B-042).

`get_portfolio_snapshot` och `get_premium_flows` läser individrader i betrodd kod och lämnar
bara aggregat: inga personnummer, namn, födelsedatum eller löner. Celler med 1–9 försäkringar
eller personer döljs, med kompletterande döljning mot totalen (`analytics.portfolio_snapshot`).
Båda läser bara kolumner som rollen `agent_aktuarie` redan har (`utils/agent_roles.py`).
Monterade i podden `bestand`; produktrapporten (`agents/flows/definitions/product_report.py`)
visar talen i avsnitt 2 och 3.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select

from analytics.portfolio_snapshot import MIN_CELL, birth_year, cohort_of, month_starts, suppress_counts, suppress_sets
from models import InsuredPerson, Policy, PolicyBenefit, PolicyState, PremiumTransaction
from services.contract import OperationContext, OperationKind, operation
from services.errors import InvalidInputError
from services.operations import common

#: Första år med premiehistorik i beståndet (genererad historik från 2023-01)
FIRST_YEAR = 2023

STATE_LABELS = {
    "premium_paying": "Premiebetalande",
    "paid_up": "Fribrev",
    "in_payout": "Utbetalning",
    "payout_paused": "Pausad utbetalning",
    "terminated": "Avslutad",
    "unknown": "Läge saknas",
}
IN_FORCE = ("premium_paying", "paid_up", "in_payout", "payout_paused")
TRANSFER_NOTE = "Flytt till eller från andra bolag stöds inte i produkten (försäkringsvillkor v2.0)."
FLOW_DEFINITION = (
    "Betalmarkerade ordinarie premier och premiejusteringar med betaldag i månaden, som i ledningsmåttet. "
    "Avgifter ingår inte. Betalmarkerat är inte bankavstämt."
)


class YearQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    year: int = Field(ge=FIRST_YEAR, description="Kalenderår, från 2023 till innevarande år")


class CountCell(BaseModel):
    key: str
    label: str
    policies: int | None = Field(description="Antal försäkringar; None = dold")
    hidden_reason: str | None = None


class PortfolioSnapshot(BaseModel):
    read_at: datetime
    as_of_date: date = Field(description="Läsdagen: beståndet och lägena gäller denna dag")
    year: int = Field(description="Året som rörelserna avser")
    policies_total: int | None = Field(description="Alla försäkringar oavsett läge; None = dold")
    policies_in_force: int | None = Field(description="Försäkringar som inte är avslutade")
    insured_in_force: int | None = Field(description="Personer med minst en försäkring som inte är avslutad")
    by_state: list[CountCell] = Field(description="Försäkringar per läge vid läsdagen; summan är policies_total")
    by_cohort: list[CountCell] = Field(description="Försäkringar som inte är avslutade, per födelsedecennium; "
                                                   "summan är policies_in_force")
    entered_in_year: int | None = Field(description="Försäkringar med startdag under året, till och med läsdagen")
    paid_up_in_year: int | None = Field(description="Försäkringar som blev fribrev under året, till och med läsdagen")
    min_cell_size: int


class MonthFlow(BaseModel):
    month: date
    paid_sek: Decimal | None = Field(description="Betalmarkerat belopp; None = dolt eller underkänt")
    persons: int | None = Field(description="Personer med betalmarkerad premie; None = dolt eller underkänt")
    state: Literal["available", "suppressed", "failed"]
    hidden_reason: str | None = None


class PremiumFlows(BaseModel):
    read_at: datetime
    as_of_date: date
    year: int
    period_from: date
    period_to: date = Field(description="Exklusivt slut: första dagen efter sista avslutade månaden")
    months: list[MonthFlow] = Field(description="Avslutade månader under året; innevarande månad ingår inte")
    total_paid_sek: Decimal | None
    total_persons: int | None
    total_state: Literal["available", "suppressed", "failed", "no_months"]
    transfers_in_sek: Decimal | None = Field(description="Inflyttat kapital; None = ej tillämpligt")
    transfers_out_sek: Decimal | None = Field(description="Avflyttat kapital; None = ej tillämpligt")
    transfers_note: str
    definition: str
    min_cell_size: int


def _check_year(year: int, today: date) -> None:
    if year > today.year:
        raise InvalidInputError(f"Välj ett år från {FIRST_YEAR} till {today.year}")


def _cells(counts: Counter, keys: list[str]) -> tuple[list[CountCell], int]:
    hidden = suppress_counts({k: counts.get(k, 0) for k in keys})
    cells = [CountCell(key=k, label=STATE_LABELS.get(k, k), policies=None if k in hidden else counts.get(k, 0),
                       hidden_reason=hidden.get(k)) for k in keys]
    return cells, sum(counts.get(k, 0) for k in keys)


def _visible(n: int) -> int | None:
    return n if n == 0 or n >= MIN_CELL else None


@operation(
    name="get_portfolio_snapshot",
    description="Läser beståndet som aggregat: försäkringar per läge och födelsedecennium samt årets nya och "
                "fribrev, med småcellsskydd. Inga personuppgifter.",
    kind=OperationKind.READ,
    pii=False,
)
def get_portfolio_snapshot(ctx: OperationContext, data: YearQuery) -> PortfolioSnapshot:
    today = common.today()
    _check_year(data.year, today)
    session = ctx.require_session()
    year_from, year_to = date(data.year, 1, 1), min(date(data.year, 12, 31), today)
    current = select(PolicyState.policy_id, PolicyState.state).where(
        PolicyState.valid_from <= today, or_(PolicyState.valid_to.is_(None), PolicyState.valid_to >= today),
    ).subquery()
    rows = session.execute(
        select(Policy.id, Policy.insured_person_id, Policy.start_date, current.c.state,
               InsuredPerson.personal_id_number)
        .join(InsuredPerson, InsuredPerson.id == Policy.insured_person_id)
        .outerjoin(current, current.c.policy_id == Policy.id)
    ).all()
    paid_up = set(session.scalars(select(PolicyState.policy_id).where(
        PolicyState.state == "paid_up", PolicyState.valid_from >= year_from, PolicyState.valid_from <= year_to)))

    states, cohorts, insured = Counter(), Counter(), set()
    entered = 0
    for policy_id, person_id, start, state, pnr in rows:
        state = state or "unknown"
        states[state] += 1
        if state in IN_FORCE:
            cohorts[cohort_of(birth_year(pnr))] += 1
            insured.add(person_id)
        entered += year_from <= start <= year_to
    state_keys = [*IN_FORCE, "terminated"] + (["unknown"] if states.get("unknown") else [])
    by_state, total = _cells(states, state_keys)
    by_cohort, in_force = _cells(cohorts, sorted(cohorts))
    return PortfolioSnapshot(
        read_at=datetime.now(UTC), as_of_date=today, year=data.year,
        policies_total=_visible(total), policies_in_force=_visible(in_force), insured_in_force=_visible(len(insured)),
        by_state=by_state, by_cohort=by_cohort,
        entered_in_year=_visible(entered), paid_up_in_year=_visible(len(paid_up)),
        min_cell_size=MIN_CELL,
    )


@operation(
    name="get_premium_flows",
    description="Läser betalmarkerade premier per avslutad månad under ett år, med antal personer, årstotal och "
                "småcellsskydd. Inga personuppgifter.",
    kind=OperationKind.READ,
    pii=False,
)
def get_premium_flows(ctx: OperationContext, data: YearQuery) -> PremiumFlows:
    today = common.today()
    _check_year(data.year, today)
    this_month = today.replace(day=1)
    year_from = date(data.year, 1, 1)
    last = min(date(data.year, 12, 1), date(this_month.year - (this_month.month == 1), (this_month.month - 2) % 12 + 1, 1))
    months = month_starts(data.year, last) if last >= year_from else []
    period_to = date(last.year + (last.month == 12), last.month % 12 + 1, 1) if months else year_from
    base = dict(read_at=datetime.now(UTC), as_of_date=today, year=data.year, period_from=year_from,
                period_to=period_to, transfers_in_sek=None, transfers_out_sek=None, transfers_note=TRANSFER_NOTE,
                definition=FLOW_DEFINITION, min_cell_size=MIN_CELL)
    if not months:
        return PremiumFlows(**base, months=[], total_paid_sek=None, total_persons=None, total_state="no_months")

    session = ctx.require_session()
    paid = and_(PremiumTransaction.status == "paid", PremiumTransaction.transaction_type.in_(("premium", "adjustment")))
    rows = session.execute(
        select(Policy.insured_person_id, PremiumTransaction.paid_date, PremiumTransaction.amount_sek)
        .select_from(PremiumTransaction).join(PolicyBenefit).join(Policy)
        .where(paid, PremiumTransaction.paid_date >= year_from, PremiumTransaction.paid_date < period_to)
    ).all()
    invalid = session.scalar(select(PremiumTransaction.benefit_id).where(
        paid, or_(PremiumTransaction.paid_date.is_(None), PremiumTransaction.paid_date > today)).limit(1))
    if invalid is not None:
        failed = [MonthFlow(month=m, paid_sek=None, persons=None, state="failed") for m in months]
        return PremiumFlows(**base, months=failed, total_paid_sek=None, total_persons=None, total_state="failed")

    amounts: dict[date, Decimal] = defaultdict(Decimal)
    persons: dict[date, set] = {m: set() for m in months}
    for person_id, paid_date, amount in rows:
        month = paid_date.replace(day=1)
        amounts[month] += amount
        persons[month].add(person_id)
    hidden = suppress_sets(persons)
    flows = [
        MonthFlow(month=m, paid_sek=None if m in hidden else amounts[m].quantize(Decimal("0.01")),
                  persons=None if m in hidden else len(persons[m]),
                  state="suppressed" if m in hidden else "available", hidden_reason=hidden.get(m))
        for m in months
    ]
    everyone = set().union(*persons.values())
    small = 0 < len(everyone) < MIN_CELL
    return PremiumFlows(
        **base, months=flows,
        total_paid_sek=None if small else sum(amounts.values(), Decimal(0)).quantize(Decimal("0.01")),
        total_persons=None if small else len(everyone),
        total_state="suppressed" if small else "available",
    )
