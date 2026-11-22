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

**Planer och delningar (paket B steg 4, Karls val V2–V9).** Beslut om plan och delning skrivs av
`payout_plans` utan bokning; ändringsmånadens stängning genomför dem i steg 1, på värderingen vid
föregående månadsslut: delningen flyttar C i ören med största bråkrest och varje G_j proportionellt
(orsaken `split`), och en ändrad plan räknar om varje G_j värdebevarande på sin historiska grund som ny
version (`plan_kind = 'plan'`, länk till planen). En del med rätt under månaden enligt plan blockerar
tills månadsrätten finns i steg 5 (V3).

**66-årsmånaden (Karls val S4, V4–V6).** En ej startad del vars ägare fyllt 66 senast i månaden och
saknar plan redovisas i kontrollposten *standardstart* (före steg 4:s migration *standardstart väntar på
steg 4*, exakt som i steg 3). Verifierad ägare som fyller 66 i månaden visar
standardplanen i granskningen och blockerar till steg 5; overifierat underlag och den som passerat 66
utan plan får ett ärende `payout_review` en gång, och sparandet stängs. Startmånaden flyttas aldrig tyst
(PR-ITP1-025). Utan steg 4:s tabeller beter sig stängningen som i steg 3.

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
    Case,
    InsuredPerson,
    LedgerBatch,
    LedgerCapitalEntry,
    LedgerControl,
    LedgerGuaranteePart,
    PaymentAllocation,
    PayoutPart,
    PayoutPartState,
    PayoutPlan,
    PayoutSplit,
    Policy,
    PolicyBenefit,
)
from services import capital_ledger as cl
from services import parameters
from services import payout_plans as pl
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
from skills.calculation import payout_plan as pp
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
    #: Steg 4: garantidelsversioner (delning, omräkning), nya delar ur delning och ärenden att öppna
    version_rows: list[dict] = field(default_factory=list)
    split_parts: list[dict] = field(default_factory=list)
    review_cases: list[dict] = field(default_factory=list)

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


