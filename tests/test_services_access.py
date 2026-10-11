"""Tester för åtkomstregistret, golven och produktregelstatus (tjänstelager.md §4, B-028)."""

from datetime import date

import pytest
from pydantic import BaseModel

from services import (
    AccessRegister,
    AgentAccess,
    OperationContext,
    OperationKind,
    OperationRegistry,
    ProductRuleCatalog,
    RuleStatus,
    ServiceConfigError,
    default_registry,
    effective_access,
    operation,
)


class Empty(BaseModel):
    pass


def write_rule(directory, rule_id, status):
    (directory / f"{rule_id}-test.md").write_text(
        f"# {rule_id} – test\n\n> **Version:** 0.1 | **Granskningsstatus:** {status} | **Ägare:** Operatören\n",
        encoding="utf-8",
    )


@pytest.fixture
def rules(tmp_path):
    write_rule(tmp_path, "PR-T-001", "Utkast")
    write_rule(tmp_path, "PR-T-002", "Godkänd")
    write_rule(tmp_path, "PR-T-003", "Ersatt")
    return ProductRuleCatalog(tmp_path)


def make_op(kind, rules=(), name="op"):
    registry = OperationRegistry()

    @operation(name=name, description="test", kind=kind, rules=rules, registry=registry)
    def op(ctx: OperationContext, data: Empty) -> Empty:
        return Empty()

    return registry.get(name)


def decide(kind, level, rule_ids, rules):
    op = make_op(kind, rule_ids)
    register = AccessRegister.from_dict({"op": level} if level else {})
    return effective_access(op, register, rules)


class TestGolv:
    def test_saknas_i_registret_blir_endast_handlaggare(self, rules):
        d = decide(OperationKind.READ, None, (), rules)
        assert d.effective == AgentAccess.HUMAN_ONLY
        assert d.registered is None
        assert "saknas i åtkomstregistret" in d.reasons

    def test_lasning_kan_oppnas_for_agent(self, rules):
        assert decide(OperationKind.READ, "AGENT", (), rules).effective == AgentAccess.AGENT

    def test_registret_kan_skarpa(self, rules):
        assert decide(OperationKind.READ, "HUMAN_ONLY", (), rules).effective == AgentAccess.HUMAN_ONLY

    def test_external_kraver_minst_godkannande(self, rules):
        d = decide(OperationKind.EXTERNAL, "AGENT", ("PR-T-002",), rules)
        assert d.effective == AgentAccess.APPROVAL

    def test_skrivning_med_utkastregel_blir_endast_handlaggare(self, rules):
        d = decide(OperationKind.WRITE, "AGENT", ("PR-T-001",), rules)
        assert d.effective == AgentAccess.HUMAN_ONLY
        assert any("PR-T-001 (utkast)" in r for r in d.reasons)

    def test_skrivning_med_ersatt_eller_okand_regel_blir_endast_handlaggare(self, rules):
        assert decide(OperationKind.WRITE, "APPROVAL", ("PR-T-003",), rules).effective == AgentAccess.HUMAN_ONLY
        assert decide(OperationKind.WRITE, "APPROVAL", ("PR-FINNS-EJ",), rules).effective == AgentAccess.HUMAN_ONLY

    def test_skrivning_utan_regel_blir_endast_handlaggare(self, rules):
        d = decide(OperationKind.WRITE, "AGENT", (), rules)
        assert d.effective == AgentAccess.HUMAN_ONLY
        assert "skrivande operation utan produktregel" in d.reasons

    def test_skrivning_med_godkand_regel_foljer_registret(self, rules):
        assert decide(OperationKind.WRITE, "APPROVAL", ("PR-T-002",), rules).effective == AgentAccess.APPROVAL
        assert decide(OperationKind.WRITE, "AGENT", ("PR-T-002",), rules).effective == AgentAccess.AGENT

    def test_en_ej_godkand_regel_racker_for_att_stanga(self, rules):
        d = decide(OperationKind.WRITE, "AGENT", ("PR-T-002", "PR-T-001"), rules)
        assert d.effective == AgentAccess.HUMAN_ONLY

    def test_berakning_paverkas_inte_av_regelstatus(self, rules):
        assert decide(OperationKind.COMPUTE, "AGENT", ("PR-T-001",), rules).effective == AgentAccess.AGENT


class TestRegistret:
    def test_ogiltig_niva_ger_fel(self):
        with pytest.raises(ServiceConfigError, match="Ogiltig nivå"):
            AccessRegister.from_dict({"op": "MAYBE"})

    def test_nivan_ar_skiftlagesokanslig(self):
        assert AccessRegister.from_dict({"op": "approval"}).levels["op"] == AgentAccess.APPROVAL

    def test_okand_operation_i_registret_ger_fel(self):
        registry = OperationRegistry()
        with pytest.raises(ServiceConfigError, match="okända operationer: stavfel_op"):
            AccessRegister.from_dict({"stavfel_op": "AGENT"}).validate_against(registry)

    def test_registret_i_repot_ar_giltigt(self):
        register = AccessRegister.load()
        register.validate_against(default_registry)
        assert all(isinstance(level, AgentAccess) for level in register.levels.values())


