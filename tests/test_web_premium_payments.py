"""Handläggar-UI:t, paket A steg 7: sidan Premier och betalningar (B-046, P1-PREMIE-001 §8).

Mot demobeståndet i minnet. Motpartssimulatorn skapar arbetsgivarnas löneunderlagsfiler och
bankens fil, som handläggaren lämnar in genom sidans formulär. Operationernas dag sätts till
kedjans affärsdatum: filen tas emot 2026-11-05, faktureras 2026-11-07 och betalas 2026-11-15.
"""

from __future__ import annotations

import json
import re
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text

from models import BankEvent, Case, Invoice, OperationEventRecord, SalaryFile, SalaryReport
from services import AgentAccess
from services.operations import common
from simulation.counterparties import PaymentBehaviour, SalaryScenario, bank_file, salary_file
from web.presenters import sek

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

DEMOBOLAGET, EXEMPELVERKEN = "5560000001", "5560000002"
OCTOBER = date(2026, 10, 1)


@pytest.fixture
def clock(web, monkeypatch):
    state = SimpleNamespace(today=date(2026, 11, 7))
    monkeypatch.setattr(common, "today", lambda: state.today)
    return state


def post(web, url, data, files=None):
    return web.client.post(url, data={**data, "csrf_token": web.csrf}, files=files)


def upload(simulated) -> dict:
    body = json.dumps({**simulated.payload, "_label": simulated.label}, default=str).encode()
    return {"file": (f"{simulated.reference}.json", body, "application/json")}


def employer_file(web, org, scenario=None, seed=1):
    with web.session_factory() as s:
        return salary_file(s, org, OCTOBER, received_date=date(2026, 11, 5), seed=seed, scenario=scenario)


def receive(web, simulated):
    return post(web, "/premier/filer", {"reason": "Arbetsgivarens lönefil för oktober"}, upload(simulated))


def digest(page) -> str:
    return re.search(r'name="expected_digest" value="([a-f0-9]{64})"', page.text).group(1)


def approve(web, org, reference, expected):
    return post(web, "/premier/fil/godkann", {
        "employer_org_number": org, "file_reference": reference, "expected_digest": expected,
        "reason": "Granskad mot följebrevet",
    })


def approved_file(web, org, scenario=None):
    simulated = employer_file(web, org, scenario)
    page = receive(web, simulated)
    assert page.status_code == 200, page.text
    assert approve(web, org, simulated.reference, digest(page)).status_code == 200
    return simulated


def invoice(web, org):
    return post(web, "/premier/fakturera", {"employer_org_number": org, "period_month": "2026-10",
                                            "reason": "Godkänt löneunderlag för oktober"})


def count(web, model, *where):
    with web.session_factory() as s:
        return s.scalar(select(func.count()).select_from(model).where(*where))


def message(page) -> str:
    return " ".join(re.findall(r'class="alert__message">([^<]*)<', page.text))