def _booked_amounts(session: Session, chain: list[LedgerBatch], home: dict) -> dict[tuple[str, str], Decimal]:
    """Månadens bokade belopp per (spår, orsak) över stängningen och dess rättelser.

    Delningens poster (steg 4) räknas inte: delningen görs om på samma föregående månadsslut vid en rättelse.
    """
    rows = session.execute(
        select(LedgerCapitalEntry.payout_part_id, LedgerCapitalEntry.origin_id, LedgerCapitalEntry.reason,
               func.sum(LedgerCapitalEntry.amount_sek))
        .where(LedgerCapitalEntry.batch_id.in_([b.id for b in chain]), LedgerCapitalEntry.account == CUSTOMER,
               LedgerCapitalEntry.reason != "split")
        .group_by(LedgerCapitalEntry.payout_part_id, LedgerCapitalEntry.origin_id, LedgerCapitalEntry.reason)).all()
    return {(_key(home, p, o), r): Decimal(total).quantize(Decimal("0.01")) for p, o, r, total in rows}


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

    # Steg 1: öppningskapitalet per kapitalspår. Ett spår är (uttagsdel, ursprung): efter en delning bär två
    # delar samma ursprung. Spårnyckeln är ursprunget på dess egen del (som i steg 3) och `ursprung@del` annars
    steg4 = pl.plans_present(session)
    home = _homes(session)
    opening_tracks = cl.tracks(session, previous_end)
    origins = [Origin(_key(home, t.payout_part_id, t.origin_id), str(t.payout_part_id), t.balance)
               for t in opening_tracks]
    problems: list[str] = []

    # Steg 1 (steg 4): delningar och planer med ändringsmånaden, genomförda på föregående månadsslut (V2, V9)
    splits = pl.splits_in(session, month) if steg4 else []
    effective_plans = _effective_plans(session, month) if steg4 else []
    guarantees_before = cl.guarantee_parts(session, previous_end)
    split_parts, split_entries, version_rows = [], [], []
    for split in splits:
        origins, rows, entries, new_part, problem = _split(session, month, split, origins, guarantees_before, home,
                                                           book=current is None)
        split_parts.append(new_part)
        version_rows += rows
        split_entries += entries
        problems += problem
    for plan in effective_plans:
        rows, problem = _recalculation(month, plan, guarantees_before,
                                       split_from={s.from_part_id for s in splits})
        version_rows += rows if current is None else []
        problems += problem
    new_ids = {p["id"] for p in split_parts}
    split_owner = {p["id"]: p["split_from_part_id"] for p in split_parts}

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

    # Steg 1: levandestatus och uttagslägen för delarna i stängningen (S4). En ny del ur månadens delning
    # finns inte ännu: den är ej startad och har den delade delens ägare
    parts = {uuid.UUID(o.policy_id) for o in [*origins, *additions]}
    stored = parts - new_ids
    owners = _owners(session, stored | set(split_owner.values()))
    owners.update({new: owners.get(old, (None, "")) for new, old in split_owner.items()})
    benefit_of = _benefits(session, stored)
    receiving = {p.id for ps in receiving_parts(session, set(benefit_of.values()), month, end).values() for p in ps}
    receiving |= new_ids
    started = sorted(str(p) for p in parts if p not in receiving)
    deceased = sorted(str(p) for p in parts if owners.get(p, (None, ""))[1] == "deceased")
    unknown_birth = sorted(str(p) for p in parts if owners.get(p, (None, ""))[0] is None)
    pending_start = sorted(str(p) for p in parts if p in receiving and (born := owners.get(p, (None, ""))[0])
                           and date(born.year + PENSION_AGE, born.month, 1) <= month)
    if started:
        problems.append(f"{len(started)} uttagsdelar med kapital har startat, pausats eller avslutats under "
                        f"{month:%Y-%m} (t.ex. {started[0]}); månadsrätt och slutavräkning byggs i paket B steg 5–7")
    if deceased:
        problems.append(f"{len(deceased)} uttagsdelar tillhör en person registrerad som avliden (t.ex. "
                        f"{deceased[0]}); dödsfallsavräkningen byggs i paket B steg 7")
    if unknown_birth:
        problems.append(f"{len(unknown_birth)} uttagsdelar saknar ägarens födelsedag (t.ex. {unknown_birth[0]})")

    # Steg 1 (steg 4): rätt under månaden enligt plan blockerar (V3); standardstart och ärenden vid 66 (V4, V6)
    pending_ids = {uuid.UUID(p) for p in pending_start}
    start = (_standard_start(session, month, previous_end, (stored & pending_ids) - set(unknown_ids(owners)))
             if steg4 else {"planned": [], "standard": [], "cases": []})
    with_right = sorted(str(part) for part, plan in pl.plans_in_force(session, stored, month).items()
                        if pl.schedule_of(plan).has_right(month)) if steg4 else []
    if with_right:
        problems.append(f"{len(with_right)} uttagsdelar har rätt under {month:%Y-%m} enligt beslutad plan (t.ex. "
                        f"{with_right[0]}); månadsrätt byggs i paket B steg 5")
    if start["standard"]:
        problems.append(f"{len(start['standard'])} uttagsdelar får standardstart {month:%Y-%m} (PR-ITP1-025), t.ex. "
                        f"{start['standard'][0]['payout_part_id']}; månadsrätt byggs i paket B steg 5")

    try:
        computed = compute_month(month, rate, fee_rate, tax_rate, origins, additions)
    except ValueError as exc:
        raise CloseError(f"Avräkningen per kapitalspår går inte ihop: {exc}") from exc

    opening_balance = {o.id: o.capital for o in origins}
    if current is None:
        status, entry_rows = "open", split_entries + _close_entries(month, origins, additions, computed)
    else:
        booked = _booked_amounts(session, chain, home)
        diff = {k: computed.amounts.get(k, ZERO) - booked.get(k, ZERO) for k in {*computed.amounts, *booked}}
        diff = {k: v for k, v in diff.items() if v != 0}
        if not diff:
            return MonthPlan(month=month, period_end=end, status="closed", content=current.content,
                             checksum=current.checksum, supersedes=current, version=len(chain))
        if any(e > end for e in closed):
            raise CloseError(f"{month:%Y-%m} ger andra belopp än den stängda versionen, men en senare månad är "
                             "stängd. Bara den senast stängda månaden kan rättas i första versionen")
        status = "correction"
        current_balance = {_key(home, t.payout_part_id, t.origin_id): t.balance for t in cl.tracks(session, end)}
        entry_rows = _correction_entries(month, len(chain) + 1, diff, current_balance,
                                         {o.id: o.policy_id for o in additions + origins})

    g_before = sum((g.guarantee_sek_per_month for g in guarantees_before), Decimal(0))
    g_added = sum((r["guarantee_sek_per_month"] for r in guarantee_rows), Decimal(0)) if current is None else \
        sum((g.guarantee_sek_per_month for g in booked_parts), Decimal(0))
    versions = version_rows if current is None else _chain_versions(session, chain)
    replaced = {g.id: g.guarantee_sek_per_month for g in guarantees_before}
    g_change = (sum((r["guarantee_sek_per_month"] for r in versions), Decimal(0))
                - sum((replaced.get(i, Decimal(0)) for i in {r["supersedes_id"] for r in versions}), Decimal(0)))
    controls = _controls(month, computed, origins, additions, opening_balance, avk, fee_label, tax_label,
                         intake_summary, started, deceased, pending_start, g_before, g_added, guarantee_rows,
                         previous, start=start if steg4 else None, g_change=g_change, splits=len(splits),
                         plans=len(effective_plans), with_right=with_right)
    version = len(chain) + 1
    rows_digest = vb.checksum({"guarantee_parts": [_plain(r) for r in guarantee_rows],
                               "entries": [_plain(r) for r in entry_rows],
                               **({"guarantee_versions": [_plain(r) for r in version_rows],
                                   "payout_parts": [_plain(r) for r in split_parts]}
                                  if version_rows or split_parts else {})})
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
                   "guarantee_closing_sek_per_month": str(g_before + g_added + g_change),
                   "entries": len(entry_rows),
                   **({"guarantee_versions": len(version_rows), "guarantee_change_sek_per_month": str(g_change),
                       "splits": len(splits), "plans": len(effective_plans)} if steg4 else {})},
        "standard_start_pending": pending_start,
        **({"payout": {"plans": [str(p.id) for p in effective_plans], "splits": [str(s.id) for s in splits],
                       "planned_parts": start["planned"], "standard_start": start["standard"],
                       "review_cases": [{k: str(v) for k, v in c.items() if k != "person_id"}
                                        for c in start["cases"]],
                       "with_right": with_right}} if steg4 else {}),
        "rows_checksum": rows_digest,
        "controls": [c.as_dict() for c in controls],
    }
    return MonthPlan(month=month, period_end=end, status=status, content=content, checksum=vb.checksum(content),
                     guarantee_rows=guarantee_rows, entry_rows=entry_rows, controls=controls, problems=problems,
                     supersedes=current, version=version, version_rows=version_rows, split_parts=split_parts,
                     review_cases=start["cases"] if current is None else [])


