"""Månadsrätt, beloppsbeslut och bolagskonto i tjänstelagret (paket B steg 5, B-047 punkt 6 och 8, Karls val W1–W12).

Designstoppet P1-PENSION-001 §5.5 och §9 (PB6, PB10, PB11). Månadsstängningen (`services.month_close`)
räknar och bokar månadsrätten i PR-ITP1-020 steg 5; här finns läsningarna, beloppsbesluten och
bolagskontot. Den rena beräkningen ligger i `skills.calculation.pension_claim` och `payout_plan`.

**Beloppsbeslut (W2, PR-ITP1-009).** Planens M gäller när planen träder i kraft i rättighetsmånaden.
Annars beslutas M på föregående månadsslut vid verklig start (även efter uppskov), vid återstart och i
varje januari: M = max(round_half_up(max(G, B)), ceil_öre(ΣG_j), golv), där golvet för en livsvarig del
under de första 60 rätterna är senast beslutade M. Beloppet ligger fast mellan besluten.

**Bolagskontot (W7, PR-ITP1-028).** `register_capital` bokar ägarens dokumenterade insättning som en egen
verifikation `company_capital` i första öppna månaden. Bolagskontot blir aldrig negativt. Den första
stängningen med en månadsrätt kräver en registrerad insättning (PB11). E_min räknas av aktuarien i
projekt 6 (A8); stängningen visar bara likviditetsdelen 12 × ΣM.

**Utan steg 5:s migration** (`claims_present` nej) finns inga anspråk: stängningen beter sig som i steg 4.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import column, func, inspect, select, table
from sqlalchemy.orm import Session

from models import (
    LedgerBatch,
    LedgerCapitalEntry,
    PayoutAmount,
    PayoutPlan,
    PensionClaim,
    PensionClaimFunding,
)
from services import capital_ledger as cl
from services import payout_plans as pl
from services import valuation_bases as vb
from services.valuation_extract import PRECISION, month_end
from skills.calculation import actuarial_annuity as aa
from skills.calculation import payout_plan as pp
from utils.bank_calendar import next_bank_day

METHOD = "pension-claims-1"
CLAIM_TABLES = (PayoutAmount.__tablename__, PensionClaim.__tablename__, PensionClaimFunding.__tablename__)
CAPITAL_KIND = "company_capital"
COMPANY = "company"
LIABILITY = "payment_liability"
ZERO = Decimal("0.00")
#: Steg 7:s tabell för återförda anspråk (Y5); läses bara när den finns
REVERSALS = "pension_claim_reversals"
#: Hur stressgapet i E_min redovisas tills aktuarien räknar det (projekt 6, A8; Karls val W7)
STRESS_GAP = "ej beräknat – E_min räknas av aktuarien i projekt 6 (A8)"


class ClaimServiceError(ValueError):
    """Bolagskontot, beloppet eller anspråket kan inte registreras eller läsas."""


def claims_present(session: Session) -> bool:
    """Är steg 5:s migration körd (tabellerna för belopp, anspråk och finansiering)?"""
    names = set(inspect(session.connection()).get_table_names())
    return set(CLAIM_TABLES) <= names


def _require(session: Session) -> None:
    if not claims_present(session):
        raise ClaimServiceError("Månadsrätterna är inte införda i vald databas – migrate_pension_claims.py först")


# --- kalendern ------------------------------------------------------------------------------------


def state_in(schedule: pp.Schedule, month: date) -> str:
    """Delens pensionsläge under månaden enligt planen: ej startad, pågående, pausad eller avslutad."""
    month = month.replace(day=1)
    if month < schedule.first_right:
        return "not_started"
    if schedule.paused(month):
        return "paused"
    return "in_payout" if schedule.has_right(month) else "ended"


def payment_day(right_month: date) -> date:
    """Första svenska bankdagen efter rättighetsmånaden (PR-ITP1-026)."""
    return next_bank_day(aa.add_months(right_month.replace(day=1), 1))


# --- konton ---------------------------------------------------------------------------------------


def account_balance(session: Session, account: str, month: date, part_id: uuid.UUID | None = None) -> Decimal:
    """Kontots saldo efter alla poster till och med månaden, för en del eller hela kontot."""
    query = select(func.coalesce(func.sum(LedgerCapitalEntry.amount_sek), 0)).where(
        LedgerCapitalEntry.account == account, LedgerCapitalEntry.month <= month.replace(day=1))
    if part_id is not None:
        query = query.where(LedgerCapitalEntry.payout_part_id == part_id)
    return Decimal(str(session.scalar(query))).quantize(Decimal("0.01"))


def liability_by_part(session: Session, month: date) -> dict[uuid.UUID, Decimal]:
    rows = session.execute(select(LedgerCapitalEntry.payout_part_id, func.sum(LedgerCapitalEntry.amount_sek))
                           .where(LedgerCapitalEntry.account == LIABILITY,
                                  LedgerCapitalEntry.month <= month.replace(day=1))
                           .group_by(LedgerCapitalEntry.payout_part_id)).all()
    return {part: Decimal(str(total)).quantize(Decimal("0.01")) for part, total in rows}


def capital_batches(session: Session) -> list[LedgerBatch]:
    return list(session.scalars(select(LedgerBatch).where(LedgerBatch.kind == CAPITAL_KIND)
                                .order_by(LedgerBatch.created_at, LedgerBatch.id)))


def capital_registered(session: Session) -> bool:
    """Finns en dokumenterad startinsättning på bolagskontot (PB11)?"""
    return session.scalar(select(LedgerBatch.id).where(LedgerBatch.kind == CAPITAL_KIND).limit(1)) is not None


def first_open_month(session: Session) -> date:
    """Första månad som inte är stängd: månaden efter senaste stängning eller efter det ingående läget."""
    opening = cl.opening_batch(session)
    if opening is None:
        raise ClaimServiceError("Kapitaljournalen har inget ingående läge – övergången från S-04 görs först")
    closed = cl.closed_month_ends(session)
    return aa.first_month_after(max([opening.period_end, *closed]))


def register_capital(session: Session, amount: Decimal, decided_on: date, document_ref: str, note: str,
                     emin_reference: str | None, actor: str) -> tuple[LedgerBatch, bool]:
    """Bokar ägarens insättning på bolagskontot i första öppna månaden (PR-ITP1-028, W7). Idempotent."""
    _require(session)
    amount = Decimal(str(amount))
    if amount <= 0 or amount != amount.quantize(Decimal("0.01")):
        raise ClaimServiceError("Insättningen ska vara positiv och i hela ören")
    month = first_open_month(session)
    content = {"method": METHOD, "design": "P1-PENSION-001 §9, PB11, W7", "rules": ["PR-ITP1-028"],
               "kind": CAPITAL_KIND, "amount_sek": str(amount), "decided_on": decided_on.isoformat(),
               "document_ref": document_ref, "note": note, "emin_reference": emin_reference,
               "month": month.isoformat()}
    checksum = vb.checksum({k: v for k, v in content.items() if k != "month"})
    existing = session.scalar(select(LedgerBatch).where(LedgerBatch.kind == CAPITAL_KIND,
                                                        LedgerBatch.checksum == checksum))
    if existing is not None:
        return existing, False
    before = account_balance(session, COMPANY, month)
    batch = LedgerBatch(id=cl.stable_id(CAPITAL_KIND, checksum), kind=CAPITAL_KIND, period_end=month_end(month),
                        source="ledger", extract_id=None, extract_checksum=None,
                        content={**content, "company_before_sek": str(before),
                                 "company_after_sek": str(before + amount)},
                        checksum=checksum, created_by=actor)
    session.add(batch)
    session.flush()
    session.add(LedgerCapitalEntry(id=cl.stable_id(CAPITAL_KIND, checksum, "entry"), batch_id=batch.id,
                                   account=COMPANY, payout_part_id=None, origin_id=None, month=month,
                                   reason="company_capital", amount_sek=amount, balance_before_sek=before,
                                   balance_after_sek=before + amount, source="ledger", created_by=actor))
    session.flush()
    return batch, True


# --- anspråk och finansiering ---------------------------------------------------------------------


def funded_later(session: Session, claim_ids) -> dict[uuid.UUID, Decimal]:
    claim_ids = list(claim_ids)
    if not claim_ids:
        return {}
    rows = session.execute(select(PensionClaimFunding.claim_id, func.sum(PensionClaimFunding.amount_sek))
                           .where(PensionClaimFunding.claim_id.in_(claim_ids))
                           .group_by(PensionClaimFunding.claim_id)).all()
    return {c: Decimal(str(total)).quantize(Decimal("0.01")) for c, total in rows}


def not_reversed(session: Session, query):
    """Steg 7 (Y5): ett återfört anspråk efter dödsmånaden är varken ej finansierat eller betalbart. Utan steg 7:s
    tabell är frågan oförändrad (B-052)."""
    if not inspect(session.connection()).has_table(REVERSALS):
        return query
    reversed_ids = select(table(REVERSALS, column("claim_id")).c.claim_id)
    return query.where(PensionClaim.id.notin_(reversed_ids))


def outstanding_unfunded(session: Session, before: date | None = None) -> list[tuple[PensionClaim, Decimal]]:
    """Anspråk med ej finansierad rest, äldsta först (rättighetsmånad, del): (anspråk, rest). Ett återfört anspråk
    (steg 7) räknas inte."""
    query = not_reversed(session, select(PensionClaim).where(PensionClaim.unfunded_sek > 0))
    if before is not None:
        query = query.where(PensionClaim.right_month < before)
    claims = list(session.scalars(query.order_by(PensionClaim.right_month, PensionClaim.payout_part_id)))
    later = funded_later(session, [c.id for c in claims])
    out = [(c, c.unfunded_sek - later.get(c.id, ZERO)) for c in claims]
    return [(c, rest) for c, rest in out if rest > 0]


def claims_before(session: Session, part_ids, month: date) -> dict[uuid.UUID, int]:
    """Antal bokade månadsrätter per del före månaden – avstäms mot kalenderns förbrukade rätter."""
    part_ids = list(part_ids)
    if not part_ids:
        return {}
    return dict(session.execute(select(PensionClaim.payout_part_id, func.count())
                                .where(PensionClaim.payout_part_id.in_(part_ids), PensionClaim.right_month < month)
                                .group_by(PensionClaim.payout_part_id)).all())


def amounts_by_part(session: Session, part_ids, month: date) -> dict[uuid.UUID, PayoutAmount]:
    """Senaste beloppsbeslut per del med giltighet senast månaden."""
    part_ids = list(part_ids)
    if not part_ids:
        return {}
    out = {}
    for row in session.scalars(select(PayoutAmount).where(PayoutAmount.payout_part_id.in_(part_ids),
                                                          PayoutAmount.effective_month <= month)
                               .order_by(PayoutAmount.payout_part_id, PayoutAmount.effective_month)):
        out[row.payout_part_id] = row
    return out


def amount_from_plan(plan: PayoutPlan, month: date, reason: str) -> dict:
    """Beloppsbeslutet ur en plan som träder i kraft i rättighetsmånaden: planens M gäller (W2)."""
    amount = plan.content["amount"]
    return {"payout_part_id": str(plan.payout_part_id), "plan_id": str(plan.id), "effective_month": month.isoformat(),
            "reason": reason, "valuation_date": plan.content["valuation_date"],
            "capital_sek": plan.content["capital_sek"],
            "guarantee_sek_per_month": plan.content["guarantee_sek_per_month"],
            "capital_amount_sek": plan.content["capital_amount_sek"],
            "payout_basis_code": plan.content["payout_basis"]["code"],
            "payout_basis_checksum": plan.content["payout_basis"]["checksum"],
            "payout_factor": plan.content["payout_basis"]["factor"], "m_sek": amount["m_sek"],
            "floor_sek": amount["previous_floor_sek"], "binding": amount["binding"],
            "source": {"plan": plan.checksum}}


def compute_amount(owner: pl.Owner, plan: PayoutPlan, month: date, valuation: date, reason: str,
                   previous: PayoutAmount | None, bases: pl.Bases, *, previous_form: str | None,
                   guarantees: list, capital: Decimal) -> dict:
    """Nytt M på värderingen vid föregående månadsslut: verklig start, återstart eller januari (PR-ITP1-009, W2).

    `guarantees` är delens gällande garantidelar och `capital` dess kundkapital vid värderingsdagen.
    """
    schedule = pl.schedule_of(plan)
    g_total = sum((g.guarantee_sek_per_month for g in guarantees), Decimal(0))
    factor = pl.factor(bases.payout_model, owner.model_birth, valuation, schedule)
    b = (capital / factor).quantize(PRECISION)
    change = {"start": "start", "restart": "pause", "january": "january"}[reason]
    floor = pp.amount_floor(schedule, change, month, previous.m_sek if previous else None, previous_form)
    amount = pp.pension_amount(g_total, b, floor)
    return {"payout_part_id": str(owner.part.id), "plan_id": str(plan.id), "effective_month": month.isoformat(),
            "reason": reason, "valuation_date": valuation.isoformat(), "capital_sek": str(capital),
            "guarantee_sek_per_month": str(g_total.quantize(PRECISION)), "capital_amount_sek": str(b),
            "payout_basis_code": bases.payout_code, "payout_basis_checksum": bases.payout_checksum,
            "payout_factor": str(factor), "m_sek": str(amount["m_sek"]),
            "floor_sek": str(amount["previous_floor_sek"]) if amount["previous_floor_sek"] is not None else None,
            "binding": amount["binding"],
            "source": {"previous_amount": str(previous.id) if previous else None,
                       "guarantee_parts": len(guarantees), "rights_before": schedule.rights_before(month)}}


def amount_row(data: dict) -> dict:
    """Raden för `payout_amounts` ur beslutet i sammanställningen."""
    part = uuid.UUID(data["payout_part_id"])
    month = date.fromisoformat(data["effective_month"])
    return {"id": cl.stable_id("payout_amount", str(part), month.isoformat()), "payout_part_id": part,
            "plan_id": uuid.UUID(data["plan_id"]), "effective_month": month, "reason": data["reason"],
            "valuation_date": date.fromisoformat(data["valuation_date"]), "capital_sek": Decimal(data["capital_sek"]),
            "guarantee_sek_per_month": Decimal(data["guarantee_sek_per_month"]),
            "capital_amount_sek": Decimal(data["capital_amount_sek"]), "payout_basis_code": data["payout_basis_code"],
            "payout_basis_checksum": data["payout_basis_checksum"], "payout_factor": Decimal(data["payout_factor"]),
            "m_sek": Decimal(data["m_sek"]),
            "floor_sek": Decimal(data["floor_sek"]) if data["floor_sek"] is not None else None,
            "binding": data["binding"], "content": data}


def claim_id(part_id, month: date) -> uuid.UUID:
    return cl.stable_id("pension_claim", str(part_id), month.replace(day=1).isoformat())


# --- läsning --------------------------------------------------------------------------------------


def company_view(session: Session, on_month: date) -> dict:
    """Bolagskontot: insättningar, saldo och ej finansierade anspråk, utan individrader."""
    insertions = [{"batch_id": str(b.id), "amount_sek": b.content["amount_sek"], "decided_on": b.content["decided_on"],
                   "document_ref": b.content["document_ref"], "month": b.content["month"],
                   "emin_reference": b.content.get("emin_reference"), "created_by": b.created_by}
                  for b in capital_batches(session)]
    open_claims = outstanding_unfunded(session)
    return {"month": on_month.isoformat(), "balance_sek": str(account_balance(session, COMPANY, on_month)),
            "liability_sek": str(account_balance(session, LIABILITY, on_month)), "insertions": insertions,
            "unfunded_claims": len(open_claims), "unfunded_sek": str(sum((r for _, r in open_claims), ZERO)),
            "stress_gap": STRESS_GAP}


def claims_view(session: Session, *, month: date | None = None, part_ids=None) -> list[dict]:
    """Månadsrätterna för en månad eller delar, med finansiering och kvarstående ej finansierat."""
    query = select(PensionClaim)
    if month is not None:
        query = query.where(PensionClaim.right_month == month)
    if part_ids is not None:
        query = query.where(PensionClaim.payout_part_id.in_(list(part_ids)))
    claims = list(session.scalars(query.order_by(PensionClaim.right_month, PensionClaim.payout_part_id)))
    later = funded_later(session, [c.id for c in claims])
    return [{"claim_id": str(c.id), "payout_part_id": str(c.payout_part_id), "right_month": c.right_month.isoformat(),
             "right_number": c.right_number, "gross_sek": str(c.gross_sek), "from_capital_sek": str(c.from_capital_sek),
             "company_support_sek": str(c.company_support_sek), "unfunded_sek": str(c.unfunded_sek),
             "funded_later_sek": str(later.get(c.id, ZERO)),
             "unfunded_remaining_sek": str(c.unfunded_sek - later.get(c.id, ZERO)),
             "final_settlement": c.final_settlement, "payment_day": c.payment_day.isoformat(),
             "amount_id": str(c.amount_id), "batch_id": str(c.batch_id)} for c in claims]


def per_part_counts(claims: list[dict]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for c in claims:
        out[c["payout_part_id"]] += 1
    return dict(out)


__all__ = ["CAPITAL_KIND", "CLAIM_TABLES", "COMPANY", "LIABILITY", "METHOD", "STRESS_GAP", "ClaimServiceError",
           "account_balance", "amount_from_plan", "amount_row", "amounts_by_part", "capital_registered",
           "claim_id", "claims_before", "claims_present", "claims_view", "company_view", "compute_amount",
           "first_open_month", "funded_later", "liability_by_part", "not_reversed", "outstanding_unfunded", "payment_day",
           "register_capital", "state_in"]
