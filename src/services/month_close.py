"""Månadsstängning för sparandet i den operativa kapital- och garantijournalen (paket B steg 3, B-047 punkt 3).

Beslutat i P1-PENSION-001 §7 (PB5) med Karls val S1–S7 2026-11-19. En körning per månad för hela
kollektivet, i PR-ITP1-020:s ordning och med samma värderingsversion genom alla steg. Steg 3 omfattar
sparandet: stegen 1–4 och 8. Månadsrätt, dödsfall och arvsvinst (steg 5–7) byggs i paket B steg 5 och 7.

| Steg | Innehåll | Här |
|---|---|---|
| 1 | Öppningskapital per kapitalspår och uttagsdel; levandestatus och uttagslägen | `tracks` per föregående månadsslut; startad del med kapital eller registrerat dödsfall blockerar (S4) |
| 2 | Avkastning på öppningskapitalet enligt antagen AVK för månaden (PR-021) | `roll_origins` / `close_month` |
| 3 | Kapitalavgift och skattebelastning på öppningsbasen (PR-022, PR-023) | `roll_origins` / `close_month` |
| 4 | Månadens mottagna nettopremier vid månadsslut, med garantidel, utan avkastning denna månad | `ledger_premiums.premium_intake` |
| 8 | Stäng och stäm av kundkapital och garanti; underlag för nästa månad | Kontrollposter i `ledger_controls` |

**Granskning och bokning (§7.2).** `plan_month` räknar hela stängningen utan att skriva och ger en
sammanställning med granskningssumma: föregående läge, AVK med kontrollsumma, parameterversioner, paket
A:s premier (stoppunkten), poster per steg och kontroller. `apply_month` binder summan och skriver allt i
en transaktion med ett transaktionsbundet lås. Ändrat underlag mellan granskning och bokning ger konflikt.
Samma innehåll igen ger ingen ny effekt.

**Rättelse (Karls val S2–S3).** En stängd månad ändras aldrig. Räknas månaden om och ger andra belopp –
ändrad AVK eller parameterversion för månaden – blir det en ny verifikation `month_correction` som pekar
på den version den ersätter, med motposter som nettodifferens per kapitalspår och orsak. Garantidelarna
ändras inte. Bara den senast stängda månaden kan rättas. En redan bokad premie som ändrats i paket A
blockerar (återtag är ett senare steg). Sena registreringar bokas i nästa öppna månad, inte som rättelse.

**Blockeras:** journalen eller steg 3:s migration saknas, månaden har inte tagit slut, föregående månad är
öppen, saknad eller ej antagen AVK för månaden (fall 17), saknad parameterversion, startad uttagsdel med
kapital, registrerat dödsfall och en kontroll som inte går ihop. En blockerad månad skapar inga poster.

**66-årsmånaden (Karls val S4).** En ej startad del vars ägare fyllt 66 senast i månaden och saknar plan
stängs för sparandet och redovisas i kontrollposten *standardstart väntar på steg 4*. Startmånaden
flyttas aldrig tyst; rätten räknas fram när steg 4 finns (PR-ITP1-025).

Avgift och skatt som inte kan dras (C för litet) avstås och redovisas bara i sammanställningen;
bolagskontot kommer i steg 5. Ren beräkning: `compute_month` (fall 13).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analytics.portfolio_snapshot import birth_date
from models import (
    InsuredPerson,
    LedgerBatch,
    LedgerCapitalEntry,
    LedgerControl,
    LedgerGuaranteePart,
    PaymentAllocation,
    PayoutPart,
    Policy,
    PolicyBenefit,
)
from services import capital_ledger as cl
from services import parameters
from services import valuation_bases as vb
from services.capital_ledger import (
    CLOSE_KIND,
    CORRECTION_KIND,
    CUSTOMER,
    Control,
    LedgerError,
    stable_id,
)
from services.errors import ServiceError
from services.ledger_premiums import IntakeError, PremiumAddition, premium_intake
from services.payout_parts import receiving_parts
from services.valuation_extract import ExtractError, _returns, month_end
from skills.calculation import actuarial_annuity as aa
from skills.calculation.premium_origin_ledger import (
    Origin,
    origin_code_version,
    roll_origins,
)

METHOD = "month-close-1"
LEDGER = "ledger"
ZERO = Decimal("0.00")
#: Kapitalpostens orsaker i stegens ordning (PR-020 steg 2–4)
REASONS = ("return", "fee", "tax", "premium")
#: Transaktionsbundet lås för alla stängningar och rättelser: en åt gången
LOCK = (6048, 0)
PENSION_AGE = 66


class CloseError(LedgerError):
    """Månaden kan inte stängas eller rättas, t.ex. saknad AVK eller öppen föregående månad."""


class CloseConflict(CloseError):
    """Granskningssumman stämmer inte: underlaget har ändrats sedan granskningen."""


@dataclass
class MonthPlan:
    """Granskningsunderlaget: vad stängningen eller rättelsen skulle skriva, kontrollerna och summan."""

    month: date
    period_end: date
    #: `open` → stängning, `correction` → rättelse, `closed` → stängd och oförändrad (inget att skriva)
    status: str
    content: dict
    checksum: str
    guarantee_rows: list[dict] = field(default_factory=list)
    entry_rows: list[dict] = field(default_factory=list)
    controls: list[Control] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    supersedes: LedgerBatch | None = None
    version: int = 1

    @property
    def kind(self) -> str:
        return CORRECTION_KIND if self.status == "correction" else CLOSE_KIND

    @property
    def passed(self) -> bool:
        return not self.problems and all(c.passed for c in self.controls)

    def summary(self) -> dict:
        return {**self.content, "status": self.status, "review_checksum": self.checksum, "passed": self.passed,
                "problems": self.problems}


@dataclass(frozen=True)
class Computed:
    """En månads avräkning per kapitalspår: belopp per (spår, orsak), utgående spår och månadens summor."""

    amounts: dict[tuple[str, str], Decimal]
    closing: dict[str, Decimal]
    totals: dict[str, Decimal]


def compute_month(month: date, rate: Decimal, fee_rate: Decimal, tax_rate: Decimal, tracks: list[Origin],
                  additions: list[Origin]) -> Computed:
    """PR-020 steg 2–4 per kapitalspår. `Origin.policy_id` bär uttagsdelen: öresfördelningen sker per del.

    Fall 13: C0 = 100 000,00, r = 1 %, avgift 0,20 % och skattebelastning 0,354 % ger +1 000,00, −16,67 och
    −29,50, alltså C1 = 100 953,83.
    """
    result, entries, closed = roll_origins(month, rate, tracks, additions, fee_rate=fee_rate, tax_rate=tax_rate)
    amounts: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    for e in entries:
        amounts[(e["origin_id"], e["kind"])] += Decimal(e["amount"])
    totals = {"opening_sek": closed.total("opening"), "returns_sek": closed.total("investment_return"),
              "fees_sek": closed.total("fee"), "taxes_sek": closed.total("tax"),
              "fees_waived_sek": closed.total("fee_waived"), "taxes_waived_sek": closed.total("tax_waived"),
              "premiums_sek": closed.total("premiums"), "closing_sek": closed.total("closing")}
    return Computed(dict(amounts), {o.id: o.capital for o in result}, totals)


def _plain(row: dict) -> dict:
    return {k: (str(v) if isinstance(v, (uuid.UUID, Decimal, date)) else v) for k, v in row.items()}


def _owners(session: Session, part_ids) -> dict[uuid.UUID, tuple[date | None, str]]:
    """Uttagsdel → (ägarens födelsedag, personens status). Inga personuppgifter lämnar funktionen."""
    part_ids = list(part_ids)
    out = {}
    for start in range(0, len(part_ids), 5000):
        for part, pnr, status in session.execute(
                select(PayoutPart.id, InsuredPerson.personal_id_number, InsuredPerson.status)
                .join(PolicyBenefit, PolicyBenefit.id == PayoutPart.benefit_id)
                .join(Policy, Policy.id == PolicyBenefit.policy_id)
                .join(InsuredPerson, InsuredPerson.id == Policy.insured_person_id)
                .where(PayoutPart.id.in_(part_ids[start:start + 5000]))):
            out[part] = (birth_date(pnr), status)
    return out


def _benefits(session: Session, part_ids) -> dict[uuid.UUID, uuid.UUID]:
    part_ids = list(part_ids)
    out = {}
    for start in range(0, len(part_ids), 5000):
        out.update(dict(session.execute(select(PayoutPart.id, PayoutPart.benefit_id)
                                        .where(PayoutPart.id.in_(part_ids[start:start + 5000]))).all()))
    return out


def _chain_premiums(session: Session, chain: list[LedgerBatch], month: date) -> list[LedgerGuaranteePart]:
    """Garantidelarna som månadens stängning bokade (version 1 ur paket A)."""
    ids = [b.id for b in chain]
    return list(session.scalars(select(LedgerGuaranteePart).where(
        LedgerGuaranteePart.batch_id.in_(ids), LedgerGuaranteePart.version == 1)
        .order_by(LedgerGuaranteePart.id)))


def _booked_amounts(session: Session, chain: list[LedgerBatch]) -> dict[tuple[str, str], Decimal]:
    """Månadens bokade belopp per (spår, orsak) över stängningen och dess rättelser."""
    rows = session.execute(
        select(LedgerCapitalEntry.origin_id, LedgerCapitalEntry.reason, func.sum(LedgerCapitalEntry.amount_sek))
        .where(LedgerCapitalEntry.batch_id.in_([b.id for b in chain]), LedgerCapitalEntry.account == CUSTOMER)
        .group_by(LedgerCapitalEntry.origin_id, LedgerCapitalEntry.reason)).all()
    return {(str(o), r): Decimal(total).quantize(Decimal("0.01")) for o, r, total in rows}


def plan_month(session: Session, month: date, today: date) -> MonthPlan:
    """Räknar månadens stängning – eller rättelse av en stängd månad – utan att skriva."""
    month = month.replace(day=1)
    end = month_end(month)
    if not cl.month_close_present(session):
        raise CloseError("Månadsstängningen är inte införd i vald databas – migrate_month_close.py först")
    opening = cl.opening_batch(session)
    if opening is None:
        raise CloseError("Kapitaljournalen har inget ingående läge – övergången från S-04 görs först")
    cl.verify_opening(session, opening)
    if end <= opening.period_end:
        raise CloseError(f"{month:%Y-%m} ligger i det ingående läget per {opening.period_end}")
    if today <= end:
        raise CloseError(f"{month:%Y-%m} har inte tagit slut; den kan stängas tidigast "
                         f"{aa.first_month_after(end):%Y-%m-%d}")
    closed = cl.closed_month_ends(session)
    previous_end = month_end(aa.add_months(month, -1))
    if previous_end != opening.period_end and previous_end not in closed:
        raise CloseError(f"Föregående månad {previous_end:%Y-%m} är öppen – månaderna stängs i ordning")
    previous = opening if previous_end == opening.period_end else cl.effective_batch(session, previous_end)
    chain = cl.month_chain(session, end)
    current = chain[-1] if chain else None

    # Steg 2–3: avkastning för månaden ur antagen AVK och månadens parameterversioner (PR-021–023)
    try:
        avk, rates = _returns(session, end, [month])
    except ExtractError as exc:
        raise CloseError(f"{exc}. Stängningen blockeras; inga poster skapas") from exc
    try:
        fee_rate, tax_rate, fee_label, tax_label = parameters.capital_rates(session, [month])[month]
    except ServiceError as exc:
        raise CloseError(str(exc)) from exc
    rate = rates[month]

    # Steg 1: öppningskapitalet per kapitalspår
    opening_tracks = cl.tracks(session, previous_end)
    origins = [Origin(str(t.origin_id), str(t.payout_part_id), t.balance) for t in opening_tracks]

    # Steg 4: månadens premier – vid stängning ur paket A, vid rättelse de redan bokade
    intake_summary, additions_src, booked_parts = None, [], []
    if current is None:
        try:
            intake = premium_intake(session, month)
        except IntakeError as exc:
            raise CloseError(str(exc)) from exc
        intake_summary = {**intake.summary, "checksum": intake.checksum}
        additions_src = intake.additions
    else:
        booked_parts = _chain_premiums(session, chain, month)
        allocations = {a.id: a for a in session.scalars(select(PaymentAllocation).where(
            PaymentAllocation.id.in_([g.payment_allocation_id for g in booked_parts])))}
        changed = [str(g.payment_allocation_id) for g in booked_parts
                   if (a := allocations.get(g.payment_allocation_id)) is None
                   or a.kind != "invoice_line" or a.amount_sek != g.premium_sek]
        if changed:
            raise CloseError(f"{len(changed)} bokade premier har ändrats i paket A sedan stängningen, t.ex. "
                             f"{changed[0]}. Återtag av mottagen premie är ett senare steg – manuell prövning")
    guarantee_rows = [_guarantee_row(a) for a in additions_src]
    additions = ([Origin(str(r["id"]), str(r["payout_part_id"]), r["premium_sek"]) for r in guarantee_rows]
                 if current is None else
                 [Origin(str(g.id), str(g.payout_part_id), g.premium_sek) for g in booked_parts])

    # Steg 1: levandestatus och uttagslägen för delarna i stängningen (S4)
    parts = {uuid.UUID(o.policy_id) for o in [*origins, *additions]}
    owners = _owners(session, parts)
    benefit_of = _benefits(session, parts)
    receiving = {p.id for ps in receiving_parts(session, set(benefit_of.values()), month, end).values() for p in ps}
    started = sorted(str(p) for p in parts if p not in receiving)
    deceased = sorted(str(p) for p in parts if owners.get(p, (None, ""))[1] == "deceased")
    unknown_birth = sorted(str(p) for p in parts if owners.get(p, (None, ""))[0] is None)
    pending_start = sorted(str(p) for p in parts if p in receiving and (born := owners.get(p, (None, ""))[0])
                           and date(born.year + PENSION_AGE, born.month, 1) <= month)
    problems = []
    if started:
        problems.append(f"{len(started)} uttagsdelar med kapital har startat, pausats eller avslutats under "
                        f"{month:%Y-%m} (t.ex. {started[0]}); månadsrätt och slutavräkning byggs i paket B steg 5–7")
    if deceased:
        problems.append(f"{len(deceased)} uttagsdelar tillhör en person registrerad som avliden (t.ex. "
                        f"{deceased[0]}); dödsfallsavräkningen byggs i paket B steg 7")
    if unknown_birth:
        problems.append(f"{len(unknown_birth)} uttagsdelar saknar ägarens födelsedag (t.ex. {unknown_birth[0]})")

    try:
        computed = compute_month(month, rate, fee_rate, tax_rate, origins, additions)
    except ValueError as exc:
        raise CloseError(f"Avräkningen per kapitalspår går inte ihop: {exc}") from exc

    opening_balance = {o.id: o.capital for o in origins}
    if current is None:
        status, entry_rows = "open", _close_entries(month, origins, additions, computed)
    else:
        booked = _booked_amounts(session, chain)
        diff = {k: computed.amounts.get(k, ZERO) - booked.get(k, ZERO) for k in {*computed.amounts, *booked}}
        diff = {k: v for k, v in diff.items() if v != 0}
        if not diff:
            return MonthPlan(month=month, period_end=end, status="closed", content=current.content,
                             checksum=current.checksum, supersedes=current, version=len(chain))
        if any(e > end for e in closed):
            raise CloseError(f"{month:%Y-%m} ger andra belopp än den stängda versionen, men en senare månad är "
                             "stängd. Bara den senast stängda månaden kan rättas i första versionen")
        status = "correction"
        current_balance = {str(t.origin_id): t.balance for t in cl.tracks(session, end)}
        entry_rows = _correction_entries(month, len(chain) + 1, diff, current_balance,
                                         {o.id: o.policy_id for o in additions + origins})

    g_before = sum((g.guarantee_sek_per_month for g in cl.guarantee_parts(session, previous_end)), Decimal(0))
    g_added = sum((r["guarantee_sek_per_month"] for r in guarantee_rows), Decimal(0)) if current is None else \
        sum((g.guarantee_sek_per_month for g in booked_parts), Decimal(0))
    controls = _controls(month, computed, origins, additions, opening_balance, avk, fee_label, tax_label,
                         intake_summary, started, deceased, pending_start, g_before, g_added, guarantee_rows,
                         previous)
    version = len(chain) + 1
    rows_digest = vb.checksum({"guarantee_parts": [_plain(r) for r in guarantee_rows],
                               "entries": [_plain(r) for r in entry_rows]})
    content = {
        "method": METHOD, "origin_method": origin_code_version(), "design": "P1-PENSION-001 §7, B-047",
        "kind": CORRECTION_KIND if status == "correction" else CLOSE_KIND, "version": version,
        "month": month.isoformat(), "period_end": end.isoformat(), "source": LEDGER,
        "previous": {"kind": previous.kind, "period_end": previous.period_end.isoformat(),
                     "checksum": previous.checksum},
        "supersedes": current.checksum if current is not None else None,
        "return_basis": {"code": avk.code, "checksum": avk.checksum, "rate": str(rate)},
        "parameters": {"capital_fee_rate": [fee_label], "customer_tax_rate": [tax_label],
                       "fee_rate": str(fee_rate), "tax_rate": str(tax_rate)},
        "premiums": intake_summary if current is None else {"booked_in": current.checksum,
                                                            "allocations": len(booked_parts)},
        "totals": {**{k: str(v) for k, v in computed.totals.items()},
                   "tracks": len(computed.closing), "payout_parts": len(parts),
                   "new_guarantee_parts": len(guarantee_rows),
                   "guarantee_opening_sek_per_month": str(g_before),
                   "guarantee_added_sek_per_month": str(g_added),
                   "guarantee_closing_sek_per_month": str(g_before + g_added),
                   "entries": len(entry_rows)},
        "standard_start_pending": pending_start,
        "rows_checksum": rows_digest,
        "controls": [c.as_dict() for c in controls],
    }
    return MonthPlan(month=month, period_end=end, status=status, content=content, checksum=vb.checksum(content),
                     guarantee_rows=guarantee_rows, entry_rows=entry_rows, controls=controls, problems=problems,
                     supersedes=current, version=version)


def _guarantee_row(a: PremiumAddition) -> dict:
    return {"id": stable_id(CLOSE_KIND, "guarantee", str(a.payment_allocation_id)), "payout_part_id": a.payout_part_id,
            "origin_kind": "payment_allocation", "premium_transaction_id": a.premium_transaction_id,
            "payment_allocation_id": a.payment_allocation_id, "premium_sek": a.premium_sek,
            "period_month": a.period_month, "received_month": a.received_month, "value_date": a.value_date,
            "plan_kind": "reference_lifelong", "plan_start": a.plan_start, "basis_code": a.basis_code,
            "basis_checksum": a.basis_checksum, "factor": a.factor,
            "guarantee_sek_per_month": a.guarantee_sek_per_month, "version": 1, "reason": "premium",
            "supersedes_id": None, "source": LEDGER}


def _entry(month: date, tag: str, origin: str, part: str, reason: str, amount: Decimal, before: Decimal) -> dict:
    return {"id": stable_id(tag, month.isoformat(), origin, reason), "account": CUSTOMER,
            "payout_part_id": uuid.UUID(part), "origin_id": uuid.UUID(origin), "month": month, "reason": reason,
            "amount_sek": amount, "balance_before_sek": before, "balance_after_sek": before + amount,
            "source": LEDGER}


def _close_entries(month: date, origins: list[Origin], additions: list[Origin], computed: Computed) -> list[dict]:
    rows, tag = [], f"{CLOSE_KIND}:1"
    for o in sorted(origins, key=lambda o: o.id):
        balance = o.capital
        for reason in REASONS[:3]:
            amount = computed.amounts.get((o.id, reason), ZERO)
            if amount:
                rows.append(_entry(month, tag, o.id, o.policy_id, reason, amount, balance))
                balance += amount
        if balance != computed.closing[o.id]:
            raise CloseError(f"Kapitalspåret {o.id} går inte ihop med månadens avräkning")
    for o in sorted(additions, key=lambda o: o.id):
        rows.append(_entry(month, tag, o.id, o.policy_id, "premium", o.capital, ZERO))
    return rows


def _correction_entries(month: date, version: int, diff: dict, balance: dict[str, Decimal],
                        part_of: dict[str, str]) -> list[dict]:
    """Motposter som nettodifferens per spår och orsak; ökningar först så att inget saldo blir negativt."""
    rows, tag = [], f"{CORRECTION_KIND}:{version}"
    for origin in sorted({o for o, _ in diff}):
        current = balance.get(origin, ZERO)
        changes = sorted(((r, v) for (o, r), v in diff.items() if o == origin), key=lambda rv: (rv[1] < 0, REASONS.index(rv[0])))
        for reason, amount in changes:
            rows.append(_entry(month, tag, origin, part_of[origin], reason, amount, current))
            current += amount
    return rows


def _controls(month, computed, origins, additions, opening_balance, avk, fee_label, tax_label, intake_summary,
              started, deceased, pending_start, g_before, g_added, guarantee_rows, previous) -> list[Control]:
    t = computed.totals
    flow = t["opening_sek"] + t["returns_sek"] - t["fees_sek"] - t["taxes_sek"] + t["premiums_sek"]
    track_sum = sum(computed.closing.values(), ZERO)
    negative = [o for o, v in computed.closing.items() if v < 0]
    opening_sum = sum(opening_balance.values(), ZERO)
    premium_sum = sum((o.capital for o in additions), ZERO)
    sources = {"previous": previous.checksum, "return_basis": avk.checksum}
    controls = [
        Control("föregående läge", True, f"{previous.kind} per {previous.period_end} med kontrollsumma "
                f"{previous.checksum[:12]}; {len(origins)} kapitalspår och {opening_sum} kr",
                expected=str(t["opening_sek"]), actual=str(opening_sum), difference=opening_sum - t["opening_sek"],
                sources=sources),
        Control("avkastning för månaden", True, f"{avk.code} antagen, {computed.totals['returns_sek']} kr "
                f"(PR-ITP1-021)", sources=sources),
        Control("avgift och skattebelastning", True, f"{fee_label} och {tax_label} på öppningsbasen "
                f"(PR-ITP1-022, -023); avstått {t['fees_waived_sek']} kr och {t['taxes_waived_sek']} kr",
                sources=sources),
        Control("kapital per spår", not negative and track_sum == t["closing_sek"],
                f"{len(computed.closing)} spår summerar till {track_sum} kr; inget negativt saldo",
                expected=str(t["closing_sek"]), actual=str(track_sum), difference=track_sum - t["closing_sek"],
                sources=sources),
        Control("kapital totalt", flow == t["closing_sek"],
                f"IB {t['opening_sek']} + avkastning {t['returns_sek']} − avgift {t['fees_sek']} − skatt "
                f"{t['taxes_sek']} + premier {t['premiums_sek']} = UB {t['closing_sek']} kr",
                expected=str(flow), actual=str(t["closing_sek"]), difference=t["closing_sek"] - flow, sources=sources),
        Control("garanti totalt", True, f"ΣG {g_before} + {g_added} = {g_before + g_added} kr/mån; avkastning ändrar "
                "aldrig G", expected=str(g_before + g_added), actual=str(g_before + g_added), sources=sources),
    ]
    if intake_summary is not None:
        intake_sum = Decimal(intake_summary["premium_sek"])
        controls += [
            Control("premier ur paket A", premium_sum == intake_sum == t["premiums_sek"]
                    and len(guarantee_rows) == intake_summary["allocations"],
                    f"{intake_summary['allocations']} allokeringar på fakturarader, {intake_sum} kr, varav "
                    f"{intake_summary['late_sek']} kr registrerade efter föregående stängning",
                    expected=str(intake_sum), actual=str(premium_sum), difference=premium_sum - intake_sum,
                    sources={**sources, "premiums": intake_summary["checksum"]}),
            Control("avstämningskontot", True, f"{intake_summary['suspense_sek']} kr på avstämningskontot och "
                    f"{intake_summary['after_month_end_sek']} kr mottaget efter månadsslutet följer inte med",
                    sources=sources),
        ]
    controls += [
        Control("startade delar", not started, f"{len(started)} startade delar med kapital" if started
                else "Alla delar i stängningen är ej startade hela månaden", actual=str(len(started)), sources=sources),
        Control("levandestatus", not deceased, f"{len(deceased)} delar med registrerat dödsfall" if deceased
                else "Inget registrerat dödsfall bland delarnas ägare", actual=str(len(deceased)), sources=sources),
        Control("standardstart väntar på steg 4", True,
                f"{len(pending_start)} ej startade delar vars ägare fyllt {PENSION_AGE} senast {month:%Y-%m}; "
                "sparandet stängs, startmånaden flyttas inte och rätten räknas fram i steg 4 (PR-ITP1-025)"
                if pending_start else f"Ingen ägare har fyllt {PENSION_AGE} senast {month:%Y-%m}",
                actual=str(len(pending_start)), sources=sources),
    ]
    return controls


def apply_month(session: Session, month: date, actor: str, reviewed_checksum: str,
                today: date) -> tuple[LedgerBatch, bool]:
    """Bokar stängningen eller rättelsen med granskningens kontrollsumma. (verifikation, ny) – idempotent."""
    if session.bind.dialect.name == "postgresql":
        session.execute(select(func.pg_advisory_xact_lock(*LOCK)))
    plan = plan_month(session, month, today)
    if plan.status == "closed":
        chain = cl.month_chain(session, plan.period_end)
        booked = next((b for b in chain if b.checksum == reviewed_checksum), None)
        if booked is None:
            raise CloseConflict(f"{plan.month:%Y-%m} är stängd med annat innehåll – granska månaden igen")
        verify_month(session, chain[-1])
        return chain[-1], False
    if plan.checksum != reviewed_checksum:
        raise CloseConflict("Underlaget har ändrats sedan granskningen – granska månaden igen")
    if not plan.passed:
        failed = [c.step for c in plan.controls if not c.passed]
        raise CloseError("Stängningen stoppas: " + "; ".join(plan.problems + [f"kontrollen {f} avviker" for f in failed]))
    batch = LedgerBatch(id=stable_id(plan.kind, plan.period_end.isoformat(), str(plan.version)), kind=plan.kind,
                        period_end=plan.period_end, source=LEDGER, extract_id=None, extract_checksum=None,
                        content=plan.content, checksum=plan.checksum, created_by=actor,
                        supersedes_id=plan.supersedes.id if plan.kind == CORRECTION_KIND else None)
    session.add(batch)
    session.flush()
    if plan.guarantee_rows:
        session.bulk_insert_mappings(LedgerGuaranteePart, [{**r, "batch_id": batch.id, "created_by": actor}
                                                           for r in plan.guarantee_rows])
    if plan.entry_rows:
        # Ett nytt spår (premie) får sin post först efter sin garantidel
        session.bulk_insert_mappings(LedgerCapitalEntry, [{**r, "batch_id": batch.id, "created_by": actor}
                                                          for r in plan.entry_rows])
    session.add_all(LedgerControl(id=stable_id(plan.kind, plan.period_end.isoformat(), str(plan.version), c.step),
                                  batch_id=batch.id, step=c.step, expected=c.expected, actual=c.actual,
                                  difference=c.difference, sources=c.sources, passed=c.passed, detail=c.detail)
                    for c in plan.controls)
    session.flush()
    verify_month(session, batch)
    return batch, True


def verify_month(session: Session, batch: LedgerBatch) -> None:
    """Prövar en bokad stängning eller rättelse mot sin sammanställning, och månadens saldon mot totalerna."""
    if vb.checksum(batch.content) != batch.checksum:
        raise CloseError("Verifikationens sammanställning har ändrats")
    totals = batch.content["totals"]
    count = session.scalar(select(func.count()).select_from(LedgerCapitalEntry)
                           .where(LedgerCapitalEntry.batch_id == batch.id))
    parts = session.scalar(select(func.count()).select_from(LedgerGuaranteePart)
                           .where(LedgerGuaranteePart.batch_id == batch.id))
    if (count, parts) != (totals["entries"], totals["new_guarantee_parts"]):
        raise CloseError(f"Verifikationens rader stämmer inte ({count} poster och {parts} garantidelar mot "
                         f"{totals['entries']} och {totals['new_guarantee_parts']})")
    closing = sum((t.balance for t in cl.tracks(session, batch.period_end)), ZERO)
    if closing != Decimal(totals["closing_sek"]):
        raise CloseError(f"Journalens kundkapital per {batch.period_end} är {closing} kr, inte "
                         f"{totals['closing_sek']} kr enligt den gällande versionen")
    failed = session.scalars(select(LedgerControl.step).where(LedgerControl.batch_id == batch.id,
                                                               LedgerControl.passed.is_(False))).all()
    if failed:
        raise CloseError(f"Verifikationen har underkända kontroller: {', '.join(failed)}")


def month_view(session: Session, month: date) -> dict:
    """Månadens versioner: stängningen och dess rättelser med sammanställning, utan rader."""
    month = month.replace(day=1)
    chain = cl.month_chain(session, month_end(month))
    if not chain:
        raise CloseError(f"{month:%Y-%m} är inte stängd")
    verify_month(session, chain[-1])
    return {"month": month.isoformat(), "period_end": month_end(month).isoformat(),
            "effective": {**chain[-1].content, "batch_id": str(chain[-1].id), "checksum": chain[-1].checksum},
            "versions": [{"batch_id": str(b.id), "kind": b.kind, "version": b.content["version"],
                          "checksum": b.checksum, "created_by": b.created_by,
                          "created_at": b.created_at.isoformat() if b.created_at else None} for b in chain]}


__all__ = ["METHOD", "CloseConflict", "CloseError", "Computed", "MonthPlan", "apply_month", "compute_month",
           "month_view", "plan_month", "verify_month"]