def unknown_ids(owners: dict) -> list:
    return [p for p, (born, _) in owners.items() if born is None]


def _homes(session: Session) -> dict[uuid.UUID, uuid.UUID]:
    """Ursprung (garantidel version 1) → uttagsdelen där ursprunget bildades."""
    return dict(session.execute(select(LedgerGuaranteePart.id, LedgerGuaranteePart.payout_part_id)
                                .where(LedgerGuaranteePart.version == 1)).all())


def _key(home: dict, part, origin) -> str:
    """Spårnyckeln: ursprunget på sin egen del (som i steg 3), annars `ursprung@del` efter delning."""
    part, origin = uuid.UUID(str(part)), uuid.UUID(str(origin))
    return str(origin) if home.get(origin, part) == part else f"{origin}@{part}"


def _origin_of(key: str) -> str:
    return key.split("@")[0]


def _effective_plans(session: Session, month: date) -> list[PayoutPlan]:
    return list(session.scalars(select(PayoutPlan).where(PayoutPlan.effective_month == month)
                                .order_by(PayoutPlan.payout_part_id, PayoutPlan.version)))


def _version_row(month: date, tag: str, source: LedgerGuaranteePart, part, reason: str, g: Decimal, *,
                 plan: PayoutPlan | None = None, factor: Decimal | None = None) -> dict:
    """En ny garantidelsversion som ersätter `source` från ändringsmånaden (delning eller omräkning)."""
    row = {"id": stable_id(CLOSE_KIND, tag, str(source.id), str(part)), "payout_part_id": uuid.UUID(str(part)),
           "origin_kind": source.origin_kind, "premium_transaction_id": source.premium_transaction_id,
           "payment_allocation_id": source.payment_allocation_id, "premium_sek": source.premium_sek,
           "period_month": source.period_month, "received_month": source.received_month,
           # Versionen gäller från ändringsmånaden; föregående månadsslut visar den ersatta versionen
           "value_date": month, "plan_kind": "plan" if plan is not None else source.plan_kind,
           "plan_start": plan.first_right if plan is not None else source.plan_start,
           "basis_code": source.basis_code, "basis_checksum": source.basis_checksum,
           "factor": factor if factor is not None else source.factor, "guarantee_sek_per_month": g,
           "version": source.version + 1, "reason": reason, "supersedes_id": source.id, "source": LEDGER}
    if plan is not None:
        row["plan_id"] = plan.id
    return row


