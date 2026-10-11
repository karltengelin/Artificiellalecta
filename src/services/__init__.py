"""Tjänstelagret – den enda vägen in till försäkringssystemets operationer (B-028).

Handläggar-UI:t, agenter (via harness) och skript anropar operationer här.
Vad agenter får göra bestäms i åtkomstregistret `access_register.yaml`.
Specifikation: 02_system/tjänstelager.md.

    from services import Actor, OperationContext, ServiceLayer
    service = ServiceLayer()
    ctx = OperationContext(actor=Actor.human("karl"), reason="Ny lön enligt lönebesked")
    result = service.execute("register_salary_change", ctx, {...})
"""

from services.access import AccessDecision, AccessRegister, effective_access
from services.approvals import ApprovalRequest, MemoryApprovalStore
from services.contract import (
    Actor,
    AgentAccess,
    Operation,
    OperationContext,
    OperationKind,
    OperationRegistry,
    default_registry,
    operation,
)
from services.errors import (
    AccessDeniedError,
    ApprovalError,
    InvalidInputError,
    MissingReasonError,
    ServiceConfigError,
    ServiceError,
    UnknownOperationError,
)
from services.events import JsonlEventLog, MemoryEventLog, OperationEvent
from services.rules import ProductRuleCatalog, RuleStatus
from services.service import OperationResult, ResultStatus, ServiceLayer

__all__ = [
    "AccessDecision",
    "AccessDeniedError",
    "AccessRegister",
    "Actor",
    "AgentAccess",
    "ApprovalError",
    "ApprovalRequest",
    "InvalidInputError",
    "JsonlEventLog",
    "MemoryApprovalStore",
    "MemoryEventLog",
    "MissingReasonError",
    "Operation",
    "OperationContext",
    "OperationEvent",
    "OperationKind",
    "OperationRegistry",
    "OperationResult",
    "ProductRuleCatalog",
    "ResultStatus",
    "RuleStatus",
    "ServiceConfigError",
    "ServiceError",
    "ServiceLayer",
    "UnknownOperationError",
    "default_registry",
    "effective_access",
    "operation",
]
