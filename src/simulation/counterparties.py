"""Motpartssimulatorn: arbetsgivarens löneunderlagsfil och bankens filer (B-046, PA8, P1-PREMIE-001 §9).

Simulatorn läser beståndet och skapar filer som om de kom utifrån. Den skriver aldrig i
affärstabellerna. Filerna lämnas till `import_salary_file` och `import_bank_file` som vilken
fil som helst och går genom samma kontroller. Varje fil märks med simulatorns version och seed,
i filreferensen och i `label`. Facit hålls separat i `facit` och skrivs aldrig i databasen
(processöversikten §4).

Samma seed, scenario och bestånd ger samma fil, byte för byte. En fil som lämnas in två gånger
blir därför samma intag (fall 6 och 15).

Bankens kvittofil för utbetalningar (paket B steg 6, Karls val X11) är bara banksidan: den läser den
godkända bankfilen som banken fått och svarar per uppdrag med utfört, avvisat, återkommet eller okänt.
Kunden och Skatteverket simuleras inte.

Folkbokföringens avisering om dödsfall (paket B steg 7, Karls val Y14) har källan `population-register-sim`:
personnummer, dödsdag, aviseringsdag och besked-id. Den läses med `import_death_notices`, där varje besked
registreras som misstänkt och verifieras av handläggaren. Anhörigas besked registreras manuellt och simuleras
inte.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import func, select

from models import (
    Employer,
    InsuredPerson,
    Invoice,
    InvoiceLineRecord,
    PaymentAllocation,
    Policy,
    PolicyState,
    SalaryReport,
)
from services.death_reports import POPULATION_SOURCE, notice_file_checksum
from services.operations.common import luhn_valid, month_of
from services.operations.payments import bank_file_checksum
from services.operations.salary_files import file_checksum
from services.payout_orders import receipt_file_checksum
from utils.bank_calendar import next_bank_day

SIMULATOR = "motpartssimulator"
VERSION = "1"
BANK_SOURCE = "bank-sim"
PAYOUT_BANK_SOURCE = "bank-sim-payout"
CENT = Decimal("0.01")
#: Lön för en okänd person i filen; beloppet spelar ingen roll, raden registreras aldrig
UNKNOWN_SALARY = Decimal(40000)


# --- filen ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SimulatedFile:
    """En fil från en motpart: indata till operationen, märkning och facit var för sig."""

    kind: Literal["salary_file", "bank_file", "payout_receipt_file", "death_notice_file"]
    operation: str
    payload: dict[str, Any]
    label: dict[str, Any]
    facit: dict[str, Any]

    @property
    def reference(self) -> str:
        return self.payload["file_reference"]

    @property
    def empty(self) -> bool:
        if self.kind == "payout_receipt_file":
            return not self.payload["receipts"]
        if self.kind == "death_notice_file":
            return not self.payload["notices"]
        return self.kind == "bank_file" and not self.payload["events"]

    def write(self, directory: Path) -> tuple[Path, Path]:
        """Skriver filen och facit som två JSON-filer. Facit hamnar aldrig i filen till operationen."""
        directory.mkdir(parents=True, exist_ok=True)
        name = self.reference.replace("/", "_")
        content = directory / f"{name}.json"
        facit = directory / f"{name}.facit.json"
        content.write_text(_dump({**self.payload, "_label": self.label}), encoding="utf-8")
        facit.write_text(_dump({"label": self.label, "facit": self.facit}), encoding="utf-8")
        return content, facit


def load_payload(path: Path) -> dict[str, Any]:
    """Läser en skriven fil som indata till operationen (märkningen tas bort)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("_label", None)
    return data


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"


def _label(seed: int, scenario: Any) -> dict[str, Any]:
    scenario_dict = {k: str(v) if isinstance(v, Decimal) else v for k, v in asdict(scenario).items()} \
        if not isinstance(scenario, dict) else scenario
    return {"simulator": SIMULATOR, "version": VERSION, "seed": seed, "scenario": scenario_dict}