def _split(session: Session, month: date, split: PayoutSplit, origins: list[Origin], guarantees: list, home: dict,
           *, book: bool) -> tuple[list[Origin], list[dict], list[dict], dict, list[str]]:
    """Delning i steg 1 (V9): kapital i ören per spår och garantidelarna proportionellt, utan ny värdering.

    Spåren delas också vid en rättelse (`book` nej), men posterna och versionerna är då redan bokade.
    """
    problems = []
    old = str(split.from_part_id)
    new = pl.new_part_id(split.id)
    share = Decimal(split.share)
    own = [o for o in origins if o.policy_id == old]
    tracks = [cl.Track(split.from_part_id, uuid.UUID(_origin_of(o.id)), "", "", o.capital) for o in own]
    target, moves = pl.split_amounts(tracks, share)
    planned = {t["origin_id"]: Decimal(t["moved"]) for t in split.content["tracks"]}
    if target != Decimal(split.content["new_capital_sek"]) or \
            planned != {str(t.origin_id): m for t, m in zip(tracks, moves)}:
        problems.append(f"Delningen {split.id} bygger på ett annat kapital än vid beslutet – delningen behöver nytt "
                        "beslut")
    moved = dict(zip((o.id for o in own), moves))
    out, entries = [], []
    tag = f"{CLOSE_KIND}:split:{split.id}"
    for o in origins:
        amount = moved.get(o.id, ZERO)
        if not amount:
            out.append(o)
            continue
        new_key = _key(home, new, _origin_of(o.id))
        out += [Origin(o.id, o.policy_id, o.capital - amount), Origin(new_key, str(new), amount)]
        if book:
            entries += [_entry(month, tag, o.id, old, "split", -amount, o.capital),
                        _entry(month, tag, new_key, str(new), "split", amount, ZERO)]
    rows = []
    for g in [g for g in guarantees if g.payout_part_id == split.from_part_id]:
        if g.plan_kind == "plan":
            problems.append(f"Delningen {split.id} gäller en del med planbaserad garanti – planen beslutas efter "
                            "delningen")
            continue
        keep, part = pl.split_guarantee(g.guarantee_sek_per_month, share)
        rows += [_version_row(month, "split", g, split.from_part_id, "split", keep),
                 _version_row(month, "split", g, new, "split", part)]
    parent = session.get(PayoutPart, split.from_part_id)
    new_part = {"id": new, "benefit_id": parent.benefit_id, "part_number": split.new_part_number,
                "share_of_origin": (parent.share_of_origin * share).quantize(Decimal("1e-10")),
                "split_from_part_id": parent.id, "split_date": month, "split_share": share,
                "parent_share_after": (parent.share_of_origin * (1 - share)).quantize(Decimal("1e-10"))}
    return out, (rows if book else []), entries, new_part, problems


def _recalculation(month: date, plan: PayoutPlan, guarantees: list, *, split_from: set) -> tuple[list[dict], list[str]]:
    """Planens omräkning av garantidelarna (PR-ITP1-008, V7), som beslutet räknade den."""
    if plan.payout_part_id in split_from:
        return [], [f"Planen {plan.id} och en delning gäller samma del samma månad – besluta en i taget"]
    own = {str(g.id): g for g in guarantees if g.payout_part_id == plan.payout_part_id}
    planned = {g["id"]: g for g in plan.content["guarantees"]}
    if set(own) != set(planned):
        return [], [(f"Garantidelarna för planen {plan.id} har ändrats sedan beslutet ({len(planned)} beslutade, "
                     f"{len(own)} i journalen) – planen behöver nytt beslut")]
    rows = [_version_row(month, f"plan:{plan.id}", own[i], plan.payout_part_id, "recalculation",
                         Decimal(planned[i]["g_new"]), plan=plan, factor=Decimal(planned[i]["factor_new"]))
            for i in sorted(own)]
    return rows, []


