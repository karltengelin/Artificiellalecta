"""Handläggar-UI:t, S1: sök, översikt, löneunderlag och premiehistorik.

Alla sidor läser via tjänstelagret; varje visning loggas som läsning av
personuppgifter med handläggaren som aktör.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import select

from models import OperationEventRecord
from web.config import WebConfigError, WebSettings
from web.routes.insured import parse_query

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

ANNA = "198505151236"
CECILIA = "199001017897"


def read_events(web, operation: str | None = None) -> list[OperationEventRecord]:
    with web.session_factory() as s:
        query = select(OperationEventRecord).order_by(OperationEventRecord.occurred_at)
        if operation:
            query = query.where(OperationEventRecord.operation == operation)
        return list(s.scalars(query))


# --- sök ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("19850515-1236", ("pnr", ANNA)),
        (" 198505151236 ", ("pnr", ANNA)),
        ("al-000002", ("policy", "AL-000002")),
        ("AL000002", ("policy", "AL-000002")),
    ],
)
def test_sokningen_kanner_igen_personnummer_och_forsakringsnummer(query, expected):
    assert parse_query(query) == expected


def test_sokning_pa_personnummer_leder_till_oversikten(web):
    response = web.client.get("/sok", params={"q": "19850515-1236"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/forsakrade/{ANNA}"


def test_sokning_med_htmx_navigerar_med_hx_location(web):
    response = web.client.get("/sok", params={"q": "AL-000003"}, headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.headers["HX-Location"] == "/forsakringar/AL-000003"


def test_tiosiffrigt_personnummer_ger_begripligt_fel(web):
    response = web.client.get("/sok", params={"q": "850515-1236"})
    assert response.status_code == 422
    assert "tolv siffror" in response.text


def test_okant_personnummer_ger_404_med_sokrutan_kvar(web):
    response = web.client.get("/forsakrade/199912319999")
    assert response.status_code == 404
    assert "Ingen försäkrad med det personnumret" in response.text
    assert 'name="q"' in response.text


# --- översikt, löneunderlag, premier ------------------------------------------------------------


def test_oversikten_visar_person_anstallning_forsakringar_och_kapital(web):
    response = web.client.get(f"/forsakrade/{ANNA}")
    assert response.status_code == 200
    text = response.text
    assert "Anna Andersson" in text
    assert "19850515-1236" in text
    assert "Demobolaget AB" in text
    assert "AL-000001" in text
    assert "Premiebetalande" in text
    assert "45 000 kr" in text  # aktuell månadslön på personen


def test_oversikt_via_forsakringsnummer_markerar_forsakringen(web):
    response = web.client.get("/forsakringar/AL-000003")
    assert response.status_code == 200
    assert "Cecilia Carlsson" in response.text
    assert 'class="is-highlight"' in response.text
    assert "Fribrev" in response.text


def test_varje_sidvisning_loggas_som_lasning_av_personuppgifter(web):
    web.client.get(f"/forsakrade/{ANNA}")
    events = read_events(web, "get_insured_overview")
    assert len(events) == 1
    event = events[0]
    assert (event.outcome, event.actor_type, event.actor_id, event.pii) == ("executed", "human", "karl", True)
    assert event.input == {"personal_id_number": ANNA, "policy_number": None}
    assert event.output is None  # läsresultat loggas inte


def test_loneunderlaget_skiljer_tom_historik_fran_rapporter(web):
    response = web.client.get(f"/forsakrade/{ANNA}/loneunderlag")
    assert response.status_code == 200
    assert "Inget löneunderlag registrerat" in response.text
    assert [e.operation for e in read_events(web)][-2:] == ["get_insured_overview", "get_salary_reports"]


def test_premiehistoriken_visar_rader_och_summa_betalt(web):
    response = web.client.get("/forsakringar/AL-000001/premier")
    assert response.status_code == 200
    assert "21 rader" in response.text  # 2025-01–2026-09
    assert "Fakturerad" in response.text
    assert "Betald" in response.text


def test_premiehistoriken_kan_avgransas_pa_manader(web):
    response = web.client.get("/forsakringar/AL-000001/premier", params={"fran": "2026-01", "till": "2026-03"})
    assert response.status_code == 200
    assert "3 rader" in response.text
    event = read_events(web, "get_premium_history")[-1]
    assert event.input["from_month"] == "2026-01-01"
    assert event.input["to_month"] == "2026-03-01"


def test_okant_forsakringsnummer_ger_404(web):
    response = web.client.get("/forsakringar/AL-999999/premier")
    assert response.status_code == 404
    assert "Ingen försäkring med nummer AL-999999" in response.text


def test_okand_adress_ger_404_sida(web):
    response = web.client.get("/finns-inte")
    assert response.status_code == 404
    assert "Adressen finns inte" in response.text


# --- bara lokalt ---------------------------------------------------------------------------------


def test_annan_vard_an_lokal_nekas(web):
    response = web.client.get("/", headers={"Host": "evil.example"})
    assert response.status_code == 400


def test_standardinstallningarna_ar_lokala_och_demo():
    settings = WebSettings()
    assert settings.allowed_hosts == ("127.0.0.1", "localhost")
    assert settings.database == "demo"
    assert not settings.is_production


def test_ogiltiga_installningar_stoppas():
    with pytest.raises(WebConfigError):
        WebSettings(database="prod")
    with pytest.raises(WebConfigError):
        WebSettings(handler_id="Karl Tengelin")


def test_lakebase_valjs_bara_uttryckligen(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://bestand")
    monkeypatch.delenv("HANDLAGGARE_DB", raising=False)
    assert WebSettings.from_env().database == "demo"
    monkeypatch.setenv("HANDLAGGARE_DB", "lakebase")
    assert WebSettings.from_env().is_production


def test_lakebasevarning_syns_i_sidhuvudet(web):
    web.app.state.settings = WebSettings(database="lakebase", allowed_hosts=("testserver",))
    response = web.client.get("/")
    assert "Lakebase-beståndet: ändringar sparas på riktigt" in response.text


# --- gränsen mot tjänstelagret --------------------------------------------------------------------

WEB_SRC = Path(__file__).resolve().parents[1] / "src" / "web"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_webbkoden_ror_varken_modeller_eller_sessioner():
    """UI:t anropar bara tjänstelagret – även läsningar, eftersom läsningar av personuppgifter loggas."""
    for path in WEB_SRC.rglob("*.py"):
        imports = _imports(path)
        assert not any(name == "models" or name.startswith("models.") for name in imports), path
        assert not any(name.startswith("services.operations") for name in imports), path
        assert not any(name.startswith("sqlalchemy.orm") for name in imports), path
        if path.name != "database.py":  # bara databasvalet skapar motorn
            assert not any(name.startswith("sqlalchemy") for name in imports), path