class TestSidan:
    def test_tom_sida_med_menyval_och_avstamning(self, web, clock):
        page = web.client.get("/premier")
        assert page.status_code == 200
        html = page.text
        assert 'href="/premier" aria-current="page"' in html
        for text_ in ("Premier och betalningar", "Löneunderlagsfiler", "Fakturor", "Inbetalningar", "Avstämningskonto",
                      "Går ihop", "Inga löneunderlagsfiler", "Avstämningskontot är tomt", "import_salary_file",
                      "create_invoice", "import_bank_file", "allocate_unmatched_payment"):
            assert text_ in html, text_

    def test_hela_kedjan_genom_sidan(self, web, clock):
        """Fil → granskning → godkännande → faktura → bankfil → avstämningskonto → manuell fördelning."""
        simulated = employer_file(web, DEMOBOLAGET, SalaryScenario(missing=1, zero=1, unknown_person=True))
        page = receive(web, simulated)
        assert page.status_code == 200
        assert f"Filen {simulated.reference} är mottagen och validerad" in message(page)
        assert "Väntar på granskning" in page.text and "Okänd person" in page.text and "Saknade rader" in page.text
        assert count(web, SalaryReport, SalaryReport.period_month == OCTOBER) == 0  # intaget registrerar inget

        page = approve(web, DEMOBOLAGET, simulated.reference, digest(page))
        assert page.status_code == 200
        assert "premierader registrerade; 2 ärenden" in message(page)
        assert "Ärenden från filen" in page.text and "Avvikelse i lönefil" in page.text and "Saknad rad" in page.text
        assert count(web, Case, Case.case_type == "salary_file_deviation") == 2

        page = invoice(web, DEMOBOLAGET)
        assert page.status_code == 200
        assert "INV-000001" in message(page) and "Faktureringen" in page.text
        with web.session_factory() as s:
            debit = s.scalar(select(Invoice).where(Invoice.invoice_number == "INV-000001"))
            total = debit.total_sek

        clock.today = date(2026, 11, 15)
        with web.session_factory() as s:
            bank = bank_file(s, OCTOBER, {DEMOBOLAGET: PaymentBehaviour("wrong_reference")}, as_of=clock.today, seed=1)
        page = post(web, "/premier/bankfil", {"reason": "Bankfil från den simulerade banken"}, upload(bank))
        assert page.status_code == 200
        assert "Bankfilen" in page.text and "Okänd referens" in page.text
        suspense = page.text.split('id="avstamningskonto"')[1]
        assert "Fördela" in suspense and "1 post med saldo" in suspense
        assert '<option value="INV-000001" selected>' in suspense  # betalarens egen öppna faktura är förvald
        [case_number] = re.findall(r'href="/arenden/(CASE-\d+)"', suspense)

        key = re.search(r'name="request_key" value="([a-f0-9]+)"', suspense).group(1)
        allocation = {
            "source_system": "bank-sim", "event_id": bank.payload["events"][0]["event_id"],
            "invoice_number": "INV-000001", "amount_sek": "", "payer_verification": "Bekräftat med arbetsgivaren",
            "request_key": key, "reason": "Betalaren verifierad per telefon",
        }
        page = post(web, "/premier/fordela", allocation)
        assert page.status_code == 200
        assert f"fördelat från avstämningskontot till INV-000001; {sek(0)} kvar" in message(page)
        assert "Avstämningskontot är tomt" in page.text and "Går ihop" in page.text
        assert "Betald" in page.text.split('id="fakturor"')[1]
        # Samma formulär igen (samma nyckel) ger samma kvitto; en ny nyckel stoppas eftersom saldot är noll
        again = post(web, "/premier/fordela", allocation)
        assert again.status_code == 200 and "redan gjord med samma idempotensnyckel" in message(again)
        fresh = post(web, "/premier/fordela", {**allocation, "request_key": "ny-nyckel"})
        assert fresh.status_code == 422 and "inget oallokerat belopp" in fresh.text and "Ingenting har ändrats" in fresh.text

        detail = web.client.get("/premier/fakturor/INV-000001")
        assert detail.status_code == 200
        assert "Betald" in detail.text and "Ordinarie" in detail.text and debit.ocr_reference in detail.text
        assert str(total).replace(".", ",") in detail.text.replace("\xa0", "").replace(" ", "")
        assert case_number.startswith("CASE-")

    def test_ingen_personnummer_utanfor_filens_rader(self, web, clock):
        simulated = approved_file(web, DEMOBOLAGET)
        invoice(web, DEMOBOLAGET)
        overview = web.client.get("/premier").text
        invoice_page = web.client.get("/premier/fakturor/INV-000001").text
        with web.session_factory() as s:
            reported = s.scalars(select(SalaryFile.content)).one()["rows"]
        for row in reported:
            assert row["personal_id_number"] not in overview
            assert row["personal_id_number"] not in invoice_page
        file_page = web.client.get("/premier/fil", params={"arbetsgivare": DEMOBOLAGET, "referens": simulated.reference})
        assert reported[0]["personal_id_number"] in file_page.text
        with web.session_factory() as s:
            reads = s.scalars(select(OperationEventRecord.operation).where(OperationEventRecord.kind == "read")).all()
        assert "get_salary_file" in reads  # läsningen av individrader loggas
        assert "list_salary_files" not in reads and "list_bank_events" not in reads  # inga personuppgifter

    def test_urval_pa_arbetsgivare_och_period(self, web, clock):
        approved_file(web, DEMOBOLAGET)
        approved_file(web, EXEMPELVERKEN)
        page = web.client.get("/premier", params={"arbetsgivare": EXEMPELVERKEN, "period": "2026-10"})
        files = page.text.split('id="filer"')[1].split('id="fakturor"')[0]
        assert f"SIM1-{EXEMPELVERKEN}-202610" in files and f"SIM1-{DEMOBOLAGET}-202610" not in files
        assert "Rensa" in page.text
        assert "Inga löneunderlagsfiler i urvalet" in web.client.get("/premier", params={"period": "2026-11"}).text


