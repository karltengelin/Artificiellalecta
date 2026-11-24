"""Skattestatus, utbetalningskonto, bankuppdrag och bankkvitton (paket B steg 6, B-054, Karls val X1–X13).

Designstoppet P1-PENSION-001 §8 (PB7, PB8) och §8.3. Anspråket från steg 5 (`pension_claims`) är kontraktet
och ändras aldrig (W1). Betalningsförloppet står i egna rader som pekar på anspråket, och betalningsläget
härleds ur dem: förberett i bankfil, skickat, okänt, betalt, avvisat eller återkommet.

**Betalbart anspråk (X2).** Ett anspråk betalas bara när det är helt finansierat (W8) och saknar både öppen
och verkställd rad. Hela bruttot betalas i en rad. Efter avvisning eller retur krävs ett nytt verifierat
konto innan nästa försök (X8). Ett nytt försök är en ny rad med samma anspråk och nästa försöksnummer, aldrig
ett nytt anspråk, belopp eller en ny debitering av kundkapitalet (PR-ITP1-026).

**Bankfilen (X7).** `build_file` samlar de betalbara anspråken med betalningsdag senast den givna dagen,
per person, och räknar skatten per uppdrag (X3, `skills.calculation.payout_tax`). Utförandedagen är den
senare av betalningsdagen och närmaste bankdag från i dag. En person utan verifierat konto, utan skattestatus
för utbetalningsdagens år eller med huvudinkomst utan skattetabell blockeras med ärende, och skulden står kvar.
En avliden person stoppas. En ej godkänd fil ersätts när underlaget ändrats; samma underlag igen ger samma
fil. Godkännandet binder filens kontrollsumma och är den externa handlingen.

**Dödsfall (paket B steg 7, Y3, Y5 och Y10).** Ett misstänkt dödsfall stoppar personen med skälet
`death_suspected`. Ett återfört anspråk efter dödsmånaden är inte betalbart. Efter ett verifierat dödsfall
betalas bara anspråk med rätt senast dödsmånaden, till dödsboets verifierade konto när delarna är avräknade
och behörigheten prövad – annars blockeras personen med skälet `estate_missing`. Skatten är dödsboets
registrerade skattestatus utan gränserna för småbelopp, och uppdraget märks som dödsbo.

**Kvitton (X8–X9).** Varje kvitto sparas en gång per källsystem och kvitto-id; samma kvitto igen ger ingen
effekt, och samma id med ändrat innehåll ger konflikt för hela filen. Utförda och återkomna betalningar i en
kvittofil bokas som en egen verifikation `payout_settlement` i första öppna månaden: skulden minskar med
bruttot (`payout`) och skatteskulden ökar med skatten (`withholding`); en återkommen betalning ger exakta
motposter (`payout_returned`). Avvisat och okänt utfall bokas inte.

**Utan steg 6:s migration** (`orders_present` nej) finns inget av detta, och stängningen beter sig som i steg 5.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from analytics.portfolio_snapshot import birth_date
from models import (
    Case,
    InsuredPerson,
    LedgerBatch,
    LedgerCapitalEntry,
    PayoutAccount,
    PayoutFile,
    PayoutOrder,
    PayoutOrderLine,
    PayoutPart,
    PayoutReceipt,
    PensionClaim,
    Policy,
    PolicyBenefit,
    TaxStatus,
)
from services import capital_ledger as cl
from services import death_reports as dr
from services import payout_plans as pl
from services import pension_claims as pc
from services.valuation_extract import month_end
from skills.calculation import actuarial_annuity as aa
from skills.calculation import payout_tax as tx
from utils.bank_calendar import next_bank_day
from utils.checksums import checksum as content_checksum

METHOD = "payout-orders-1"
ORDER_TABLES = (TaxStatus.__tablename__, PayoutAccount.__tablename__, PayoutFile.__tablename__,
                PayoutOrder.__tablename__, PayoutOrderLine.__tablename__, PayoutReceipt.__tablename__)
SETTLEMENT_KIND = "payout_settlement"
TAX_LIABILITY = "tax_liability"
PAYOUT, WITHHOLDING, RETURNED = "payout", "withholding", "payout_returned"
ZERO = Decimal("0.00")
#: Betalningslägen som håller anspråket öppet (inget nytt försök) respektive avslutat
OPEN_STATES = ("bank_prepared", "sent", "unknown")
RETRY_STATES = ("rejected", "returned")
#: Tillåtna övergångar för ett uppdrag: senaste utfall → nytt utfall (X8)
TRANSITIONS = {None: {"executed", "rejected", "unknown"}, "unknown": {"executed", "rejected", "unknown"},
               "executed": {"returned"}}
#: Frivilligt högre sidoavdrag gäller från första utbetalningen två veckor efter begäran (X5)
VOLUNTARY_DELAY = timedelta(days=14)


class OrderServiceError(ValueError):
    """Skattestatus, konto, bankfil eller kvitto kan inte registreras eller läsas."""


class OrderConflict(OrderServiceError):
    """Underlaget har ändrats sedan granskningen, eller ett kvitto krockar med ett tidigare."""


def orders_present(session: Session) -> bool:
    """Är steg 6:s migration körd (skattestatus, konto, bankfil, uppdrag, rader och kvitton)?"""
    names = set(inspect(session.connection()).get_table_names())
    return set(ORDER_TABLES) <= names


def _require(session: Session) -> None:
    if not orders_present(session):
        raise OrderServiceError("Bankuppdragen är inte införda i vald databas – migrate_payout_orders.py först")


def _stable(*parts) -> uuid.UUID:
    return cl.stable_id("payout", *[str(p) for p in parts])


def mask(account_number: str) -> str:
    """Kontonumret maskerat i läsningar: bara de fyra sista siffrorna (X6)."""
    return "*" * max(len(account_number) - 4, 0) + account_number[-4:]


# --- skattestatus (X5) ----------------------------------------------------------------------------


def _latest(session: Session, model, *where):
    return session.scalar(select(model).where(*where).order_by(model.version.desc()).limit(1))


def _close_cases(session: Session, person_id: uuid.UUID, case_type: str, actor: str, note: str, **match) -> int:
    closed = 0
    for case in session.scalars(select(Case).where(Case.case_type == case_type, Case.insured_person_id == person_id,
                                                   Case.status != "closed")):
        if all(case.details.get(k) == v for k, v in match.items()):
            case.status, case.outcome, case.closed_by = "closed", "approved", actor
            case.closed_at, case.closing_note = datetime.now(UTC), note
            closed += 1
    return closed


def register_tax_status(session: Session, person: InsuredPerson, tax_year: int, kind: str, *, rate: Decimal | None,
                        fixed_amount: Decimal | None, table_number: int | None, table_column: int | None,
                        raised_deduction: bool, decision_ref: str | None, received: date, channel: str,
                        actor: str) -> tuple[TaxStatus, bool]:
    """Ny version av personens skattestatus för året (PR-ITP1-026, X5). Samma innehåll igen: ingen ny version."""
    _require(session)
    if kind not in tx.A_TAX_KINDS + ("sink",):
        raise OrderServiceError(f"Okänt skatteslag {kind}")
    rate = Decimal(str(rate)) if rate is not None else None
    fixed_amount = Decimal(str(fixed_amount)) if fixed_amount is not None else None
    if kind == "side_income":
        rate = rate if rate is not None else tx.SIDE_RATE
        if rate < tx.SIDE_RATE or (rate * 100) != (rate * 100).to_integral_value():
            raise OrderServiceError("Sidoinkomst har ett avdrag i hela procent på minst 30 % (PR-ITP1-026 p. 4)")
        if fixed_amount is not None or table_number is not None:
            raise OrderServiceError("Sidoinkomst har bara en procentsats")
    elif kind == "sink":
        if rate is None or not decision_ref:
            raise OrderServiceError("SINK kräver ett registrerat beslut med sats; adress räcker inte (PR-ITP1-026 p. 2)")
    elif kind == "individual_decision":
        if not decision_ref or (rate is None) == (fixed_amount is None):
            raise OrderServiceError("Individuellt beslut kräver beslutsreferens och antingen procent eller belopp")
    elif kind == "main_income":
        if table_number is None or table_column is None or not 1 <= table_column <= 6:
            raise OrderServiceError("Huvudinkomst kräver skattetabell och pensionskolumn (1–6)")
        born = birth_date(person.personal_id_number)
        if tax_year == 2026 and born is not None and table_column != (2 if born.year <= 1959 else 6):
            raise OrderServiceError("Pensionskolumnen för 2026 är 2 för födda 1959 eller tidigare och 6 för födda "
                                    "1960 eller senare (SKVFS 2025:20)")
    if rate is not None and not Decimal(0) <= rate <= Decimal(1):
        raise OrderServiceError("Satsen ska ligga mellan 0 och 1")
    valid_from = date(tax_year, 1, 1)
    if kind == "side_income" and rate > tx.SIDE_RATE:
        valid_from = max(valid_from, received + VOLUNTARY_DELAY)
    content = {"method": METHOD, "rules": ["PR-ITP1-026"], "person": str(person.id), "tax_year": tax_year,
               "kind": kind, "rate": str(rate) if rate is not None else None,
               "fixed_amount_sek": str(fixed_amount) if fixed_amount is not None else None,
               "table_number": table_number, "table_column": table_column, "raised_deduction": raised_deduction,
               "decision_ref": decision_ref, "valid_from": valid_from.isoformat()}
    digest = content_checksum(content)
    latest = _latest(session, TaxStatus, TaxStatus.insured_person_id == person.id, TaxStatus.tax_year == tax_year)
    if latest is not None and latest.checksum == digest:
        return latest, False
    version = latest.version + 1 if latest else 1
    row = TaxStatus(id=_stable("tax_status", person.id, tax_year, version), insured_person_id=person.id,
                    tax_year=tax_year, version=version, supersedes_id=latest.id if latest else None, kind=kind,
                    rate=rate, fixed_amount_sek=fixed_amount, table_number=table_number, table_column=table_column,
                    raised_deduction=raised_deduction, decision_ref=decision_ref, valid_from=valid_from,
                    received_date=received, channel=channel, content=content, checksum=digest, created_by=actor)
    session.add(row)
    session.flush()
    if kind != "main_income":
        _close_cases(session, person.id, "tax_status", actor, f"Skattestatus registrerad för {tax_year}",
                     tax_year=tax_year)
    return row, True


def status_for(session: Session, person_id: uuid.UUID, tax_year: int, on: date) -> TaxStatus | None:
    """Gällande version för året på utbetalningsdagen: högsta version som börjat gälla."""
    return session.scalar(select(TaxStatus).where(TaxStatus.insured_person_id == person_id,
                                                  TaxStatus.tax_year == tax_year, TaxStatus.valid_from <= on)
                          .order_by(TaxStatus.version.desc()).limit(1))


# --- konto (X6) -----------------------------------------------------------------------------------


def register_account(session: Session, person: InsuredPerson, clearing: str, account: str, bank: str, *,
                     verified: bool, method: str | None, reference: str | None, received: date, channel: str,
                     actor: str) -> tuple[PayoutAccount, bool]:
    """Ny version av personens utbetalningskonto (X6). Samma konto och verifiering igen: ingen ny version."""
    _require(session)
    if not (clearing.isdigit() and 4 <= len(clearing) <= 5 and account.isdigit() and 1 <= len(account) <= 20):
        raise OrderServiceError("Clearingnumret har 4–5 siffror och kontonumret 1–20 siffror")
    if verified and not (method and reference):
        raise OrderServiceError("Ett verifierat konto kräver verifieringssätt och referens")
    content = {"person": str(person.id), "clearing": clearing, "account": account, "bank": bank,
               "verified": verified, "method": method if verified else None,
               "reference": reference if verified else None}
    digest = content_checksum(content)
    latest = _latest(session, PayoutAccount, PayoutAccount.insured_person_id == person.id)
    if latest is not None and latest.checksum == digest:
        return latest, False
    version = latest.version + 1 if latest else 1
    row = PayoutAccount(id=_stable("account", person.id, version), insured_person_id=person.id, version=version,
                        supersedes_id=latest.id if latest else None, clearing_number=clearing,
                        account_number=account, bank_name=bank, verified=verified,
                        verification_method=content["method"], verification_ref=content["reference"],
                        received_date=received, channel=channel, checksum=digest, created_by=actor)
    session.add(row)
    session.flush()
    if verified:
        _close_cases(session, person.id, "payout_hindrance", actor, "Nytt verifierat konto registrerat")
    return row, True


def current_account(session: Session, person_id: uuid.UUID) -> PayoutAccount | None:
    return _latest(session, PayoutAccount, PayoutAccount.insured_person_id == person_id)


def account_view(row: PayoutAccount | None) -> dict | None:
    if row is None:
        return None
    return {"account_id": str(row.id), "version": row.version, "clearing_number": row.clearing_number,
            "account_number": mask(row.account_number), "bank_name": row.bank_name, "verified": row.verified,
            "verification_method": row.verification_method}


# --- betalningsläget per anspråk ------------------------------------------------------------------


@dataclass(frozen=True)
class LineState:
    line: PayoutOrderLine
    order: PayoutOrder
    file: PayoutFile
    outcome: str | None

    @property
    def state(self) -> str:
        if self.file.status == "superseded":
            return "withdrawn"
        if self.file.status == "prepared":
            return "bank_prepared"
        return {None: "sent", "executed": "paid"}.get(self.outcome, self.outcome)


def _last_outcomes(session: Session, order_ids) -> dict[uuid.UUID, str]:
    order_ids = list(order_ids)
    out: dict[uuid.UUID, str] = {}
    if not order_ids:
        return out
    for r in session.scalars(select(PayoutReceipt).where(PayoutReceipt.order_id.in_(order_ids))
                             .order_by(PayoutReceipt.order_id, PayoutReceipt.sequence)):
        out[r.order_id] = r.outcome
    return out


def line_states(session: Session, claim_ids=None) -> dict[uuid.UUID, list[LineState]]:
    """Försöken per anspråk i ordning, med filens läge och bankens senaste utfall."""
    query = (select(PayoutOrderLine, PayoutOrder, PayoutFile).join(PayoutOrder, PayoutOrder.id == PayoutOrderLine.order_id)
             .join(PayoutFile, PayoutFile.id == PayoutOrder.file_id))
    if claim_ids is not None:
        claim_ids = list(claim_ids)
        if not claim_ids:
            return {}
        query = query.where(PayoutOrderLine.claim_id.in_(claim_ids))
    rows = session.execute(query.order_by(PayoutOrderLine.claim_id, PayoutOrderLine.attempt)).all()
    outcomes = _last_outcomes(session, {o.id for _, o, _ in rows})
    out: dict[uuid.UUID, list[LineState]] = defaultdict(list)
    for line, order, file in rows:
        out[line.claim_id].append(LineState(line, order, file, outcomes.get(order.id)))
    return out


def claim_state(claim: PensionClaim, remaining_unfunded: Decimal, lines: list[LineState]) -> str:
    """Anspråkets betalningsläge (§4): ej finansierat, finansierat eller senaste försökets läge."""
    active = [s for s in lines if s.state != "withdrawn"]
    if active:
        return active[-1].state
    return "unfunded" if remaining_unfunded > 0 else "funded"


# --- bankfilen (X2, X3, X7) -----------------------------------------------------------------------


def earliest_execution(today: date) -> date:
    return next_bank_day(today)


def _lump_sum(claim: PensionClaim, execution: date) -> bool:
    """Engångsbelopp: rätten gäller en tidigare månad än månaden före utförandet (PR-ITP1-026 p. 6)."""
    return claim.right_month < aa.add_months(execution.replace(day=1), -1)


def _year_window(year: int) -> list[date]:
    """Rättighetsmånaderna vars betalningsdag normalt ligger i året: december året före till november."""
    month, out = date(year - 1, 12, 1), []
    while month <= date(year, 11, 1):
        out.append(month)
        month = aa.add_months(month, 1)
    return out


def expected_year_total(session: Session, person_parts: list[uuid.UUID], year: int, *,
                        pending: list[PensionClaim]) -> Decimal:
    """Förväntad årssumma från bolaget till personen (X3): verkställt i året, obetalda rätter med betalningsdag i
    året och återstående rätter i året enligt gällande plan och beslutat M, över alla personens delar."""
    total = ZERO
    claims = list(session.scalars(select(PensionClaim).where(PensionClaim.payout_part_id.in_(person_parts))))
    states = line_states(session, [c.id for c in claims])
    pending_ids = {c.id for c in pending}
    last_month: dict[uuid.UUID, date] = {}
    for c in claims:
        last_month[c.payout_part_id] = max(last_month.get(c.payout_part_id, c.right_month), c.right_month)
        active = [s for s in states.get(c.id, []) if s.state != "withdrawn"]
        if active and active[-1].state == "paid":
            if active[-1].file.execution_date.year == year:
                total += c.gross_sek
        elif c.id in pending_ids or c.payment_day.year == year:
            total += c.gross_sek
    plans = pl.plans_in_force(session, person_parts, date(year, 11, 1))
    amounts = pc.amounts_by_part(session, person_parts, date(year, 11, 1))
    for part, plan in plans.items():
        schedule = pl.schedule_of(plan)
        m = amounts[part].m_sek if part in amounts else Decimal(plan.content["amount"]["m_sek"])
        for month in _year_window(year):
            if month > last_month.get(part, date.min) and schedule.has_right(month):
                total += m
    return total.quantize(Decimal("0.01"))


@dataclass
class FilePlan:
    """Den beräknade bankfilen: uppdrag per person, blockerade personer och ärenden att öppna."""

    payment_day: date
    execution_date: date
    orders: list[dict]
    blocked: list[dict]
    cases: list[dict]
    logical_checksum: str

    def summary(self) -> dict:
        gross = sum((Decimal(o["gross_sek"]) for o in self.orders), ZERO)
        tax = sum((Decimal(o["tax_sek"]) for o in self.orders), ZERO)
        return {"payment_day": self.payment_day.isoformat(), "execution_date": self.execution_date.isoformat(),
                "delayed": self.execution_date > self.payment_day, "orders": len(self.orders),
                "lines": sum(len(o["lines"]) for o in self.orders), "gross_sek": str(gross), "tax_sek": str(tax),
                "net_sek": str(gross - tax), "blocked": self.blocked}


def _payable(session: Session, payment_day: date) -> list[tuple[PensionClaim, list[LineState]]]:
    """Betalbara anspråk med betalningsdag senast dagen (X2) och deras tidigare försök. Ett återfört anspråk efter
    dödsmånaden (steg 7, Y5) är inte betalbart."""
    claims = list(session.scalars(pc.not_reversed(session, select(PensionClaim).where(PensionClaim.payment_day <= payment_day))
                                  .order_by(PensionClaim.right_month, PensionClaim.payout_part_id)))
    later = pc.funded_later(session, [c.id for c in claims])
    states = line_states(session, [c.id for c in claims])
    payable = []
    for c in claims:
        if c.unfunded_sek - later.get(c.id, ZERO) > 0:  # W8: inga bankuppdrag för det ej finansierade
            continue
        # Försök i en förberedd fil räknas som tillbakadragna: den nya filen ersätter den
        active = [s for s in states.get(c.id, []) if s.state not in ("withdrawn", "bank_prepared")]
        if active and active[-1].state in ("paid", "sent", "unknown"):
            continue
        payable.append((c, active))
    return payable


def build_file(session: Session, payment_day: date, today: date) -> FilePlan:
    """Bankfilen för betalningsdagen: uppdrag per person med skatt, och blockerade personer med skäl (X7)."""
    _require(session)
    execution = max(payment_day, earliest_execution(today))
    payable = _payable(session, payment_day)
    owners = pl.owners(session, {c.payout_part_id for c, _ in payable})
    by_person: dict[uuid.UUID, list[tuple[PensionClaim, list[LineState]]]] = defaultdict(list)
    for c, active in payable:
        by_person[owners[c.payout_part_id].person_id].append((c, active))
    orders, blocked, cases = [], [], []
    year = execution.year
    reports = dr.current_reports(session, by_person) if dr.deaths_present(session) else {}
    for person_id in sorted(by_person, key=str):
        items = by_person[person_id]
        status = next(owners[c.payout_part_id].status for c, _ in items)
        base = {"person_id": str(person_id), "claims": [str(c.id) for c, _ in items]}
        report = reports.get(person_id)
        if report is not None and report.status == "suspected":  # steg 7: misstänkt dödsfall stoppar (Y3)
            blocked.append({**base, "reason": "death_suspected"})
            continue
        if report is not None and report.status == "verified":  # steg 7: dödsboet (Y10)
            order = _estate_order(session, person_id, report, items, execution, year, base, blocked, cases)
            if order is not None:
                orders.append(order)
            continue
        if status == "deceased":  # avliden utan verifierat besked (steg 7: register_death_report)
            blocked.append({**base, "reason": "deceased"})
            continue
        account = current_account(session, person_id)
        after_rejection = [c for c, active in items if active and active[-1].state in RETRY_STATES
                           and active[-1].order.account_id == (account.id if account else None)]
        if account is None or not account.verified or after_rejection:
            reason = ("account_missing" if account is None else "account_unverified" if not account.verified
                      else "account_after_rejection")
            blocked.append({**base, "reason": reason})
            cases.append({"type": "payout_hindrance", "person_id": person_id, "reason": reason})
            continue
        tax_status = status_for(session, person_id, year, execution)
        if tax_status is None:
            blocked.append({**base, "reason": "tax_status_missing", "tax_year": year})
            cases.append({"type": "tax_status", "person_id": person_id, "reason": "missing", "tax_year": year})
            continue
        gross = sum((c.gross_sek for c, _ in items), ZERO)
        expected = expected_year_total(session, _person_parts(session, person_id), year,
                                       pending=[c for c, _ in items])
        rule = tx.TaxRule(tax_status.kind, tax_status.rate, tax_status.fixed_amount_sek)
        try:
            result = tx.withholding(gross, rule, expected)
        except tx.TaxBlocked as exc:
            blocked.append({**base, "reason": f"tax_{exc.reason}", "tax_year": year})
            cases.append({"type": "tax_status", "person_id": person_id, "reason": exc.reason, "tax_year": year})
            continue
        lines = [{"claim_id": str(c.id), "payout_part_id": str(c.payout_part_id),
                  "right_month": c.right_month.isoformat(), "gross_sek": str(c.gross_sek),
                  "lump_sum": _lump_sum(c, execution)}
                 for c, _ in items]
        orders.append({"person_id": str(person_id), "account_id": str(account.id),
                       "tax_status_id": str(tax_status.id), "tax_year": year, **result.plain(), "lines": lines,
                       "lump_sum_sek": str(sum((c.gross_sek for c, _ in items if _lump_sum(c, execution)), ZERO))})
    logical = {"method": METHOD, "payment_day": payment_day.isoformat(), "execution_date": execution.isoformat(),
               "orders": orders}
    return FilePlan(payment_day, execution, orders, blocked, cases, content_checksum(logical))


def _estate_order(session: Session, person_id: uuid.UUID, report, items: list, execution: date, year: int, base: dict,
                  blocked: list, cases: list) -> dict | None:
    """Uppdraget till dödsboet (Y10): bara anspråk med rätt senast dödsmånaden, när delarna är avräknade och
    behörigheten och kontot är verifierade. Skatten är 30 % eller beslutet, utan gränserna för småbelopp."""
    death_month = report.death_date.replace(day=1)
    items = [(c, active) for c, active in items if c.right_month <= death_month]  # efter D: återförs i stängningen
    if not items:
        return None
    base = {**base, "claims": [str(c.id) for c, _ in items]}
    estate, account = dr.estate_for_payment(session, person_id)
    if estate is None or not dr.person_settled(session, person_id):
        blocked.append({**base, "reason": "estate_missing"})
        return None
    if any(active and active[-1].state in RETRY_STATES and active[-1].order.account_id == account.id
           for _, active in items):
        blocked.append({**base, "reason": "account_after_rejection"})
        return None
    tax_status = status_for(session, person_id, year, execution)
    if tax_status is None:
        blocked.append({**base, "reason": "tax_status_missing", "tax_year": year})
        cases.append({"type": "tax_status", "person_id": person_id, "reason": "missing", "tax_year": year})
        return None
    gross = sum((c.gross_sek for c, _ in items), ZERO)
    rule = tx.TaxRule(tax_status.kind, tax_status.rate, tax_status.fixed_amount_sek)
    try:
        result = tx.withholding(gross, rule, ZERO, thresholds=False)
    except tx.TaxBlocked as exc:
        blocked.append({**base, "reason": f"tax_{exc.reason}", "tax_year": year})
        cases.append({"type": "tax_status", "person_id": person_id, "reason": exc.reason, "tax_year": year})
        return None
    lines = [{"claim_id": str(c.id), "payout_part_id": str(c.payout_part_id), "right_month": c.right_month.isoformat(),
              "gross_sek": str(c.gross_sek), "lump_sum": _lump_sum(c, execution)} for c, _ in items]
    # Underlaget för kontrolluppgiften märks som dödsbo (Y10, projekt 6)
    return {"person_id": str(person_id), "account_id": str(account.id), "tax_status_id": str(tax_status.id),
            "tax_year": year, **result.plain(), "lines": lines,
            "lump_sum_sek": str(sum((c.gross_sek for c, _ in items if _lump_sum(c, execution)), ZERO)),
            "estate": True, "estate_authority_id": str(estate.id)}


def _person_parts(session: Session, person_id: uuid.UUID) -> list[uuid.UUID]:
    return sorted(session.scalars(select(PayoutPart.id).join(PolicyBenefit, PolicyBenefit.id == PayoutPart.benefit_id)
                                  .join(Policy, Policy.id == PolicyBenefit.policy_id)
                                  .where(Policy.insured_person_id == person_id)), key=str)


def current_prepared(session: Session) -> PayoutFile | None:
    return session.scalar(select(PayoutFile).where(PayoutFile.status == "prepared").limit(1))


def _open_cases(session: Session, cases: list[dict], today: date, actor: str) -> list[str]:
    """Ett ärende `payout_hindrance` per person och öppet hinder, ett `tax_status` per person och år (X5, X6)."""
    opened = []
    for spec in cases:
        person_id, kind = spec["person_id"], spec["type"]
        existing = session.scalars(select(Case).where(Case.case_type == kind, Case.insured_person_id == person_id)).all()
        if kind == "tax_status" and any(c.details.get("tax_year") == spec["tax_year"]
                                        and c.details.get("reason") == spec["reason"] for c in existing):
            continue
        if kind == "payout_hindrance" and any(c.status != "closed" for c in existing):
            continue
        details = {"reason": spec["reason"], **({"tax_year": spec["tax_year"]} if "tax_year" in spec else {}),
                   **{k: v for k, v in spec.items() if k in ("order_reference", "receipt_id")},
                   "text": _CASE_TEXT[spec["reason"]]}
        case = Case(id=uuid.uuid4(), case_number=pl.next_case_number(session), case_type=kind, status="open",
                    insured_person_id=person_id, channel="system", received_date=today,
                    source_reference=f"{kind}:{spec['reason']}", details=details, created_by=actor)
        session.add(case)
        session.flush()
        opened.append(case.case_number)
    return opened


_CASE_TEXT = {
    "account_missing": "Konto saknas – skulden står kvar; ingen paus eller uppskov (PR-ITP1-026)",
    "account_unverified": "Kontot är inte verifierat – skulden står kvar; ingen paus eller uppskov (PR-ITP1-026)",
    "account_after_rejection": "Banken avvisade eller returnerade betalningen – nytt verifierat konto krävs före "
                               "nytt försök med samma anspråk (PR-ITP1-026)",
    "bank_rejected": "Banken avvisade betalningen – skulden står kvar; nytt försök när kontot verifierats",
    "bank_returned": "Betalningen kom tillbaka – skulden är öppen igen; nytt försök när kontot verifierats",
    "missing": "Skattestatus saknas för utbetalningsdagens år – betalningen blockeras, aldrig ett antagande (PB7)",
    "table_missing": "Huvudinkomst kräver skattetabell för året – betalningen blockeras med skulden kvar (X4)",
}


def create_file(session: Session, payment_day: date, today: date, actor: str) -> tuple[PayoutFile | None, dict, bool]:
    """Skapar bankfilen (X7): samma underlag som den förberedda filen ger den filen igen; annars ersätts den."""
    plan = build_file(session, payment_day, today)
    opened = _open_cases(session, plan.cases, today, actor)
    summary = {**plan.summary(), "cases_opened": opened}
    prepared = current_prepared(session)
    if prepared is not None and prepared.content["logical_checksum"] == plan.logical_checksum:
        return prepared, summary, False
    if not plan.orders:
        if prepared is not None:  # underlaget har ändrats och inget är betalbart: den förberedda filen dras tillbaka
            prepared.status = "superseded"
        return None, summary, False
    if prepared is not None:
        prepared.status = "superseded"
        session.flush()
    previous = dict(session.execute(select(PayoutOrderLine.claim_id, func.max(PayoutOrderLine.attempt))
                                    .where(PayoutOrderLine.claim_id.in_(
                                        [uuid.UUID(line["claim_id"]) for o in plan.orders for line in o["lines"]]))
                                    .group_by(PayoutOrderLine.claim_id)).all())
    # Försöksnumret står utanför den logiska kontrollsumman: en ersatt fils rader räknas som försök
    orders = [{**o, "lines": [{**line, "attempt": previous.get(uuid.UUID(line["claim_id"]), 0) + 1}
                               for line in o["lines"]]} for o in plan.orders]
    content = {"method": METHOD, "design": "P1-PENSION-001 §8.2–8.3, X1–X9", "rules": ["PR-ITP1-026"],
               "payment_day": payment_day.isoformat(), "execution_date": plan.execution_date.isoformat(),
               "logical_checksum": plan.logical_checksum, "supersedes": str(prepared.id) if prepared else None,
               "orders": orders, "summary": {k: v for k, v in summary.items() if k != "cases_opened"}}
    digest = content_checksum(content)
    file = PayoutFile(id=_stable("file", digest), file_reference=f"PAY-{plan.execution_date:%Y%m%d}-{digest[:8]}",
                      payment_day=payment_day, execution_date=plan.execution_date, status="prepared",
                      supersedes_id=prepared.id if prepared else None, content=content, checksum=digest,
                      created_by=actor)
    session.add(file)
    session.flush()
    for o in orders:
        order_id = _stable("order", digest, o["person_id"])
        session.add(PayoutOrder(id=order_id, file_id=file.id, insured_person_id=uuid.UUID(o["person_id"]),
                                account_id=uuid.UUID(o["account_id"]), tax_status_id=uuid.UUID(o["tax_status_id"]),
                                tax_year=o["tax_year"], reference=f"PO{plan.execution_date:%y%m%d}{order_id.hex[:12].upper()}",
                                gross_sek=Decimal(o["gross_sek"]), tax_sek=Decimal(o["tax_sek"]),
                                net_sek=Decimal(o["net_sek"]), tax_method=o["tax_method"],
                                content={k: v for k, v in o.items() if k != "lines"}, created_by=actor))
        session.flush()
        for line in o["lines"]:
            session.add(PayoutOrderLine(id=_stable("line", order_id, line["claim_id"]), order_id=order_id,
                                        claim_id=uuid.UUID(line["claim_id"]),
                                        payout_part_id=uuid.UUID(line["payout_part_id"]), attempt=line["attempt"],
                                        gross_sek=Decimal(line["gross_sek"]), lump_sum=line["lump_sum"],
                                        created_by=actor))
    session.flush()
    return file, summary, True


def bank_payload(session: Session, file: PayoutFile) -> dict:
    """Bankfilen som den lämnas till banken: utförandedag, referens, konto och nettobelopp per uppdrag."""
    orders = session.scalars(select(PayoutOrder).where(PayoutOrder.file_id == file.id)
                             .order_by(PayoutOrder.reference)).all()
    accounts = {a.id: a for a in session.scalars(select(PayoutAccount).where(
        PayoutAccount.id.in_([o.account_id for o in orders])))} if orders else {}
    return {"file_reference": file.file_reference, "execution_date": file.execution_date.isoformat(),
            "checksum": file.checksum, "currency": "SEK",
            "orders": [{"reference": o.reference, "clearing_number": accounts[o.account_id].clearing_number,
                        "account_number": accounts[o.account_id].account_number,
                        "bank_name": accounts[o.account_id].bank_name, "amount_sek": str(o.net_sek)}
                       for o in orders]}


def approve_file(session: Session, file_id: uuid.UUID, reviewed_checksum: str, today: date, actor: str) -> dict:
    """Godkänner bankfilen hashbundet (X7). Ändrat underlag sedan filen skapades ger konflikt."""
    _require(session)
    file = session.get(PayoutFile, file_id)
    if file is None:
        raise OrderServiceError(f"Bankfilen {file_id} finns inte")
    if file.status == "approved":
        if file.checksum != reviewed_checksum:
            raise OrderConflict("Bankfilen är redan godkänd med en annan kontrollsumma")
        return {"file_reference": file.file_reference, "created": False, "bank_file": bank_payload(session, file)}
    if file.status != "prepared":
        raise OrderConflict("Bankfilen är ersatt av en nyare fil – granska och godkänn den i stället")
    if file.checksum != reviewed_checksum:
        raise OrderConflict("Kontrollsumman stämmer inte med bankfilen – granska filen igen")
    plan = build_file(session, file.payment_day, today)
    if plan.logical_checksum != file.content["logical_checksum"] or plan.execution_date != file.execution_date:
        raise OrderConflict("Underlaget har ändrats sedan bankfilen skapades (konto, skatt, anspråk eller "
                            "utförandedag) – skapa filen igen")
    file.status, file.approved_by, file.approved_at = "approved", actor, datetime.now(UTC)
    session.flush()
    return {"file_reference": file.file_reference, "created": True, "bank_file": bank_payload(session, file)}


# --- kvitton och journalen (X8, X9) ---------------------------------------------------------------


def receipt_content(receipt: dict) -> dict:
    return {"receipt_id": receipt["receipt_id"], "reference": receipt["reference"], "outcome": receipt["outcome"],
            "bank_date": str(receipt["bank_date"]), "reason_code": receipt.get("reason_code")}


def receipt_file_checksum(source_system: str, file_reference: str, receipts: list[dict]) -> str:
    """Kontrollsumman över kvittofilens innehåll, som bankens fil bär (samma mönster som `bank_file_checksum`)."""
    return content_checksum({"source_system": source_system, "file_reference": file_reference,
                             "receipts": [receipt_content(r) for r in receipts]})


def import_receipts(session: Session, source_system: str, file_reference: str, receipts: list[dict],
                    file_checksum: str, today: date, actor: str) -> dict:
    """Läser bankens kvittofil idempotent (X8) och bokar utförda och återkomna betalningar (X9)."""
    _require(session)
    if receipt_file_checksum(source_system, file_reference, receipts) != file_checksum:
        raise OrderServiceError("Kvittofilens kontrollsumma stämmer inte med innehållet – filen läses inte")
    ids = [r["receipt_id"] for r in receipts]
    if len(set(ids)) != len(ids):
        raise OrderServiceError("Samma kvitto-id förekommer flera gånger i filen")
    if any(r["bank_date"] > today for r in receipts):
        raise OrderServiceError("Ett kvitto har bankdag i framtiden")
    outcomes, new = [], []
    last: dict[uuid.UUID, str | None] = {}
    counts: dict[uuid.UUID, int] = {}
    for r in receipts:
        digest = content_checksum(receipt_content(r))
        existing = session.scalar(select(PayoutReceipt).where(PayoutReceipt.source_system == source_system,
                                                              PayoutReceipt.receipt_id == r["receipt_id"]))
        if existing is not None:
            if existing.content_checksum != digest:
                raise OrderConflict(f"Kvittot {r['receipt_id']} är redan inläst med annat innehåll – ingenting i "
                                    "filen är registrerat")
            outcomes.append({"receipt_id": r["receipt_id"], "status": "already_received"})
            continue
        order = session.scalar(select(PayoutOrder).where(PayoutOrder.reference == r["reference"]))
        if order is None:
            raise OrderConflict(f"Kvittot {r['receipt_id']} gäller okänt uppdrag {r['reference']}")
        if session.get(PayoutFile, order.file_id).status != "approved":
            raise OrderConflict(f"Uppdraget {r['reference']} är inte godkänt och skickat")
        if order.id not in last:
            history = session.scalars(select(PayoutReceipt).where(PayoutReceipt.order_id == order.id)
                                      .order_by(PayoutReceipt.sequence)).all()
            last[order.id] = history[-1].outcome if history else None
            counts[order.id] = len(history)
        if r["outcome"] not in TRANSITIONS.get(last[order.id], set()):
            raise OrderConflict(f"Uppdraget {r['reference']} kan inte gå från {last[order.id] or 'skickat'} till "
                                f"{r['outcome']} – ingenting i filen är registrerat")
        last[order.id] = r["outcome"]
        counts[order.id] += 1
        new.append((r, order, digest, counts[order.id]))
        outcomes.append({"receipt_id": r["receipt_id"], "status": "new", "outcome": r["outcome"],
                         "reference": r["reference"]})
    settle = [(r, o, seq) for r, o, _, seq in new if r["outcome"] in ("executed", "returned")]
    batch = _settle(session, source_system, file_reference, file_checksum, settle, actor) if settle else None
    cases = []
    for r, order, digest, sequence in new:
        session.add(PayoutReceipt(id=_stable("receipt", source_system, r["receipt_id"]), source_system=source_system,
                                  receipt_id=r["receipt_id"], file_reference=file_reference,
                                  file_checksum=file_checksum, content_checksum=digest, order_id=order.id,
                                  outcome=r["outcome"], bank_date=r["bank_date"], reason_code=r.get("reason_code"),
                                  sequence=sequence,
                                  settlement_batch_id=batch.id if batch and r["outcome"] in ("executed", "returned")
                                  else None, created_by=actor))
        if r["outcome"] in RETRY_STATES:
            cases.append({"type": "payout_hindrance", "person_id": order.insured_person_id,
                          "reason": f"bank_{r['outcome']}", "order_reference": order.reference,
                          "receipt_id": r["receipt_id"]})
    session.flush()
    opened = _open_cases(session, cases, today, actor)
    return {"file_reference": file_reference, "receipts": len(receipts), "new": len(new),
            "already_received": len(receipts) - len(new), "outcomes": outcomes, "cases_opened": opened,
            "settlement": {"batch_id": str(batch.id), **batch.content["totals"], "month": batch.content["month"]}
            if batch else None}


def _settle(session: Session, source_system: str, file_reference: str, file_checksum: str,
            settle: list[tuple[dict, PayoutOrder, int]], actor: str) -> LedgerBatch:
    """Verifikationen `payout_settlement` för kvittofilens utförda och återkomna betalningar (X9)."""
    month = pc.first_open_month(session)
    batch_id = cl.stable_id(SETTLEMENT_KIND, file_checksum)
    liability = pc.liability_by_part(session, month)
    tax_balance = pc.account_balance(session, TAX_LIABILITY, month)
    entries, rows = [], []
    totals = {"executed": 0, "returned": 0, "paid_gross_sek": ZERO, "returned_gross_sek": ZERO,
              "withholding_sek": ZERO, "withholding_returned_sek": ZERO, "net_sek": ZERO}
    for r, order, _ in sorted(settle, key=lambda x: (x[1].reference, x[2])):
        lines = session.scalars(select(PayoutOrderLine).where(PayoutOrderLine.order_id == order.id)
                                .order_by(PayoutOrderLine.claim_id)).all()
        executed = r["outcome"] == "executed"
        sign = Decimal(-1) if executed else Decimal(1)
        reason = PAYOUT if executed else RETURNED
        for line in lines:
            before = liability.get(line.payout_part_id, ZERO)
            amount = sign * line.gross_sek
            entries.append(LedgerCapitalEntry(
                id=cl.stable_id(SETTLEMENT_KIND, str(batch_id), str(line.id), r["receipt_id"]), batch_id=batch_id,
                account=pc.LIABILITY, payout_part_id=line.payout_part_id, origin_id=None, month=month, reason=reason,
                amount_sek=amount, balance_before_sek=before, balance_after_sek=before + amount, source="ledger",
                created_by=actor))
            liability[line.payout_part_id] = before + amount
        if order.tax_sek:
            amount = -sign * order.tax_sek
            entries.append(LedgerCapitalEntry(
                id=cl.stable_id(SETTLEMENT_KIND, str(batch_id), str(order.id), r["receipt_id"], "tax"),
                batch_id=batch_id, account=TAX_LIABILITY, payout_part_id=None, origin_id=None, month=month,
                reason=WITHHOLDING if executed else RETURNED, amount_sek=amount, balance_before_sek=tax_balance,
                balance_after_sek=tax_balance + amount, source="ledger", created_by=actor))
            tax_balance += amount
        key = "executed" if executed else "returned"
        totals[key] += 1
        totals["paid_gross_sek" if executed else "returned_gross_sek"] += order.gross_sek
        totals["withholding_sek" if executed else "withholding_returned_sek"] += order.tax_sek
        totals["net_sek"] += -sign * order.net_sek
        rows.append({"receipt_id": r["receipt_id"], "reference": order.reference, "outcome": r["outcome"],
                     "bank_date": str(r["bank_date"]), "gross_sek": str(order.gross_sek),
                     "tax_sek": str(order.tax_sek), "net_sek": str(order.net_sek), "lines": len(lines)})
    content = {"method": METHOD, "kind": SETTLEMENT_KIND, "design": "P1-PENSION-001 §8.3, X9",
               "rules": ["PR-ITP1-026"], "source_system": source_system, "file_reference": file_reference,
               "file_checksum": file_checksum, "month": month.isoformat(), "receipts": rows,
               "totals": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in totals.items()},
               "entries": len(entries)}
    batch = LedgerBatch(id=batch_id, kind=SETTLEMENT_KIND, period_end=month_end(month), source="ledger",
                        extract_id=None, extract_checksum=None, content=content,
                        checksum=content_checksum(content), created_by=actor)
    session.add(batch)
    session.flush()
    session.add_all(entries)
    session.flush()
    return batch


def settlements_in(session: Session, month: date) -> dict:
    """Månadens utbetalningar ur verifikationerna `payout_settlement`, för stängningens kontroll (X10)."""
    month = month.replace(day=1)
    batches = session.scalars(select(LedgerBatch).where(LedgerBatch.kind == SETTLEMENT_KIND,
                                                        LedgerBatch.period_end == month_end(month))).all()
    totals = defaultdict(lambda: ZERO)
    for b in batches:
        for k in ("paid_gross_sek", "returned_gross_sek", "withholding_sek", "withholding_returned_sek", "net_sek"):
            totals[k] += Decimal(b.content["totals"][k])
    rows = session.execute(select(LedgerCapitalEntry.account, func.sum(LedgerCapitalEntry.amount_sek))
                           .where(LedgerCapitalEntry.batch_id.in_([b.id for b in batches]))
                           .group_by(LedgerCapitalEntry.account)).all() if batches else []
    sums = {account: Decimal(str(total)).quantize(Decimal("0.01")) for account, total in rows}
    return {"batches": len(batches), "liability_sek": sums.get(pc.LIABILITY, ZERO),
            "tax_liability_sek": sums.get(TAX_LIABILITY, ZERO), **{k: totals[k] for k in (
                "paid_gross_sek", "returned_gross_sek", "withholding_sek", "withholding_returned_sek", "net_sek")}}


# --- läsning --------------------------------------------------------------------------------------


def files_view(session: Session, *, file_id: uuid.UUID | None = None) -> list[dict]:
    """Bankfilerna med uppdrag, maskerade konton, rader, försök och bankens utfall."""
    query = select(PayoutFile).order_by(PayoutFile.created_at, PayoutFile.id)
    if file_id is not None:
        query = query.where(PayoutFile.id == file_id)
    out = []
    for file in session.scalars(query):
        orders = session.scalars(select(PayoutOrder).where(PayoutOrder.file_id == file.id)
                                 .order_by(PayoutOrder.reference)).all()
        outcomes = _last_outcomes(session, [o.id for o in orders])
        items = []
        for o in orders:
            lines = session.scalars(select(PayoutOrderLine).where(PayoutOrderLine.order_id == o.id)
                                    .order_by(PayoutOrderLine.claim_id)).all()
            items.append({"reference": o.reference, "person_id": str(o.insured_person_id),
                          "account": account_view(session.get(PayoutAccount, o.account_id)),
                          "tax_year": o.tax_year, "tax_kind": o.content.get("tax_kind"), "tax_method": o.tax_method,
                          "expected_year_total_sek": o.content.get("expected_year_total_sek"), "gross_sek": str(o.gross_sek),
                          "tax_sek": str(o.tax_sek), "net_sek": str(o.net_sek),
                          "outcome": outcomes.get(o.id),
                          "lines": [{"claim_id": str(x.claim_id), "payout_part_id": str(x.payout_part_id),
                                     "attempt": x.attempt, "gross_sek": str(x.gross_sek), "lump_sum": x.lump_sum}
                                    for x in lines]})
        out.append({"file_id": str(file.id), "file_reference": file.file_reference,
                    "payment_day": file.payment_day.isoformat(), "execution_date": file.execution_date.isoformat(),
                    "status": file.status, "checksum": file.checksum, "approved_by": file.approved_by,
                    "summary": file.content["summary"], "orders": items})
    return out


def claims_payment_view(session: Session, month: date | None = None) -> list[dict]:
    """Varje anspråks betalningsläge (§4) och försök, utan att anspråket ändras."""
    query = select(PensionClaim).order_by(PensionClaim.right_month, PensionClaim.payout_part_id)
    if month is not None:
        query = query.where(PensionClaim.right_month == month.replace(day=1))
    claims = list(session.scalars(query))
    later = pc.funded_later(session, [c.id for c in claims])
    states = line_states(session, [c.id for c in claims])
    return [{"claim_id": str(c.id), "payout_part_id": str(c.payout_part_id), "right_month": c.right_month.isoformat(),
             "gross_sek": str(c.gross_sek), "payment_day": c.payment_day.isoformat(),
             "state": claim_state(c, c.unfunded_sek - later.get(c.id, ZERO), states.get(c.id, [])),
             "attempts": [{"attempt": s.line.attempt, "reference": s.order.reference, "state": s.state}
                          for s in states.get(c.id, [])]} for c in claims]


__all__ = ["METHOD", "ORDER_TABLES", "SETTLEMENT_KIND", "TAX_LIABILITY", "FilePlan", "LineState", "OrderConflict",
           "OrderServiceError", "account_view", "approve_file", "bank_payload", "build_file", "claim_state",
           "claims_payment_view", "create_file", "current_account", "current_prepared", "expected_year_total",
           "files_view", "import_receipts", "line_states", "mask", "orders_present", "receipt_file_checksum",
           "register_account", "register_tax_status", "settlements_in", "status_for"]