def _standard_start(session: Session, month: date, valuation: date, part_ids: set) -> dict:
    """66-årsmånaden (PR-ITP1-025, V4, V6): standardplan för verifierad ägare, annars ärende; inga tysta starter."""
    out = {"planned": [], "standard": [], "cases": []}
    if not part_ids:
        return out
    planned = pl.planned_parts(session, part_ids)
    out["planned"] = sorted(str(p) for p in planned)
    owner_of = pl.owners(session, part_ids - planned)
    reviewed = {(c.insured_person_id, (c.details or {}).get("reason")) for c in session.scalars(
        select(Case).where(Case.case_type == "payout_review",
                           Case.insured_person_id.in_([o.person_id for o in owner_of.values()])))}
    bases = None
    for part_id in sorted(owner_of, key=str):
        owner = owner_of[part_id]
        sixty_six = pp.sixty_six_month(owner.birth, PENSION_AGE)
        if sixty_six == month:
            problems = owner.verification(session)
            if not problems:
                bases = bases or pl.Bases.load(session, month)
                plan = pl.standard_plan(session, owner, month, bases=bases, valuation=valuation,
                                        pension_age=PENSION_AGE)
                out["standard"].append({"payout_part_id": str(part_id), "first_right": plan["schedule"]["first_right"],
                                        "first_payment_day": plan["first_payment_day"],
                                        "guarantee_sek_per_month": plan["guarantee_sek_per_month"],
                                        "capital_amount_sek": plan["capital_amount_sek"],
                                        "m_sek": plan["amount"]["m_sek"], "review_checksum": plan["review_checksum"]})
                continue
            reason, detail = "standard_start_unverified", "; ".join(problems)
        else:
            reason, detail = "passed_66_without_plan", f"66 år {sixty_six:%Y-%m}, ingen plan registrerad"
        if (owner.person_id, reason) in reviewed:
            continue
        reviewed.add((owner.person_id, reason))
        out["cases"].append({"payout_part_id": str(part_id), "person_id": owner.person_id,
                             "policy_id": owner.policy_id, "reason": reason, "detail": detail,
                             "sixty_six_month": sixty_six.isoformat()})
    return out


def _chain_versions(session: Session, chain: list[LedgerBatch]) -> list[dict]:
    return [{"guarantee_sek_per_month": g.guarantee_sek_per_month, "supersedes_id": g.supersedes_id}
            for g in session.scalars(select(LedgerGuaranteePart).where(
                LedgerGuaranteePart.batch_id.in_([b.id for b in chain]), LedgerGuaranteePart.version > 1))]


def _guarantee_row(a: PremiumAddition) -> dict:
    return {"id": stable_id(CLOSE_KIND, "guarantee", str(a.payment_allocation_id)), "payout_part_id": a.payout_part_id,
            "origin_kind": "payment_allocation", "premium_transaction_id": a.premium_transaction_id,
            "payment_allocation_id": a.payment_allocation_id, "premium_sek": a.premium_sek,
            "period_month": a.period_month, "received_month": a.received_month, "value_date": a.value_date,
            "plan_kind": a.plan_kind, "plan_start": a.plan_start, "basis_code": a.basis_code,
            "basis_checksum": a.basis_checksum, "factor": a.factor,
            "guarantee_sek_per_month": a.guarantee_sek_per_month, "version": 1, "reason": "premium",
            "supersedes_id": None, "source": LEDGER,
            # Planen sätts bara för en premie på en del med beslutad plan (steg 4), så att raden går att
            # skriva där steg 4:s migration inte är körd
            **({"plan_id": a.plan_id} if a.plan_id is not None else {})}


