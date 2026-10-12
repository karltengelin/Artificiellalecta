"""Handläggar-UI:t, S3: godkännandekön och händelseloggen.

Demobeståndet har två agentförslag i kön (utils/demo_data.py): löneunderlag för
Anna 2026-10 och fribrev för Bertil (AL-000002) med sista dag 2026-09-30.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from models import ApprovalRequestRecord, OperationEventRecord, PolicyState, SalaryReport
from services import AccessDeniedError, Actor, NotFoundError, OperationContext

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

ANNA = "198505151236"
BERTIL = "197203034561"
AGENT = OperationContext(actor=Actor.agent("case_handler", team="forsakring"), run_id="run-1")


def post(web, url: str, data: dict | None = None, *, csrf: bool = True):
    return web.client.post(url, data={**(data or {}), **({"csrf_token": web.csrf} if csrf else {})})


def proposals(web) -> dict[str, ApprovalRequestRecord]:
    with web.session_factory() as s:
        return {r.operation: r for r in s.scalars(select(ApprovalRequestRecord))}


def events(web, **where) -> list[OperationEventRecord]:
    with web.session_factory() as s:
        query = select(OperationEventRecord).order_by(OperationEventRecord.occurred_at)
        for key, value in where.items():
            query = query.where(getattr(OperationEventRecord, key) == value)
        return list(s.scalars(query))


def salary_reports(web) -> list[SalaryReport]:
    with web.session_factory() as s:
        return list(s.scalars(select(SalaryReport)))


# --- kön ----------------------------------------------------------------------------------------


def test_kon_visar_vantande_forslag_och_antal_i_menyn(web):
    response = web.client.get("/godkannanden")
    assert response.status_code == 200
    text = response.text
    assert 'title="Väntande förslag">2<' in text
    assert "register_salary_report" in text and "set_policy_paid_up" in text
    assert "demo_handlaggaragent" in text and "Lönefil från Demobolaget AB" in text
    assert f'href="/forsakrade/{ANNA}"' in text and 'href="/forsakringar/AL-000002"' in text
    assert "Godkänn och utför" in text and "Avslå" in text
    assert events(web, operation="list_approval_requests")[-1].actor_id == "karl"  # läsningen loggas


def test_godkant_forslag_verkstalls_med_agenten_som_forslagsstallare(web):
    request_id = proposals(web)["register_salary_report"].id
    response = post(web, f"/godkannanden/{request_id}/godkann", {"note": "Stämmer med lönefilen"})
    assert response.status_code == 200, response.text
    assert "Förslaget är godkänt och utfört" in response.text
    assert "Anna Andersson" in response.text
    [report] = salary_reports(web)
    assert (report.period_month, report.pensionable_salary_sek) == (date(2026, 10, 1), Decimal("46500.00"))
    decided = proposals(web)["register_salary_report"]
    assert (decided.status, decided.decided_by, decided.decision_note) == ("approved", "karl", "Stämmer med lönefilen")
    executed = events(web, operation="register_salary_report", outcome="executed")[-1]
    assert (executed.actor_id, executed.proposed_by, executed.approval_id) == ("karl", "demo_handlaggaragent", request_id)
    assert 'title="Väntande förslag">1<' in web.client.get("/").text


def test_godkant_fribrev_via_forsakringsnummer(web):
    request_id = proposals(web)["set_policy_paid_up"].id
    response = post(web, f"/godkannanden/{request_id}/godkann")  # kommentaren är valfri
    assert response.status_code == 200, response.text
    assert "Fribrev AL-000002" in response.text and "Bertil Berg" in response.text
    with web.session_factory() as s:
        open_state = s.scalars(select(PolicyState).where(PolicyState.valid_to.is_(None),
                                                         PolicyState.state == "paid_up",
                                                         PolicyState.valid_from == date(2026, 10, 1))).one()
    assert open_state is not None


def test_godkannande_som_krockar_med_aktuellt_lage_rullas_tillbaka(web):
    """Handläggaren hann registrera underlaget själv – förslaget prövas igen och krockar."""
    response = post(web, f"/forsakrade/{ANNA}/loneunderlag", {
        "kind": "new", "period_month": "2026-10", "pensionable_salary_sek": "46500", "employer_org_number": "5560000001",
        "source": "employer", "received_date": "2026-10-12", "reason": "Lönefilen registrerad manuellt",
    })
    assert response.status_code == 200
    request_id = proposals(web)["register_salary_report"].id
    response = post(web, f"/godkannanden/{request_id}/godkann")
    assert response.status_code == 409
    assert "Krock med aktuellt läge" in response.text
    assert f"Gäller ärende <code>{request_id}</code>" in response.text
    assert "Ingenting har ändrats" in response.text
    assert proposals(web)["register_salary_report"].status == "pending"
    assert len(salary_reports(web)) == 1
    assert not events(web, approval_id=request_id, outcome="executed")


def test_samma_forslag_kan_inte_avgoras_tva_ganger(web):
    request_id = proposals(web)["set_policy_paid_up"].id
    assert post(web, f"/godkannanden/{request_id}/godkann").status_code == 200
    response = post(web, f"/godkannanden/{request_id}/godkann")
    assert response.status_code == 409
    assert "redan approved" in response.text
    response = post(web, f"/godkannanden/{request_id}/avsla", {"note": "För sent"})
    assert response.status_code == 409


def test_avslag_kraver_skal_och_andrar_ingenting(web):
    request_id = proposals(web)["register_salary_report"].id
    response = post(web, f"/godkannanden/{request_id}/avsla", {"note": " "})
    assert response.status_code == 422
    assert "Skäl saknas" in response.text
    assert proposals(web)["register_salary_report"].status == "pending"

    response = post(web, f"/godkannanden/{request_id}/avsla", {"note": "Lönefilen var preliminär"})
    assert response.status_code == 200
    assert "är avslaget" in response.text
    decided = proposals(web)["register_salary_report"]
    assert (decided.status, decided.decided_by) == ("rejected", "karl")
    rejected = events(web, outcome="rejected")[-1]
    assert (rejected.approval_id, rejected.detail, rejected.proposed_by) == (
        request_id, "Lönefilen var preliminär", "demo_handlaggaragent")
    assert salary_reports(web) == []
    assert "Lönefilen var preliminär" in web.client.get("/godkannanden", params={"status": "avslagna"}).text


def test_okant_arende(web):
    assert post(web, "/godkannanden/finnsinte/godkann").status_code == 404
    assert post(web, "/godkannanden/finnsinte/avsla", {"note": "x"}).status_code == 409


def test_beslut_kraver_formulartoken(web):
    request_id = proposals(web)["register_salary_report"].id
    assert post(web, f"/godkannanden/{request_id}/godkann", csrf=False).status_code == 403
    assert post(web, f"/godkannanden/{request_id}/avsla", {"note": "x"}, csrf=False).status_code == 403
    assert proposals(web)["register_salary_report"].status == "pending"


# --- händelseloggen ------------------------------------------------------------------------------


def test_handelseloggen_visar_andringar_och_doljer_lasningar(web):
    web.client.get(f"/forsakrade/{ANNA}")
    text = web.client.get("/handelselogg").text
    assert "Föreslagen" in text and "demo_handlaggaragent" in text
    assert "get_insured_overview" not in text.split("<tbody>")[1]
    with_reads = web.client.get("/handelselogg", params={"lasningar": "1"}).text
    assert "get_insured_overview" in with_reads.split("<tbody>")[1]
    assert events(web, operation="get_operation_events")[-1].input["include_reads"] is True


def test_handelseloggen_kan_filtreras(web):
    request_id = proposals(web)["register_salary_report"].id
    post(web, f"/godkannanden/{request_id}/avsla", {"note": "Fel månad"})
    text = web.client.get("/handelselogg", params={"utfall": "rejected"}).text
    body = text.split("<tbody>")[1]
    assert "Avslagen" in body and "Föreslagen" not in body
    assert web.client.get("/handelselogg", params={"utfall": "okänt"}).status_code == 422


def test_handelser_per_forsakrad(web):
    for request_id in [r.id for r in proposals(web).values()]:
        post(web, f"/godkannanden/{request_id}/godkann")
    anna = web.client.get(f"/forsakrade/{ANNA}/handelser").text.split("<tbody>")[1]
    bertil = web.client.get(f"/forsakrade/{BERTIL}/handelser").text.split("<tbody>")[1]
    assert "register_salary_report" in anna and "set_policy_paid_up" not in anna
    assert "set_policy_paid_up" in bertil and "register_salary_report" not in bertil


# --- operationerna i tjänstelagret ---------------------------------------------------------------


def test_kon_och_loggen_ar_endast_handlaggare(web):
    for name, data in [("list_approval_requests", {}), ("count_approval_requests", {}),
                       ("get_operation_events", {})]:
        assert web.service.decision(name).effective.value == "HUMAN_ONLY"
        with pytest.raises(AccessDeniedError):
            web.service.execute(name, AGENT, data)


def test_raknaren_loggas_inte(web):
    before = len(events(web))
    counts = web.service.execute("count_approval_requests", OperationContext(actor=Actor.human("karl")), {}).output
    assert (counts.pending, counts.approved, counts.rejected) == (2, 0, 0)
    assert len(events(web)) == before


def test_handelser_for_premierattelse_hittas_via_premieradens_id(web):
    from tests.test_web_changes import premium_id

    original = premium_id(web, "AL-000001", date(2026, 9, 1))
    post(web, f"/forsakringar/AL-000001/premier/{original}/rattelse",
         {"corrected_salary_sek": "46000", "basis_reference": "Rättat lönebesked", "reason": "Rättelse"})
    ctx = OperationContext(actor=Actor.human("karl"))
    anna = web.service.execute("get_operation_events", ctx, {"personal_id_number": ANNA}).output
    assert [e.operation for e in anna.events][:1] == ["correct_premium_transaction"]
    bertil = web.service.execute("get_operation_events", ctx, {"personal_id_number": BERTIL}).output
    assert "correct_premium_transaction" not in [e.operation for e in bertil.events]
    with pytest.raises(NotFoundError):
        web.service.execute("get_operation_events", ctx, {"personal_id_number": "199912319999"})


def test_loggen_kan_begransas_och_sager_till_nar_fler_finns(web):
    ctx = OperationContext(actor=Actor.human("karl"))
    log = web.service.execute("get_operation_events", ctx, {"limit": 1}).output
    assert (log.count, log.truncated) == (1, True)


def test_efter_beslut_pekar_historiken_pa_en_sida_som_gar_att_ladda_om(web):
    ids = {name: r.id for name, r in proposals(web).items()}
    rejected = post(web, f"/godkannanden/{ids['register_salary_report']}/avsla", {"note": "Fel"})
    assert rejected.headers["HX-Push-Url"] == "/godkannanden?status=vantar"
    approved = post(web, f"/godkannanden/{ids['set_policy_paid_up']}/godkann")
    assert approved.headers["HX-Push-Url"] == f"/forsakrade/{BERTIL}"
    reload = web.client.get(f"/godkannanden/{ids['set_policy_paid_up']}/godkann", follow_redirects=False)
    assert (reload.status_code, reload.headers["location"]) == (303, "/godkannanden")
