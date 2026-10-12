"""Hur tjänstelagrets data och fel visas för handläggaren: etiketter, format och felrutor."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from services import (
    AccessDeniedError,
    ApprovalError,
    BlockedError,
    ConflictError,
    InvalidInputError,
    MissingReasonError,
    NotFoundError,
    ProductRuleCatalog,
    ServiceError,
)

# --- etiketter ---------------------------------------------------------------------------------

POLICY_STATES = {
    "premium_paying": "Premiebetalande",
    "paid_up": "Fribrev",
    "in_payout": "Utbetalning pågår",
    "payout_paused": "Utbetalning pausad",
    "terminated": "Avslutad",
}
PERSON_STATUS = {
    "active": "Aktiv",
    "terminated": "Anställningen avslutad",
    "retired": "Pensionerad",
    "deceased": "Avliden",
}
TRANSACTION_TYPES = {"premium": "Premie", "adjustment": "Justering", "fee": "Avgift"}
TRANSACTION_STATUS = {"pending": "Ej fakturerad", "invoiced": "Fakturerad", "paid": "Betald", "cancelled": "Makulerad"}
BENEFIT_TYPES = {"retirement_dc": "Ålderspension", "tgl": "TGL", "family_protection": "Familjeskydd"}
SALARY_SOURCES = {"employer": "Arbetsgivaren", "manual": "Handläggare"}
EVENT_OUTCOMES = {"executed": "Utförd", "proposed": "Föreslagen", "rejected": "Avslagen", "denied": "Nekad"}
APPROVAL_STATUS = {"pending": "Väntar", "approved": "Godkänd", "rejected": "Avslagen"}
ACTOR_TYPES = {"human": "Handläggare", "agent": "Agent", "system": "Skript"}
OPERATION_KINDS = {"read": "Läsning", "compute": "Beräkning", "write": "Ändring", "external": "Extern"}

LABELS = {
    "policy_state": POLICY_STATES,
    "person_status": PERSON_STATUS,
    "transaction_type": TRANSACTION_TYPES,
    "transaction_status": TRANSACTION_STATUS,
    "benefit_type": BENEFIT_TYPES,
    "salary_source": SALARY_SOURCES,
    "event_outcome": EVENT_OUTCOMES,
    "approval_status": APPROVAL_STATUS,
    "actor_type": ACTOR_TYPES,
    "operation_kind": OPERATION_KINDS,
}


def label(value: Any, kind: str) -> str:
    if value is None:
        return "–"
    return LABELS[kind].get(str(value), str(value))


# --- format ------------------------------------------------------------------------------------

_NBSP = " "


def sek(value: Any, decimals: int = 2) -> str:
    """12 345,50 kr – svensk tusengruppering, decimalkomma."""
    if value is None or value == "":
        return "–"
    amount = Decimal(str(value))
    text = f"{amount:,.{decimals}f}".replace(",", _NBSP).replace(".", ",")
    return text.replace("-", "−") + f"{_NBSP}kr"


def number(value: Any) -> str:
    if value is None:
        return "–"
    return f"{Decimal(str(value)):,}".replace(",", _NBSP).replace(".", ",")


def iso_date(value: Any) -> str:
    if value is None or value == "":
        return "–"
    if isinstance(value, datetime):
        return local_time(value)
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    if "T" in text:  # tidsstämpel i ISO-format från händelseloggen och kön
        try:
            return local_time(datetime.fromisoformat(text))
        except ValueError:
            return text[:16].replace("T", " ")
    return text


def local_time(value: datetime) -> str:
    """Tjänstelagret sparar UTC (SQLite tappar tidszonen) – visas i datorns lokala tid."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def month(value: Any) -> str:
    if value is None or value == "":
        return "–"
    if isinstance(value, date):
        return f"{value:%Y-%m}"
    return str(value)[:7]


def personal_id(value: str | None) -> str:
    """ÅÅÅÅMMDD-NNNN för läsbarhet."""
    if not value or len(value) != 12:
        return value or "–"
    return f"{value[:8]}-{value[8:]}"


# --- formulärvärden ----------------------------------------------------------------------------


def clean_decimal(raw: str | None) -> str | None:
    """'45 000,50' → '45000.50'. Tom sträng → None (fältet saknas)."""
    if raw is None:
        return None
    text = re.sub(r"[\s  ]", "", raw).replace(",", ".").replace("−", "-")
    if not text:
        return None
    try:
        Decimal(text)
    except InvalidOperation:
        return text  # indatamodellen ger ett begripligt fel
    return text


def clean_month(raw: str | None) -> str | None:
    """'2026-10' (input type=month) → '2026-10-01'."""
    if not raw:
        return None
    text = raw.strip()
    return f"{text}-01" if re.fullmatch(r"\d{4}-\d{2}", text) else text


def clean_text(raw: str | None) -> str | None:
    text = (raw or "").strip()
    return text or None


# --- fel ---------------------------------------------------------------------------------------

_RULE_REF = re.compile(r"PR-ITP1-\d{3}")

