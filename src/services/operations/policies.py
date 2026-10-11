"""Fribrev vid anställningens slut (Fas 1f T3, PR-ITP1-013, villkor §7).

När ny löpande premie upphör är förmånen premiefri (fribrev). Operationen
registrerar arbetsgivarens avanmälan – anställningens sista dag – och sätter
försäkringen i fribrev från dagen efter, i samma transaktion. Lön under
avslutsmånaden ingår utan dagproportionering (PR-ITP1-013).

Befintlig modell: ett läge per försäkring i `policy_states`. Den kan inte
uttrycka fribrev samtidigt med pågående eller pausad pension (fribrev är
upphörd premie, inte ett pensionsläge – UTTAG_GEMENSAMT), så operationen gäller
bara försäkringar vars pension inte har startat. Den ersätter aldrig
`in_payout`/`payout_paused`.

Blockeras (manuell prövning): uttagsläge i tidslinjen, framtida fribrevsdag
(läsningen tolkar den öppna raden som dagens läge), fler premiebetalande
försäkringar för personen, premie eller löneunderlag för månader efter
slutdagen (slutlön/bonus prövas manuellt), avliden eller pensionerad person,
och fribrev av andra skäl än avslutad anställning (t.ex. 66 år – frivillig
fortsättning enligt PR-ITP1-016 kan inte prövas i modellen).
"""

from __future__ import annotations

from datetime import date
from itertools import pairwise

from pydantic import BaseModel, Field
from sqlalchemy import select

from models import InsuredPerson, Policy, PolicyState, PremiumTransaction, SalaryReport
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, ConflictError, NotFoundError
from services.operations import common

PAYOUT_STATES = ("in_payout", "payout_paused", "terminated")


class PaidUpInput(BaseModel):
    policy_number: str = Field(description="Försäkringsnummer, t.ex. AL-000123")
    employment_end_date: date = Field(
        description="Anställningens sista dag enligt arbetsgivarens avanmälan. Fribrev gäller från dagen efter"
    )


class StatePeriod(BaseModel):
    state: str
    valid_from: date
    valid_to: date | None


class PaidUpResult(BaseModel):
    policy_number: str
    employment_end_date: date
    paid_up_from: date
    closed_period: StatePeriod = Field(description="Premieperioden som stängdes")
    new_period: StatePeriod = Field(description="Fribrevsperioden som öppnades")
    employment_end_registered: bool = Field(description="Sant om anställningens slut registrerades nu")
    person_status_before: str
    person_status_after: str


@operation(
    name="set_policy_paid_up",
    description=(
        "Registrerar anställningens slut (avanmälan) och sätter försäkringen i fribrev från dagen efter "
        "(PR-ITP1-013). Bara premiebetalande försäkring vars pension inte har startat; ingen framtidsdatering."
    ),
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-013"],
    pii=True,
)
def set_policy_paid_up(ctx: OperationContext, data: PaidUpInput) -> PaidUpResult:
    session = ctx.require_session()
    today = common.today()
    end = data.employment_end_date
    paid_up_from = common.next_day(end)

    policy = session.scalar(select(Policy).where(Policy.policy_number == data.policy_number).with_for_update())
    if policy is None:
        raise NotFoundError(f"Ingen försäkring med nummer {data.policy_number}")
    person = session.scalar(
        select(InsuredPerson).where(InsuredPerson.id == policy.insured_person_id).with_for_update()
    )
    if person.status in ("deceased", "retired"):
        raise BlockedError(f"Den försäkrade har status {person.status} – fribrev prövas manuellt")

    states = _states(session, policy.id)
    open_states = [s for s in states if s.valid_to is None]
    if len(open_states) != 1:
        raise BlockedError("Försäkringens lägeshistorik har inget eller flera öppna lägen – manuell utredning")
    current = open_states[0]
    if any(s.state in PAYOUT_STATES for s in states):
        raise BlockedError(
            "Försäkringen har haft uttag eller är avslutad. Fribrev under uttag kräver att premieläget "
            "skiljs från pensionsläget (UTTAG_GEMENSAMT) – stöds inte i nuvarande modell"
        )
    if current.state == "paid_up":
        raise ConflictError(f"Försäkringen är redan fribrev från {current.valid_from}")
    if current.state != "premium_paying":
        raise BlockedError(f"Försäkringens läge är {current.state} – fribrev stöds bara från premiebetalande")

    if paid_up_from > today:
        raise BlockedError(
            f"Fribrev från {paid_up_from} ligger i framtiden. Framtidsdatering stöds inte – läsningen visar den "
            "öppna raden som dagens läge. Registrera avanmälan när anställningen har upphört"
        )
    if end < person.employment_start_date:
        raise BlockedError(f"Slutdagen {end} ligger före anställningens start {person.employment_start_date}")
    if end < current.valid_from:
        raise BlockedError(f"Slutdagen {end} ligger före premieperiodens start {current.valid_from}")
    if person.employment_end_date is not None and person.employment_end_date != end:
        raise ConflictError(
            f"Anställningens slut är redan registrerat som {person.employment_end_date} – en ändring är en rättelse"
        )
    _check_other_policies(session, person.id, policy.id)
    _check_nothing_after(session, person.id, end)

    closed = StatePeriod(state=current.state, valid_from=current.valid_from, valid_to=end)
    current.valid_to = end
    session.flush()  # stäng innan nästa öppnas – max ett öppet läge (partiellt unikt index)
    session.add(
        PolicyState(
            policy_id=policy.id, state="paid_up", valid_from=paid_up_from,
            note=f"Anställningen upphörde {end.isoformat()} (fribrev, PR-ITP1-013)",
        )
    )
    status_before = person.status
    registered = person.employment_end_date is None
    person.employment_end_date = end
    if person.status == "active":
        person.status = "terminated"
    session.flush()
    _validate_timeline(_states(session, policy.id))

    return PaidUpResult(
        policy_number=policy.policy_number,
        employment_end_date=end,
        paid_up_from=paid_up_from,
        closed_period=closed,
        new_period=StatePeriod(state="paid_up", valid_from=paid_up_from, valid_to=None),
        employment_end_registered=registered,
        person_status_before=status_before,
        person_status_after=person.status,
    )


