"""Begäran, uttagsplan, beslut, belopp och delning i tjänstelagret (paket B steg 4, B-047 punkt 3, Karls val V1–V11).

Designstoppet P1-PENSION-001 §5 (PB3, PB6) med Karls val V1–V11 2026-11-21. Den rena beräkningen
(kalender, M-formeln, golv och omräkning) ligger i `skills.calculation.payout_plan`; här läses
journal, grunder och register.

**Begäran (§5.1, V8).** `register_request` sparar varje begäran med mottagningsdag, kanal, aktör och
innehåll och prövar fristen: sista kalenderdagen i månaden före ändringsmånaden. Utfallen är
`in_time`, `late` (med förslag på nästa möjliga månad), `incomplete` (med de konkreta uppgifterna
som saknas), `stopped` (avliden, okänd identitet, saknad behörighet) och `blocked` (uttag före 66,
PB1). Varje begäran får ett ärende `payout_request`. En bekräftelse av ett förslag är en ny begäran
som pekar på den sena.

**Förhandsberäkning och beslut (§5.2–5.3, V2, V7, V10).** `evaluate_request` räknar ny plan, G, B och
M på värderingen vid månadsslutet före ändringsmånaden, med granskningssumma. Ett beslut binder
summan och sparar en ny planversion; det kräver att det månadsslutet är täckt av journalen (ingående
läge eller stängd månad) och att ändringsmånaden inte är stängd. Utanför det fönstret är beräkningen
vägledande (`bindable = false`). Beslutet ändrar ingenting i journalen: ändringsmånadens stängning
genomför planen i steg 1 – omräkningen av garantidelarna (`content.guarantees`) och, för delning,
kapitalet och garantin.

**Delning (PR-ITP1-024, V9).** Bara en ej startad del; ny och kvarvarande del minst 10 %, högst tre
delar. Kapitalet delas i ören på spåren och garantidelarna proportionellt, utan ny värdering.

**Utan steg 4:s migration** (`plans_present` nej) finns inga planer: läsningarna svarar tomt och
skrivningarna blockeras med hänvisning till migrationen.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from analytics.portfolio_snapshot import birth_date
from models import (
    Case,
    Employer,
    InsuredPerson,
    PayoutPart,
    PayoutPartState,
    PayoutPlan,
    PayoutRequest,
    PayoutSplit,
    Policy,
    PolicyBenefit,
)
from models.payout_part import MAX_PARTS
from services import capital_ledger as cl
from services import valuation_bases as vb
from services.valuation_extract import (
    GUARANTEE_FAMILIES,
    PRECISION,
    ExtractError,
    _adopted,
    _Guarantee,
    month_end,
)
from skills.calculation import actuarial_annuity as aa
from skills.calculation import payout_plan as pp
from skills.calculation.capital_rollforward import allocate_cents
from utils.bank_calendar import next_bank_day

METHOD = "payout-plan-1"
PLAN_TABLES = (PayoutRequest.__tablename__, PayoutPlan.__tablename__, PayoutSplit.__tablename__)
PAYOUT_FAMILY = "SIM-B"
PRODUCT = "ITP1"
AGREEMENT = "ITP"
CENT = Decimal("0.01")
RULES = ["PR-ITP1-003", "PR-ITP1-004", "PR-ITP1-005", "PR-ITP1-006", "PR-ITP1-007", "PR-ITP1-008",
         "PR-ITP1-009", "PR-ITP1-024", "PR-ITP1-025", "UTTAG_GEMENSAMT"]
#: Vad en begäran ska innehålla per slag (V8: ofullständig begäran ger komplettering, ingen tyst plan)
REQUIRED = {"start": ("first_right", "form"), "pause": ("first", "resume"), "extend": ("month", "form"),
            "split": ("month", "share", "premium_receiver")}
#: Vem som registrerar ärenden som månadsstängningen upptäcker
REVIEW_REASONS = {"standard_start_unverified": "Standardstart vid 66 utan verifierat underlag (PR-ITP1-025)",
                  "passed_66_without_plan": "66 år passerat utan registrerat val – plan efter kundens bekräftelse"}


class PlanServiceError(ValueError):
    """Begäran, planen eller delningen kan inte registreras, räknas eller beslutas."""


def plans_present(session: Session) -> bool:
    """Är steg 4:s migration körd (tabellerna för begäran, planer och delning)?"""
    names = set(inspect(session.connection()).get_table_names())
    return set(PLAN_TABLES) <= names


def _require(session: Session) -> None:
    if not plans_present(session):
        raise PlanServiceError("Uttagsplanerna är inte införda i vald databas – migrate_payout_plans.py först")


def _q(value) -> Decimal:
    return Decimal(repr(value) if isinstance(value, float) else value).quantize(PRECISION)


def _plain(value):
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (uuid.UUID, Decimal, date)):
        return str(value) if not isinstance(value, date) else value.isoformat()
    return value


# --- ägaren och delen -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Owner:
    """Delen med förmån, försäkring och ägare. Inga personuppgifter utöver födelsedagen lämnar tjänsten."""

    part: PayoutPart
    benefit_id: uuid.UUID
    policy_id: uuid.UUID
    policy_number: str
    person_id: uuid.UUID
    birth: date | None
    status: str
    product_code: str
    agreement: str

    @property
    def model_birth(self) -> date:
        return self.birth if self.birth.day == 1 else self.birth.replace(day=2)

    def verification(self, session: Session) -> list[str]:
        """Registerkontrollen för standardstart (V5): levande, födelsedag, ITP1, ITP-avtal, ingen rekonstruktion."""
        problems = []
        if self.status == "deceased":
            problems.append("ägaren är registrerad som avliden")
        if self.birth is None:
            problems.append("födelsedagen kan inte läsas")
        if self.product_code != PRODUCT:
            problems.append(f"produkten är {self.product_code}, inte {PRODUCT}")
        if self.agreement != AGREEMENT:
            problems.append(f"arbetsgivarens avtal är {self.agreement}, inte {AGREEMENT}")
        if session.scalar(select(Case.id).where(Case.insured_person_id == self.person_id,
                                                Case.case_type == "payout_reconstruction",
                                                Case.status != "closed").limit(1)):
            problems.append("ett öppet rekonstruktionsärende för uttag finns")
        return problems


def owners(session: Session, part_ids) -> dict[uuid.UUID, Owner]:
    part_ids = list(part_ids)
    out = {}
    for start in range(0, len(part_ids), 5000):
        for part, benefit, policy, person, agreement in session.execute(
                select(PayoutPart, PolicyBenefit.id, Policy, InsuredPerson, Employer.collective_agreement)
                .join(PolicyBenefit, PolicyBenefit.id == PayoutPart.benefit_id)
                .join(Policy, Policy.id == PolicyBenefit.policy_id)
                .join(InsuredPerson, InsuredPerson.id == Policy.insured_person_id)
                .join(Employer, Employer.id == InsuredPerson.employer_id)
                .where(PayoutPart.id.in_(part_ids[start:start + 5000]))):
            out[part.id] = Owner(part, benefit, policy.id, policy.policy_number, person.id,
                                 birth_date(person.personal_id_number), person.status, policy.product_code, agreement)
    return out


def find_part(session: Session, policy_number: str, part_number: int) -> Owner:
    part_id = session.scalar(select(PayoutPart.id).join(PolicyBenefit, PolicyBenefit.id == PayoutPart.benefit_id)
                             .join(Policy, Policy.id == PolicyBenefit.policy_id)
                             .where(Policy.policy_number == policy_number, PayoutPart.part_number == part_number))
    if part_id is None:
        raise PlanServiceError(f"Försäkringen {policy_number} har ingen uttagsdel {part_number}")
    return owners(session, [part_id])[part_id]


def part_state(session: Session, part_id: uuid.UUID, month: date) -> str | None:
    """Delens läge under månaden: `not_started` bara om den är ej startad hela månaden."""
    end = month_end(month)
    states = set(session.scalars(select(PayoutPartState.state).where(
        PayoutPartState.payout_part_id == part_id, PayoutPartState.valid_from <= end,
        (PayoutPartState.valid_to.is_(None)) | (PayoutPartState.valid_to >= month))))
    if not states:
        return None
    return "not_started" if states == {"not_started"} else min(states - {"not_started"})


# --- planer ---------------------------------------------------------------------------------------


def latest_plan(session: Session, part_id: uuid.UUID) -> PayoutPlan | None:
    if not plans_present(session):
        return None
    return session.scalar(select(PayoutPlan).where(PayoutPlan.payout_part_id == part_id)
                          .order_by(PayoutPlan.version.desc()).limit(1))


def plans_in_force(session: Session, part_ids, month: date) -> dict[uuid.UUID, PayoutPlan]:
    """Planversionen som gäller månaden per del: högsta version med ändringsmånad senast `month`."""
    part_ids = list(part_ids)
    if not part_ids or not plans_present(session):
        return {}
    out: dict[uuid.UUID, PayoutPlan] = {}
    for start in range(0, len(part_ids), 5000):
        for plan in session.scalars(select(PayoutPlan).where(PayoutPlan.payout_part_id.in_(part_ids[start:start + 5000]),
                                                             PayoutPlan.effective_month <= month)
                                    .order_by(PayoutPlan.payout_part_id, PayoutPlan.version)):
            out[plan.payout_part_id] = plan
    return out


def schedule_of(plan: PayoutPlan) -> pp.Schedule:
    return pp.Schedule.from_plain(plan.content["schedule"])


def planned_parts(session: Session, part_ids) -> set[uuid.UUID]:
    """Delar som har någon beslutad planversion (även framtida)."""
    part_ids = list(part_ids)
    if not part_ids or not plans_present(session):
        return set()
    return set(session.scalars(select(PayoutPlan.payout_part_id).where(PayoutPlan.payout_part_id.in_(part_ids))))


# --- värdering ------------------------------------------------------------------------------------


@dataclass
class Bases:
    """Garantigrunderna per kod och utbetalningsgrunden som gäller ändringsmånaden."""

    guarantee: _Guarantee
    payout_code: str
    payout_checksum: str
    payout_model: tuple

    @classmethod
    def load(cls, session: Session, month: date) -> Bases:
        try:
            guarantee = _Guarantee([r for f in GUARANTEE_FAMILIES for r in _adopted(session, f)])
        except ExtractError as exc:
            raise PlanServiceError(f"Garantigrunderna kan inte läsas: {exc}") from exc
        payout = vb.in_force(session, PAYOUT_FAMILY, month)
        if payout is None:
            raise PlanServiceError(f"Ingen antagen utbetalningsgrund i {PAYOUT_FAMILY} gäller {month:%Y-%m}")
        vb.verify_checksum(payout)
        return cls(guarantee, payout.code, payout.checksum, aa.basis_from_assumptions(payout.assumptions))


def factor(model: tuple, birth: date, valuation: date, schedule: pp.Schedule) -> Decimal:
    """A(t, D) för planens återstående rätt efter värderingen, i utdragets precision."""
    mortality, rate = model
    args = schedule.factor_arguments(valuation)
    return _q(aa.annuity_factor(mortality, birth, valuation, args["start"], args["payments"],
                                paused=args["paused"], net_interest_rate=rate))


def guarantee_schedule(row, plans: dict) -> pp.Schedule:
    """Planen en garantidel är räknad på: referensplanen eller den beslutade planversionen."""
    if row.plan_kind == "plan":
        return schedule_of(plans[row.plan_id])
    return pp.Schedule(row.plan_start, None)


def covered(session: Session, period_end: date) -> bool:
    """Är månadsslutet bokat i journalen (ingående läge eller stängd månad)?"""
    opening = cl.opening_batch(session)
    return opening is not None and (period_end == opening.period_end or period_end in cl.closed_month_ends(session))


def valuation_point(session: Session, effective: date) -> tuple[date, bool, str | None]:
    """(värderingsdag, bindande, skäl om vägledande) för en ändring från månaden `effective` (V2)."""
    wanted = month_end(aa.add_months(effective, -1))
    if covered(session, wanted) and month_end(effective) not in cl.closed_month_ends(session):
        return wanted, True, None
    opening = cl.opening_batch(session)
    if opening is None:
        raise PlanServiceError("Kapitaljournalen har inget ingående läge – övergången från S-04 görs först")
    if month_end(effective) in cl.closed_month_ends(session):
        raise PlanServiceError(f"{effective:%Y-%m} är redan stängd – ändringen kan gälla tidigast nästa öppna månad")
    known = [opening.period_end, *cl.closed_month_ends(session)]
    used = max(d for d in known if d <= wanted) if any(d <= wanted for d in known) else opening.period_end
    return used, False, (f"Vägledande: {wanted} är inte bokat i journalen; beräknat på {used}. Beslut kan fattas "
                         f"när {wanted:%Y-%m} är stängd och {effective:%Y-%m} är öppen")


def _part_capital(session: Session, part_id: uuid.UUID, on: date) -> list[cl.Track]:
    return [t for t in cl.tracks(session, on) if t.payout_part_id == part_id]


def _part_guarantees(session: Session, part_id: uuid.UUID, on: date) -> list:
    return [g for g in cl.guarantee_parts(session, on) if g.payout_part_id == part_id]


def _plans_by_id(session: Session, ids) -> dict:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {p.id: p for p in session.scalars(select(PayoutPlan).where(PayoutPlan.id.in_(ids)))}


def evaluate(session: Session, owner: Owner, schedule: pp.Schedule, change: str, effective: date, *,
             origin: str, request_id: uuid.UUID | None, bases: Bases | None = None,
             valuation: date | None = None, bindable: bool = True, note: str | None = None) -> dict:
    """Förhandsberäkningen av en planversion: omräknade garantidelar, G, B, M och kalender (§5.3)."""
    if owner.birth is None:
        raise PlanServiceError("Ägarens födelsedag kan inte läsas")
    if valuation is None:
        valuation, bindable, note = valuation_point(session, effective)
    bases = bases or Bases.load(session, effective)
    birth = owner.model_birth
    previous = latest_plan(session, owner.part.id)
    rows = _part_guarantees(session, owner.part.id, valuation)
    plans = _plans_by_id(session, [getattr(r, "plan_id", None) for r in rows if r.plan_kind == "plan"])
    guarantees, g_total = [], Decimal(0)
    for row in rows:
        model = bases.guarantee.models[row.basis_code]
        old = factor(model, birth, valuation, guarantee_schedule(row, plans))
        new = factor(model, birth, valuation, schedule)
        value, g_new = pp.recalculated(row.guarantee_sek_per_month, old, new)
        g_new = g_new.quantize(PRECISION)
        g_total += g_new
        guarantees.append({"id": str(row.id), "version": row.version, "basis_code": row.basis_code,
                           "basis_checksum": row.basis_checksum, "plan_kind": row.plan_kind,
                           "g_old": str(row.guarantee_sek_per_month), "factor_old": str(old),
                           "value": str(value.quantize(PRECISION)), "factor_new": str(new), "g_new": str(g_new)})
    tracks = _part_capital(session, owner.part.id, valuation)
    capital = sum((t.balance for t in tracks), Decimal("0.00"))
    payout_factor = factor(bases.payout_model, birth, valuation, schedule)
    b = (capital / payout_factor).quantize(PRECISION)
    floor = pp.amount_floor(schedule, change, effective, previous.m_sek if previous else None,
                            previous.form if previous else None)
    amount = pp.pension_amount(g_total, b, floor)
    first_right_month = next((m for m in _months_from(effective, 1200) if schedule.has_right(m)), None)
    content = {
        "method": METHOD, "design": "P1-PENSION-001 §5, V1–V11", "rules": RULES,
        "payout_part_id": str(owner.part.id), "policy_number": owner.policy_number,
        "part_number": owner.part.part_number, "origin": origin,
        "request_id": str(request_id) if request_id else None, "change": change,
        "effective_month": effective.isoformat(), "valuation_date": valuation.isoformat(), "bindable": bindable,
        "note": note, "schedule": schedule.plain(), "consumed": schedule.rights_before(effective),
        "remaining": schedule.remaining_from(effective),
        "next_right": first_right_month.isoformat() if first_right_month else None,
        "first_payment_day": next_bank_day(aa.add_months(first_right_month, 1)).isoformat()
        if first_right_month else None,
        "capital_sek": str(capital), "guarantees": guarantees, "guarantee_sek_per_month": str(g_total),
        "payout_basis": {"code": bases.payout_code, "checksum": bases.payout_checksum, "factor": str(payout_factor)},
        "capital_amount_sek": str(b),
        "amount": _plain(amount),
        "previous_plan": ({"id": str(previous.id), "version": previous.version, "m_sek": str(previous.m_sek),
                           "form": previous.form} if previous else None),
    }
    return {**content, "review_checksum": vb.checksum(content)}


def _months_from(first: date, count: int):
    month = first
    for _ in range(count):
        yield month
        month = aa.add_months(month, 1)


def standard_plan(session: Session, owner: Owner, month: date, *, bases: Bases | None = None,
                  valuation: date | None = None, pension_age: int = pp.PENSION_AGE) -> dict:
    """Standardplanen livsvarig från 66-årsmånaden (PR-ITP1-025), räknad på föregående månadsslut."""
    start = pp.sixty_six_month(owner.birth, pension_age)
    return evaluate(session, owner, pp.Schedule(start, None), "start", month, origin="standard_start",
                    request_id=None, bases=bases, valuation=valuation or month_end(aa.add_months(month, -1)),
                    bindable=True)


# --- begäran --------------------------------------------------------------------------------------


def _month(value) -> date | None:
    if value in (None, ""):
        return None
    day = date.fromisoformat(str(value))
    if day.day != 1:
        raise PlanServiceError(f"{value} ska vara en månadsförsta (ÅÅÅÅ-MM-01)")
    return day


def change_month(session: Session, owner: Owner, kind: str, content: dict, received: date) -> date:
    """Ändringsmånaden som fristen räknas mot (V8)."""
    if kind == "start":
        wanted = _month(content["first_right"])
        current = latest_plan(session, owner.part.id)
        reference = (date.fromisoformat(current.content["schedule"]["first_right"]) if current is not None
                     else pp.sixty_six_month(owner.birth))
        return wanted if reference < pp.next_possible_month(received) else min(wanted, reference)
    if kind == "pause":
        return _month(content["first"])
    return _month(content["month"])


def _missing(kind: str, content: dict) -> list[str]:
    missing = [f for f in REQUIRED[kind] if content.get(f) in (None, "")]
    form = content.get("form")
    if kind in ("start", "extend") and form not in (None, "", *pp.FORMS):
        missing.append(f"form ska vara {' eller '.join(pp.FORMS)}")
    if kind in ("start", "extend") and form == "fixed_term" and not content.get("payments"):
        missing.append("payments (antal rättigheter för tidsbegränsad plan)")
    return missing


def request_identity(part_id, kind, content, received, channel, requester, authority, confirms) -> tuple[uuid.UUID, str]:
    body = {"payout_part_id": str(part_id), "kind": kind, "content": content, "received_date": received.isoformat(),
            "channel": channel, "requester": requester, "authority_verified": authority,
            "confirms_request_id": str(confirms) if confirms else None}
    digest = vb.checksum(body)
    return cl.stable_id("payout_request", digest), digest


def next_case_number(session: Session) -> str:
    from services.operations.cases import (
        _next_case_number,  # samma nummerserie som övriga ärenden
    )
    return _next_case_number(session)


def register_request(session: Session, owner: Owner, kind: str, content: dict, received: date, channel: str,
                     requester: str, authority_verified: bool, confirms: uuid.UUID | None,
                     actor: str) -> tuple[PayoutRequest, bool]:
    """Sparar begäran med fristens utfall och ett ärende `payout_request`. Samma begäran igen: ingen ny rad."""
    _require(session)
    request_id, digest = request_identity(owner.part.id, kind, content, received, channel, requester,
                                          authority_verified, confirms)
    if (existing := session.get(PayoutRequest, request_id)) is not None:
        return existing, False
    if confirms is not None:
        confirmed = session.get(PayoutRequest, confirms)
        if confirmed is None or confirmed.payout_part_id != owner.part.id or confirmed.outcome != "late":
            raise PlanServiceError("Bekräftelsen ska peka på en sen begäran för samma uttagsdel")
    missing = _missing(kind, content)
    stop = []
    if owner.status == "deceased":
        stop.append("ägaren är registrerad som avliden")
    if owner.birth is None:
        stop.append("identiteten kan inte styrkas: födelsedagen kan inte läsas")
    if requester == "representative" and not authority_verified:
        stop.append("ombudets behörighet är inte verifierad")
    change = None
    if not stop and not missing:
        try:
            change = change_month(session, owner, kind, content, received)
        except (PlanServiceError, ValueError) as exc:
            missing.append(str(exc))
    blocked = (kind == "start" and change is not None and not stop and not missing
               and _month(content["first_right"]) < pp.sixty_six_month(owner.birth))
    change = change or pp.next_possible_month(received)
    deadline = pp.deadline_for(change)
    outcome = ("stopped" if stop else "incomplete" if missing else "blocked" if blocked
               else "late" if received > deadline else "in_time")
    if blocked:
        stop.append("uttag före 66 år (PR-ITP1-002) ingår inte i första versionen (PB1)")
    proposed = pp.next_possible_month(received) if outcome == "late" else None
    case = Case(id=uuid.uuid4(), case_number=next_case_number(session), case_type="payout_request",
                status="waiting_info" if outcome == "incomplete" else "open",
                insured_person_id=owner.person_id, policy_id=owner.policy_id, channel=channel,
                received_date=received, source_reference=f"payout_request:{request_id}",
                details={"request_id": str(request_id), "kind": kind, "outcome": outcome,
                         "payout_part": owner.part.part_number, "change_month": change.isoformat(),
                         "deadline": deadline.isoformat(),
                         "proposed_month": proposed.isoformat() if proposed else None,
                         "missing": missing + stop}, created_by=actor)
    session.add(case)
    session.flush()
    request = PayoutRequest(
        id=request_id, insured_person_id=owner.person_id, payout_part_id=owner.part.id, kind=kind,
        change_month=change, content=content, received_date=received, channel=channel, requester=requester,
        authority_verified=authority_verified, deadline=deadline, outcome=outcome, proposed_month=proposed,
        missing=missing + stop, confirms_request_id=confirms, case_id=case.id, checksum=digest,
        registered_by=actor)
    session.add(request)
    session.flush()
    return request, True


def request_schedule(session: Session, owner: Owner, request: PayoutRequest) -> tuple[pp.Schedule, str]:
    """Ny planens kalender ur begäran (PR-ITP1-003–007). Avslag ger PlanError."""
    content = request.content
    current_plan = latest_plan(session, owner.part.id)
    current = schedule_of(current_plan) if current_plan is not None else None
    state = part_state(session, owner.part.id, request.change_month)
    if request.kind == "start":
        if state not in (None, "not_started"):
            raise pp.PlanError("Delen har startat; efter start används paus eller förlängning (PR-ITP1-003)")
        payments = content.get("payments") if content.get("form") == "fixed_term" else None
        return pp.start_plan(_month(content["first_right"]), payments, owner.birth, current=current,
                             change_month=request.change_month), "start"
    if current is None:
        raise pp.PlanError("Delen saknar beslutad plan – paus och förlängning gäller en påbörjad del")
    if request.kind == "pause":
        return pp.pause_plan(current, _month(content["first"]), _month(content["resume"])), "pause"
    payments = content.get("payments") if content.get("form") == "fixed_term" else None
    return pp.extend_plan(current, payments, request.change_month), "extend"


def _decidable(session: Session, request: PayoutRequest) -> None:
    if request.outcome != "in_time":
        raise PlanServiceError(f"Begäran har utfallet {request.outcome} – bara en begäran i tid och fullständig kan "
                               "beslutas; en sen begäran bekräftas med en ny begäran för föreslagen månad")
    if session.scalar(select(PayoutPlan.id).where(PayoutPlan.request_id == request.id)) or \
            session.scalar(select(PayoutSplit.id).where(PayoutSplit.request_id == request.id)):
        raise PlanServiceError("Begäran är redan beslutad")


def preview_request(session: Session, request: PayoutRequest) -> dict:
    """Förhandsberäkningen för begäran: planversion eller delning med granskningssumma."""
    _require(session)
    owner = owners(session, [request.payout_part_id])[request.payout_part_id]
    if request.kind == "split":
        return preview_split(session, owner, request)
    try:
        schedule, change = request_schedule(session, owner, request)
    except pp.PlanError as exc:
        raise PlanServiceError(str(exc)) from exc
    return evaluate(session, owner, schedule, change, request.change_month, origin="request", request_id=request.id)


def decide_plan(session: Session, request: PayoutRequest, reviewed_checksum: str, reason: str,
                actor: str) -> PayoutPlan:
    """Sparar planversionen hashbundet mot förhandsberäkningen (V2). Journalen ändras i ändringsmånadens stängning."""
    _decidable(session, request)
    if request.kind == "split":
        raise PlanServiceError("Delning beslutas med split_payout_part")
    preview = preview_request(session, request)
    if preview["review_checksum"] != reviewed_checksum:
        raise PlanConflict("Underlaget har ändrats sedan förhandsberäkningen – räkna om planen")
    if not preview["bindable"]:
        raise PlanServiceError(preview["note"])
    previous = latest_plan(session, request.payout_part_id)
    if previous is not None and previous.effective_month > request.change_month:
        raise PlanServiceError(f"En senare planversion gäller från {previous.effective_month:%Y-%m}")
    content = {k: v for k, v in preview.items() if k != "review_checksum"}
    schedule = pp.Schedule.from_plain(content["schedule"])
    plan = PayoutPlan(
        id=cl.stable_id("payout_plan", reviewed_checksum), payout_part_id=request.payout_part_id,
        version=previous.version + 1 if previous else 1, supersedes_id=previous.id if previous else None,
        origin="request", request_id=request.id, change=content["change"], effective_month=request.change_month,
        valuation_date=date.fromisoformat(content["valuation_date"]), form=schedule.form,
        first_right=schedule.first_right, payments=schedule.payments,
        pauses=content["schedule"]["pauses"], end_month=schedule.end_month, consumed=content["consumed"],
        capital_sek=Decimal(content["capital_sek"]), guarantee_sek_per_month=Decimal(content["guarantee_sek_per_month"]),
        capital_amount_sek=Decimal(content["capital_amount_sek"]), payout_basis_code=content["payout_basis"]["code"],
        payout_basis_checksum=content["payout_basis"]["checksum"],
        payout_factor=Decimal(content["payout_basis"]["factor"]), m_sek=Decimal(content["amount"]["m_sek"]),
        floor_sek=Decimal(content["amount"]["previous_floor_sek"]) if content["amount"]["previous_floor_sek"] else None,
        content=content, checksum=reviewed_checksum, reason=reason, decided_by=actor)
    session.add(plan)
    _close_case(session, request, actor, f"Planversion {plan.version} beslutad: {reason}")
    session.flush()
    return plan


def _close_case(session: Session, request: PayoutRequest, actor: str, note: str) -> None:
    case = session.get(Case, request.case_id) if request.case_id else None
    if case is not None and case.status != "closed":
        case.status, case.outcome, case.closed_by = "closed", "approved", actor
        case.closed_at, case.closing_note = datetime.now(UTC), note


class PlanConflict(PlanServiceError):
    """Granskningssumman stämmer inte: underlaget har ändrats."""


# --- delning --------------------------------------------------------------------------------------


def split_amounts(tracks: list[cl.Track], share: Decimal) -> tuple[Decimal, list[Decimal]]:
    """Den nya delens kapital i ören och fördelningen på spåren (V9). Fall 7: 100 000,00 × 30 % = 30 000,00."""
    total = sum((t.balance for t in tracks), Decimal("0.00"))
    target = (total * share).quantize(CENT, ROUND_HALF_UP)
    return target, allocate_cents(target, [t.balance for t in tracks]) if tracks else []


def split_guarantee(g: Decimal, share: Decimal) -> tuple[Decimal, Decimal]:
    """(kvar, ny) för en garantidel: proportionellt utan ny värdering, summan exakt bevarad."""
    new = (g * share).quantize(PRECISION)
    return g - new, new


def new_part_id(split_id: uuid.UUID) -> uuid.UUID:
    return cl.stable_id("payout_split", "part", str(split_id))


def preview_split(session: Session, owner: Owner, request: PayoutRequest) -> dict:
    content = request.content
    effective = request.change_month
    share = Decimal(str(content["share"]))
    if not pp.split_share_valid(share):
        raise PlanServiceError(f"Andelen {share:%} avslås: ny och kvarvarande del ska vara minst 10 % (PR-ITP1-024)")
    state = part_state(session, owner.part.id, effective)
    plan = plans_in_force(session, [owner.part.id], effective).get(owner.part.id)
    if state != "not_started" or (plan is not None and pp.Schedule.from_plain(plan.content["schedule"])
                                  .first_right <= effective):
        raise PlanServiceError("Bara en ej startad uttagsdel kan delas i första versionen (PR-ITP1-024)")
    existing = dict(session.execute(select(PayoutPart.id, PayoutPart.part_number)
                                    .where(PayoutPart.benefit_id == owner.benefit_id)).all())
    numbers = sorted(existing.values())
    # Beslutade delningar vars nya del ännu inte skapats av stängningen räknas också
    pending = [s for s in session.scalars(select(PayoutSplit).where(PayoutSplit.from_part_id.in_(list(existing))))
               if new_part_id(s.id) not in existing]
    taken = len(numbers) + len(pending)
    if taken >= MAX_PARTS:
        raise PlanServiceError(f"Försäkringen har redan {taken} uttagsdelar; högst {MAX_PARTS} (PR-ITP1-024)")
    number = taken + 1
    receiver = int(content["premium_receiver"])
    if receiver not in (*numbers, number):
        raise PlanServiceError(f"Premiemottagaren {receiver} är ingen av förmånens delar efter delningen")
    valuation, bindable, note = valuation_point(session, effective)
    tracks = _part_capital(session, owner.part.id, valuation)
    target, moves = split_amounts(tracks, share)
    guarantees = []
    for row in _part_guarantees(session, owner.part.id, valuation):
        keep, new = split_guarantee(row.guarantee_sek_per_month, share)
        guarantees.append({"id": str(row.id), "version": row.version, "g": str(row.guarantee_sek_per_month),
                           "kept": str(keep), "new": str(new)})
    capital = sum((t.balance for t in tracks), Decimal("0.00"))
    body = {
        "method": METHOD, "design": "P1-PENSION-001 §5, V1–V11", "rules": ["PR-ITP1-015", "PR-ITP1-024"],
        "kind": "split", "payout_part_id": str(owner.part.id), "policy_number": owner.policy_number,
        "part_number": owner.part.part_number, "new_part_number": number, "share": str(share),
        "request_id": str(request.id), "effective_month": effective.isoformat(),
        "valuation_date": valuation.isoformat(), "bindable": bindable, "note": note,
        "capital_sek": str(capital), "new_capital_sek": str(target), "kept_capital_sek": str(capital - target),
        "tracks": [{"origin_id": str(t.origin_id), "balance": str(t.balance), "moved": str(m)}
                   for t, m in zip(tracks, moves)],
        "guarantees": guarantees, "premium_receiver_number": receiver,
    }
    return {**body, "review_checksum": vb.checksum(body)}


def decide_split(session: Session, request: PayoutRequest, reviewed_checksum: str, reason: str,
                 actor: str) -> PayoutSplit:
    _decidable(session, request)
    if request.kind != "split":
        raise PlanServiceError("Begäran gäller inte delning")
    preview = preview_request(session, request)
    if preview["review_checksum"] != reviewed_checksum:
        raise PlanConflict("Underlaget har ändrats sedan förhandsberäkningen – räkna om delningen")
    if not preview["bindable"]:
        raise PlanServiceError(preview["note"])
    content = {k: v for k, v in preview.items() if k != "review_checksum"}
    split = PayoutSplit(
        id=cl.stable_id("payout_split", reviewed_checksum), from_part_id=request.payout_part_id, request_id=request.id,
        new_part_number=content["new_part_number"], share=Decimal(content["share"]),
        effective_month=request.change_month, valuation_date=date.fromisoformat(content["valuation_date"]),
        premium_receiver_number=content["premium_receiver_number"], capital_sek=Decimal(content["capital_sek"]),
        content=content, checksum=reviewed_checksum, reason=reason, decided_by=actor)
    session.add(split)
    _close_case(session, request, actor, f"Delning beslutad: {reason}")
    session.flush()
    return split


def splits_in(session: Session, month: date) -> list[PayoutSplit]:
    if not plans_present(session):
        return []
    return list(session.scalars(select(PayoutSplit).where(PayoutSplit.effective_month == month)
                                .order_by(PayoutSplit.id)))


def premium_receiver(session: Session, benefit_ids, month: date) -> dict[uuid.UUID, int]:
    """Förmån → primär premiemottagare enligt senaste genomförda delning (PR-ITP1-015, V9)."""
    benefit_ids = list(benefit_ids)
    if not benefit_ids or not plans_present(session):
        return {}
    out = {}
    for benefit, number in session.execute(
            select(PayoutPart.benefit_id, PayoutSplit.premium_receiver_number)
            .join(PayoutPart, PayoutPart.id == PayoutSplit.from_part_id)
            .where(PayoutPart.benefit_id.in_(benefit_ids), PayoutSplit.effective_month <= month)
            .order_by(PayoutSplit.effective_month)):
        out[benefit] = number
    return out


# --- läsning --------------------------------------------------------------------------------------


def part_view(session: Session, owner: Owner, on: date) -> dict:
    """Delens planer, begäran och delningar med kapital och garanti per dagen (ett månadsslut)."""
    plans = (session.scalars(select(PayoutPlan).where(PayoutPlan.payout_part_id == owner.part.id)
                             .order_by(PayoutPlan.version)).all() if plans_present(session) else [])
    requests = (session.scalars(select(PayoutRequest).where(PayoutRequest.payout_part_id == owner.part.id)
                                .order_by(PayoutRequest.received_date)).all() if plans_present(session) else [])
    splits = (session.scalars(select(PayoutSplit).where(PayoutSplit.from_part_id == owner.part.id)).all()
              if plans_present(session) else [])
    capital = sum((t.balance for t in _part_capital(session, owner.part.id, on)), Decimal("0.00"))
    g = sum((r.guarantee_sek_per_month for r in _part_guarantees(session, owner.part.id, on)), Decimal(0))
    return {
        "policy_number": owner.policy_number, "part_number": owner.part.part_number,
        "share_of_origin": str(owner.part.share_of_origin), "state": part_state(session, owner.part.id, on.replace(day=1)),
        "sixty_six_month": pp.sixty_six_month(owner.birth).isoformat() if owner.birth else None,
        "on": on.isoformat(), "capital_sek": str(capital), "guarantee_sek_per_month": str(g),
        "plans": [{"version": p.version, "origin": p.origin, "change": p.change,
                   "effective_month": p.effective_month.isoformat(), "form": p.form,
                   "first_right": p.first_right.isoformat(), "payments": p.payments, "pauses": p.pauses,
                   "end_month": p.end_month.isoformat() if p.end_month else None, "m_sek": str(p.m_sek),
                   "decided_by": p.decided_by, "checksum": p.checksum} for p in plans],
        "requests": [{"id": str(r.id), "kind": r.kind, "change_month": r.change_month.isoformat(),
                      "received_date": r.received_date.isoformat(), "outcome": r.outcome,
                      "proposed_month": r.proposed_month.isoformat() if r.proposed_month else None,
                      "missing": r.missing} for r in requests],
        "splits": [{"new_part_number": s.new_part_number, "share": str(s.share),
                    "effective_month": s.effective_month.isoformat(),
                    "premium_receiver_number": s.premium_receiver_number} for s in splits],
    }


__all__ = ["METHOD", "Bases", "Owner", "PlanConflict", "PlanServiceError", "covered", "decide_plan", "decide_split",
           "evaluate", "factor", "find_part", "latest_plan", "new_part_id", "owners", "part_view",
           "plans_in_force", "plans_present", "premium_receiver", "preview_request", "register_request",
           "schedule_of", "split_amounts", "split_guarantee", "splits_in", "standard_plan", "valuation_point"]
