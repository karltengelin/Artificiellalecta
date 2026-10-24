"""Tester för skill-registret och den effektiva profilen (Fas 3b-2, harness.md §3–4).

Testregistret har en operation per utfall: utföra, föreslå, endast handläggare,
regelgolv, personuppgifter och en operation utan poddmappning. Det räcker inte
att ett verktyg saknas i listan – testerna anropar det ändå och visar att
operationen aldrig nåddes.
"""

from datetime import date

import pytest
from pydantic import BaseModel

from agents import (
    Ecosystem,
    HarnessError,
    Outcome,
    RunRequest,
    RunRequestError,
    SkillDeniedError,
    SkillInputError,
    SkillRegistry,
    compile_profile,
)
from agents.ecosystem import Limits
from services import (
    AccessRegister,
    Actor,
    MemoryEventLog,
    OperationContext,
    OperationKind,
    OperationRegistry,
    ProductRuleCatalog,
    ServiceLayer,
    default_registry,
    operation,
)
from services.db import AGENT_ROLES


class NoteRef(BaseModel):
    case_ref: str


class NoteInput(BaseModel):
    case_ref: str
    text: str


class Done(BaseModel):
    ok: bool = True


CALLS: list[tuple[str, str, str | None, str | None]] = []
registry = OperationRegistry()


def _called(name, ctx):
    CALLS.append((name, ctx.actor.id, ctx.run_id, ctx.reason))
    return Done()


@operation(name="preview", description="Beräknar", kind=OperationKind.COMPUTE, registry=registry)
def preview(ctx: OperationContext, data: NoteRef) -> Done:
    return _called("preview", ctx)


@operation(name="lookup", description="Läser kund", kind=OperationKind.READ, pii=True, registry=registry)
def lookup(ctx: OperationContext, data: NoteRef) -> Done:
    return _called("lookup", ctx)


@operation(name="file_note", description="Sparar anteckning", kind=OperationKind.WRITE,
           rules=["PR-T-GODKAND"], registry=registry)
def file_note(ctx: OperationContext, data: NoteInput) -> Done:
    return _called("file_note", ctx)


@operation(name="close_case", description="Stänger ärende", kind=OperationKind.WRITE,
           rules=["PR-T-GODKAND"], registry=registry)
def close_case(ctx: OperationContext, data: NoteRef) -> Done:
    return _called("close_case", ctx)


@operation(name="draft_rule_write", description="Skrivning med utkastregel", kind=OperationKind.WRITE,
           rules=["PR-T-UTKAST"], registry=registry)
def draft_rule_write(ctx: OperationContext, data: NoteRef) -> Done:
    return _called("draft_rule_write", ctx)


@operation(name="new_operation", description="Ny, ännu omappad", kind=OperationKind.READ, registry=registry)
def new_operation(ctx: OperationContext, data: NoteRef) -> Done:
    return _called("new_operation", ctx)


REGISTER = {
    "preview": "AGENT",
    "lookup": "AGENT",
    "file_note": "APPROVAL",
    "close_case": "HUMAN_ONLY",
    "draft_rule_write": "AGENT",  # registret öppnar – regelgolvet stänger
    "new_operation": "AGENT",  # öppen i registret men utan poddmappning
}

LIMITS = {
    "max_steps": 20, "max_tool_calls": 30, "max_cost_usd": 2.0,
    "max_output_tokens": 4000, "max_context_bytes": 120000, "max_wall_seconds": 600,
}

POLICY = {
    "schema_version": 1,
    "policy_id": "test",
    "team_ids": ["t1", "t2"],
    "defaults": {"allowed_effects": ["read", "compute", "write"], "limits": LIMITS},
    "pods": {
        "calc": {"owner_team": "t1", "mountable_by": ["t1"], "pii": False, "allowed_effects": ["compute"],
                 "skills": {"preview": {"service_operation": "preview"}}},
        "cust": {"owner_team": "t1", "mountable_by": ["t1"], "pii": True, "allowed_effects": ["read"],
                 "skills": {"lookup": {"service_operation": "lookup"}}},
        "notes": {"owner_team": "t1", "mountable_by": ["t1"], "pii": False, "allowed_effects": ["write"],
                  "skills": {"file_note": {"service_operation": "file_note"},
                             "close_case": {"service_operation": "close_case"},
                             "draft_rule_write": {"service_operation": "draft_rule_write"}}},
    },
    "teams": {"t1": {"lead": "lead", "mandate": "Testteam", "pods": ["calc", "cust", "notes"],
                     "allowed_effects": ["read", "compute", "write"], "limits": {"max_steps": 12}}},
    "agents": {
        "lead": {"name": "Ledare", "team": "t1", "instruction": "02_system/agenter/handlaggaragent.md",
                 "model_role": "standard", "pods": ["calc", "cust", "notes"],
                 "allowed_effects": ["read", "compute", "write"]},
        "specialist": {"name": "Specialist", "team": "t1", "instruction": "02_system/agenter/handlaggaragent.md",
                       "model_role": "fast", "pods": ["calc"], "allowed_effects": ["compute"]},
    },
    "delegation": {"enabled": False, "max_depth": 2, "max_children": 3,
                   "root_limits": {"max_steps": 60, "max_tool_calls": 90, "max_cost_usd": 5.0,
                                   "max_wall_seconds": 900}},
}

