"""Handläggar-UI:t, Fas 3c 3c-P2: sidan /parametrar (B-035).

Mot demobeståndet i minnet; testets dag är 2026-10-12 (conftest), så tidigaste
giltighetsdag för en ny version är 2026-11-01.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from models import ProductParameter

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")


def post(web, url, data):
    return web.client.post(url, data={**data, "csrf_token": web.csrf})


def schedule_form(**overrides):
    data = {
        "key": "premium_age_end", "value": "67", "valid_from": "2027-01", "rule_version": "1.1",
        "source_ref": "K-SIM-ITP-2027", "decision_ref": "B-035 demo", "reason": "Fiktiv avtalsändring",
    }
    return {**data, **overrides}


def age_end_versions(web):
    with web.session_factory() as s:
        rows = s.scalars(select(ProductParameter).where(ProductParameter.key == "premium_age_end")
                         .order_by(ProductParameter.valid_from))
        return [(r.valid_from, r.valid_to, r.status) for r in rows]


def test_sidan_visar_gallande_varden_och_versioner(web):
    page = web.client.get("/parametrar")
    assert page.status_code == 200
    html = page.text
    assert 'href="/parametrar" aria-current="page"' in html
    for text in ("Premieålder till", "66 år", "4,5 %", "30 %", "7,5 IBB", "30 IBB", "PR-ITP1-013 v1.0", "K-ITP-FIL"):
        assert text in html, text
    assert "Schemalägg en ny version" in html and "schedule_product_parameter_change" in html


def test_handlaggaren_schemalagger_och_drar_tillbaka(web):
    page = post(web, "/parametrar/ny", schedule_form())
    assert page.status_code == 200
    assert "Premieålder till blir 67 år från 2027-01-01" in page.text
    assert "Kommande" in page.text and "Dra tillbaka" in page.text
    assert age_end_versions(web) == [(date(2023, 1, 1), date(2026, 12, 31), "valid"), (date(2027, 1, 1), None, "valid")]

    page = post(web, "/parametrar/aterkalla", {"key": "premium_age_end", "valid_from": "2027-01-01", "reason": "Ändringen ställdes in"})
    assert page.status_code == 200
    assert "är återkallad" in page.text and "66 år gäller vidare" in page.text
    assert age_end_versions(web)[0] == (date(2023, 1, 1), None, "valid")


def test_stopp_visas_och_ingenting_andras(web):
    page = post(web, "/parametrar/ny", schedule_form(valid_from="2026-10"))
    assert page.status_code == 422
    assert "tidigast 2026-11-01" in page.text and "Ingenting har ändrats" in page.text
    assert 'value="2026-10"' in page.text  # formuläret behåller värdena
    assert len(age_end_versions(web)) == 1


def test_procent_och_kommatecken_tolkas(web):
    page = post(web, "/parametrar/ny", schedule_form(key="premium_rate_low", value="0,05", valid_from="2026-11"))
    assert "Premiesats under brytpunkten blir 5 % från 2026-11-01" in page.text


def test_formularet_kraver_token(web):
    response = web.client.post("/parametrar/ny", data=schedule_form())
    assert response.status_code == 403
    assert len(age_end_versions(web)) == 1


def test_andringen_loggas_med_handlaggare_och_motivering(web):
    post(web, "/parametrar/ny", schedule_form())
    events = web.client.get("/handelselogg").text
    assert "schedule_product_parameter_change" in events and "Fiktiv avtalsändring" in events
