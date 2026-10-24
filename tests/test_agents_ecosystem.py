"""Tester för körpolicyn ecosystem.yaml (Fas 3b-1, harness.md §3).

Policyn ska stoppa vid start när något inte stämmer – hellre ingen profil än en
som delvis gäller. Testerna bygger små policyer ur en giltig bas och ändrar en sak.
"""

import copy

import pytest
from pydantic import BaseModel

from agents import Ecosystem, EcosystemConfigError, Limits
from services import (
    OperationContext,
    OperationKind,
    OperationRegistry,
    default_registry,
    operation,
)


class Ref(BaseModel):
    ref: str


class Done(BaseModel):
    ok: bool = True


registry = OperationRegistry()


@operation(name="preview", description="Beräkning", kind=OperationKind.COMPUTE, registry=registry)
def preview(ctx: OperationContext, data: Ref) -> Done:
    return Done()


@operation(name="lookup", description="Läsning", kind=OperationKind.READ, pii=True, registry=registry)
def lookup(ctx: OperationContext, data: Ref) -> Done:
    return Done()


@operation(name="file_note", description="Skrivning", kind=OperationKind.WRITE, registry=registry)
def file_note(ctx: OperationContext, data: Ref) -> Done:
    return Done()


LIMITS = {
    "max_steps": 20, "max_tool_calls": 30, "max_cost_usd": 2.0,
    "max_output_tokens": 4000, "max_context_bytes": 120000, "max_wall_seconds": 600,
}

BASE = {
    "schema_version": 1,
    "policy_id": "test",
    "team_ids": ["t1", "t2"],
    "defaults": {"allowed_effects": ["read", "compute", "write"], "limits": LIMITS},
    "pods": {
        "calc": {
            "owner_team": "t1", "mountable_by": ["t1", "t2"], "pii": False,
            "allowed_effects": ["compute"], "skills": {"preview": {"service_operation": "preview"}},
        },
        "cust": {
            "owner_team": "t1", "mountable_by": ["t1"], "pii": True,
            "allowed_effects": ["read", "write"],
            "skills": {"lookup": {"service_operation": "lookup"}, "file_note": {"service_operation": "file_note"}},
        },
    },
    "teams": {
        "t1": {
            "lead": "a1", "mandate": "Testteam", "pods": ["calc", "cust"],
            "allowed_effects": ["read", "compute", "write"], "delegates_to": ["t2"],
            "limits": {"max_steps": 12, "max_cost_usd": 0.5},
        },
    },
    "agents": {
        "a1": {
            "name": "Agent 1", "team": "t1", "instruction": "02_system/agenter/handlaggaragent.md",
            "model_role": "standard", "pods": ["calc", "cust"], "allowed_effects": ["read", "compute", "write"],
            "limits": {"max_steps": 10},
        },
    },
    "delegation": {
        "enabled": False, "max_depth": 2, "max_children": 3,
        "root_limits": {"max_steps": 60, "max_tool_calls": 90, "max_cost_usd": 5.0, "max_wall_seconds": 900},
    },
}


def changed(**path_values):
    """En kopia av BASE där nyckelvägar som 'agents.a1.pods' får nya värden."""
    data = copy.deepcopy(BASE)
    for path, value in path_values.items():
        node = data
        *parents, last = path.split("__")
        for key in parents:
            node = node[key]
        node[last] = value
    return data


def test_basen_ar_giltig():
    eco = Ecosystem.from_dict(BASE)
    eco.validate_against_registry(registry)
    assert eco.skill_names() == ["file_note", "lookup", "preview"]
    assert eco.pod_of("lookup") == "cust"


class TestRepoPolicyn:
    def test_laddas_mot_riktiga_register_roller_och_instruktioner(self):
        eco = Ecosystem.load()
        assert eco.checksum and len(eco.checksum) == 64
        assert eco.teams["forsakring"].lead == "case_handler"
        assert set(eco.team_ids) == {
            "forsakring", "kommunikation", "kapital", "aktuarie", "compliance", "ekonomi", "utveckling"
        }

    def test_handlaggarens_granser_enligt_harness_6_3(self):
        assert Ecosystem.load().agent_limits("case_handler") == Limits(
            max_steps=12, max_tool_calls=18, max_cost_usd=0.50,
            max_output_tokens=1500, max_context_bytes=40000, max_wall_seconds=180,
        )

    def test_omappade_operationer_ar_stangda(self):
        unmapped = Ecosystem.load().unmapped_operations(default_registry)
        assert "list_employers" in unmapped and "enroll_insured_person" in unmapped
        assert "calculate_premium_preview" not in unmapped


