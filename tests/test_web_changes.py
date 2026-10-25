"""Handläggar-UI:t, S2: skrivformulären för löneunderlag, fribrev och premierättelse.

Varje stoppat anrop (BlockedError, ConflictError, valideringsfel, saknad
motivering, saknad formulärtoken) visas med skäl och regel – och testerna
kontrollerar att ingenting ändrades, varken data eller händelselogg.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models import (
    InsuredPerson,
    OperationEventRecord,
    Policy,
    PolicyBenefit,
    PolicyState,
    PremiumTransaction,
    ProductParameter,
    SalaryReport,
)

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

ANNA = "198505151236"  # aktiv, AL-000001, premier 2025-01–2026-09 (2026-09 fakturerad)
REASON = "Lönefil från Demobolaget AB, referens i formuläret"


def post(web, url: str, data: dict, *, csrf: bool = True, **kwargs):
    payload = {**data, **({"csrf_token": web.csrf} if csrf else {})}
    return web.client.post(url, data=payload, **kwargs)


def salary_form(**overrides) -> dict:
    data = {
        "kind": "new", "period_month": "2026-10", "pensionable_salary_sek": "47 000,50",
        "employer_org_number": "5560000001", "source": "employer", "source_reference": "LON-2026-10-A",
        "received_date": "2026-10-10", "reason": REASON,
    }
    return {**data, **overrides}


def snapshot(web) -> dict:
    """Det som en stoppad ändring inte får röra."""
    with web.session_factory() as s:
        return {
            "salary_reports": s.scalar(select(func.count()).select_from(SalaryReport)),
            "premiums": s.scalar(select(func.count()).select_from(PremiumTransaction)),
            "states": sorted((st.state, st.valid_from, st.valid_to) for st in s.scalars(select(PolicyState))),
            "persons": sorted((p.personal_id_number, p.status, p.employment_end_date)
                              for p in s.scalars(select(InsuredPerson))),
            "changes": s.scalar(
                select(func.count()).select_from(OperationEventRecord)
                .where(OperationEventRecord.kind == "write", OperationEventRecord.outcome == "executed")
            ),
        }


def premium_id(web, policy_number: str, month: date) -> str:
    with web.session_factory() as s:
        return str(s.scalar(
            select(PremiumTransaction.id)
            .join(PolicyBenefit, PremiumTransaction.benefit_id == PolicyBenefit.id)
            .join(Policy, PolicyBenefit.policy_id == Policy.id)
            .where(Policy.policy_number == policy_number, PremiumTransaction.period_month == month,
                   PremiumTransaction.transaction_type == "premium")
        ))


def last_write_event(web) -> OperationEventRecord:
    with web.session_factory() as s:
        return s.scalars(
            select(OperationEventRecord).where(OperationEventRecord.kind == "write")
            .order_by(OperationEventRecord.occurred_at.desc())
        ).first()


# --- löneunderlag -------------------------------------------------------------------------------


def test_formularet_visar_operationen_reglerna_och_agentnivan(web):
    response = web.client.get(f"/forsakrade/{ANNA}/loneunderlag/ny")
    assert response.status_code == 200
    text = response.text
    assert "register_salary_report" in text
    assert "<code>PR-ITP1-014</code> pensionsmedförande månadslön" in text
    assert "effektiv nivå: <code>HUMAN_ONLY</code>" in text  # regelgolvet till 2026-11-01
    assert "kommande, gäller från 2026-11-01" in text
    assert f'value="{web.csrf}"' in text
    assert 'value="5560000001"' in text  # nuvarande arbetsgivare förifylld


def test_nytt_loneunderlag_registreras_och_loggas(web):
    response = post(web, f"/forsakrade/{ANNA}/loneunderlag", salary_form())
    assert response.status_code == 200, response.text
    assert "Nytt löneunderlag registrerat" in response.text
    with web.session_factory() as s:
        report = s.scalars(select(SalaryReport)).one()
    assert (report.period_month, report.version, report.pensionable_salary_sek) == (
        date(2026, 10, 1), 1, Decimal("47000.50"))
    event = last_write_event(web)
    assert (event.operation, event.outcome, event.actor_type, event.actor_id, event.reason) == (
        "register_salary_report", "executed", "human", "karl", REASON)
    assert "PR-ITP1-014 v1.0 kommande" in event.detail


def test_rattelse_blir_ny_version(web):
    post(web, f"/forsakrade/{ANNA}/loneunderlag", salary_form())
    response = post(web, f"/forsakrade/{ANNA}/loneunderlag", salary_form(
        kind="correction", corrects_version="1", pensionable_salary_sek="48000", source_reference="LON-2026-10-B"))
    assert response.status_code == 200, response.text
    assert "Rättat från 47000.50 till 48000" in response.text
    salary_page = web.client.get(f"/forsakrade/{ANNA}/loneunderlag").text
    assert "v2" in salary_page and "ersatt" in salary_page


def test_saknad_motivering_stoppas_och_ingenting_andras(web):
    before = snapshot(web)
    response = post(web, f"/forsakrade/{ANNA}/loneunderlag", salary_form(reason="  "))
    assert response.status_code == 422
    assert "Motivering saknas" in response.text
    assert "Ingenting har ändrats" in response.text
    assert snapshot(web) == before


def test_ogiltigt_belopp_visas_vid_faltet_och_inmatningen_finns_kvar(web):
    before = snapshot(web)
    response = post(web, f"/forsakrade/{ANNA}/loneunderlag", salary_form(pensionable_salary_sek="fyrtio"))
    assert response.status_code == 422
    assert "Ogiltiga uppgifter" in response.text
    assert "Ange ett belopp" in response.text
    assert 'value="LON-2026-10-A"' in response.text  # övriga värden kvar
    assert snapshot(web) == before


def test_manad_med_premie_stoppas_med_skal(web):
    before = snapshot(web)
    response = post(web, f"/forsakrade/{ANNA}/loneunderlag", salary_form(period_month="2026-09"))
    assert response.status_code == 422
    assert "Stoppat – kräver manuell prövning" in response.text
    assert "correct_premium_transaction" in response.text
    assert "Ingenting har ändrats" in response.text
    assert snapshot(web) == before


def test_framtida_manad_stoppas_med_regel_och_regelstatus(web):
    response = post(web, f"/forsakrade/{ANNA}/loneunderlag", salary_form(period_month="2026-11"))
    assert response.status_code == 422
    assert "har inte kommit" in response.text
    assert "<code>PR-ITP1-014</code> pensionsmedförande månadslön" in response.text
    assert "(kommande, gäller från 2026-11-01)" in response.text


def test_dubblett_ar_en_konflikt_med_regel(web):
    post(web, f"/forsakrade/{ANNA}/loneunderlag", salary_form())
    before = snapshot(web)
    response = post(web, f"/forsakrade/{ANNA}/loneunderlag", salary_form(source_reference="LON-2026-10-X"))
    assert response.status_code == 409
    assert "Krock med aktuellt läge" in response.text
    assert "<code>PR-ITP1-017</code>" in response.text
    assert snapshot(web) == before


def test_utan_formulartoken_nekas_skrivningen(web):
    before = snapshot(web)
    response = post(web, f"/forsakrade/{ANNA}/loneunderlag", salary_form(), csrf=False)
    assert response.status_code == 403
    assert "formulärtoken" in response.text
    response = post(web, f"/forsakrade/{ANNA}/loneunderlag", {**salary_form(), "csrf_token": "fel"}, csrf=False)
    assert response.status_code == 403
    assert snapshot(web) == before


def test_htmx_far_felsvaret_med_formularet(web):
    response = post(web, f"/forsakrade/{ANNA}/loneunderlag", salary_form(period_month="2026-09"),
                    headers={"HX-Request": "true"})
    assert response.status_code == 422
    assert "<form" in response.text and "Stoppat" in response.text


def test_forhandsberakning_sparar_ingenting(web):
    before = snapshot(web)
    response = post(web, "/berakna/premie", {
        "pensionable_salary_sek": "45 000", "period_month": "2026-10", "personal_id_number": ANNA,
    })
    assert response.status_code == 200
    assert "2 025,00 kr" in response.text
    assert snapshot(web) == before


def test_forhandsberakning_visar_andrade_parametrar_utan_gamla_granser_eller_satser(web):
    with web.session_factory() as s:
        for key, value in (("premium_rate_low", "0.05"), ("premium_age_end", "40")):
            s.scalars(select(ProductParameter).where(ProductParameter.key == key)).one().value = Decimal(value)
    before = snapshot(web)
    response = post(web, "/berakna/premie", {
        "pensionable_salary_sek": "45 000", "period_month": "2026-10", "personal_id_number": ANNA,
    })
    assert response.status_code == 200
    assert "Utanför gällande åldersfönster" in response.text  # Anna är 41 år, gränsen är 40
    assert "25–66" not in response.text
    eligible = post(web, "/berakna/premie", {
        "pensionable_salary_sek": "45 000", "period_month": "2026-10", "personal_id_number": "199204171236",
    })
    assert eligible.status_code == 200
    assert "2 250,00 kr" in eligible.text  # 5 %, inte den tidigare satsen 4,5 %
    assert "4,5 %-delen" not in eligible.text
    assert snapshot(web) == before


# --- fribrev ------------------------------------------------------------------------------------


def test_fribrev_registreras_med_anstallningens_slut(web):
    assert "Avanmälan/fribrev" in web.client.get(f"/forsakrade/{ANNA}").text
    assert web.client.get("/forsakringar/AL-000001/fribrev").status_code == 200
    response = post(web, "/forsakringar/AL-000001/fribrev",
                    {"employment_end_date": "2026-09-30", "reason": "Avanmälan från Demobolaget AB"})
    assert response.status_code == 200, response.text
    assert "Fribrev AL-000001" in response.text
    with web.session_factory() as s:
        person = s.scalars(select(InsuredPerson).where(InsuredPerson.personal_id_number == ANNA)).one()
        states = sorted(
            (st.state, st.valid_from, st.valid_to)
            for st in s.scalars(select(PolicyState).join(Policy).where(Policy.policy_number == "AL-000001"))
        )
    assert (person.status, person.employment_end_date) == ("terminated", date(2026, 9, 30))
    assert states == [("paid_up", date(2026, 10, 1), None), ("premium_paying", date(2015, 3, 1), date(2026, 9, 30))]
    assert last_write_event(web).operation == "set_policy_paid_up"


@pytest.mark.parametrize(
    ("policy", "end", "status", "text"),
    [
        ("AL-000001", "2026-10-20", 422, "ligger i framtiden"),
        ("AL-000004", "2026-09-30", 422, "fribrev prövas manuellt"),  # pensionerad, utbetalning pågår
        ("AL-000003", "2025-12-31", 409, "redan fribrev"),
    ],
)
def test_fribrev_som_inte_stods_stoppas_och_ingenting_andras(web, policy, end, status, text):
    before = snapshot(web)
    response = post(web, f"/forsakringar/{policy}/fribrev", {"employment_end_date": end, "reason": "Avanmälan"})
    assert response.status_code == status
    assert text in response.text
    assert "Ingenting har ändrats" in response.text
    assert snapshot(web) == before


def test_fribrev_for_okand_forsakring_ger_404(web):
    response = post(web, "/forsakringar/AL-999999/fribrev", {"employment_end_date": "2026-09-30", "reason": "x"})
    assert response.status_code == 404
    assert "Ingen försäkring med nummer AL-999999" in response.text


# --- premierättelse -----------------------------------------------------------------------------


def test_rattelse_av_ej_mottagen_premie_skapar_lankad_rad(web):
    original = premium_id(web, "AL-000001", date(2026, 9, 1))
    url = f"/forsakringar/AL-000001/premier/{original}/rattelse"
    form = web.client.get(url)
    assert form.status_code == 200 and "2026-09" in form.text
    response = post(web, url, {"corrected_salary_sek": "46000", "basis_reference": "Rättat lönebesked 2026-09",
                               "reason": "Arbetsgivaren rättade septemberlönen"})
    assert response.status_code == 200, response.text
    assert "Ej mottagen premie" in response.text
    with web.session_factory() as s:
        adjustment = s.scalars(select(PremiumTransaction).where(PremiumTransaction.transaction_type == "adjustment")).one()
    assert (str(adjustment.corrects_transaction_id), adjustment.amount_sek, adjustment.status) == (
        original, Decimal("45.00"), "pending")
    assert "rättelse" in web.client.get("/forsakringar/AL-000001/premier").text


def test_minskning_av_mottagen_premie_stoppas_med_regler(web):
    original = premium_id(web, "AL-000001", date(2026, 8, 1))
    before = snapshot(web)
    response = post(web, f"/forsakringar/AL-000001/premier/{original}/rattelse",
                    {"corrected_salary_sek": "40000", "basis_reference": "Rättat lönebesked", "reason": "Rättelse"})
    assert response.status_code == 422
    assert "minska redan mottagen premie" in response.text
    assert "<code>PR-ITP1-019</code>" in response.text and "<code>PR-ITP1-020</code>" in response.text
    assert "Ingenting har ändrats" in response.text
    assert snapshot(web) == before


def test_rattelse_av_okand_rad_ger_404(web):
    response = web.client.get("/forsakringar/AL-000001/premier/00000000-0000-0000-0000-000000000000/rattelse")
    assert response.status_code == 404
