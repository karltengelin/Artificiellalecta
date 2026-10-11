"""Händelselogg och godkännandekö i databasen (tabellerna operation_events och approval_requests)."""

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from models import ApprovalRequestRecord, OperationEventRecord
from services import (
    AccessRegister,
    Actor,
    OperationContext,
    OperationKind,
    OperationRegistry,
    ProductRuleCatalog,
    ServiceLayer,
    operation,
)
from services.approvals import DatabaseApprovalStore
from services.events import DatabaseEventLog

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")


class Change(BaseModel):
    policy_number: str
    fail: bool = False


class Done(BaseModel):
    ok: bool = True


registry = OperationRegistry()


@operation(name="change_something", description="Ändring", kind=OperationKind.WRITE,
           rules=["PR-T-001"], pii=True, registry=registry)
def change_something(ctx: OperationContext, data: Change) -> Done:
    if data.fail:
        raise ValueError("simulerat fel i operationen")
    return Done()


HUMAN = OperationContext(actor=Actor.human("karl"), reason="Test")
AGENT = OperationContext(actor=Actor.agent("case_handler", team="forsakring"), reason="Förslag", run_id="run-9")


@pytest.fixture
def make_service(insurance_db, tmp_path):
    (tmp_path / "PR-T-001-x.md").write_text("> **Granskningsstatus:** Godkänd\n", encoding="utf-8")

    def make():
        return ServiceLayer(
            registry=registry,
            register=AccessRegister.from_dict({"change_something": "APPROVAL"}),
            rules=ProductRuleCatalog(tmp_path),
            session_factory=insurance_db.session_factory,
        )

    return make


def rows(insurance_db, model):
    with insurance_db.session_factory() as s:
        return s.scalars(select(model)).all()


def test_med_databas_anvands_databastabellerna_som_standard(make_service):
    service = make_service()
    assert isinstance(service.events, DatabaseEventLog)
    assert isinstance(service.approvals, DatabaseApprovalStore)


def test_utford_andring_loggas_i_tabellen(make_service, insurance_db):
    make_service().execute("change_something", HUMAN, {"policy_number": "AL-000001"})
    (event,) = rows(insurance_db, OperationEventRecord)
    assert (event.operation, event.outcome, event.actor_id, event.pii) == ("change_something", "executed", "karl", True)
    assert event.input == {"policy_number": "AL-000001", "fail": False}
    assert event.rules == ["PR-T-001"]


def test_misslyckad_andring_lamnar_ingen_loggrad(make_service, insurance_db):
    with pytest.raises(ValueError):
        make_service().execute("change_something", HUMAN, {"policy_number": "AL-000001", "fail": True})
    assert rows(insurance_db, OperationEventRecord) == []


def test_agentforslag_overlever_omstart_och_kan_godkannas(make_service, insurance_db):
    approval_id = make_service().execute("change_something", AGENT, {"policy_number": "AL-000001"}).approval_id

    restarted = make_service()  # ny instans – kön ligger i databasen
    (pending,) = restarted.approvals.list("pending")
    assert (pending.id, pending.proposed_by, pending.run_id) == (approval_id, "case_handler", "run-9")

    restarted.approve(approval_id, OperationContext(actor=Actor.human("karl")), note="OK")
    (record,) = rows(insurance_db, ApprovalRequestRecord)
    assert (record.status, record.decided_by, record.decision_note) == ("approved", "karl", "OK")
    assert record.decided_at is not None

    events = sorted(rows(insurance_db, OperationEventRecord), key=lambda e: e.occurred_at)
    assert [(e.outcome, e.actor_id, e.proposed_by) for e in events] == [
        ("proposed", "case_handler", None),
        ("executed", "karl", "case_handler"),
    ]


def test_handelseloggen_kan_lasas_tillbaka(make_service):
    service = make_service()
    service.execute("change_something", HUMAN, {"policy_number": "AL-000001"})
    (event,) = service.events.list()
    assert (event.operation, event.actor_type, event.outcome) == ("change_something", "human", "executed")
