"""Genomförandekontrakt och underlagskrav för bolagspiloten."""

from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256

from agents.flows.store import canonical_hash
from agents.gateways import GatewayError, ReadRegulatoryDocumentInput
from agents.results import CompanyInterpretation
from services import Actor, OperationContext
from services.errors import ConflictError, InvalidInputError
from services.operations.product_parameters import RULE_OF, ParameterChangeInput

INTERPRET = "interpret_rule"
IMPACT = "estimate_premium_effect"
DEVELOP = "prepare_development"
ACTIVATE = "prepare_parameter_activation"
APPROVE_INTERPRETATION = "approve_interpretation"
ACTIVATION = "schedule_product_parameter_change"
ORIGIN = "company_mission"
VERIFIER = Actor.system("company_orchestrator")


def current_items(state):
    return [item for item in state["assignments"].values() if item["brief"] == len(state["briefs"])]


def fresh_sources(regulatory, sources):
    for saved in sources:
        try:
            live = regulatory.read_document(ReadRegulatoryDocumentInput(handle=saved["handle"])).document
        except FileNotFoundError as exc:
            raise GatewayError("not_found", "Det granskade källdokumentet saknas") from exc
        if live.sha256 != saved["sha256"]:
            raise ConflictError("Källunderlaget har ändrats. Lägg till en precisering och beställ ny tolkning.")


def check_drafts(drafts, item):
    evidence = item["result"]["output"]["evidence"]
    for draft in evidence["drafts"]:
        try:
            content = drafts.read_draft(item["team"], item["run"], draft["name"])
        except FileNotFoundError as exc:
            raise GatewayError("not_found", "Det granskade specialistutkastet saknas") from exc
        if sha256(content.encode("utf-8")).hexdigest() != draft["sha256"]:
            raise ConflictError("Specialistutkastet har ändrats. Beställ ett nytt granskningsunderlag.")


def interpretation(item):
    data = item["result"]["output"]
    if data["schema"] != "CompanyInterpretation" or canonical_hash(item["result"]) != item["result_hash"]:
        raise ConflictError("Tolkningens sparade underlag kan inte verifieras")
    return CompanyInterpretation.model_validate(data["result"])


def interpretation_for(state, ident):
    item = next((i for i in current_items(state) if i["id"] == ident and
                 i["capability"] == INTERPRET and i["status"] == "completed"), None)
    if not item:
        raise InvalidInputError("Ange ett färdigt tolkningsunderlag från den aktuella beställningen")
    return item


def supports_parameter(proposal):
    return (proposal.change_kind == "parameter" and len(proposal.parameter_changes) == 1
            and proposal.parameter_changes[0].key in RULE_OF
            and proposal.parameter_changes[0].rule_id == RULE_OF[proposal.parameter_changes[0].key]
            and proposal.effective_on == proposal.parameter_changes[0].valid_from)


def supports_development(proposal):
    return bool(proposal.change_kind == "code" and not proposal.parameter_changes and proposal.effective_on
                and proposal.affected_rules and proposal.draft_names and proposal.code_dependency.strip())


def accepted_interpretation(state, item):
    return any(d["kind"] == APPROVE_INTERPRETATION and d["decision"] == "approved"
               and d["basis"] == item["id"] and d["basis_hash"] == item["result_hash"]
               and d["brief"] == len(state["briefs"]) for d in state["decisions"])


def checked_effect(state, item):
    return next((a for a in reversed(current_items(state)) if a["capability"] == IMPACT
                 and a["inputs"]["basis"] == item["id"] and a["status"] == "completed"), None)


def matching_parameter(trusted, proposal):
    change = proposal.parameter_changes[0]
    before = parameter_on(trusted, change.key, change.valid_from - timedelta(days=1))
    after = parameter_on(trusted, change.key, change.valid_from)
    if before is None or after != before or before["value"] != change.current_value:
        raise ConflictError("Parameterns utgångsvärde eller giltighet har ändrats. Ny tolkning krävs.")
    return before


def parameter_on(trusted, key, on: date):
    listing = trusted.execute("get_product_parameters", OperationContext(actor=VERIFIER),
                              {"on_date": on.isoformat()}).output
    return next((v.model_dump() for v in listing.versions if v.key == key and v.state == "gällande"), None)


def activation_input(item, decision, ident):
    change = interpretation(item).parameter_changes[0]
    details = decision["details"]
    return ParameterChangeInput(
        key=change.key, value=change.new_value, valid_from=change.valid_from,
        rule_version=details["rule_version"], source_ref=item["inputs"]["source"],
        decision_ref=f"BO-{ident}/{decision['id'][:12]}",
    ).model_dump(mode="json")


def activation_evidence(trusted, expected, previous):
    start = date.fromisoformat(expected["valid_from"])
    before = parameter_on(trusted, expected["key"], start - timedelta(days=1))
    after = parameter_on(trusted, expected["key"], start)
    expected_fields = {**expected, "value": Decimal(expected["value"]), "valid_from": start,
                       "rule_id": RULE_OF[expected["key"]]}
    verified = bool(after and before and before["value"] == Decimal(previous["value"]) and
                    before["valid_from"].isoformat() == previous["valid_from"] and
                    before["rule_version"] == previous["rule_version"] and
                    before["valid_to"] == start - timedelta(days=1) and
                    all(after.get(k) == v for k, v in expected_fields.items()))
    return {"verified": verified, "before": _serial(before), "after": _serial(after)}


def _serial(row):
    return {k: str(v) if isinstance(v, (date, Decimal)) else v for k, v in row.items()} if row else None
