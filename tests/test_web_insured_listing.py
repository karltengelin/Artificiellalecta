"""Beståndsvyn använder tjänstelagret och behåller urvalet mellan sidor."""

import re
from html import unescape
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from models import OperationEventRecord
from web.config import WebSettings


def test_namnsokning_fran_startsidan_oppnar_bestandet(web):
    response = web.client.get("/sok", params={"q": "Anna Andersson"}, follow_redirects=False)
    assert response.status_code == 303
    assert parse_qs(urlparse(response.headers["location"]).query) == {"q": ["Anna Andersson"]}
    result = web.client.get(response.headers["location"])
    assert result.status_code == 200
    assert "1 träff</strong>" in result.text
    assert 'href="/forsakrade/198505151236"' in result.text
    assert 'href="/forsakringar/AL-000001"' in result.text


def test_bestandet_visar_datakalla_och_sidindelning(web):
    response = web.client.get("/forsakrade")
    assert response.status_code == 200
    assert "Bestånd i DEMO – lokal övningsdata" in response.text
    assert "35 träffar" in response.text
    assert "Visar 1–25 · Sida 1 av 2" in response.text
    first = set(re.findall(r'href="(/forsakrade/\d{12})"', response.text))
    assert len(first) == 25
    next_url = unescape(re.search(r'rel="next" href="([^"]+)"', response.text)[1])
    following = web.client.get(next_url)
    second = set(re.findall(r'href="(/forsakrade/\d{12})"', following.text))
    assert len(second) == 10
    assert not first & second
    assert "Visar 26–35 · Sida 2 av 2" in following.text


def test_sidbyte_bevarar_sokord_arbetsgivare_lage_och_sidstorlek(web):
    response = web.client.get("/forsakrade", params={
        "q": "a", "employer_org_number": "5560000001", "policy_state": "premium_paying", "page_size": 1,
    })
    assert response.status_code == 200
    next_url = unescape(re.search(r'rel="next" href="([^"]+)"', response.text)[1])
    assert parse_qs(urlparse(next_url).query) == {
        "q": ["a"], "employer_org_number": ["5560000001"],
        "policy_state": ["premium_paying"], "page_size": ["1"], "page": ["2"],
    }
    following = web.client.get(next_url)
    assert following.status_code == 200
    assert 'value="premium_paying" selected' in following.text
    assert 'value="5560000001" selected' in following.text


def test_tomt_urval_och_rensa_lank(web):
    response = web.client.get("/forsakrade", params={"q": "saknashelt"})
    assert response.status_code == 200
    assert "0 träffar" in response.text
    assert "Inga försäkrade matchar urvalet" in response.text
    assert "rensa urvalet" in response.text


@pytest.mark.parametrize("query", [
    {"page": 0}, {"page_size": 1000}, {"policy_state": "unknown"},
    {"employer_org_number": "fel"}, {"q": "a" * 201},
])
def test_ogiltigt_urval_visar_valideringsfel(web, query):
    response = web.client.get("/forsakrade", params=query)
    assert response.status_code == 422
    assert "Visa beståndet utan filter" in response.text
    assert "0 träffar" not in response.text


def test_bestandslasningen_loggas_med_handlaggare_och_urval(web):
    response = web.client.get("/forsakrade", params={"q": "Cecilia", "policy_state": "paid_up"})
    assert response.status_code == 200
    with web.session_factory() as session:
        (entry,) = session.scalars(select(OperationEventRecord).where(
            OperationEventRecord.operation == "list_insured_persons",
        )).all()
        assert (entry.actor_id, entry.actor_type, entry.pii) == ("karl", "human", True)
        assert entry.input["q"] == "Cecilia"
        assert entry.input["policy_state"] == "paid_up"
        assert entry.output is None


def test_databasfel_blir_fel_inte_ett_tomt_bestand(web, monkeypatch):
    web.app.state.settings = WebSettings(database="lakebase", allowed_hosts=("testserver",))

    def unavailable(*args, **kwargs):
        raise ConnectionError("hemlig anslutningsinformation")

    monkeypatch.setattr(web.service, "execute", unavailable)
    with TestClient(web.app, raise_server_exceptions=False) as client:
        response = client.get("/forsakrade")
    assert response.status_code == 500
    assert "0 träffar" not in response.text
    assert "hemlig anslutningsinformation" not in response.text
    assert "Ingen annan databas används automatiskt" in response.text
