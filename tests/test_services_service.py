"""Tester för ServiceLayer: aktörer, nekad åtkomst, godkännande och händelselogg (B-028)."""

from contextlib import contextmanager

import pytest
from pydantic import BaseModel

from services import (
    AccessDeniedError,
    AccessRegister,
    Actor,
    ApprovalError,
    InvalidInputError,
    MemoryEventLog,
    MissingReasonError,
    OperationContext,
    OperationKind,
    OperationRegistry,
    ProductRuleCatalog,
    ServiceConfigError,
    ServiceLayer,
    UnknownOperationError,
    operation,
)


class PolicyRef(BaseModel):
    policy_number: str


class SalaryChange(BaseModel):
    policy_number: str
    monthly_salary_sek: int


class Done(BaseModel):
    ok: bool = True


CALLS: list[str] = []

registry = OperationRegistry()


@operation(name="get_overview", description="Läser översikt", kind=OperationKind.READ, pii=True, registry=registry)
def get_overview(ctx: OperationContext, data: PolicyRef) -> Done:
    CALLS.append("get_overview")
    return Done()


@operation(name="preview_premium", description="Förhandsberäkning", kind=OperationKind.COMPUTE, registry=registry)
def preview_premium(ctx: OperationContext, data: PolicyRef) -> Done:
    CALLS.append("preview_premium")
    return Done()


@operation(
    name="register_salary_change", description="Ny lön", kind=OperationKind.WRITE,
    rules=["PR-T-GODKAND"], pii=True, registry=registry,
)
def register_salary_change(ctx: OperationContext, data: SalaryChange) -> Done:
    CALLS.append(f"register_salary_change:{ctx.actor.id}")
    return Done()


@operation(
    name="terminate_policy", description="Avslutar försäkring", kind=OperationKind.WRITE,
    rules=["PR-T-GODKAND"], registry=registry,
)
def terminate_policy(ctx: OperationContext, data: PolicyRef) -> Done:
    CALLS.append("terminate_policy")
    return Done()


@operation(
    name="start_withdrawal", description="Uttag", kind=OperationKind.WRITE,
    rules=["PR-T-UTKAST"], registry=registry,
)
def start_withdrawal(ctx: OperationContext, data: PolicyRef) -> Done:
    CALLS.append("start_withdrawal")
    return Done()


REGISTER = {
    "get_overview": "AGENT",
    "preview_premium": "AGENT",
    "register_salary_change": "APPROVAL",
    "terminate_policy": "HUMAN_ONLY",
    "start_withdrawal": "AGENT",  # registret öppnar – men regeln är utkast
}

HUMAN = OperationContext(actor=Actor.human("karl"), reason="Enligt lönebesked")
AGENT = OperationContext(
    actor=Actor.agent("case_handler", team="forsakring"), reason="Kunden meddelade ny lön", run_id="run-1"
)


@pytest.fixture
def service(tmp_path):
    for rule_id, status in (("PR-T-GODKAND", "Godkänd"), ("PR-T-UTKAST", "Utkast")):
        (tmp_path / f"{rule_id}-x.md").write_text(f"> **Granskningsstatus:** {status}\n", encoding="utf-8")
    CALLS.clear()
    return ServiceLayer(
        registry=registry,
        register=AccessRegister.from_dict(REGISTER),
        rules=ProductRuleCatalog(tmp_path),
        events=MemoryEventLog(),
    )


SALARY = {"policy_number": "AL-000001", "monthly_salary_sek": 42000}


class TestHandlaggare:
    def test_handlaggare_far_utfora_endast_handlaggare_operation(self, service):
        result = service.execute("terminate_policy", HUMAN, {"policy_number": "AL-000001"})
        assert not result.pending and CALLS == ["terminate_policy"]
        (event,) = service.events.events
        assert (event.outcome, event.actor_type, event.actor_id) == ("executed", "human", "karl")
        assert event.reason == "Enligt lönebesked"

    def test_handlaggare_far_utfora_operation_med_utkastregel(self, service):
        service.execute("start_withdrawal", HUMAN, {"policy_number": "AL-000001"})
        assert CALLS == ["start_withdrawal"]

    def test_systemaktor_behandlas_som_handlaggare(self, service):
        ctx = OperationContext(actor=Actor.system("premium_run"), reason="Månadskörning")
        service.execute("terminate_policy", ctx, {"policy_number": "AL-000001"})
        assert service.events.events[0].actor_type == "system"


