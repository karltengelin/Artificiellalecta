"""Uttagsdelar och pensionsförloppet i tjänstelagret (paket B steg 1, B-047 punkt 2, P1-PENSION-001 §4).

Gemensamma läsningar och kontroller för operationerna som tidigare tolkade `in_payout` på
försäkringen. Premieförloppet läses i `policy_states`; pensionsförloppet per uttagsdel i
`payout_part_states`. Inga operationer här – bara hjälpfunktioner i betrodd kod.

**Agentrollerna:** `agent_forsakring` och `agent_aktuarie` har SELECT på båda tabellerna
(B-048); `agent_compliance` har det inte. En läsning som körs med en roll utan rätten får inte
läsa dem:
`payout_readable` svarar nej när sessionen ansluter med en roll – eller aktören är en agent
vars teams roll – i `utils/agent_roles.py` saknar SELECT på båda tabellerna. Rollen avgör
även för system- och människoaktörer på agentens anslutning (t.ex. harness när mandatet byggs).
Läsningen redovisar då pensionsförloppet som ej läst i stället för att gissa. Rätten styrs
av `ROLE_GRANTS`, utan kodändring här.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, or_, select

from models import PayoutPart, PayoutPartState, PolicyBenefit
from services.contract import Actor
from services.transaction import DB_ROLE_KEY
from utils.agent_roles import ROLE_GRANTS

PAYOUT_TABLES = (PayoutPart.__tablename__, PayoutPartState.__tablename__)
#: Skäl som visas när pensionsförloppet inte läses med agentens roll
NOT_READ_FOR_AGENT = "Uttagsdelarnas pensionsförlopp läses inte med agentens databasroll (B-048)"


@dataclass(frozen=True)
class PartView:
    """En uttagsdels läge vid en dag (eller i dag)."""

    part_number: int
    share_of_origin: Decimal
    state: str | None
    end_reason: str | None
    valid_from: date | None


def _grants_payout(grants) -> bool:
    return grants is not None and set(PAYOUT_TABLES) <= set(grants.select)


def payout_readable(actor: Actor, session=None) -> bool:
    """Får läsningen läsa uttagsdelarna? Nej om sessionens roll eller agentens teamroll saknar rätten."""
    role = session.info.get(DB_ROLE_KEY) if session is not None else None
    if role is not None and not _grants_payout(next((g for g in ROLE_GRANTS.values() if g.role == role), None)):
        return False
    if actor.is_agent:
        return _grants_payout(ROLE_GRANTS.get(actor.team or ""))
    return True


def create_initial_part(session, benefit: PolicyBenefit, *, valid_from: date | None = None,
                        note: str | None = None) -> PayoutPart:
    """Uttagsdel 1 i läget `not_started` från förmånens start (eller `valid_from`). Utan ekonomisk effekt."""
    part = PayoutPart(benefit_id=benefit.id, part_number=1, share_of_origin=Decimal(1))
    session.add(part)
    session.flush()
    session.add(PayoutPartState(
        payout_part_id=part.id, state="not_started", valid_from=valid_from or benefit.start_date,
        note=note or "Uttagsdel 1, ej startad (P1-PENSION-001 §4)",
    ))
    session.flush()
    return part


def parts_by_policy(session, policy_ids, on: date | None = None) -> dict:
    """Uttagsdelarna per försäkring med läget i dag (öppen rad) eller vid dagen `on`. En databasfråga."""
    current = (PayoutPartState.valid_to.is_(None) if on is None
               else and_(PayoutPartState.valid_from <= on,
                         or_(PayoutPartState.valid_to.is_(None), PayoutPartState.valid_to >= on)))
    rows = session.execute(
        select(PolicyBenefit.policy_id, PayoutPart, PayoutPartState)
        .join(PayoutPart, PayoutPart.benefit_id == PolicyBenefit.id)
        .outerjoin(PayoutPartState, and_(PayoutPartState.payout_part_id == PayoutPart.id, current))
        .where(PolicyBenefit.policy_id.in_(list(policy_ids)))
        .order_by(PolicyBenefit.policy_id, PayoutPart.benefit_id, PayoutPart.part_number)
    ).all()
    found: dict = defaultdict(list)
    for policy_id, part, state in rows:
        found[(policy_id, part.id)].append((part, state))
    out: dict = defaultdict(list)
    for (policy_id, _), matches in found.items():
        part = matches[0][0]
        states = [state for _, state in matches if state is not None]
        state = states[0] if len(states) == 1 else None  # inget eller motstridiga lägen: okänt
        out[policy_id].append(PartView(
            part_number=part.part_number, share_of_origin=part.share_of_origin,
            state=state.state if state else None, end_reason=state.end_reason if state else None,
            valid_from=state.valid_from if state else None,
        ))
    return out


def summary_state(parts: list[PartView]) -> str | None:
    """Försäkringens pensionsförlopp i ett ord, för listor och aggregat.

    `in_payout` om någon del betalas ut, annars `paused` om någon är pausad, annars `not_started`
    om någon inte har startat, annars `ended` när alla delar är avslutade. Saknas delar eller
    läge: None.
    """
    states = [p.state for p in parts]
    if not states or None in states:
        return None
    for state in ("in_payout", "paused", "not_started"):
        if state in states:
            return state
    return "ended"


def receiving_parts(session, benefit_ids, month: date, month_end: date) -> dict:
    """Uttagsdelar som kan ta emot premie för månaden: ej startade hela månaden (PR-ITP1-015, -025).

    En del räknas om den har ett `not_started`-läge under månaden och inget startat eller
    avslutat läge som överlappar den. Svarar med delarna per förmån.
    """
    benefit_ids = list(benefit_ids)
    out: dict = defaultdict(list)
    if not benefit_ids:
        return out
    rows = session.execute(
        select(PayoutPart, PayoutPartState)
        .join(PayoutPartState, PayoutPartState.payout_part_id == PayoutPart.id)
        .where(PayoutPart.benefit_id.in_(benefit_ids), PayoutPartState.valid_from <= month_end,
               or_(PayoutPartState.valid_to.is_(None), PayoutPartState.valid_to >= month))
        .order_by(PayoutPart.benefit_id, PayoutPart.part_number)
    ).all()
    overlapping: dict = defaultdict(list)
    for part, state in rows:
        overlapping[part].append(state.state)
    for part, states in overlapping.items():
        if all(s == "not_started" for s in states):
            out[part.benefit_id].append(part)
    return out
