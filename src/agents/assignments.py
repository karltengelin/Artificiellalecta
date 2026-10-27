"""Uppdragsmallar för teamen compliance och aktuarie (Fas 3c 3c-T, flaggskeppsflöde.md §5 och §7).

    request = request_for_interpretation("K-SIM-ITP-2027")
    outcome = run_assignment(ai, eco, skills, service, request)
    outcome.result.output                   # InterpretationProposal med bevis (agents.results)

    mandate = mandate_from_interpretation(outcome.result.output, ref="pc-FLOW-000001")
    request = request_for_impact(mandate)
    outcome = run_assignment(ai, eco, skills, service, request, parameter_change=mandate)

Mallarna är betrodd kod: mål, begränsningar, resultatschema och referenser kommer härifrån,
aldrig från modellen. Uppdragstexten innehåller inga personuppgifter. Flödesmotorn (3c-2)
kör stegen och binder grindarna; här finns bara uppdragen och körningen av ett steg.

Aktuarieagenten får bara räkna på den ändring som grind 1 har godkänt. `mandate_from_interpretation`
tar den ur den godkända tolkningen; dispatchern prövar varje anrop mot mandatet.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from agents.delegation import DelegationRuntime
from agents.ecosystem import Ecosystem, Limits
from agents.errors import HarnessError
from agents.gateways import Gateways
from agents.journal import Journal
from agents.loop import RunOutcome, run_agent
from agents.profile import compile_profile
from agents.run import RunRequest
from agents.scope import ParameterChangeMandate
from agents.skills import SkillRegistry
from ai import AIClient
from services import ServiceLayer

INTERPRETATION_CONSTRAINTS = (
    "Läs källan och de produktregler den berör innan du drar slutsatser",
    "Ange nuvarande värde enligt get_product_parameters och nytt värde enligt källan",
    "Ändra inga gällande dokument och skriv inget B-nummer – lämna förslag som utkast",
    "Inga kundpersonuppgifter",
)
IMPACT_CONSTRAINTS = (
    "Räkna bara på den godkända ändringen – andra värden nekas",
    "Varje tal kommer från beräkningen; dold och ej beräknad är aldrig noll",
    "Ingen individdata och inga försök att härleda dolda celler",
    "Volymen gäller dagens lön utan lönetillväxt och utan avkastning – säg det",
)


def request_for_interpretation(
    source_handle: str, *, task_id: str | None = None, limits: Limits | None = None, **links: Any
) -> RunRequest:
    """Steg 1: compliance tolkar källan till produktregler och parametrar.

    `links` är flödets referenser (flow_id, flow_step_id, root_run_id) när ett flöde beställer.
    """
    return RunRequest(
        task_id=task_id or f"task-tolkning-{uuid.uuid4().hex[:8]}",
        target_team="compliance",
        goal=(
            f"Tolka regelverksändringen i källan {source_handle}. Läs källan, de produktregler och tolkningar "
            "som berörs och parameterregistret. Ta fram berörda regler, föreslagna parameterändringar med nuvarande "
            "och nytt värde och giltighet, kundpåverkan och osäkerheter. Skriv en konsekvensanalys och ett förslag "
            "till ändrad regeltext som utkast."
        ),
        constraints=INTERPRETATION_CONSTRAINTS,
        expected_output="Tolkning med källor och utkast för operatörens granskning i grind 1",
        result_schema="InterpretationProposal",
        references=(source_handle,),
        limits=limits or Limits(),
        **links,
    )


def mandate_from_interpretation(
    output: dict[str, Any], *, ref: str, index: int = 0, horizon_years: int = 10
) -> ParameterChangeMandate:
    """Mandatet ur en godkänd tolkning (`RunResult.output` med schemat InterpretationProposal).

    Betrodd kod anropar detta efter grind 1. Tolkningen ska föreslå minst en parameterändring;
    `index` väljer vilken när den föreslår flera.
    """
    if output.get("schema") != "InterpretationProposal":
        raise HarnessError("Mandatet byggs bara ur en tolkning (InterpretationProposal)")
    changes = output["result"]["parameter_changes"]
    if not 0 <= index < len(changes):
        raise HarnessError("Tolkningen föreslår ingen parameterändring att räkna på")
    change = changes[index]
    return ParameterChangeMandate(
        ref=ref, key=change["key"], value=Decimal(str(change["new_value"])),
        valid_from=date.fromisoformat(change["valid_from"]), horizon_years=horizon_years,
    )


def request_for_impact(
    mandate: ParameterChangeMandate, *, task_id: str | None = None, limits: Limits | None = None, **links: Any
) -> RunRequest:
    """Steg 2: aktuarien tar fram beståndsinsikten för den godkända ändringen."""
    return RunRequest(
        task_id=task_id or f"task-insikt-{uuid.uuid4().hex[:8]}",
        target_team="aktuarie",
        goal=(
            f"Ta fram beståndsinsikten för ändringen {mandate.key} = {mandate.value} från "
            f"{mandate.valid_from.isoformat()}, med horisonten {mandate.horizon_years} år. Kör beräkningen med exakt "
            "de värdena, förklara vem som berörs, när och hur mycket, och skriv ett rapportutkast."
        ),
        constraints=IMPACT_CONSTRAINTS,
        expected_output="Beståndsinsikt med antaganden och rapportutkast för operatörens beslut i grind 2",
        result_schema="PortfolioImpactResult",
        references=(mandate.ref,),
        parameter_change_ref=mandate.ref,
        limits=limits or Limits(),
        **links,
    )


def run_assignment(
    ai: AIClient,
    ecosystem: Ecosystem,
    skills: SkillRegistry,
    service: ServiceLayer,
    request: RunRequest,
    *,
    parameter_change: ParameterChangeMandate | None = None,
    gateways: Gateways | None = None,
    run_id: str | None = None,
    journal: Journal | None = None,
    journal_dir: Path | None = None,
    delegation: DelegationRuntime | None = None,
) -> RunOutcome:
    """Kör ett uppdrag från mallarna ovan genom samma profil, loop, dispatcher och journal som alla körningar.

    `delegation` behövs när uppdraget har delegeringsmål (`delegation_targets`, 3c-1).
    """
    profile = compile_profile(ecosystem, skills, service, request=request)
    return run_agent(
        ai, profile, service, request, parameter_change=parameter_change, gateways=gateways,
        run_id=run_id, journal=journal, journal_dir=journal_dir, delegation=delegation,
    )
