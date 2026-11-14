"""Bolagsorkestratörens lokala uppdragskö och körning via harness."""

from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

from agents.assignments import (
    mandate_from_interpretation,
    request_for_impact,
    request_for_interpretation,
    run_assignment,
)
from agents.company_capabilities import (
    ACTIVATE,
    APPROVE_INTERPRETATION,
    DEVELOP,
    IMPACT,
    INTERPRET,
    activation_evidence,
    check_drafts,
    current_items,
    fresh_sources,
    interpretation,
    interpretation_for,
    matching_parameter,
)
from agents.company_coordination import Coordination
from agents.company_decisions import activation_receipt, decide, submit_activation
from agents.company_store import MissionStore, now
from agents.company_team_catalog import team_catalog
from agents.company_tools import SKILL, TEAM
from agents.delegation import CUMULATIVE, RootLedger
from agents.ecosystem import REPO_ROOT, Ecosystem, Limits
from agents.flows.questions import policy_ref
from agents.flows.store import canonical_hash
from agents.gateways import GatewayError, Gateways, ReadRegulatoryDocumentInput
from agents.gateways.drafts import _check_content
from agents.journal import DEFAULT_JOURNAL_DIR
from agents.run import RunRequest, RunStatus
from agents.skills import SkillRegistry
from agents.trace import read_run_trace
from services import ServiceLayer
from services.change_requests import ChangeRequestOrder
from services.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    ServiceError,
)

CONTRACT = 1
MAX_BRIEFS = 6
MAX_RUNS = 18
# Ordningen följer sparade anspråk och resultat. Varje klick kör högst ett segment.
ACTIONS = {"queued", "waiting_external", "reconciliation_required"}
SOURCE_SKILLS = ("list_regulatory_documents", "read_regulatory_document")