def _money(value: Decimal) -> str:
    return format(Decimal(value).quantize(CENT), "f")


# --- arbetsgivarens löneunderlagsfil ---------------------------------------------------------------


@dataclass(frozen=True)
class SalaryScenario:
    """Uttryckliga avvikelser i en arbetsgivarfil. Utan avvikelser rapporteras alla med aktuell lön."""

    missing: int = 0
    """Premiebetalande personer som utelämnas (fall 4)."""
    zero: int = 0
    """Personer som rapporteras med uttrycklig lön 0 kr (fall 3)."""
    unknown_person: bool = False
    """En rad för en person som inte finns i beståndet (fall 5)."""
    corrections: int = 0
    """Redan rapporterade personer som får en rättelserad (fall 8–11)."""
    correction_change: Decimal = Decimal("0.10")
    """Rättelsens ändring som andel av gällande lön; negativ för rättelse nedåt."""
    salary_variation: Decimal = Decimal(0)
    """Seedbunden variation kring aktuell lön, som andel åt vardera hållet."""


def salary_file(session, employer_org_number: str, period: date, *, received_date: date, seed: int,
                scenario: SalaryScenario | None = None, file_reference: str | None = None) -> SimulatedFile:
    """Arbetsgivarens löneunderlagsfil för en period, ur beståndet och scenariot.

    Premiebetalande personer utan rapport för perioden får en ny rad. Redan rapporterade får
    bara en rad om scenariot rättar dem, så att en ny fil för samma period inte dubbelrapporterar.
    """
    scenario = scenario or SalaryScenario()
    period = month_of(period)
    employer = _employer(session, employer_org_number)
    rng = random.Random(f"{seed}:{employer_org_number}:{period:%Y-%m}")
    people = _premium_paying(session, employer, period)
    reported = _reported_versions(session, employer, period)
    fresh = [p for p in people if p.personal_id_number not in reported]
    already = [p for p in people if p.personal_id_number in reported]
    if scenario.missing + scenario.zero > len(fresh):
        raise ValueError(f"Scenariot utelämnar eller nollar {scenario.missing + scenario.zero} personer, men bara "
                         f"{len(fresh)} är orapporterade för {period:%Y-%m}")
    if scenario.corrections > len(already):
        raise ValueError(f"Scenariot rättar {scenario.corrections} personer, men bara {len(already)} är "
                         f"rapporterade för {period:%Y-%m}")

    picked = rng.sample([p.personal_id_number for p in fresh], scenario.missing + scenario.zero)
    missing, zero = set(picked[: scenario.missing]), set(picked[scenario.missing:])
    corrected = set(rng.sample([p.personal_id_number for p in already], scenario.corrections))

    rows: list[dict[str, Any]] = []
    for person in fresh:
        pnr = person.personal_id_number
        if pnr in missing:
            continue
        salary = Decimal(0) if pnr in zero else _vary(rng, person.monthly_salary_sek, scenario.salary_variation)
        rows.append(_row(pnr, period, salary, "new"))
    for person in already:
        pnr = person.personal_id_number
        if pnr in corrected:
            version, salary = reported[pnr]
            changed = (salary * (1 + scenario.correction_change)).quantize(Decimal(1), ROUND_HALF_UP)
            rows.append(_row(pnr, period, max(changed, Decimal(0)), "correction", corrects_version=version))
    unknown = []
    if scenario.unknown_person:
        unknown.append(_unknown_person(session, rng))
        rows.append(_row(unknown[0], period, UNKNOWN_SALARY, "new"))
    rows.sort(key=lambda r: (r["personal_id_number"], r["kind"]))

    reference = file_reference or f"SIM{VERSION}-{employer_org_number}-{period:%Y%m}-S{seed}"
    checksum = file_checksum(employer_org_number, period, reference, received_date, rows)
    payload = {
        "employer_org_number": employer_org_number, "period_month": period.isoformat(),
        "file_reference": reference, "received_date": received_date.isoformat(), "checksum": checksum,
        "rows": rows,
    }
    facit = {
        "rows": len(rows),
        "new": sorted(r["personal_id_number"] for r in rows if r["kind"] == "new"
                      and r["personal_id_number"] not in zero and r["personal_id_number"] not in unknown),
        "zero": sorted(zero),
        "missing": sorted(missing),
        "unknown": unknown,
        "corrections": sorted(corrected),
        "expected": {"valid": len(rows) - len(unknown), "deviations": len(unknown), "missing": len(missing)},
    }
    return SimulatedFile("salary_file", "import_salary_file", payload, _label(seed, scenario), facit)