FIELD_NAMES = {
    "__all__": "Uppgifterna",
    "personal_id_number": "Personnummer",
    "employer_org_number": "Arbetsgivarens organisationsnummer",
    "period_month": "Månad",
    "pensionable_salary_sek": "Pensionsmedförande lön",
    "kind": "Typ av rapport",
    "corrects_version": "Version som rättas",
    "source": "Ursprung",
    "source_reference": "Avsändarens referens",
    "received_date": "Mottagen",
    "policy_number": "Försäkringsnummer",
    "employment_end_date": "Anställningens sista dag",
    "transaction_id": "Premierad",
    "corrected_salary_sek": "Rättad lön",
    "basis_reference": "Underlag",
    "reason": "Motivering",
    "note": "Skäl",
    "first_name": "Förnamn",
    "last_name": "Efternamn",
    "employment_start_date": "Anställd från",
    "itp1_start_date": "ITP1 från",
    "employment_category": "Ställning",
    "affiliation_reference": "Anmälan",
    "monthly_salary_sek": "Aktuell månadslön",
    "employment_rate": "Tjänstgöringsgrad",
    "email": "E-post",
    "phone": "Telefon",
    "org_number": "Organisationsnummer",
    "name": "Namn",
    "affiliation_date": "Ansluten till ITP",
    "industry_code": "SNI-kod",
    "address_street": "Gatuadress",
    "address_postal_code": "Postnummer",
    "address_city": "Ort",
    "contact_name": "Kontaktperson",
    "contact_email": "Kontaktens e-post",
    "contact_phone": "Kontaktens telefon",
}


@dataclass
class ErrorView:
    """En felruta: vad som hände, varför, vilka regler – och att ingenting ändrades."""

    kind: str  # blocked, conflict, invalid, notfound, denied, approval, error
    title: str
    message: str
    status_code: int
    rules: list[dict[str, str | None]] = field(default_factory=list)
    field_errors: dict[str, str] = field(default_factory=dict)
    nothing_changed: bool = False


def describe_error(exc: Exception, rules: ProductRuleCatalog | None = None, *, write: bool = False) -> ErrorView:
    """write: felet kom från en ändring. Tjänstelagret rullar då tillbaka hela anropet –
    rutan säger uttryckligen att ingenting ändrades."""
    if isinstance(exc, BlockedError):
        view = ErrorView("blocked", "Stoppat – kräver manuell prövning", str(exc), 422)
    elif isinstance(exc, ConflictError):
        view = ErrorView("conflict", "Krock med aktuellt läge", str(exc), 409)
    elif isinstance(exc, MissingReasonError):
        view = ErrorView("invalid", "Motivering saknas", "Ändringar kräver en motivering.", 422,
                         field_errors={"reason": "Ange varför ändringen görs"})
    elif isinstance(exc, InvalidInputError):
        field_errors = _field_errors(exc.__cause__) if isinstance(exc.__cause__, ValidationError) else {}
        message = "Kontrollera fälten nedan." if field_errors else str(exc)
        view = ErrorView("invalid", "Ogiltiga uppgifter", message, 422, field_errors=field_errors)
    elif isinstance(exc, NotFoundError):
        view = ErrorView("notfound", "Hittades inte", str(exc), 404)
    elif isinstance(exc, AccessDeniedError):
        view = ErrorView("denied", "Ej behörig", str(exc), 403)
    elif isinstance(exc, ApprovalError):
        view = ErrorView("approval", "Godkännandet gick inte att genomföra", str(exc), 409)
    elif isinstance(exc, ServiceError):
        view = ErrorView("error", "Tjänstelagret avbröt anropet", str(exc), 500)
    else:
        view = ErrorView("error", "Oväntat fel", f"{type(exc).__name__}: {exc}", 500)
    view.rules = rule_refs(view.message, rules)
    view.nothing_changed = write and isinstance(exc, ServiceError)
    return view


def rule_refs(text: str, rules: ProductRuleCatalog | None) -> list[dict[str, str | None]]:
    """Produktregler som nämns i ett felmeddelande, med rubrik och status."""
    refs = []
    for rule_id in dict.fromkeys(_RULE_REF.findall(text or "")):
        refs.append({
            "id": rule_id,
            "title": rules.title(rule_id) if rules else None,
            "status": rules.label(rule_id) if rules else None,
        })
    return refs


def _field_errors(exc: ValidationError) -> dict[str, str]:
    errors: dict[str, str] = {}
    for error in exc.errors():
        loc = [str(part) for part in error.get("loc", ()) if not isinstance(part, int)]
        name = loc[0] if loc else "__all__"
        message = error.get("msg", "Ogiltigt värde")
        message = message.removeprefix("Value error, ")
        errors.setdefault(name, _translate(message, error.get("type", "")))
    return errors


def _translate(message: str, error_type: str) -> str:
    """Pydantics vanligaste meddelanden på svenska; övriga (redan svenska från modellerna) som de är."""
    translations = {
        "missing": "Obligatoriskt fält",
        "string_pattern_mismatch": "Fel format",
        "date_from_datetime_parsing": "Ange ett datum (ÅÅÅÅ-MM-DD)",
        "date_parsing": "Ange ett datum (ÅÅÅÅ-MM-DD)",
        "date_type": "Ange ett datum (ÅÅÅÅ-MM-DD)",
        "decimal_parsing": "Ange ett belopp, t.ex. 45000 eller 45 000,50",
        "decimal_type": "Ange ett belopp, t.ex. 45000 eller 45 000,50",
        "decimal_max_places": "Högst två decimaler",
        "decimal_max_digits": "För stort belopp",
        "greater_than_equal": "Får inte vara negativt",
        "literal_error": "Ogiltigt val",
        "int_parsing": "Ange ett heltal",
        "uuid_parsing": "Ogiltigt id",
        "less_than_equal": "För stort värde",
        "string_too_short": "För kort",
        "string_too_long": "För långt",
    }
    return translations.get(error_type, message)
