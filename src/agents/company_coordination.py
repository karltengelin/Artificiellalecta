"""Samordningsverktyget arbetar med ett betrott anspråk och en aktuell beställning."""

from dataclasses import asdict
from uuid import uuid4

from agents.company_capabilities import (
    ACTIVATE,
    APPROVE_INTERPRETATION,
    CAPABILITIES,
    DEVELOP,
    IMPACT,
    INTERPRET,
    accepted_interpretation,
    check_drafts,
    checked_effect,
    current_items,
    fresh_sources,
    interpretation,
    interpretation_for,
    supports_development,
    supports_parameter,
)
from agents.company_tools import TEAM, CoordinationInput, CoordinationResult
from agents.flows.store import canonical_hash
from agents.gateways import GatewayError, ReadRegulatoryDocumentInput
from agents.gateways.drafts import _check_content
from services.errors import ConflictError, InvalidInputError, ServiceError

MAX_ASSIGNMENTS = 8


class Coordination:
    def __init__(self, store, gateways, ident, actor, run):
        self.store = store
        self.gateways = gateways
        self.ident = ident
        self.actor = actor
        self.run = run

    def invoke(self, team: str, run: str, data: CoordinationInput) -> CoordinationResult:
        if team != TEAM or run != self.run:
            raise GatewayError("denied", "Samordningsverktyget kräver orkestratörens aktuella anspråk", security=True)
        try:
            if data.action in ("status", "catalog"):
                state = self.store.get(self.ident, self.actor)["state"]
                if state["claim"] != run:
                    raise ConflictError("Anspråket har avslutats")
                return CoordinationResult(data=self.status(state) if data.action == "status" else self.catalog(state))
            with self.store.edit(self.ident, self.actor, claim=run) as state:
                result = self.order(state, data) if data.action == "order" else self.review(state, data)
            return CoordinationResult(data=result)
        except ServiceError as exc:
            raise GatewayError("contract", str(exc)) from exc

    @staticmethod
    def catalog(state):
        items = [item for item in current_items(state)
                 if item["capability"] == INTERPRET and item["status"] == "completed"]
        names = {INTERPRET}
        for item in items:
            proposal = interpretation(item)
            if supports_parameter(proposal):
                if accepted_interpretation(state, item):
                    names.add(IMPACT)
                    if proposal.draft_names and checked_effect(state, item):
                        names.add(ACTIVATE)
                else:
                    names.add(APPROVE_INTERPRETATION)
            if supports_development(proposal):
                names.add(DEVELOP)
        active = {name: asdict(value) for name, value in CAPABILITIES.items() if name in names}
        if APPROVE_INTERPRETATION in names:
            active[APPROVE_INTERPRETATION] = {"team": "compliance", "when": "Granska före parametermandat",
                "input": "Färdigt tolkningsunderlag", "result": "Mänskligt beslut om tolkningen"}
        return {"capabilities": active}

    @staticmethod
    def status(state):
        items = []
        for item in current_items(state):
            view = {k: item[k] for k in ("id", "capability", "team", "status", "run", "result_hash")}
            if item["result"]:
                output = item["result"].get("output")
                if output:
                    view["sources"] = output["evidence"]["sources"]
                    estimate = output["evidence"].get("estimate")
                    if estimate:
                        view["estimate_status"] = estimate["totals_status"]
                        view["estimate_period"] = [estimate["period_from"], estimate["period_to"]]
                    else:
                        view["result"] = output["result"]
                else:
                    view["message"] = item["result"]["summary"]
                    view["uncertainties"] = item["result"].get("uncertainties", [])
            items.append(view)
        return {"assignments": items, "reviews": state["reviews"],
                "decisions": [d for d in state["decisions"] if d["brief"] == len(state["briefs"])],
                "external": state["external"], "effects": state["effects"]}

    def order(self, state, data):
        name = data.capability
        if name not in (INTERPRET, IMPACT) or data.key is None:
            raise InvalidInputError("Välj en beställningsbar förmåga och en stabil nyckel")
        if name == INTERPRET:
            if not data.source or not data.goal or data.basis:
                raise InvalidInputError("Ange bevakningskälla och ett mål för tolkningen")
            _check_content(data.goal)
            source = self.gateways.regulatory.read_document(ReadRegulatoryDocumentInput(handle=data.source)).document
            if source.kind != "bevakning" or not source.fictional:
                raise InvalidInputError("I piloten får Compliance bara utreda fiktiva bevakningskällor")
            inputs = {"source": data.source, "source_hash": source.sha256, "goal": data.goal}
        else:
            if data.source or data.goal:
                raise InvalidInputError("Premieanalysens mål och källa kommer från det granskade underlaget")
            item = interpretation_for(state, data.basis)
            if not supports_parameter(interpretation(item)) or not accepted_interpretation(state, item):
                raise InvalidInputError("Premieeffekt kräver en mänskligt godkänd tolkning av exakt en stödd parameter")
            inputs = {"basis": item["id"], "hash": item["result_hash"]}
        brief = len(state["briefs"])
        fingerprint = canonical_hash({"name": name, "brief": brief, "inputs": inputs})
        if existing := state["assignments"].get(data.key):
            if existing["fingerprint"] != fingerprint:
                raise ConflictError("Beställningsnyckeln är redan bunden till ett annat underlag")
            return {"id": existing["id"], "status": existing["status"]}
        equivalent = next((i for i in current_items(state) if i["fingerprint"] == fingerprint), None)
        if equivalent:
            raise ConflictError(f"Underlaget är redan beställt med nyckeln {equivalent['key']}")
        if len(state["assignments"]) >= MAX_ASSIGNMENTS:
            raise ConflictError("Uppdragets tak för specialistbeställningar är nått")
        if state["external"] is not None or state["reviews"]:
            raise ConflictError("En granskning eller verkställighet väntar redan")
        item = {"id": uuid4().hex, "key": data.key, "brief": brief, "capability": name,
                "team": CAPABILITIES[name].team, "schema": CAPABILITIES[name].result, "fingerprint": fingerprint,
                "inputs": inputs, "ordered_by_run": self.run, "status": "queued", "run": None,
                "result": None, "result_hash": None}
        state["assignments"][data.key] = item
        return {"id": item["id"], "status": item["status"]}

    def review(self, state, data):
        if data.capability not in (APPROVE_INTERPRETATION, ACTIVATE, DEVELOP) or data.key or data.source or data.goal:
            raise InvalidInputError("Ange vilken granskning och vilket deluppdrag som avses")
        basis = interpretation_for(state, data.basis)
        if any(d["basis"] == basis["id"] and d["decision"] == "approved" and d["kind"] in (ACTIVATE, DEVELOP)
               for d in state["decisions"]):
            raise ConflictError("Det här regelunderlaget har redan antagits")
        proposal = interpretation(basis)
        fresh_sources(self.gateways.regulatory, basis["result"]["output"]["evidence"]["sources"])
        check_drafts(self.gateways.drafts, basis)
        effect = None
        if data.capability == DEVELOP:
            if not supports_development(proposal):
                raise InvalidInputError("Kodöverlämning kräver en renodlad kodändring med regelutkast och giltighet")
        else:
            if not supports_parameter(proposal):
                raise InvalidInputError("Granskningen stöder exakt en befintlig parameter; blandade ändringar kräver bedömning")
            if data.capability == ACTIVATE:
                effect = checked_effect(state, basis)
                if not accepted_interpretation(state, basis) or effect is None or not proposal.draft_names:
                    raise InvalidInputError("Regelbeslutet kräver regelutkast, godkänd tolkning och utredd premieeffekt")
            elif accepted_interpretation(state, basis):
                raise ConflictError("Tolkningen för detta underlag är redan godkänd")
        if any(item["status"] == "queued" for item in current_items(state)) or state["external"] is not None:
            raise ConflictError("Ett deluppdrag eller en verkställighet väntar")
        review = {"kind": data.capability, "basis": basis["id"], "basis_hash": basis["result_hash"],
                  "brief": len(state["briefs"]), "effect": effect["id"] if effect else None,
                  "effect_hash": effect["result_hash"] if effect else None}
        review["hash"] = canonical_hash(review)
        if state["reviews"] and state["reviews"] != [review]:
            raise ConflictError("En annan granskning väntar redan")
        state["reviews"] = [review]
        return {"review": review}
