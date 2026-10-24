"""Resursmandat för en körning: vilka personer, försäkringar och perioder agenten får röra (3b-3).

Design: harness.md §5.1. En databasroll med SELECT på hela individtabellen säkrar
inte kundscope – därför prövar betrodd kod varje anrop *före* tjänstelagret och
varje resultat *innan* det lämnas till modellen.

`ExecutionScope` byggs av betrodd kod (UI, flöde, skript) – aldrig av modellen –
och hör till uppdragets `execution_scope_ref`. I v1 är arbetsenheten en tilldelad
försäkrad och högst 24 månader (harness.md §6.3); masshantering kräver en egen profil.

Prövningen är stängd som standard: indata till ett PII-verktyg godtas bara om
varje identifierande fält kan kontrolleras mot scopet. Ett id som inte går att
pröva (t.ex. en transaktions-UUID), nästlade indata eller en öppen period nekas.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agents.errors import ScopeError
from services import Actor, OperationContext, ServiceLayer

MAX_SCOPE_MONTHS = 24
MAX_SCOPE_PERSONS = 1

# Identifierande fält i indata och var de prövas
_PERSON_FIELDS = {"personal_id_number"}
_POLICY_FIELDS = {"policy_number"}
_EMPLOYER_FIELDS = {"employer_org_number", "org_number"}
_PERIOD_BOUNDS = ("from_month", "to_month")  # öppen period (None) nekas
_UNVERIFIABLE_ID = re.compile(r"(^|_)(id|uuid)$")


class ExecutionScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: str = Field(min_length=1)
    persons: frozenset[str]
    policies: frozenset[str] = frozenset()
    employers: frozenset[str] = frozenset()
    from_month: date
    to_month: date
    case_id: str | None = None

    @model_validator(mode="after")
    def _limits(self) -> ExecutionScope:
        if not 1 <= len(self.persons) <= MAX_SCOPE_PERSONS:
            raise ValueError(f"Ett uppdrag gäller exakt {MAX_SCOPE_PERSONS} försäkrad i v1")
        if self.from_month.day != 1 or self.to_month.day != 1:
            raise ValueError("from_month och to_month anges som första dagen i månaden")
        if self.to_month < self.from_month:
            raise ValueError("to_month är före from_month")
        if _months(self.from_month, self.to_month) > MAX_SCOPE_MONTHS:
            raise ValueError(f"Perioden får vara högst {MAX_SCOPE_MONTHS} månader")
        return self

    def check_input(self, skill: str, data: BaseModel) -> None:
        """Nej med samtliga skäl om indata rör något utanför scopet."""
        reasons: list[str] = []
        subject = False
        for name, value in data.model_dump().items():
            if value is None:
                if name in _PERIOD_BOUNDS:
                    reasons.append(f"{name} måste anges inom uppdragets period")
                continue
            if isinstance(value, (dict, list, tuple, set)):
                reasons.append(f"{name}: nästlade indata kan inte prövas mot scopet")
            elif name in _PERSON_FIELDS:
                subject = True
                if value not in self.persons:
                    reasons.append(f"{name}: personen ingår inte i uppdraget")
            elif name in _POLICY_FIELDS:
                subject = True
                if value not in self.policies:
                    reasons.append(f"{name}: försäkringen ingår inte i uppdraget")
            elif name in _EMPLOYER_FIELDS:
                if value not in self.employers:
                    reasons.append(f"{name}: arbetsgivaren ingår inte i uppdraget")
            elif isinstance(value, uuid.UUID) or _UNVERIFIABLE_ID.search(name):
                reasons.append(f"{name}: id:t kan inte prövas mot scopet")
            elif name.endswith("_month") and isinstance(value, date) and not self._in_period(value):
                # Premie- och lönemånader avgränsas; andra datum (t.ex. received_date) är inte perioder
                reasons.append(
                    f"{name} {value.isoformat()} ligger utanför uppdragets period "
                    f"{self.from_month.isoformat()}–{self.to_month.isoformat()}"
                )
        if not subject:
            reasons.append("anropet anger ingen försäkrad eller försäkring ur uppdraget")
        if reasons:
            raise ScopeError(f"'{skill}' utanför uppdragets scope: {'; '.join(reasons)}")

    def check_output(self, skill: str, payload: Any) -> None:
        """Resultatet får bara nämna personer, försäkringar och arbetsgivare i scopet."""
        found: list[str] = []
        _walk_identifiers(payload, self, found)
        if found:
            raise ScopeError(
                f"Resultatet från '{skill}' innehöll uppgifter utanför uppdraget och lämnades inte ut "
                f"({', '.join(sorted(set(found)))})"
            )

    def _in_period(self, value: date) -> bool:
        month = value.replace(day=1)
        return self.from_month <= month <= self.to_month


def scope_for_person(
    service: ServiceLayer,
    *,
    ref: str,
    personal_id_number: str,
    from_month: date,
    to_month: date,
    assigned_by: str,
    case_id: str | None = None,
) -> ExecutionScope:
    """Betrodd kod: bygger scopet för en tilldelad försäkrad ur tjänstelagret.

    `assigned_by` är handläggaren som tilldelar uppdraget. Läsningen görs som
    systemaktör och loggas i händelseloggen (personuppgifter).
    """
    ctx = OperationContext(
        actor=Actor.system("harness_scope"),
        reason=f"Resursmandat {ref} för agentuppdrag, tilldelat av {assigned_by}",
        case_id=case_id,
    )
    overview = service.execute("get_insured_overview", ctx, {"personal_id_number": personal_id_number}).output
    return ExecutionScope(
        ref=ref,
        persons=frozenset({overview.personal_id_number}),
        policies=frozenset(p.policy_number for p in overview.policies),
        employers=frozenset({overview.employer.org_number}),
        from_month=from_month,
        to_month=to_month,
        case_id=case_id,
    )


def _walk_identifiers(node: Any, scope: ExecutionScope, found: list[str]) -> None:
    if isinstance(node, dict):
        allowed = (
            (_PERSON_FIELDS, scope.persons),
            (_POLICY_FIELDS, scope.policies),
            (_EMPLOYER_FIELDS, scope.employers),
        )
        for key, value in node.items():
            if isinstance(value, str):
                if any(key in fields and value not in values for fields, values in allowed):
                    found.append(key)
            else:
                _walk_identifiers(value, scope, found)
    elif isinstance(node, list):
        for item in node:
            _walk_identifiers(item, scope, found)


def _months(start: date, end: date) -> int:
    """Antal månader inklusive båda ändarna."""
    return (end.year - start.year) * 12 + end.month - start.month + 1
