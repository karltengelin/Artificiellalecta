"""Övergången till tre förlopp (paket B steg 1, B-047 punkt 2, P1-PENSION-001 §4).

Flyttar beståndet från modellen med ett läge per försäkring (B-022) till uttagsdelar:

1. Varje ålderspensionsförmån utan uttagsdel får **del 1 i läget `not_started`** från förmånens
   start. Ingen ekonomisk effekt: inga garantidelar, kapitalposter eller premier ändras.
2. Lägena `in_payout` och `payout_paused` i `policy_states` **flyttas till del 1** (som `in_payout`
   och `paused`, med samma datum); delen är `not_started` fram till första uttagsläget.
3. Premieförloppet behåller sina rader. Var premieläget före uttaget `paid_up` öppnas det igen,
   eftersom det bara stängdes för att modellen hade ett läge. Var det `premium_paying` och slutar
   samma dag som den registrerade anställningen, öppnas `paid_up` dagen efter – samma läge som
   `set_policy_paid_up` hade registrerat. Annars lämnas premieförloppet utan öppet läge.
4. Varje flyttat uttag får ett **rekonstruktionsärende** (`payout_reconstruction`) till handläggaren.
   Plan, garantidelar, månadsrätter och utbetalningar konstrueras inte i efterhand.

Mönster som inte går att flytta entydigt – `terminated`, uttagslägen som inte ligger sist eller
med glapp, flera ålderspensionsförmåner på försäkringen – stoppar övergången (`problems`).
Idempotent: förmåner som redan har delar och försäkringar utan gamla uttagslägen rörs inte.

Används av migrationen (`utils/migration_payout_parts.py`, Postgres och Lakebase) och av
demo- och testdatabaserna (`utils/demo_data.py`). I Lakebase finns inga uttagslägen.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import pairwise

from sqlalchemy import select

from models import (
    Case,
    InsuredPerson,
    PayoutPart,
    PayoutPartState,
    Policy,
    PolicyBenefit,
    PolicyState,
)
from models.policy_state import LEGACY_PAYOUT_STATES, POLICY_STATES
from services.payout_parts import create_initial_part

TRANSITION_ACTOR = "system:payout_transition"
CASE_TYPE = "payout_reconstruction"
DESIGN_REF = "P1-PENSION-001 §4"
#: Gamla uttagslägen och deras motsvarighet i uttagsdelens pensionsförlopp
STATE_MAP = {"in_payout": "in_payout", "payout_paused": "paused"}
MISSING = ["planversion", "garantidelar per uttagsdel", "månadsrätter och betalningsskuld", "utbetalningar"]


@dataclass
class MovedPayout:
    """Ett uttag som flyttas från försäkringen till del 1."""

    policy_id: uuid.UUID
    policy_number: str
    person_id: uuid.UUID
    benefit_id: uuid.UUID
    rows: list[tuple[str, date, date | None]]
    part_states: list[tuple[str, date, date | None]]
    premium_course: str
    #: reopen = fribrevet öppnas igen, paid_up = nytt fribrev efter anställningens slut, none = inget öppet läge
    premium_action: str = "none"
    case_number: str | None = None


@dataclass
class TransitionResult:
    benefits: int = 0
    parts_to_create: int = 0
    moved: list[MovedPayout] = field(default_factory=list)
    other_benefit_types: int = 0
    problems: list[str] = field(default_factory=list)
    applied: bool = False

    @property
    def nothing_to_do(self) -> bool:
        return not self.parts_to_create and not self.moved and not self.problems


def _premium_course(states: list[PolicyState], first_payout: PolicyState, person: InsuredPerson):
    """Vad premieförloppet blir när uttagsraderna flyttas: (beskrivning, åtgärd)."""
    before = [s for s in states if s.valid_from < first_payout.valid_from]
    if not before:
        return None, None
    last = before[-1]
    if last.valid_to is None or last.valid_to + timedelta(days=1) != first_payout.valid_from:
        return None, None
    if last.state == "paid_up":
        return f"fribrev från {last.valid_from} fortsätter (öppnat igen)", ("reopen", last)
    end = person.employment_end_date
    if last.state == "premium_paying" and end is not None and end == last.valid_to:
        return (f"fribrev från {end + timedelta(days=1)}, dagen efter registrerat anställningsslut {end}",
                ("paid_up", last))
    return (f"premieförloppet efter {last.valid_to} är okänt och lämnas utan öppet läge", ("none", last))


def plan_transition(session, *, parts_table: bool = True) -> TransitionResult:
    """Vad övergången skulle göra, utan att skriva. `parts_table=False`: tabellerna finns inte än (torrkörning)."""
    result = TransitionResult()
    benefits = session.scalars(select(PolicyBenefit).order_by(PolicyBenefit.policy_id, PolicyBenefit.start_date)).all()
    with_parts = set(session.scalars(select(PayoutPart.benefit_id).distinct())) if parts_table else set()
    retirement = [b for b in benefits if b.benefit_type == "retirement_dc"]
    result.benefits = len(retirement)
    result.other_benefit_types = len(benefits) - len(retirement)
    result.parts_to_create = sum(b.id not in with_parts for b in retirement)

    unexpected = session.scalars(
        select(PolicyState).where(PolicyState.state.not_in((*POLICY_STATES, *LEGACY_PAYOUT_STATES)))
    ).all()
    for row in unexpected:
        result.problems.append(
            f"Försäkring {row.policy_id}: läget {row.state} från {row.valid_from} kan inte flyttas – "
            "avslut sker bara genom slutavräkning eller dödsfall (PB10). Manuell utredning"
        )
    policy_ids = list(dict.fromkeys(session.scalars(
        select(PolicyState.policy_id).where(PolicyState.state.in_(LEGACY_PAYOUT_STATES))
        .order_by(PolicyState.policy_id)
    )))
    for policy_id in policy_ids:
        policy = session.get(Policy, policy_id)
        person = session.get(InsuredPerson, policy.insured_person_id)
        states = sorted(policy.states, key=lambda s: s.valid_from)
        first = next(i for i, s in enumerate(states) if s.state in LEGACY_PAYOUT_STATES)
        tail = states[first:]
        label = policy.policy_number
        if any(s.state not in LEGACY_PAYOUT_STATES for s in tail):
            result.problems.append(f"{label}: uttagslägena ligger inte sist i tidslinjen – manuell utredning")
            continue
        own = [b for b in retirement if b.policy_id == policy_id]
        if len(own) != 1:
            result.problems.append(f"{label}: {len(own)} ålderspensionsförmåner – uttaget kan inte knytas till en del")
            continue
        benefit = own[0]
        if benefit.id in with_parts:
            result.problems.append(f"{label}: förmånen har redan uttagsdelar men försäkringen har gamla uttagslägen")
            continue
        if benefit.start_date >= tail[0].valid_from:
            result.problems.append(f"{label}: uttaget börjar {tail[0].valid_from}, inte efter förmånens start")
            continue
        gaps = [(a, b) for a, b in pairwise(tail)
                if a.valid_to is None or a.valid_to + timedelta(days=1) != b.valid_from]
        if gaps:
            result.problems.append(f"{label}: uttagslägena har glapp eller överlapp – manuell utredning")
            continue
        description, action = _premium_course(states, tail[0], person)
        if action is None:
            result.problems.append(f"{label}: premieförloppet slutar inte dagen före uttaget – manuell utredning")
            continue
        part_states = [("not_started", benefit.start_date, tail[0].valid_from - timedelta(days=1))]
        part_states += [(STATE_MAP[s.state], s.valid_from, s.valid_to) for s in tail]
        result.moved.append(MovedPayout(
            policy_id=policy.id, policy_number=label, person_id=person.id, benefit_id=benefit.id,
            rows=[(s.state, s.valid_from, s.valid_to) for s in tail], part_states=part_states,
            premium_course=description, premium_action=action[0],
        ))
    return result


def apply_transition(session, today: date) -> TransitionResult:
    """Genomför övergången i sessionens transaktion. Stoppar (ValueError) vid hinder, utan att skriva."""
    from services.operations.cases import _next_case_number  # undviker cirkulär import

    result = plan_transition(session)
    if result.problems:
        raise ValueError("Övergången till uttagsdelar stoppas: " + "; ".join(result.problems))
    moved = {m.benefit_id: m for m in result.moved}
    with_parts = set(session.scalars(select(PayoutPart.benefit_id).distinct()))
    for benefit in session.scalars(select(PolicyBenefit).where(PolicyBenefit.benefit_type == "retirement_dc")
                                   .order_by(PolicyBenefit.policy_id, PolicyBenefit.start_date)):
        if benefit.id in with_parts:
            continue
        entry = moved.get(benefit.id)
        if entry is None:
            create_initial_part(session, benefit, note="Uttagsdel 1 vid övergången, ej startad (P1-PENSION-001 §4)")
            continue
        part = PayoutPart(benefit_id=benefit.id, part_number=1)
        session.add(part)
        session.flush()
        for state, valid_from, valid_to in entry.part_states:
            note = ("Uttagsdel 1 vid övergången, ej startad (P1-PENSION-001 §4)" if state == "not_started"
                    else f"Flyttat från försäkringens läge vid övergången ({DESIGN_REF}); rekonstrueras i ärende")
            session.add(PayoutPartState(payout_part_id=part.id, state=state, valid_from=valid_from,
                                        valid_to=valid_to, note=note))
        _move_premium_course(session, entry)
        session.flush()
        entry.case_number = open_reconstruction_case(session, entry, today, _next_case_number(session))
    session.flush()
    result.applied = True
    return result


def _move_premium_course(session, entry: MovedPayout) -> None:
    policy = session.get(Policy, entry.policy_id)
    person = session.get(InsuredPerson, entry.person_id)
    states = sorted(policy.states, key=lambda s: s.valid_from)
    tail = [s for s in states if s.state in LEGACY_PAYOUT_STATES]
    _, (kind, last) = _premium_course(states, tail[0], person)
    for row in tail:
        session.delete(row)
    session.flush()  # bort med det öppna uttagsläget innan ett premieläge öppnas (ett öppet läge)
    if kind == "reopen":
        last.valid_to = None
        last.note = ((last.note + "; ") if last.note else "") + f"öppnat igen vid övergången ({DESIGN_REF})"
    elif kind == "paid_up":
        session.add(PolicyState(
            policy_id=policy.id, state="paid_up", valid_from=last.valid_to + timedelta(days=1),
            note=f"Fribrev från anställningens slut {last.valid_to}, härlett vid övergången ({DESIGN_REF})",
        ))


def open_reconstruction_case(session, entry: MovedPayout, today: date, number: str) -> str:
    """Rekonstruktionsärendet för ett flyttat uttag, skapat av betrodd kod som systemaktör."""
    session.add(Case(
        id=uuid.uuid4(), case_number=number, case_type=CASE_TYPE, status="open",
        insured_person_id=entry.person_id, policy_id=entry.policy_id, channel="system", received_date=today,
        source_reference=f"payout_transition:{entry.policy_number}",
        details={
            "design_ref": DESIGN_REF, "decision": "B-047",
            "payout_part": 1,
            "moved_states": [{"state": s, "valid_from": f.isoformat(), "valid_to": t.isoformat() if t else None}
                             for s, f, t in entry.rows],
            "part_states": [{"state": s, "valid_from": f.isoformat(), "valid_to": t.isoformat() if t else None}
                            for s, f, t in entry.part_states],
            "premium_course": entry.premium_course,
            "missing": MISSING,
            "instruction": (
                "Uttaget fanns som läge på försäkringen utan plan, garantidelar eller månadsrätter. "
                "Rekonstruera beslutad plan och utbetalningshistorik ur underlag; konstruera ingen historik."
            ),
        },
        created_by=TRANSITION_ACTOR,
    ))
    session.flush()
    return number