class CompanyMissions:
    def __init__(self, factory, trusted, requests, releases, *, dataset, ai=None, gateways=None, journal_dir=None):
        self.store = MissionStore(factory, dataset=dataset)
        self.store.initialize()
        self.trusted, self.requests, self.releases = trusted, requests, releases
        self.ai = ai
        self.gateways = gateways or Gateways()
        self.journal_dir = Path(journal_dir or DEFAULT_JOURNAL_DIR)
        if self.ai is not None:
            self.eco = Ecosystem.load(roles=ai.config.roles)
            self.skills = SkillRegistry.build(self.eco, trusted.registry)
            self.policy = canonical_hash({
                "model": policy_ref(self.eco, ai),
                "instructions": {k: (REPO_ROOT / item.instruction).read_text(encoding="utf-8")
                                 for k, item in self.eco.agents.items()},
                "access_register": (trusted.register.path.read_text(encoding="utf-8")
                                    if trusted.register.path else None),
                "contract": CONTRACT,
            })
        self.teams = team_catalog(self.eco if ai is not None else Ecosystem.load())
        self.team_services = {team: ServiceLayer(session_factory=factory, validation_session_factory=factory,
                             registry=trusted.registry, register=trusted.register, rules=trusted.rules,
                             agent_role=f"agent_{team}") for team in ("aktuarie", "compliance")}
        # Ingen anslutning till specialistdata i orkestratörens profil.
        self.profile_service = ServiceLayer(registry=trusted.registry, register=trusted.register, rules=trusted.rules)

    def start(self, ident, actor, goal):
        self._active()
        self._identifier(ident)
        goal = self._goal(goal)
        return self.store.create(ident, actor, {
            "status": "queued", "contract": CONTRACT, "policy": self.policy, "claim": None,
            "briefs": [{"key": ident, "goal": goal}], "assignments": {}, "decisions": [], "reviews": [],
            "runs": [], "messages": [], "external": None, "effects": [], "stop": None,
            "root_run": f"run-{ident}", "budget": self.eco.delegation.root_limits.model_dump(),
        })

    @staticmethod
    def _identifier(value):
        try:
            if UUID(hex=value).hex != value:
                raise ValueError
        except (ValueError, TypeError, AttributeError) as exc:
            raise InvalidInputError("Ogiltig beställningsnyckel") from exc

    @staticmethod
    def _goal(goal):
        goal = goal.strip()
        if not 1 <= len(goal) <= 3200:
            raise InvalidInputError("Ange en beställning på 1–3 200 tecken")
        _check_content(goal)
        return goal

    def follow_up(self, ident, actor, revision, key, goal):
        self._active()
        self._identifier(key)
        brief = {"key": key, "goal": self._goal(goal)}
        with self.store.edit(ident, actor, revision=revision, replay=lambda state: brief in state["briefs"]) as state:
            previous = next((b for b in state["briefs"] if b["key"] == key), None)
            if previous is not None:
                if previous != brief:
                    raise ConflictError("Beställningsnyckeln används för en annan precisering")
                return
            if (state["status"] in {"running", "reconciliation_required", "taken_over"} or state["claim"]
                    or state["external"] or len(state["briefs"]) >= MAX_BRIEFS):
                raise ConflictError("Uppdraget kan inte preciseras i sitt nuvarande läge")
            for item in current_items(state):
                if item["status"] == "queued":
                    item["status"] = "superseded"
            state["briefs"].append(brief)
            state.update(status="queued", reviews=[], stop=None)

    def review(self, ident, actor, revision, seen, verdict, form):
        # Domänläsningar får en egen transaktion. CAS sparar beslutet bara om samma
        # uppdragsrevision fortfarande ägs av operatören.
        row = self.store.get(ident, actor)
        if row["revision"] != revision:
            raise ConflictError("Uppdraget har ändrats. Läs om sidan")
        state = row["state"]
        if verdict == "approved" and state["reviews"] and state["reviews"][0]["kind"] != APPROVE_INTERPRETATION:
            self._active()
        decide(state, ident, actor, seen, verdict, form, gateways=self.gateways, trusted=self.trusted)
        with self.store.edit(ident, actor, revision=revision) as saved:
            saved.update(state)

    def take_over(self, ident, actor, revision, note):
        note = note.strip()
        if not 1 <= len(note) <= 500:
            raise InvalidInputError("Ange skälet för övertagandet")
        _check_content(note)
        with self.store.edit(ident, actor, revision=revision) as state:
            if state["status"] == "running":
                raise ConflictError("En körning äger uppdraget. Vänta eller stäm av ett avbrott först.")
            for item in current_items(state):
                if item["status"] == "queued":
                    item["status"] = "cancelled"
            state.update(status="taken_over", claim=None, stop=note, takeover={"by": actor.id, "at": now()})

    def interrupted(self, ident, actor, revision):
        """Operatören intygar att den tidigare lokala processen har stoppats."""
        with self.store.edit(ident, actor, revision=revision) as state:
            if state["status"] != "running" or state["claim"] is None:
                raise ConflictError("Det finns inget avbrutet anspråk")
            claim = state["claim"]
            for entry in state["runs"]:
                if entry["run"] == claim and entry["usage"] is None:
                    _reserve_interrupted(entry)
            for item in current_items(state):
                if item["run"] == claim and item["status"] == "running":
                    item["status"] = "interrupted"
            state.update(status="reconciliation_required", claim=None,
                         stop="Avbrutet anspråk. Kontrollera körspåret och domänkvitton före fortsatt arbete.")
            state.setdefault("interruptions", []).append({"run": claim, "by": actor.id, "at": now()})

    def process(self, ident, actor, revision):
        self._active()
        with self.store.edit(ident, actor, revision=revision) as state:
            if state["status"] not in ACTIONS or state["claim"]:
                raise ConflictError("Uppdraget kan inte köras i sitt nuvarande läge")
            if state["contract"] != CONTRACT or state["policy"] != self.policy:
                raise ConflictError("Körpolicyn har ändrats. Uppdraget behöver manuell avstämning.")
            task = state["external"]
            if state["status"] == "reconciliation_required" and task is None:
                raise ConflictError("Avbruten agentkörning kräver övertagande; den körs inte om")
            item = next((i for i in current_items(state) if i["status"] == "queued"), None)
            claim = state["root_run"] if not state["runs"] and not task else f"run-{uuid4().hex}"
            limits = None if task else self._limits(state, item["team"] if item else TEAM)
            if not task and limits is None:
                state.update(status="budget_stopped", stop="Uppdragets körbudget eller segmenttak är förbrukat.")
                return
            state.update(status="running", claim=claim, stop=None)
            if item:
                item.update(status="running", run=claim)
            if limits:
                state["runs"].append({"run": claim, "brief": len(state["briefs"]), "limits": limits.model_dump(),
                                      "status": "running", "usage": None, "assignment": item["id"] if item else None})
        try:
            if task:
                self._process_external(ident, actor, claim, state, task)
            else:
                outcome = self._run(ident, actor, state, claim, limits, item)
                self._save_run(ident, actor, claim, outcome, item)
        except (GatewayError, ServiceError) as exc:
            # Även vid nekad extern fortsättning kontrolleras kvitton före ett nytt försök.
            self._stop_claim(ident, actor, claim, str(exc), external=task is not None)
        except Exception:
            try:
                self._stop_claim(ident, actor, claim, "Körningen avbröts. Kontrollera journal och domänkvitton.",
                                 external=True)
            except ConflictError:
                # Ett övertaget anspråk får inte kunna skriva tillbaka resultat eller status.
                pass
            raise

    def _stop_claim(self, ident, actor, claim, note, *, external):
        with self.store.edit(ident, actor, claim=claim) as state:
            for entry in state["runs"]:
                if entry["run"] == claim and entry["usage"] is None:
                    _reserve_interrupted(entry)
            for item in current_items(state):
                if item["run"] == claim and item["status"] == "running":
                    item.update(status="interrupted", result={"summary": note})
            state.update(claim=None, stop=note,
                         status="reconciliation_required" if external else "needs_human")

    def _active(self):
        if self.ai is None:
            raise ConflictError("Pilotens körning är avstängd. Sparade uppdrag går att öppna.")

    def _limits(self, state, team):
        if len(state["runs"]) >= MAX_RUNS:
            return None
        used = {key: sum((run["usage"] or {}).get(key, 0) for run in state["runs"])
                for key in CUMULATIVE.values()}
        left = RootLedger(Limits(**state["budget"]), base=used).remaining({})
        remaining = {k: round(v, 6) if k == "max_cost_usd" else int(v) for k, v in left.items()}
        if min(remaining.values()) <= 0:
            return None
        return self.eco.agent_limits(self.eco.teams[team].lead).narrowed(Limits(**remaining))

    def _run(self, ident, actor, state, claim, limits, item):
        links = {"root_run_id": state["root_run"]}
        mandate = None
        gateways = self.gateways
        if item is None:
            request = RunRequest(
                task_id=ident, target_team=TEAM, limits=limits, **links,
                goal=state["briefs"][-1]["goal"],
                background=("Ursprunglig beställning: " + state["briefs"][0]["goal"] if len(state["briefs"]) > 1 else ""),
                result_schema="CoordinationAnswer", only_skills=(*SOURCE_SKILLS, SKILL),
                constraints=("Använd status för aktuellt sparat läge. Lägg aldrig fram ett verksamhetsresultat utan underlag.",),
            )
            service = self.profile_service
            gateways = replace(gateways, coordination=Coordination(
                self.store, gateways, ident, actor, claim, teams=self.teams,
            ))
        else:
            service = self.team_services[item["team"]]
            inputs = item["inputs"]
            links.update(parent_run_id=item["ordered_by_run"], depth=1)
            if item["capability"] == INTERPRET:
                source = gateways.regulatory.read_document(ReadRegulatoryDocumentInput(handle=inputs["source"])).document
                if source.sha256 != inputs["source_hash"]:
                    raise ConflictError("Beställd källa har ändrats före tolkningen")
                request = request_for_interpretation(source.handle, task_id=item["id"], limits=limits, **links)
                request = request.model_copy(update={
                    "background": inputs["goal"],
                    "result_schema": "CompanyInterpretation",
                    "goal": request.goal + " Ange change_kind och effective_on. Beskriv ny logik och beroenden "
                    "i code_dependency. Markera blandad påverkan explicit. Välj interpretation_only om bara "
                    "tolkning är möjlig utan regeländring, och unsupported när verksamhetsstöd saknas.",
                    "only_skills": (*SOURCE_SKILLS, "get_product_parameters", "write_draft"),
                })
            else:
                basis = interpretation_for(state, inputs["basis"])
                if basis["result_hash"] != inputs["hash"]:
                    raise ConflictError("Beställd tolkning har ändrats")
                fresh_sources(gateways.regulatory, basis["result"]["output"]["evidence"]["sources"])
                check_drafts(gateways.drafts, basis)
                matching_parameter(self.trusted, interpretation(basis))
                output = basis["result"]["output"]
                mandate = mandate_from_interpretation(output, ref=f"pc-{item['id']}")
                request = request_for_impact(mandate, task_id=item["id"], limits=limits, **links)
                request = request.model_copy(update={
                    "background": inputs.get("goal", ""),
                    "only_skills": ("estimate_parameter_change_impact", "write_draft"),
                })
        return run_assignment(self.ai, self.eco, self.skills, service, request, parameter_change=mandate,
                              gateways=gateways, run_id=claim, journal_dir=self.journal_dir)

    def _save_run(self, ident, actor, claim, outcome, item):
        result = outcome.result.model_dump(mode="json")
        with self.store.edit(ident, actor, claim=claim) as state:
            entry = state["runs"][-1]
            entry.update(status=result["status"], usage={
                "steps": outcome.steps, "tool_calls": outcome.tool_calls, "cost_usd": result["cost_usd"],
                "elapsed_seconds": round(outcome.elapsed_seconds, 3),
            })
            state["claim"] = None
            if item:
                saved = state["assignments"][item["key"]]
                if result["status"] == "completed" and saved["capability"] == INTERPRET:
                    sources = result["output"]["evidence"]["sources"]
                    if not any(s["handle"] == saved["inputs"]["source"] and
                               s["sha256"] == saved["inputs"]["source_hash"] for s in sources):
                        result.update(status="needs_human", output=None,
                                      summary="Tolkningen saknar verifierat underlag för den beställda källan.")
                if saved["capability"] == IMPACT and result["status"] == "completed":
                    # Endast aggregatet används som sakuppgift i centralen.
                    result["summary"] = "Premieeffekten redovisas i det sparade beräkningsunderlaget."
                saved.update(status=result["status"], result=result, result_hash=canonical_hash(result))
            else:
                if result["output"]:
                    try:
                        _check_content(result["summary"])
                    except GatewayError:
                        result.update(status="needs_human", output=None,
                                      summary="Svaret behöver granskas enligt pilotens dataklass.")
                state["messages"].append({"brief": len(state["briefs"]), "run": claim, "answer": result})
            if result["status"] == RunStatus.BLOCKED:
                state.update(status="needs_human", stop=result["summary"])
            elif result["status"] == RunStatus.LIMIT_REACHED:
                state["status"] = "budget_stopped"
            elif result["status"] == RunStatus.RECONCILIATION_REQUIRED:
                state["status"] = "reconciliation_required"
            elif any(i["status"] == "queued" for i in current_items(state)):
                state["status"] = "queued"
            elif state["reviews"]:
                state["status"] = "waiting_review"
            elif item:
                state["status"] = "queued"
            else:
                answer = (result["output"] or {}).get("result", {})
                status = answer.get("status", "needs_human")
                state["status"] = status if status != "waiting" else "needs_human"

    def _process_external(self, ident, actor, claim, state, task):
        decision = next(d for d in state["decisions"] if d["id"] == task["decision"])
        item = interpretation_for(state, decision["basis"])
        if decision["decision"] != "approved" or item["result_hash"] != decision["basis_hash"]:
            raise ConflictError("Det sparade beslutet gäller ett annat underlag")
        sources = item["result"]["output"]["evidence"]["sources"]
        if task["kind"] == ACTIVATE:
            receipt = activation_receipt(self.trusted, task)
            if receipt is None and not task["receipt"]:
                fresh_sources(self.gateways.regulatory, sources)
                check_drafts(self.gateways.drafts, item)
                matching_parameter(self.trusted, interpretation(item))
                submit_activation(self.trusted, task, decision)
                receipt = activation_receipt(self.trusted, task)
            if receipt is None or (task["receipt"] and task["receipt"] != receipt.id):
                raise ConflictError("Aktiveringsförslaget saknas eller har bytt kvitto")
            observed, status = receipt.model_dump(mode="json"), receipt.status
            if status == "approved":
                observed["effect"] = activation_evidence(self.trusted, task["request"], task["previous"])
                status = "verified" if observed["effect"]["verified"] else "needs_human"
            receipt_id = receipt.id
        elif task["kind"] == DEVELOP:
            order = ChangeRequestOrder.model_validate(task["request"])
            if task["receipt"]:
                receipt = self.requests.get(actor, UUID(task["receipt"]))
            else:
                # Ett förlorat svar får avstämmas även om källan ändrades efter verkställigheten.
                if self.requests.get(actor, self.requests.order_id(order.origin)) is None:
                    fresh_sources(self.gateways.regulatory, sources)
                    check_drafts(self.gateways.drafts, item)
                submitted = self.requests.submit_order(actor, order)
                receipt = self.requests.get(actor, submitted.id)
            if (receipt is None or self.requests.order_id(order.origin) != receipt.id
                    or receipt.origin != order.origin or receipt.draft.model_dump(mode="json")
                    != order.model_dump(mode="json", exclude={"origin"})):
                raise ConflictError("Utvecklingsärendet saknas")
            receipt_id = str(receipt.id)
            release = self.releases.read(actor, receipt.id)
            observed = {"status": receipt.status}
            status = "pending"
            if (receipt.status == "verified" and release and release.approval and release.check and release.check.passed
                    and release.deployment and release.check.version == release.deployment.version):
                status = "verified"
                observed.update(review_id=release.approval.id, approval_by=release.approval.actor_id,
                                review_hash=release.approval.bundle.fingerprint,
                                code=release.approval.bundle.candidate.head,
                                tests=release.approval.bundle.candidate.references.test_ref,
                                deployment=release.deployment.model_dump(mode="json"),
                                check=release.check.model_dump(mode="json"))
            elif release and release.stopped:
                status = "needs_human"
        else:
            raise ConflictError("Okänd domänåtgärd")
        with self.store.edit(ident, actor, claim=claim) as saved:
            saved["claim"] = None
            task.update(receipt=receipt_id, status=status, observed=observed)
            if status in {"verified", "rejected"}:
                saved["effects"].append(task)
                saved.update(external=None, status="queued" if status == "verified" else "rejected")
            else:
                saved.update(external=task, status="waiting_external" if status == "pending" else "needs_human",
                             stop=None if status == "pending" else "Domänutfallet behöver en mänsklig avstämning.")

    def artifact(self, ident, actor, assignment_id, name):
        state = self.store.get(ident, actor)["state"]
        item = next((i for i in state["assignments"].values() if i["id"] == assignment_id), None)
        output = ((item or {}).get("result") or {}).get("output")
        if not output or name not in {d["name"] for d in output["evidence"]["drafts"]}:
            raise NotFoundError("Utkastet saknas")
        check_drafts(self.gateways.drafts, item)
        return self.gateways.drafts.read_draft(item["team"], item["run"], name)

    def trace(self, ident, actor, run):
        state = self.store.get(ident, actor)["state"]
        if not any(r["run"] == run for r in state["runs"]):
            raise NotFoundError("Körningen saknas")
        return read_run_trace(self.journal_dir, run)


def _reserve_interrupted(entry):
    entry.update(status="interrupted", usage={key: entry["limits"][limit] for limit, key in CUMULATIVE.items()})
