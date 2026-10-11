"""Åtkomstregistret och effektiv agentåtkomst (tjänstelager.md §4, B-028).

Registret (access_register.yaml) anger vad agenter får göra med varje
operation. Effektiv nivå är den strängaste av registrets nivå och tre golv:
  - operationen saknas i registret                          -> HUMAN_ONLY
  - external (påverkar omvärlden)                          -> minst APPROVAL
  - write/external vars produktregel inte är `godkänd`     -> HUMAN_ONLY
Handläggare (och skript som operatören startar) får alltid utföra allt (B-017).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from services.contract import AgentAccess, Operation, OperationKind, OperationRegistry, strictest
from services.errors import ServiceConfigError
from services.rules import ProductRuleCatalog, RuleStatus

DEFAULT_REGISTER_PATH = Path(__file__).with_name("access_register.yaml")


@dataclass(frozen=True)
class AccessRegister:
    levels: dict[str, AgentAccess]
    path: Path | None = None

    @classmethod
    def load(cls, path: Path | None = None) -> AccessRegister:
        path = path or DEFAULT_REGISTER_PATH
        if not path.exists():
            raise ServiceConfigError(f"Åtkomstregistret hittades inte: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.from_dict(data.get("operations") or {}, path=path)

    @classmethod
    def from_dict(cls, levels: dict[str, str], path: Path | None = None) -> AccessRegister:
        parsed = {}
        for name, level in levels.items():
            try:
                parsed[name] = AgentAccess(str(level).strip().upper())
            except ValueError:
                raise ServiceConfigError(
                    f"Ogiltig nivå '{level}' för '{name}' i åtkomstregistret – "
                    f"tillåtna: {', '.join(a.value for a in AgentAccess)}"
                ) from None
        return cls(levels=parsed, path=path)

    def validate_against(self, registry: OperationRegistry) -> None:
        """En rad för en operation som inte finns är troligen ett stavfel – stoppa direkt."""
        unknown = sorted(name for name in self.levels if name not in registry)
        if unknown:
            raise ServiceConfigError(
                f"Åtkomstregistret nämner okända operationer: {', '.join(unknown)}"
            )


@dataclass(frozen=True)
class AccessDecision:
    operation: str
    registered: AgentAccess | None  # nivån i registret (None = saknas)
    effective: AgentAccess
    reasons: tuple[str, ...]  # varför effektiv nivå är strängare än registrets


def effective_access(
    op: Operation, register: AccessRegister, rules: ProductRuleCatalog
) -> AccessDecision:
    registered = register.levels.get(op.name)
    reasons: list[str] = []

    if registered is None:
        effective = AgentAccess.HUMAN_ONLY
        reasons.append("saknas i åtkomstregistret")
    else:
        effective = registered

    if op.kind == OperationKind.EXTERNAL and effective == AgentAccess.AGENT:
        effective = AgentAccess.APPROVAL
        reasons.append("external-operationer kräver minst godkännande (§3.5)")

    if op.kind.changes_state and effective != AgentAccess.HUMAN_ONLY:
        if not op.rules:
            effective = AgentAccess.HUMAN_ONLY
            reasons.append("skrivande operation utan produktregel")
        else:
            not_approved = [
                f"{rule_id} ({status.value})"
                for rule_id in op.rules
                if (status := rules.status(rule_id)) != RuleStatus.GODKAND
            ]
            if not_approved:
                effective = strictest(effective, AgentAccess.HUMAN_ONLY)
                reasons.append(f"produktregel inte godkänd: {', '.join(not_approved)}")

    return AccessDecision(
        operation=op.name, registered=registered, effective=effective, reasons=tuple(reasons)
    )