class TestProduktregler:
    def test_status_lases_ur_rubriken(self, rules):
        assert rules.status("PR-T-001") == RuleStatus.UTKAST
        assert rules.status("PR-T-002") == RuleStatus.GODKAND
        assert rules.status("PR-T-003") == RuleStatus.ERSATT
        assert rules.status("PR-SAKNAS") == RuleStatus.OKAND

    def test_id_matchar_inte_langre_id(self, tmp_path):
        write_rule(tmp_path, "PR-T-0010", "Godkänd")
        assert ProductRuleCatalog(tmp_path).status("PR-T-001") == RuleStatus.OKAND

    def test_refresh_laser_om_andrad_status(self, tmp_path):
        write_rule(tmp_path, "PR-T-001", "Utkast")
        catalog = ProductRuleCatalog(tmp_path)
        assert catalog.status("PR-T-001") == RuleStatus.UTKAST
        write_rule(tmp_path, "PR-T-001", "Godkänd")
        catalog.refresh()
        assert catalog.status("PR-T-001") == RuleStatus.GODKAND

    def test_regelpaket_specificerat_men_inte_infort(self, tmp_path):
        (tmp_path / "README.md").write_text("> **Paket:** PR-X v1.0\n", encoding="utf-8")
        (tmp_path / "PR-X-001-a.md").write_text(
            "> **Status:** Specificerad tillämpning för simuleringen; införande separat.\n", encoding="utf-8"
        )
        catalog = ProductRuleCatalog(tmp_path)
        assert catalog.status("PR-X-001") == RuleStatus.SPECIFICERAD
        assert catalog.adoption_decision is None

    def test_infort_paket_gor_reglerna_godkanda_utom_ersatta(self, tmp_path):
        (tmp_path / "README.md").write_text(
            "> **Paket:** PR-X v1.0 | **Införandebeslut:** B-031 | **Gäller från:** 2026-11-01\n", encoding="utf-8"
        )
        (tmp_path / "PR-X-001-a.md").write_text("> **Status:** Specificerad tillämpning.\n", encoding="utf-8")
        (tmp_path / "PR-X-002-b.md").write_text("> **Status:** Ersatt av PR-X-001.\n", encoding="utf-8")
        catalog = ProductRuleCatalog(tmp_path, today=date(2026, 11, 1))
        assert catalog.adoption_decision == "B-031"
        assert catalog.status("PR-X-001") == RuleStatus.GODKAND
        assert catalog.status("PR-X-002") == RuleStatus.ERSATT

    def test_infort_paket_med_senare_giltighetsdag_ar_kommande(self, tmp_path):
        (tmp_path / "README.md").write_text(
            "> **Paket:** PR-X v1.0 | **Införandebeslut:** B-031 | **Gäller från:** 2026-11-01\n", encoding="utf-8"
        )
        (tmp_path / "PR-X-001-a.md").write_text(
            "> **Filversion:** 1.0 | **Paket:** PR-X v1.0\n> **Status:** Specificerad.\n", encoding="utf-8"
        )
        catalog = ProductRuleCatalog(tmp_path, today=date(2026, 10, 31))
        assert catalog.status("PR-X-001") == RuleStatus.KOMMANDE
        d = decide(OperationKind.WRITE, "APPROVAL", ("PR-X-001",), catalog)
        assert d.effective == AgentAccess.HUMAN_ONLY
        assert any("PR-X-001 (kommande, gäller från 2026-11-01)" in r for r in d.reasons)

    def test_regelstatus_for_handelseloggen(self, tmp_path):
        (tmp_path / "README.md").write_text("> **Paket:** PR-X v1.0 | **Dokumentdatum:** 2026-10-11\n", encoding="utf-8")
        (tmp_path / "PR-X-001-a.md").write_text(
            "> **Filversion:** 1.0 | **Paket:** PR-X v1.0\n> **Status:** Specificerad.\n", encoding="utf-8"
        )
        catalog = ProductRuleCatalog(tmp_path)
        assert catalog.package == "PR-X v1.0"
        assert catalog.describe(["PR-X-001"]) == "Regelstatus: PR-X-001 v1.0 specificerad; paket PR-X v1.0 ej infört"

    def test_specificerad_regel_stanger_skrivning_for_agenter(self, tmp_path):
        (tmp_path / "PR-X-001-a.md").write_text("> **Status:** Specificerad.\n", encoding="utf-8")
        d = decide(OperationKind.WRITE, "AGENT", ("PR-X-001",), ProductRuleCatalog(tmp_path))
        assert d.effective == AgentAccess.HUMAN_ONLY
        assert any("PR-X-001 (specificerad)" in r for r in d.reasons)

    def test_reglerna_i_repot_har_kanda_statusvarden(self):
        # Formatet ägs av delprojekt 4 – testet larmar om det ändras så att tjänstelagret inte kan läsa det
        catalog = ProductRuleCatalog()
        rule_files = sorted(catalog.rules_dir.glob("PR-*.md"))
        assert rule_files, "inga produktregler hittades"
        for path in rule_files:
            rule_id = "-".join(path.stem.split("-")[:3])
            assert catalog.status(rule_id) != RuleStatus.OKAND, path.name
