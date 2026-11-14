"""Värderingens datautdrag ur den operativa journalen: källan `ledger` (paket B steg 2, B-047 punkt 4, B-042).

A6 (`services.valuation.compute_valuation`) läser journalen med `source="ledger"` i stället för att
rekonstruera S-04 ur premiehistoriken (P1-PENSION-001 §6, PB4). Utdraget har samma form som S-04
(`ValuationExtract`), så värderingen, segmenten och kontrollerna är oförändrade:

- **Kapital** per försäkring är summan av kundkapitalets spår på dess uttagsdelar per dagen.
- **Garantidelar** är journalens gällande versioner: P_j, mottagning, grund, A_g och G_j. Ursprungets
  referens är premieraden för S-04 och allokeringen för paket A.
- **Historik:** månadssummor och flöden före övergången kommer ur det sparade S-04-utdraget som
  verifikationen pekar ut; ingen historik bokas om. Månader efter övergången kommer ur journalens
  stängningar (steg 3).
- **Ej beräknat:** försäkringarna som inte fördes över, med S-04:s orsak, och försäkringar vars
  uttagsdel har startat vid dagen (pensionsdelen värderas när steg 4–7 finns).

Journalen ger ett utdrag bara för en dag den har ett stängt läge för: i steg 2 det ingående läget
per 2026-10-31. Andra dagar blockeras tills månadsstängningen finns (steg 3).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from analytics.portfolio_snapshot import birth_date
from models import (
    InsuredPerson,
    LedgerGuaranteePart,
    Policy,
    PolicyState,
    ValuationBasis,
    ValuationExtractRecord,
)
from services import capital_ledger as cl
from services import valuation_bases as vb
from services.payout_parts import parts_by_policy, summary_state
from services.valuation_extract import (
    CALCULATED_STATES,
    NOT_CALCULATED,
    PAYOUT_REASONS,
    CapitalFlows,
    ExtractError,
    ExtractPolicy,
    GuaranteePart,
    NotCalculated,
    Plan,
    QualityCheck,
    ValuationExtract,
    extract_checksum,
    month_end,
)
from skills.calculation import actuarial_annuity as aa

SOURCE = "ledger"
ZERO = Decimal("0.00")


def covered_dates(session: Session) -> list[date]:
    """Dagarna journalen har ett stängt läge för. I steg 2: det ingående läget."""
    batch = cl.opening_batch(session)
    return [batch.period_end] if batch is not None else []


def _opening_extract(session: Session, batch) -> ValuationExtract:
    record = session.get(ValuationExtractRecord, batch.extract_id)
    if record is None or record.checksum != batch.extract_checksum:
        raise ExtractError("Det sparade S-04-utdraget som journalen öppnades med saknas")
    extract = ValuationExtract.model_validate(record.content)
    if extract_checksum(extract) != batch.extract_checksum:
        raise ExtractError("Det sparade S-04-utdraget har ändrat innehåll")
    return extract


def build_ledger_extract(session: Session, valuation_date: date) -> ValuationExtract:
    """Bygger värderingens utdrag ur journalen per ett månadsslut (källan `ledger`). Skriver ingenting."""
    if valuation_date != month_end(valuation_date):
        raise ExtractError("Värderingsdatumet ska vara ett månadsslut")
    batch = cl.opening_batch(session)
    if batch is None:
        raise ExtractError("Kapitaljournalen har inget ingående läge – övergången från S-04 är inte gjord")
    try:
        cl.verify_opening(session, batch)
    except cl.LedgerError as exc:
        raise ExtractError(str(exc)) from exc
    if valuation_date not in covered_dates(session):
        raise ExtractError(f"Journalen har inget stängt läge per {valuation_date}; den har "
                           f"{', '.join(map(str, covered_dates(session)))}. Månadsstängningen byggs i paket B steg 3")
    opening = _opening_extract(session, batch)

    parts = cl.guarantee_parts(session, valuation_date)
    found_tracks = cl.tracks(session, valuation_date)
    policy_of = cl.policy_of_parts(session, {r.payout_part_id for r in parts})
    g_by_policy, c_by_policy = defaultdict(list), defaultdict(lambda: ZERO)
    for row in parts:
        g_by_policy[policy_of[row.payout_part_id]].append(row)
    for t in found_tracks:
        c_by_policy[t.policy_id] += t.balance
    journal_policies = set(g_by_policy) | set(c_by_policy)

    policies = session.execute(
        select(Policy.id, InsuredPerson.personal_id_number).join(InsuredPerson, InsuredPerson.id == Policy.insured_person_id)
        .where(Policy.start_date <= valuation_date).order_by(Policy.id)).all()
    db_ids = {str(p) for p, _ in policies}
    states = defaultdict(list)
    for policy_id, state in session.execute(select(PolicyState.policy_id, PolicyState.state).where(
            PolicyState.valid_from <= valuation_date,
            (PolicyState.valid_to.is_(None)) | (PolicyState.valid_to >= valuation_date))):
        states[str(policy_id)].append(state)
    payout = parts_by_policy(session, [p for p, _ in policies], on=valuation_date)
    payout = {str(k): v for k, v in payout.items()}
    flows_before = {p.policy_id: p.flows for p in opening.policies}
    not_transferred = [NotCalculated.model_validate(n) for n in batch.content["not_transferred"]]

    problems, out, not_calculated = [], [], list(not_transferred)
    for policy_id, pnr in policies:
        key = str(policy_id)
        if key not in journal_policies:
            continue
        born = birth_date(pnr)
        if born is None:
            problems.append(f"{key}: födelsedatum saknas")
            continue
        reason = PAYOUT_REASONS.get(summary_state(payout.get(key, [])))
        if reason is not None:
            not_calculated.append(NotCalculated(policy_id=key, reason=NOT_CALCULATED[reason]))
            continue
        found = states.get(key, [])
        if len(found) != 1 or found[0] not in CALCULATED_STATES:
            problems.append(f"{key}: {'inget läge' if not found else 'motstridiga eller okända lägen'}")
            continue
        model_birth = born if born.day == 1 else born.replace(day=2)
        rows = sorted(g_by_policy.get(key, []), key=lambda r: (r.received_month, cl.origin_ref(r)))
        guarantee = [GuaranteePart(premium_id=cl.origin_ref(r), period_month=r.period_month,
                                   received_month=r.received_month, premium=r.premium_sek, basis=r.basis_code,
                                   factor=r.factor, guarantee=r.guarantee_sek_per_month) for r in rows]
        flows = flows_before.get(key, CapitalFlows(premiums=ZERO, returns=ZERO, fees=ZERO, taxes=ZERO))
        out.append(ExtractPolicy(policy_id=key, birth_month=f"{born:%Y-%m}", born_on_first=born.day == 1,
                                 state=found[0], plan=Plan(kind="reference_lifelong",
                                                           start=aa.reference_start(model_birth, valuation_date)),
                                 guarantee_parts=guarantee, capital=c_by_policy.get(key, ZERO), flows=flows,
                                 source=SOURCE))
    outside = len(db_ids - journal_policies - {n.policy_id for n in not_transferred})

    used = sorted({(r.basis_code, r.basis_checksum) for r in parts})
    bases = {code: digest for code, digest in opening.bases.items() if vb.family_of(code) == "AVK-SIM"}
    bases.update(dict(used))
    checks = _checks(session, batch, valuation_date, opening, out, not_calculated, outside, problems, used,
                     len(policies), found_tracks)
    extract = ValuationExtract(valuation_date=valuation_date, source=SOURCE, bases=dict(sorted(bases.items())),
                               parameters=opening.parameters, policies=out, not_calculated=not_calculated,
                               outside_population=outside, months=opening.months, checks=checks,
                               approved=all(c.passed for c in checks))
    extract.checksum = extract_checksum(extract)
    return extract


def _checks(session, batch, valuation_date, opening, out, not_calculated, outside, problems, used, db_policies,
            found_tracks) -> list[QualityCheck]:
    accounted = len(out) + len(not_calculated) + outside + len(problems)
    checks = [
        QualityCheck(name="ingående läge", passed=True,
                     detail=f"Verifikationen {batch.checksum[:12]} med S-04 {batch.extract_checksum[:12]} och "
                            "godkända kontroller"),
        QualityCheck(name="antal försäkringar", passed=accounted == db_policies,
                     detail=f"{len(out)} i utdraget, {len(not_calculated)} ej beräknade, {outside} utan garanti och "
                            f"kapital och {len(problems)} med fel, mot {db_policies} försäkringar i beståndet"),
        QualityCheck(name="fullständiga uppgifter", passed=not problems,
                     detail="; ".join(problems[:5]) or "Alla försäkringar i journalen har födelsedag och ett läge"),
    ]
    known = {r.code: r.checksum for r in session.scalars(select(ValuationBasis).where(
        ValuationBasis.code.in_([code for code, _ in used])))}
    wrong = [code for code, digest in used if known.get(code) != digest]
    for code in known:
        try:
            vb.verify_checksum(session.scalar(select(ValuationBasis).where(ValuationBasis.code == code)))
        except vb.BasisError:
            wrong.append(code)
    checks.append(QualityCheck(name="kända grunder", passed=not wrong,
                               detail=", ".join(sorted(set(wrong))) or "Varje garantidel har en antagen grund med "
                                                                       "oförändrad kontrollsumma"))
    negative = [x.policy_id for x in out if x.capital < 0 or any(g.guarantee < 0 for g in x.guarantee_parts)]
    negative += [t.policy_id for t in found_tracks if t.balance < 0]
    checks.append(QualityCheck(name="inga negativa belopp", passed=not negative,
                               detail=", ".join(sorted(set(negative))[:5]) or "Inget negativt C, spår eller G_j"))
    # §6.2 p. 5: en premie får aldrig ge både ett S-04-ursprung och ett ursprung ur paket A
    s04 = select(LedgerGuaranteePart.premium_transaction_id).where(LedgerGuaranteePart.origin_kind == "s04_premium")
    double = session.scalar(select(func.count()).select_from(LedgerGuaranteePart).where(
        LedgerGuaranteePart.origin_kind == "payment_allocation", LedgerGuaranteePart.premium_transaction_id.in_(s04)))
    checks.append(QualityCheck(name="en källa per premie", passed=not double,
                               detail=f"{double} premierader har både S-04-ursprung och allokering" if double else
                               "Ingen premie finns både som S-04-ursprung och som allokering i paket A"))
    final = sum((x.capital for x in out), ZERO)
    closing = opening.months[-1].closing if opening.months else ZERO
    excluded = sum((t.balance for t in found_tracks if t.policy_id not in {x.policy_id for x in out}), ZERO)
    ok = final + excluded == closing if valuation_date == batch.period_end else True
    checks.append(QualityCheck(name="kapitalavstämning", passed=ok,
                               detail=f"ΣC = {final} kr ur journalens spår mot S-04:s utgående {closing} kr" if ok
                               else f"ΣC {final} kr + {excluded} kr utanför utdraget avviker från {closing} kr"))
    return checks


__all__ = ["SOURCE", "build_ledger_extract", "covered_dates"]
