"""Frysta försöksunderlag för P6-MANAD-001, utan databas- eller journalverkställighet.

Kontrakten skiljer källans premieperiod från mottagning/värdedatum. Ett paket
innehåller S-04 och de grunder som faktiskt användes, inte en senare omläsning.
Kontrollsummor binder även parameterinnehåll och den valda scenariokonventionen.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services import valuation_bases as vb
from services.valuation_extract import ValuationExtract, extract_checksum, month_end
from skills.calculation import actuarial_annuity as aa
from skills.calculation.capital_rollforward import allocate_cents

DESIGN = "P6-MANAD-001"
INPUT_VERSION = "premium-month-inputs-1"
MONEY = Decimal("0.01")
HASH = r"^[0-9a-f]{64}$"
KEY = r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Source(Strict):
    system: str = Field(pattern=KEY)
    reference: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    checksum: str = Field(pattern=HASH)
    synthetic: bool
    payload: dict

    @model_validator(mode="after")
    def intact(self):
        if vb.checksum(self.payload) != self.checksum:
            raise ValueError("Källunderlagets kontrollsumma stämmer inte")
        return self


class BasisSnapshot(Strict):
    code: str
    purpose: str
    checksum: str = Field(pattern=HASH)
    valid_from: date
    valid_to: date | None
    assumptions: dict

    @model_validator(mode="after")
    def intact(self):
        if vb.checksum(self.assumptions) != self.checksum:
            raise ValueError(f"Grundens innehåll stämmer inte: {self.code}")
        vb.normalize(self.purpose, self.assumptions)
        return self


class InvoiceLine(Strict):
    id: str = Field(pattern=KEY)
    benefit_id: str
    policy_id: str
    period_month: date
    due_sek: Decimal = Field(gt=0)
    calculation_basis: dict

    @model_validator(mode="after")
    def valid_line(self):
        if self.period_month.day != 1 or self.due_sek != self.due_sek.quantize(MONEY):
            raise ValueError("Premieperiod ska vara månadsförsta och beloppet hela ören")
        if not self.calculation_basis:
            raise ValueError("Premieunderlagets IBB-, regel- och parameterversioner krävs")
        return self


class InvoiceInput(Strict):
    id: str = Field(pattern=KEY)
    source: Source
    payer_id: str
    lines: list[InvoiceLine] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def unique_lines(self):
        if len({line.id for line in self.lines}) != len(self.lines):
            raise ValueError("Dubbla premierads-ID:n")
        if self.source.payload != self.model_dump(mode="json", exclude={"source"}):
            raise ValueError("Fakturaunderlaget motsvarar inte den bundna källan")
        return self


class ReceiptInput(Strict):
    source: Source
    event_id: str = Field(pattern=KEY)
    payment_reference: str = Field(min_length=1, max_length=200)
    payer_id: str = Field(min_length=1, max_length=100)
    received_date: date
    currency: Literal["SEK"] = "SEK"
    gross_sek: Decimal = Field(ge=0)
    external_deduction_sek: Decimal = Field(ge=0)
    net_sek: Decimal = Field(ge=0)
    invoice_id: str | None = Field(default=None, pattern=KEY)
    delivery_ref: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def amounts_match(self):
        amounts = (self.gross_sek, self.external_deduction_sek, self.net_sek)
        if any(x != x.quantize(MONEY) for x in amounts):
            raise ValueError("Mottagningsbeloppen ska vara i hela ören")
        if self.gross_sek - self.external_deduction_sek != self.net_sek:
            raise ValueError("Brutto minus dokumenterat externt avdrag ska vara netto")
        if self.source.payload != self.model_dump(mode="json", exclude={"source", "delivery_ref"}):
            raise ValueError("Mottagningsuppgifterna motsvarar inte bank-/simuleringskällan")
        return self

    @property
    def value_date(self) -> date:
        return month_end(self.received_date)

    def economic_content(self) -> dict:
        # Transportförsöket är inte betalningens ekonomiska identitet.
        return self.model_dump(mode="json", exclude={"delivery_ref"})


def obligation(invoice: InvoiceInput, line: InvoiceLine) -> tuple:
    """Ordinarie premie faktureras en gång per förmån och period. Ett tillägg på mottagen premie
    (PR-ITP1-019 p.1, paket A:s radtyp `additional`) är en egen länkad premiepost och räknas för sig."""
    if line.calculation_basis.get("invoice_line_type") == "additional":
        return ("additional", invoice.id, line.id)
    return (line.benefit_id, line.period_month)


def receipt_key(scenario_id: str, receipt: ReceiptInput) -> str:
    return vb.checksum({"scenario": scenario_id, "system": receipt.source.system,
                        "event": receipt.event_id})


def allocate_receipt(invoice: InvoiceInput, receipt: ReceiptInput,
                     allocated: dict[str, Decimal]) -> tuple[dict[str, Decimal], Decimal]:
    """PR-018: fördela bara till återstående positiva rader; resten är oallokerat."""
    if receipt.invoice_id != invoice.id or receipt.payer_id != invoice.payer_id:
        return {}, receipt.net_sek
    lines = sorted(invoice.lines, key=lambda line: line.id)
    if any(allocated.get(line.id, Decimal(0)) < 0
           or allocated.get(line.id, Decimal(0)) > line.due_sek for line in lines):
        raise ValueError("Tidigare allokering överskrider premieutrymmet")
    weights = [line.due_sek - allocated.get(line.id, Decimal(0)) for line in lines]
    matched = min(receipt.net_sek, sum(weights, Decimal(0)))
    shares = allocate_cents(matched, weights)
    return {line.id: share for line, share in zip(lines, shares, strict=True) if share}, receipt.net_sek - matched


class MonthInputs(Strict):
    version: Literal["premium-month-inputs-1"] = INPUT_VERSION
    design: Literal["P6-MANAD-001"] = DESIGN
    scenario_id: str = Field(pattern=KEY)
    synthetic: Literal[True] = True
    opening: ValuationExtract
    bases: list[BasisSnapshot]
    parameters: list[dict]
    opening_basis_code: str
    opening_curve_code: str
    expected_opening_checksum: str = Field(pattern=HASH)
    code_version: str
    period_end: date
    invoices: list[InvoiceInput]
    receipts: list[ReceiptInput]
    november_return: Decimal = Decimal("0.002")
    rate_shift_bp: Decimal = Decimal(50)
    expense_factor: Decimal = Decimal("1.10")
    checksum: str = ""

    @model_validator(mode="after")
    def coherent(self):
        e = self.opening
        if (not e.approved or not all(c.passed for c in e.checks) or e.not_calculated
                or e.checksum != extract_checksum(e) or e.checksum != self.expected_opening_checksum):
            raise ValueError("IB är inte fullständigt avstämt eller dess kontrollsumma har ändrats")
        if not e.policies or len({p.policy_id for p in e.policies}) != len(e.policies):
            raise ValueError("IB kräver en identifierad, unik försäkringspopulation")
        if any(p.state not in ("premium_paying", "paid_up")
               or p.plan.start <= self.period_end for p in e.policies):
            raise ValueError("Månadsförsöket stöder endast ej påbörjade, oförändrade referensplaner")
        if not reference_plan_unchanged(self):
            raise ValueError("Referensplanen ska stämma vid både IB och UB")
        if (e.valuation_date != date(2026, 10, 31) or self.period_end != date(2026, 11, 30)):
            raise ValueError("Första försöksunderlaget gäller oktober-IB och november 2026")
        snapshots = {b.code: b for b in self.bases}
        if len(snapshots) != len(self.bases):
            raise ValueError("Dubbla grundversioner")
        required = {**e.bases, self.opening_basis_code: None, self.opening_curve_code: None}
        if set(required) - set(snapshots):
            raise ValueError("Frysta grundversioner saknas")
        if any(digest is not None and snapshots[code].checksum != digest for code, digest in required.items()):
            raise ValueError("Utdragets grundreferens stämmer inte med fryst innehåll")
        parts = [g for p in e.policies for g in p.guarantee_parts]
        if len({g.premium_id for g in parts}) != len(parts):
            raise ValueError("En historisk premie får inte bilda flera ursprung")
        population = {p.policy_id for p in e.policies}
        invoice_ids = {i.id for i in self.invoices}
        if len(invoice_ids) != len(self.invoices):
            raise ValueError("Dubbla fakturaunderlag")
        obligations = [obligation(invoice, line) for invoice in self.invoices for line in invoice.lines]
        if len(set(obligations)) != len(obligations):
            raise ValueError("Samma ordinarie premieunderlag har fakturerats flera gånger")
        if any(line.policy_id not in population for i in self.invoices for line in i.lines):
            raise ValueError("Premieunderlaget utökar den frysta populationen")
        if any(not i.source.synthetic for i in self.invoices) or any(not r.source.synthetic for r in self.receipts):
            raise ValueError("Första försöket kräver uttryckligen syntetiska motpartsunderlag")
        if any(r.value_date != self.period_end for r in self.receipts):
            raise ValueError("Mottagningarna ska avse den valda novembermånaden")
        keys = [receipt_key(self.scenario_id, r) for r in self.receipts]
        if len(set(keys)) != len(keys):
            raise ValueError("Samma bankhändelse förekommer flera gånger i försöksunderlaget")
        if not self.parameters or any(not row.get("checksum") for row in self.parameters):
            raise ValueError("Frysta kapital- och skatteparametrar med kontrollsummor krävs")
        for row in self.parameters:
            if vb.checksum({k: v for k, v in row.items() if k != "checksum"}) != row["checksum"]:
                raise ValueError("Parameterinnehållets kontrollsumma stämmer inte")
        parameter_labels = {row.get("label") for row in self.parameters}
        if any(label not in parameter_labels for labels in e.parameters.values() for label in labels):
            raise ValueError("Utdragets parameterreferenser saknar fryst innehåll")
        if self.checksum and self.checksum != inputs_checksum(self):
            raise ValueError("Försöksunderlagets kontrollsumma stämmer inte")
        return self


def inputs_checksum(inputs: MonthInputs) -> str:
    return vb.checksum(inputs.model_dump(mode="json", exclude={"checksum"}))


def extended_returns(inputs: MonthInputs) -> dict:
    """Innehåll för nytt AVK-förslag; antar eller ändrar aldrig en registrerad grund."""
    old = next(b for b in inputs.bases if b.code == "AVK-SIM-2026-01")
    assumptions = vb.normalize("return_series", old.assumptions)
    if date.fromisoformat(assumptions["months"][-1]["month"]) != date(2026, 10, 1):
        raise ValueError("Startserien ska sluta i oktober 2026")
    return vb.normalize("return_series", {**assumptions,
        "description": "Syntetisk S-04-bana, historik bevarad; november enligt godkänt P6-MANAD-001 D5.",
        "months": [*assumptions["months"], {"month": "2026-11-01", "rate": str(inputs.november_return)}]})


def reference_plan_unchanged(inputs: MonthInputs) -> bool:
    """Referensplanen får inte tyst flyttas när försöksmånaden stängs."""
    for p in inputs.opening.policies:
        year, month = map(int, p.birth_month.split("-"))
        birth = date(year, month, 1 if p.born_on_first else 2)
        if aa.reference_start(birth, inputs.period_end) != p.plan.start:
            return False
    return True
