"""Tjänstelagret – den enda vägen in till försäkringssystemets operationer (B-028).

Handläggar-UI:t, agenter (via harness) och skript anropar operationer här.
Vad agenter får göra bestäms i åtkomstregistret `access_register.yaml`.
Specifikation: 02_system/tjänstelager.md.

    from services import Actor, OperationContext, ServiceLayer
    service = ServiceLayer()
    ctx = OperationContext(actor=Actor.human("karl"), reason="Lönefil för september")
    result = service.execute("register_salary_report", ctx, {...})
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
    BlockedError,
    ConflictError,
    InvalidInputError,
    MissingReasonError,
    NotFoundError,
    ServiceConfigError,
    ServiceError,
    UnknownOperationError,
)
from services.events import JsonlEventLog, MemoryEventLog, OperationEvent
from services.rules import ProductRuleCatalog, RuleStatus
from services.service import OperationResult, ResultStatus, ServiceLayer

# Registrerar alla operationer i standardregistret (måste ligga efter importerna ovan)
from services import operations  # noqa: E402, F401  isort: skip

__all__ = [
    "AccessDecision",
    "AccessDeniedError",
    "AccessRegister",
    "Actor",
    "AgentAccess",
    "ApprovalError",
    "ApprovalRequest",
    "BlockedError",
    "ConflictError",
    "InvalidInputError",
    "JsonlEventLog",
    "MemoryApprovalStore",
    "MemoryEventLog",
    "MissingReasonError",
    "NotFoundError",
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