AGENT_CTX = OperationContext(actor=Actor.agent("lead", team="t1"), run_id="run-1")
NO_ROLE = "personuppgifter: tjänstelagret ansluter inte med teamets begränsade databasroll (harness.md §5.1)"


@pytest.fixture
def setup(tmp_path):
    for rule_id, status in (("PR-T-GODKAND", "Godkänd"), ("PR-T-UTKAST", "Utkast")):
        (tmp_path / f"{rule_id}-x.md").write_text(f"> **Granskningsstatus:** {status}\n", encoding="utf-8")
    CALLS.clear()
    eco = Ecosystem.from_dict(POLICY)
    service = ServiceLayer(
        registry=registry, register=AccessRegister.from_dict(REGISTER),
        rules=ProductRuleCatalog(tmp_path), events=MemoryEventLog(),
    )
    skills = SkillRegistry.build(eco, registry)
    return eco, skills, service


def profile_for(setup, **kwargs):
    eco, skills, service = setup
    if "request" not in kwargs and "agent_id" not in kwargs:
        kwargs["agent_id"] = "lead"
    return compile_profile(eco, skills, service, **kwargs)


def request(**overrides):
    return RunRequest(**{"task_id": "task-1", "target_team": "t1", "goal": "Testa", **overrides})


class TestUtfall:
    def test_varje_skill_far_ratt_utfall(self, setup):
        profile = profile_for(setup)
        outcomes = {d.skill: d.outcome for d in profile.decisions}
        assert outcomes == {
            "preview": Outcome.EXECUTE,
            "file_note": Outcome.PROPOSE,
            "close_case": Outcome.HIDDEN,
            "draft_rule_write": Outcome.HIDDEN,
            "lookup": Outcome.HIDDEN,
        }

    def test_skalen_for_dolda_verktyg(self, setup):
        profile = profile_for(setup)
        assert any("HUMAN_ONLY i åtkomstregistret" in r for r in profile.decision("close_case").reasons)
        assert any("PR-T-UTKAST" in r for r in profile.decision("draft_rule_write").reasons)
        assert profile.decision("lookup").reasons == ("personuppgifter kräver execution_scope i uppdraget", NO_ROLE)

    def test_pii_forblir_dold_aven_med_scope_utan_databasroll(self, setup):
        profile = profile_for(setup, request=request(execution_scope_ref="scope-1"))
        assert profile.decision("lookup").reasons == (NO_ROLE,)

    def test_pii_oppnas_med_scope_och_teamets_databasroll(self, setup, monkeypatch):
        monkeypatch.setitem(AGENT_ROLES, "t1", ("agent_t1", "AGENT_T1_DATABASE_URL"))
        _, _, service = setup
        service.agent_role = "agent_t1"  # i drift: services.db.agent_service_layer
        assert profile_for(setup).decision("lookup").outcome == Outcome.HIDDEN  # utan scope
        profile = profile_for(setup, request=request(execution_scope_ref="scope-1"))
        assert profile.decision("lookup").outcome == Outcome.EXECUTE

    def test_ett_annat_teams_roll_oppnar_inte(self, setup, monkeypatch):
        monkeypatch.setitem(AGENT_ROLES, "t1", ("agent_t1", "AGENT_T1_DATABASE_URL"))
        _, _, service = setup
        service.agent_role = "agent_forsakring"
        profile = profile_for(setup, request=request(execution_scope_ref="scope-1"))
        assert profile.decision("lookup").reasons == (NO_ROLE,)

    def test_omappad_operation_blir_inget_verktyg(self, setup):
        profile = profile_for(setup)
        assert profile.unmapped_operations == ("new_operation",)
        assert "new_operation" not in {t.name for t in profile.tool_specs()}
        with pytest.raises(SkillDeniedError, match="Okänd skill"):
            profile.require("new_operation")

    def test_specialist_far_bara_sina_poddar(self, setup):
        profile = profile_for(setup, agent_id="specialist")
        assert [d.skill for d in profile.visible()] == ["preview"]
        assert "podden 'notes' finns inte i agentens poddar" in profile.decision("file_note").reasons

    def test_forklaringen_listar_alla_skal(self, setup):
        text = profile_for(setup).explain()
        assert "preview" in text and "föreslå (godkännande)" in text
        assert "endast handläggare i tjänstelagret" in text
        assert "new_operation" in text