class TestFil:
    def test_samma_fil_igen_ger_samma_kvitto(self, web, clock):
        simulated = employer_file(web, EXEMPELVERKEN)
        receive(web, simulated)
        page = receive(web, simulated)
        assert page.status_code == 200 and "redan mottagen med samma innehåll" in message(page)
        assert count(web, SalaryFile) == 1

    def test_avslag_registrerar_ingenting(self, web, clock):
        simulated = employer_file(web, EXEMPELVERKEN)
        receive(web, simulated)
        page = post(web, "/premier/fil/avsla", {
            "employer_org_number": EXEMPELVERKEN, "file_reference": simulated.reference,
            "decision_note": "Fel period enligt arbetsgivaren", "reason": "Arbetsgivaren återkallade filen",
        })
        assert page.status_code == 200
        assert "Avslagen" in page.text and "Fel period enligt arbetsgivaren" in page.text and "Avslagen fil" in page.text
        assert count(web, SalaryReport, SalaryReport.period_month == OCTOBER) == 0
        assert "Godkänn filen" not in page.text

    def test_andrat_underlag_stoppar_godkannandet(self, web, clock):
        simulated = employer_file(web, EXEMPELVERKEN)
        receive(web, simulated)
        page = approve(web, EXEMPELVERKEN, simulated.reference, "0" * 64)
        assert page.status_code == 409
        assert "granska filen igen" in page.text and "Ingenting har ändrats" in page.text
        assert "Godkänn filen" in page.text  # filen kan granskas och godkännas igen
        assert count(web, SalaryReport, SalaryReport.period_month == OCTOBER) == 0

    def test_fel_kontrollsumma_och_ogiltig_json(self, web, clock):
        simulated = employer_file(web, EXEMPELVERKEN)
        broken = {**simulated.payload, "checksum": "f" * 64}
        files = {"file": ("lon.json", json.dumps(broken, default=str).encode(), "application/json")}
        page = post(web, "/premier/filer", {"reason": "Lönefil"}, files)
        assert page.status_code == 422 and "kontrollsumma" in page.text and "Ingenting har ändrats" in page.text

        page = post(web, "/premier/filer", {"reason": "Lönefil"}, {"file": ("lon.json", b"{inte json", "application/json")})
        assert page.status_code == 422 and "Filen kunde inte läsas" in page.text and "inte giltig JSON" in page.text
        assert count(web, SalaryFile) == 0

    def test_motivering_kravs(self, web, clock):
        page = post(web, "/premier/filer", {"reason": ""}, upload(employer_file(web, EXEMPELVERKEN)))
        assert page.status_code == 422 and "Motivering saknas" in page.text
        assert count(web, SalaryFile) == 0


