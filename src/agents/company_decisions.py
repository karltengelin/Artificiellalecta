"""Mänskliga beslut och uppdragsbundna överlämningar till ordinarie domäner."""

import re
from datetime import date
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import inspect, select

from agents.company_capabilities import (
    ACTIVATE,
    ACTIVATION,
    APPROVE_INTERPRETATION,
    DEVELOP,
    ORIGIN,
    activation_input,
    check_drafts,
    checked_effect,
    fresh_sources,
    interpretation,
    interpretation_for,
    matching_parameter,
)
from agents.company_store import missions, now
from agents.gateways import DraftGateway, GatewayError, RegulatoryGateway
from agents.gateways.drafts import _check_content
from services import Actor, OperationContext
from services.change_requests import (
    ChangeRequestOrder,
    ChangeRequestOrigin,
    Notes,
    ShortText,
)
from services.errors import ApprovalError, ConflictError, InvalidInputError
from services.parameters import plain, version_label, versions_on
from utils.checksums import canonical_hash

COMPLIANCE_AGENT = Actor.agent("compliance_agent", team="compliance")


class RuleAdoption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_version: str = Field(pattern=r"^\d+\.\d+$")
    valid_from: date
    decision_number: str | None = Field(default=None, pattern=r"^B-\d{3}$")


class CodeRuleAdoption(RuleAdoption):
    model_config = ConfigDict(str_strip_whitespace=True)

    rule_id: str = Field(pattern=r"^PR-ITP1-\d{3}$")
    code_reason: Notes
    affected_system: ShortText
    expected_effect: Notes


class RuleTextCommit(BaseModel):
    commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    note: str | None = Field(default=None, max_length=500)


def decide(state, ident, actor, seen, verdict, form, *, gateways, trusted):
    if state["status"] != "waiting_review" or not state["reviews"]:
        raise ConflictError("Uppdraget väntar inte på granskning")
    review = state["reviews"][0]
    if review["hash"] != seen:
        raise ConflictError("Granskningsunderlaget har ändrats. Läs om sidan")
    if verdict not in ("approved", "rejected"):
        raise InvalidInputError("Välj ett giltigt beslut")
    note = form.get("note", "").strip()
    if len(note) > 500 or (verdict == "rejected" and not note):
        raise InvalidInputError("Ange ett skäl på högst 500 tecken vid avslag")
    _check_content(note)
    decision = {**review, "id": uuid4().hex, "decision": verdict, "by": actor.id,
                "at": now(), "note": note, "details": None}
    if verdict == "approved":
        item = interpretation_for(state, review["basis"])
        if item["result_hash"] != review["basis_hash"]:
            raise ConflictError("Tolkningens version är ändrad")
        sources = item["result"]["output"]["evidence"]["sources"]
        fresh_sources(gateways.regulatory, sources)
        check_drafts(gateways.drafts, item)
        if review["kind"] != APPROVE_INTERPRETATION:
            decision["details"] = _adoption(review["kind"], interpretation(item), form)
            state["external"] = _external(state, ident, item, decision, sources, trusted)
    state["decisions"].append(decision)
    state["reviews"] = []
    state["status"] = "queued" if verdict == "approved" else "rejected"


def _adoption(kind, proposal, form):
    fields = ("rule_version", "valid_from", "decision_number")
    model = RuleAdoption
    if kind == DEVELOP:
        fields += ("rule_id", "code_reason", "affected_system", "expected_effect")
        model = CodeRuleAdoption
    try:
        adoption = model.model_validate({k: form.get(k) or None for k in fields})
        if kind == DEVELOP:
            _check_content(f"{adoption.code_reason}\n{adoption.affected_system}\n{adoption.expected_effect}")
        if adoption.valid_from != proposal.effective_on:
            raise InvalidInputError("Giltighetsdagen ska motsvara tolkningens källbundna giltighet")
        if kind == DEVELOP and adoption.rule_id not in proposal.affected_rules:
            raise InvalidInputError("Den antagna regeln måste finnas i tolkningens berörda regler")
        details = adoption.model_dump(mode="json")
        if kind == ACTIVATE:
            details.update(RuleTextCommit(commit=form.get("commit", "")).model_dump(mode="json", exclude={"note"}))
        return details
    except ValidationError as exc:
        raise InvalidInputError("Fyll i giltighet, regelversion och obligatoriskt genomförandeunderlag") from exc


