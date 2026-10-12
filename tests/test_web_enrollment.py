"""Handläggar-UI:t, S5: anslutning, aktuell lön, kontaktuppgifter och arbetsgivare.

Avslutas med hela handläggarflödet: anslut en ny försäkrad, ändra aktuell lön,
registrera löneunderlag, sätt fribrev – och se ändringarna i tabellerna och
händelseloggen.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models import Employer, InsuredPerson, OperationEventRecord, Policy, PolicyState, SalaryReport

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

ANNA = "198505151236"
CECILIA = "199001017897"
NORA = "199204171236"


def post(web, url: str, data: dict, *, csrf: bool = True, **kwargs):
    return web.client.post(url, data={**data, **({"csrf_token": web.csrf} if csrf else {})}, **kwargs)


def enroll_form(**overrides) -> dict:
    data = {
        "personal_id_number": "19920417-1236", "first_name": "Nora", "last_name": "Nyström",
        "employer_org_number": "5560000001", "employment_category": "ordinary",
        "employment_start_date": "2026-09-01", "itp1_start_date": "2026-09-01",
        "affiliation_reference": "ANM-2026-09-17", "monthly_salary_sek": "41 000", "employment_rate": "100",
        "email": "nora@example.se", "phone": "", "reason": "Anmälan om nyanställd från Demobolaget AB",
    }
    return {**data, **overrides}


def table_counts(web) -> tuple:
    with web.session_factory() as s:
        return tuple(s.scalar(select(func.count()).select_from(m)) for m in (InsuredPerson, Policy, Employer))


def get_person(web, pnr: str) -> InsuredPerson:
    with web.session_factory() as s:
        return s.scalars(select(InsuredPerson).where(InsuredPerson.personal_id_number == pnr)).one()


# --- anslutning ---------------------------------------------------------------------------------


def test_anslutningsformularet_visar_arbetsgivare_och_regler(web):
    response = web.client.get("/forsakrade/ny", params={"arbetsgivare": "5560000002"})
    assert response.status_code == 200
    assert '<option value="5560000002" selected>Exempelverken AB (5560000002)</option>' in response.text
    assert "<code>PR-ITP1-012</code> anslutning, produkt och avtalsparter" in response.text
    assert "Anslut ny försäkrad" in web.client.get("/").text


def test_ny_forsakrad_ansluts_och_visas(web):
    response = post(web, "/forsakrade/ny", enroll_form())
    assert response.status_code == 200, response.text
    assert "Ansluten: Nora Nyström" in response.text
    assert "AL-000005" in response.text  # demobeståndet har AL-000001–000004
    assert "Inte skickat" in response.text  # försäkringsbeskedet
    assert response.headers["HX-Push-Url"] == f"/forsakrade/{NORA}"
    nora = get_person(web, NORA)
    assert (nora.first_name, nora.status, nora.email, nora.phone) == ("Nora", "active", "nora@example.se", None)
    overview = web.client.get(f"/forsakrade/{NORA}").text
    assert "Premiebetalande" in overview and "nora@example.se" in overview


@pytest.mark.parametrize(
    ("overrides", "status", "texts"),
    [
        ({"employment_category": "owner"}, 422, ["företagare eller delägare", "<code>PR-ITP1-012</code>"]),
        ({"personal_id_number": "199204171234"}, 422, ["Personnummer:", "kontrollsiffra"]),
        ({"personal_id_number": ANNA}, 409, ["finns redan som aktiv"]),
        ({"itp1_start_date": "2026-08-01"}, 422, ["Uppgifterna:", "före anställningen"]),
        ({"reason": ""}, 422, ["Motivering saknas"]),
    ],
)
def test_anslutning_som_stoppas_visar_skal_och_behaller_vardena(web, overrides, status, texts):
    before = table_counts(web)
    response = post(web, "/forsakrade/ny", enroll_form(**overrides))
    assert response.status_code == status
    for text in texts:
        assert text in response.text
    assert "Ingenting har ändrats" in response.text
    assert 'value="ANM-2026-09-17"' in response.text
    assert table_counts(web) == before


# --- arbetsgivare -------------------------------------------------------------------------------


def test_arbetsgivarlistan_visar_aktiva_forsakrade(web):
    text = web.client.get("/arbetsgivare").text
    rows = text.split("<tbody>")[1]
    assert "Demobolaget AB" in rows and "Exempelverken AB" in rows
    assert '<td class="num">2</td>' in rows and '<td class="num">0</td>' in rows
    assert "Kontaktpersoner visas inte" in text


def test_ny_arbetsgivare_registreras(web):
    response = post(web, "/arbetsgivare/ny", {
        "org_number": "556677-8899", "name": "Nyföretaget AB", "affiliation_date": "2026-01-01",
        "address_postal_code": "411 05", "contact_email": "lon@nyforetaget.se", "reason": "Tecknat ITP-avtal",
    })
    assert response.status_code == 200, response.text
    assert "Nyföretaget AB (5566778899) är registrerad" in response.text
    assert response.headers["HX-Push-Url"] == "/arbetsgivare"
    assert "Nyföretaget AB" in web.client.get("/forsakrade/ny").text


@pytest.mark.parametrize(
    ("org", "status", "text"),
    [("5560000001", 409, "finns redan"), ("5566778890", 422, "kontrollsiffra")],
)
def test_arbetsgivare_som_inte_kan_registreras(web, org, status, text):
    before = table_counts(web)
    response = post(web, "/arbetsgivare/ny",
                    {"org_number": org, "name": "X AB", "affiliation_date": "2026-01-01", "reason": "Avtal"})
    assert response.status_code == status
    assert text in response.text
    assert table_counts(web) == before


# --- aktuell lön och kontaktuppgifter -----------------------------------------------------------


def test_aktuell_lon_andras_och_skiljs_fran_loneunderlag(web):
    form = web.client.get(f"/forsakrade/{ANNA}/lon")
    assert form.status_code == 200
    assert 'value="45000.00"' in form.text and "Aktuell lön är stamdata" in form.text
    response = post(web, f"/forsakrade/{ANNA}/lon", {"monthly_salary_sek": "46 000", "employment_rate": "",
                                                    "reason": "Löneöversyn 2026"})
    assert response.status_code == 200, response.text
    assert "45 000,00 kr → <strong>46 000,00 kr</strong>" in response.text
    assert get_person(web, ANNA).monthly_salary_sek == Decimal("46000.00")
    with web.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(SalaryReport)) == 0
    again = post(web, f"/forsakrade/{ANNA}/lon", {"monthly_salary_sek": "46000", "reason": "Igen"})
    assert again.status_code == 409


def test_aktuell_lon_efter_anstallningens_slut_stoppas(web):
    response = post(web, f"/forsakrade/{CECILIA}/lon", {"monthly_salary_sek": "50000", "reason": "x"})
    assert response.status_code == 422
    assert "pågående anställning" in response.text


def test_kontaktuppgifter_andras(web):
    form = web.client.get(f"/forsakrade/{ANNA}/kontakt")
    assert 'value="anna.andersson@example.se"' in form.text
    response = post(web, f"/forsakrade/{ANNA}/kontakt", {
        "email": "anna@example.org", "phone": "070-123 45 67", "source": "insured",
        "reason": "Begärt av den försäkrade i telefon, verifierad med kontrollfrågor",
    })
    assert response.status_code == 200, response.text
    assert "anna.andersson@example.se → <strong>anna@example.org</strong>" in response.text
    anna = get_person(web, ANNA)
    assert (anna.email, anna.phone) == ("anna@example.org", "070-123 45 67")
    bad = post(web, f"/forsakrade/{ANNA}/kontakt", {"email": "fel@", "phone": "", "source": "insured", "reason": "x"})
    assert bad.status_code == 422
    assert "E-post: Fel format" in bad.text


# --- hela flödet ----------------------------------------------------------------------------------


def test_handlaggarflodet_anslut_lon_loneunderlag_fribrev(web):
    assert post(web, "/forsakrade/ny", enroll_form()).status_code == 200
    assert post(web, f"/forsakrade/{NORA}/lon", {"monthly_salary_sek": "42000", "reason": "Ny lön från oktober"}
                ).status_code == 200
    assert post(web, f"/forsakrade/{NORA}/loneunderlag", {
        "kind": "new", "period_month": "2026-10", "pensionable_salary_sek": "42000",
        "employer_org_number": "5560000001", "source": "employer", "received_date": "2026-10-12",
        "reason": "Lönefil oktober",
    }).status_code == 200
    response = post(web, "/forsakringar/AL-000005/fribrev",
                    {"employment_end_date": "2026-10-11", "reason": "Avanmälan: provanställningen avbröts"})
    assert response.status_code == 200, response.text

    with web.session_factory() as s:
        nora = s.scalars(select(InsuredPerson).where(InsuredPerson.personal_id_number == NORA)).one()
        states = sorted((st.state, st.valid_from, st.valid_to)
                        for st in s.scalars(select(PolicyState).join(Policy).where(Policy.policy_number == "AL-000005")))
        report = s.scalars(select(SalaryReport).where(SalaryReport.insured_person_id == nora.id)).one()
        writes = [e.operation for e in s.scalars(
            select(OperationEventRecord)
            .where(OperationEventRecord.kind == "write", OperationEventRecord.outcome == "executed")
            .order_by(OperationEventRecord.occurred_at))]
    assert (nora.status, nora.employment_end_date, nora.monthly_salary_sek) == ("terminated", date(2026, 10, 11),
                                                                               Decimal("42000.00"))
    assert states == [("paid_up", date(2026, 10, 12), None), ("premium_paying", date(2026, 9, 1), date(2026, 10, 11))]
    assert (report.period_month, report.pensionable_salary_sek) == (date(2026, 10, 1), Decimal("42000.00"))
    assert writes == ["enroll_insured_person", "update_current_salary", "register_salary_report", "set_policy_paid_up"]

    page = web.client.get(f"/forsakrade/{NORA}/handelser").text.split("<tbody>")[1]
    for operation in writes:
        assert operation in page