def _entry(month: date, tag: str, key: str, part: str, reason: str, amount: Decimal, before: Decimal) -> dict:
    """En kapitalpost på spåret `key`; för ett spår på ursprungets egen del är id:t detsamma som i steg 3."""
    return {"id": stable_id(tag, month.isoformat(), key, reason), "account": CUSTOMER,
            "payout_part_id": uuid.UUID(part), "origin_id": uuid.UUID(_origin_of(key)), "month": month,
            "reason": reason,
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
              started, deceased, pending_start, g_before, g_added, guarantee_rows, previous, *, start=None,
              g_change=Decimal(0), splits=0, plans=0, with_right=()) -> list[Control]:
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
                "aldrig G", expected=str(g_before + g_added), actual=str(g_before + g_added), sources=sources)
        if start is None else
        Control("garanti totalt", True, f"ΣG {g_before} + premier {g_added} + omräkning och delning {g_change} = "
                f"{g_before + g_added + g_change} kr/mån; {plans} planer och {splits} delningar genomförs; "
                "avkastning ändrar aldrig G", expected=str(g_before + g_added + g_change),
                actual=str(g_before + g_added + g_change), sources=sources),
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
    ]
    if start is None:  # steg 4:s migration inte körd: som i steg 3
        # Exakt steg 3:s kontrollpost, så att stängningen före migrationen är identisk med steg 3 (B-051 p. 11)
        controls.append(Control(
            "standardstart väntar på steg 4", True,
            f"{len(pending_start)} ej startade delar vars ägare fyllt {PENSION_AGE} senast {month:%Y-%m}; "
            "sparandet stängs, startmånaden flyttas inte och rätten räknas fram i steg 4 (PR-ITP1-025)"
            if pending_start else f"Ingen ägare har fyllt {PENSION_AGE} senast {month:%Y-%m}",
            actual=str(len(pending_start)), sources=sources))
        return controls
    earlier = len(pending_start) - len(start["planned"]) - len(start["standard"]) - len(start["cases"])
    controls += [
        Control("standardstart", not start["standard"],
                f"{len(pending_start)} ej startade delar vars ägare fyllt {PENSION_AGE} senast {month:%Y-%m}: "
                f"{len(start['planned'])} har beslutad plan, {len(start['standard'])} får standardplan i månaden "
                f"(månadsrätt i steg 5), {len(start['cases'])} nya ärenden payout_review och "
                f"{max(earlier, 0)} med ärende sedan tidigare; startmånaden flyttas aldrig tyst (PR-ITP1-025)"
                if pending_start else f"Ingen ägare har fyllt {PENSION_AGE} senast {month:%Y-%m}",
                expected="0", actual=str(len(start["standard"])), sources=sources),
        Control("rätt enligt plan", not with_right,
                f"{len(with_right)} delar har rätt under {month:%Y-%m} enligt beslutad plan; månadsrätt byggs i "
                "steg 5" if with_right else f"Ingen del har rätt under {month:%Y-%m} enligt beslutad plan",
                expected="0", actual=str(len(with_right)), sources=sources),
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
    for p in plan.split_parts:  # steg 4: den nya delen ur månadens delning, ej startad från ändringsmånaden
        parent = session.get(PayoutPart, p["split_from_part_id"])
        parent.share_of_origin = p["parent_share_after"]
        session.add(PayoutPart(id=p["id"], benefit_id=p["benefit_id"], part_number=p["part_number"],
                               share_of_origin=p["share_of_origin"], split_from_part_id=p["split_from_part_id"],
                               split_date=p["split_date"], split_share=p["split_share"]))
        session.flush()
        session.add(PayoutPartState(payout_part_id=p["id"], state="not_started", valid_from=p["split_date"],
                                    note=f"Uttagsdel {p['part_number']} genom delning (PR-ITP1-024)"))
        session.flush()
    rows = plan.guarantee_rows + plan.version_rows
    for with_plan in (False, True):  # samma nycklar per anrop; `plan_id` bara där en plan finns
        batch_rows = [{**r, "batch_id": batch.id, "created_by": actor} for r in rows if ("plan_id" in r) == with_plan]
        if batch_rows:
            session.bulk_insert_mappings(LedgerGuaranteePart, batch_rows)
    if plan.entry_rows:
        # Ett nytt spår (premie) får sin post först efter sin garantidel
        session.bulk_insert_mappings(LedgerCapitalEntry, [{**r, "batch_id": batch.id, "created_by": actor}
                                                          for r in plan.entry_rows])
    for c in plan.review_cases:  # steg 4: ärenden vid 66 (V4, V6), i samma transaktion som stängningen
        session.add(Case(id=stable_id(plan.kind, plan.period_end.isoformat(), "review", c["payout_part_id"]),
                         case_number=pl.next_case_number(session), case_type="payout_review", status="open",
                         insured_person_id=c["person_id"], policy_id=c["policy_id"], channel="system",
                         received_date=today, source_reference=f"month_close:{plan.period_end.isoformat()}",
                         details={"reason": c["reason"], "detail": c["detail"], "payout_part_id": c["payout_part_id"],
                                  "sixty_six_month": c["sixty_six_month"], "month": plan.month.isoformat(),
                                  "text": pl.REVIEW_REASONS[c["reason"]]},
                         created_by=actor))
        session.flush()
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
    expected_parts = totals["new_guarantee_parts"] + totals.get("guarantee_versions", 0)
    if (count, parts) != (totals["entries"], expected_parts):
        raise CloseError(f"Verifikationens rader stämmer inte ({count} poster och {parts} garantidelar mot "
                         f"{totals['entries']} och {expected_parts})")
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
