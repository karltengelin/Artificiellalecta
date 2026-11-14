"""Överlämning till månadsjournalen (paket A steg 6, B-046, P1-PREMIE-001 §4.7 och §7 fall 20).

Kedjan går genom tjänstelagret: löneunderlag → faktura → rättelser → bankfiler → export →
`open_premium_month` → `receive_premium_payment`. Arbetsgivaren 5560000001 har fyra
premiebetalande försäkrade med mottagen historik, så att de ingår i IB per 2026-10-31.

| Händelse | Mottagen | Utfall i paket A |
|---|---|---|
| INV-000001: A 2 025,00, B 4 708,13, C 2 025,00, D 2 025,00 | 11-07 | ordinarie faktura |
| C rättas 45 000 → 50 000 före betalning | 11-07 | kredit INV-000002, ny debet INV-000003 2 250,00 |
| E1 4 000,00 på INV-000001 | 11-10 | delbetalning på A, B och D |
| E2 4 758,13 på INV-000001 | 11-16 | restbetalning; A, B och D betalda |
| D rättas 45 000 → 50 000 efter betalning | 11-16 | tillägg INV-000004 225,00 |
| E3 2 000,00 på INV-000003 | 11-20 | delbetalning av den nya debeten |
| E4 300,00 på INV-000004 | 11-20 | 225,00 på tillägget, 75,00 till avstämningskontot |
| E5 100,00 med okänd OCR | 11-20 | hela beloppet till avstämningskontot |
| E6 250,00 på INV-000003 | 12-02 | efter journalmånaden |
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, inspect, select

from models import (
    BankEvent,
    Base,
    BaseAmount,
    Employer,
    InsuredPerson,
    Invoice,
    InvoiceLineRecord,
    PaymentAllocation,
    Policy,
    PolicyState,
    PremiumReceipt,
    PremiumTransaction,
)
from services import (
    Actor,
    AgentAccess,
    BlockedError,
    OperationContext,
    ProductRuleCatalog,
    ServiceLayer,
    parameters,
)
from services import valuation_bases as vb
from services.db import session_factory_for
from services.errors import AccessDeniedError
from services.operations import common
from services.operations.payments import bank_file_checksum
from services.operations.salary_files import file_checksum
from services.premium_month_export import (
    ExportError,
    _trial_population,
    verify_journal_allocation,
)
from services.premium_month_inputs import InvoiceInput, MonthInputs, receipt_key
from services.premium_month_preparation import bound_source
from services.valuation_extract import build_extract
from tests.conftest import add_retirement_benefit

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

START = date(2026, 11, 7)
EMPLOYER = "5560000001"
OCTOBER = date(2026, 10, 1)
PERSONS = {"A": "198505151234", "B": "197803031234", "C": "198201011234", "D": "199002021234"}
SALARY = {"A": "45000", "B": "60000", "C": "45000", "D": "45000"}
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Överlämning av oktoberpremierna till månadsjournalen")
SCENARIO = "paket-a-2026-10-v1"


@pytest.fixture
def clock(monkeypatch):
    state = SimpleNamespace(today=START)
    monkeypatch.setattr(common, "today", lambda: state.today)
    return state


def _person(s, employer, pnr, number):
    person = InsuredPerson(
        personal_id_number=pnr, first_name="Test", last_name=pnr[-4:], employer_id=employer.id,
        employment_start_date=date(2020, 1, 1), monthly_salary_sek=Decimal(45000), employment_rate=Decimal(100),
        itp1_start_date=date(2020, 1, 1), status="active")
    s.add(person)
    s.flush()
    policy = Policy(policy_number=f"AL-0001{number:02d}", insured_person_id=person.id,
                    signed_date=date(2020, 1, 1), start_date=date(2020, 1, 1))
    s.add(policy)
    s.flush()
    benefit = add_retirement_benefit(s, policy.id, date(2020, 1, 1))
    s.add(PolicyState(policy_id=policy.id, state="premium_paying", valid_from=date(2020, 1, 1)))
    s.flush()
    # Mottagen historik gör att försäkringen ingår i IB-populationen per 2026-10-31
    s.add(PremiumTransaction(benefit_id=benefit.id, period_month=date(2023, 1, 1), transaction_type="premium",
                             amount_sek=Decimal("10000.00"), status="paid", paid_date=date(2023, 1, 15)))


def service(db, today=START):
    return ServiceLayer(session_factory=db.factory, rules=ProductRuleCatalog(today=today))


def run(db, name, data=None, ctx=HUMAN):
    return service(db).execute(name, ctx, data or {}).output


def salary_file(db, rows, ref):
    received = date(2026, 11, 5)
    view = run(db, "import_salary_file", {
        "employer_org_number": EMPLOYER, "period_month": OCTOBER.isoformat(), "file_reference": ref,
        "received_date": received.isoformat(), "rows": rows,
        "checksum": file_checksum(EMPLOYER, OCTOBER, ref, received, rows)})
    run(db, "approve_salary_file", {"employer_org_number": EMPLOYER, "file_reference": ref,
                                    "expected_digest": view.review_digest})


def row(key, amount=None, kind="new", corrects=None):
    return {"personal_id_number": PERSONS[key], "period_month": OCTOBER.isoformat(),
            "pensionable_salary_sek": amount or SALARY[key], "kind": kind, "corrects_version": corrects}


def invoice(db):
    return run(db, "create_invoice", {"employer_org_number": EMPLOYER, "period_month": OCTOBER.isoformat()}).invoices


def bank(db, clock, ref, events):
    clock.today = max(date.fromisoformat(e["received_date"]) for e in events)
    return run(db, "import_bank_file", {"source_system": "bank-sim", "file_reference": ref, "events": events,
                                        "checksum": bank_file_checksum("bank-sim", ref, events)})


def event(event_id, amount, reference, received):
    return {"event_id": event_id, "received_date": received, "amount_sek": amount,
            "payer_org_number": EMPLOYER, "reference": reference}


@pytest.fixture
def chain(tmp_path, clock):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = session_factory_for(engine)
    with factory() as s:
        parameters.add_missing_defaults(s)
        vb.add_missing_defaults(s)
        s.add_all([BaseAmount(year=2023, income_base_amount_sek=Decimal(74300)),
                   BaseAmount(year=2026, income_base_amount_sek=Decimal(83400))])
        employer = Employer(org_number=EMPLOYER, name="Testbolaget AB", affiliation_date=date(2010, 1, 1))
        s.add(employer)
        s.flush()
        for number, pnr in enumerate(PERSONS.values(), start=1):
            _person(s, employer, pnr, number)
        s.commit()
    db = SimpleNamespace(engine=engine, factory=factory)

    salary_file(db, [row(key) for key in PERSONS], "LON-2026-10")
    [first] = invoice(db)
    assert first.total_sek == Decimal("10783.13")
    salary_file(db, [row("C", "50000", "correction", 1)], "LON-2026-10-R1")
    credit, rebill = invoice(db)
    assert (credit.total_sek, rebill.total_sek) == (Decimal("-2025.00"), Decimal("2250.00"))
    bank(db, clock, "BANK-11-10", [event("E1", "4000.00", first.ocr_reference, "2026-11-10")])
    bank(db, clock, "BANK-11-16", [event("E2", "4758.13", first.ocr_reference, "2026-11-16")])
    salary_file(db, [row("D", "50000", "correction", 1)], "LON-2026-10-R2")
    [additional] = invoice(db)
    assert [line.line_type for line in additional.lines] == ["additional"]
    bank(db, clock, "BANK-11-20", [event("E3", "2000.00", rebill.ocr_reference, "2026-11-20"),
                                   event("E4", "300.00", additional.ocr_reference, "2026-11-20"),
                                   event("E5", "100.00", "9999999999", "2026-11-20")])
    bank(db, clock, "BANK-12-02", [event("E6", "250.00", rebill.ocr_reference, "2026-12-02")])
    with factory() as s:
        db.opening_checksum = build_extract(s, date(2026, 10, 31)).checksum
    db.invoices = SimpleNamespace(first=first, credit=credit, rebill=rebill, additional=additional)
    yield db
    engine.dispose()


def export(db, scenario=SCENARIO, period="2026-10-01"):
    return run(db, "export_premium_month", {"period_month": period, "scenario_id": scenario,
                                            "expected_opening_checksum": db.opening_checksum}).payload


def open_and_receive(db, payload):
    package = MonthInputs.model_validate_json(payload["inputs_json"])
    opened = run(db, "open_premium_month", {"inputs_json": payload["inputs_json"],
                                            "reviewed_checksum": payload["checksum"]}).payload
    results = []
    for r in sorted(package.receipts, key=lambda r: (r.received_date, receipt_key(package.scenario_id, r))):
        results.append(run(db, "receive_premium_payment",
                           {"journal_id": package.scenario_id, "receipt": r.model_dump(mode="json")}).payload)
    return package, opened, results


def package_a_allocations(db, until=date(2026, 11, 30)) -> dict[tuple[str, str, str], Decimal]:
    """Paket A:s radallokeringar per (bankhändelse, faktura, rad) för mottagningar i journalmånaden."""
    out: dict[tuple[str, str, str], Decimal] = {}
    with db.factory() as s:
        rows = s.execute(select(PaymentAllocation.amount_sek, BankEvent.event_id, Invoice.invoice_number,
                                InvoiceLineRecord.line_number)
                         .join(BankEvent, BankEvent.id == PaymentAllocation.bank_event_id)
                         .join(Invoice, Invoice.id == PaymentAllocation.invoice_id)
                         .join(InvoiceLineRecord, InvoiceLineRecord.id == PaymentAllocation.invoice_line_id)
                         .where(PaymentAllocation.kind == "invoice_line", BankEvent.received_date <= until)).all()
        for amount, event_id, number, line_number in rows:
            key = (event_id, number, f"line-{line_number:04d}")
            out[key] = out.get(key, Decimal(0)) + amount
    return out


def journal_allocations(db, package) -> dict[tuple[str, str, str], Decimal]:
    """Journalens kvitton per (bankhändelse, faktura, rad), med bankens händelse-ID ur källreferensen."""
    out: dict[tuple[str, str, str], Decimal] = {}
    with db.factory() as s:
        for receipt in s.scalars(select(PremiumReceipt).where(PremiumReceipt.journal_id == package.scenario_id)):
            r = receipt.content["receipt"]
            bank_event = r["source"]["reference"].split(":", 1)[1]
            assert Decimal(receipt.content["unallocated_sek"]) == 0
            for a in receipt.content["allocations"]:
                key = (bank_event, r["invoice_id"], a["line_id"])
                out[key] = out.get(key, Decimal(0)) + Decimal(a["net_sek"])
    return out


class TestFall20:
    def test_open_premium_month_godtar_paketet_och_kvittona_motsvarar_allokeringarna(self, chain):
        payload = export(chain)
        package, opened, results = open_and_receive(chain, payload)
        assert opened["state"] == "open" and opened["expected_receipts"] == 4
        assert {r["reused"] for r in results} == {False}
        expected = package_a_allocations(chain)
        assert journal_allocations(chain, package) == expected
        assert sum(expected.values()) == Decimal("10983.13") == Decimal(payload["summary"]["received_sek"])
        summary = run(chain, "get_premium_month", {"journal_id": SCENARIO}).payload
        assert (summary["receipts"], summary["state"]) == (4, "open")

    def test_garantidelen_skapas_av_journalen_pa_mottagningsmanaden(self, chain):
        open_and_receive(chain, export(chain))
        with chain.factory() as s:
            parts = [a for r in s.scalars(select(PremiumReceipt)) for a in r.content["allocations"]]
        assert all(Decimal(a["guarantee_sek_per_month"]) > 0 for a in parts)
        assert {a["value_date"] for a in parts} == {"2026-11-30"}
        assert {a["period_month"] for a in parts} == {"2026-10-01"}


class TestBetalningsfall:
    def test_delbetalning_och_restbetalning(self, chain):
        package, _, _ = open_and_receive(chain, export(chain))
        first = chain.invoices.first.invoice_number
        journal = journal_allocations(chain, package)
        e1 = {line: v for (ev, inv, line), v in journal.items() if ev == "E1" and inv == first}
        e2 = {line: v for (ev, inv, line), v in journal.items() if ev == "E2" and inv == first}
        assert sum(e1.values()) == Decimal("4000.00") and sum(e2.values()) == Decimal("4758.13")
        invoice_input = next(i for i in package.invoices if i.id == first)
        # Delbetalning plus rest ger exakt varje rads belopp: inget mer, inget mindre
        assert {line.id: line.due_sek for line in invoice_input.lines} == {
            line: e1[line] + e2[line] for line in e1}

    def test_kredit_och_ny_debet(self, chain):
        package = MonthInputs.model_validate_json(export(chain)["inputs_json"])
        invoices = {i.id: i for i in package.invoices}
        first, rebill = chain.invoices.first, chain.invoices.rebill
        assert chain.invoices.credit.invoice_number not in invoices
        # Den krediterade raden är ingen fordran och följer inte med; den nya debeten gör det
        assert len(invoices[first.invoice_number].lines) == 3
        assert sum(line.due_sek for line in invoices[first.invoice_number].lines) == Decimal("8758.13")
        [line] = invoices[rebill.invoice_number].lines
        assert (line.due_sek, line.calculation_basis["invoice_line_type"]) == (Decimal("2250.00"), "rebill")
        assert len(line.calculation_basis["covers"]) == 1

    def test_tillagg(self, chain):
        package, _, _ = open_and_receive(chain, export(chain))
        additional = chain.invoices.additional.invoice_number
        [line] = next(i for i in package.invoices if i.id == additional).lines
        assert (line.due_sek, line.calculation_basis["invoice_line_type"]) == (Decimal("225.00"), "additional")
        ordinary = [x for i in package.invoices for x in i.lines
                    if x.benefit_id == line.benefit_id and x.calculation_basis["invoice_line_type"] == "ordinary"]
        assert len(ordinary) == 1, "tillägget och originalet avser samma förmån och period"
        journal = journal_allocations(chain, package)
        assert journal[("E4", additional, line.id)] == Decimal("225.00")

    def test_avstamningskontot_och_senare_mottagningar_foljer_inte_med(self, chain):
        payload = export(chain)
        summary = payload["summary"]
        package = MonthInputs.model_validate_json(payload["inputs_json"])
        references = {r.source.reference for r in package.receipts}
        assert references == {"bank-sim:E1", "bank-sim:E2", "bank-sim:E3", "bank-sim:E4"}
        e4 = next(r for r in package.receipts if r.source.reference == "bank-sim:E4")
        assert (e4.gross_sek, e4.net_sek) == (Decimal("225.00"), Decimal("225.00"))
        assert (summary["suspense_on_period_invoices_sek"], summary["suspense_without_invoice_sek"]) == (
            "75.00", "100.00")
        assert summary["after_month_end"] == {"bank_events": 1, "allocated_sek": "250.00"}
        assert (summary["invoices"], summary["invoice_lines"], summary["credited_lines_left_out"]) == (3, 5, 1)
        assert {r.value_date for r in package.receipts} == {date(2026, 11, 30)}


class TestIdempotens:
    def test_samma_export_tva_ganger_ger_ingen_dubbel_effekt(self, chain):
        first = export(chain)
        package, _, _ = open_and_receive(chain, first)
        second = export(chain)
        assert (second["checksum"], second["inputs_json"]) == (first["checksum"], first["inputs_json"])
        with chain.factory() as s:
            before = s.scalar(select(func.count()).select_from(PremiumReceipt))
        _, opened, results = open_and_receive(chain, second)
        assert opened["receipts"] == 4 and {r["reused"] for r in results} == {True}
        with chain.factory() as s:
            assert s.scalar(select(func.count()).select_from(PremiumReceipt)) == before == 4
        assert journal_allocations(chain, package) == package_a_allocations(chain)

    def test_exporten_skriver_ingenting(self, chain):
        def counts():
            with chain.factory() as s:
                names = [n for n in inspect(s.connection()).get_table_names() if n != "operation_events"]
                return {n: s.connection().exec_driver_sql(f'SELECT count(*) FROM "{n}"').scalar_one() for n in names}

        before = counts()
        export(chain)
        assert counts() == before

    def test_nytt_scenario_id_ger_eget_paket(self, chain):
        assert export(chain, "paket-a-2026-10-v2")["checksum"] != export(chain)["checksum"]


class TestStopp:
    def test_agent_far_inte_exportera(self, chain):
        assert service(chain).decision("export_premium_month").effective == AgentAccess.HUMAN_ONLY
        agent = OperationContext(actor=Actor.agent("handlaggare"), reason="prov")
        with pytest.raises(AccessDeniedError):
            run(chain, "export_premium_month", {"period_month": "2026-10-01", "scenario_id": SCENARIO,
                                                "expected_opening_checksum": chain.opening_checksum}, ctx=agent)

    def test_annan_period_stoppas(self, chain):
        with pytest.raises(BlockedError, match="2026-10"):
            export(chain, period="2026-11-01")

    def test_fel_ib_summa_stoppas(self, chain):
        chain.opening_checksum = "0" * 64
        with pytest.raises(BlockedError, match="IB"):
            export(chain)

    def test_mottagning_fore_journalmanaden_stoppas(self, chain):
        with chain.factory() as s:
            s.scalar(select(BankEvent).where(BankEvent.event_id == "E1")).received_date = date(2026, 10, 30)
            s.commit()
        with pytest.raises(BlockedError, match="före 2026-11"):
            export(chain)

    def test_annan_fordelning_an_paket_a_stoppas(self, chain):
        package = MonthInputs.model_validate_json(export(chain)["inputs_json"])
        expected = {}
        for r in package.receipts:
            invoice_input = next(i for i in package.invoices if i.id == r.invoice_id)
            expected[r.event_id] = {line.id: Decimal(0) for line in invoice_input.lines}
        with pytest.raises(ExportError, match="annorlunda än paket A"):
            verify_journal_allocation(package, expected)

    def test_population_utanfor_forsoket_stoppas(self):
        plan = SimpleNamespace(start=date(2027, 1, 1))
        policy = SimpleNamespace(policy_id="p1", plan=plan)
        line = {"policy_id": "p2"}
        cases = [
            (SimpleNamespace(not_calculated=["x"], policies=[policy]), "inte beräknas"),
            (SimpleNamespace(not_calculated=[], policies=[SimpleNamespace(policy_id="p1",
                                                                          plan=SimpleNamespace(start=date(2026, 11, 1)))]),
             "referensplan"),
            (SimpleNamespace(not_calculated=[], policies=[policy]), "saknas i IB-populationen"),
        ]
        for extract, message in cases:
            with pytest.raises(ExportError, match=message):
                _trial_population(SimpleNamespace(extract=extract), [{"lines": [line]}])


def test_tillagg_ar_egen_premiepost_men_ordinarie_premie_bara_en_gang():
    from services.premium_month_inputs import obligation

    def invoice_input(ident, kind):
        body = {"id": ident, "payer_id": EMPLOYER, "lines": [
            {"id": "line-0001", "benefit_id": "b", "policy_id": "p", "period_month": "2026-10-01",
             "due_sek": "100.00", "calculation_basis": {"invoice_line_type": kind}}]}
        return InvoiceInput.model_validate({**body, "source": bound_source("employer", ident, body)})

    ordinary, again, extra = invoice_input("INV-1", "ordinary"), invoice_input("INV-2", "rebill"), \
        invoice_input("INV-3", "additional")
    assert obligation(ordinary, ordinary.lines[0]) == obligation(again, again.lines[0])
    assert obligation(extra, extra.lines[0]) != obligation(ordinary, ordinary.lines[0])
