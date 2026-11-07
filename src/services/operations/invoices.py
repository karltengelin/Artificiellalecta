"""Fakturor och förfallobevakning (paket A steg 3, B-046, P1-PREMIE-001 §4.4–4.5).

`create_invoice` samlar en arbetsgivares öppna premieunderlag för en premieperiod
och skapar fakturor (PR-ITP1-017). Varje premiekedja – den ordinarie premieraden och
dess länkade rättelser (PR-ITP1-019 p.1) – faktureras efter sitt läge:

- **Inte fakturerad:** en ordinarie rad med kedjans belopp; rättelser före
  faktureringen ingår i den (§4.3). Noll premie ger ingen rad.
- **Fakturerad men inte betald:** den fakturerade raden krediteras i sin helhet på en
  kreditfaktura och det rättade beloppet debiteras på nytt (`rebill`).
- **Betald:** rättelsen uppåt blir en tilläggsrad. Rättelse nedåt av mottagen premie
  blockeras redan i premieunderlaget (PR-ITP1-019 p.3).

Förfallodagen är fakturadatum plus 30 dagar, flyttad till nästa bankdag. OCR-referensen
har längd- och kontrollsiffra enligt modulus 10. En faktura ändras aldrig; omfakturering
sker med kredit och ny debet. Premieraderna får status `invoiced`. Ingen extern sändning.

`check_overdue_invoices` är den dagliga bevakningen (§4.5): ett ärende
`payment_overdue` till handläggaren dagen efter förfallodagen, eskalerat till
operatören efter 30 dagars dröjsmål. Ingen påminnelseavgift, ingen dröjsmålsränta,
ingen uppsägning och inget pensionsstopp. Förfallna premier är fordringar, inte kapital.

Delbetalningar och mottagna belopp kommer i steg 4; i detta steg är en premiekedja
betald när dess premierad har status `paid`.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from models import (
    Case,
    Employer,
    Invoice,
    InvoiceLineRecord,
    Policy,
    PolicyBenefit,
    PremiumTransaction,
    SalaryReport,
)
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, NotFoundError
from services.operations import common
from services.operations.cases import _next_case_number
from services.operations.premium_basis import FIRST_OPERATIVE_PERIOD
from utils.bank_calendar import invoice_due_date
from utils.ocr import ocr_reference

RULES = ["PR-ITP1-017", "PR-ITP1-018", "PR-ITP1-019"]
#: Systemvägen som skapar bevakningens ärenden (P1-PREMIE-001 §6)
MONITOR_ACTOR = "invoice_monitor"
#: Mottagare av eskalerade förfallna fakturor (§4.5)
ESCALATION_ASSIGNEE = "operator"
ESCALATION_DAYS = 30
ZERO = Decimal("0.00")


# --- vyer -----------------------------------------------------------------------------------------


class InvoiceLineView(BaseModel):
    line_number: int
    line_type: Literal["ordinary", "rebill", "additional", "credit"]
    policy_number: str
    benefit_id: str
    period_month: date
    amount_sek: Decimal
    premium_transaction_id: str = Field(description="Premiekedjans ordinarie premierad")
    covers: list[str] = Field(description="Premieraderna som raden fakturerar")
    credits: str | None = Field(default=None, description="Krediterad rad som <fakturanummer>:<radnummer>")


class InvoiceView(BaseModel):
    invoice_number: str
    invoice_type: Literal["debit", "credit"]
    employer_org_number: str
    period_month: date
    ocr_reference: str
    invoice_date: date
    due_date: date
    total_sek: Decimal
    credited_invoice_number: str | None
    open_sek: Decimal | None = Field(
        description="Debetfaktura: summa efter krediteringar (mottagna belopp avräknas från steg 4)"
    )
    checksum: str
    lines: list[InvoiceLineView]


def _view(session, invoice: Invoice) -> InvoiceView:
    org = session.scalar(select(Employer.org_number).where(Employer.id == invoice.employer_id))
    credited = session.scalar(select(Invoice.invoice_number).where(Invoice.id == invoice.credited_invoice_id))
    rows = session.execute(
        select(InvoiceLineRecord, Policy.policy_number)
        .join(Policy, Policy.id == InvoiceLineRecord.policy_id)
        .where(InvoiceLineRecord.invoice_id == invoice.id)
        .order_by(InvoiceLineRecord.line_number)
    ).all()
    lines = [
        InvoiceLineView(
            line_number=line.line_number, line_type=line.line_type, policy_number=policy_number,
            benefit_id=str(line.benefit_id), period_month=line.period_month, amount_sek=line.amount_sek,
            premium_transaction_id=str(line.premium_transaction_id), covers=list(line.covers),
            credits=_line_label(session, line.credits_line_id),
        )
        for line, policy_number in rows
    ]
    return InvoiceView(
        invoice_number=invoice.invoice_number, invoice_type=invoice.invoice_type, employer_org_number=org,
        period_month=invoice.period_month, ocr_reference=invoice.ocr_reference, invoice_date=invoice.invoice_date,
        due_date=invoice.due_date, total_sek=invoice.total_sek, credited_invoice_number=credited,
        open_sek=_open_amount(session, invoice) if invoice.invoice_type == "debit" else None,
        checksum=invoice.checksum, lines=lines,
    )


def _line_label(session, line_id) -> str | None:
    if line_id is None:
        return None
    row = session.execute(
        select(Invoice.invoice_number, InvoiceLineRecord.line_number)
        .join(Invoice, Invoice.id == InvoiceLineRecord.invoice_id)
        .where(InvoiceLineRecord.id == line_id)
    ).one()
    return f"{row[0]}:{row[1]}"


def _open_amount(session, invoice: Invoice) -> Decimal:
    """Debetfakturans summa plus kreditfakturor mot den. Mottagna belopp avräknas i steg 4."""
    credits = session.scalar(
        select(func.coalesce(func.sum(Invoice.total_sek), 0)).where(Invoice.credited_invoice_id == invoice.id)
    )
    return Decimal(invoice.total_sek) + Decimal(credits)


# --- create_invoice -------------------------------------------------------------------------------


class InvoiceRequest(BaseModel):
    employer_org_number: str = Field(pattern=r"^\d{10}$", description="Arbetsgivarens organisationsnummer")
    period_month: date = Field(description="Premieperioden – dagen i datumet ignoreras")

    @field_validator("period_month")
    @classmethod
    def _first_of_month(cls, value: date) -> date:
        return common.month_of(value)


class SkippedRow(BaseModel):
    transaction_id: str
    reason: str


class InvoiceRun(BaseModel):
    employer_org_number: str
    period_month: date
    invoices: list[InvoiceView]
    skipped: list[SkippedRow] = Field(description="Öppna premierader som inte kunde faktureras, med skäl")
    note: str


@operation(
    name="create_invoice",
    description=(
        "Fakturerar en arbetsgivares öppna premieunderlag för en premieperiod (PR-ITP1-017): ordinarie "
        "premie, kredit och ny debet när en fakturerad men obetald premie rättats, och tillägg när en betald "
        "premie rättats uppåt. Förfallodag 30 dagar till nästa bankdag, OCR med kontrollsiffra. Ingen sändning."
    ),
    kind=OperationKind.WRITE,
    rules=RULES,
)
def create_invoice(ctx: OperationContext, data: InvoiceRequest) -> InvoiceRun:
    session = ctx.require_session()
    period = data.period_month
    if period < FIRST_OPERATIVE_PERIOD:
        raise BlockedError(
            f"{period:%Y-%m} ligger före första operativa premieperiod {FIRST_OPERATIVE_PERIOD:%Y-%m}. "
            "Den genererade historiken faktureras inte (B-046, PA1)"
        )
    employer = session.scalar(select(Employer).where(Employer.org_number == data.employer_org_number))
    if employer is None:
        raise NotFoundError(f"Ingen arbetsgivare med organisationsnummer {data.employer_org_number}")

    debit_lines: list[dict[str, Any]] = []
    credit_lines: dict[uuid.UUID, list[dict[str, Any]]] = {}
    skipped: list[SkippedRow] = []
    for original, chain in _chains(session, employer, period):
        pending = [r for r in chain if r.status == "pending"]
        if not pending or all(r.amount_sek == 0 for r in pending):
            continue
        base = {"premium_transaction_id": original.id, "benefit_id": original.benefit_id,
                "period_month": original.period_month}
        if original.status == "pending":
            total = sum((r.amount_sek for r in pending), ZERO)
            if total > 0:
                debit_lines.append({**base, "line_type": "ordinary", "amount_sek": total, "rows": pending})
            elif total < 0:
                skipped.append(SkippedRow(transaction_id=str(original.id),
                                          reason="Negativ premie före fakturering – manuell prövning"))
            continue
        if any(r.status == "paid" for r in chain):
            for row in pending:
                if row.amount_sek > 0:
                    debit_lines.append({**base, "line_type": "additional", "amount_sek": row.amount_sek,
                                        "rows": [row]})
                elif row.amount_sek < 0:
                    skipped.append(SkippedRow(
                        transaction_id=str(row.id),
                        reason="Rättelse nedåt av mottagen premie – återtag ingår inte (PR-ITP1-019 p.3)"))
            continue
        # Fakturerad men inte betald: kredit av den fakturerade raden och ny debet med rättat belopp
        live = _live_debit_line(session, original.id)
        if live is None:
            skipped.append(SkippedRow(transaction_id=str(original.id),
                                      reason="Premieraden är fakturerad men fakturaraden saknas – manuell prövning"))
            continue
        corrected = sum((r.amount_sek for r in chain), ZERO)
        # Rättat till noll: krediten ensam fakturerar rättelsen
        credit_lines.setdefault(live.invoice_id, []).append(
            {**base, "line_type": "credit", "amount_sek": -live.amount_sek,
             "rows": [] if corrected > 0 else pending, "credits": live})
        if corrected > 0:
            debit_lines.append({**base, "line_type": "rebill", "amount_sek": corrected, "rows": pending})

    invoices: list[Invoice] = []
    for credited_id, lines in sorted(credit_lines.items(), key=lambda item: str(item[0])):
        invoices.append(_create(session, ctx, employer, period, "credit", lines, credited_id))
    if debit_lines:
        invoices.append(_create(session, ctx, employer, period, "debit", debit_lines, None))
    views = [_view(session, invoice) for invoice in invoices]
    note = (f"{len(views)} fakturor skapade: " + ", ".join(f"{v.invoice_number} ({v.total_sek} kr)" for v in views)
            if views else "Inget öppet premieunderlag att fakturera för perioden")
    return InvoiceRun(employer_org_number=employer.org_number, period_month=period, invoices=views,
                      skipped=skipped, note=note + ". Ingen faktura är skickad.")


def _chains(session, employer, period: date):
    """Arbetsgivarens premiekedjor för perioden: premierader ur registrerat löneunderlag och deras rättelser."""
    premiums = session.scalars(
        select(PremiumTransaction)
        .where(PremiumTransaction.transaction_type == "premium", PremiumTransaction.period_month == period,
               PremiumTransaction.status != "cancelled")
        .order_by(PremiumTransaction.id)
        .with_for_update()
    ).all()
    report_ids = {}
    for row in premiums:
        ref = (row.calculation_basis or {}).get("salary_report") or {}
        if ref.get("id"):
            report_ids[row.id] = uuid.UUID(ref["id"])
    own = set(session.scalars(
        select(SalaryReport.id).where(SalaryReport.id.in_(set(report_ids.values())),
                                      SalaryReport.employer_id == employer.id)
    )) if report_ids else set()
    for original in premiums:
        if report_ids.get(original.id) not in own:
            continue
        linked = session.scalars(
            select(PremiumTransaction)
            .where(PremiumTransaction.corrects_transaction_id == original.id,
                   PremiumTransaction.status != "cancelled")
            .order_by(PremiumTransaction.id)
            .with_for_update()
        ).all()
        yield original, [original, *linked]


def _live_debit_line(session, premium_id) -> InvoiceLineRecord | None:
    credited = select(InvoiceLineRecord.credits_line_id).where(InvoiceLineRecord.credits_line_id.is_not(None))
    lines = session.scalars(
        select(InvoiceLineRecord).where(
            InvoiceLineRecord.premium_transaction_id == premium_id,
            InvoiceLineRecord.line_type.in_(("ordinary", "rebill")),
            InvoiceLineRecord.id.not_in(credited),
        )
    ).all()
    return lines[0] if len(lines) == 1 else None


def _create(session, ctx, employer, period, invoice_type, lines, credited_id) -> Invoice:
    sequence = (session.scalar(select(func.count()).select_from(Invoice)) or 0) + 1
    number = f"INV-{sequence:06d}"
    today = common.today()
    invoice = Invoice(
        id=uuid.uuid4(), invoice_number=number, employer_id=employer.id, period_month=period,
        invoice_type=invoice_type, ocr_reference=ocr_reference(f"7{sequence:06d}"), invoice_date=today,
        due_date=invoice_due_date(today), total_sek=sum((line["amount_sek"] for line in lines), ZERO),
        credited_invoice_id=credited_id, checksum="0" * 64, created_by=ctx.actor.id,
    )
    session.add(invoice)
    session.flush()
    policies = dict(session.execute(
        select(PolicyBenefit.id, PolicyBenefit.policy_id).where(
            PolicyBenefit.id.in_({line["benefit_id"] for line in lines}))
    ).all())
    content_lines = []
    for number_in_invoice, line in enumerate(lines, start=1):
        record = InvoiceLineRecord(
            id=uuid.uuid4(), invoice_id=invoice.id, line_number=number_in_invoice, line_type=line["line_type"],
            premium_transaction_id=line["premium_transaction_id"], covers=[str(r.id) for r in line["rows"]],
            benefit_id=line["benefit_id"], policy_id=policies[line["benefit_id"]],
            period_month=line["period_month"], amount_sek=line["amount_sek"],
            credits_line_id=line["credits"].id if "credits" in line else None,
        )
        session.add(record)
        for row in line["rows"]:
            row.status = "invoiced"
        content_lines.append({
            "line_number": record.line_number, "line_type": record.line_type,
            "premium_transaction_id": str(record.premium_transaction_id), "covers": record.covers,
            "benefit_id": str(record.benefit_id), "policy_id": str(record.policy_id),
            "period_month": record.period_month.isoformat(), "amount_sek": str(record.amount_sek),
            "credits_line_id": str(record.credits_line_id) if record.credits_line_id else None,
        })
    session.flush()
    invoice.checksum = _checksum({
        "invoice_number": invoice.invoice_number, "invoice_type": invoice.invoice_type,
        "employer_org_number": employer.org_number, "period_month": period.isoformat(),
        "ocr_reference": invoice.ocr_reference, "invoice_date": invoice.invoice_date.isoformat(),
        "due_date": invoice.due_date.isoformat(), "total_sek": str(invoice.total_sek),
        "credited_invoice_id": str(credited_id) if credited_id else None, "lines": content_lines,
    })
    session.flush()
    return invoice


def _checksum(content: dict) -> str:
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


# --- get_invoice och list_invoices ----------------------------------------------------------------


class InvoiceLookup(BaseModel):
    invoice_number: str = Field(pattern=r"^INV-\d{6}$", description="Fakturanumret, t.ex. INV-000001")


@operation(
    name="get_invoice",
    description="Visar en faktura med rader, förfallodag, OCR, kreditering och öppet belopp.",
    kind=OperationKind.READ,
)
def get_invoice(ctx: OperationContext, data: InvoiceLookup) -> InvoiceView:
    session = ctx.require_session()
    invoice = session.scalar(select(Invoice).where(Invoice.invoice_number == data.invoice_number))
    if invoice is None:
        raise NotFoundError(f"Okänd faktura: {data.invoice_number}")
    return _view(session, invoice)


class InvoiceQuery(BaseModel):
    employer_org_number: str | None = Field(default=None, pattern=r"^\d{10}$")
    period_month: date | None = Field(default=None, description="Premieperiod, valfri")
    open_only: bool = Field(default=False, description="Bara debetfakturor med öppet belopp")
    limit: int = Field(default=100, ge=1, le=500)


class InvoiceSummary(BaseModel):
    invoice_number: str
    invoice_type: str
    employer_org_number: str
    period_month: date
    ocr_reference: str
    invoice_date: date
    due_date: date
    total_sek: Decimal
    open_sek: Decimal | None


class InvoiceList(BaseModel):
    invoices: list[InvoiceSummary]
    count: int


@operation(
    name="list_invoices",
    description="Listar fakturor per arbetsgivare och premieperiod, med öppet belopp för debetfakturor.",
    kind=OperationKind.READ,
)
def list_invoices(ctx: OperationContext, data: InvoiceQuery) -> InvoiceList:
    session = ctx.require_session()
    query = select(Invoice, Employer.org_number).join(Employer, Employer.id == Invoice.employer_id)
    if data.employer_org_number is not None:
        query = query.where(Employer.org_number == data.employer_org_number)
    if data.period_month is not None:
        query = query.where(Invoice.period_month == common.month_of(data.period_month))
    if data.open_only:
        query = query.where(Invoice.invoice_type == "debit")
    rows = session.execute(query.order_by(Invoice.invoice_number)).all()
    summaries = []
    for invoice, org in rows:
        open_sek = _open_amount(session, invoice) if invoice.invoice_type == "debit" else None
        if data.open_only and not open_sek:
            continue
        summaries.append(InvoiceSummary(
            invoice_number=invoice.invoice_number, invoice_type=invoice.invoice_type, employer_org_number=org,
            period_month=invoice.period_month, ocr_reference=invoice.ocr_reference,
            invoice_date=invoice.invoice_date, due_date=invoice.due_date, total_sek=invoice.total_sek,
            open_sek=open_sek,
        ))
        if len(summaries) == data.limit:
            break
    return InvoiceList(invoices=summaries, count=len(summaries))


# --- check_overdue_invoices -----------------------------------------------------------------------


class OverdueCheck(BaseModel):
    """Bevakningen körs för dagens datum; inga parametrar."""


class OverdueEntry(BaseModel):
    invoice_number: str
    case_number: str
    days_overdue: int
    open_sek: Decimal
    action: Literal["created", "escalated"]


class OverdueResult(BaseModel):
    as_of: date
    overdue_invoices: int = Field(description="Debetfakturor med öppet belopp efter förfallodagen")
    overdue_sek: Decimal
    actions: list[OverdueEntry]
    note: str


@operation(
    name="check_overdue_invoices",
    description=(
        "Daglig bevakning av förfallna fakturor (PR-ITP1-017): ärende payment_overdue till handläggaren dagen "
        "efter förfallodagen, eskalerat till operatören efter 30 dagars dröjsmål. Ingen avgift, ingen ränta, "
        "ingen uppsägning och inget pensionsstopp."
    ),
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-017"],
)
def check_overdue_invoices(ctx: OperationContext, data: OverdueCheck) -> OverdueResult:
    session = ctx.require_session()
    today = common.today()
    invoices = session.scalars(
        select(Invoice).where(Invoice.invoice_type == "debit", Invoice.due_date < today)
        .order_by(Invoice.invoice_number)
    ).all()
    actions: list[OverdueEntry] = []
    overdue = 0
    overdue_sek = ZERO
    for invoice in invoices:
        open_sek = _open_amount(session, invoice)
        if open_sek <= 0:
            continue
        overdue += 1
        overdue_sek += open_sek
        days = (today - invoice.due_date).days
        escalate = days >= ESCALATION_DAYS
        case = session.scalar(
            select(Case).where(Case.case_type == "payment_overdue", Case.employer_id == invoice.employer_id,
                               Case.source_reference == invoice.invoice_number).with_for_update()
        )
        if case is None:
            case = Case(
                id=uuid.uuid4(), case_number=_next_case_number(session), case_type="payment_overdue",
                status="open", employer_id=invoice.employer_id, period_month=invoice.period_month,
                channel="system", received_date=today, source_reference=invoice.invoice_number,
                details=_overdue_details(invoice, open_sek, days, escalate, today),
                assigned_to=ESCALATION_ASSIGNEE if escalate else None, created_by=MONITOR_ACTOR,
            )
            session.add(case)
            session.flush()
            actions.append(OverdueEntry(invoice_number=invoice.invoice_number, case_number=case.case_number,
                                        days_overdue=days, open_sek=open_sek, action="created"))
        elif escalate and case.status != "closed" and not case.details.get("escalated"):
            case.details = _overdue_details(invoice, open_sek, days, True, today)
            case.assigned_to = ESCALATION_ASSIGNEE
            actions.append(OverdueEntry(invoice_number=invoice.invoice_number, case_number=case.case_number,
                                        days_overdue=days, open_sek=open_sek, action="escalated"))
    return OverdueResult(
        as_of=today, overdue_invoices=overdue, overdue_sek=overdue_sek, actions=actions,
        note=(f"{overdue} förfallna fakturor, {overdue_sek} kr öppet. Fordringarna står kvar; ingen avgift, "
              "ränta, uppsägning eller ändrad garanti (PR-ITP1-017)."),
    )


def _overdue_details(invoice: Invoice, open_sek: Decimal, days: int, escalated: bool, today: date) -> dict:
    return {
        "invoice_number": invoice.invoice_number, "ocr_reference": invoice.ocr_reference,
        "due_date": invoice.due_date.isoformat(), "open_sek": str(open_sek), "days_overdue": days,
        "escalated": escalated, "escalated_on": today.isoformat() if escalated else None,
        "rule": "PR-ITP1-017",
    }
