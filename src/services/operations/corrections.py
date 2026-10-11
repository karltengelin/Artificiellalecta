"""Rättelse av en premierad efter rättat löneunderlag (Fas 1f T3, PR-ITP1-019 p.1–2).

Ursprungsraden ändras aldrig. Rättelsen är en ny `adjustment`-rad med
`corrects_transaction_id` = ursprungsraden och differensen mellan rättad och
hittills gällande premie (ursprung + tidigare länkade rättelser). Premien räknas
om för just ursprungsmånaden med den månadens inkomstbasbelopp och trappan
(PR-ITP1-001, PR-ITP1-032). Den nya raden är `pending`: en ny fordran eller
kredit att fakturera (PR-ITP1-017) – kapitalet påverkas först när den tas emot.

Stöds:
- ej mottagen premie (`pending`/`invoiced`): kredit eller tillägg på fordran
- mottagen premie där rättad premie är minst det redan mottagna: tilläggspremie
  som ny fordran; ny garanti uppstår först när den tas emot (PR-ITP1-018)

Blockeras (manuell prövning):
- rättelse som skulle minska redan mottagen premie – återtag kräver spårad
  kapitalandel och historisk garantidel (PR-ITP1-019 p.3, PR-ITP1-020) som
  modellen saknar; operationen gissar ingen andel av dagens kapital
- flera premierader samma månad för personen (fördelning, PR-ITP1-015)
- andra radtyper än `premium`, makulerade rader, rader utan beräkningsunderlag
  eller som inte går att räkna fram igen, och IBB som avviker från radens underlag
- månad med justeringar utan länk (oklart om premien redan rättats)
- avliden försäkrad (avräkning enligt PR-ITP1-010)

Negativa rättighetsändringar och återkrav avgörs av människa (PR-ITP1-031) –
operationen är HUMAN_ONLY i åtkomstregistret.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select

from models import BaseAmount, InsuredPerson, Policy, PolicyBenefit, PremiumTransaction, SalaryReport
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError, ConflictError, NotFoundError
from services.operations import common
from skills.calculation.calculate_itp1_premium import calculate_itp1_premium

RULES = ["PR-ITP1-001", "PR-ITP1-014", "PR-ITP1-017", "PR-ITP1-019", "PR-ITP1-032"]


class PremiumCorrectionInput(BaseModel):
    transaction_id: uuid.UUID = Field(description="Premieraden som rättas (transaction_id i premiehistoriken)")
    corrected_salary_sek: Decimal = Field(
        ge=0, max_digits=10, decimal_places=2,
        description="Rättad pensionsmedförande lön för premiemånaden (PR-ITP1-014)",
    )
    basis_reference: str = Field(
        min_length=3, max_length=200, description="Det nya underlaget, t.ex. rättat lönebesked med referens"
    )


class PremiumCorrectionResult(BaseModel):
    original_transaction_id: str
    adjustment_transaction_id: str
    policy_number: str
    period_month: date
    case: str = Field(description="unreceived_claim = ej mottagen premie; additional_premium = tillägg på mottagen")
    income_base_amount_sek: Decimal = Field(description="Premiemånadens IBB")
    previous_salary_sek: Decimal
    corrected_salary_sek: Decimal
    previous_total_sek: Decimal = Field(description="Ursprungsraden + tidigare länkade rättelser")
    corrected_total_sek: Decimal
    difference_sek: Decimal = Field(description="Den nya rättelseradens belopp (+ tillägg, − kredit)")
    received_sek: Decimal = Field(description="Redan mottaget av månadens premie (ursprung + rättelser)")
    capital_effect: str


@operation(
    name="correct_premium_transaction",
    description=(
        "Rättar en premierad efter rättat löneunderlag (PR-ITP1-019 p.1): räknar om premien med "
        "premiemånadens IBB och skapar en länkad rättelserad med differensen som ny fordran eller kredit. "
        "Ursprungsraden bevaras. Minskning av redan mottagen premie blockeras."
    ),
    kind=OperationKind.WRITE,
    rules=RULES,
    pii=True,
)
def correct_premium_transaction(ctx: OperationContext, data: PremiumCorrectionInput) -> PremiumCorrectionResult:
    session = ctx.require_session()
    original = session.scalar(
        select(PremiumTransaction).where(PremiumTransaction.id == data.transaction_id).with_for_update()
    )
    if original is None:
        raise NotFoundError(f"Ingen premietransaktion med id {data.transaction_id}")
    if original.transaction_type != "premium":
        raise BlockedError(f"Bara ordinarie premierader rättas här – raden är {original.transaction_type}")
    if original.status == "cancelled":
        raise BlockedError("Raden är makulerad och kan inte rättas")

    benefit = session.get(PolicyBenefit, original.benefit_id)
    policy = session.get(Policy, benefit.policy_id)
    person = session.scalar(select(InsuredPerson).where(InsuredPerson.id == policy.insured_person_id).with_for_update())
    if person.status == "deceased":
        raise BlockedError("Den försäkrade är avliden – rättelse efter dödsfall avräknas manuellt (PR-ITP1-010)")

    month = original.period_month
    month_rows = common.premium_rows_in_month(session, common.benefit_ids_of(session, person.id), month)
    linked = [r for r in month_rows if r.corrects_transaction_id == original.id]
    _check_month(original, month_rows, linked)

    ibb = _income_base_amount(session, original)
    born = common.birth_date(person.personal_id_number)
    reproduced = calculate_itp1_premium(original.pensionable_salary_sek, ibb, birth_date=born, period_month=month)
    if reproduced.total_premium_sek != original.amount_sek:
        raise BlockedError(
            f"Ursprungsraden går inte att räkna fram igen ({original.amount_sek} kr enligt raden, "
            f"{reproduced.total_premium_sek} kr ur dess underlag) – manuell prövning"
        )

    report = _current_salary_report(session, person, month)
    if report is not None and Decimal(report.pensionable_salary_sek) != Decimal(data.corrected_salary_sek):
        raise BlockedError(
            f"Löneunderlaget för {month:%Y-%m} är registrerat (version {report.version}: "
            f"{report.pensionable_salary_sek} kr). Rätta först underlaget med register_salary_report"
        )

    corrected = calculate_itp1_premium(data.corrected_salary_sek, ibb, birth_date=born, period_month=month)
    previous_total = original.amount_sek + sum((r.amount_sek for r in linked), Decimal(0))
    received = sum((r.amount_sek for r in [original, *linked] if r.status == "paid"), Decimal(0))
    difference = corrected.total_premium_sek - previous_total
    if difference == 0:
        raise ConflictError(
            f"Premien för {month:%Y-%m} motsvarar redan det rättade underlaget ({previous_total} kr) – "
            "ingen rättelse behövs"
        )
    if corrected.total_premium_sek < received:
        raise BlockedError(
            f"Rättelsen skulle minska redan mottagen premie (mottaget {received} kr, rättad premie "
            f"{corrected.total_premium_sek} kr). Återtag kräver spårad kapitalandel och historisk garantidel "
            "(PR-ITP1-019 p.3, PR-ITP1-020), som saknas i modellen – manuell prövning"
        )
    case = "additional_premium" if received > 0 else "unreceived_claim"

    adjustment = PremiumTransaction(
        benefit_id=original.benefit_id,
        period_month=month,
        transaction_type="adjustment",
        pensionable_salary_sek=data.corrected_salary_sek,
        amount_sek=difference,
        status="pending",
        corrects_transaction_id=original.id,
        calculation_basis={
            "correction_of": str(original.id),
            "case": case,
            "rule": "PR-ITP1-019 p.1 lönerättelse",
            "ibb_year": month.year,
            "previous_salary": str(original.pensionable_salary_sek),
            "previous_total": str(previous_total),
            "corrected_total": str(corrected.total_premium_sek),
            "difference": str(difference),
            "received_before": str(received),
            "basis_reference": data.basis_reference,
            "salary_report": {"id": str(report.id), "version": report.version} if report else None,
            "premium_calculation": corrected.calculation_basis,
        },
    )
    session.add(adjustment)
    session.flush()

    return PremiumCorrectionResult(
        original_transaction_id=str(original.id),
        adjustment_transaction_id=str(adjustment.id),
        policy_number=policy.policy_number,
        period_month=month,
        case=case,
        income_base_amount_sek=ibb,
        previous_salary_sek=original.pensionable_salary_sek,
        corrected_salary_sek=data.corrected_salary_sek,
        previous_total_sek=previous_total,
        corrected_total_sek=corrected.total_premium_sek,
        difference_sek=difference,
        received_sek=received,
        capital_effect="Ingen nu – rättelseraden är en fordran/kredit (pending) som påverkar kapitalet först när den tas emot",
    )


def _check_month(original: PremiumTransaction, month_rows: list, linked: list) -> None:
    premiums = [r for r in month_rows if r.transaction_type == "premium"]
    if len(premiums) > 1:
        raise BlockedError(
            f"Personen har {len(premiums)} premierader för {original.period_month:%Y-%m} (flera försäkringar). "
            "Rättelsen kräver fördelning enligt PR-ITP1-015 – stöds inte"
        )
    unlinked = [r for r in month_rows if r.transaction_type == "adjustment" and r not in linked]
    if unlinked:
        raise BlockedError(
            f"{original.period_month:%Y-%m} har justeringar utan länk till premieraden – det går inte att avgöra "
            "om premien redan rättats. Manuell prövning"
        )
    if not original.calculation_basis:
        raise BlockedError("Ursprungsraden saknar beräkningsunderlag – rättelsen kan inte göras spårbart")
    if original.pensionable_salary_sek is None:
        raise BlockedError("Ursprungsraden saknar löneunderlag")


def _income_base_amount(session, original: PremiumTransaction) -> Decimal:
    """Premiemånadens IBB (PR-ITP1-032) – och samma som ursprungsraden räknades med."""
    base = session.get(BaseAmount, original.period_month.year)
    if base is None:
        raise NotFoundError(f"Inkomstbasbelopp saknas för {original.period_month.year} (tabellen base_amounts)")
    used = original.calculation_basis.get("ibb")
    if used is None or Decimal(used) != Decimal(base.income_base_amount_sek):
        raise BlockedError(
            f"IBB i ursprungsradens underlag ({used}) avviker från base_amounts för {original.period_month.year} "
            f"({base.income_base_amount_sek}) – manuell prövning"
        )
    return Decimal(base.income_base_amount_sek)


def _current_salary_report(session, person: InsuredPerson, month: date) -> SalaryReport | None:
    return session.scalar(
        select(SalaryReport)
        .where(
            SalaryReport.insured_person_id == person.id,
            SalaryReport.employer_id == person.employer_id,
            SalaryReport.period_month == month,
        )
        .order_by(SalaryReport.version.desc())
    )
