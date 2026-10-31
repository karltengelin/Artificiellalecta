"""Betrodd kontroll av nya ärendeuppdrags förslag; modellen utfärdar inga undantag."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import inspect, select

from models import Case, CaseWork
from services.contract import AgentAccess, OperationKind
from services.errors import ApprovalError
from services.operations.cases import _view
from services.operations.salary import SalaryReportInput


def case_digest(case) -> str:
    """Underlaget binds; status, tilldelning och senaste körning är inte sakunderlag."""
    fields = ("case_number", "case_type", "personal_id_number", "employer_org_number", "policy_number",
              "period_month", "received_date", "source_reference", "details")
    data = {name: getattr(case, name) for name in fields}
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def expected_salary(case) -> SalaryReportInput:
    return SalaryReportInput(
        personal_id_number=case.personal_id_number, employer_org_number=case.employer_org_number,
        period_month=case.period_month, received_date=case.received_date,
        source_reference=case.source_reference, **case.details,
    )


def guard_case_proposal(session, request, service, *, work_id=None, policy_path=None):
    """Körs i beslutets transaktion. Äldre förslag utan CaseWork behåller sin väg."""
    if session is None or not request.run_id:
        if work_id:
            raise ApprovalError("Automatisk ärendehantering kräver varaktigt uppdrag")
        return None
    if not inspect(session.connection()).has_table("case_work"):
        if work_id:
            raise ApprovalError("Ärendeuppdragens migration saknas")
        return None
    # Samma låsordning som arbetsytan: ärende, därefter uppdrag.
    case = session.scalar(select(Case).where(Case.case_number == request.case_id).with_for_update())
    work = session.scalar(select(CaseWork).where(CaseWork.run_id == request.run_id).with_for_update())
    if work is None:
        if work_id:
            raise ApprovalError("Förslaget hör inte till ett ärendeuppdrag")
        return None
    if case is None or case.status == "closed" or work.case_number != request.case_id:
        raise ApprovalError("Ärendet är stängt eller hör inte till förslaget")
    if work.cancel_requested or work.status not in {"running", "waiting_approval"}:
        raise ApprovalError("Uppdraget är pausat eller återtaget; avslå förslaget före ny handläggning")
    view = _view(session, case)
    if case_digest(view) != work.case_digest:
        raise ApprovalError("Ärendeunderlaget har ändrats; förslaget måste granskas om")
    if request.operation != "register_salary_report" or request.proposed_by != "case_handler":
        raise ApprovalError("Operationen ingår inte i detta ärendeuppdrag")
    if SalaryReportInput.model_validate(request.input) != expected_salary(view):
        raise ApprovalError("Förslaget motsvarar inte ärendets verifierade löneunderlag")
    if work_id:
        from agents.case_policy import DEFAULT_POLICY, CasePolicy

        policy, version = CasePolicy.load(policy_path or DEFAULT_POLICY)
        if (work.id != work_id or work.mode != "handle" or not work.allow_proposals
                or work.policy != policy.snapshot(case.case_type, version) or work.policy["review_required"]):
            raise ApprovalError("Uppdraget har inget aktuellt mandat för automatisk slutbehandling")
        op = service.registry.get(request.operation)
        if op.kind != OperationKind.WRITE or service.decision(op.name).effective != AgentAccess.APPROVAL:
            raise ApprovalError("Reglerna tillåter inte automatisk verkställighet")
        # Endast ordinarie nya arbetsgivarrapporter i första automationsförmågan.
        if view.details["kind"] != "new" or view.details["source"] != "employer":
            raise ApprovalError("Rättelser och manuella underlag kräver mänsklig granskning")
    return work
