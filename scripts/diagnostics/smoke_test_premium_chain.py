"""Röktest av premiekedjan med simulerade motparter (paket A steg 5–6, B-046, P1-PREMIE-001 §9 och §12).

Motpartssimulatorn skapar arbetsgivarnas löneunderlagsfiler och bankens filer ur beståndet.
Skriptet agerar handläggare, märkt `rooktest`, och lämnar filerna till samma operationer som
riktiga filer: intag och godkännande, fakturering, bankfil och matchning, förfallobevakning och
avstämning. Kedjan slutar i månadsjournalen: periodens mottagna premier exporteras med
`export_premium_month` och tas emot av `open_premium_month` och `receive_premium_payment`
(steg 6, fall 20). Inga modellanrop görs.

| `--db`     | Databas                                                                        |
|------------|--------------------------------------------------------------------------------|
| `demo`     | Demobeståndet i en SQLite-databas i minnet                                     |
| `svc_test` | Demobeståndet i ett eget schema i SERVICES_TEST_POSTGRES_URL, tas bort efteråt |

Lakebase ingår inte; där krävs de nya tabellerna först (steg 8).

**Bestånd.** Demobeståndet byggs utan personer födda före 1961 (`born_from=1961`): David Dahl
med pågående utbetalning och kohortens födda 1959–1960, vars referensplan startar 2026-11.
Månadsjournalens första försök (P6-MANAD-001) tar bara emot ett IB där alla försäkringar
beräknas och ingen plan startar under journalmånaden. Valet gäller bara detta röktest.

**Affärsdatum.** Kedjan löper över drygt två månader: filen tas emot, fakturan förfaller,
bevakningen påminner och eskalerar, och resten betalas sent. Röktestet sätter därför
operationernas dagsfunktion till kedjans affärsdatum steg för steg. Det gäller bara inom
röktestet; en gemensam simuleringsklocka (S-01) finns inte.

Scenariot för premieperioden (standard 2026-10):

| Arbetsgivare      | Löneunderlag                               | Betalning                                              |
|-------------------|--------------------------------------------|--------------------------------------------------------|
| Demobolaget AB    | en saknad rad, en nolla, en okänd person   | delbetalar hälften, får påminnelse och eskalering, betalar resten sent |
| Exempelverken AB  | utan avvikelser                            | betalar i tid men två gånger; det andra beloppet går till avstämningskontot |

Månadsjournalen för november 2026 får båda arbetsgivarnas novemberbetalningar. Demobolagets
sena restbetalning (januari) och Exempelverkens dubbelbetalning på avstämningskontot följer inte med.

Kontrollerna skiljer **verksamhetskontroller** (kedjan ska stämma av för alla filer: ingen
dubbel effekt, avstämningen går ihop, bara kedjans tabeller ändras) från **facit för
scenariot** (det simulatorn förutsade för just dessa filer).

Användning (från repo-roten, i .venv):
    python scripts/diagnostics/smoke_test_premium_chain.py                    # demo
    python scripts/diagnostics/smoke_test_premium_chain.py --db svc_test
    python scripts/diagnostics/smoke_test_premium_chain.py --seed 7 --utdata logs/simulation
"""

from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from smoke_test_flow import Report, demo_database, svc_test_database

OPERATOR_ID = "rooktest"
DEMOBOLAGET, EXEMPELVERKEN = "5560000001", "5560000002"
#: Tabeller som kedjan får ändra; alla andra ska ha samma radantal efteråt
CHANGING = {"salary_files", "salary_reports", "premium_transactions", "invoices", "invoice_lines", "bank_events",
            "payment_allocations", "cases", "operation_events",
            # Månadsjournalen (steg 6): journal, kvitton och IB-värderingen som scenarioutkast
            "premium_month_journals", "premium_receipts", "valuation_runs", "valuation_results",
            "valuation_extracts"}
#: Månadsjournalens första försök tar bara emot ett IB utan påbörjade planer (P6-MANAD-001)
BORN_FROM = 1961
SCENARIO = "rooktest-paket-a-2026-10"


@contextmanager
def business_day(state: dict):
    """Operationernas dagsfunktion följer kedjans affärsdatum – bara inom röktestet."""
    from services.operations import common

    original = common.today
    common.today = lambda: state["today"]
    try:
        yield
    finally:
        common.today = original


def row_counts(factory) -> dict[str, int]:
    from sqlalchemy import inspect

    with factory() as session:
        names = sorted(inspect(session.connection()).get_table_names())
        return {name: session.connection().exec_driver_sql(f'SELECT count(*) FROM "{name}"').scalar_one()
                for name in names}


