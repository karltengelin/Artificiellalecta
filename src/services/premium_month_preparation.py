"""Skrivskyddad förberedelse av novemberförsöket. Inga nya grunder antas här."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from analytics.portfolio_snapshot import birth_date
from models import (
    BaseAmount,
    InsuredPerson,
    Policy,
    PolicyBenefit,
    PolicyState,
    ProductParameter,
    ValuationBasis,
)
from services import parameters
from services import valuation_bases as vb
from services.premium_month_inputs import (
    BasisSnapshot,
    MonthInputs,
    inputs_checksum,
    reference_plan_unchanged,
)
from services.valuation import compute_valuation
from skills.calculation.calculate_itp1_premium import calculate_itp1_premium

OPENING_DATE = date(2026, 10, 31)
PERIOD_END = date(2026, 11, 30)


def bound_source(system: str, reference: str, payload: dict) -> dict:
    return {"system": system, "reference": reference, "version": "1", "synthetic": True,
            "payload": payload, "checksum": vb.checksum(payload)}


def snapshot_parameters(session) -> list[dict]:
    out = []
    for row in session.scalars(select(ProductParameter).where(ProductParameter.status == "valid")
                              .order_by(ProductParameter.key, ProductParameter.valid_from)):
        body = {"key": row.key, "value": str(parameters.plain(row.value)), "unit": row.unit,
                "valid_from": str(row.valid_from), "valid_to": str(row.valid_to) if row.valid_to else None,
                "rule_id": row.rule_id, "rule_version": row.rule_version, "source_ref": row.source_ref,
                "decision_ref": row.decision_ref, "label": parameters.label(row)}
        out.append({**body, "checksum": vb.checksum(body)})
    return out


def prepare_inputs(session, scenario_id: str, expected_opening_checksum: str) -> MonthInputs:
    """Läser och räknar; anroparen ansvarar för READ ONLY-transaktion vid Lakebase."""
    c = compute_valuation(session, OPENING_DATE, "scenario", basis_code="SIM-V-2026-01",
                          curve_code="FI-SIM-2026-10")
    if not c.checks_passed:
        raise ValueError("IB:s värderingskontroller är underkända")
    population = {p.policy_id for p in c.extract.policies}
    rows = session.execute(select(PolicyBenefit, Policy, InsuredPerson).select_from(PolicyBenefit)
                           .join(Policy, Policy.id == PolicyBenefit.policy_id)
                           .join(InsuredPerson, InsuredPerson.id == Policy.insured_person_id)
                           .order_by(Policy.policy_number, PolicyBenefit.id)).all()
    invoices, receipts = [], []
    for benefit, policy, person in rows:
        if (str(policy.id) not in population or benefit.benefit_type != "retirement_dc"
                or benefit.start_date > date(2026, 10, 1)
                or benefit.end_date is not None and benefit.end_date < OPENING_DATE):
            continue
        state = session.scalar(select(PolicyState).where(PolicyState.policy_id == policy.id,
            PolicyState.valid_from <= date(2026, 10, 1),
            (PolicyState.valid_to.is_(None)) | (PolicyState.valid_to >= date(2026, 10, 1))))
        if state is None or state.state != "premium_paying":
            continue
        # Ett syntetiskt löneunderlag, inte ett påstående om faktiskt rapporterad lön.
        period = date(2026, 10, 1)
        base_amount = session.get(BaseAmount, period.year)
        if base_amount is None:
            raise ValueError("IBB för den syntetiska premieperioden saknas")
        born = birth_date(person.personal_id_number)
        if born is None:
            raise ValueError("Saknat födelsedatum")
        calculated = calculate_itp1_premium(Decimal(45000), base_amount.income_base_amount_sek,
            birth_date=born, period_month=period, parameters=parameters.premium_parameters(session, period))
        if not calculated.in_age_window or calculated.total_premium_sek <= 0:
            continue
        index = len(invoices) + 1
        invoice_id = f"synthetic-invoice-{index:04}"
        line = {"id": "line-1", "policy_id": str(policy.id), "benefit_id": str(benefit.id),
                "period_month": period.isoformat(), "due_sek": str(calculated.total_premium_sek),
                "calculation_basis": {**calculated.calculation_basis, "synthetic_salary_sek": "45000",
                                      "product_package": "PR-ITP1-v1.0", "decision": "P6-MANAD-001 D2"}}
        invoice_body = {"id": invoice_id, "payer_id": str(person.employer_id), "lines": [line]}
        invoices.append({**invoice_body, "source": bound_source("synthetic-employer", invoice_id, invoice_body)})
        receipt_body = {"event_id": f"payment-{index:04}", "payment_reference": invoice_id,
            "payer_id": str(person.employer_id), "received_date": "2026-11-16", "currency": "SEK",
            "gross_sek": str(calculated.total_premium_sek), "external_deduction_sek": "0.00",
            "net_sek": str(calculated.total_premium_sek), "invoice_id": invoice_id}
        receipts.append({**receipt_body, "source": bound_source("synthetic-bank", receipt_body["event_id"], receipt_body)})
        if len(invoices) == 12:
            break
    if len(invoices) < 10:
        raise ValueError("Försöket kräver minst tio behöriga befintliga försäkringar för skyddade aggregat")
    required = set(c.extract.bases) | {c.basis.code, c.curve.code, "SIM-G-2026-01"}
    bases = [BasisSnapshot(code=b.code, purpose=b.purpose, assumptions=b.assumptions, checksum=b.checksum,
                           valid_from=b.valid_from, valid_to=b.valid_to)
             for b in session.scalars(select(ValuationBasis).where(ValuationBasis.code.in_(required))
                                      .order_by(ValuationBasis.code))]
    package = MonthInputs(scenario_id=scenario_id, opening=c.extract, bases=bases,
        parameters=snapshot_parameters(session), opening_basis_code=c.basis.code, opening_curve_code=c.curve.code,
        expected_opening_checksum=expected_opening_checksum, code_version=c.code_version,
        period_end=PERIOD_END, invoices=invoices, receipts=receipts)
    if not reference_plan_unchanged(package):
        raise ValueError("Referensplaner flyttas under försöksmånaden")
    return MonthInputs.model_validate({**package.model_dump(mode="json"), "checksum": inputs_checksum(package)})
