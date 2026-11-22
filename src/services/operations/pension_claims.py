"""Bolagskonto och månadsrätter (paket B steg 5, B-047 punkt 6 och 8, P1-PENSION-001 §9 och §10).

Två operationer, båda `HUMAN_ONLY` (PB12, Karls val W7 och W12 2026-11-22). Agenter nekas även i
operationen, och den skrivande nekar också systemaktören:

- `register_company_capital` bokar ägarens dokumenterade insättning på bolagskontot som en egen
  verifikation `company_capital` i första öppna månaden, med belopp, beslutsdag, dokumentreferens och
  valfri hänvisning till aktuariens E_min (PR-ITP1-028, PB11). Samma insättning igen ger ingen ny effekt.
  E_min räknas inte här – det gör aktuarien i projekt 6 (A8).
- `list_pension_claims` visar månadsrätterna för en månad med finansiering och kvarstående ej
  finansierat belopp, och bolagskontots läge.

Månadsrätterna bokas av månadsstängningen (`close_policy_month`). Logiken ligger i
`services.pension_claims`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import Field

from services import pension_claims as pc
from services.contract import OperationContext, OperationKind, operation
from services.errors import BlockedError
from services.operations.actuarial_analysis import JsonResult
from services.operations.capital_ledger import _human, _no_agent, _require_journal
from services.premium_month_inputs import Strict

RULES = ["PR-ITP1-020", "PR-ITP1-026", "PR-ITP1-027", "PR-ITP1-028"]


def _session(ctx: OperationContext):
    session = ctx.require_session()
    _require_journal(session)
    if not pc.claims_present(session):
        raise BlockedError("Månadsrätterna är inte införda i vald databas – migrate_pension_claims.py först")
    return session


class CapitalInput(Strict):
    amount_sek: Decimal = Field(gt=0, max_digits=14, decimal_places=2, description="Insättningen i kronor")
    decided_on: date = Field(description="Dagen ägaren beslutade insättningen")
    document_ref: str = Field(min_length=3, max_length=200, description="Referens till beslutsunderlaget")
    note: str = Field(default="", max_length=2000, description="Kommentar")
    emin_reference: str | None = Field(default=None, max_length=200,
                                       description="Hänvisning till aktuariens E_min (projekt 6, A8), om den finns")


class ClaimsInput(Strict):
    month: date | None = Field(default=None, description="Rättighetsmånaden, ÅÅÅÅ-MM-01; utan: alla månader")


@operation(
    name="register_company_capital",
    description="Bokar ägarens dokumenterade insättning på bolagskontot (PR-ITP1-028) som en egen verifikation i "
                "första öppna månaden. Bolagskontot finansierar bristen när kundkapitalet inte räcker till en "
                "månadsrätt. Samma insättning igen ger ingen ny effekt.",
    kind=OperationKind.WRITE,
    rules=["PR-ITP1-028"],
)
def register_company_capital(ctx: OperationContext, data: CapitalInput) -> JsonResult:
    _human(ctx, "register_company_capital", "Bolagskapitalet")
    session = _session(ctx)
    try:
        batch, created = pc.register_capital(session, data.amount_sek, data.decided_on, data.document_ref,
                                              data.note, data.emin_reference, ctx.actor.id)
    except pc.ClaimServiceError as exc:
        raise BlockedError(str(exc)) from exc
    return JsonResult(payload={**batch.content, "batch_id": str(batch.id), "checksum": batch.checksum,
                               "created": created})


@operation(
    name="list_pension_claims",
    description="Visar månadsrätterna med brutto, kapitaldel, bolagsstöd, ej finansierat och betalningsdag, och "
                "bolagskontots saldo, insättningar och betalningsskuld.",
    kind=OperationKind.READ,
    rules=RULES,
    pii=True,
)
def list_pension_claims(ctx: OperationContext, data: ClaimsInput) -> JsonResult:
    _no_agent(ctx, "list_pension_claims")
    session = _session(ctx)
    month = data.month.replace(day=1) if data.month else None
    claims = pc.claims_view(session, month=month)
    on = month or (max((date.fromisoformat(c["right_month"]) for c in claims), default=None)
                   or pc.first_open_month(session))
    return JsonResult(payload={"month": month.isoformat() if month else None, "claims": claims,
                               "count": len(claims), "company": pc.company_view(session, on)})
