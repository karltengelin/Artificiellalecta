"""Pilotens ordinarie webbväg med lokal SQLite, riktigt harness och skriptad modell."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime
from threading import Event
from uuid import UUID, uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from agents.company_capabilities import (
    ACTIVATE,
    APPROVE_INTERPRETATION,
    DEVELOP,
    IMPACT,
)
from agents.company_coordination import Coordination
from agents.company_team_catalog import team_catalog
from agents.company_tools import SKILL, TEAM, CoordinationInput
from agents.deliveries import DeliveryStore, sha256
from agents.gateways import GatewayError, RegulatoryGateway
from ai import AIClient, AIConfig
from ai.providers.fake import FakeProvider, text_result
from ai.tracing import MemoryTraceSink
from models.flow import ArchiveBase, Flow, FlowGateDecision, FlowStep
from services import Actor, OperationContext
from services.change_requests import ReviewReferences
from services.development_demo import Candidate, Evidence
from services.errors import AccessDeniedError, ApprovalError, ConflictError
from services.operations import common
from tests.flow_helpers import (
    call,
    impact_script,
    interpretation_script,
)
from web.app import create_app
from web.config import WebSettings
from web.routes.company_missions import BASE

OPERATOR = Actor.human("karl")
SOURCE = "K-SIM-PARAM-2027"
CHANGE = {"key": "premium_rate_low", "current_value": "0.045", "new_value": "0.05",
          "valid_from": "2027-01-01", "rule_id": "PR-ITP1-001", "rationale": "Den nya fiktiva premiesatsen"}
CODE_SOURCE = "K-SIM-KOD-2027"
ORIGIN = {"Origin": "https://testserver"}
PASSWORD = "ett fiktivt operatörslösenord för test"
QUESTION = "Utred den här nya regeln, visa premieeffekten om den behövs för beslutet och förbered genomförandet."


def answer(status="waiting", *, sources=(), assignments=(), summary="Jag följer det sparade underlaget."):
    return text_result(json.dumps({"status": status, "summary": summary, "source_handles": sources,
                                   "assignment_refs": assignments}, ensure_ascii=False))


def tool(action, **kwargs):
    return call(SKILL, {"action": action, **kwargs}, action + uuid4().hex[:8],
                "Registrera eller läs uppdragsunderlag")


def order(key="tolkning", source=SOURCE, goal="Utred källans regeländring"):
    return tool("order", target_team="compliance", key=key, source=source, goal=goal)


def interpretation(source=SOURCE, kind="parameter"):
    change = CHANGE if kind != "code" else {**CHANGE, "rule_id": "PR-ITP1-013"}
    runs = interpretation_script(source, change)
    result = json.loads(runs[-1].text)
    result.update(change_kind=kind, effective_on="2027-02-01" if kind == "code" else "2027-01-01",
                  code_dependency="")
    if kind not in {"parameter", "mixed"}:
        result["parameter_changes"] = []
    if kind in {"code", "mixed"}:
        result["code_dependency"] = "Motorn behöver pröva ursprungsmånadens regler vid rättelser."
    return [*runs[:-1], text_result(json.dumps(result, ensure_ascii=False))]


def client(*responses):
    config = AIConfig.from_dict({
        "providers": {"test": {"type": "fake"}},
        "models": {"test:flow": {"price": {"input": 0, "output": 0},
                                 "capabilities": {"tools": True, "structured_output": True}}},
        "roles": {"deep": {"model": "test:flow"}, "standard": {"model": "test:flow"}},
    })
    return AIClient(config, sink=MemoryTraceSink(), provider_overrides={"test": FakeProvider(responses)}, environ={})


def hidden(page, name):
    match = re.search(rf'name="{name}" value="([^"]+)"', page.text)
    assert match is not None, page.text
    return match[1]


def login(web):
    page = web.get("/logga-in")
    response = web.post("/logga-in", data={"csrf_token": hidden(page, "csrf_token"),
                                         "username": OPERATOR.id, "password": PASSWORD}, headers=ORIGIN)
    assert response.status_code == 303


class Demo:
    def __init__(self, settings, tmp_path):
        self.settings, self.tmp_path = settings, tmp_path
        self.app = self.web = self.pilot = None
        self.url = None

    def open(self, *, active=True):
        self.app = create_app(settings=self.settings, company_ai=client() if active else None)
        self.web = TestClient(self.app, base_url="https://testserver", follow_redirects=False)
        login(self.web)
        self.pilot = self.app.state.company_missions
        if self.pilot:
            self.pilot.journal_dir = self.tmp_path / "runs"
        return self

    def website(self, *responses):
        self.pilot.ai = client(*responses)

    def start(self, goal=QUESTION + " Källa " + SOURCE):
        data = {"key": uuid4().hex, "goal": goal, "csrf_token": self.session_csrf}
        response = self.web.post(BASE, data=data, headers=ORIGIN)
        assert response.status_code == 303, response.text
        self.url = response.headers["location"]
        return data

    @property
    def session_csrf(self):
        return hidden(self.web.get(BASE), "csrf_token") if self.pilot and self.pilot.ai else (
            self.app.state.operator_auth.resolve(self.web.cookies.get("__Host-al-operator-demo")).csrf_token)

    @property
    def ident(self):
        return self.url.rsplit("/", 1)[-1]

    @property
    def row(self):
        return self.pilot.store.get(self.ident, OPERATOR)

    @property
    def state(self):
        return self.row["state"]

    def action(self, name, *, expected=303, **data):
        fields = {"csrf_token": self.session_csrf, "revision": self.row["revision"], **data}
        response = self.web.post(f"{self.url}/{name}", data=fields, headers=ORIGIN)
        assert response.status_code == expected, response.text
        return response

    def process(self, *responses):
        self.website(*responses)
        self.action("kor")

    def decide(self, verdict="approved", **data):
        review = self.state["reviews"][0]
        self.action("granska", verdict=verdict, seen=review["hash"], **data)

    def interpret(self, source=SOURCE, kind="parameter"):
        self.process(tool("catalog"), order(source=source), answer())
        assert self.state["assignments"]["tolkning"]["status"] == "queued"
        self.process(*interpretation(source, kind))
        item = self.state["assignments"]["tolkning"]
        assert item["status"] == "completed", item
        return item


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "today", lambda: date(2026, 11, 15))
    settings = WebSettings(demo_path=tmp_path / "demo.db", allowed_hosts=("testserver",),
                           operator_password_hash=PasswordHasher().hash(PASSWORD))
    return Demo(settings, tmp_path).open()



def test_fria_fragor_och_skrivskyddad_historik(demo, tmp_path):
    new_form = demo.web.get(BASE)
    assert new_form.status_code == 200
    assert 'name="goal"' in new_form.text
    assert 'name="question_type"' not in new_form.text
    assert "Beståndsstatistik" not in new_form.text
    assert "Agentteam" not in new_form.text
    assert demo.web.get("/central/bolagsuppdrag").status_code == 200

    archive_url = "/central/uppdragsarkiv"
    assert "Inga arkiverade uppdrag" in demo.web.get(archive_url).text
    store = demo.app.state.mission_archive
    store.deliveries = DeliveryStore(tmp_path / "deliveries")
    archive_id = "FLOW-000001"
    waiting_id = "FLOW-000002"
    report_path = store.deliveries.root / archive_id / "v1" / "rapport.md"
    report_path.parent.mkdir(parents=True)
    data = b"# Sparad rapport"
    report_path.write_bytes(data)
    checksum = sha256(data)
    with store.factory() as session:
        ArchiveBase.metadata.create_all(session.connection())
        session.add_all([
            Flow(flow_id=archive_id, flow_type="product_report", definition_version="1",
                 status="completed", input={"month": "2026-10"}, created_by=OPERATOR.id,
                 finished_at=datetime.now(UTC)),
            Flow(flow_id=waiting_id, flow_type="rule_change_parameter", definition_version="1",
                 status="waiting_gate", input={}, created_by=OPERATOR.id),
        ])
        session.flush()
        session.add(FlowStep(flow_id=archive_id, step_key="render", position=1, kind="system",
                             title="Levererad rapport", status="completed", result_hash=checksum,
                             result={"delivery": {"version": 1, "files": {"rapport.md": checksum}}}))
        session.add(FlowGateDecision(flow_id=archive_id, step_key="granska", decision="approved",
                                     decided_by=OPERATOR.id, bound_steps=["render"], bound_hash=checksum))
        session.commit()

    assert waiting_id in demo.web.get(archive_url).text
    for path in (f"/floden/{archive_id}", f"/team/aktuarie/rapporter/{archive_id}"):
        archived = demo.web.get(path)
        assert archived.status_code == 200
        assert "Sparade beslut" in archived.text
        assert checksum in archived.text
    pending = demo.web.get(f"/floden/{waiting_id}")
    assert pending.status_code == 200
    assert "waiting_gate" in pending.text
    assert "<form" not in pending.text.split("<main", 1)[1]
    assert demo.web.post(f"/floden/{waiting_id}/grind", data={"decision": "approved"}).status_code == 404
    assert demo.web.post("/floden", data={"flow_type": "rule_change_parameter"}).status_code == 405
    assert demo.web.post("/team/aktuarie/rapporter", data={"month": "2026-10"}).status_code == 405

    download = f"/team/aktuarie/rapporter/{archive_id}/leverans/1/rapport.md"
    assert demo.web.get(download).content == data
    report_path.write_bytes(b"changed")
    assert demo.web.get(download).status_code == 409
    guest = TestClient(demo.app, base_url="https://testserver", follow_redirects=False)
    assert guest.get(download).status_code in (303, 401, 403)


def test_parameter_via_webb_med_omstart_och_avstamning(demo, monkeypatch):
    assert BASE in demo.web.get("/central").text
    form = demo.start()
    assert demo.web.post(BASE, data=form, headers=ORIGIN).headers["location"] == demo.url
    assert demo.web.post(BASE, data={**form, "goal": "Annat mål"}, headers=ORIGIN).status_code == 409
    demo.process(order(), order(), order(goal="Ändrat mål under samma nyckel"), answer())
    assert list(demo.state["assignments"]) == ["tolkning"]
    demo.open()
    demo.process(*interpretation())
    item = demo.state["assignments"]["tolkning"]
    assert item["status"] == "completed"
    demo.process(tool("status"), tool("review", review_kind=APPROVE_INTERPRETATION, basis=item["id"]),
                 answer(assignments=[item["id"]]))
    assert "Godkänn tolkning för analysmandat" in demo.web.get(demo.url).text
    path = f"{demo.url}/utkast/{item['id']}/regeldiff.md"
    assert demo.web.get(path).status_code == 200
    assert demo.web.get(f"{demo.url}/spar/{item['run']}").status_code == 200
    demo.open()
    review = demo.state["reviews"][0]
    demo.action("granska", expected=409, verdict="approved", seen="fel")
    with pytest.raises(AccessDeniedError):
        demo.pilot.review(demo.ident, Actor.agent("company_orchestrator"), demo.row["revision"],
                          review["hash"], "approved", {})
    demo.decide()
    demo.process(tool("catalog"), tool("order", target_team="aktuarie", key="premie", basis=item["id"]), answer())
    demo.process(*impact_script(CHANGE))
    assert demo.state["assignments"]["premie"]["result"]["output"]["evidence"]["estimate"]["key"] == CHANGE["key"]
    demo.process(tool("status"), tool("review", review_kind=ACTIVATE, basis=item["id"]), answer())
    demo.decide(rule_version="1.1", valid_from=CHANGE["valid_from"], commit="abcdef1")
    assert len(demo.state["decisions"]) == 2
    original = demo.pilot.trusted.execute

    def lose_response(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[0] == "schedule_product_parameter_change":
            raise RuntimeError("avbrott efter skrivning")
        return result

    with monkeypatch.context() as patched:
        patched.setattr(demo.pilot.trusted, "execute", lose_response)
        with pytest.raises(RuntimeError, match="avbrott"):
            demo.pilot.process(demo.ident, OPERATOR, demo.row["revision"])
    assert demo.state["status"] == "reconciliation_required"
    demo.open()
    demo.process()
    task = demo.state["external"]
    approval = task["receipt"]
    assert demo.state["status"] == "waiting_external"
    assert len([a for a in demo.pilot.trusted.approvals.list()
                if a.input.get("decision_ref") == task["request"]["decision_ref"]]) == 1
    ctx = OperationContext(actor=Actor.agent("company_orchestrator"))
    with pytest.raises(ApprovalError):
        demo.pilot.trusted.approve(approval, ctx)
    with pytest.raises(ApprovalError):
        demo.pilot.trusted.approve(approval, OperationContext(actor=Actor.human("other")))
    assert f"arende-{approval}" in demo.web.get("/godkannanden").text
    path = f"/godkannanden/{approval}/godkann"
    assert demo.web.post(path, data={"csrf_token": demo.app.state.csrf_token}, headers=ORIGIN).status_code == 403
    assert demo.web.post(path, data={"csrf_token": demo.session_csrf}, headers=ORIGIN).status_code == 200
    assert demo.pilot.trusted.approvals.get(approval).status == "approved"
    demo.process()
    assert demo.state["effects"][0]["observed"]["effect"]["verified"]
    assert demo.state["external"] is None
    demo.process(tool("status"), answer("answered", assignments=[item["id"]], summary="Premieeffekten finns i analysen."))
    assert demo.state["status"] == "answered"
    assert "Verifierad schemaläggning" in demo.web.get(demo.url).text
    demo.open(active=False)
    assert demo.web.get(demo.url).status_code == 200
    assert "Nya starter är avstängda" in demo.web.get(BASE).text
    assert demo.web.post(BASE, data={**form, "csrf_token": demo.session_csrf}, headers=ORIGIN).status_code == 409


def test_teamkatalogen_visar_profiler_och_pilotens_bestallningsvagar(demo):
    demo.start()
    with demo.pilot.store.edit(demo.ident, OPERATOR) as state:
        state["claim"] = "test-catalog"
    coord = Coordination(demo.pilot.store, demo.pilot.gateways, demo.ident, OPERATOR, "test-catalog",
                         teams=demo.pilot.teams)
    output = coord.invoke(TEAM, "test-catalog", CoordinationInput(action="catalog")).data
    teams = output["teams"]
    assert set(teams) == set(demo.pilot.eco.team_ids) and TEAM not in teams
    compliance = teams["compliance"]
    assert compliance["agent_count"] == 1 and compliance["lead"] == "compliance_agent"
    assert "kundkonsekvenser" in compliance["agents"][0]["description"]
    assert teams["aktuarie"]["company_intake"] and "värderingsunderlag" in teams["aktuarie"]["agents"][0]["description"]
    assert teams["utveckling"]["agents"][0]["runtime"] == "project_11_demo"
    assert teams["utveckling"]["lead"] is None
    assert teams["forsakring"]["agent_count"] == 1 and teams["forsakring"]["company_intake"] is None
    assert teams["ekonomi"]["agent_count"] == 0
    page = demo.web.get(BASE)
    assert "Dina uppdrag" in page.text
    assert "team_catalog" not in page.context and "Agentteam</h2>" not in page.text
    with pytest.raises(GatewayError, match="tar inte emot direkta beställningar"):
        coord.invoke(TEAM, "test-catalog", CoordinationInput(action="order", target_team="forsakring", key="forsakring"))
    assert not demo.state["assignments"]

    eco = demo.pilot.eco
    analyst = eco.agents["actuary_agent"].model_copy(update={"name": "Analytiker", "description": "Beståndsanalys"})
    updated = eco.model_copy(update={"agents": {**eco.agents, "analyst": analyst}})
    actuarial = team_catalog(updated)["aktuarie"]
    assert actuarial["agent_count"] == 2
    assert [p["lead"] for p in actuarial["agents"]] == [True, False]


def code_sources(demo, *handles):
    root = demo.tmp_path / "sources"
    (root / "04_regulatoriskt/03_bevakning").mkdir(parents=True)
    from agents.ecosystem import REPO_ROOT

    for rule in (REPO_ROOT / "01_domän/produktregler").glob("PR-ITP1-*.md"):
        dest = root / "01_domän/produktregler" / rule.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(rule.read_bytes())
    for handle in handles:
        (root / "04_regulatoriskt/03_bevakning" / f"{handle}-prov.md").write_text(
            f"# {handle} – FIKTIV testkälla\n\n**Version:** 1.0\n\n"
            "Rättelser ska bedömas enligt särskilda övergångsvillkor för ursprungsmånaden.\n", encoding="utf-8")
    demo.pilot.gateways = replace(demo.pilot.gateways, regulatory=RegulatoryGateway(root))
    return root


def test_kod_till_projekt_elva_och_verifierat_demoutfall(demo, monkeypatch):
    demo.start(QUESTION + " Källa " + CODE_SOURCE)
    item = demo.interpret(CODE_SOURCE, "code")
    demo.process(tool("status"), tool("review", review_kind=DEVELOP, basis=item["id"]), answer())
    demo.decide(rule_id="PR-ITP1-013", rule_version="1.2", valid_from="2027-02-01",
                code_reason="Rättelser kräver ny periodlogik.", affected_system="Premiemotorn",
                expected_effect="Rättelser bedöms på rätt ursprungsmånad.")
    store = demo.pilot.requests
    submit = store.submit_order

    def lost(actor, order):
        submit(actor, order)
        raise RuntimeError("Avbruten överlämning")

    with monkeypatch.context() as patched:
        patched.setattr(store, "submit_order", lost)
        with pytest.raises(RuntimeError, match="Avbruten överlämning"):
            demo.pilot.process(demo.ident, OPERATOR, demo.row["revision"])
    assert demo.state["status"] == "reconciliation_required"
    demo.open()
    demo.process()
    task = demo.state["external"]
    ident = UUID(task["receipt"])
    url = f"/central/utveckling/{ident}"
    change_page = demo.web.get(url)
    assert change_page.status_code == 200 and f'{demo.url}#beslut-' in change_page.text
    store, releases = demo.pilot.requests, demo.pilot.releases
    item_order = store.get(OPERATOR, ident)
    assert len(store.list(OPERATOR)) == 1
    assert item_order.origin.channel == "company_mission" and item_order.origin.reference.startswith(demo.ident)
    assert CODE_SOURCE in item_order.draft.source_refs
    assert store.move(OPERATOR, ident, "new", "in_progress")
    refs = ReviewReferences(code_ref="demo:commit", test_ref="demo:prov")
    assert store.move(OPERATOR, ident, "in_progress", "waiting_review", refs)
    candidate = Candidate(pull_request=ident, base="a" * 40, head="b" * 40, diff="+testad kod",
                          references=refs, checks=(Evidence(name="kodprov", reference="demo:prov",
                                                            passed=True, summary="Verifierat i syntetisk demo"),))
    releases.delivery.stage(candidate)
    bundle = releases.read(OPERATOR, ident, preview=True).preview
    for action, fields in [("approve", {"review": bundle.fingerprint}), ("merge", {}), ("deploy", {}), ("verify", {})]:
        if action != "approve":
            fields["approval_id"] = releases.read(OPERATOR, ident).approval.id
        post = demo.web.post(f"{url}/inforande/{action}", data={"csrf_token": demo.session_csrf, **fields}, headers=ORIGIN)
        assert post.status_code == 303, post.text
    demo.open()
    demo.process()
    observed = demo.state["effects"][0]["observed"]
    assert observed["check"]["passed"] and observed["code"] == candidate.head
    assert observed["tests"] == refs.test_ref
    assert not any(i["capability"] == IMPACT for i in demo.state["assignments"].values())
    assert "Verifierat införande" in demo.web.get(demo.url).text


@pytest.mark.parametrize(("kind", "status"), [("interpretation_only", "answered"), ("mixed", "needs_human"),
                                               ("unsupported", "needs_human")])
def test_specialist_utan_verkstallighet(demo, kind, status):
    demo.start()
    item = demo.interpret(kind=kind)
    if kind == "interpretation_only":
        demo.process(tool("status"), answer(status, assignments=[item["id"]]))
    else:
        demo.process(tool("catalog"), tool("status"),
                     tool("order", target_team="aktuarie", key="nekad", basis=item["id"]),
                     answer(status, assignments=[item["id"]], summary="Detta behöver mänsklig bedömning."))
    assert demo.state["status"] == status
    assert list(demo.state["assignments"]) == ["tolkning"]
    assert not demo.state["reviews"] and not demo.state["effects"]


def test_direktsvar_precisering_och_tillgang(demo):
    demo.start("Vad anger försäkringsvillkoren?")
    assert TestClient(demo.app, base_url="https://testserver").get(demo.url).status_code == 401
    demo.process(call("read_regulatory_document", {"handle": "villkor"}, 1),
                 answer("answered", sources=["villkor"], summary="Se de gällande villkoren för försäkringen."))
    assert demo.state["status"] == "answered"
    assert "villkor" in demo.state["messages"][0]["answer"]["output"]["evidence"]["sources"][0]["handle"]
    key, original_revision = uuid4().hex, demo.row["revision"]
    demo.action("precisera", key=key, goal="Utgå från produktregeln om garantin.")
    demo.action("precisera", key=key, goal="Utgå från produktregeln om garantin.", revision=original_revision)
    assert len(demo.state["briefs"]) == 2 and demo.state["briefs"][0]["goal"].startswith("Vad anger")
    demo.process(answer("needs_information", summary="Vilken del av garantin avses?"))
    assert demo.state["status"] == "needs_information"


def test_kalla_andras_eller_saknas_avslag_och_overtagande(demo):
    root = code_sources(demo, CODE_SOURCE)
    demo.start()
    demo.process(order(source="K-SIM-SAKNAS-2027"), answer("needs_information"))
    assert not demo.state["assignments"]
    demo.action("precisera", key=uuid4().hex, goal=f"Använd den fiktiva källan {CODE_SOURCE}.")
    item = demo.interpret(CODE_SOURCE, "code")
    demo.process(tool("review", review_kind=DEVELOP, basis=item["id"]), answer())
    path = next((root / "04_regulatoriskt/03_bevakning").glob("*.md"))
    original = path.read_bytes()
    path.write_bytes(original + b"changed")
    review = demo.state["reviews"][0]
    demo.action("granska", expected=409, verdict="approved", seen=review["hash"])
    demo.decide("rejected", note="Beroendet behöver ny bedömning")
    assert demo.state["status"] == "rejected"
    assert demo.state["decisions"][0]["decision"] == "rejected" and not demo.state["effects"]
    demo.action("ta-over", note="Jag fortsätter med nytt källunderlag")
    assert demo.state["status"] == "taken_over"


def test_ansprak_avbrott_och_budget(demo, monkeypatch):
    demo.start()
    ready, release = Event(), Event()
    original = demo.pilot._run

    def blocked(*args):
        ready.set()
        assert release.wait(10)
        return original(*args)

    demo.website(answer("needs_information"))
    monkeypatch.setattr(demo.pilot, "_run", blocked)
    version = demo.row["revision"]
    with ThreadPoolExecutor(2) as pool:
        one = pool.submit(demo.pilot.process, demo.ident, OPERATOR, version)
        assert ready.wait(10)
        try:
            with pytest.raises(ConflictError):
                demo.pilot.process(demo.ident, OPERATOR, version)
            with pytest.raises(ConflictError):
                demo.pilot.take_over(demo.ident, OPERATOR, demo.row["revision"], "Avbryt")
        finally:
            release.set()
        one.result()
    assert len(demo.state["runs"]) == 1
    demo.action("precisera", key=uuid4().hex, goal="Annan uppgift")
    monkeypatch.setattr("agents.company_missions.MAX_RUNS", 1)
    demo.process()
    assert demo.state["status"] == "budget_stopped"
    demo.action("ta-over", note="Budgeten är slut")
    assert demo.state["status"] == "taken_over"