class TestVerktygsschema:
    def test_bara_oppna_verktyg_visas(self, setup):
        assert [t.name for t in profile_for(setup).tool_specs()] == ["file_note", "preview"]

    def test_omslaget_saknar_identitetsfalt_och_kraver_motivering_vid_skrivning(self, setup):
        specs = {t.name: t for t in profile_for(setup).tool_specs()}
        note = specs["file_note"].parameters
        assert note["properties"].keys() == {"data", "reason"}
        assert note["additionalProperties"] is False
        assert note["properties"]["reason"]["type"] == "string"
        assert "godkännandekö" in specs["file_note"].description
        assert "godkännandekö" not in specs["preview"].description

    def test_riktiga_scheman_har_inga_syskon_till_ref(self):
        """OpenAI:s strikta läge godtar inte nyckelord bredvid $ref."""
        eco = Ecosystem.load()
        offenders = []

        def walk(node, path):
            if isinstance(node, dict):
                if "$ref" in node and len(node) > 1:
                    offenders.append(path)
                for key, value in node.items():
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    walk(value, f"{path}[{i}]")

        for skill in SkillRegistry.build(eco, default_registry):
            walk(skill.tool_spec().parameters, skill.name)
        assert offenders == []


class TestAnrop:
    def test_utfora_gar_via_tjanstelagret_som_agent(self, setup):
        _, _, service = setup
        skill = profile_for(setup).require("preview")
        result = skill.invoke(service, AGENT_CTX, {"data": {"case_ref": "C-1"}, "reason": None})
        assert skill.result_payload(result) == {"status": "done", "output": {"ok": True}}
        assert CALLS == [("preview", "lead", "run-1", None)]

    def test_foreslag_hamnar_i_kon_och_andrar_ingenting(self, setup):
        _, _, service = setup
        skill = profile_for(setup).require("file_note")
        result = skill.invoke(
            service, AGENT_CTX, {"data": {"case_ref": "C-1", "text": "Ny lön"}, "reason": "Kunden ringde"}
        )
        payload = skill.result_payload(result)
        assert payload["status"] == "pending_approval" and payload["approval_id"] == result.approval_id
        assert "Ingenting är ändrat" in payload["note"]
        assert [c for c in CALLS if c[0] == "file_note"] == []  # provkörd, inte utförd
        (pending,) = service.approvals.list("pending")
        assert (pending.proposed_by, pending.reason, pending.run_id) == ("lead", "Kunden ringde", "run-1")

    @pytest.mark.parametrize("skill", ["close_case", "draft_rule_write", "lookup", "hittepa", "new_operation"])
    def test_dolt_eller_paahittat_verktyg_nas_aldrig(self, setup, skill):
        with pytest.raises(SkillDeniedError):
            profile_for(setup).require(skill)
        assert CALLS == []

    @pytest.mark.parametrize(
        "arguments, message",
        [
            ({"data": {"case_ref": "C-1", "text": "x"}, "reason": "r", "actor": "human"}, "okända fält actor"),
            ({"data": {"case_ref": "C-1", "text": "x", "approved_by": "karl"}, "reason": "r"},
             "okända fält data.approved_by"),
            ({"data": {"case_ref": "C-1", "text": "x"}}, "ogiltiga argument"),
            ({"data": {"case_ref": "C-1", "text": "x"}, "reason": ""}, "ogiltiga argument"),
            ({"data": {"case_ref": "C-1"}, "reason": "r"}, "ogiltiga argument"),
            ("inte ett objekt", "ska vara ett objekt"),
        ],
    )
    def test_ogiltiga_argument_nekas_fore_tjanstelagret(self, setup, arguments, message):
        _, _, service = setup
        skill = profile_for(setup).require("file_note")
        with pytest.raises(SkillInputError, match=message):
            skill.invoke(service, AGENT_CTX, arguments)
        assert service.approvals.list("pending") == [] and CALLS == []

    def test_skill_kor_aldrig_som_handlaggare(self, setup):
        _, _, service = setup
        skill = profile_for(setup).require("preview")
        with pytest.raises(HarnessError, match="bara för agenter"):
            skill.invoke(service, OperationContext(actor=Actor.human("karl")), {"data": {"case_ref": "C-1"},
                                                                               "reason": None})
        assert CALLS == []


