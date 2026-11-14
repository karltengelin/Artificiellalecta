"""Operativ kapital- och garantijournal: övergången från S-04 och journalens läsningar (paket B steg 2).

Beslutat i B-047 punkt 4 och P1-PENSION-001 §6 (PB4). Tabellerna står i databasschema.md §7c.
Journalen är bolagets enda källa för C och G efter övergången.

**Övergången (§6.2).** Ingående läge är datautdraget S-04 per 2026-10-31, samma utdrag som
P6-MANAD-001 frös (hash `023946…3fefa` i Lakebase). Ursprungsspåren återskapas med
`reconstruct_origins`, som spelar upp S-04:s historiska månadsavräkning i ören. Varje garantidel och
varje kapitalspår knyts till försäkringens uttagsdel 1 (steg 1). Ingen historik bokas: varje spår får
en post med orsaken `opening` och sitt saldo per 2026-10-31, märkt `reconstructed_s04` och kopplad
till premieraden (valt av Karl 2026-11-14). Utdraget sparas oförändrat i `valuation_extracts` och
pekas ut av verifikationen, så historikens månader och flöden kan läsas utan att bokas om.
Historiska `premium_transactions` ändras inte.

Varje försäkrings C och G och kollektivets summa ska bevaras exakt – i Lakebase 42 087 223,57 kr
och 119 195,6502916268 kr/mån (fall 36). Minsta avvikelse stoppar övergången. Försäkringar som S-04
inte beräknar (påbörjat uttag, negativ premierad) förs inte över; de listas i verifikationen.

Övergången granskas först (`plan_opening`, skriver ingenting) och genomförs sedan med granskningens
kontrollsumma (`apply_opening`). Samma innehåll igen ger ingen ny effekt.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from models import (
    LedgerBatch,
    LedgerCapitalEntry,
    LedgerControl,
    LedgerGuaranteePart,
    PayoutPart,
    PayoutPartState,
    PolicyBenefit,
    PremiumTransaction,
    ValuationExtractRecord,
)
from services import valuation_bases as vb
from services.valuation_extract import (
    ExtractError,
    ValuationExtract,
    build_extract,
    extract_checksum,
    month_end,
)
from skills.calculation import actuarial_annuity as aa
from skills.calculation.premium_origin_ledger import (
    Origin,
    origin_code_version,
    reconstruct_origins,
)

#: Ingående läge: S-04 per oktober 2026, samma som P6-MANAD-001 (§6.2 p. 1)
OPENING_DATE = date(2026, 10, 31)
OPENING_KIND = "opening_s04"
S04 = "reconstructed_s04"
METHOD = "capital-ledger-1"
CUSTOMER = "customer_capital"
ZERO = Decimal("0.00")
#: Namnrymd för journalens stabila id:n, så att granskning och bokning ger samma rader
NAMESPACE = uuid.UUID("5f0c1f0e-6b1d-4b8e-9a43-2f6f2e4f8b26")


class LedgerError(ValueError):
    """Journalen kan inte läsas eller övergången inte göras, t.ex. underkänt utdrag eller saknad del."""


def stable_id(*parts: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, ":".join(parts))


def journal_present(session: Session) -> bool:
    """Är journalens tabeller införda i vald databas? (Lakebase före migrationen: nej.)"""
    return inspect(session.connection()).has_table(LedgerBatch.__tablename__)


def opening_batch(session: Session) -> LedgerBatch | None:
    """Verifikationen för det ingående läget, eller None om journalen saknas eller inte är öppnad."""
    if not journal_present(session):
        return None
    return session.scalar(select(LedgerBatch).where(LedgerBatch.kind == OPENING_KIND))


@dataclass(frozen=True)
class Control:
    step: str
    passed: bool
    detail: str
    expected: str | None = None
    actual: str | None = None
    difference: Decimal | None = None
    sources: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"step": self.step, "passed": self.passed, "detail": self.detail, "expected": self.expected,
                "actual": self.actual, "difference": None if self.difference is None else str(self.difference),
                "sources": self.sources}


@dataclass
class OpeningPlan:
    """Granskningsunderlaget för övergången: raderna som skulle skrivas, kontrollerna och summan."""

    extract: ValuationExtract
    replay_checksum: str
    guarantee_rows: list[dict]
    entry_rows: list[dict]
    controls: list[Control]
    content: dict
    checksum: str
    problems: list[str]

    @property
    def passed(self) -> bool:
        return not self.problems and all(c.passed for c in self.controls)

    def summary(self) -> dict:
        return {**self.content, "review_checksum": self.checksum, "passed": self.passed, "problems": self.problems}


def _model_birth(birth_month: str, born_on_first: bool) -> date:
    year, month = (int(x) for x in birth_month.split("-"))
    return date(year, month, 1 if born_on_first else 2)


def _parts_for(session: Session, premium_ids: list[str]) -> tuple[dict[str, uuid.UUID], dict[uuid.UUID, dict]]:
    """Premierad → uttagsdel (del 1 på premiens förmån), och per förmån delarna och deras läge vid övergången."""
    benefit_of = {}
    ids = [uuid.UUID(p) for p in premium_ids]
    for start in range(0, len(ids), 5000):
        chunk = ids[start:start + 5000]
        benefit_of.update({str(tx): benefit for tx, benefit in session.execute(
            select(PremiumTransaction.id, PremiumTransaction.benefit_id).where(PremiumTransaction.id.in_(chunk)))})
    benefits = sorted(set(benefit_of.values()), key=str)
    parts: dict[uuid.UUID, dict] = {}
    for start in range(0, len(benefits), 5000):
        chunk = benefits[start:start + 5000]
        for part, state in session.execute(
                select(PayoutPart, PayoutPartState.state)
                .outerjoin(PayoutPartState, (PayoutPartState.payout_part_id == PayoutPart.id)
                           & (PayoutPartState.valid_from <= OPENING_DATE)
                           & ((PayoutPartState.valid_to.is_(None)) | (PayoutPartState.valid_to >= OPENING_DATE)))
                .where(PayoutPart.benefit_id.in_(chunk))):
            info = parts.setdefault(part.benefit_id, {"parts": {}, "states": defaultdict(list)})
            info["parts"][part.part_number] = part.id
            info["states"][part.part_number].append(state)
    part_of = {}
    for premium_id, benefit in benefit_of.items():
        info = parts.get(benefit)
        if info and 1 in info["parts"]:
            part_of[premium_id] = info["parts"][1]
    return part_of, parts


def plan_opening(session: Session, expected_extract_checksum: str | None = None,
                 extract: ValuationExtract | None = None) -> OpeningPlan:
    """Bygger S-04 per 2026-10-31, återskapar spåren och planerar journalens ingående läge. Skriver inget."""
    if extract is None:
        try:
            extract = build_extract(session, OPENING_DATE)
        except ExtractError as exc:
            raise LedgerError(f"S-04 per {OPENING_DATE} kan inte byggas: {exc}") from exc
    if extract.valuation_date != OPENING_DATE or extract.checksum != extract_checksum(extract):
        raise LedgerError("Utdraget gäller inte 2026-10-31 eller har ändrat innehåll")
    problems = [] if extract.approved else [
        "S-04 är underkänt: " + ", ".join(c.name for c in extract.checks if not c.passed)]
    try:
        origins, replay = reconstruct_origins(extract)
    except ValueError as exc:
        raise LedgerError(f"Ursprungsspåren kan inte återskapas ur S-04: {exc}") from exc

    premium_ids = [g.premium_id for p in extract.policies for g in p.guarantee_parts]
    part_of, info = _parts_for(session, premium_ids)
    for benefit, data in sorted(info.items(), key=lambda kv: str(kv[0])):
        if set(data["parts"]) != {1}:
            problems.append(f"Förmånen {benefit} har delarna {sorted(data['parts'])}; övergången kräver bara del 1 "
                            "(delning före övergången stöds inte)")
        states = data["states"].get(1, [])
        if states != ["not_started"]:
            problems.append(f"Del 1 på förmånen {benefit} är {states or 'utan läge'} per {OPENING_DATE}, "
                            "inte not_started")
    missing = [p for p in premium_ids if p not in part_of]
    if missing:
        problems.append(f"{len(missing)} premierader saknar uttagsdel 1, t.ex. {missing[0]} – kör steg 1:s övergång först")

    guarantee_rows, by_policy_g, part_of_policy = [], defaultdict(Decimal), defaultdict(set)
    origin_row = {}
    for policy in extract.policies:
        born = _model_birth(policy.birth_month, policy.born_on_first)
        for g in policy.guarantee_parts:
            part = part_of.get(g.premium_id)
            if part is None:
                continue
            value_date = month_end(g.received_month)
            row_id = stable_id(OPENING_KIND, "guarantee", g.premium_id)
            origin_row[g.premium_id] = row_id
            part_of_policy[policy.policy_id].add(part)
            guarantee_rows.append({
                "id": row_id, "payout_part_id": part, "origin_kind": "s04_premium",
                "premium_transaction_id": uuid.UUID(g.premium_id), "payment_allocation_id": None,
                "premium_sek": g.premium, "period_month": g.period_month, "received_month": g.received_month,
                "value_date": value_date, "plan_kind": "reference_lifelong",
                "plan_start": aa.reference_start(born, value_date), "basis_code": g.basis,
                "basis_checksum": extract.bases[g.basis], "factor": g.factor, "guarantee_sek_per_month": g.guarantee,
                "version": 1, "reason": "premium", "supersedes_id": None, "source": S04})
            by_policy_g[policy.policy_id] += g.guarantee
    entry_rows, by_policy_c = [], defaultdict(Decimal)
    for o in origins:
        part = part_of.get(o.id)
        if part is None:
            continue
        entry_rows.append({
            "id": stable_id(OPENING_KIND, "entry", o.id), "account": CUSTOMER, "payout_part_id": part,
            "origin_id": origin_row[o.id], "month": OPENING_DATE.replace(day=1), "reason": "opening",
            "amount_sek": o.capital, "balance_before_sek": ZERO, "balance_after_sek": o.capital, "source": S04})
        by_policy_c[o.policy_id] += o.capital

    controls = _opening_controls(extract, expected_extract_checksum, replay, origins, guarantee_rows, entry_rows,
                                 by_policy_c, by_policy_g, part_of_policy)
    rows_digest = vb.checksum({
        "guarantee_parts": [_plain(r) for r in guarantee_rows], "entries": [_plain(r) for r in entry_rows]})
    content = {
        "method": METHOD, "kind": OPENING_KIND, "opening_date": OPENING_DATE.isoformat(), "source": S04,
        "design": "P1-PENSION-001 §6.2", "extract_checksum": extract.checksum, "replay_checksum": replay,
        "origin_method": origin_code_version(), "rows_checksum": rows_digest,
        "totals": {"policies": len(extract.policies), "guarantee_parts": len(guarantee_rows),
                   "capital_tracks": len(entry_rows),
                   "payout_parts": len({part for parts in part_of_policy.values() for part in parts}),
                   "capital_sek": str(sum((r["amount_sek"] for r in entry_rows), ZERO)),
                   "guarantee_sek_per_month": str(sum((r["guarantee_sek_per_month"] for r in guarantee_rows),
                                                      Decimal(0)))},
        "not_transferred": [n.model_dump(mode="json") for n in extract.not_calculated],
        "outside_population": extract.outside_population,
        "controls": [c.as_dict() for c in controls],
    }
    return OpeningPlan(extract=extract, replay_checksum=replay, guarantee_rows=guarantee_rows, entry_rows=entry_rows,
                       controls=controls, content=content, checksum=vb.checksum(content), problems=problems)


def _plain(row: dict) -> dict:
    return {k: (str(v) if isinstance(v, (uuid.UUID, Decimal, date)) else v) for k, v in row.items()}


def _opening_controls(extract, expected, replay, origins, guarantee_rows, entry_rows, by_policy_c, by_policy_g,
                      part_of_policy) -> list[Control]:
    s04_c = sum((p.capital for p in extract.policies), ZERO)
    s04_g = sum((g.guarantee for p in extract.policies for g in p.guarantee_parts), Decimal(0))
    c = sum((r["amount_sek"] for r in entry_rows), ZERO)
    g = sum((r["guarantee_sek_per_month"] for r in guarantee_rows), Decimal(0))
    wrong_c = [p.policy_id for p in extract.policies if by_policy_c.get(p.policy_id, ZERO) != p.capital]
    wrong_g = [p.policy_id for p in extract.policies
               if by_policy_g.get(p.policy_id, Decimal(0)) != sum((x.guarantee for x in p.guarantee_parts), Decimal(0))]
    parts = [g_.premium_id for p in extract.policies for g_ in p.guarantee_parts]
    several = [p for p, ps in part_of_policy.items() if len(ps) != 1]
    closing = extract.months[-1].closing if extract.months else ZERO
    sources = {"extract": extract.checksum, "replay": replay}
    return [
        Control("utdragets kontrollsumma", extract.approved and (expected is None or extract.checksum == expected),
                ("S-04 godkänt" if extract.approved else "S-04 underkänt")
                + ("" if expected is None else f"; väntad hash {expected[:6]}…{expected[-5:]}"),
                expected=expected, actual=extract.checksum, sources=sources),
        Control("ursprungsspårens uppspelning", len(origins) == len(parts),
                f"{len(origins)} spår ur {len(extract.months)} månader, varje månad i ören lika med S-04",
                expected=str(len(parts)), actual=str(len(origins)), sources=sources),
        Control("kapital per försäkring", not wrong_c,
                ", ".join(wrong_c[:5]) or f"Alla {len(extract.policies)} försäkringar exakt i ören",
                expected="0", actual=str(len(wrong_c)), sources=sources),
        Control("garanti per försäkring", not wrong_g,
                ", ".join(wrong_g[:5]) or f"Alla {len(extract.policies)} försäkringar exakt i tio decimaler",
                expected="0", actual=str(len(wrong_g)), sources=sources),
        Control("kapital totalt", c == s04_c == closing, f"ΣC i journalen {c} kr mot S-04 {s04_c} kr",
                expected=str(s04_c), actual=str(c), difference=c - s04_c, sources=sources),
        Control("garanti totalt", g == s04_g, f"ΣG i journalen {g} kr/mån mot S-04 {s04_g} kr/mån",
                expected=str(s04_g), actual=str(g), difference=g - s04_g, sources=sources),
        Control("garantidelar", len(guarantee_rows) == len(parts) == len(set(parts)),
                f"{len(guarantee_rows)} garantidelar, en per premierad i S-04",
                expected=str(len(parts)), actual=str(len(guarantee_rows)), sources=sources),
        Control("uttagsdelar", not several and len(part_of_policy) == len(extract.policies),
                ", ".join(several[:5]) or "Varje försäkring har sina garantidelar och spår på exakt en uttagsdel",
                expected=str(len(extract.policies)), actual=str(len(part_of_policy)), sources=sources),
        Control("ej överförda", True,
                f"{len(extract.not_calculated)} försäkringar beräknas inte i S-04 och förs inte över"
                + (": " + ", ".join(sorted({n.reason for n in extract.not_calculated})) if extract.not_calculated else ""),
                expected=None, actual=str(len(extract.not_calculated)), sources=sources),
    ]


def store_extract(session: Session, extract: ValuationExtract, actor: str) -> ValuationExtractRecord:
    """Sparar utdraget en gång (unik kontrollsumma), som värderingsmotorn gör."""
    row = session.scalar(select(ValuationExtractRecord).where(ValuationExtractRecord.checksum == extract.checksum))
    if row is None:
        row = ValuationExtractRecord(
            valuation_date=extract.valuation_date, source=extract.source, checksum=extract.checksum,
            approved=extract.approved, policies=len(extract.policies),
            guarantee_parts=sum(len(p.guarantee_parts) for p in extract.policies),
            capital_sek=sum((p.capital for p in extract.policies), ZERO),
            content=extract.model_dump(mode="json"), created_by=actor)
        session.add(row)
        session.flush()
    return row


def apply_opening(session: Session, actor: str, reviewed_checksum: str,
                  expected_extract_checksum: str | None = None) -> tuple[LedgerBatch, bool]:
    """Bokar det ingående läget med granskningens kontrollsumma. (verifikation, ny) – idempotent."""
    if session.bind.dialect.name == "postgresql":
        session.execute(select(func.pg_advisory_xact_lock(6047, OPENING_DATE.toordinal())))
    existing = opening_batch(session)
    if existing is not None:
        if existing.checksum != reviewed_checksum:
            raise LedgerConflict("Journalens ingående läge finns redan med annat innehåll; en rättelse blir en ny "
                                 "länkad verifikation, inte en ny övergång")
        verify_opening(session, existing)
        return existing, False
    plan = plan_opening(session, expected_extract_checksum)
    if plan.checksum != reviewed_checksum:
        raise LedgerConflict("Underlaget har ändrats sedan granskningen – granska övergången igen")
    if not plan.passed:
        failed = [c.step for c in plan.controls if not c.passed]
        raise LedgerError("Övergången stoppas: " + "; ".join(plan.problems + [f"kontrollen {f} avviker" for f in failed]))
    record = store_extract(session, plan.extract, actor)
    batch = LedgerBatch(id=stable_id(OPENING_KIND, "batch", plan.extract.checksum), kind=OPENING_KIND,
                        period_end=OPENING_DATE, source=S04, extract_id=record.id,
                        extract_checksum=plan.extract.checksum, content=plan.content, checksum=plan.checksum,
                        created_by=actor)
    session.add(batch)
    session.flush()
    session.bulk_insert_mappings(LedgerGuaranteePart, [{**r, "batch_id": batch.id, "created_by": actor}
                                                       for r in plan.guarantee_rows])
    session.bulk_insert_mappings(LedgerCapitalEntry, [{**r, "batch_id": batch.id, "created_by": actor}
                                                      for r in plan.entry_rows])
    session.add_all(LedgerControl(id=stable_id(OPENING_KIND, "control", c.step), batch_id=batch.id, step=c.step,
                                  expected=c.expected, actual=c.actual, difference=c.difference, sources=c.sources,
                                  passed=c.passed, detail=c.detail) for c in plan.controls)
    session.flush()
    verify_opening(session, batch)
    return batch, True


class LedgerConflict(LedgerError):
    """Samma bokning med annat innehåll, eller ändrat underlag mellan granskning och bokning."""


def verify_opening(session: Session, batch: LedgerBatch) -> None:
    """Prövar det bokade ingående läget mot verifikationens sammanställning och det sparade utdraget."""
    if vb.checksum(batch.content) != batch.checksum:
        raise LedgerError("Verifikationens sammanställning har ändrats")
    record = session.get(ValuationExtractRecord, batch.extract_id)
    if record is None or record.checksum != batch.extract_checksum:
        raise LedgerError("Det sparade S-04-utdraget saknas eller har annan kontrollsumma")
    totals = batch.content["totals"]
    count, capital = session.execute(
        select(func.count(), func.coalesce(func.sum(LedgerCapitalEntry.amount_sek), 0))
        .where(LedgerCapitalEntry.batch_id == batch.id)).one()
    # G summeras i Python: SQLite summerar NUMERIC som flyttal, och G har tio decimaler
    values = session.scalars(select(LedgerGuaranteePart.guarantee_sek_per_month)
                             .where(LedgerGuaranteePart.batch_id == batch.id)).all()
    found = (count, Decimal(str(capital)).quantize(Decimal("0.01")), len(values), sum(values, Decimal(0)))
    wanted = (totals["capital_tracks"], Decimal(totals["capital_sek"]), totals["guarantee_parts"],
              Decimal(totals["guarantee_sek_per_month"]))
    if found[:3] != wanted[:3] or found[3].quantize(Decimal("1e-10")) != wanted[3].quantize(Decimal("1e-10")):
        raise LedgerError(f"Journalens rader stämmer inte med verifikationen ({found} mot {wanted})")
    failed = session.scalars(select(LedgerControl.step).where(LedgerControl.batch_id == batch.id,
                                                               LedgerControl.passed.is_(False))).all()
    if failed:
        raise LedgerError(f"Verifikationen har underkända kontroller: {', '.join(failed)}")


# --- Läsningar ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Track:
    """Ett kapitalspår: uttagsdel och ursprung med saldo, försäkring och ursprungets referens."""

    payout_part_id: uuid.UUID
    origin_id: uuid.UUID
    policy_id: str
    origin_ref: str
    balance: Decimal


def policy_of_parts(session: Session, part_ids) -> dict[uuid.UUID, str]:
    part_ids = list(part_ids)
    out = {}
    for start in range(0, len(part_ids), 5000):
        out.update({part: str(policy) for part, policy in session.execute(
            select(PayoutPart.id, PolicyBenefit.policy_id).join(PolicyBenefit, PolicyBenefit.id == PayoutPart.benefit_id)
            .where(PayoutPart.id.in_(part_ids[start:start + 5000])))})
    return out


def origin_ref(row: LedgerGuaranteePart) -> str:
    """Ursprungets referens i utdraget: premieradens id för S-04, allokeringens id för paket A."""
    return str(row.premium_transaction_id if row.origin_kind == "s04_premium" else row.payment_allocation_id)


def guarantee_parts(session: Session, on: date) -> list[LedgerGuaranteePart]:
    """Gällande garantidelar per dagen: värdedag senast `on` och inte ersatta av en senare version."""
    rows = list(session.scalars(select(LedgerGuaranteePart).where(LedgerGuaranteePart.value_date <= on)
                                .order_by(LedgerGuaranteePart.received_month, LedgerGuaranteePart.id)))
    superseded = {r.supersedes_id for r in rows if r.supersedes_id is not None}
    return [r for r in rows if r.id not in superseded]


def tracks(session: Session, on: date) -> list[Track]:
    """Kundkapitalets spår med saldo per dagen: summan av spårets poster till och med månaden."""
    month = on.replace(day=1)
    rows = session.execute(
        select(LedgerCapitalEntry.payout_part_id, LedgerCapitalEntry.origin_id,
               func.sum(LedgerCapitalEntry.amount_sek))
        .where(LedgerCapitalEntry.account == CUSTOMER, LedgerCapitalEntry.month <= month)
        .group_by(LedgerCapitalEntry.payout_part_id, LedgerCapitalEntry.origin_id)).all()
    origins = {r.id: r for r in session.scalars(select(LedgerGuaranteePart).where(LedgerGuaranteePart.version == 1))}
    policy_of = policy_of_parts(session, {part for part, _, _ in rows})
    out = [Track(part, origin, policy_of[part], origin_ref(origins[origin]),
                 Decimal(total).quantize(Decimal("0.01"))) for part, origin, total in rows]
    return sorted(out, key=lambda t: (t.policy_id, t.origin_ref, str(t.payout_part_id)))


def opening_origins(session: Session, extract: ValuationExtract) -> tuple[list[Origin], str]:
    """Kapitalspåren per 2026-10-31 ur journalen som ursprung för P6-MANAD-001:s scenario (§6.3).

    Scenariot läser den operativa journalen i stället för att återskapa spåren ur S-04. Spårens summa
    per försäkring ska vara utdragets C; annars stoppas läsningen. Svarar med verifikationens summa
    som identitet för uppspelningen.
    """
    batch = opening_batch(session)
    if batch is None:
        raise LedgerError("Kapitaljournalen har inget ingående läge")
    verify_opening(session, batch)
    found = tracks(session, extract.valuation_date)
    origins = [Origin(t.origin_ref, t.policy_id, t.balance) for t in found]
    by_policy = defaultdict(Decimal)
    for o in origins:
        by_policy[o.policy_id] += o.capital
    if any(by_policy.get(p.policy_id, ZERO) != p.capital for p in extract.policies) or \
            set(by_policy) - {p.policy_id for p in extract.policies}:
        raise LedgerError("Journalens kapitalspår stämmer inte med utdragets kapital per försäkring")
    return sorted(origins, key=lambda o: o.id), batch.checksum


__all__ = ["CUSTOMER", "METHOD", "OPENING_DATE", "OPENING_KIND", "Control", "LedgerConflict", "LedgerError",
           "OpeningPlan", "Track", "apply_opening", "guarantee_parts", "journal_present", "opening_batch",
           "opening_origins", "origin_ref", "plan_opening", "policy_of_parts", "stable_id", "store_extract", "tracks", "verify_opening"]
