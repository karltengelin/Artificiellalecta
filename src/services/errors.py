"""Fel från tjänstelagret (02_system/tjänstelager.md)."""

from __future__ import annotations


class ServiceError(Exception):
    """Basklass för alla fel från tjänstelagret."""


class ServiceConfigError(ServiceError):
    """Felaktig konfiguration: ogiltig registerrad, okänd operation i registret, dubbla namn m.m."""


class UnknownOperationError(ServiceError):
    """Operationen finns inte i operationsregistret."""


class InvalidInputError(ServiceError):
    """Indata validerar inte mot operationens indatamodell."""


class MissingReasonError(ServiceError):
    """Skrivande operationer kräver en motivering (spårbarhet, B-028)."""


class AccessDeniedError(ServiceError):
    """Aktören får inte utföra operationen."""

    def __init__(self, message: str, *, operation: str, actor_id: str, reasons: tuple[str, ...] = ()):
        super().__init__(message)
        self.operation = operation
        self.actor_id = actor_id
        self.reasons = reasons


class ApprovalError(ServiceError):
    """Fel vid godkännande: okänt ärende, redan avgjort, eller godkännare som inte är människa."""