def _row(pnr: str, period: date, salary: Decimal, kind: str, *, corrects_version: int | None = None) -> dict:
    return {"personal_id_number": pnr, "period_month": period.isoformat(), "pensionable_salary_sek": _money(salary),
            "kind": kind, "corrects_version": corrects_version}


def _vary(rng: random.Random, salary: Decimal, variation: Decimal) -> Decimal:
    if not variation:
        return Decimal(salary).quantize(Decimal(1), ROUND_HALF_UP)
    factor = Decimal(str(round(rng.uniform(-float(variation), float(variation)), 4)))
    return (salary * (1 + factor)).quantize(Decimal(1), ROUND_HALF_UP)


def _employer(session, org_number: str) -> Employer:
    employer = session.scalar(select(Employer).where(Employer.org_number == org_number))
    if employer is None:
        raise ValueError(f"Ingen arbetsgivare med organisationsnummer {org_number} i beståndet")
    return employer


def _month_end(month: date) -> date:
    following = month.replace(day=28) + timedelta(days=4)
    return following - timedelta(days=following.day)


def _premium_paying(session, employer: Employer, period: date) -> list[InsuredPerson]:
    """Samma urval som intagets kontroll av saknade rapporter: premiebetalande under perioden."""
    end = _month_end(period)
    people = session.scalars(
        select(InsuredPerson)
        .join(Policy, Policy.insured_person_id == InsuredPerson.id)
        .join(PolicyState, PolicyState.policy_id == Policy.id)
        .where(
            InsuredPerson.employer_id == employer.id,
            InsuredPerson.status != "deceased",
            PolicyState.state == "premium_paying",
            PolicyState.valid_from <= end,
            (PolicyState.valid_to.is_(None)) | (PolicyState.valid_to >= period),
        )
        .order_by(InsuredPerson.personal_id_number)
    ).all()
    unique: dict[str, InsuredPerson] = {}
    for person in people:
        unique.setdefault(person.personal_id_number, person)
    return list(unique.values())


def _reported_versions(session, employer: Employer, period: date) -> dict[str, tuple[int, Decimal]]:
    """Gällande version och lön per person med rapport för perioden."""
    rows = session.execute(
        select(InsuredPerson.personal_id_number, SalaryReport.version, SalaryReport.pensionable_salary_sek)
        .join(InsuredPerson, InsuredPerson.id == SalaryReport.insured_person_id)
        .where(SalaryReport.employer_id == employer.id, SalaryReport.period_month == period)
        .order_by(SalaryReport.version)
    ).all()
    return {pnr: (version, salary) for pnr, version, salary in rows}


def _unknown_person(session, rng: random.Random) -> str:
    """Ett Luhn-giltigt personnummer som inte finns i beståndet."""
    while True:
        stem = f"80{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}{rng.randint(900, 999):03d}"
        check = next(d for d in range(10) if luhn_valid(f"{stem}{d}"))
        pnr = f"19{stem}{check}"
        if session.scalar(select(InsuredPerson.id).where(InsuredPerson.personal_id_number == pnr)) is None:
            return pnr


