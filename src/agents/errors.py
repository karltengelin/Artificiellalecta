"""Fel från harness (02_system/harness.md)."""

from __future__ import annotations


class HarnessError(Exception):
    """Basklass för alla fel från harness."""


class EcosystemConfigError(HarnessError):
    """Ogiltig körpolicy: okänd podd eller operation, rättighet utöver teamets, dubbel mappning m.m.

    Stoppar profilen vid start – en felaktig policy ska aldrig delvis gälla.
    """


class RunRequestError(HarnessError):
    """Uppdraget försöker något det inte får, t.ex. höja en gräns eller byta agentens team."""


class SkillDeniedError(HarnessError):
    """Skillen finns inte, eller är inte öppen för agenten i den här körningen."""

    def __init__(self, message: str, *, skill: str, reasons: tuple[str, ...] = ()):
        super().__init__(message)
        self.skill = skill
        self.reasons = reasons


class SkillInputError(HarnessError):
    """Modellens anrop validerar inte mot skillens schema – inklusive okända fält."""