class TestStrukturStoppas:
    @pytest.mark.parametrize(
        "data, message",
        [
            (changed(agents__a1__pods=["calc", "cust", "extra"]), "poddar utöver teamets"),
            (changed(teams__t1__pods=["calc"]), "poddar utöver teamets: cust"),
            (changed(agents__a1__allowed_effects=["read"], teams__t1__allowed_effects=["compute"]),
             "sidoeffekter utöver teamets: read"),
            (changed(agents__a1__delegates_to=["t1"]), "delegeringsmål utöver teamets"),
            (changed(agents__a1__limits={"max_steps": 13}), "gränser över teamets"),
            (changed(agents__a1__limits={"max_cost_usd": 0.6}), "max_cost_usd 0.6 > 0.5"),
            (changed(teams__t1__limits={"max_tool_calls": 31}), "gränser över de globala taken"),
            (changed(defaults__limits={"max_steps": 20}), "defaults.limits saknar"),
            (changed(pods__calc__skills={"lookup": {"service_operation": "preview"}}),
             "finns i både"),
            (changed(pods__calc__skills={"preview2": {"service_operation": "lookup"}}),
             "mappad två gånger"),
            (changed(defaults__allowed_effects=["read", "external"]), "external kan inte öppnas"),
            (changed(teams__t1__deny_skills=["lokup"]), "nekar okänd skill 'lokup'"),
            (changed(pods__cust__mountable_by=["t2"]), "får inte monteras på teamet"),
            (changed(pods__calc__owner_team="okant"), "okänt ägarteam"),
            (changed(teams__t1__lead="saknas"), "ledande agent 'saknas' finns inte"),
            (changed(teams__t1__delegates_to=["t1"]), "ogiltigt delegeringsmål"),
            (changed(agents__a1__team="t2"), "har ingen aktiv profil"),
            (changed(team_ids=["t1", "t1", "t2"]), "dubbletter"),
            (changed(agents={**BASE["agents"], "Agent-2": BASE["agents"]["a1"]}), "snake_case"),
        ],
    )
    def test_ogiltig_policy(self, data, message):
        with pytest.raises(EcosystemConfigError, match=message):
            Ecosystem.from_dict(data)

    def test_okant_falt_stoppas(self):
        with pytest.raises(EcosystemConfigError, match="Extra inputs"):
            Ecosystem.from_dict(changed(agents__a1__actor="human"))

    def test_dubbel_yaml_nyckel_stoppas(self):
        text = "schema_version: 1\npolicy_id: a\npolicy_id: b\n"
        with pytest.raises(EcosystemConfigError, match="dubbel nyckel 'policy_id'"):
            Ecosystem.from_yaml(text)


class TestMotTjanstelagret:
    def test_okand_operation(self):
        eco = Ecosystem.from_dict(changed(pods__calc__skills={"preview": {"service_operation": "previw"}}))
        with pytest.raises(EcosystemConfigError, match="operationen 'previw' finns inte"):
            eco.validate_against_registry(registry)

    def test_pii_operation_i_podd_utan_pii(self):
        eco = Ecosystem.from_dict(changed(pods__cust__pii=False))
        with pytest.raises(EcosystemConfigError, match="personuppgifter, podden är utan PII"):
            eco.validate_against_registry(registry)

    def test_skrivning_i_podd_som_bara_far_lasa(self):
        eco = Ecosystem.from_dict(changed(pods__cust__allowed_effects=["read"]))
        with pytest.raises(EcosystemConfigError, match="operationen är write, podden tillåter read"):
            eco.validate_against_registry(registry)

    def test_okand_modellroll(self):
        eco = Ecosystem.from_dict(changed(agents__a1__model_role="genius"))
        with pytest.raises(EcosystemConfigError, match="Okänd modellroll"):
            eco.validate_model_roles(["fast", "standard", "deep"])


class TestInstruktioner:
    def write(self, root, text):
        path = root / "02_system" / "agenter" / "agent.md"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")

    def test_team_i_instruktionen_maste_stamma(self, tmp_path):
        self.write(tmp_path, "| **Team** | Annat (`t2`) – se … |\n")
        eco = Ecosystem.from_dict(changed(agents__a1__instruction="02_system/agenter/agent.md"))
        with pytest.raises(EcosystemConfigError, match="anger teamet 't2', policyn 't1'"):
            eco.validate_instructions(tmp_path)

    def test_instruktion_utanfor_agentmappen(self, tmp_path):
        self.write(tmp_path, "| **Team** | Test (`t1`) |\n")
        eco = Ecosystem.from_dict(changed(agents__a1__instruction="02_system/agenter/../../.env"))
        with pytest.raises(EcosystemConfigError, match="ska ligga i 02_system/agenter/"):
            eco.validate_instructions(tmp_path)

    def test_saknad_instruktion(self, tmp_path):
        eco = Ecosystem.from_dict(changed(agents__a1__instruction="02_system/agenter/saknas.md"))
        with pytest.raises(EcosystemConfigError, match="finns inte"):
            eco.validate_instructions(tmp_path)


def test_granser_kan_bara_sankas():
    top = Limits(max_steps=12, max_cost_usd=0.5)
    assert top.narrowed(Limits(max_steps=20, max_tool_calls=5)) == Limits(
        max_steps=12, max_cost_usd=0.5, max_tool_calls=5
    )
    assert Limits(max_steps=13).exceeding(top) == ["max_steps 13 > 12"]