# --- bankens fil ---------------------------------------------------------------------------------

PaymentKind = Literal["on_time", "partial", "late", "wrong_reference", "wrong_payer", "twice", "none"]


@dataclass(frozen=True)
class PaymentBehaviour:
    """Hur en arbetsgivare betalar sina öppna debetfakturor för perioden."""

    kind: PaymentKind = "on_time"
    days_after_invoice: int = 5
    """Betalningsdag räknat från fakturadagen, högst förfallodagen (alla utom `late` och `none`)."""
    days_late: int = 10
    """Dagar efter förfallodagen (`late`)."""
    share: Decimal = Decimal("0.5")
    """Andel av det öppna beloppet (`partial`)."""


#: Väntat utfall per beteende, så som facit beskriver det
EXPECTED = {
    "on_time": "allocated", "late": "allocated", "partial": "partial",
    "wrong_reference": "suspense:unknown_reference", "wrong_payer": "suspense:wrong_payer",
}


@dataclass
class _BankEvents:
    events: list[dict[str, Any]] = field(default_factory=list)
    facit: list[dict[str, Any]] = field(default_factory=list)
    pending: list[dict[str, Any]] = field(default_factory=list)


def bank_file(session, period: date, behaviours: Mapping[str, PaymentBehaviour], *, as_of: date, seed: int,
              file_reference: str | None = None) -> SimulatedFile:
    """Bankens fil med inbetalningar till och med `as_of` för arbetsgivarnas öppna debetfakturor.

    Arbetsgivaren betalar det som återstår av fakturan. En krediterad faktura betalas inte.
    Inbetalningar som enligt beteendet sker efter `as_of` kommer inte med; de står i facit som
    väntande. Händelse-ID:t är stabilt per seed, faktura och öppet belopp, så samma händelse i två
    filer känns igen, medan en senare betalning av en rest blir en ny händelse.
    """
    period = month_of(period)
    rng = random.Random(f"{seed}:bank:{period:%Y-%m}")
    out = _BankEvents()
    for org in sorted(behaviours):
        behaviour = behaviours[org]
        employer = _employer(session, org)
        for invoice, open_sek in _open_debit_invoices(session, employer, period):
            _pay(session, out, rng, invoice, open_sek, org, behaviour, as_of=as_of, seed=seed)
    out.events.sort(key=lambda e: (e["received_date"], e["event_id"]))
    reference = file_reference or f"SIM{VERSION}-BANK-{as_of:%Y%m%d}-S{seed}"
    checksum = bank_file_checksum(BANK_SOURCE, reference, out.events)
    payload = {"source_system": BANK_SOURCE, "file_reference": reference, "checksum": checksum,
               "events": out.events}
    total = sum((Decimal(e["amount_sek"]) for e in out.events), Decimal(0))
    facit = {"events": out.facit, "pending": out.pending, "total_sek": _money(total), "as_of": as_of.isoformat()}
    scenario = {org: {k: str(v) if isinstance(v, Decimal) else v for k, v in asdict(b).items()}
                for org, b in sorted(behaviours.items())}
    return SimulatedFile("bank_file", "import_bank_file", payload, _label(seed, scenario), facit)


def _open_debit_invoices(session, employer: Employer, period: date) -> list[tuple[Invoice, Decimal]]:
    """Debetfakturor med kvar att betala: totalen minus krediterade rader och det som redan betalats."""
    invoices = session.scalars(
        select(Invoice)
        .where(Invoice.employer_id == employer.id, Invoice.period_month == period, Invoice.invoice_type == "debit")
        .order_by(Invoice.invoice_number)
    ).all()
    result = []
    for invoice in invoices:
        lines = select(InvoiceLineRecord.id).where(InvoiceLineRecord.invoice_id == invoice.id)
        paid = session.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount_sek), 0))
            .where(PaymentAllocation.invoice_line_id.in_(lines), PaymentAllocation.kind == "invoice_line")
        )
        credited = session.scalar(  # kreditraderna är negativa
            select(func.coalesce(func.sum(InvoiceLineRecord.amount_sek), 0))
            .where(InvoiceLineRecord.credits_line_id.in_(lines))
        )
        open_sek = (invoice.total_sek + Decimal(credited) - Decimal(paid)).quantize(CENT)
        if open_sek > 0:
            result.append((invoice, open_sek))
    return result


