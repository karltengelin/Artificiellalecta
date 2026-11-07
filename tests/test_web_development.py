"""Utvecklingsytan via den vanliga appfabriken, operatörsinloggningen och en lokal demofil."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from subprocess import CompletedProcess
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from agents import development_codex
from agents.development import CodingResult, CodingTask, run_development_case
from agents.journal import read_journal
from scripts.demo.run_development_case import DRAFT, FILE, SOURCE, ScriptedCoder, verify_quote
from services import Actor
from services.change_requests import (
    DEVELOPER,
    ChangeQueueRun,
    ChangeRequest,
    ChangeRequestDraft,
    ReviewReferences,
    change_request_events,
    change_requests_table,
)
from services.errors import AccessDeniedError, ConflictError
from web import development_github
from web.app import create_app
from web.config import WebSettings
from web.database import demo_engine

BASE = "/central/utveckling"
ORIGIN = {"Origin": "https://testserver"}
PASSWORD = "en-fiktiv-losenfras-for-u1"
REVIEW = ReviewReferences(code_ref="commit demo-12", test_ref="testprotokoll demo-12")


@pytest.fixture(scope="module")
def password_hash():
    return PasswordHasher().hash(PASSWORD)


@pytest.fixture
def settings(tmp_path, password_hash):
    return WebSettings(demo_path=tmp_path / "demo.db", allowed_hosts=("testserver",),
                       handler_id="legacy-handler", operator_id="karl", operator_password_hash=password_hash)


def client_for(app):
    return TestClient(app, base_url="https://testserver", follow_redirects=False)


def login(client, username="karl"):
    page = client.get("/logga-in")
    response = client.post("/logga-in", headers=ORIGIN, data={
        "username": username, "password": PASSWORD, "csrf_token": page.context["session_csrf"],
    })
    assert response.status_code == 303


def new_form(client, **fields):
    page = client.get(BASE + "/ny")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert 'name="request_id"' in page.text
    return {
        "request_id": str(page.context["request_id"]), "csrf_token": page.context["operator_csrf"],
        "kind": "defect", "title": "Fel vid export", "need": "Kolumnrubriken saknas.", **fields,
    }


def test_fel_och_regel_anvander_samma_kontrakt_efter_omstart(settings):
    # Återskapa schemaformen hos en äldre demofil med befintligt bestånd.
    engine = demo_engine(settings.demo_path)
    change_request_events.drop(engine)
    change_requests_table.drop(engine)
    engine.dispose()
    with client_for(create_app(settings=settings)) as client:
        assert f'href="{BASE}"' in client.get("/central").text
        login(client)
        assert "Du har inga ändringsärenden ännu" in client.get(BASE).text
        bug = new_form(client, need="Text med <script> och radbrytning.\nKolumnrubriken saknas.")
        rule = new_form(client, kind="rule_change", title="Visa giltighetsdatum", affected_system="Regelöversikt",
                        need="Tillämpa en fiktiv regel för en framtida period.", motivation="Spårbarhet",
                        acceptance="Gammal och ny period visas med rätt version.", source_refs="SIM-KÄLLA-01",
                        decision_ref="SIM-BESLUT-01", rule_version="SIM-REGEL v2", effective_on="2027-01-01")
        responses = [client.post(BASE, headers=ORIGIN, data=form) for form in (bug, rule)]
        assert all(r.status_code == 303 for r in responses)
        bug_url, rule_url = [r.headers["location"] for r in responses]
        assert bug_url == f"{BASE}/{bug['request_id']}"
        assert rule_url == f"{BASE}/{rule['request_id']}"

    with client_for(create_app(settings=settings)) as client:
        login(client)
        listing = client.get(BASE)
        assert listing.status_code == 200 and listing.headers["cache-control"] == "no-store"
        assert f'href="{bug_url}"' in listing.text and f'href="{rule_url}"' in listing.text
        assert "Felanmälan" in listing.text and "Regeländring" in listing.text
        bug_page, rule_page = client.get(bug_url), client.get(rule_url)
        assert bug_page.status_code == rule_page.status_code == 200
        assert "med &lt;script&gt; och radbrytning.\nKolumnrubriken" in bug_page.text
        assert "SIM-BESLUT-01" in rule_page.text and "SIM-REGEL v2" in rule_page.text
        for page in (bug_page, rule_page):
            item = page.context["item"]
            assert isinstance(item, ChangeRequest)
            assert item.requested_by == "karl" and item.status == "new"
        assert rule_page.context["item"].draft.effective_on == date(2027, 1, 1)


def test_atkomst_och_validering(settings):
    app = create_app(settings=settings)
    with client_for(app) as client:
        for url in (BASE, BASE + "/ny", BASE + "/11111111-1111-4111-8111-111111111111"):
            response = client.get(url)
            assert response.status_code == 401 and response.headers["cache-control"] == "no-store"
        assert client.post(BASE, headers=ORIGIN, data={"csrf_token": app.state.csrf_token}).status_code == 401
        login(client)
        form = new_form(client, title="   ", effective_on="2027-02-30")
        assert client.post(BASE, headers={"Origin": "https://example.test"}, data=form).status_code == 403
        assert client.post(BASE, headers=ORIGIN, data={**form, "csrf_token": app.state.csrf_token}).status_code == 403
        assert client.post(BASE, headers=ORIGIN, data={**form, "requested_by": "annat-id"}).status_code == 400
        invalid = client.post(BASE, headers=ORIGIN, data=form)
        assert invalid.status_code == 422 and invalid.headers["cache-control"] == "no-store"
        assert invalid.context["errors"].keys() == {"title", "effective_on"}
        assert str(invalid.context["request_id"]) == form["request_id"]
        assert invalid.context["values"]["need"] == form["need"]
        assert client.get(BASE).context["items"] == []
        response = client.post(BASE, headers=ORIGIN, data={**form, "title": "Eget ärende", "effective_on": ""})
        assert response.status_code == 303
        detail = response.headers["location"]

    with client_for(create_app(settings=replace(settings, operator_id="annan"))) as client:
        login(client, "annan")
        assert client.get(BASE).context["items"] == []
        hidden = client.get(detail)
        assert hidden.status_code == 404 and "Eget ärende" not in hidden.text

    for actor in (Actor.agent("karl"), Actor.system("karl")):
        with pytest.raises(AccessDeniedError):
            app.state.change_requests.list(actor)


def test_samtidigt_omforsok_ar_idempotent(settings):
    app = create_app(settings=settings)
    with client_for(app) as client:
        login(client)
        form = new_form(client)
        store = app.state.change_requests
        actor = Actor.human("karl")
        draft = ChangeRequestDraft(kind="defect", title=form["title"], need=form["need"])
        barrier = Barrier(2, timeout=10)

        def submit():
            barrier.wait()
            return store.create(actor, UUID(form["request_id"]), draft)

        with ThreadPoolExecutor(max_workers=2) as executor:
            attempts = [executor.submit(submit) for _ in range(2)]
            assert attempts[0].result() == attempts[1].result()
        replay = client.post(BASE, headers=ORIGIN, data=form)
        assert replay.status_code == 303 and replay.headers["location"] == f"{BASE}/{form['request_id']}"
        collision = client.post(BASE, headers=ORIGIN, data={**form, "title": "En annan titel"})
        assert collision.status_code == 409
        assert [item.draft.title for item in client.get(BASE).context["items"]] == [form["title"]]


@pytest.mark.parametrize("database", ["svc_test", "lakebase"])
def test_andra_miljoer_anropar_ingen_databas(web, settings, database, monkeypatch):
    service = web.app.state.service

    def fail(*args, **kwargs):
        pytest.fail("Utvecklingsytan får inte använda annan databas")

    monkeypatch.setattr(service, "execute", fail)
    monkeypatch.setattr(service, "_session_factory", fail)
    app = create_app(service=service, settings=replace(settings, database=database))
    assert app.state.change_requests is None
    with client_for(app) as client:
        login(client)
        page = client.get(BASE)
        assert page.status_code == 404 and "finns i demomiljön" in page.text
        response = client.post(BASE, headers=ORIGIN, data={"csrf_token": page.context["operator_csrf"]})
        assert response.status_code == 404


@pytest.fixture
def github_api(monkeypatch):
    calls = []
    responses = {}

    class GitHubResponse(BytesIO):
        def __init__(self, status, payload):
            super().__init__(json.dumps(payload).encode())
            self.status = status

    class GitHubConnection:
        def __init__(self, host, *, timeout):
            assert host == "api.github.com"
            assert 0 < timeout <= 2

        def request(self, method, path, *, headers):
            assert headers["Authorization"] == "Bearer fiktiv"
            calls.append((method, path))
            self.path = path

        def getresponse(self):
            response = responses[self.path]
            if isinstance(response, Exception):
                raise response
            return GitHubResponse(*response)

        def close(self):
            pass

    monkeypatch.setattr(development_github, "HTTPSConnection", GitHubConnection)
    return calls, responses


def post_action(client, detail, action, token, **fields):
    return client.post(f"{detail}/{action}", headers=ORIGIN, data={"csrf_token": token, **fields})


def test_u2_board_laser_github_separat_och_fungerar_vid_avbrott(settings, github_api, monkeypatch):
    calls, responses = github_api
    settings = replace(settings, development_github_token="fiktiv")
    repository = settings.development_github_repository
    pr_path = f"/repos/{repository}/pulls/12"
    pr_url = f"https://github.com/{repository}/pull/12"
    responses[pr_path] = (200, {"number": 12, "state": "closed", "merged": True, "draft": False})

    class Clock(datetime):
        now_utc = datetime(2026, 11, 7, tzinfo=UTC)

        @classmethod
        def now(cls, tz):
            return cls.now_utc

    monkeypatch.setattr(development_github, "datetime", Clock)
    with client_for(create_app(settings=settings)) as client:
        login(client)
        form = new_form(client)
        token = form["csrf_token"]
        detail = client.post(BASE, headers=ORIGIN, data=form).headers["location"]
        board = client.get(BASE)
        assert [item.draft.title for item in board.context["columns"]["new"]] == [form["title"]]
        assert 'id="status-waiting_review"' in board.text
        assert post_action(client, detail, "status", token, previous="new", status="in_progress").status_code == 303
        assert post_action(client, detail, "github", token, previous="", github_url=pr_url).status_code == 303
        assert calls == []
        assert "Status hämtas när du öppnar ärendet." in client.get(BASE).text
        assert calls == []

        page = client.get(detail)
        assert page.status_code == 200
        assert "Bolagets ärendestatus" in page.text and "Teknisk status från GitHub" in page.text
        assert "Pågår" in page.text and "Mergad" in page.text
        assert "fiktiv" not in page.text
        board = client.get(BASE)
        assert board.context["columns"]["new"] == []
        assert [item.draft.title for item in board.context["columns"]["in_progress"]] == [form["title"]]
        assert "Pull request #12" in board.text and "Mergad" in board.text
        assert calls == [("GET", pr_path)]

        Clock.now_utc += timedelta(minutes=2)
        responses[pr_path] = TimeoutError("hemlig teknisk feldetalj")
        assert "Föråldrad GitHub-status" in client.get(BASE).text
        page = client.get(detail)
        assert page.status_code == 200
        assert "GitHub-status kunde inte hämtas." in page.text and "Föråldrad GitHub-status" in page.text
        assert "Mergad" in page.text and "hemlig teknisk feldetalj" not in page.text
        assert post_action(client, detail, "status", token, previous="in_progress", status="waiting_review").status_code == 422
        assert post_action(client, detail, "status", token, previous="in_progress", status="waiting_review",
                           **REVIEW.model_dump()).status_code == 303
        board = client.get(BASE)
        assert board.status_code == 200 and "GitHub-status kunde inte hämtas." in board.text
        assert [item.draft.title for item in board.context["columns"]["waiting_review"]] == [form["title"]]
        assert calls == [("GET", pr_path), ("GET", pr_path)]

    with client_for(create_app(settings=replace(settings, development_github_token=None))) as client:
        login(client)
        item = client.get(detail).context["item"]
        assert item.github_url == pr_url and item.status == "waiting_review"
        assert item.review == REVIEW and item.assignee_id == "karl"
        assert [(event.actor_id, event.action, event.current) for event in item.history] == [
            ("karl", "status", "waiting_review"), ("karl", "review", REVIEW.test_ref),
            ("karl", "github", pr_url), ("karl", "status", "in_progress"), ("karl", "human_claim", "karl"),
        ]


def test_u2_bevarar_u1_arende_vid_uppgradering_av_demofil(settings):
    with client_for(create_app(settings=settings)) as client:
        login(client)
        detail = client.post(BASE, headers=ORIGIN, data=new_form(client)).headers["location"]
    engine = demo_engine(settings.demo_path)
    change_request_events.drop(engine)
    engine.dispose()

    with client_for(create_app(settings=settings)) as client:
        login(client)
        page = client.get(detail)
        assert page.status_code == 200
        item = page.context["item"]
        assert item.draft.title == "Fel vid export"
        assert item.status == "new" and item.github_url is None and item.history == ()


def test_u2_skrivskydd_omforsok_och_utgangna_formular(settings, github_api):
    calls, responses = github_api
    settings = replace(settings, development_github_repository="example/Repo", development_github_token="fiktiv")
    responses["/repos/example/Repo/issues/8"] = (301, {})
    issue = "https://github.com/example/Repo/issues/8"
    with client_for(create_app(settings=settings)) as client:
        login(client)
        form = new_form(client)
        token = form["csrf_token"]
        detail = client.post(BASE, headers=ORIGIN, data=form).headers["location"]
        assert post_action(client, detail, "status", "fel", previous="new", status="in_progress").status_code == 403
        assert post_action(client, detail, "status", token, previous="new", status="waiting_review").status_code == 422
        for invalid in ("https://evil.test/example/Repo/issues/8", "https://github.com/annan/Repo/issues/8",
                        "https://github.com@example/Repo/issues/8", "https://github.com/example/Repo/issues/8?token=x"):
            assert post_action(client, detail, "github", token, previous="", github_url=invalid).status_code == 422
        assert post_action(client, detail, "github", token, previous="", github_url=issue).status_code == 303
        assert "GitHub-status kunde inte hämtas." in client.get(detail).text
        assert calls == [("GET", "/repos/example/Repo/issues/8")]
        assert post_action(client, detail, "github", token, previous="", github_url=issue).status_code == 303
        assert post_action(client, detail, "github", token, previous="", github_url="").status_code == 409
        assert post_action(client, detail, "github", token, previous=issue, github_url="").status_code == 303
        assert post_action(client, detail, "status", token, previous="new", status="in_progress").status_code == 303
        assert post_action(client, detail, "status", token, previous="new", status="in_progress").status_code == 303
        assert post_action(client, detail, "status", token, previous="waiting_review", status="in_progress").status_code == 303
        assert post_action(client, detail, "status", token, previous="in_progress", status="new").status_code == 303
        assert post_action(client, detail, "status", token, previous="in_progress", status="waiting_review",
                           **REVIEW.model_dump()).status_code == 409
        assert len(client.get(detail).context["item"].history) == 6
        assert client.post(BASE, headers=ORIGIN, data=form).headers["location"] == detail

    with client_for(create_app(settings=replace(settings, operator_id="annan"))) as client:
        assert post_action(client, detail, "status", "fel", previous="new", status="in_progress").status_code == 401
        login(client, "annan")
        token = new_form(client)["csrf_token"]
        assert client.get(detail).status_code == 404
        assert post_action(client, detail, "status", token, previous="new", status="in_progress").status_code == 404
        assert post_action(client, detail, "github", token, previous="", github_url=issue).status_code == 404
        assert calls == [("GET", "/repos/example/Repo/issues/8")]


@pytest.mark.parametrize(("kind", "payload", "label"), [
    ("issues", {"state": "open"}, "Öppen"),
    ("issues", {"state": "closed"}, "Stängd"),
    ("issues", {"state": "open", "pull_request": {}}, None),
    ("pull", {"state": "open", "draft": True, "merged": False}, "Utkast"),
    ("pull", {"state": "open", "draft": False, "merged": False}, "Öppen"),
    ("pull", {"state": "closed", "draft": False, "merged": False}, "Stängd"),
    ("pull", {"state": "closed", "draft": False}, None),
])
def test_github_tillstand_fran_api(github_api, kind, payload, label):
    calls, responses = github_api
    repository = "example/Repo"
    collection = "pulls" if kind == "pull" else kind
    path = f"/repos/{repository}/{collection}/12"
    responses[path] = (200, {"number": 12, **payload})
    reader = development_github.GitHubReader(repository, "fiktiv")
    status = reader.status(f"https://github.com/{repository}/{kind}/12", refresh=True)
    assert calls == [("GET", path)]
    assert status.label == label
    assert (status.error is None) == (label is not None)


def demo_scope(*allowed, actor=DEVELOPER):
    return ChangeQueueRun(actor=actor, run_id=uuid4(), requested_by="karl", allowed_requests=allowed)


def test_u3_mandat_och_samtidigt_ansprak(settings):
    app = create_app(settings=settings)
    store = app.state.change_requests
    human = Actor.human("karl")
    case_id, other_id, foreign_id = uuid4(), uuid4(), uuid4()
    store.create(human, case_id, DRAFT)
    store.create(human, other_id, DRAFT)
    store.create(Actor.human("annan"), foreign_id, DRAFT)
    scope = demo_scope(case_id, foreign_id)
    assert [item.id for item in store.list_new(scope)] == [case_id]
    for denied in (other_id, foreign_id):
        with pytest.raises(AccessDeniedError):
            store.claim(scope, denied)
    for actor in (Actor.agent("aktuarie", "aktuarie"), Actor.agent("utvecklaragent"), human):
        with pytest.raises(AccessDeniedError):
            store.list_new(demo_scope(case_id, actor=actor))
        with pytest.raises(AccessDeniedError):
            store.claim(demo_scope(case_id, actor=actor), case_id)

    barrier = Barrier(2, timeout=10)

    def compete(action):
        barrier.wait()
        try:
            action()
        except ConflictError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        agent = executor.submit(compete, lambda: store.claim(scope, case_id))
        operator = executor.submit(compete, lambda: store.move(human, case_id, "new", "in_progress"))
    assert agent.result() != operator.result()
    item = store.get(human, case_id)
    assert item.status == "in_progress" and not store.list_new(scope)
    assert item.assignee_id == (DEVELOPER.id if agent.result() else human.id)
    assert [event.action for event in item.history] == ["status", "agent_claim" if agent.result() else "human_claim"]


def test_u3_codexadapter_rattar_testfel_och_lamnar_granskningsbevis(settings, tmp_path, monkeypatch):
    app = create_app(settings=settings)
    store = app.state.change_requests
    attempts = []
    executable = tmp_path / "codex"

    def local_cli(args, *, input, cwd, env, timeout, **kwargs):
        assert args[:6] == [str(executable), "--ask-for-approval", "never", "exec", "--ephemeral", "--ignore-user-config"]
        assert "read-only" in args and 0 < timeout <= 120
        assert env == {"U3_TEST": "syntetiskt"}
        schema = json.loads(Path(args[-2]).read_text(encoding="utf-8"))
        assert schema["required"] == ["plan", "path", "before", "after"]
        assert sorted(path.name for path in cwd.iterdir()) == [".git", FILE]
        assert (cwd / FILE).read_text(encoding="utf-8") == SOURCE
        assert (cwd / ".git" / "HEAD").read_text(encoding="utf-8").startswith("ref: refs/heads/demo/")
        task = CodingTask.model_validate_json(input.split("\n\n", 1)[1])
        attempts.append(task.feedback.summary)
        edit = ScriptedCoder().propose(task, cwd, timeout)
        return CompletedProcess(args, 0, edit.model_dump_json(), "")

    monkeypatch.setattr(development_codex, "run", local_cli)
    with client_for(app) as client:
        login(client)
        form = new_form(client, **DRAFT.model_dump(mode="json", exclude_none=True))
        detail = client.post(BASE, headers=ORIGIN, data=form).headers["location"]
        case_id = UUID(form["request_id"])
        scope = demo_scope(case_id)
        result = run_development_case(
            store, scope, case_id, coder=development_codex.CodexCli(executable, isolated_env={"U3_TEST": "syntetiskt"}),
            files={FILE: SOURCE}, verify=verify_quote, directory=tmp_path,
        )
        assert "1200" in attempts[0] and "rabatt 0" in attempts[1]
        assert result.outcome == "tests_passed" and not result.baseline.passed
        assert [attempt.tests.passed for attempt in result.attempts] == [False, True]
        assert "+SELECT :price - :discount;" in result.attempts[-1].diff
        assert CodingResult.model_validate_json((tmp_path / str(scope.run_id) / "result.json").read_bytes()) == result
        trace, incomplete = read_journal(tmp_path / f"{scope.run_id}.jsonl")
        assert not incomplete and trace[-1]["outcome"] == "tests_passed"
        assert [event["passed"] for event in trace if event["type"] == "development_tested"] == [False, True]

        board = client.get(BASE)
        assert [item.id for item in board.context["columns"]["waiting_review"]] == [case_id]
        assert "utvecklaragent (agent)" in board.text
        page = client.get(detail)
        assert page.context["item"].review == result.review()
        assert result.review().code_ref in page.text and result.review().test_ref in page.text
        assert str(scope.run_id) in page.text and "Tog ansvar som agent" in page.text
        store.handoff(scope, case_id, result.review())
        with pytest.raises(ConflictError):
            store.handoff(scope, case_id, REVIEW)


def test_u3_operator_tar_over_och_inaktuell_korning_kan_inte_lamna_underlag(settings):
    app = create_app(settings=settings)
    store = app.state.change_requests
    with client_for(app) as client:
        login(client)
        form = new_form(client)
        detail = client.post(BASE, headers=ORIGIN, data=form).headers["location"]
        case_id = UUID(form["request_id"])
        scope = demo_scope(case_id)
        store.claim(scope, case_id)
        assert "Ta över ärendet" in client.get(detail).text
        assert post_action(client, detail, "ta-over", "fel", run_id=scope.run_id).status_code == 403
        assert post_action(client, detail, "ta-over", form["csrf_token"], run_id=uuid4()).status_code == 409
        assert post_action(client, detail, "status", form["csrf_token"], previous="in_progress",
                           status="new").status_code == 409
        assert not store.takeover(Actor.human("annan"), case_id, scope.run_id)
        for _ in range(2):
            assert post_action(client, detail, "ta-over", form["csrf_token"], run_id=scope.run_id).status_code == 303
        with pytest.raises(ConflictError):
            store.handoff(scope, case_id, REVIEW)
        board = client.get(BASE)
        assert board.context["columns"]["in_progress"][0].assignee_id == "karl"
        assert "Ansvarig · karl" in board.text
        page = client.get(detail)
        assert "Tog över från agentkörning" in page.text
        assert [event.action for event in page.context["item"].history] == ["takeover", "status", "agent_claim"]
        assert post_action(client, detail, "status", form["csrf_token"], previous="in_progress",
                           status="waiting_review", **REVIEW.model_dump()).status_code == 303


def test_u3_diff_utanfor_filmandatet_blockeras(settings, tmp_path):
    app = create_app(settings=settings)
    store = app.state.change_requests
    case_id = uuid4()
    store.create(Actor.human("karl"), case_id, DRAFT)

    class OutsideScope(ScriptedCoder):
        def propose(self, task, workspace, timeout):
            return super().propose(task, workspace, timeout).model_copy(update={"path": "../outside.sql"})

    result = run_development_case(store, demo_scope(case_id), case_id, coder=OutsideScope(),
                                  files={FILE: SOURCE}, verify=verify_quote, directory=tmp_path)
    assert result.outcome == "blocked" and result.attempts == ()
    item = store.get(Actor.human("karl"), case_id)
    assert item.status == "in_progress" and item.review is None


def test_u3_overtagande_under_kodforsok_och_gammal_kornyckel(settings, tmp_path):
    store = create_app(settings=settings).state.change_requests
    human = Actor.human("karl")
    case_id = uuid4()
    store.create(human, case_id, DRAFT)
    scope = demo_scope(case_id)

    class InterruptedCoder(ScriptedCoder):
        def propose(self, task, workspace, timeout):
            assert store.takeover(human, case_id, scope.run_id)
            return super().propose(task, workspace, timeout)

    result = run_development_case(store, scope, case_id, coder=InterruptedCoder(),
                                  files={FILE: SOURCE}, verify=verify_quote, directory=tmp_path)
    assert result.outcome == "superseded" and result.attempts == ()
    assert store.get(human, case_id).assignee_id == human.id
    assert store.move(human, case_id, "in_progress", "new")
    with pytest.raises(ConflictError):
        store.claim(scope, case_id)
    next_run = demo_scope(case_id)
    store.claim(next_run, case_id)
    with pytest.raises(ConflictError):
        store.handoff(scope, case_id, REVIEW)
    assert store.get(human, case_id).agent_run_id == next_run.run_id
