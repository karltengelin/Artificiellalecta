"""Läsningarna bakom handläggarsidan *Pensioner och utbetalningar* (paket B steg 8, B-056, P1-PENSION-001 §10.1).

Tre läsningar som steg 1–7 saknar (Z4): läget för hela uttagsflödet, uttagsdelarna med ägare och plan, och
en persons skattestatus och konton i alla versioner. Modulen läser bara – den skriver ingenting och ändrar
ingen av steg 1–7:s moduler. Den fungerar i en databas där steg 1–7 bara delvis är införda: varje del
prövar sina tabeller och svarar `introduced: false` i stället för att fallera (Z9).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, inspect, or_, select
from sqlalchemy.orm import Session

from analytics.portfolio_snapshot import birth_date
from models import (
    Case,
    InsuredPerson,
    LedgerBatch,
    LedgerCapitalEntry,
    LedgerControl,
    LedgerGuaranteePart,
    PayoutAccount,
    PayoutPart,
    PayoutPartState,
    Policy,
    PolicyBenefit,
    TaxStatus,
)
from services import capital_ledger as cl
from services import death_reports as dr
from services import payout_orders as po
from services import payout_plans as plans
from services import pension_claims as pc
from skills.calculation import actuarial_annuity as aa
from skills.calculation import payout_plan as pp

ZERO = Decimal("0.00")
#: Steg 1:s och 2:s tabeller, samma som migreringarna inför. De läses ur modellerna och inte ur
#: utils.migration_*: migreringsmodulerna importerar tjänstelagret, och det blir en cirkelimport.
PART_TABLES = tuple(m.__tablename__ for m in (PayoutPart, PayoutPartState))
LEDGER_TABLES = tuple(m.__tablename__ for m in (LedgerBatch, LedgerGuaranteePart, LedgerCapitalEntry, LedgerControl))
#: Alla saldon räknas efter alla bokningar, också den öppna månadens (insättning, bankkvitton)
LAST_MONTH = date(9999, 12, 1)

#: Ärendetyperna som hör till uttagsflödet (paket B steg 1–7)
PENSION_CASE_TYPES = ("payout_reconstruction", "payout_request", "payout_review", "company_capital",
                      "payout_hindrance", "tax_status", "death_report", "death_recovery", "inheritance_pool")

#: Steg 1–7 med tabeller och migrationsskript (Z9). Steg 3 inför en kolumn, inte en tabell.
STEPS = (
    (1, "Uttagsdelar", PART_TABLES, "migrate_payout_parts.py"),
    (2, "Kapitaljournal", LEDGER_TABLES, "migrate_capital_ledger.py"),
    (3, "Månadsstängning", ("ledger_batches.supersedes_id",), "migrate_month_close.py"),
    (4, "Uttagsplaner", plans.PLAN_TABLES, "migrate_payout_plans.py"),
    (5, "Månadsrätter och bolagskonto", pc.CLAIM_TABLES, "migrate_pension_claims.py"),
    (6, "Skatt, konto och bankuppdrag", po.ORDER_TABLES, "migrate_payout_orders.py"),
    (7, "Dödsfall och arvsvinst", dr.DEATH_TABLES, "migrate_death_reports.py"),
)


class DeskError(ValueError):
    """Uppgiften kan inte läsas, t.ex. en okänd försäkring eller person."""


# --- stegen ---------------------------------------------------------------------------------------


def steps(session: Session) -> list[dict]:
    """Vilka av steg 1–7 som är införda i vald databas, med saknade tabeller per steg."""
    names = set(inspect(session.connection()).get_table_names())
    supersedes = cl.month_close_present(session)
    out = []
    for number, title, tables, script in STEPS:
        if number == 3:
            missing = [] if supersedes else list(tables)
        else:
            missing = [t for t in tables if t not in names]
        out.append({"step": number, "title": title, "tables": list(tables), "script": script,
                    "introduced": not missing, "partial": bool(missing) and len(missing) < len(tables),
                    "missing_tables": missing})
    return out


def introduced(step_rows: list[dict], number: int) -> bool:
    """Steget och alla steg före det är införda (stegen bygger på varandra)."""
    return all(s["introduced"] for s in step_rows if s["step"] <= number)


# --- läget ----------------------------------------------------------------------------------------


def _months(session: Session) -> dict:
    opening = cl.opening_batch(session)
    closed = cl.closed_month_ends(session)
    last = max([opening.period_end, *closed]) if opening else None
    return {"opening": opening.period_end.isoformat() if opening else None,
            "last_closed": max(closed).isoformat() if closed else None,
            "next_open": aa.first_month_after(last).isoformat() if last else None,
            "closed_months": len(closed)}


def _part_states(session: Session) -> dict[str, int]:
    rows = session.execute(select(PayoutPartState.state, func.count()).where(PayoutPartState.valid_to.is_(None))
                           .group_by(PayoutPartState.state)).all()
    return {state: count for state, count in rows}


def _turning_66(session: Session, today: date) -> int:
    """Ej startade delar vars ägare fyller 66 inom tolv månader från dagen."""
    first, last = today.replace(day=1), aa.add_months(today.replace(day=1), 12)
    count = 0
    for pnr in session.scalars(select(InsuredPerson.personal_id_number)
                               .join(Policy, Policy.insured_person_id == InsuredPerson.id)
                               .join(PolicyBenefit, PolicyBenefit.policy_id == Policy.id)
                               .join(PayoutPart, PayoutPart.benefit_id == PolicyBenefit.id)
                               .join(PayoutPartState, PayoutPartState.payout_part_id == PayoutPart.id)
                               .where(PayoutPartState.valid_to.is_(None), PayoutPartState.state == "not_started")):
        birth = birth_date(pnr)
        if birth and first <= pp.sixty_six_month(birth) <= last:
            count += 1
    return count


def _cases(session: Session) -> tuple[dict[str, int], list[dict]]:
    """Öppna ärenden per typ, och de ärenden som inte gäller en person (bolagskonto, arvsvinstpool)."""
    rows = session.execute(select(Case.case_type, func.count()).where(Case.case_type.in_(PENSION_CASE_TYPES),
                                                                     Case.status != "closed")
                           .group_by(Case.case_type)).all()
    counts = {t: 0 for t in PENSION_CASE_TYPES} | {t: n for t, n in rows}
    subjectless = [{"case_number": c.case_number, "case_type": c.case_type, "status": c.status,
                    "received_date": c.received_date.isoformat()}
                   for c in session.scalars(select(Case).where(Case.case_type.in_(("company_capital", "inheritance_pool")),
                                                               Case.status != "closed")
                                            .order_by(Case.received_date, Case.case_number))]
    return counts, subjectless


def status(session: Session, today: date) -> dict:
    """Hela uttagsflödets läge utan personuppgifter: steg, månader, delar, ärenden och saldon (Z2, Z4)."""
    step_rows = steps(session)
    out: dict = {"today": today.isoformat(), "steps": step_rows, "months": None, "parts": None, "cases": None,
                 "subjectless_cases": [], "balances": {}, "company_capital_registered": None}
    if introduced(step_rows, 1):
        states = _part_states(session)
        out["parts"] = {"by_state": states, "total": sum(states.values()), "turning_66_within_12_months":
                        _turning_66(session, today)}
        out["cases"], out["subjectless_cases"] = _cases(session)
    if introduced(step_rows, 2):
        out["months"] = _months(session)
    balances = out["balances"]
    if introduced(step_rows, 5):
        balances["payment_liability_sek"] = str(pc.account_balance(session, pc.LIABILITY, LAST_MONTH))
        balances["company_sek"] = str(pc.account_balance(session, pc.COMPANY, LAST_MONTH))
        out["company_capital_registered"] = pc.capital_registered(session)
    if introduced(step_rows, 6):
        balances["tax_liability_sek"] = str(pc.account_balance(session, po.TAX_LIABILITY, LAST_MONTH))
    if introduced(step_rows, 7):
        balances["inheritance_pool_sek"] = str(pc.account_balance(session, dr.POOL, LAST_MONTH))
    return out


# --- uttagsdelarna --------------------------------------------------------------------------------


def _plan_summary(plan) -> dict | None:
    if plan is None:
        return None
    return {"version": plan.version, "origin": plan.origin, "form": plan.form,
            "first_right": plan.first_right.isoformat(), "payments": plan.payments,
            "end_month": plan.end_month.isoformat() if plan.end_month else None, "m_sek": str(plan.m_sek)}


def _open_cases_by_person(session: Session, person_ids) -> dict[uuid.UUID, list[dict]]:
    out: dict[uuid.UUID, list[dict]] = defaultdict(list)
    person_ids = list(person_ids)
    for start in range(0, len(person_ids), 5000):
        for c in session.scalars(select(Case).where(Case.insured_person_id.in_(person_ids[start:start + 5000]),
                                                    Case.case_type.in_(PENSION_CASE_TYPES), Case.status != "closed")
                                 .order_by(Case.received_date, Case.case_number)):
            out[c.insured_person_id].append({"case_number": c.case_number, "case_type": c.case_type,
                                             "status": c.status})
    return out


def list_parts(session: Session, today: date, *, state: str | None = None, turning_66: bool = False,
               case_type: str | None = None, policy_number: str | None = None, query: str | None = None,
               limit: int = 100, offset: int = 0) -> dict:
    """Uttagsdelarna med försäkringsnummer, ägarens namn, 66-årsmånad, läge och gällande plan – inget personnummer."""
    query_rows = (select(PayoutPart, PayoutPartState, Policy.policy_number, InsuredPerson)
                  .join(PolicyBenefit, PolicyBenefit.id == PayoutPart.benefit_id)
                  .join(Policy, Policy.id == PolicyBenefit.policy_id)
                  .join(InsuredPerson, InsuredPerson.id == Policy.insured_person_id)
                  .join(PayoutPartState, (PayoutPartState.payout_part_id == PayoutPart.id)
                        & PayoutPartState.valid_to.is_(None)))
    if state is not None:
        query_rows = query_rows.where(PayoutPartState.state == state)
    if policy_number is not None:
        query_rows = query_rows.where(Policy.policy_number == policy_number)
    if query:
        like = f"%{query.strip()}%"
        query_rows = query_rows.where(or_(Policy.policy_number.ilike(like), InsuredPerson.first_name.ilike(like),
                                          InsuredPerson.last_name.ilike(like)))
    if case_type is not None:
        query_rows = query_rows.where(InsuredPerson.id.in_(
            select(Case.insured_person_id).where(Case.case_type == case_type, Case.status != "closed")))
    rows = session.execute(query_rows.order_by(Policy.policy_number, PayoutPart.part_number)).all()
    if turning_66:
        first, last = today.replace(day=1), aa.add_months(today.replace(day=1), 12)
        rows = [r for r in rows if r[1].state == "not_started" and (b := birth_date(r[3].personal_id_number))
                and first <= pp.sixty_six_month(b) <= last]
    total = len(rows)
    page = rows[offset:offset + limit]
    part_ids = [r[0].id for r in page]
    in_force = plans.plans_in_force(session, part_ids, LAST_MONTH)
    cases = _open_cases_by_person(session, {r[3].id for r in page})
    items = []
    for part, part_state, number, person in page:
        birth = birth_date(person.personal_id_number)
        items.append({"part_id": str(part.id), "policy_number": number, "part_number": part.part_number,
                      "share_of_origin": str(part.share_of_origin), "owner_name": f"{person.first_name} {person.last_name}",
                      "person_status": person.status,
                      "sixty_six_month": pp.sixty_six_month(birth).isoformat() if birth else None,
                      "state": part_state.state, "end_reason": part_state.end_reason,
                      "state_from": part_state.valid_from.isoformat(),
                      "plan": _plan_summary(in_force.get(part.id)), "open_cases": cases.get(person.id, [])})
    return {"parts": items, "count": len(items), "total": total, "offset": offset, "limit": limit,
            "plans_introduced": plans.plans_present(session)}


# --- personen -------------------------------------------------------------------------------------


def _person(session: Session, *, policy_number: str | None, personal_id_number: str | None) -> InsuredPerson:
    if policy_number is not None:
        person = session.scalar(select(InsuredPerson).join(Policy, Policy.insured_person_id == InsuredPerson.id)
                                .where(Policy.policy_number == policy_number))
        if person is None:
            raise DeskError(f"Försäkringen {policy_number} finns inte")
        return person
    person = session.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == personal_id_number))
    if person is None:
        raise DeskError("Ingen försäkrad med det personnumret")
    return person


def _tax_view(row: TaxStatus) -> dict:
    return {"tax_status_id": str(row.id), "tax_year": row.tax_year, "version": row.version, "kind": row.kind,
            "rate": str(row.rate) if row.rate is not None else None,
            "fixed_amount_sek": str(row.fixed_amount_sek) if row.fixed_amount_sek is not None else None,
            "table_number": row.table_number, "table_column": row.table_column,
            "raised_deduction": row.raised_deduction, "decision_ref": row.decision_ref,
            "valid_from": row.valid_from.isoformat(), "received_date": row.received_date.isoformat(),
            "channel": row.channel, "created_by": row.created_by}


def _account_history(row: PayoutAccount) -> dict:
    return {**po.account_view(row),  # verifieringsreferensen kan bära kontonumret och visas inte (Z6)
            "received_date": row.received_date.isoformat(), "channel": row.channel, "created_by": row.created_by}


def person_view(session: Session, *, policy_number: str | None = None, personal_id_number: str | None = None) -> dict:
    """Personens försäkringar och delar, skattestatus och konton i alla versioner; kontonumren maskerade (Z4, Z6)."""
    if (policy_number is None) == (personal_id_number is None):
        raise DeskError("Ange antingen försäkringsnummer eller personnummer")
    person = _person(session, policy_number=policy_number, personal_id_number=personal_id_number)
    step_rows = steps(session)
    parts = []
    if introduced(step_rows, 1):
        for part, number in session.execute(
                select(PayoutPart, Policy.policy_number).join(PolicyBenefit, PolicyBenefit.id == PayoutPart.benefit_id)
                .join(Policy, Policy.id == PolicyBenefit.policy_id).where(Policy.insured_person_id == person.id)
                .order_by(Policy.policy_number, PayoutPart.part_number)):
            current = session.scalar(select(PayoutPartState).where(PayoutPartState.payout_part_id == part.id,
                                                                   PayoutPartState.valid_to.is_(None)))
            parts.append({"part_id": str(part.id), "policy_number": number, "part_number": part.part_number,
                          "state": current.state if current else None,
                          "end_reason": current.end_reason if current else None})
    birth = birth_date(person.personal_id_number)
    out = {"person_id": str(person.id), "personal_id_number": person.personal_id_number,
           "name": f"{person.first_name} {person.last_name}", "status": person.status,
           "birth_date": birth.isoformat() if birth else None,
           "sixty_six_month": pp.sixty_six_month(birth).isoformat() if birth else None,
           "policies": sorted(set(session.scalars(select(Policy.policy_number)
                                                  .where(Policy.insured_person_id == person.id)))),
           "parts": parts, "orders_introduced": introduced(step_rows, 6), "tax_statuses": [], "accounts": [],
           "current_account": None}
    if out["orders_introduced"]:
        out["tax_statuses"] = [_tax_view(r) for r in session.scalars(
            select(TaxStatus).where(TaxStatus.insured_person_id == person.id)
            .order_by(TaxStatus.tax_year, TaxStatus.version))]
        out["accounts"] = [_account_history(r) for r in session.scalars(
            select(PayoutAccount).where(PayoutAccount.insured_person_id == person.id).order_by(PayoutAccount.version))]
        out["current_account"] = po.account_view(po.current_account(session, person.id))
    return out


__all__ = ["DeskError", "PENSION_CASE_TYPES", "STEPS", "introduced", "list_parts", "person_view", "status", "steps"]