class TestUppdrag:
    def test_uppdrag_kan_neka_och_smalna_av(self, setup):
        profile = profile_for(setup, request=request(deny_skills=("preview",),
                                                     allowed_effects=frozenset({OperationKind.COMPUTE})))
        assert profile.visible() == []
        assert "nekad i uppdraget" in profile.decision("preview").reasons
        assert "sidoeffekten write är inte tillåten i uppdraget" in profile.decision("file_note").reasons

    def test_uppdrag_kan_sanka_men_inte_hoja_granser(self, setup):
        assert profile_for(setup, request=request(limits=Limits(max_steps=5))).limits.max_steps == 5
        with pytest.raises(RunRequestError, match="bara sänka"):
            profile_for(setup, request=request(limits=Limits(max_steps=13)))

    def test_uppdrag_med_okand_nekad_skill_stoppas(self, setup):
        with pytest.raises(RunRequestError, match="okända skills"):
            profile_for(setup, request=request(deny_skills=("prevew",)))

    def test_uppdrag_gar_till_ledande_agent(self, setup):
        assert profile_for(setup, request=request()).agent_id == "lead"
        with pytest.raises(RunRequestError, match="ledande agent 'lead'"):
            profile_for(setup, request=request(agent="specialist"))
        with pytest.raises(RunRequestError, match="ingen aktiv profil"):
            profile_for(setup, request=request(target_team="t2"))

    def test_uppdragets_falt_ar_stangda(self):
        with pytest.raises(ValueError):
            RunRequest(task_id="t", target_team="t1", goal="g", actor="human")


class TestRepoPolicyn:
    """Handläggaragenten med de riktiga registren – före och efter PR-ITP1 v1.0:s giltighetsdag."""

    def profile(self, day):
        eco = Ecosystem.load()
        service = ServiceLayer(events=MemoryEventLog(), rules=ProductRuleCatalog(today=day))
        return compile_profile(eco, SkillRegistry.build(eco, default_registry), service, agent_id="case_handler")

    @pytest.mark.parametrize("day, level", [(date(2026, 10, 31), "HUMAN_ONLY"), (date(2026, 11, 1), "APPROVAL")])
    def test_lonunderlag_foljer_regelstatus_men_ar_dolt_som_pii(self, day, level):
        decision = self.profile(day).decision("register_salary_report")
        assert decision.service_level.value == level
        assert decision.outcome == Outcome.HIDDEN

    @pytest.mark.parametrize("day", [date(2026, 10, 31), date(2026, 11, 1)])
    def test_bara_premieforhandsberakningen_ar_oppen(self, day):
        profile = self.profile(day)
        assert [d.skill for d in profile.visible()] == ["calculate_premium_preview"]
        reasons = profile.decision("correct_premium_transaction").reasons
        assert "nekad för teamet 'forsakring'" in reasons
        assert "nekad för agenten" in profile.decision("set_policy_paid_up").reasons

    def test_versionsbild(self):
        snap = self.profile(date(2026, 11, 1)).snapshot
        assert snap.policy_id == "harness-v1" and snap.rules_date == date(2026, 11, 1)
        assert all(len(h) == 64 for h in (snap.ecosystem_sha256, snap.access_register_sha256,
                                         snap.instruction_sha256, snap.product_rules_sha256))

    def test_premieforhandsberakning_hela_vagen(self, insurance_db):
        eco = Ecosystem.load()
        service = ServiceLayer(session_factory=insurance_db.session_factory)
        profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), service,
                                  agent_id="case_handler")
        skill = profile.require("calculate_premium_preview")
        ctx = OperationContext(actor=Actor.agent("case_handler", team="forsakring"), run_id="run-2")
        result = skill.invoke(
            service, ctx, {"data": {"monthly_salary_sek": "80000", "period_month": "2026-03-01",
                                    "birth_date": None}, "reason": None},
        )
        payload = skill.result_payload(result)
        assert payload["status"] == "done"
        assert payload["output"]["total_premium_sek"] == "10708.13"  # samma som tjänstelagrets test
