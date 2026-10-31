"""Antagandebibliotekets operationer (A4, B-042, tjänstelager.md §9.7).

Läsning (`list_valuation_bases`, `get_valuation_basis`) är AGENT och monterad i podden
`antaganden`. Förslag (`propose_valuation_basis`) är APPROVAL i registret, men monteras för
aktuarieagenten först med antagandeöversynen (A9), när rollen `agent_aktuarie` får lägga förslag
i kön. Antagande och avslag (`adopt_valuation_basis`, `reject_valuation_basis`) görs bara av
människa; antagandet kräver beslutsreferens (styrelsebeslut eller B-nummer).

Innehållet i en grund ändras aldrig: ett förslag skapar en ny rad, och antagandet sätter bara
status, giltighet och beslut. När en grund antas avslutas den gällande grunden i samma familj
dagen före. Garantigrunder (SIM-G, SIM-HIST) gäller bara framåt: tidigast nästa månadsförsta,
så att redan intjänade garantidelar behåller sin grund (B-027).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from models import ValuationBasis
from models.valuation_basis import BASIS_FAMILIES
from services import valuation_bases as vb
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, ConflictError, InvalidInputError, NotFoundError
from services.operations import common
from services.operations.product_parameters import first_of_next_month

STATE_TEXT = {"proposed": "förslag", "rejected": "avslagen"}
CODE_PATTERN = r"^(SIM-G|SIM-HIST|SIM-B|SIM-R|SIM-V|FI-SIM|AVK-SIM)-\d{4}-\d{2}$"


class ListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on_date: date | None = Field(default=None, description="Dagen som gällande grunder visas för; standard i dag")
    family: str | None = Field(default=None, description="Bara en familj, t.ex. SIM-V eller FI-SIM")


class BasisSummary(BaseModel):
    code: str
    family: str
    purpose: str
    title: str
    status: str
    state: str = Field(description="gällande, kommande, upphörd, förslag eller avslagen i förhållande till on_date")
    valid_from: date | None
    valid_to: date | None
    decision_ref: str | None
    checksum: str
    checksum_ok: bool


class BasisList(BaseModel):
    on_date: date
    bases: list[BasisSummary]
    in_force: dict[str, str] = Field(description="Gällande grund per familj on_date")


class CodeQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=CODE_PATTERN, description="Grundens kod, t.ex. SIM-V-2026-01")


class BasisDetail(BasisSummary):
    assumptions: dict[str, Any]
    source_refs: str
    supersedes_code: str | None
    proposal_reason: str
    created_by: str
    adopted_by: str | None
    review_note: str | None


class ProposeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=CODE_PATTERN, description="Ny kod i familjen, t.ex. SIM-V-2027-01")
    title: str = Field(min_length=3, max_length=200)
    assumptions: dict[str, Any] = Field(description="Antagandena enligt schemat för familjens ändamål")
    source_refs: str = Field(min_length=1, max_length=300, description="Källor, t.ex. erfarenhetsanalys och FI")
    supersedes_code: str | None = Field(default=None, pattern=CODE_PATTERN,
                                        description="Grunden förslaget ska ersätta, i samma familj")


class AdoptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=CODE_PATTERN)
    valid_from: date = Field(description="Första dag grunden gäller")
    decision_ref: str = Field(min_length=3, max_length=100, description="Styrelsebeslut eller B-nummer")


class RejectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=CODE_PATTERN)
    note: str = Field(min_length=3, max_length=1000)


def _state(row: ValuationBasis, on: date) -> str:
    if row.status != "adopted":
        return STATE_TEXT[row.status]
    if row.valid_from > on:
        return "kommande"
    return "upphörd" if row.valid_to is not None and row.valid_to < on else "gällande"


def _summary(row: ValuationBasis, on: date) -> dict[str, Any]:
    return dict(code=row.code, family=row.family, purpose=row.purpose, title=row.title, status=row.status,
                state=_state(row, on), valid_from=row.valid_from, valid_to=row.valid_to,
                decision_ref=row.decision_ref, checksum=row.checksum,
                checksum_ok=vb.checksum(row.assumptions) == row.checksum)


def _detail(row: ValuationBasis, on: date) -> BasisDetail:
    return BasisDetail(**_summary(row, on), assumptions=row.assumptions, source_refs=row.source_refs,
                       supersedes_code=row.supersedes_code, proposal_reason=row.proposal_reason,
                       created_by=row.created_by, adopted_by=row.adopted_by, review_note=row.review_note)


def _get(session, code: str, *, lock: bool = False) -> ValuationBasis:
    query = select(ValuationBasis).where(ValuationBasis.code == code)
    row = session.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise NotFoundError(f"Grunden {code} finns inte")
    return row


@operation(
    name="list_valuation_bases",
    description="Visar antagandebibliotekets grunder och diskonteringskurvor med status, giltighet, beslut och "
                "kontrollsumma, och vilken grund som gäller per familj en viss dag. Inga personuppgifter.",
    kind=OperationKind.READ,
)
def list_valuation_bases(ctx: OperationContext, data: ListQuery) -> BasisList:
    on = data.on_date or common.today()
    if data.family is not None and data.family not in BASIS_FAMILIES:
        raise InvalidInputError(f"Okänd familj {data.family} (kända: {', '.join(BASIS_FAMILIES)})")
    query = select(ValuationBasis).order_by(ValuationBasis.family, ValuationBasis.code)
    if data.family:
        query = query.where(ValuationBasis.family == data.family)
    rows = list(ctx.require_session().scalars(query))
    summaries = [BasisSummary(**_summary(r, on)) for r in rows]
    return BasisList(on_date=on, bases=summaries,
                     in_force={s.family: s.code for s in summaries if s.state == "gällande"})


@operation(
    name="get_valuation_basis",
    description="Visar en grund med alla antaganden, källor och beslut. Kontrollsumman prövas; ett ändrat "
                "innehåll stoppar läsningen. Inga personuppgifter.",
    kind=OperationKind.READ,
)
def get_valuation_basis(ctx: OperationContext, data: CodeQuery) -> BasisDetail:
    row = _get(ctx.require_session(), data.code)
    try:
        vb.verify_checksum(row)
    except vb.BasisError as exc:
        raise BlockedError(str(exc)) from exc
    return _detail(row, common.today())


@operation(
    name="propose_valuation_basis",
    description="Föreslår en ny grund eller diskonteringskurva i antagandebiblioteket. Förslaget gäller inte förrän "
                "en människa antar det med giltighetsdag och beslut. Inga personuppgifter.",
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-031"],
)
def propose_valuation_basis(ctx: OperationContext, data: ProposeInput) -> BasisDetail:
    session = ctx.require_session()
    try:
        family = vb.family_of(data.code)
        assumptions = vb.normalize(BASIS_FAMILIES[family], data.assumptions)
    except vb.BasisError as exc:
        raise InvalidInputError(str(exc)) from exc
    if session.scalar(select(ValuationBasis.id).where(ValuationBasis.code == data.code)) is not None:
        raise ConflictError(f"Grunden {data.code} finns redan – välj en ny kod")
    if data.supersedes_code is not None:
        old = _get(session, data.supersedes_code)
        if old.family != family:
            raise InvalidInputError(f"{data.supersedes_code} hör till {old.family}, förslaget till {family}")
    row = ValuationBasis(
        code=data.code, family=family, purpose=BASIS_FAMILIES[family], title=data.title, assumptions=assumptions,
        checksum=vb.checksum(assumptions), source_refs=data.source_refs, status="proposed",
        supersedes_code=data.supersedes_code, proposal_reason=ctx.reason or "", created_by=ctx.actor.id,
    )
    session.add(row)
    session.flush()
    return _detail(row, common.today())


@operation(
    name="adopt_valuation_basis",
    description="Antar en föreslagen grund från en giltighetsdag med beslutsreferens. Den gällande grunden i samma "
                "familj avslutas dagen före. Garantigrunder gäller tidigast från nästa månadsförsta.",
    kind=OperationKind.WRITE,
)
def adopt_valuation_basis(ctx: OperationContext, data: AdoptInput) -> BasisDetail:
    session = ctx.require_session()
    row = _get(session, data.code, lock=True)
    if row.status != "proposed":
        raise BlockedError(f"{data.code} är {STATE_TEXT.get(row.status, 'antagen')} – bara förslag kan antas")
    try:
        vb.verify_checksum(row)
    except vb.BasisError as exc:
        raise BlockedError(str(exc)) from exc
    today = common.today()
    if row.purpose == "guarantee" and data.valid_from < first_of_next_month(today):
        raise BlockedError("En garantigrund gäller bara framåt: tidigast nästa månadsförsta (B-027)")
    family_rows = list(session.scalars(select(ValuationBasis).where(
        ValuationBasis.family == row.family, ValuationBasis.status == "adopted").with_for_update()))
    if any(r.valid_from >= data.valid_from for r in family_rows):
        raise ConflictError(f"En antagen grund i {row.family} gäller redan från {data.valid_from} eller senare")
    current = next((r for r in family_rows if r.valid_to is None), None)
    if current is not None:
        current.valid_to = data.valid_from - timedelta(days=1)
        session.flush()
    row.status, row.valid_from, row.decision_ref = "adopted", data.valid_from, data.decision_ref
    row.adopted_by, row.adopted_at = ctx.actor.id, datetime.now(UTC)
    session.flush()
    return _detail(row, today)


@operation(
    name="reject_valuation_basis",
    description="Avslår en föreslagen grund med en anteckning. Förslaget finns kvar som historik.",
    kind=OperationKind.WRITE,
)
def reject_valuation_basis(ctx: OperationContext, data: RejectInput) -> BasisDetail:
    session = ctx.require_session()
    row = _get(session, data.code, lock=True)
    if row.status != "proposed":
        raise BlockedError(f"{data.code} är inget förslag")
    row.status, row.review_note = "rejected", data.note
    session.flush()
    return _detail(row, common.today())