def bank_outcomes(result) -> dict[str, str]:
    """Matchningens utfall i facits språk; en delbetalning syns som fördelad utan rest."""
    mapped = {}
    for o in result.outcomes:
        if o.reason is not None and o.allocated_sek == 0:
            mapped[o.event_id] = f"suspense:{o.reason}"
        elif o.unallocated_sek == 0 and o.allocated_sek == o.amount_sek:
            mapped[o.event_id] = "allocated"
        else:
            mapped[o.event_id] = f"delvis till avstämningskontot ({o.reason})"
    return mapped


def facit_outcomes(sim) -> dict[str, str]:
    return {e["event_id"]: "allocated" if e["expected"] == "partial" else e["expected"] for e in sim.facit["events"]}


def run_chain(db, period: date, seed: int, utdata: Path | None, report: Report) -> None:
    from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer
    from simulation.counterparties import (
        PaymentBehaviour,
        SalaryScenario,
        bank_file,
        salary_file,
    )
    from utils.bank_calendar import next_bank_day

    state = {"today": next_bank_day(date(period.year + period.month // 12, period.month % 12 + 1, 5))}
    ctx = OperationContext(actor=Actor.human(OPERATOR_ID), reason="Röktest av premiekedjan (paket A steg 5)")

    def call(operation: str, data: dict):
        service = ServiceLayer(session_factory=db.factory, rules=ProductRuleCatalog(today=state["today"]))
        return service.execute(operation, ctx, data).output

    def simulate(make, *args, **kwargs):
        with db.factory() as session:
            sim = make(session, *args, **kwargs)
        if utdata is not None:
            sim.write(utdata)
        return sim

    before = row_counts(db.factory)
    with business_day(state):
        # 1. Löneunderlag: intag, granskning och godkännande
        print(f"\n{state['today']}: löneunderlagsfiler för {period:%Y-%m}")
        scenarios = {DEMOBOLAGET: SalaryScenario(missing=1, zero=1, unknown_person=True),
                     EXEMPELVERKEN: SalaryScenario()}
        for org, scenario in scenarios.items():
            sim = simulate(salary_file, org, period, received_date=state["today"], seed=seed, scenario=scenario)
            view = call("import_salary_file", sim.payload)
            summary = view.summary
            report.check("facit", f"{org}: intagets utfall som simulatorn förutsade",
                         (summary.valid, summary.deviations, summary.missing) == tuple(sim.facit["expected"].values()),
                         f"{summary.valid} giltiga, {summary.deviations} avvikande, {summary.missing} saknade")
            again = call("import_salary_file", sim.payload)
            report.check("verksamhet", f"{org}: samma fil igen ger samma intag (fall 6)", again.file_id == view.file_id)
            decision = call("approve_salary_file", {"employer_org_number": org, "file_reference": sim.reference,
                                                    "expected_digest": view.review_digest})
            report.check("verksamhet", f"{org}: avvikande och saknade rader blir ärenden",
                         len(decision.cases) == summary.deviations + summary.missing, f"{len(decision.cases)} ärenden")

        # 2. Faktura per arbetsgivare
        invoices = {}
        for org in scenarios:
            run = call("create_invoice", {"employer_org_number": org, "period_month": period.isoformat()})
            [invoices[org]] = run.invoices
            print(f"  {org}: {invoices[org].invoice_number} {invoices[org].total_sek} kr, förfaller "
                  f"{invoices[org].due_date}, OCR {invoices[org].ocr_reference}")
        demo_inv, exempel_inv = invoices[DEMOBOLAGET], invoices[EXEMPELVERKEN]
        again = call("create_invoice", {"employer_org_number": DEMOBOLAGET, "period_month": period.isoformat()})
        report.check("verksamhet", "fakturering igen ger ingen ny faktura", not again.invoices)

        # 3. Första bankfilen: delbetalning och dubbelbetalning
        state["today"] = state["today"] + timedelta(days=10)
        print(f"\n{state['today']}: bankfil 1")
        behaviours = {DEMOBOLAGET: PaymentBehaviour("partial", share=Decimal("0.5")),
                      EXEMPELVERKEN: PaymentBehaviour("twice")}
        first = simulate(bank_file, period, behaviours, as_of=state["today"], seed=seed)
        result = call("import_bank_file", first.payload)
        report.check("facit", "matchningens utfall som simulatorn förutsade",
                     bank_outcomes(result) == facit_outcomes(first), str(bank_outcomes(result)))
        again = call("import_bank_file", first.payload)
        report.check("verksamhet", "samma bankfil igen ger inga nya allokeringar (fall 15)",
                     {o.status for o in again.outcomes} == {"already_received"} and again.allocated_sek == 0)
        receivables = call("get_receivables", {})
        half = (demo_inv.total_sek * Decimal("0.5")).quantize(Decimal("0.01"))
        report.check("facit", "Demobolagets resterande fordran efter delbetalningen",
                     receivables.receivables_sek == demo_inv.total_sek - half, f"{receivables.receivables_sek} kr")
        report.check("facit", "Exempelverkens andra betalning på avstämningskontot",
                     receivables.suspense_sek == exempel_inv.total_sek, f"{receivables.suspense_sek} kr")
        report.check("verksamhet", "inbetalt = fördelat + avstämningskonto; fakturerat - fördelat = fordringar",
                     receivables.balanced)

        # 4. Förfallobevakning: påminnelse dagen efter förfallodagen, eskalering efter 30 dagar
        for days, action in ((1, "created"), (31, "escalated")):
            state["today"] = demo_inv.due_date + timedelta(days=days)
            overdue = call("check_overdue_invoices", {})
            print(f"\n{state['today']}: förfallobevakning – {overdue.note}")
            report.check("facit", f"{days} dagar efter förfallodagen: {action} för Demobolagets faktura",
                         [(a.invoice_number, a.action) for a in overdue.actions] == [(demo_inv.invoice_number, action)])

        # 5. Andra bankfilen: Demobolaget betalar resten sent
        behaviours = {DEMOBOLAGET: PaymentBehaviour("late", days_late=35)}
        state["today"] = demo_inv.due_date + timedelta(days=40)
        print(f"\n{state['today']}: bankfil 2")
        second = simulate(bank_file, period, behaviours, as_of=state["today"], seed=seed)
        result = call("import_bank_file", second.payload)
        report.check("facit", "restbetalningen fördelas fullt", bank_outcomes(result) == facit_outcomes(second),
                     str(bank_outcomes(result)))
        report.check("verksamhet", "fakturans premierader blir betalda", result.paid_premium_rows > 0,
                     f"{result.paid_premium_rows} rader")
        receivables = call("get_receivables", {})
        report.check("facit", "inga öppna fordringar kvar", receivables.receivables_sek == 0)
        report.check("verksamhet", "avstämningen går ihop efter hela kedjan", receivables.balanced,
                     f"inbetalt {receivables.bank_total_sek}, fördelat {receivables.allocated_sek}, "
                     f"avstämningskonto {receivables.suspense_sek}")

    # 6. Överlämning till månadsjournalen (steg 6, fall 20)
    hand_over(db, call, invoices, report)

    after = row_counts(db.factory)
    changed = {name for name in after if after[name] != before.get(name)}
    report.check("verksamhet", "bara kedjans tabeller har ändrats", changed <= CHANGING,
                 ", ".join(sorted(changed - CHANGING)) or ", ".join(f"{n} +{after[n] - before.get(n, 0)}"
                                                                     for n in sorted(changed)))


def package_a_allocations(factory, until: date) -> dict[tuple[str, str, str], Decimal]:
    """Paket A:s radallokeringar per (bankhändelse, faktura, rad) för mottagningar till och med `until`."""
    from sqlalchemy import select

    from models import BankEvent, Invoice, InvoiceLineRecord, PaymentAllocation

    out: dict[tuple[str, str, str], Decimal] = {}
    with factory() as session:
        rows = session.execute(
            select(PaymentAllocation.amount_sek, BankEvent.event_id, Invoice.invoice_number,
                   InvoiceLineRecord.line_number)
            .join(BankEvent, BankEvent.id == PaymentAllocation.bank_event_id)
            .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
            .join(InvoiceLineRecord, InvoiceLineRecord.id == PaymentAllocation.invoice_line_id)
            .where(PaymentAllocation.kind == "invoice_line", BankEvent.received_date <= until)).all()
    for amount, event_id, number, line_number in rows:
        key = (event_id, number, f"line-{line_number:04d}")
        out[key] = out.get(key, Decimal(0)) + amount
    return out


def journal_allocations(factory, journal_id: str) -> tuple[dict[tuple[str, str, str], Decimal], Decimal]:
    """Journalens kvitton per (bankhändelse, faktura, rad) och journalens oallokerade belopp."""
    from sqlalchemy import select

    from models import PremiumReceipt

    out: dict[tuple[str, str, str], Decimal] = {}
    unallocated = Decimal(0)
    with factory() as session:
        for row in session.scalars(select(PremiumReceipt).where(PremiumReceipt.journal_id == journal_id)):
            receipt = row.content["receipt"]
            event_id = receipt["source"]["reference"].split(":", 1)[1]
            unallocated += Decimal(row.content["unallocated_sek"])
            for allocation in row.content["allocations"]:
                key = (event_id, receipt["invoice_id"], allocation["line_id"])
                out[key] = out.get(key, Decimal(0)) + Decimal(allocation["net_sek"])
    return out, unallocated


def hand_over(db, call, invoices: dict, report: Report) -> None:
    """Steg 6: periodens mottagna premier till månadsjournalen, två gånger utan dubbel effekt."""
    from services.premium_month_inputs import MonthInputs, receipt_key
    from services.premium_month_preparation import OPENING_DATE, PERIOD_END
    from services.valuation_extract import build_extract

    print(f"\nÖverlämning till månadsjournalen för {PERIOD_END:%Y-%m}")
    with db.factory() as session:
        # Röktestet granskar IB själv; i drift anger handläggaren den granskade kontrollsumman
        opening_checksum = build_extract(session, OPENING_DATE).checksum
    request = {"period_month": "2026-10-01", "scenario_id": SCENARIO, "expected_opening_checksum": opening_checksum}

    def receive(payload):
        package = MonthInputs.model_validate_json(payload["inputs_json"])
        opened = call("open_premium_month", {"inputs_json": payload["inputs_json"],
                                             "reviewed_checksum": payload["checksum"]}).payload
        ordered = sorted(package.receipts, key=lambda r: (r.received_date, receipt_key(SCENARIO, r)))
        results = [call("receive_premium_payment", {"journal_id": SCENARIO, "receipt": r.model_dump(mode="json")})
                   .payload for r in ordered]
        return package, opened, results

    first = call("export_premium_month", request).payload
    summary = first["summary"]
    print(f"  källpaket {first['checksum'][:12]}…: {summary['invoices']} fakturor, {summary['receipts']} kvitton, "
          f"{summary['received_sek']} kr; utanför: avstämningskonto {summary['suspense_on_period_invoices_sek']} kr, "
          f"efter månadsslutet {summary['after_month_end']['allocated_sek']} kr")
    demo_inv, exempel_inv = invoices[DEMOBOLAGET], invoices[EXEMPELVERKEN]
    half = (demo_inv.total_sek * Decimal("0.5")).quantize(Decimal("0.01"))
    report.check("facit", "paketet har novemberbetalningarna men inte avstämningskontot eller januaribetalningen",
                 (summary["receipts"], Decimal(summary["received_sek"]),
                  Decimal(summary["suspense_on_period_invoices_sek"]),
                  Decimal(summary["after_month_end"]["allocated_sek"]))
                 == (2, half + exempel_inv.total_sek, exempel_inv.total_sek, demo_inv.total_sek - half),
                 f"{summary['receipts']} kvitton, {summary['received_sek']} kr")

    package, opened, results = receive(first)
    report.check("verksamhet", "open_premium_month godtar källpaketet (fall 20)",
                 opened["state"] == "open" and opened["expected_receipts"] == len(package.receipts),
                 f"journal {SCENARIO}, {opened['expected_receipts']} väntade kvitton")
    journal, unallocated = journal_allocations(db.factory, SCENARIO)
    expected = package_a_allocations(db.factory, PERIOD_END)
    report.check("verksamhet", "journalens kvitton motsvarar allokeringarna exakt i ören (fall 20)",
                 journal == expected and unallocated == 0 and {r["reused"] for r in results} == {False},
                 f"{len(journal)} radallokeringar, {sum(journal.values(), Decimal(0))} kr")

    again = call("export_premium_month", request).payload
    _, reopened, repeated = receive(again)
    journal_again, _ = journal_allocations(db.factory, SCENARIO)
    report.check("verksamhet", "samma export igen ger samma paket och ingen ny effekt i journalen",
                 again["checksum"] == first["checksum"] and reopened["receipts"] == len(package.receipts)
                 and {r["reused"] for r in repeated} == {True} and journal_again == journal)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", choices=("demo", "svc_test"), default="demo")
    parser.add_argument("--period", type=date.fromisoformat, default=date(2026, 10, 1),
                        help="Premieperiod, ÅÅÅÅ-MM-01 (standard 2026-10, första operativa)")
    parser.add_argument("--seed", type=int, default=2026, help="Simulatorns seed")
    parser.add_argument("--utdata", type=Path, help="Skriv de simulerade filerna och facit hit")
    args = parser.parse_args()

    databases = {"demo": lambda: demo_database(born_from=BORN_FROM),
                 "svc_test": lambda: svc_test_database((), born_from=BORN_FROM)}
    report = Report()
    with databases[args.db]() as db:
        print(f"Databas: {db.label}; period {args.period:%Y-%m}, seed {args.seed}")
        run_chain(db, args.period.replace(day=1), args.seed, args.utdata, report)
    passed = sum(1 for *_, ok, _ in report.checks if ok)
    print(f"\n{passed} av {len(report.checks)} kontroller godkända.")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