def _states(session, policy_id) -> list[PolicyState]:
    return list(
        session.scalars(
            select(PolicyState).where(PolicyState.policy_id == policy_id)
            .order_by(PolicyState.valid_from).with_for_update()
        )
    )


def _check_other_policies(session, person_id, policy_id) -> None:
    other = session.scalar(
        select(Policy.policy_number)
        .join(PolicyState, PolicyState.policy_id == Policy.id)
        .where(
            Policy.insured_person_id == person_id,
            Policy.id != policy_id,
            PolicyState.valid_to.is_(None),
            PolicyState.state == "premium_paying",
        )
    )
    if other is not None:
        raise BlockedError(
            f"Personen har fler premiebetalande försäkringar ({other}). Avanmälan ska omfatta alla – "
            "stöds inte i denna version"
        )


def _check_nothing_after(session, person_id, end: date) -> None:
    """Premie eller löneunderlag efter slutmånaden tyder på fel slutdag – eller slutlön/bonus att pröva."""
    last_month = common.month_of(end)
    later_premium = session.scalar(
        select(PremiumTransaction.period_month)
        .where(
            PremiumTransaction.benefit_id.in_(common.benefit_ids_of(session, person_id)),
            PremiumTransaction.period_month > last_month,
            PremiumTransaction.transaction_type.in_(("premium", "adjustment")),
            PremiumTransaction.status != "cancelled",
        )
        .order_by(PremiumTransaction.period_month)
    )
    if later_premium is not None:
        raise BlockedError(
            f"Det finns premie för {later_premium:%Y-%m}, efter slutdagen {end}. Kontrollera slutdagen; "
            "slutlön eller bonus efter avslut prövas manuellt (PR-ITP1-013)"
        )
    later_report = session.scalar(
        select(SalaryReport.period_month)
        .where(SalaryReport.insured_person_id == person_id, SalaryReport.period_month > last_month)
        .order_by(SalaryReport.period_month)
    )
    if later_report is not None:
        raise BlockedError(f"Det finns löneunderlag för {later_report:%Y-%m}, efter slutdagen {end}")


def _validate_timeline(states: list[PolicyState]) -> None:
    """Hela tidslinjen efter ändringen: högst ett öppet läge, sist, och inga överlapp."""
    ordered = sorted(states, key=lambda s: s.valid_from)
    open_rows = [s for s in ordered if s.valid_to is None]
    if len(open_rows) > 1 or (open_rows and open_rows[0] is not ordered[-1]):
        raise BlockedError("Lägeshistoriken skulle få fler än ett öppet läge")
    for earlier, later in pairwise(ordered):
        if earlier.valid_to is None or earlier.valid_to >= later.valid_from:
            raise BlockedError(
                f"Lägeshistoriken skulle överlappa: {earlier.state} {earlier.valid_from}–{earlier.valid_to} "
                f"och {later.state} från {later.valid_from}"
            )
