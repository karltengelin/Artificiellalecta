"""Handläggar-UI:t, Fas 5 F5-4: ärendesidorna och handläggaragenten.

Mot demobeståndet i minnet. Agenten är en FakeProvider med skriptade svar – inga
modellanrop. Agentens tjänstelager prövar regelpaketet som om det gällde (2026-11-01),
så att agenten får föreslå löneunderlag; handläggarens UI har dagens regelstatus.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select

from ai.providers.fake import FakeProvider, text_result, tool_call_result
from models import Case, SalaryReport
from services import ProductRuleCatalog, ServiceLayer
from tests.test_agents_loop import ai_client
from web.agent import CaseAgent

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

ANNA = "198505151236"  # aktiv hos 5560000001, premier t.o.m. 2026-09
EMPLOYER = "5560000001"


def post(web, url, data, *, csrf=True):
    return web.client.post(url, data={**data, **({"csrf_token": web.csrf} if csrf else {})})


def case_form(**overrides):
    data = {
        "personal_id_number": ANNA, "employer_org_number": EMPLOYER, "kind": "new", "period_month": "2026-10",
        "pensionable_salary_sek": "47 000", "source": "employer", "source_reference": "LON-2026-10-ANNA",
        "received_date": "2026-10-10", "reason": "Lönefil från Demobolaget AB",
    }
    return {**data, **overrides}


def cases_in_db(web) -> int:
    with web.session_factory() as s:
        return s.scalar(select(func.count()).select_from(Case))


@pytest.fixture
def agent_web(web, tmp_path):
    """UI:t med en handläggaragent vars modell är skriptad; `script` fylls av testet."""
    fake = FakeProvider()
    web.app.state.case_agent = CaseAgent(
        agent_service_factory=lambda: ServiceLayer(
            session_factory=web.session_factory, validation_session_factory=web.session_factory,
            agent_role="agent_forsakring", rules=ProductRuleCatalog(today=date(2026, 11, 1)),
        ),
        simulated_role=True,
        ai_factory=lambda: ai_client(fake),
        journal_dir=tmp_path,
    )
    web.fake = fake
    web.journal_dir = tmp_path
    return web


def create(web, **overrides) -> str:
    response = post(web, "/arenden", case_form(**overrides))
    assert response.status_code == 200, response.text
    with web.session_factory() as s:
        return s.scalar(select(Case.case_number).order_by(Case.case_number.desc()))


class TestListaOchRegistrering:
    def test_meny_och_tom_lista(self, web):
        page = web.client.get("/arenden")
        assert page.status_code == 200
        assert 'href="/arenden"' in page.text and "Inga ärenden i urvalet" in page.text

    def test_formularet_fylls_i_fran_den_forsakrade(self, web):
        page = web.client.get(f"/arenden/ny?pnr={ANNA}")
        assert f'value="{ANNA}"' in page.text and f'value="{EMPLOYER}"' in page.text

    def test_registrera_och_visa(self, web):
        number = create(web)
        assert number == "CASE-000001"
        page = web.client.get(f"/arenden/{number}")
        assert "Anna Andersson" in page.text and "47" in page.text and "LON-2026-10-ANNA" in page.text
        assert "Öppet" in page.text
        listing = web.client.get("/arenden")
        assert number in listing.text

    def test_stoppad_registrering_andrar_ingenting(self, web):
        response = post(web, "/arenden", case_form(pensionable_salary_sek=""))
        assert response.status_code == 422
        assert "Ingenting har ändrats" in response.text or "ingenting" in response.text.lower()
        assert cases_in_db(web) == 0

    def test_formulartoken_kravs(self, web):
        assert post(web, "/arenden", case_form(), csrf=False).status_code == 403
        assert cases_in_db(web) == 0


class TestAgenten:
    def test_korning_utan_forslag(self, agent_web):
        number = create(agent_web)
        agent_web.fake.queue(
            tool_call_result("get_case", {"data": {"case_number": number}, "reason": None}),
            text_result("Underlaget ser komplett ut men inget förslag lades."),
        )
        page = post(agent_web, f"/arenden/{number}/agent", {})
        assert page.status_code == 200, page.text
        assert "Agentens körning" in page.text and "Klar" in page.text
        assert "Underlaget ser komplett ut" in page.text
        assert "simulerad" in page.text
        with agent_web.session_factory() as s:
            case = s.scalar(select(Case).where(Case.case_number == number))
        assert case.status == "in_progress" and case.last_run_id
        assert (agent_web.journal_dir / f"{case.last_run_id}.jsonl").exists()

    def test_forslag_godkannande_och_stangning(self, agent_web):
        number = create(agent_web)
        salary = {
            "data": {"personal_id_number": ANNA, "employer_org_number": EMPLOYER, "period_month": "2026-10-01",
                     "pensionable_salary_sek": "47000", "kind": "new", "corrects_version": None, "source": "employer",
                     "source_reference": "LON-2026-10-ANNA", "received_date": "2026-10-10"},
            "reason": "Enligt ärendets lönefil",
        }
        agent_web.fake.queue(
            tool_call_result("get_case", {"data": {"case_number": number}, "reason": None}),
            tool_call_result("register_salary_report", salary, call_id="call_2"),
        )
        page = post(agent_web, f"/arenden/{number}/agent", {})
        assert "Väntar på godkännande" in page.text and "ingenting är ändrat ännu" in page.text
        (approval_id,) = [r.id for r in agent_web.service.approvals.list("pending") if r.case_id == number]

        queue = agent_web.client.get("/godkannanden")
        assert f'href="/arenden/{number}"' in queue.text
        assert post(agent_web, f"/godkannanden/{approval_id}/godkann", {}).status_code == 200

        closed = post(agent_web, f"/arenden/{number}/stang", {"outcome": "approved", "reason": "Registrerat"})
        assert closed.status_code == 200 and "Ärendet är stängt" in closed.text
        assert "Starta agent" not in closed.text  # stängt ärende körs inte igen

    def test_utan_agent_finns_ingen_knapp(self, web):
        number = create(web)
        page = web.client.get(f"/arenden/{number}")
        assert "Agenten är inte konfigurerad" in page.text and "Starta agent" not in page.text
        assert post(web, f"/arenden/{number}/agent", {}).status_code == 409


class TestHandlaggning:
    def test_egen_registrering_i_arendet_och_stangning(self, web):
        number = create(web)
        form = web.client.get(f"/forsakrade/{ANNA}/loneunderlag/ny?arende={number}&manad=2026-10&lon=47000")
        assert f'name="case_number" value="{number}"' in form.text and "LON-2026-10-ANNA" in form.text
        response = post(web, f"/forsakrade/{ANNA}/loneunderlag", {
            "case_number": number, "kind": "new", "period_month": "2026-10", "pensionable_salary_sek": "47000",
            "employer_org_number": EMPLOYER, "source": "employer", "source_reference": "LON-2026-10-ANNA",
            "received_date": "2026-10-10", "reason": "Registrerat i ärendet",
        })
        assert response.status_code == 200, response.text
        with web.session_factory() as s:
            assert s.scalar(select(func.count()).select_from(SalaryReport)) == 1
        page = web.client.get(f"/arenden/{number}")
        assert "register_salary_report" in page.text  # i ärendets historik
        closed = post(web, f"/arenden/{number}/stang", {"outcome": "approved", "reason": "Registrerat själv"})
        assert "Ärendet är stängt" in closed.text

    def test_avslag_kraver_motivering_och_statusbyte(self, web):
        number = create(web)
        refused = post(web, f"/arenden/{number}/stang", {"outcome": "rejected", "reason": "Fel underlag"})
        assert refused.status_code == 422
        changed = post(web, f"/arenden/{number}/status", {"status": "waiting_info", "reason": "Komplettering begärd"})
        assert "Väntar på komplettering" in changed.text
        closed = post(web, f"/arenden/{number}/stang", {
            "outcome": "rejected", "closing_note": "Lönen gäller fel månad", "reason": "Avslag",
        })
        assert "Avslaget" in closed.text

    def test_godkant_utan_andring_stoppas(self, web):
        number = create(web)
        response = post(web, f"/arenden/{number}/stang", {"outcome": "approved", "reason": "Klart"})
        assert response.status_code == 422 and "genomförd ändring" in response.text
