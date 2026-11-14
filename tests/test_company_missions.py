"""Pilotens ordinarie webbväg med lokal SQLite, riktigt harness och skriptad modell."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from functools import partial
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
    INTERPRET,
)
from agents.company_tools import SKILL
from agents.flows.questions import QuestionConsole
from agents.gateways import RegulatoryGateway
from ai import AIClient, AIConfig
from ai.providers.fake import FakeProvider, text_result
from ai.tracing import MemoryTraceSink
from reporting import render_report
from reporting.template import Fonts
from services import Actor, OperationContext
from services.change_requests import ReviewReferences
from services.development_demo import Candidate, Evidence
from services.errors import AccessDeniedError, ApprovalError, ConflictError
from services.operations import common
from tests.flow_helpers import (
    CHANGE,
    SOURCE,
    call,
    flow_client,
    impact_script,
    interpretation_script,
)
from web.app import create_app
from web.config import WebSettings
from web.routes.company_missions import BASE

OPERATOR = Actor.human("karl")
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
    return tool("order", capability=INTERPRET, key=key, source=source, goal=goal)


def interpretation(source=SOURCE, kind="parameter"):
    runs = interpretation_script(source)
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

    def open(self, *, active=True, legacy=False):
        self.app = create_app(settings=self.settings, company_ai=client() if active else None,
                              rule_flow_ai=flow_client() if legacy else None)
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
    demo.process(tool("status"), tool("review", capability=APPROVE_INTERPRETATION, basis=item["id"]),
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
    demo.process(tool("catalog"), tool("order", capability=IMPACT, key="premie", basis=item["id"]), answer())
    demo.process(*impact_script())
    assert demo.state["assignments"]["premie"]["result"]["output"]["evidence"]["estimate"]["key"] == CHANGE["key"]
    demo.process(tool("status"), tool("review", capability=ACTIVATE, basis=item["id"]), answer())
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
    demo.process(tool("status"), tool("review", capability=DEVELOP, basis=item["id"]), answer())
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
                     tool("order", capability=IMPACT, key="nekad", basis=item["id"]),
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
    demo.process(tool("review", capability=DEVELOP, basis=item["id"]), answer())
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


def test_historik_och_pilot_i_samma_demofil(demo):
    month = "2026-10-01"
    def connect_legacy():
        service = demo.app.state.service
        ai = client(
            call("get_company_metrics", {"month": month}, 1),
            text_result(json.dumps({"status": "partial", "month": month, "conclusion": "Bestånd och premier.",
                                    "limitations": [], "assumptions": [], "next_steps": []})),
        )
        console = QuestionConsole.build(service._session_factory, trusted=service, actuary_service=service,
            ai=ai, renderer=partial(render_report, fonts=Fonts.helvetica()), environment_id="demo",
            dataset_ref=demo.settings.dataset_ref, deliveries_dir=demo.tmp_path / "deliveries",
            journal_dir=demo.tmp_path / "legacy-runs")
        demo.app.state.question_console = console

    connect_legacy()

    def legacy_start():
        page = demo.web.get("/central/fragor")
        response = demo.web.post("/central/fragor", headers=ORIGIN, data={
            "csrf_token": page.context["operator_csrf"], "request_token": page.context["request_token"],
            "team": "aktuarie", "question_type": "portfolio_overview", "month": month[:7],
        })
        assert response.status_code == 303, response.text
        return response.headers["location"]

    def legacy_decide(url, decision):
        page = demo.web.get(url)
        flow = page.context["flow"]
        response = demo.web.post(f"{url}/granska", headers=ORIGIN, data={
            "csrf_token": page.context["operator_csrf"], "version": flow.version, "note": "Granskad",
            "seen_hash": flow.gate_hashes["review"], "decision": decision,
        })
        assert response.status_code == 303, response.text

    done = legacy_start()
    legacy_decide(done, "approved")
    connect_legacy()
    pending = legacy_start()
    original_pdf = demo.web.get(done + "/leverans/1/rapport.pdf").content
    assert original_pdf.startswith(b"%PDF-")
    demo.start("Vad säger villkoren?")
    demo.process(call("read_regulatory_document", {"handle": "villkor"}, 1),
                 answer("answered", sources=["villkor"], summary="Försäkringsvillkoren anger tillämpliga villkor."))
    demo.open(active=False)
    connect_legacy()
    assert demo.web.get(demo.url).status_code == 200
    for url in (done, pending):
        page = demo.web.get(url)
        flow = page.context["flow"]
        team = demo.web.get(f"/team/aktuarie/uppdrag/{flow.flow_id}")
        assert team.context["trace"].run_id == page.context["trace"].run_id
        assert demo.web.get(url + "/leverans/1/rapport.md").status_code == 200
    assert demo.web.get(done + "/leverans/1/rapport.pdf").content == original_pdf
    assert demo.web.get(done).context["assignment"].accepted
    assert demo.web.get(pending).context["assignment"].status == "waiting_gate"
    legacy_decide(pending, "rejected")
    assert "supersedes=" in demo.web.get(pending).text
