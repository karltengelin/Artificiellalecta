"""Mottagning och avstämd syntetisk månad, genom det gemensamma tjänstelagret.

Första införandet avser bara P6-MANAD-001:s frysta försöksunderlag. Inga
premium_transactions betalmarkeras och ingen huvudbok eller tillgångssida skapas.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field
from sqlalchemy import inspect, select

from models import (
    PremiumMonthClose,
    PremiumMonthJournal,
    PremiumReceipt,
    ValuationBasis,
)
from services import valuation_bases as vb
from services.contract import OperationContext, OperationKind, operation
from services.errors import (
    AccessDeniedError,
    BlockedError,
    ConflictError,
    NotFoundError,
)
from services.operations.actuarial_analysis import JsonResult
from services.operations.valuations import save_computation
from services.premium_month_analysis import change_analysis
from services.premium_month_inputs import (
    HASH,
    KEY,
    MonthInputs,
    ReceiptInput,
    Strict,
    allocate_receipt,
    receipt_key,
)
from services.premium_month_preparation import snapshot_parameters
from services.valuation import compute_valuation
from services.valuation_extract import (
    CapitalFlows,
    GuaranteePart,
    MonthTotals,
    QualityCheck,
    extract_checksum,
)
from skills.calculation import actuarial_annuity as aa
from skills.calculation import fta_valuation as fv
from skills.calculation.premium_origin_ledger import (
    Origin,
    origin_code_version,
    reconstruct_origins,
    roll_origins,
)

ZERO = Decimal("0.00")
PRECISION = Decimal("1e-10")


class OpenMonth(Strict):
    inputs_json: str = Field(max_length=30000000)
    reviewed_checksum: str = Field(pattern=HASH)


class JournalQuery(Strict):
    journal_id: str = Field(pattern=KEY)


class ReceiveInput(JournalQuery):
    receipt: ReceiptInput


class ReviewMonth(JournalQuery):
    reviewed_checksum: str = Field(pattern=HASH)


class MonthInspection(JournalQuery):
    include_sources: bool = False


def _intact(row):
    if vb.checksum(row.content) != row.checksum:
        raise BlockedError("Journalunderlagets kontrollsumma stämmer inte")
    return row.content


def _journal(session, ident, lock=False):
    if not inspect(session.connection()).has_table(PremiumMonthJournal.__tablename__):
        raise BlockedError("Månadsjournalen är inte införd i vald databas; separat granskat införande krävs")
    query = select(PremiumMonthJournal).where(PremiumMonthJournal.id == ident)
    row = session.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise NotFoundError("Månadsjournalen saknas")
    _intact(row)
    return row


def _package(row):
    return MonthInputs.model_validate(row.content["inputs"])


def _close(session, ident):
    row = session.scalar(select(PremiumMonthClose).where(PremiumMonthClose.journal_id == ident))
    if row:
        _intact(row)
    return row


def _verify_closed_sources(session, journal, closed):
    rows = _receipts(session, journal.id)
    sources = closed.content["sources"]
    if (sources["journal"] != journal.checksum or sources["receipts"] != [r.checksum for r in rows]):
        raise BlockedError("Månadsunderlagets källor har ändrats sedan stängningen")


def _receipts(session, ident):
    rows = list(session.scalars(select(PremiumReceipt).where(PremiumReceipt.journal_id == ident)
                               .order_by(PremiumReceipt.received_date, PremiumReceipt.id)))
    for row in rows:
        _intact(row)
    return rows


def _snapshots_match(session, p):
    for snapshot in p.bases:
        row = session.scalar(select(ValuationBasis).where(ValuationBasis.code == snapshot.code))
        if (row is None or row.status != "adopted" or row.checksum != snapshot.checksum
                or vb.checksum(row.assumptions) != snapshot.checksum):
            raise BlockedError("Den frysta grundversionen saknas eller har ändrats")
    actual = {r["checksum"] for r in snapshot_parameters(session)}
    if any(r["checksum"] not in actual for r in p.parameters):
        raise BlockedError("De frysta produktparametrarna har ändrats")


def _serialize_origins(origins):
    out = []
    for o in origins:
        body = {"id": o.id, "policy_id": o.policy_id, "capital": str(o.capital)}
        out.append({**body, "checksum": vb.checksum(body)})
    return out


def _origins(rows):
    return [Origin(r["id"], r["policy_id"], Decimal(r["capital"])) for r in rows]


def _save(session, computation, actor, reason):
    return save_computation(session, computation, actor, reason)


def month_summary(session, journal) -> dict:
    p = _package(journal)
    closed = _close(session, journal.id)
    receipts = _receipts(session, journal.id)
    return {"journal_id": journal.id, "source_checksum": journal.checksum, "inputs_checksum": p.checksum,
        "opening_checksum": p.opening.checksum, "period_end": p.period_end.isoformat(), "synthetic": True,
        "scenario_only": True, "receipts": len(receipts), "expected_receipts": len(p.receipts),
        "state": "approved_analysis" if closed and closed.approved_by else "review_required" if closed else "open",
        "review_checksum": closed.checksum if closed else None}


@operation(name="open_premium_month", kind=OperationKind.WRITE, pii=True,
           rules=["PR-ITP1-018", "PR-ITP1-020", "PR-ITP1-031"],
           description="Öppnar ett granskat syntetiskt månadsförsök med fryst S-04 och rekonstruerade kapitalspår.")
def open_month(ctx: OperationContext, data: OpenMonth) -> JsonResult:
    if ctx.actor.is_agent:
        raise AccessDeniedError("Försöksunderlaget öppnas av människa eller betrodd systemkod",
                                operation="open_premium_month", actor_id=ctx.actor.id)
    session = ctx.require_session()
    p = MonthInputs.model_validate_json(data.inputs_json)
    if not p.checksum or p.checksum != data.reviewed_checksum:
        raise BlockedError("Försöksunderlaget har inte samma kontrollsumma som det granskade")
    existing = session.get(PremiumMonthJournal, p.scenario_id)
    if existing:
        _intact(existing)
        if _package(existing).checksum != p.checksum:
            raise ConflictError("Scenario-ID finns med annat underlag; rättelse kräver ny version")
        return JsonResult(payload=month_summary(session, existing))
    _snapshots_match(session, p)
    origins, replay = reconstruct_origins(p.opening)
    c = compute_valuation(session, p.opening.valuation_date, "scenario", basis_code=p.opening_basis_code,
                          curve_code=p.opening_curve_code, extract=p.opening)
    run = _save(session, c, ctx.actor.id, ctx.reason or "")
    content = {"inputs": p.model_dump(mode="json"), "origins": _serialize_origins(origins),
               "replay_checksum": replay, "origin_method": origin_code_version(), "opening_run_id": str(run.id),
               "opening_fta_sek": str(c.totals.fta), "opening_result_checksum": c.result_checksum,
               "code_version": c.code_version}
    row = PremiumMonthJournal(id=p.scenario_id, content=content, checksum=vb.checksum(content), created_by=ctx.actor.id)
    session.add(row)
    session.flush()
    return JsonResult(payload=month_summary(session, row))


@operation(name="receive_premium_payment", kind=OperationKind.WRITE, pii=True,
           rules=["PR-ITP1-008", "PR-ITP1-018", "PR-ITP1-020", "PR-ITP1-031"],
           description="Matchar en granskad syntetisk betalning och skapar kapital- och garantispår exakt en gång.")
def receive_payment(ctx: OperationContext, data: ReceiveInput) -> JsonResult:
    session = ctx.require_session()
    journal = _journal(session, data.journal_id, lock=True)
    p, r = _package(journal), data.receipt
    ident = receipt_key(journal.id, r)
    existing = session.get(PremiumReceipt, ident)
    if existing:
        body = _intact(existing)
        if body["receipt"] != r.economic_content():
            raise ConflictError("Samma ekonomiska original-ID har ändrat innehåll")
        return JsonResult(payload={"receipt_id": ident, "checksum": existing.checksum, "reused": True})
    if _close(session, journal.id):
        raise BlockedError("Månaden är stängd; ingen ny effekt får läggas ovanpå avslutet")
    expected = {receipt_key(journal.id, item): item for item in p.receipts}
    if ident not in expected or expected[ident].economic_content() != r.economic_content():
        raise BlockedError("Mottagningen motsvarar inte det granskade försöksunderlaget")
    rows = _receipts(session, journal.id)
    received_ids = {row.id for row in rows}
    remaining = sorted((item for key, item in expected.items() if key not in received_ids),
                       key=lambda item: (item.received_date, receipt_key(journal.id, item)))
    if not remaining or receipt_key(journal.id, remaining[0]) != ident:
        raise BlockedError("Mottagningarna ska behandlas i fryst datum-/originalordning")
    invoice = next((i for i in p.invoices if i.id == r.invoice_id), None)
    allocated = {}
    for row in rows:
        if row.content["receipt"]["invoice_id"] == r.invoice_id:
            for item in row.content["allocations"]:
                allocated[item["line_id"]] = allocated.get(item["line_id"], ZERO) + Decimal(item["net_sek"])
    shares, remainder = allocate_receipt(invoice, r, allocated) if invoice else ({}, r.net_sek)
    allocations = []
    guarantee = next(b for b in p.bases if b.code == "SIM-G-2026-01")
    if not (guarantee.valid_from <= r.value_date and (guarantee.valid_to is None or guarantee.valid_to >= r.value_date)):
        raise BlockedError("Ingen fryst garantitariff gäller vid mottagningen")
    mortality, rate = aa.basis_from_assumptions(guarantee.assumptions)
    policies = {x.policy_id: x for x in p.opening.policies}
    for line in invoice.lines if invoice else []:
        amount = shares.get(line.id, ZERO)
        if amount == 0:
            continue
        policy = policies[line.policy_id]
        year, month = map(int, policy.birth_month.split("-"))
        born = r.value_date.replace(year=year, month=month, day=1 if policy.born_on_first else 2)
        g, factor = aa.guarantee_part(mortality, born, r.value_date, amount, net_interest_rate=rate)
        allocation_id = vb.checksum({"original": ident, "invoice": invoice.id, "line": line.id})
        allocations.append({"id": allocation_id, "line_id": line.id, "policy_id": line.policy_id,
            "benefit_id": line.benefit_id, "period_month": line.period_month.isoformat(), "net_sek": str(amount),
            "value_date": r.value_date.isoformat(), "source_checksum": r.source.checksum,
            "invoice_checksum": invoice.source.checksum, "basis_code": guarantee.code,
            "basis_checksum": guarantee.checksum, "plan": policy.plan.model_dump(mode="json"),
            "factor": str(Decimal(repr(factor)).quantize(PRECISION)),
            "guarantee_sek_per_month": str(Decimal(repr(g)).quantize(PRECISION)), "synthetic": True})
    for allocation in allocations:
        allocation["checksum"] = vb.checksum(allocation)
    if sum((Decimal(x["net_sek"]) for x in allocations), ZERO) + remainder != r.net_sek:
        raise BlockedError("Mottagningsavstämningen stämmer inte")
    content = {"receipt": r.economic_content(), "allocations": allocations, "unallocated_sek": str(remainder),
               "source_journal_checksum": journal.checksum}
    row = PremiumReceipt(id=ident, journal_id=journal.id, source_system=r.source.system,
        source_event_id=r.event_id, received_date=r.received_date, content=content,
        checksum=vb.checksum(content), created_by=ctx.actor.id)
    session.add(row)
    session.flush()
    return JsonResult(payload={"receipt_id": ident, "checksum": row.checksum, "reused": False})


def _model(session, basis_code, curve_code, tax):
    basis = session.scalar(select(ValuationBasis).where(ValuationBasis.code == basis_code))
    curve = session.scalar(select(ValuationBasis).where(ValuationBasis.code == curve_code))
    vb.verify_checksum(basis)
    vb.verify_checksum(curve)
    return fv.ValuationModel.from_assumptions(basis.assumptions, curve.assumptions, float(tax))


@operation(name="close_premium_month", kind=OperationKind.WRITE, pii=True,
           rules=["PR-ITP1-018", "PR-ITP1-020", "PR-ITP1-028", "PR-ITP1-031"],
           description="Stänger det syntetiska månadsförsöket med oberoende A6-värdering och strikt avstämd FTA-brygga.")
def close_month(ctx: OperationContext, data: JournalQuery) -> JsonResult:
    session = ctx.require_session()
    journal = _journal(session, data.journal_id, lock=True)
    previous = _close(session, journal.id)
    if previous:
        _verify_closed_sources(session, journal, previous)
        return JsonResult(payload=month_summary(session, journal))
    p = _package(journal)
    if journal.content["origin_method"] != origin_code_version():
        raise BlockedError("Ursprungsmodellens kod har ändrats; nytt granskat försök krävs")
    _snapshots_match(session, p)
    rows = _receipts(session, journal.id)
    if {r.id for r in rows} != {receipt_key(journal.id, r) for r in p.receipts}:
        raise BlockedError("Alla källhändelser är inte avstämda")
    allocations = [a for r in rows for a in r.content["allocations"]]
    additions = [Origin(a["id"], a["policy_id"], Decimal(a["net_sek"])) for a in allocations]
    period = p.period_end.replace(day=1)
    fee, tax, fee_label, tax_label = parameters_for_month(session, period)
    avk = vb.in_force(session, "AVK-SIM", p.period_end)
    if avk is None:
        raise BlockedError("Antagen avkastningsserie saknas")
    vb.verify_checksum(avk)
    old_returns = next(b for b in p.bases if b.code == "AVK-SIM-2026-01").assumptions["months"]
    if avk.assumptions["months"][:len(old_returns)] != old_returns:
        raise BlockedError("Den nya AVK-serien skriver om IB:s historik")
    rates = {m["month"]: Decimal(m["rate"]) for m in avk.assumptions["months"]}
    if rates.get(period.isoformat()) != p.november_return:
        raise BlockedError("Novemberavkastning saknas eller motsvarar inte granskad version")
    origins, entries, month = roll_origins(period, p.november_return, _origins(journal.content["origins"]),
        additions, fee_rate=fee, tax_rate=tax)
    parameter_refs = {}
    for key in ("capital_fee_rate", "customer_tax_rate"):
        found = [row for row in p.parameters if row["key"] == key and row["valid_from"] <= period.isoformat()
                 and (row["valid_to"] is None or row["valid_to"] >= period.isoformat())]
        if len(found) != 1:
            raise BlockedError("Exakt en fryst kapitalparameter ska gälla månaden")
        parameter_refs[key] = {"version": found[0]["label"], "checksum": found[0]["checksum"]}
    origins_by_id = {a["id"]: a for a in allocations}
    for entry in entries:
        entry["id"] = vb.checksum({"journal": journal.id, "origin": entry["origin_id"],
                                    "month": entry["month"], "kind": entry["kind"]})
        entry["method_version"] = origin_code_version()
        entry["journal_checksum"] = journal.checksum
        if entry["kind"] == "return":
            entry["basis"] = {"version": avk.code, "checksum": avk.checksum}
        elif entry["kind"] in ("fee", "tax"):
            entry["basis"] = parameter_refs["capital_fee_rate" if entry["kind"] == "fee" else "customer_tax_rate"]
        else:
            allocation = origins_by_id[entry["origin_id"]]
            entry["basis"] = {"version": allocation["basis_code"], "checksum": allocation["basis_checksum"]}
            entry["receipt_source_checksum"] = allocation["source_checksum"]
        entry["checksum"] = vb.checksum(entry)
    by_policy, parts = {}, {}
    for o in origins:
        by_policy[o.policy_id] = by_policy.get(o.policy_id, ZERO) + o.capital
    for a in allocations:
        parts.setdefault(a["policy_id"], []).append(GuaranteePart(premium_id=a["id"],
            period_month=a["period_month"], received_month=period, premium=a["net_sek"], basis=a["basis_code"],
            factor=a["factor"], guarantee=a["guarantee_sek_per_month"]))
    extract = p.opening.model_copy(deep=True)
    extract.source, extract.valuation_date = "ledger", p.period_end
    extract.parameters = {**extract.parameters, "premium_journal": [journal.checksum, *[r.checksum for r in rows]]}
    extract.parameters["capital_fee_rate"] = sorted(set(extract.parameters["capital_fee_rate"] + [fee_label]))
    extract.parameters["customer_tax_rate"] = sorted(set(extract.parameters["customer_tax_rate"] + [tax_label]))
    extract.bases = {**extract.bases, avk.code: avk.checksum,
                     **{a["basis_code"]: a["basis_checksum"] for a in allocations}}
    for policy in extract.policies:
        line = month.lines[policy.policy_id]
        policy.source, policy.capital = "ledger", by_policy[policy.policy_id]
        policy.guarantee_parts += sorted(parts.get(policy.policy_id, []), key=lambda g: g.premium_id)
        policy.flows = CapitalFlows(premiums=policy.flows.premiums+line.premiums,
            returns=policy.flows.returns+line.investment_return, fees=policy.flows.fees+line.fee,
            taxes=policy.flows.taxes+line.tax)
    extract.months += [MonthTotals(month=period, rate=p.november_return, fee_rate=fee, tax_rate=tax,
        opening=month.total("opening"), returns=month.total("investment_return"), fees=month.total("fee"),
        taxes=month.total("tax"), fees_waived=month.total("fee_waived"), taxes_waived=month.total("tax_waived"),
        premiums=month.total("premiums"), closing=month.total("closing"))]
    extract.checks = [QualityCheck(name="Fryst IB och mottagningar", passed=True,
        detail="Källhashar, original-ID:n, hela populationen och kapitalspår avstämda")]
    extract.approved = True
    extract.checksum = extract_checksum(extract)
    c = compute_valuation(session, p.period_end, "scenario", basis_code=p.opening_basis_code,
                          curve_code=p.opening_curve_code, extract=extract)
    if c.code_version != journal.content["code_version"]:
        raise BlockedError("A6:s kodversion har ändrats mellan IB och UB; nytt granskat försök krävs")
    run = _save(session, c, ctx.actor.id, ctx.reason or "")
    model = _model(session, p.opening_basis_code, p.opening_curve_code, tax)
    sources = {"journal": journal.checksum, "receipts": [r.checksum for r in rows],
        "opening_extract": p.opening.checksum, "closing_extract": extract.checksum,
        "opening_result": journal.content["opening_result_checksum"], "closing_result": c.result_checksum,
        "basis": c.basis.checksum, "curve": c.curve.checksum, "tax": tax_label, "code": c.code_version,
        "absence_of_out_of_scope_events": p.checksum}
    analysis = change_analysis(p.opening, extract, model, model, premium_sek=month.total("premiums"),
        expected_opening=Decimal(journal.content["opening_fta_sek"]), expected_closing=c.totals.fta, sources=sources)
    content = {"extract": extract.model_dump(mode="json"), "origins": _serialize_origins(origins),
        "entries": entries, "sources": sources, "analysis": analysis, "closing_run_id": str(run.id),
        "capital_movements": extract.months[-1].model_dump(mode="json"),
        "unallocated_sek": str(sum((Decimal(r.content["unallocated_sek"]) for r in rows), ZERO)),
        "contributing_policies": len({a["policy_id"] for a in allocations})}
    row = PremiumMonthClose(id=vb.checksum({"journal": journal.id, "period": p.period_end.isoformat()}),
        journal_id=journal.id, period_end=p.period_end, content=content, checksum=vb.checksum(content),
        created_by=ctx.actor.id)
    session.add(row)
    session.flush()
    return JsonResult(payload=month_summary(session, journal))


def parameters_for_month(session, period):
    from services.parameters import capital_rates

    return capital_rates(session, [period])[period]


@operation(name="get_premium_month", kind=OperationKind.READ, pii=True,
           description="Visar källreferens, period och granskningsstatus för ett syntetiskt månadsförsök.")
def get_month(ctx: OperationContext, data: MonthInspection) -> JsonResult:
    session = ctx.require_session()
    journal = _journal(session, data.journal_id)
    payload = month_summary(session, journal)
    if data.include_sources:
        if ctx.actor.type != "human":
            raise AccessDeniedError("Individjournalens granskning kräver mänsklig aktör",
                                    operation="get_premium_month", actor_id=ctx.actor.id)
        closed = _close(session, journal.id)
        if closed:
            _verify_closed_sources(session, journal, closed)
        payload["sources"] = {"opening": journal.content,
            "receipts": [{"id": r.id, "checksum": r.checksum, "content": r.content}
                         for r in _receipts(session, journal.id)], "closing": closed.content if closed else None}
    return JsonResult(payload=payload)


@operation(name="approve_premium_month", kind=OperationKind.WRITE, rules=["PR-ITP1-031"],
           description="Människan godkänner exakt granskat analysunderlag; en scenariovärdering låses aldrig.")
def approve_month(ctx: OperationContext, data: ReviewMonth) -> JsonResult:
    if ctx.actor.type != "human":
        raise AccessDeniedError("Analysleveransen godkänns av människa",
                                operation="approve_premium_month", actor_id=ctx.actor.id)
    session = ctx.require_session()
    journal = _journal(session, data.journal_id, lock=True)
    row = _close(session, journal.id)
    if row is None or row.checksum != data.reviewed_checksum:
        raise ConflictError("Månadsunderlaget saknas eller skiljer sig från det granskade")
    _verify_closed_sources(session, journal, row)
    _snapshots_match(session, _package(journal))
    from services.operations.actuarial_analysis import _saved

    _saved(session, UUID(journal.content["opening_run_id"]))
    _saved(session, UUID(row.content["closing_run_id"]))
    if Decimal(row.content["analysis"]["unexplained_sek"]) != 0:
        raise BlockedError("Oförklarad differens stoppar godkännandet")
    if not row.approved_by:
        row.approved_by, row.approved_at = ctx.actor.id, datetime.now(UTC)
    return JsonResult(payload=month_summary(session, journal))


def analyse_month(session, query):
    """Betrott systemsteg: bara skyddad FTA-brygga ut, aldrig individjournalen."""
    from services.operations.actuarial_analysis import _saved, _scenario_model
    from services.valuation import policy_inputs

    journal = _journal(session, query.journal_id)
    closed = _close(session, journal.id)
    if closed is None:
        raise BlockedError("Stäng och stäm av månaden före förändringsanalysen")
    _verify_closed_sources(session, journal, closed)
    p = _package(journal)
    old_run, old_extract, old_model = _saved(session, UUID(journal.content["opening_run_id"]))
    new_run, new_extract, base_model = _saved(session, UUID(closed.content["closing_run_id"]))
    model = _scenario_model(base_model, query)
    independent_ub = fv.totals(fv.value_policies(model, new_run.valuation_date, policy_inputs(new_extract)))
    sources = {**closed.content["sources"], "monthly_close": closed.checksum,
               "scenario": vb.checksum(query.model_dump(mode="json"))}
    payload = change_analysis(old_extract, new_extract, old_model, model,
        premium_sek=Decimal(closed.content["capital_movements"]["premiums"]),
        expected_opening=old_run.fta_sek, expected_closing=independent_ub.fta, sources=sources)
    hidden = (0 < len(p.opening.policies) < 10 or 0 < closed.content["contributing_policies"] < 10)
    if hidden:
        payload = {"rows": [], "status": "suppressed", "reason": "Småcellsskydd för population eller premieeffekt"}
    else:
        payload["capital_movements"] = closed.content["capital_movements"]
        payload["unallocated_sek"] = closed.content["unallocated_sek"]
    payload["sources"] = [journal.checksum, closed.checksum, sources["scenario"]]
    return payload, hidden