def _pay(session, out: _BankEvents, rng, invoice: Invoice, open_sek: Decimal, org: str,
         behaviour: PaymentBehaviour, *, as_of: date, seed: int) -> None:
    kind = behaviour.kind
    if kind == "none":
        out.pending.append({"invoice": invoice.invoice_number, "open_sek": _money(open_sek), "why": "betalar inte"})
        return
    if kind == "late":
        day = next_bank_day(invoice.due_date + timedelta(days=behaviour.days_late))
    else:
        day = next_bank_day(min(invoice.invoice_date + timedelta(days=behaviour.days_after_invoice),
                                invoice.due_date))
    if day > as_of:
        out.pending.append({"invoice": invoice.invoice_number, "open_sek": _money(open_sek),
                            "why": f"betalar {day.isoformat()}, efter filens dag"})
        return

    amount = open_sek
    if kind == "partial":
        amount = max((open_sek * behaviour.share).quantize(CENT, ROUND_HALF_UP), CENT)
    reference = invoice.ocr_reference
    if kind == "wrong_reference":
        reference = reference[:-1] + str((int(reference[-1]) + 1) % 10)  # kontrollsiffran stämmer inte
    payer = _stranger(session, rng) if kind == "wrong_payer" else org
    payments = [(amount, EXPECTED.get(kind, "allocated"))]
    if kind == "twice":
        payments.append((amount, "suspense:overpayment"))
    for number, (sek, expected) in enumerate(payments, start=1):
        # Öppet belopp i ID:t: en senare betalning av resten blir en ny händelse, samma fil igen samma händelse
        event_id = f"SIM{VERSION}-S{seed}-{invoice.invoice_number}-{int(open_sek * 100)}-{number}"
        out.events.append({"event_id": event_id, "received_date": day.isoformat(), "amount_sek": _money(sek),
                           "payer_org_number": payer, "reference": reference})
        out.facit.append({"event_id": event_id, "invoice": invoice.invoice_number, "amount_sek": _money(sek),
                          "behaviour": kind, "expected": expected})


def _stranger(session, rng: random.Random) -> str:
    """Ett organisationsnummer som inte är anslutet."""
    while True:
        org = f"559{rng.randint(0, 9_999_999):07d}"
        if session.scalar(select(Employer.id).where(Employer.org_number == org)) is None:
            return org


# --- bankens kvittofil för utbetalningar (paket B steg 6) -----------------------------------------

PayoutOutcome = Literal["executed", "rejected", "returned", "unknown"]
#: Bankens orsakskod per utfall (ISO 20022-liknande): felaktigt konto och stängt konto
REASON_CODES = {"rejected": "AC01", "returned": "AC04"}


