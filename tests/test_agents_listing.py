"""Skillkatalogens tabell över körpolicyns skills (Fas 3b-7) – genererad och aktuell."""

import pytest

from agents import Ecosystem
from agents.listing import (
    DEFAULT_PATH,
    END,
    START,
    authorized_agents,
    render_skill_table,
    updated_catalog,
)
from services import AccessRegister, default_registry


def test_katalogen_i_repot_ar_aktuell():
    table = render_skill_table(Ecosystem.load(), default_registry, AccessRegister.load())
    current = DEFAULT_PATH.read_text(encoding="utf-8")
    assert updated_catalog(current, table) == current, (
        "03_skills/skillkatalog.md är inte aktuell – kör python scripts/documentation/list_skills.py"
    )


def test_nekade_skills_har_inga_behoriga_agenter():
    eco = Ecosystem.load()
    assert authorized_agents(eco, "calculate_premium_preview") == ["actuary_agent", "case_handler", "compliance_agent"]
    assert authorized_agents(eco, "correct_premium_transaction") == []  # nekad för teamet
    assert authorized_agents(eco, "set_policy_paid_up") == []  # nekad för agenten


def test_varje_skill_har_en_rad_med_podd():
    eco = Ecosystem.load()
    table = render_skill_table(eco, default_registry, AccessRegister.load())
    for skill in eco.skill_names():
        assert f"| `{skill}` | `{eco.pod_of(skill)}` |" in table


def test_markeringarna_kravs():
    with pytest.raises(ValueError, match="markeringarna"):
        updated_catalog("ingen tabell här", "| x |")
    assert updated_catalog(f"a\n{START}\ngammal\n{END}\nb", "ny") == f"a\n{START}\nny\n{END}\nb"
