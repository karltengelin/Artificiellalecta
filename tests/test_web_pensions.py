"""Handläggarsidan *Pensioner och utbetalningar* över HTTP (paket B steg 8, B-056, Karls val Z1–Z14).

Samma kedja som steg 6:s prov (`test_payout_orders.claimed`): B:s novemberrätt på 10 000 kr är bokad och
helt finansierad, i dag är 2026-12-04. Sidan körs med riktiga tjänsteoperationer mot kedjans SQLite-fil.

- Vyerna visas, och personnummer finns bara i pensionsaktens sidhuvud – aldrig i adresser, listor eller
  HX-Push-Url – och kontonummer bara maskerade (Z6).
- Registreringarna går med handläggaren som aktör och kanalen `manual`; kundportal och chattbot nekas (Z5).
- Bolagskapitalet, bankfilens godkännande och månadsstängningen kräver inloggad operatör (Z5).
- Ändrat underlag ger 409 "Underlaget har ändrats – granska igen" (Z8).
- Utan steg 4–7 (eller med bara några av dem) visar vyerna notis med tabeller och skript, och en postad
  ändring ger 409 utan att operationen anropas eller något loggas (Z9).
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from models import Case, OperationEventRecord, PayoutAccount, PayoutFile, PayoutPlan, TaxStatus
from models.death import ESTATE_DOCUMENTS, ESTATE_ROLES, REPORT_STATUSES, VERIFICATION_METHODS
from services import ProductRuleCatalog, ServiceLayer
from services import death_reports as dr
from services import payout_orders as po
from services import payout_plans as plans
from services import pension_claims as pc
from simulation.counterparties import payout_receipt_file
from tests import test_payout_orders as orders
from tests import test_premium_month_export as export_tests
from tests.test_pension_claims import POLICY
from tests.test_pension_claims import at_66 as at_66  # noqa: F401 (fixtur)
from tests.test_premium_month_export import PERSONS
from web import create_app, presenters
from web.config import WebConfigError, WebSettings
from web.operator_auth import OperatorAuth

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

chain = export_tests.chain
clock = export_tests.clock
claimed = orders.claimed

ORIGIN = {"Origin": "https://testserver"}
B = POLICY["B"]
AKT = f"/pensioner/forsakringar/{B}"
VIEWS = ("/pensioner", "/pensioner/manadsratter", "/pensioner/bankfiler", "/pensioner/dodsfall",
         "/pensioner/manadsstangning")
PNR = re.compile(r"(19|20)\d{6}-?\d{4}")


@pytest.fixture(scope="module")
def password():
    return PasswordHasher().hash("syntetisk-testlosenfras")


def _app(db, password, **settings):
    service = ServiceLayer(session_factory=db.factory, rules=ProductRuleCatalog(today=date(2026, 12, 4)))
    app = create_app(service=service, settings=WebSettings(allowed_hosts=("testserver",), **settings))
    app.state.operator_auth = OperatorAuth("karl", password)
    return app


def _login(client):
    page = client.get("/logga-in")
    assert client.post("/logga-in", data={"username": "karl", "password": "syntetisk-testlosenfras",
                                          "csrf_token": page.context["session_csrf"]},
                       headers=ORIGIN, follow_redirects=False).status_code == 303


@pytest.fixture
def desk(claimed, password):
    app = _app(claimed, password)
    with TestClient(app, base_url="https://testserver") as client:
        yield SimpleNamespace(client=client, app=app, db=claimed, csrf=app.state.csrf_token)


@pytest.fixture
def operator(desk):
    _login(desk.client)
    desk.op_csrf = lambda: desk.client.get("/pensioner/bankfiler").context["operator_csrf"]
    return desk


def post(desk, url, data=None, files=None, csrf=None):
    return desk.client.post(url, data={"csrf_token": csrf or desk.csrf, **(data or {})}, files=files, headers=ORIGIN)


def events(db) -> int:
    """Händelser för ändringar (läsningar loggas också, men räknas inte här)."""
    with db.factory() as s:
        return s.scalar(select(func.count()).select_from(OperationEventRecord)
                        .where(OperationEventRecord.kind.in_(("write", "external"))))


def alerts(text: str) -> list[str]:
    """Sidans rutor som text – för begripliga provfel."""
    return [re.sub(r"<[^>]+>|\s+", " ", a).strip() for a in re.findall(r'<div class="alert.*?</div>', text, re.S)]


def drop(db, *groups):
    with db.engine.begin() as conn:
        for tables in groups:
            for table in tables[::-1]:
                conn.exec_driver_sql(f"DROP TABLE {table}")


TAX = {"tax_year": "2026", "kind": "side_income", "rate": "0,30", "received_date": "2026-11-20",
       "reason": "Kundens blankett om sidoinkomst"}
ACCOUNT = {"clearing_number": "8327", "account_number": "12345678", "bank_name": "Provbanken", "verified": "on",
           "verification_method": "kontouppslag", "verification_ref": "VER-PROV-1", "received_date": "2026-11-20",
           "reason": "Kontouppgift verifierad med kontouppslag"}


# --- vyerna ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("url", VIEWS)
def test_vyerna_visas_utan_personnummer(desk, url):
    page = desk.client.get(url)
    assert page.status_code == 200, page.text[:2000]
    assert "Pensioner och utbetalningar" in page.text
    assert not PNR.search(page.text), PNR.search(page.text)


def test_oversikten_visar_lage_och_delar(desk):
    page = desk.client.get("/pensioner")
    assert "Senast stängda månad" in page.text and B in page.text and f'href="{AKT}"' in page.text
    assert "Utbetalning pågår" in page.text
    filtered = desk.client.get("/pensioner?lage=in_payout")
    assert B in filtered.text and POLICY["A"] not in filtered.text


def test_oversikten_soker_aldrig_pa_personnummer(desk):
    page = desk.client.get(f"/pensioner?sok={orders.B_PNR}")
    assert page.status_code == 200 and "Personnummer används aldrig" in page.text and B not in page.text


def test_pensionsakten_visar_personnumret_bara_i_huvudet(desk):
    page = desk.client.get(AKT)
    assert page.status_code == 200
    assert page.text.count("19601103-1234") == 1 and orders.B_PNR not in page.text
    assert "Planversioner" in page.text and "Månadsrätter och betalningar" in page.text


def test_menyn_har_pensioner(desk):
    assert 'href="/pensioner"' in desk.client.get("/premier").text


# --- registreringar (handläggaren) ----------------------------------------------------------------


def test_skattestatus_och_konto_registreras_manuellt_och_maskerat(desk):
    page = post(desk, f"{AKT}/skatt", TAX)
    assert page.status_code == 200 and "Skattestatus för 2026 är registrerad" in page.text
    assert page.headers["HX-Push-Url"] == AKT
    page = post(desk, f"{AKT}/konto", ACCOUNT)
    assert page.status_code == 200 and "****5678" in page.text and "12345678" not in page.text
    with desk.db.factory() as s:
        tax, account = s.scalar(select(TaxStatus)), s.scalar(select(PayoutAccount))
        assert (tax.channel, tax.created_by, str(tax.rate)) == ("manual", "karl", "0.3000")
        assert (account.channel, account.created_by) == ("manual", "karl")
    assert "12345678" not in desk.client.get(AKT).text


def test_kundportal_och_chattbot_nekas(desk):
    before = events(desk.db)
    for channel in ("customer_portal", "chatbot"):
        page = post(desk, f"{AKT}/skatt", {**TAX, "channel": channel})
        assert page.status_code == 422 and "Ingenting har ändrats" in page.text
    assert events(desk.db) == before
    with desk.db.factory() as s:
        assert s.scalar(select(func.count()).select_from(TaxStatus)) == 0


def test_motivering_och_token_kravs(desk):
    assert post(desk, f"{AKT}/skatt", {**TAX, "reason": ""}).status_code == 422
    assert post(desk, f"{AKT}/skatt", TAX, csrf="fel").status_code == 403


def test_fel_visar_formularet_igen_utan_kontonumret(desk):
    page = post(desk, f"{AKT}/konto", {**ACCOUNT, "clearing_number": "12"})
    assert page.status_code == 422 and "Ingenting har ändrats" in page.text and "12345678" not in page.text


def test_begaran_och_forhandsberakning(desk):
    page = post(desk, f"{AKT}/begaran", {"part_number": "1", "kind": "pause", "pause_first": "2027-03",
                                         "pause_resume": "2027-05", "received_date": "2026-12-04",
                                         "reason": "Kundens brev om paus"})
    assert page.status_code == 200 and "Begäran är registrerad" in page.text
    links = re.findall(rf'href="({AKT}/begaran/[0-9a-f-]{{36}})#forhand"', page.text)
    assert len(links) == 2  # kedjans startbegäran och den nya pausen
    old = desk.client.get(links[0])
    assert old.status_code == 422 and "Begäran kan inte förhandsberäknas" in old.text and "Uttagsdel 1" in old.text
    link = re.search(r"(.*)", links[1])
    preview = desk.client.get(link.group(1))
    assert preview.status_code == 200 and "Förhandsberäkning" in preview.text, alerts(preview.text)
    assert "Vägledande" in preview.text  # 2027-02 är inte stängd: ingen beslutsknapp hjälper
    checksum = re.search(r'name="reviewed_checksum" value="([0-9a-f]{64})"', preview.text).group(1)
    early = post(desk, link.group(1) + "/beslut", {"reviewed_checksum": checksum, "kind": "plan",
                                                   "reason": "Paus enligt kundens brev"})
    assert early.status_code == 422 and "Ingenting har ändrats" in early.text


@pytest.fixture
def before_november(at_66, password):
    """B fyller 66 i november; oktober är bokad och novembers stängning inte gjord."""
    app = _app(at_66, password)
    with TestClient(app, base_url="https://testserver") as client:
        yield SimpleNamespace(client=client, app=app, db=at_66, csrf=app.state.csrf_token)


def test_planbeslut_med_granskningssumma(before_november):
    desk = before_november
    page = post(desk, f"{AKT}/begaran", {"part_number": "1", "kind": "start", "first_right": "2026-11",
                                         "form": "lifelong", "received_date": "2026-10-20",
                                         "reason": "Kundens ansökan om start vid 66"})
    assert page.status_code == 200, alerts(page.text)
    link = re.search(rf'href="({AKT}/begaran/[0-9a-f-]{{36}})#forhand"', page.text).group(1)
    preview = desk.client.get(link)
    assert "Kan beslutas" in preview.text, alerts(preview.text)
    checksum = re.search(r'name="reviewed_checksum" value="([0-9a-f]{64})"', preview.text).group(1)
    wrong = post(desk, link + "/beslut", {"reviewed_checksum": "0" * 64, "kind": "plan", "reason": "Start vid 66"})
    assert wrong.status_code == 409 and "Underlaget har ändrats – granska igen" in wrong.text
    done = post(desk, link + "/beslut", {"reviewed_checksum": checksum, "kind": "plan", "reason": "Start vid 66"})
    assert done.status_code == 200 and "Planversion 1 är beslutad från 2026-11-01" in done.text, alerts(done.text)
    with desk.db.factory() as s:
        assert s.scalar(select(PayoutPlan.decided_by)) == "karl"


def test_ombud_kraver_verifierad_behorighet(desk):
    page = post(desk, f"{AKT}/begaran", {"part_number": "1", "kind": "pause", "pause_first": "2027-03",
                                         "pause_resume": "2027-05", "received_date": "2026-12-04",
                                         "requester": "representative", "reason": "Ombudets brev"})
    assert page.status_code == 422 and "behörighet" in page.text


# --- operatören -----------------------------------------------------------------------------------


def test_operatorsatgarder_kraver_inloggning(desk):
    before = events(desk.db)
    page = desk.client.get("/pensioner/manadsratter")
    assert "Kräver inloggad operatör" in page.text and 'action="/pensioner/manadsratter/bolagskonto"' not in page.text
    for url in ("/pensioner/manadsratter/bolagskonto", "/pensioner/bankfiler/godkann", "/pensioner/bankfiler/hamta",
                "/pensioner/manadsstangning/stang"):
        assert post(desk, url, {"reason": "prov"}).status_code == 401, url
    assert events(desk.db) == before


def test_bolagskapital_av_operatoren(operator):
    page = post(operator, "/pensioner/manadsratter/bolagskonto",
                {"amount_sek": "1000,00", "decided_on": "2026-12-04", "document_ref": "Ägarbeslut 2026-12-04",
                 "reason": "Påfyllnad enligt ägarbeslut"}, csrf=operator.op_csrf())
    assert page.status_code == 200 and "Insättningen är bokad" in page.text
    # processens handläggartoken räcker inte för operatörsåtgärder
    assert post(operator, "/pensioner/manadsratter/bolagskonto", {"amount_sek": "1", "decided_on": "2026-12-04",
                                                                 "document_ref": "x", "reason": "prov"}).status_code == 403


def test_bankfil_granskas_godkanns_hamtas_och_kvitteras(operator):
    post(operator, f"{AKT}/skatt", TAX)
    post(operator, f"{AKT}/konto", ACCOUNT)
    created = post(operator, "/pensioner/bankfiler/skapa", {"payment_day": "2026-12-01", "reason": "December"})
    assert created.status_code == 200 and "Jag har granskat filen" in created.text
    assert "12345678" not in created.text and "****5678" in created.text
    with operator.db.factory() as s:
        file = s.scalar(select(PayoutFile))
        file_id, checksum = str(file.id), file.checksum
    approve = {"file_id": file_id, "reviewed_checksum": checksum, "reason": "Bankfilen granskad"}
    assert post(operator, "/pensioner/bankfiler/godkann", approve, csrf=operator.op_csrf()).status_code == 422
    wrong = post(operator, "/pensioner/bankfiler/godkann", {**approve, "reviewed": "on", "reviewed_checksum": "0" * 64},
                 csrf=operator.op_csrf())
    assert wrong.status_code == 409 and "Underlaget har ändrats – granska igen" in wrong.text
    done = post(operator, "/pensioner/bankfiler/godkann", {**approve, "reviewed": "on"}, csrf=operator.op_csrf())
    assert done.status_code == 200 and "är godkänd och lämnad till banken" in done.text
    assert "12345678" not in done.text
    download = post(operator, "/pensioner/bankfiler/hamta", {"file_id": file_id, "reviewed_checksum": checksum},
                    csrf=operator.op_csrf())
    assert download.status_code == 200 and download.headers["content-type"].startswith("application/json")
    assert "attachment" in download.headers["content-disposition"]
    bank_file = download.json()
    assert "12345678" in download.text
    receipt = payout_receipt_file(bank_file, None, bank_date=date(2026, 12, 4), seed=7).payload
    upload = {"file": ("kvitton.json", io.BytesIO(json.dumps({"_label": "prov", **receipt}).encode()), "application/json")}
    first = post(operator, "/pensioner/bankfiler/kvitton", {"reason": "Bankens kvitton"}, files=upload)
    assert first.status_code == 200 and "1 nya" in first.text and "Utbetalningarna är bokade" in first.text,         alerts(first.text)
    upload["file"][1].seek(0)
    again = post(operator, "/pensioner/bankfiler/kvitton", {"reason": "Bankens kvitton igen"}, files=upload)
    assert again.status_code == 200 and "0 nya och 1 redan inlästa" in again.text
    assert "Betald" in operator.client.get(AKT).text


def test_trasig_kvittofil(desk):
    upload = {"file": ("x.json", io.BytesIO(b"inte json"), "application/json")}
    page = post(desk, "/pensioner/bankfiler/kvitton", {"reason": "Prov"}, files=upload)
    assert page.status_code == 422 and "inte giltig JSON" in page.text


def test_stangningen_granskas_och_bokas_av_operatoren(operator, clock):
    clock.today = date(2027, 1, 4)
    orders.months_ahead(operator.db, clock, date(2026, 12, 1))
    page = operator.client.get("/pensioner/manadsstangning?manad=2026-12")
    assert page.status_code == 200 and "Granskning av 2026-12" in page.text
    checksum = re.search(r'name="reviewed_checksum" value="([0-9a-f]{64})"', page.text)
    assert checksum, page.text[:3000]
    done = post(operator, "/pensioner/manadsstangning/stang", {"month": "2026-12", "reviewed_checksum": checksum.group(1),
                                                              "reason": "Kontrollerna granskade"}, csrf=operator.op_csrf())
    assert done.status_code == 200 and "Månaden 2026-12 är stängd" in done.text
    assert "Versionskedjan för 2026-12" in done.text


def test_lakebase_bokar_inte_stangningen_fran_sidan(claimed, password, clock):
    clock.today = date(2027, 1, 4)
    orders.months_ahead(claimed, clock, date(2026, 12, 1))
    app = _app(claimed, password)
    app.state.settings = replace(app.state.settings, database="lakebase")
    with TestClient(app, base_url="https://testserver") as client:
        _login(client)
        page = client.get("/pensioner/manadsstangning?manad=2026-12")
        assert "körskriptet enligt B-050 S6" in page.text, alerts(page.text)
        assert "/pensioner/manadsstangning/stang" not in page.text
        before = events(claimed)
        refused = client.post("/pensioner/manadsstangning/stang", headers=ORIGIN, data={
            "csrf_token": page.context["operator_csrf"], "month": "2026-12", "reviewed_checksum": "0" * 64,
            "reason": "prov"})
        assert refused.status_code == 409 and "Ingenting har ändrats" in refused.text
        assert events(claimed) == before


# --- steg som saknas (Z9) -------------------------------------------------------------------------


def test_utan_steg_4_till_7_visas_notis_och_inget_postas(operator):
    drop(operator.db, plans.PLAN_TABLES, pc.CLAIM_TABLES, po.ORDER_TABLES, dr.DEATH_TABLES)
    for url in (*VIEWS[1:4], AKT):
        page = operator.client.get(url)
        assert page.status_code == 200, url
        assert "är inte infört" in page.text or "inte är införda" in page.text, (url, alerts(page.text))
    akt = operator.client.get(AKT).text
    assert "migrate_payout_plans.py" in akt and 'action="' + AKT + '/skatt"' not in akt
    before = events(operator.db)
    for url, data, csrf in ((f"{AKT}/skatt", TAX, None), (f"{AKT}/begaran", {"reason": "prov"}, None),
                            ("/pensioner/bankfiler/skapa", {"reason": "prov"}, None),
                            ("/pensioner/dodsfall/avisering", {"reason": "prov"}, None),
                            ("/pensioner/manadsratter/bolagskonto", {"reason": "prov"}, operator.op_csrf())):
        page = post(operator, url, data, csrf=csrf)
        assert page.status_code == 409 and "Ingenting har ändrats" in page.text, url
        assert page.headers["HX-Push-Url"] == "/pensioner"
    assert events(operator.db) == before
    assert operator.client.get("/pensioner").status_code == 200


def test_bara_steg_4_infort(desk):
    drop(desk.db, pc.CLAIM_TABLES, po.ORDER_TABLES, dr.DEATH_TABLES)
    akt = desk.client.get(AKT).text
    assert "Planversioner" in akt and "migrate_pension_claims.py" in akt
    assert "Registrera begäran om uttag" in akt
    assert "migrate_pension_claims.py" in desk.client.get("/pensioner/bankfiler").text


def test_bara_steg_4_och_5_inforda(desk):
    drop(desk.db, po.ORDER_TABLES, dr.DEATH_TABLES)
    assert "Bolagskontot" in desk.client.get("/pensioner/manadsratter").text
    page = desk.client.get(AKT).text
    assert "migrate_payout_orders.py" in page and "Månadsrätter och betalningar" in page


def test_bara_steg_4_till_6_inforda(desk):
    drop(desk.db, dr.DEATH_TABLES)
    assert desk.client.get("/pensioner/bankfiler").status_code == 200
    assert "migrate_death_reports.py" in desk.client.get("/pensioner/dodsfall").text
    assert post(desk, "/pensioner/dodsfall/avisering", {"reason": "prov"}).status_code == 409


def test_delvis_infort_steg_varnas(desk):
    drop(desk.db, dr.DEATH_TABLES[-1:])
    page = desk.client.get("/pensioner/dodsfall")
    assert "delvis infört" in page.text


# --- dödsfall -------------------------------------------------------------------------------------


def test_dodsfallsbesked_registreras_och_syns_i_listan(desk):
    page = post(desk, f"{AKT}/dodsfall", {"status": "suspected", "reported_on": "2026-12-04",
                                          "received_date": "2026-12-04", "source": "relative",
                                          "source_ref": "Samtal 2026-12-04", "reason": "Anhörig har ringt"})
    assert page.status_code == 200 and "Dödsfallsbeskedet är registrerat" in page.text
    deaths = desk.client.get("/pensioner/dodsfall").text
    assert B in deaths and not PNR.search(deaths)
    with desk.db.factory() as s:
        assert s.scalar(select(Case.case_type).where(Case.case_type == "death_report")) == "death_report"


# --- affärsdag och inställningar ------------------------------------------------------------------


def test_simulerad_affarsdag_bara_i_demo():
    with pytest.raises(WebConfigError):
        WebSettings(database="svc_test", business_day=date(2026, 12, 15))
    with pytest.raises(WebConfigError):
        WebSettings(database="lakebase", keep_schema=True)
    assert WebSettings(business_day=date(2026, 12, 15)).business_day == date(2026, 12, 15)


def test_affarsdagen_galler_varje_forfragan(claimed, password, monkeypatch):
    from services.operations import common
    monkeypatch.undo()  # kedjans klocka bort: sidan ska få dagen från middleware
    app = _app(claimed, password, business_day=date(2027, 1, 4))
    with TestClient(app, base_url="https://testserver") as client:
        page = client.get("/pensioner")
        assert "Simulerad affärsdag 2027-01-04" in page.text and "dag 2027-01-04" in page.text
    assert common.today() == date.today()


def test_etiketterna_tacker_modellernas_varden():
    assert set(presenters.DEATH_REPORT_STATUS) == set(REPORT_STATUSES)
    assert set(presenters.DEATH_VERIFICATION) == set(VERIFICATION_METHODS)
    assert set(presenters.ESTATE_ROLES) == set(ESTATE_ROLES)
    assert set(presenters.ESTATE_DOCUMENTS) == set(ESTATE_DOCUMENTS)
    from models.case import CASE_TYPES
    assert set(CASE_TYPES) <= set(presenters.CASE_TYPES)


def test_inga_personnummer_i_testbestandets_lista(desk):
    text = desk.client.get("/pensioner").text
    assert not any(pnr in text for pnr in PERSONS.values())


# --- ärendesidan (Z11) ----------------------------------------------------------------------------


def test_arendet_leder_till_pensionsakten_och_agenten_startas_inte(desk):
    post(desk, f"{AKT}/konto", ACCOUNT)
    post(desk, "/pensioner/bankfiler/skapa", {"payment_day": "2026-12-01", "reason": "December"})  # utan skatt
    with desk.db.factory() as s:
        number = s.scalar(select(Case.case_number).where(Case.case_type == "tax_status"))
    page = desk.client.get(f"/arenden/{number}")
    assert f'href="/pensioner/arenden/{number}"' in page.text and "Starta agent" not in page.text
    link = desk.client.get(f"/pensioner/arenden/{number}", follow_redirects=False)
    assert link.status_code == 303 and link.headers["location"] == AKT
    before = events(desk.db)
    refused = post(desk, f"/arenden/{number}/agent")
    assert refused.status_code == 409 and "Ingen agent i pensionsärenden" in refused.text
    assert events(desk.db) == before


def test_arenden_utan_person_leder_till_sina_floden(desk):
    with desk.db.factory() as s:
        numbers = dict(s.execute(select(Case.case_type, Case.case_number)
                                 .where(Case.case_type.in_(("company_capital", "inheritance_pool")))).all())
    for case_type, number in numbers.items():
        target = desk.client.get(f"/pensioner/arenden/{number}", follow_redirects=False).headers["location"]
        assert target.startswith("/pensioner/manadsratter" if case_type == "company_capital" else "/pensioner/dodsfall")
