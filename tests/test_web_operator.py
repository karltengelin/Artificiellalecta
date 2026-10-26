"""Ledningsytan visar luckor och källor utan PII eller styrskrivningar."""


import json
from dataclasses import replace
from datetime import date

import pytest


@pytest.mark.parametrize("path", ["/central", "/central/team", "/central/kostnader", "/central/underlag"])
def test_operator_views_are_readable_with_real_gaps_and_no_person_data(web, path):
    response = web.client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "Operatörscentral" in response.text
    assert "198505151236" not in response.text and "Anna" not in response.text
    assert 'action="/central' not in response.text
    if path == "/central":
        assert "Ej beräknat" in response.text and "Okänd" in response.text
    if path == "/central/team":
        assert "Körläge okänt" in response.text and "Profil konfigurerad" in response.text


def test_period_cannot_be_used_for_person_lookup_or_arbitrary_time_slicing(web):
    assert web.client.get("/central?month=not-a-month").status_code == 422
    assert web.client.get("/central?month=2026-10-25").status_code == 422
    assert web.client.get("/central?month=2001-01").status_code == 422
    assert web.client.post("/central").status_code == 405


def test_source_failure_never_falls_back_or_leaks_connection_details(web, monkeypatch):
    from web.routes import operator
    def fail(*args): raise RuntimeError("postgresql://private-password@host/database")
    monkeypatch.setattr(operator, "read", fail)
    response = web.client.get("/central")
    assert response.status_code == 200 and "Saknas" in response.text
    assert "private-password" not in response.text
    assert "Ingen annan" in response.text


def test_cost_view_renders_attempts_without_exposing_raw_log_fields(web, tmp_path):
    month = date.today().strftime("%Y-%m")
    log = tmp_path / "calls.jsonl"
    log.write_text(json.dumps({
        "timestamp": month + "-01T00:00:00Z", "outcome": "error", "cost_usd": "0.012345",
        "team": "compliance", "model_ref": "unreviewed:model", "content": {"prompt": "PRIVATE_PROMPT"},
        "error_message": "PRIVATE_ERROR",
    }) + "\n", encoding="utf-8")
    manifest = tmp_path / "sources.json"
    manifest.write_text(json.dumps({"schema_version": 1, "sources": [{
        "source_id": "web-fixture", "path": "calls.jsonl", "kind": "calls",
        "environment_id": "demo", "dataset_ref": "demo:current",
    }]}), encoding="utf-8")
    web.app.state.settings = replace(web.app.state.settings, operator_manifest=manifest)
    response = web.client.get("/central/kostnader")
    assert response.status_code == 200 and "0.012345" in response.text
    assert "Ofullständig täckning" in response.text and "Compliance" in response.text
    assert "PRIVATE_PROMPT" not in response.text and "PRIVATE_ERROR" not in response.text
    assert "unreviewed:model" not in response.text