def _external(state, ident, item, decision, sources, trusted):
    details = decision["details"]
    intent = {"kind": decision["kind"], "decision": decision["id"], "status": "queued", "receipt": None}
    if decision["kind"] == ACTIVATE:
        impact = checked_effect(state, item)
        if (impact is None or impact["id"] != decision["effect"] or impact["result_hash"] != decision["effect_hash"]
                or canonical_hash(impact["result"]) != impact["result_hash"]):
            raise ConflictError("Premieeffektens underlag har ändrats")
        previous = matching_parameter(trusted, interpretation(item))
        estimate = impact["result"]["output"]["evidence"]["estimate"]
        label = version_label(previous["rule_id"], previous["rule_version"], previous["valid_from"])
        if label != estimate["current_version"] or previous["value"] != Decimal(estimate["current_value"]):
            raise ConflictError("Beräkningen gäller en annan basversion. Beställ en ny analys.")
        intent["request"] = activation_input(item, decision, ident)
        intent["previous"] = {k: str(previous[k]) for k in ("value", "valid_from", "rule_version")}
        intent["run"] = item["run"]
    else:
        source = next(s for s in sources if s["handle"] == item["inputs"]["source"])
        order = ChangeRequestOrder(
            origin=ChangeRequestOrigin(channel=ORIGIN, reference=f"{ident}/{decision['id']}"),
            kind="rule_change", title=f"Inför {details['rule_id']} v{details['rule_version']}",
            need=interpretation(item).summary, motivation=details["code_reason"],
            affected_system=details["affected_system"], acceptance=details["expected_effect"],
            source_refs=f"{source['handle']} v{source['version'] or 'okänd'} · sha {source['sha256']}",
            decision_ref=f"BO-{ident}/{decision['id'][:12]}",
            rule_version=details["rule_version"], effective_on=details["valid_from"],
        )
        intent["request"] = order.model_dump(mode="json")
    return intent


def activation_receipt(service, task):
    proposal = service.approvals.get(_proposal_id(task))
    if proposal is None:
        return None
    if (proposal.operation != ACTIVATION or proposal.input != task["request"] or proposal.run_id != task["run"]
            or proposal.proposed_by != COMPLIANCE_AGENT.id or proposal.proposed_by_team != COMPLIANCE_AGENT.team):
        raise ConflictError("Godkännandekön innehåller ett motstridigt kvitto. Stäm av förslaget manuellt")
    return proposal


def _proposal_id(task):
    return uuid5(NAMESPACE_URL, f"artificiellalecta/approval/{task['request']['decision_ref']}").hex


def submit_activation(service, task, decision):
    result = service.execute(ACTIVATION, OperationContext(
        actor=COMPLIANCE_AGENT, run_id=task["run"], reason=f"Antagen i {task['request']['decision_ref']}; "
        f"regeltextens commit {decision['details']['commit']}",
    ), task["request"], proposal_id=_proposal_id(task))
    if result.approval_id is None:
        raise ConflictError("Aktiveringsförslaget saknar verifierbart godkännande-id")


def is_pilot_activation(operation, data):
    return operation == ACTIVATION and re.fullmatch(r"BO-[a-f0-9]{32}/[a-f0-9]{12}",
                                                    str(data.get("decision_ref", ""))) is not None


def guard_activation(session, request, actor: Actor, *, service):
    """Spärra verkställighet av en ändrad, främmande eller återtagen pilotversion."""
    if not is_pilot_activation(request.operation, request.input):
        return
    reference = request.input["decision_ref"]
    ident = reference.removeprefix("BO-").partition("/")[0]
    if (session is None or session.connection().dialect.name != "sqlite"
            or not inspect(session.connection()).has_table(missions.name)):
        raise ApprovalError("Bolagspilotens verifierbara beslutsunderlag saknas")
    row = session.execute(select(missions).where(missions.c.id == ident,
        missions.c.environment == "demo", missions.c.owner == actor.id)).mappings().one_or_none()
    if not row:
        raise ApprovalError("Bolagsuppdraget tillhör en annan operatör eller miljö")
    state = row["state"]
    task = state["external"]
    if (not task or task["kind"] != ACTIVATE or task["request"] != request.input or task["run"] != request.run_id
            or _proposal_id(task) != request.id or task["receipt"] != request.id
            or state["status"] not in ("waiting_external", "running")):
        raise ApprovalError("Bolagsuppdraget saknar ett aktuellt förslag för denna version")
    decision = next(d for d in state["decisions"] if d["id"] == task["decision"])
    try:
        item = interpretation_for(state, decision["basis"])
        expected = activation_input(item, decision, ident)
        impact = checked_effect(state, item)
        if (decision["decision"] != "approved" or decision["kind"] != ACTIVATE or decision["by"] != actor.id
                or decision["basis_hash"] != item["result_hash"] or expected != request.input
                or impact is None or impact["id"] != decision["effect"] or impact["result_hash"] != decision["effect_hash"]
                or canonical_hash(impact["result"]) != impact["result_hash"]):
            raise ConflictError("Beslutet gäller ett annat underlag")
        if service.decision(ACTIVATION).effective.value != "APPROVAL":
            raise ConflictError("Tjänstelagrets mandat för förslaget har ändrats")
        fresh_sources(RegulatoryGateway(), item["result"]["output"]["evidence"]["sources"])
        check_drafts(DraftGateway(), item)
        change = interpretation(item).parameter_changes[0]
        baseline = versions_on(session, change.valid_from, keys=(change.key,)).get(change.key)
        previous = task["previous"]
        if (baseline is None or plain(baseline.value) != Decimal(previous["value"])
                or baseline.rule_version != previous["rule_version"]
                or baseline.valid_from.isoformat() != previous["valid_from"]):
            raise ConflictError("Parameterns basversion är ändrad")
    except (ConflictError, InvalidInputError, GatewayError) as exc:
        raise ApprovalError(f"Bolagsuppdragets förslag behöver granskas igen. {exc}") from exc
