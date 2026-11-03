"""Värderingskörningar: kör, läs och lås FTA-värderingen (A6, B-042, tjänstelager.md §9.8).

- `run_valuation` (write, APPROVAL i registret) bygger datautdraget, värderar beståndet och
  sparar en körning med status `draft`: utdraget med kontrollsumma, grund och kurva med
  kontrollsummor, skatteavdrag, kodversion, totaler, segment och kontroller. Körs som systemsteg
  i betrodd kod (flödet `valuation_close`, A8) eller av människa; den monteras inte för agenter.
- `list_valuation_runs` och `get_valuation_run` (read, AGENT, podden `aktuariell`) visar bara
  aggregat: totaler, segment per läge och födelsedecennium med småcellsskydd och ej beräknade
  fall per orsak. De läser aldrig utdraget med individrader (`valuation_extracts`).
- `lock_valuation` (write, HUMAN_ONLY) fastställer en basvärdering efter att kontrollerna, utdragets
  och grundernas kontrollsummor prövats igen. En låst värdering ändras inte; en ny låsning för
  samma datum ersätter den gamla (status `superseded`) och pekar på den. Scenarier låses aldrig.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from analytics.portfolio_snapshot import MIN_CELL, suppress_counts
from models import ValuationBasis, ValuationExtractRecord, ValuationResult, ValuationRun
from services import valuation_bases as vb
from services.contract import OperationContext, OperationKind, operation
from services.errors import (
    AccessDeniedError,
    BlockedError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
)
from services.operations.product_report_data import STATE_LABELS
from services.valuation import (
    QUANTITIES,
    SOURCE_NOTE,
    Computation,
    ValuationError,
    compute_valuation,
)

ORE = Decimal("0.01")
CODE_PATTERN = r"^(SIM-V|FI-SIM)-\d{4}-\d{2}$"
AMOUNTS = ("capital_sek", "fta_sek", "expenses_sek", "surplus_sek", "deficit_sek")
SCENARIO_NOTE = "Scenario: aldrig bas och kan inte låsas (VARDERINGSKONTRAKT.md §2)."


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valuation_date: date = Field(description="Månadsslut; en basvärdering görs per kvartalsslut")
    purpose: Literal["base", "scenario"] = Field(default="base", description="base eller scenario")
    basis_code: str | None = Field(default=None, pattern=CODE_PATTERN,
                                   description="Bara scenario: värderingsgrund, t.ex. SIM-V-2026-01")
    curve_code: str | None = Field(default=None, pattern=CODE_PATTERN,
                                   description="Bara scenario: diskonteringskurva, t.ex. FI-SIM-2026-10")


class ListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valuation_date: date | None = None
    purpose: Literal["base", "scenario"] | None = None
    status: Literal["draft", "locked", "superseded"] | None = None


class RunQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: uuid.UUID = Field(description="Körningens id ur list_valuation_runs")


class LockInput(RunQuery):
    reviewed_checksum: str = Field(pattern=r"^[0-9a-f]{64}$",
                                  description="review_checksum från den granskade get_valuation_run")


class Segment(BaseModel):
    state: str
    state_label: str
    cohort: str = Field(description="Födelsedecennium")
    policies: int | None = Field(description="Antal försäkringar; None = dold")
    capital_sek: Decimal | None
    fta_sek: Decimal | None
    expenses_sek: Decimal | None
    surplus_sek: Decimal | None
    deficit_sek: Decimal | None
    hidden_reason: str | None = None


class NotCalculatedCell(BaseModel):
    reason: str
    policies: int | None = Field(description="Antal; None = dolt")
    hidden_reason: str | None = None


class CheckView(BaseModel):
    name: str
    passed: bool
    detail: str


class RunSummary(BaseModel):
    run_id: uuid.UUID
    valuation_date: date
    purpose: str
    version: int
    status: str
    source: str
    basis_code: str
    curve_code: str
    fta_sek: Decimal | None = Field(description="FTA i kronor, avrundat till öre; None = dolt")
    surplus_sek: Decimal | None = Field(description="Villkorad återbäring (VÅ)")
    deficit_sek: Decimal | None = Field(description="Underskott till följd av garanti (U)")
    checks_passed: bool
    created_by: str
    created_at: datetime | None
    locked_by: str | None
    locked_at: datetime | None


class RunList(BaseModel):
    runs: list[RunSummary]


class RunDetail(RunSummary):
    review_checksum: str
    current_locked_run_id: uuid.UUID | None
    source_note: str
    purpose_note: str
    note: str
    basis_checksum: str
    curve_checksum: str
    tax_reduction: Decimal = Field(description="s_y: avdrag för avkastningsskatt i diskonteringen")
    tax_parameter: str
    extract_checksum: str
    code_version: str
    result_checksum: str
    policies: int | None
    capital_sek: Decimal | None
    guarantee_sek_per_month: Decimal | None
    expenses_sek: Decimal | None
    balance_check: str = Field(description="Kontrollfall K10: VÅ − U = ΣC − FTA")
    segments: list[Segment] = Field(description="Läge × födelsedecennium; summan är totalerna")
    not_calculated: list[NotCalculatedCell] = Field(description="Försäkringar som inte värderats, per orsak")
    checks: list[CheckView]
    lock_note: str | None
    supersedes_run_id: uuid.UUID | None
    quantities: dict[str, str] = Field(description="Vad varje belopp är (guardrail 6)")
    min_cell_size: int


def _ore(x: Decimal | None) -> Decimal | None:
    return None if x is None else x.quantize(ORE)


def _visible_total(policies: int) -> bool:
    return policies == 0 or policies >= MIN_CELL


def _summary(run: ValuationRun) -> dict:
    show = _visible_total(run.policies)
    return {"run_id": run.id, "valuation_date": run.valuation_date, "purpose": run.purpose, "version": run.version,
                "status": run.status, "source": run.source, "basis_code": run.basis_code, "curve_code": run.curve_code,
                "fta_sek": _ore(run.fta_sek) if show else None, "surplus_sek": _ore(run.surplus_sek) if show else None,
                "deficit_sek": _ore(run.deficit_sek) if show else None, "checks_passed": run.checks_passed,
                "created_by": run.created_by, "created_at": run.created_at, "locked_by": run.locked_by,
                "locked_at": run.locked_at}


def _detail(session, run: ValuationRun) -> RunDetail:
    show = _visible_total(run.policies)
    rows = session.scalars(select(ValuationResult).where(ValuationResult.run_id == run.id)
                           .order_by(ValuationResult.state, ValuationResult.cohort))
    segments = [Segment(state=r.state, state_label=STATE_LABELS.get(r.state, r.state), cohort=r.cohort,
                        policies=r.policies, hidden_reason=r.hidden_reason,
                        **{name: _ore(getattr(r, name)) for name in AMOUNTS}) for r in rows]
    balanced = run.surplus_sek - run.deficit_sek == run.capital_sek - run.fta_sek
    current_locked = session.scalar(select(ValuationRun.id).where(
        ValuationRun.valuation_date == run.valuation_date, ValuationRun.status == "locked"))
    detail = RunDetail(
        review_checksum="", current_locked_run_id=current_locked,
        **_summary(run), source_note=SOURCE_NOTE[run.source],
        purpose_note=SCENARIO_NOTE if run.purpose == "scenario" else "Basvärdering per kvartalsslut",
        note=run.note, basis_checksum=run.basis_checksum, curve_checksum=run.curve_checksum,
        tax_reduction=run.tax_reduction.normalize(), tax_parameter=run.tax_parameter, extract_checksum=run.extract_checksum,
        code_version=run.code_version, result_checksum=run.result_checksum,
        policies=run.policies if show else None, capital_sek=_ore(run.capital_sek) if show else None,
        guarantee_sek_per_month=_ore(run.guarantee_sek_per_month) if show else None,
        expenses_sek=_ore(run.expenses_sek) if show else None,
        balance_check="stämmer på öret" if balanced else "STÄMMER INTE",
        segments=segments, not_calculated=[NotCalculatedCell(**n) for n in run.not_calculated],
        checks=[CheckView(**{**c, "detail": c["detail"] if show else "Detaljer dolda – småcellsskydd"})
                for c in run.checks], lock_note=run.lock_note, supersedes_run_id=run.supersedes_id,
        quantities=QUANTITIES, min_cell_size=MIN_CELL,
    )
    # Binder hela den tillåtna läsprojektionen och den bas som skulle ersättas.
    detail.review_checksum = vb.checksum(detail.model_dump(mode="json", exclude={"review_checksum"}))
    return detail


def _not_calculated(computation: Computation) -> list[dict]:
    counts = Counter(n.reason for n in computation.extract.not_calculated)
    hidden = suppress_counts(dict(counts))
    return [{"reason": reason, "policies": None if reason in hidden else n, "hidden_reason": hidden.get(reason)}
            for reason, n in sorted(counts.items())]


def _segments(run_id: uuid.UUID, computation: Computation) -> list[ValuationResult]:
    keys = {f"{state}|{cohort}": t.policies for (state, cohort), t in computation.segments.items()}
    hidden = suppress_counts(keys)
    out = []
    for (state, cohort), t in computation.segments.items():
        reason = hidden.get(f"{state}|{cohort}")
        amounts = {} if reason else {"capital_sek": t.capital, "fta_sek": t.fta, "expenses_sek": t.expenses,
                                         "surplus_sek": t.surplus, "deficit_sek": t.deficit}
        out.append(ValuationResult(run_id=run_id, state=state, cohort=cohort,
                                   policies=None if reason else t.policies, hidden_reason=reason, **amounts))
    return out


def _stored_extract(session, computation: Computation, actor: str) -> ValuationExtractRecord:
    extract = computation.extract
    row = session.scalar(select(ValuationExtractRecord).where(ValuationExtractRecord.checksum == extract.checksum))
    if row is None:
        row = ValuationExtractRecord(
            valuation_date=extract.valuation_date, source=extract.source, checksum=extract.checksum,
            approved=extract.approved, policies=len(extract.policies),
            guarantee_parts=sum(len(p.guarantee_parts) for p in extract.policies),
            capital_sek=sum((p.capital for p in extract.policies), Decimal(0)),
            content=extract.model_dump(mode="json"), created_by=actor)
        session.add(row)
        session.flush()
    return row


def save_computation(session, computation: Computation, actor: str, note: str) -> ValuationRun:
    """Sparar en beräknad körning som utkast med nästa version för datum och ändamål."""
    if session.bind.dialect.name == "postgresql":
        session.execute(select(func.pg_advisory_xact_lock(6043, computation.valuation_date.toordinal())))
    extract = _stored_extract(session, computation, actor)
    version = (session.scalar(select(func.max(ValuationRun.version)).where(
        ValuationRun.valuation_date == computation.valuation_date,
        ValuationRun.purpose == computation.purpose)) or 0) + 1
    t = computation.totals
    run = ValuationRun(
        valuation_date=computation.valuation_date, purpose=computation.purpose, version=version, status="draft",
        source=computation.extract.source, basis_code=computation.basis.code,
        basis_checksum=computation.basis.checksum, curve_code=computation.curve.code,
        curve_checksum=computation.curve.checksum, tax_reduction=computation.tax_reduction,
        tax_parameter=computation.tax_parameter, extract_id=extract.id, extract_checksum=extract.checksum,
        code_version=computation.code_version, result_checksum=computation.result_checksum, policies=t.policies,
        capital_sek=t.capital, guarantee_sek_per_month=t.guarantee, fta_sek=t.fta, expenses_sek=t.expenses,
        surplus_sek=t.surplus, deficit_sek=t.deficit, not_calculated=_not_calculated(computation),
        checks=[c.as_dict() for c in computation.checks], checks_passed=computation.checks_passed, note=note,
        created_by=actor,
    )
    session.add(run)
    session.flush()
    session.add_all(_segments(run.id, computation))
    session.flush()
    return run


def _get(session, run_id: uuid.UUID, *, lock: bool = False) -> ValuationRun:
    query = select(ValuationRun).where(ValuationRun.id == run_id)
    run = session.scalar(query.with_for_update() if lock else query)
    if run is None:
        raise NotFoundError(f"Värderingskörningen {run_id} finns inte")
    return run


def opening_balance(session, valuation_date: date) -> ValuationRun | None:
    """IB för en period: den låsta basvärderingen närmast före datumet (förändringsanalysen, K5)."""
    return session.scalar(select(ValuationRun).where(
        ValuationRun.status == "locked", ValuationRun.purpose == "base",
        ValuationRun.valuation_date < valuation_date).order_by(ValuationRun.valuation_date.desc()).limit(1))


@operation(
    name="run_valuation",
    description="Värderar beståndet per ett månadsslut: datautdrag S-04, FTA, villkorad återbäring och underskott "
                "per försäkring på värderingsgrunden, sparat som utkast med kontrollsummor. Scenarier märks och "
                "låses aldrig. Resultatet är aggregat utan personuppgifter.",
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-028", "PR-ITP1-031"],
)
def run_valuation(ctx: OperationContext, data: RunInput) -> RunDetail:
    session = ctx.require_session()
    if data.purpose == "base" and (data.basis_code or data.curve_code):
        raise InvalidInputError("En basvärdering använder grunden och kurvan som gäller datumet – ange ingen kod")
    try:
        computation = compute_valuation(session, data.valuation_date, data.purpose, basis_code=data.basis_code,
                                        curve_code=data.curve_code)
    except ValuationError as exc:
        raise BlockedError(str(exc)) from exc
    run = save_computation(session, computation, ctx.actor.id, ctx.reason or "")
    return _detail(session, run)


@operation(
    name="list_valuation_runs",
    description="Visar värderingskörningarna med datum, ändamål, version, status, grund och kurva samt FTA, "
                "villkorad återbäring och underskott i kronor. Inga personuppgifter.",
    kind=OperationKind.READ,
)
def list_valuation_runs(ctx: OperationContext, data: ListQuery) -> RunList:
    query = select(ValuationRun).order_by(ValuationRun.valuation_date.desc(), ValuationRun.purpose,
                                          ValuationRun.version.desc())
    for column, value in ((ValuationRun.valuation_date, data.valuation_date), (ValuationRun.purpose, data.purpose),
                          (ValuationRun.status, data.status)):
        if value is not None:
            query = query.where(column == value)
    return RunList(runs=[RunSummary(**_summary(r)) for r in ctx.require_session().scalars(query)])


@operation(
    name="get_valuation_run",
    description="Visar en värderingskörning som aggregat: indata med kontrollsummor, totaler, segment per läge och "
                "födelsedecennium med småcellsskydd, ej beräknade fall per orsak och kontrollernas utfall. "
                "Inga personuppgifter.",
    kind=OperationKind.READ,
)
def get_valuation_run(ctx: OperationContext, data: RunQuery) -> RunDetail:
    session = ctx.require_session()
    return _detail(session, _get(session, data.run_id))


@operation(
    name="lock_valuation",
    description="Fastställer en basvärdering efter att kontrollerna och kontrollsummorna prövats igen. En tidigare "
                "låst värdering för samma datum ersätts. Görs bara av ansvarig aktuarie.",
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-031"],
)
def lock_valuation(ctx: OperationContext, data: LockInput) -> RunDetail:
    if ctx.actor.type != "human":
        raise AccessDeniedError("En människa måste fastställa värderingen", operation="lock_valuation",
                                actor_id=ctx.actor.id)
    session = ctx.require_session()
    day = _get(session, data.run_id).valuation_date
    if session.bind.dialect.name == "postgresql":
        # Serialiserar även första låsningen (då det ännu inte finns någon basrad
        # att låsa). Alla beslut för datumet tar samma transaktionsbundna lås.
        session.execute(select(func.pg_advisory_xact_lock(6042, day.toordinal())))
        session.expire_all()
    run = _get(session, data.run_id, lock=True)
    if run.purpose != "base":
        raise BlockedError(SCENARIO_NOTE)
    if run.status != "draft":
        raise BlockedError(f"Körningen är {run.status} – bara ett utkast kan låsas; en rättelse blir en ny körning")
    if not run.checks_passed:
        failed = ", ".join(c["name"] for c in run.checks if not c["passed"])
        raise BlockedError(f"Kontrollerna är inte godkända ({failed}) – värderingen kan inte låsas")
    if _detail(session, run).review_checksum != data.reviewed_checksum:
        raise ConflictError("Granskningsunderlaget eller periodens fastställda bas har ändrats. Läs körningen igen.")
    extract = session.get(ValuationExtractRecord, run.extract_id)
    content = {k: v for k, v in extract.content.items() if k != "checksum"}
    if not extract.approved or vb.checksum(content) != run.extract_checksum:
        raise BlockedError("Datautdragets kontrollsumma stämmer inte med körningen – innehållet har ändrats")
    for code, expected in ((run.basis_code, run.basis_checksum), (run.curve_code, run.curve_checksum)):
        row = session.scalar(select(ValuationBasis).where(ValuationBasis.code == code))
        if row is None or row.checksum != expected or vb.checksum(row.assumptions) != expected:
            raise BlockedError(f"Grunden {code} stämmer inte med körningens kontrollsumma")
    previous = session.scalar(select(ValuationRun).where(
        ValuationRun.valuation_date == run.valuation_date, ValuationRun.status == "locked").with_for_update())
    if previous is not None and previous.id == run.id:
        raise ConflictError("Körningen är redan låst")
    if previous is not None:
        previous.status = "superseded"
        session.flush()
        run.supersedes_id = previous.id
    run.status, run.locked_by, run.locked_at, run.lock_note = "locked", ctx.actor.id, datetime.now(UTC), ctx.reason
    session.flush()
    return _detail(session, run)