def payout_receipt_file(bank_file: Mapping[str, Any], outcomes: Mapping[str, PayoutOutcome] | None = None, *,
                        bank_date: date, seed: int, round_number: int = 1,
                        file_reference: str | None = None) -> SimulatedFile:
    """Bankens kvittofil för en godkänd bankfil (`approve_payout_order` → `bank_file`).

    Varje uppdrag får utfallet i `outcomes` (referens → utfall), annars utfört. Kvitto-id:t är stabilt per
    seed, uppdrag och omgång, så samma omgång igen ger samma kvitton (ingen ny effekt), medan en senare
    omgång – t.ex. retur efter utförande eller svar efter okänt – ger nya kvitton. Alla uppdrag i filen
    besvaras.
    """
    outcomes = dict(outcomes or {})
    unknown_refs = set(outcomes) - {o["reference"] for o in bank_file["orders"]}
    if unknown_refs:
        raise ValueError(f"Okända uppdrag i utfallen: {sorted(unknown_refs)}")
    receipts, facit = [], []
    for order in sorted(bank_file["orders"], key=lambda o: o["reference"]):
        outcome = outcomes.get(order["reference"], "executed")
        receipts.append({"receipt_id": f"SIM{VERSION}-PR-S{seed}-{order['reference']}-{round_number}",
                         "reference": order["reference"], "outcome": outcome, "bank_date": bank_date.isoformat(),
                         "reason_code": REASON_CODES.get(outcome)})
        facit.append({"reference": order["reference"], "outcome": outcome, "amount_sek": order["amount_sek"]})
    reference = file_reference or f"SIM{VERSION}-PAYRCPT-{bank_date:%Y%m%d}-S{seed}-R{round_number}"
    checksum = receipt_file_checksum(PAYOUT_BANK_SOURCE, reference, receipts)
    payload = {"source_system": PAYOUT_BANK_SOURCE, "file_reference": reference, "checksum": checksum,
               "receipts": receipts}
    executed = sum((Decimal(f["amount_sek"]) for f in facit if f["outcome"] == "executed"), Decimal(0))
    label = _label(seed, {"bank_file": bank_file["file_reference"], "round": round_number,
                          "outcomes": dict(sorted(outcomes.items()))})
    return SimulatedFile("payout_receipt_file", "import_payout_receipts", payload, label,
                         {"receipts": facit, "executed_net_sek": _money(executed),
                          "bank_file_checksum": bank_file["checksum"]})


# --- folkbokföringens avisering om dödsfall (paket B steg 7) --------------------------------------

#: Scenarierna per person (Y14): dödsfall i månaden, sent besked efter betalda månader (fall 31) och dödsfall
#: under paus eller på startdagen (fall 28)
DeathScenario = Literal["death_in_month", "late_notice", "paused_or_start_day"]


@dataclass(frozen=True)
class DeathCase:
    """Ett dödsfall i aviseringen: personen, dödsdagen och scenariot (bara i facit)."""

    personal_id_number: str
    death_date: date
    scenario: DeathScenario = "death_in_month"


def death_notice_file(deaths: list[DeathCase], *, notified_on: date, seed: int,
                      file_reference: str | None = None) -> SimulatedFile:
    """Folkbokföringens avisering: ett besked per dödsfall med stabilt besked-id per seed och person.

    Samma seed och dödsfall ger samma fil, så samma fil igen registrerar inget nytt (Y14). Scenariot står bara i
    facit, aldrig i filen till operationen (PA8).
    """
    if any(d.death_date > notified_on for d in deaths):
        raise ValueError("En dödsdag ligger efter aviseringsdagen")
    notices, facit = [], []
    for d in sorted(deaths, key=lambda d: (d.death_date, d.personal_id_number)):
        notice_id = f"SIM{VERSION}-DN-S{seed}-{d.personal_id_number[-4:]}{d.death_date:%Y%m%d}"
        notices.append({"notice_id": notice_id, "personal_id_number": d.personal_id_number,
                        "death_date": d.death_date.isoformat(), "notified_on": notified_on.isoformat()})
        facit.append({"notice_id": notice_id, "scenario": d.scenario, "death_date": d.death_date.isoformat()})
    reference = file_reference or f"SIM{VERSION}-DEATH-{notified_on:%Y%m%d}-S{seed}"
    payload = {"source_system": POPULATION_SOURCE, "file_reference": reference,
               "checksum": notice_file_checksum(POPULATION_SOURCE, reference, notices), "notices": notices}
    label = _label(seed, {"notified_on": notified_on.isoformat(), "deaths": len(deaths)})
    return SimulatedFile("death_notice_file", "import_death_notices", payload, label, {"notices": facit})
