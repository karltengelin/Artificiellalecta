"""Premieunderlag ur registrerat löneunderlag (paket A steg 1, B-046, P1-PREMIE-001 §4.3).

Ordinarie premie beräknas en gång per person, arbetsgivare och månad ur den gällande
versionen av löneunderlaget, med premiemånadens IBB och produktparametrar och utan
premie utanför åldersfönstret (PR-ITP1-001, -013, -014). Premien går till personens
enda ännu inte startade ålderspensionsförmån (PR-ITP1-015). Den sparas som en
`premium`-rad i `premium_transactions` med status `pending` – en kommande fordran,
inte kapital. Noll premie sparas som underlag men ger ingen fakturarad.

Rättat löneunderlag räknas om för just ursprungsmånaden. Skillnaden blir en länkad
`adjustment`-rad (PR-ITP1-019 p.1), som ny fordran eller kredit. Hur rättelsen
faktureras står i invoices.py (P1-PREMIE-001 §4.4).

Stöds: premieperioder från 2026-10 (PA1), en ålderspensionsförmån som mottagare och
ett registrerat löneunderlag hos personens arbetsgivare.

Blockeras (manuell prövning):
- premieperiod före 2026-10 – startluckan juli–september 2026 och den genererade
  historiken (PA1)
- avliden försäkrad (PR-ITP1-010)
- ingen eller flera möjliga mottagare – fördelningsinstruktion saknas (PR-ITP1-015)
- månad med premie som inte bygger på registrerat löneunderlag, eller med justeringar
  utan länk
- rättelse som skulle minska redan mottagen premie – återtag ingår inte (PR-ITP1-019 p.3)
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from models import BaseAmount, Employer, Policy, PolicyBenefit, PolicyState, PremiumTransaction, SalaryReport
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, ConflictError, NotFoundError
from services.operations import common
from services.parameters import premium_parameters
from skills.calculation.calculate_itp1_premium import calculate_itp1_premium

RULES = ["PR-ITP1-001", "PR-ITP1-013", "PR-ITP1-014", "PR-ITP1-015", "PR-ITP1-019"]
#: Första operativa premieperiod enligt B-046 (PA1)
FIRST_OPERATIVE_PERIOD = date(2026, 10, 1)
#: Lägen där premiedelen har startat och inte längre tar emot ny premie (PR-ITP1-015)
STARTED_STATES = ("in_payout", "payout_paused")
RULE_PACKAGE = "PR-ITP1 v1.0"
DESIGN_REF = "P1-PREMIE-001 §4.3"


class PremiumBasisInput(BaseModel):
    personal_id_number: str = Field(pattern=r"^\d{12}$", description="Den försäkrades personnummer, 12 siffror")
    employer_org_number: str = Field(pattern=r"^\d{10}$", description="Arbetsgivarens organisationsnummer, 10 siffror")
    period_month: date = Field(description="Premiemånaden – dagen i datumet ignoreras")

    @field_validator("period_month")
    @classmethod
    def _first_of_month(cls, value: date) -> date:
        return common.month_of(value)


class PremiumBasisResult(BaseModel):
    period_month: date
    policy_number: str
    case: Literal["new_premium", "correction", "unchanged"] = Field(
        description="new_premium = ny premierad; correction = länkad rättelserad; unchanged = premien är oförändrad"
    )
    salary_report_id: str
    salary_report_version: int
    pensionable_salary_sek: Decimal
    income_base_amount_sek: Decimal
    in_age_window: bool
    transaction_id: str | None = Field(description="Den nya raden; saknas när premien är oförändrad")
    transaction_type: str | None
    amount_sek: Decimal = Field(description="Den nya radens belopp (+ fordran, − kredit); 0 när oförändrad")
    month_total_sek: Decimal = Field(description="Månadens premie efter åtgärden (premierad + länkade rättelser)")
    received_sek: Decimal = Field(description="Redan mottaget av månadens premie")
    invoiceable: bool = Field(description="Om raden ska faktureras – noll ger ingen fakturarad")
    note: str


@operation(
    name="create_premium_from_salary_report",
    description=(
        "Skapar premieunderlag ur det gällande löneunderlaget för en försäkrad, arbetsgivare och månad "
        "(PR-ITP1-001, -015): ny premierad, eller en länkad rättelserad när underlaget rättats "
        "(PR-ITP1-019 p.1). Raden är en kommande fordran, inte kapital. Från premieperiod 2026-10 (B-046)."
    ),
    kind=OperationKind.WRITE,
    rules=RULES,
    pii=True,
)
def create_premium_from_salary_report(ctx: OperationContext, data: PremiumBasisInput) -> PremiumBasisResult:
    session = ctx.require_session()
    month = data.period_month
    if month < FIRST_OPERATIVE_PERIOD:
        raise BlockedError(
            f"{month:%Y-%m} ligger före första operativa premieperiod {FIRST_OPERATIVE_PERIOD:%Y-%m}. "
            "Juli–september 2026 är en märkt startlucka och den genererade historiken rättas med "
            "correct_premium_transaction (B-046, PA1)"
        )
    person = common.lock_person(session, data.personal_id_number)
    if person.status == "deceased":
        raise BlockedError("Den försäkrade är avliden – premie efter dödsfall prövas manuellt (PR-ITP1-010)")
    employer = session.scalar(select(Employer).where(Employer.org_number == data.employer_org_number))
    if employer is None:
        raise NotFoundError(f"Ingen arbetsgivare med organisationsnummer {data.employer_org_number}")
    report = session.scalar(
        select(SalaryReport)
        .where(
            SalaryReport.insured_person_id == person.id,
            SalaryReport.employer_id == employer.id,
            SalaryReport.period_month == month,
        )
        .order_by(SalaryReport.version.desc())
        .limit(1)
    )
    if report is None:
        raise NotFoundError(
            f"Inget registrerat löneunderlag för {month:%Y-%m} hos arbetsgivaren – registrera det först med "
            "register_salary_report. En saknad rapport ger ingen premie (PR-ITP1-017)"
        )
    base = session.get(BaseAmount, month.year)
    if base is None:
        raise NotFoundError(f"Inkomstbasbelopp saknas för {month.year} (tabellen base_amounts)")
    ibb = Decimal(base.income_base_amount_sek)
    benefit, policy = _recipient(session, person, month)

    calc = calculate_itp1_premium(
        report.pensionable_salary_sek, ibb, birth_date=common.birth_date(person.personal_id_number),
        period_month=month, parameters=premium_parameters(session, month),
    )
    report_ref = {
        "id": str(report.id), "version": report.version, "source": report.source,
        "source_reference": report.source_reference, "received_date": report.received_date.isoformat(),
    }
    month_rows = common.premium_rows_in_month(session, common.benefit_ids_of(session, person.id), month)
    common_fields = dict(
        period_month=month, policy_number=policy.policy_number, salary_report_id=str(report.id),
        salary_report_version=report.version, pensionable_salary_sek=report.pensionable_salary_sek,
        income_base_amount_sek=ibb, in_age_window=bool(calc.in_age_window),
    )

    if not month_rows:
        row = PremiumTransaction(
            benefit_id=benefit.id, period_month=month, transaction_type="premium",
            pensionable_salary_sek=report.pensionable_salary_sek, amount_sek=calc.total_premium_sek,
            status="pending",
            calculation_basis={
                **calc.calculation_basis, "salary_report": report_ref, "employer_org_number": employer.org_number,
                "rule_package": RULE_PACKAGE, "design": DESIGN_REF, "recipient": "enda ej startade förmån, vikt 1",
            },
        )
        session.add(row)
        session.flush()
        zero = calc.total_premium_sek == 0
        return PremiumBasisResult(
            **common_fields, case="new_premium", transaction_id=str(row.id), transaction_type="premium",
            amount_sek=calc.total_premium_sek, month_total_sek=calc.total_premium_sek,
            received_sek=Decimal("0.00"), invoiceable=not zero,
            note=("Noll premie sparad som underlag – ingen fakturarad"
                  + (" (utanför åldersfönstret, PR-ITP1-013)" if calc.in_age_window is False else "")
                  if zero else "Ny premierad som kommande fordran (pending)"),
        )

    original, linked = _premium_of_month(month_rows, benefit)
    used_version = max(_report_version(r) for r in [original, *linked])
    if used_version >= report.version:
        raise ConflictError(
            f"Premien för {month:%Y-%m} bygger redan på löneunderlagets version {used_version} – inget nytt underlag"
        )
    previous_total = original.amount_sek + sum((r.amount_sek for r in linked), Decimal(0))
    received = sum((r.amount_sek for r in [original, *linked] if r.status == "paid"), Decimal(0))
    difference = calc.total_premium_sek - previous_total
    if difference == 0:
        return PremiumBasisResult(
            **common_fields, case="unchanged", transaction_id=None, transaction_type=None,
            amount_sek=Decimal("0.00"), month_total_sek=previous_total, received_sek=received, invoiceable=False,
            note=f"Rättat underlag ger samma premie ({previous_total} kr) – ingen ny rad",
        )
    if calc.total_premium_sek < received:
        raise BlockedError(
            f"Rättelsen skulle minska redan mottagen premie (mottaget {received} kr, rättad premie "
            f"{calc.total_premium_sek} kr). Återtag ingår inte (PR-ITP1-019 p.3, B-046) – manuell prövning"
        )
    case = "additional_premium" if received > 0 else "unreceived_claim"
    row = PremiumTransaction(
        benefit_id=benefit.id, period_month=month, transaction_type="adjustment",
        pensionable_salary_sek=report.pensionable_salary_sek, amount_sek=difference, status="pending",
        corrects_transaction_id=original.id,
        calculation_basis={
            "correction_of": str(original.id), "case": case, "rule": "PR-ITP1-019 p.1 lönerättelse",
            "salary_report": report_ref, "previous_salary_report_version": used_version,
            "previous_total": str(previous_total), "corrected_total": str(calc.total_premium_sek),
            "difference": str(difference), "received_before": str(received),
            "rule_package": RULE_PACKAGE, "design": DESIGN_REF, "premium_calculation": calc.calculation_basis,
        },
    )
    session.add(row)
    session.flush()
    return PremiumBasisResult(
        **common_fields, case="correction", transaction_id=str(row.id), transaction_type="adjustment",
        amount_sek=difference, month_total_sek=calc.total_premium_sek, received_sek=received,
        invoiceable=True,
        note=(f"Rättat från {previous_total} till {calc.total_premium_sek} kr: "
              + ("tilläggspremie på mottagen premie; ny garanti först när den tas emot"
                 if case == "additional_premium" else "fordran eller kredit som ännu inte är mottagen")),
    )


def _recipient(session, person, month: date) -> tuple[PolicyBenefit, Policy]:
    """PR-ITP1-015: personens enda ålderspensionsförmån som ännu inte har startat utbetalning."""
    month_end = month.replace(day=28) + timedelta(days=4)
    month_end = month_end - timedelta(days=month_end.day)
    candidates = session.execute(
        select(PolicyBenefit, Policy)
        .join(Policy, PolicyBenefit.policy_id == Policy.id)
        .where(
            Policy.insured_person_id == person.id,
            PolicyBenefit.benefit_type == "retirement_dc",
            PolicyBenefit.start_date <= month_end,
            (PolicyBenefit.end_date.is_(None)) | (PolicyBenefit.end_date >= month),
        )
    ).all()
    eligible = []
    for benefit, policy in candidates:
        started = session.scalar(
            select(PolicyState.id).where(
                PolicyState.policy_id == policy.id,
                PolicyState.state.in_(STARTED_STATES),
                PolicyState.valid_from <= month_end,
                (PolicyState.valid_to.is_(None)) | (PolicyState.valid_to >= month),
            ).limit(1)
        )
        if started is None:
            eligible.append((benefit, policy))
    if not eligible:
        raise BlockedError(
            f"Ingen ålderspensionsförmån kan ta emot premie för {month:%Y-%m} – utbetalning har startat eller "
            "förmån saknas (PR-ITP1-015, -025). Manuell prövning"
        )
    if len(eligible) > 1:
        raise BlockedError(
            f"{len(eligible)} förmåner kan ta emot premie för {month:%Y-%m}. Fördelning kräver en "
            "fördelningsinstruktion eller uttrycklig primär mottagare (PR-ITP1-015) – stöds inte ännu"
        )
    return eligible[0]


def _premium_of_month(month_rows: list[PremiumTransaction], benefit: PolicyBenefit):
    premiums = [r for r in month_rows if r.transaction_type == "premium"]
    if len(premiums) != 1 or premiums[0].benefit_id != benefit.id:
        raise BlockedError(
            "Månaden har premierader för flera eller andra förmåner – fördelningen kan inte avgöras (PR-ITP1-015)"
        )
    original = premiums[0]
    linked = [r for r in month_rows if r.corrects_transaction_id == original.id]
    if any(r.transaction_type == "adjustment" and r not in linked for r in month_rows):
        raise BlockedError("Månaden har justeringar utan länk till premieraden – manuell prövning")
    if _report_version(original) is None:
        raise BlockedError(
            "Månadens premie bygger inte på registrerat löneunderlag – rätta den med correct_premium_transaction"
        )
    if any(_report_version(r) is None for r in linked):
        raise BlockedError("En rättelserad för månaden saknar länk till löneunderlaget – manuell prövning")
    return original, linked


def _report_version(row: PremiumTransaction) -> int | None:
    version = ((row.calculation_basis or {}).get("salary_report") or {}).get("version")
    return None if version is None else int(version)
