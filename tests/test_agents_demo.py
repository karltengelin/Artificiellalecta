"""Demokörningen som röktestet använder (Fas 3b-8) – här mot FakeProvider, utan nätverk."""

from agents.demo import DEMO_PERSON, demo_run
from ai.providers.fake import FakeProvider, text_result, tool_call_result
from tests.test_agents_loop import ai_client

OVERVIEW = {"data": {"personal_id_number": DEMO_PERSON, "policy_number": None}, "reason": None}
PREVIEW = {"data": {"monthly_salary_sek": "45000", "period_month": "2026-09-01", "birth_date": None},
           "reason": None}


def test_demokorningen_gar_hela_vagen_och_andrar_ingenting(tmp_path):
    fake = FakeProvider([
        tool_call_result("get_insured_overview", OVERVIEW),
        tool_call_result("calculate_premium_preview", PREVIEW, call_id="call_2"),
        text_result("Premien blir 2 025,00 kr för september 2026, enligt översikten och förhandsberäkningen."),
    ])
    result = demo_run(ai_client(fake), journal_dir=tmp_path, run_id="demo-1")
    assert result.ok, result.checks
    assert result.proposals == 0
    assert (tmp_path / "demo-1.jsonl").exists()
    # Bara läsning och beräkning – skrivverktygen visas inte för modellen
    tools = {t.name for t in fake.requests[0].tools}
    assert "calculate_premium_preview" in tools and "get_insured_overview" in tools
    assert "register_salary_report" not in tools


def test_kontrollerna_fangar_fel_premie(tmp_path):
    fake = FakeProvider([
        tool_call_result("calculate_premium_preview", PREVIEW),
        text_result("Premien blir 3 000 kr."),
    ])
    result = demo_run(ai_client(fake), journal_dir=tmp_path, run_id="demo-2")
    failed = [label for label, passed, _ in result.checks if not passed]
    assert failed == ["läsning ur beståndet", "premien i svaret"]