class TestFakturaOchBevakning:
    def test_startluckan_faktureras_inte(self, web, clock):
        page = post(web, "/premier/fakturera", {"employer_org_number": DEMOBOLAGET, "period_month": "2026-09",
                                                "reason": "Försök"})
        assert page.status_code == 422 and "startlucka" in page.text.lower()
        assert count(web, Invoice) == 0

    def test_bevakningen_skapar_arende_efter_forfallodagen(self, web, clock):
        approved_file(web, EXEMPELVERKEN)
        invoice(web, EXEMPELVERKEN)
        with web.session_factory() as s:
            due = s.scalar(select(Invoice.due_date))
        clock.today = date.fromordinal(due.toordinal() + 1)
        page = post(web, "/premier/bevakning", {"reason": "Daglig bevakning"})
        assert page.status_code == 200
        assert "Förfallobevakningen" in page.text and "ärende skapat" in page.text
        assert count(web, Case, Case.case_type == "payment_overdue") == 1


class TestBank:
    def test_dubbelbetalning_hamnar_pa_avstamningskontot(self, web, clock):
        approved_file(web, EXEMPELVERKEN)
        invoice(web, EXEMPELVERKEN)
        clock.today = date(2026, 11, 15)
        with web.session_factory() as s:
            bank = bank_file(s, OCTOBER, {EXEMPELVERKEN: PaymentBehaviour("twice")}, as_of=clock.today, seed=1)
        page = post(web, "/premier/bankfil", {"reason": "Bankfil"}, upload(bank))
        assert page.status_code == 200
        assert "Överskott" in page.text and "Går ihop" in page.text
        again = post(web, "/premier/bankfil", {"reason": "Samma bankfil igen"}, upload(bank))
        assert again.status_code == 200 and "Redan inläst" in again.text
        assert count(web, BankEvent) == len(bank.payload["events"])


class TestUtanTabeller:
    """Lakebase före steg 8: tabellerna saknas och sidan ger ett besked i stället för ett fel."""

    @pytest.fixture
    def without_tables(self, web):
        with web.engine.begin() as connection:
            for table in reversed(common.PREMIUM_FLOW_TABLES):
                connection.execute(text(f"DROP TABLE {table}"))
        return web

    def test_sidan_visar_besked(self, without_tables, clock):
        page = without_tables.client.get("/premier")
        assert page.status_code == 200
        assert "Premieflödet är inte infört" in page.text and "<code>salary_files</code>" in page.text
        assert "Ta emot och validera" not in page.text and "Ingenting har ändrats" not in page.text
        for url in ("/premier/fakturor/INV-000001", f"/premier/fil?arbetsgivare={DEMOBOLAGET}&referens=X"):
            detail = without_tables.client.get(url)
            assert detail.status_code == 200 and "Premieflödet är inte infört" in detail.text

    def test_andringar_utfors_inte(self, without_tables, clock):
        page = post(without_tables, "/premier/filer", {"reason": "Lönefil"}, upload(employer_file(without_tables, DEMOBOLAGET)))
        assert page.status_code == 409
        assert "Premieflödet är inte infört" in page.text and "Ingenting har ändrats" in page.text
        page = post(without_tables, "/premier/fakturera", {"employer_org_number": DEMOBOLAGET, "period_month": "2026-10",
                                                           "reason": "Försök"})
        assert page.status_code == 409
        assert count(without_tables, OperationEventRecord, OperationEventRecord.operation.in_(("import_salary_file", "create_invoice"))) == 0


def test_formularen_kraver_token(web, clock):
    simulated = employer_file(web, EXEMPELVERKEN)
    assert web.client.post("/premier/filer", data={"reason": "x"}, files=upload(simulated)).status_code == 403
    for url in ("/premier/fil/godkann", "/premier/fil/avsla", "/premier/fakturera", "/premier/bevakning",
                "/premier/bankfil", "/premier/fordela"):
        assert web.client.post(url, data={"reason": "x"}).status_code == 403, url
    assert count(web, SalaryFile) == 0


def test_lasningarna_ar_bara_for_handlaggare(web):
    for name in ("list_salary_files", "list_bank_events"):
        assert web.service.decision(name).effective == AgentAccess.HUMAN_ONLY