class TestAgent:
    def test_agent_nekas_endast_handlaggare_och_forsoket_loggas(self, service):
        with pytest.raises(AccessDeniedError, match="endast handläggare"):
            service.execute("terminate_policy", AGENT, {"policy_number": "AL-000001"})
        assert CALLS == []  # operationen kördes aldrig
        (event,) = service.events.events
        assert (event.outcome, event.actor_id, event.run_id) == ("denied", "case_handler", "run-1")

    def test_registret_kan_inte_oppna_forbi_utkastregel(self, service):
        with pytest.raises(AccessDeniedError) as info:
            service.execute("start_withdrawal", AGENT, {"policy_number": "AL-000001"})
        assert any("PR-T-UTKAST (utkast)" in r for r in info.value.reasons)
        assert CALLS == []

    def test_agent_far_lasa_och_personuppgiftslasning_loggas(self, service):
        service.execute("get_overview", AGENT, {"policy_number": "AL-000001"})
        (event,) = service.events.events
        assert (event.outcome, event.pii, event.output) == ("executed", True, None)

    def test_berakning_utan_personuppgifter_loggas_inte(self, service):
        service.execute("preview_premium", AGENT, {"policy_number": "AL-000001"})
        assert CALLS == ["preview_premium"] and service.events.events == []

    def test_operationer_for_agenter_doljer_endast_handlaggare(self, service):
        names = [op.name for op in service.operations_for_agents()]
        assert names == ["get_overview", "preview_premium", "register_salary_change"]


class TestGodkannande:
    def test_agentforslag_vantar_pa_godkannande(self, service):
        result = service.execute("register_salary_change", AGENT, SALARY)
        assert result.pending and result.approval_id
        assert CALLS == []
        (request,) = service.approvals.list("pending")
        assert (request.proposed_by, request.proposed_by_team, request.input) == (
            "case_handler", "forsakring", SALARY,
        )
        assert service.events.events[0].outcome == "proposed"

    def test_handlaggare_godkanner_och_operationen_kors_som_handlaggare(self, service):
        approval_id = service.execute("register_salary_change", AGENT, SALARY).approval_id
        result = service.approve(approval_id, OperationContext(actor=Actor.human("karl")), note="OK")

        assert not result.pending
        assert CALLS == ["register_salary_change:karl"]  # utförd av människan
        executed = service.events.events[-1]
        assert (executed.outcome, executed.actor_id, executed.proposed_by, executed.approval_id) == (
            "executed", "karl", "case_handler", approval_id,
        )
        assert executed.reason == "Kunden meddelade ny lön"  # agentens motivering följer med
        assert executed.run_id == "run-1"
        assert service.approvals.get(approval_id).status == "approved"

    def test_agent_kan_inte_godkanna(self, service):
        approval_id = service.execute("register_salary_change", AGENT, SALARY).approval_id
        with pytest.raises(ApprovalError, match="människa"):
            service.approve(approval_id, AGENT)

    def test_ett_arende_kan_bara_avgoras_en_gang(self, service):
        approval_id = service.execute("register_salary_change", AGENT, SALARY).approval_id
        service.approve(approval_id, HUMAN)
        with pytest.raises(ApprovalError, match="redan approved"):
            service.approve(approval_id, HUMAN)

    def test_avslag_loggas_och_operationen_kors_inte(self, service):
        approval_id = service.execute("register_salary_change", AGENT, SALARY).approval_id
        service.reject(approval_id, HUMAN, note="Lönebesked saknas")
        assert CALLS == []
        assert service.approvals.get(approval_id).status == "rejected"
        rejected = service.events.events[-1]
        assert (rejected.outcome, rejected.detail) == ("rejected", "Lönebesked saknas")

    def test_okant_arende(self, service):
        with pytest.raises(ApprovalError, match="Okänt"):
            service.approve("finns-inte", HUMAN)


class TestValidering:
    def test_skrivning_kraver_motivering(self, service):
        with pytest.raises(MissingReasonError):
            service.execute("terminate_policy", OperationContext(actor=Actor.human("karl")), {"policy_number": "X"})

    def test_ogiltig_indata(self, service):
        with pytest.raises(InvalidInputError):
            service.execute("register_salary_change", HUMAN, {"policy_number": "X"})

    def test_okand_operation(self, service):
        with pytest.raises(UnknownOperationError):
            service.execute("finns_inte", HUMAN, {})

    def test_registerrad_for_okand_operation_stoppar_start(self, tmp_path):
        with pytest.raises(ServiceConfigError, match="okända operationer"):
            ServiceLayer(
                registry=registry,
                register=AccessRegister.from_dict({**REGISTER, "stavfel": "AGENT"}),
                rules=ProductRuleCatalog(tmp_path),
                events=MemoryEventLog(),
            )


class TestSession:
    def test_operationen_far_session_och_loggen_skrivs_inom_transaktionen(self, tmp_path):
        state = {"open": False}
        seen = {}
        reg = OperationRegistry()

        @contextmanager
        def session_scope():
            state["open"] = True
            yield "session-1"
            state["open"] = False

        class OpenCheckingLog(MemoryEventLog):
            def record(self, event, session=None):
                seen["open_when_logged"] = state["open"]
                seen["log_session"] = session
                super().record(event, session)

        @operation(name="touch", description="t", kind=OperationKind.READ, pii=True, registry=reg)
        def touch(ctx: OperationContext, data: PolicyRef) -> Done:
            seen["session"] = ctx.session
            return Done()

        service = ServiceLayer(
            registry=reg, register=AccessRegister.from_dict({}), rules=ProductRuleCatalog(tmp_path),
            events=OpenCheckingLog(), session_factory=session_scope,
        )
        service.execute("touch", HUMAN, {"policy_number": "X"})
        assert seen == {"session": "session-1", "open_when_logged": True, "log_session": "session-1"}
