"""Utvecklingsytan via den vanliga appfabriken, operatörsinloggningen och en lokal demofil."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from subprocess import CompletedProcess
from threading import Barrier
from time import monotonic
from uuid import UUID, uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from agents import development_codex
from agents.development import (
    CodingAttempt,
    CodingResult,
    CodingTask,
    _git,
    run_development_case,
)
from agents.journal import read_journal
from scripts.demo.run_development_case import (
    DRAFT,
    FILE,
    SOURCE,
    ScriptedCoder,
    verify_quote,
)
from services import Actor
from services.change_requests import (
    DEVELOPER,
    ChangeQueueRun,
    ChangeRequest,
    ChangeRequestDraft,
    ChangeRequestOrder,
    ChangeRequestOrigin,
    ReviewReferences,
    change_release_events,
    change_request_events,
    change_requests_table,
)
from services.development_demo import Candidate, Evidence, OutcomeUnknown, TargetState
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
    change_release_events.drop(engine)
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


@pytest.fixture
def release_case(settings):
    app = create_app(settings=settings)
    store = app.state.change_requests
    releases = app.state.change_releases
    operator = Actor.human("karl")
    case_id = uuid4()
    run = demo_scope(case_id)
    store.create(operator, case_id, DRAFT)
    store.claim(run, case_id)
    store.handoff(run, case_id, REVIEW)
    candidate = Candidate(pull_request=case_id, base="a" * 40, head="b" * 40, diff="+ändring",
                          references=REVIEW, checks=(Evidence(name="kodprov", reference="provkörning 1",
                                                             passed=True, summary="2 av 2"),))
    releases.delivery.stage(candidate)
    return app, releases, operator, case_id, run, candidate


def approve_release(releases, operator, case_id):
    bundle = releases.read(operator, case_id, preview=True).preview
    assert releases.approve(operator, case_id, bundle.fingerprint)
    return releases.read(operator, case_id).approval.id


@pytest.mark.parametrize("change", ["head", "checks", "base"])
def test_u5_andrat_underlag_kraver_nytt_beslut(release_case, change):
    _, releases, operator, case_id, run, candidate = release_case
    original = releases.read(operator, case_id, preview=True).preview
    approval = approve_release(releases, operator, case_id)
    replacement = {"head": "c" * 40, "base": "d" * 40,
                   "checks": (candidate.checks[0].model_copy(update={"reference": "provkörning 2"}),)}
    releases.delivery.stage(candidate.model_copy(update={change: replacement[change]}))
    with pytest.raises(ConflictError, match="ändrats"):
        releases.approve(operator, case_id, original.fingerprint)
    with pytest.raises(ConflictError, match="nytt beslut"):
        releases.advance("merge", run, case_id, approval)
    assert releases.delivery.lookup_merge(f"merge/{case_id}/{approval}") is None
    next_approval = approve_release(releases, operator, case_id)
    assert next_approval != approval
    with pytest.raises(ConflictError):
        releases.advance("merge", run, case_id, approval)
    assert releases.advance("merge", run, case_id, next_approval)


@pytest.mark.parametrize("change", ["failed", "missing", "repository", "branch"])
def test_u5_policy_stoppar_merge(release_case, change):
    _, releases, operator, case_id, run, candidate = release_case
    approval = approve_release(releases, operator, case_id)
    updates = {
        "failed": {"checks": (candidate.checks[0].model_copy(update={"passed": False}),)},
        "missing": {"checks": ()},
        "repository": {"repository": "extern/annat-repo"},
        "branch": {"branch": "annan-branch"},
    }
    releases.delivery.stage(candidate.model_copy(update=updates[change]))
    assert releases.read(operator, case_id, preview=True).preview is None
    with pytest.raises(ConflictError, match="mergevillkor"):
        releases.advance("merge", run, case_id, approval)
    assert releases.delivery.lookup_merge(f"merge/{case_id}/{approval}") is None


def test_u5_kraver_manskligt_beslut_och_aktivt_agentmandat(release_case):
    app, releases, operator, case_id, run, _ = release_case
    detail_url = f"{BASE}/{case_id}"
    with client_for(app) as client:
        assert post_action(client, detail_url, "inforande/approve", "utan-session", review="okänt").status_code == 401
        login(client)
        detail = client.get(detail_url)
        assert post_action(client, detail_url, "inforande/approve", "fel-token",
                           review=detail.context["release"].preview.fingerprint).status_code == 403
    with pytest.raises(AccessDeniedError):
        releases.approve(run.actor, case_id, "")
    with pytest.raises(ConflictError, match="mänskligt beslut"):
        releases.advance("merge", run, case_id, 1)
    approval = approve_release(releases, operator, case_id)
    assert approve_release(releases, operator, case_id) == approval
    assert not releases.advance("merge", Actor.human("annan"), case_id, approval)
    for denied in (demo_scope(case_id), demo_scope(), demo_scope(case_id, actor=Actor.agent("annan"))):
        with pytest.raises(AccessDeniedError):
            releases.advance("merge", denied, case_id, approval)
    with pytest.raises(AccessDeniedError):
        releases.advance("deploy", run, case_id, approval)
    assert releases.requests.takeover(operator, case_id, run.run_id)
    with pytest.raises(AccessDeniedError):
        releases.advance("merge", run, case_id, approval)
    assert releases.advance("merge", operator, case_id, approval)


def test_u5_samtidiga_mergeanrop_ger_ett_kvitto(release_case, monkeypatch):
    _, releases, operator, case_id, run, _ = release_case
    approval = approve_release(releases, operator, case_id)
    barrier = Barrier(2)
    real_merge = releases.delivery.merge
    calls = []

    def merge(operation, candidate):
        calls.append(operation)
        return real_merge(operation, candidate)

    def advance():
        barrier.wait(timeout=5)
        return releases.advance("merge", run, case_id, approval)

    monkeypatch.setattr(releases.delivery, "merge", merge)
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = [executor.submit(advance) for _ in range(2)]
        assert all(job.result(timeout=10) for job in jobs)
    assert calls == [releases.read(operator, case_id).merge.operation]
    assert releases.requests.get(operator, case_id).status == "merged"


@pytest.mark.parametrize("stage", ["merge", "deploy"])
@pytest.mark.parametrize("applied", [False, True], ids=["before_effect", "after_effect"])
def test_u5_avbrott_stams_av_efter_omstart(settings, release_case, stage, applied, monkeypatch):
    _, releases, operator, case_id, run, _ = release_case
    approval = approve_release(releases, operator, case_id)
    if stage == "deploy":
        assert releases.advance("merge", run, case_id, approval)
    caller = run if stage == "merge" else operator
    actual = getattr(releases.delivery, stage)

    def interrupt(*args):
        if applied:
            actual(*args)
        raise OutcomeUnknown("Simulerat avbrott.")

    monkeypatch.setattr(releases.delivery, stage, interrupt)
    with pytest.raises(OutcomeUnknown, match="avbrott"):
        releases.advance(stage, caller, case_id, approval)
    assert releases.read(operator, case_id).pending == f"{stage}_pending"
    app = create_app(settings=settings)
    resumed = app.state.change_releases

    lookup_method = "lookup_merge" if stage == "merge" else "lookup_deployment"
    lookup = getattr(resumed.delivery, lookup_method)
    apply = getattr(resumed.delivery, stage)
    calls = []

    def read_outcome(*args):
        calls.append("lookup")
        return lookup(*args)

    def retry(*args):
        calls.append("retry")
        return apply(*args)

    monkeypatch.setattr(resumed.delivery, lookup_method, read_outcome)
    monkeypatch.setattr(resumed.delivery, stage, retry)
    assert resumed.advance(stage, caller, case_id, approval)
    assert calls == (["lookup"] if applied else ["lookup", "retry"])
    assert resumed.advance(stage, caller, case_id, approval)
    assert resumed.read(operator, case_id).pending is None
    assert resumed.requests.get(operator, case_id).status == ("merged" if stage == "merge" else "deployed")


def test_u5_okand_avstamning_stoppar_nytt_forsok(release_case, monkeypatch):
    _, releases, operator, case_id, run, candidate = release_case
    approval = approve_release(releases, operator, case_id)
    real_lookup = releases.delivery.lookup_merge
    real_merge = releases.delivery.merge
    calls = []

    def interrupt(*args):
        calls.append("anrop")
        raise OutcomeUnknown("Ej bekräftat.")

    monkeypatch.setattr(releases.delivery, "merge", interrupt)
    with pytest.raises(OutcomeUnknown):
        releases.advance("merge", run, case_id, approval)
    monkeypatch.setattr(releases.delivery, "lookup_merge", interrupt)
    with pytest.raises(OutcomeUnknown):
        releases.advance("merge", run, case_id, approval)
    assert calls == ["anrop", "anrop"]
    assert releases.read(operator, case_id).pending == "merge_pending"
    with pytest.raises(ConflictError):
        approve_release(releases, operator, case_id)
    releases.delivery.stage(candidate.model_copy(update={"head": "c" * 40}))
    monkeypatch.setattr(releases.delivery, "lookup_merge", real_lookup)
    with pytest.raises(ConflictError, match="Ingen merge hittades"):
        releases.advance("merge", run, case_id, approval)
    assert calls == ["anrop", "anrop"]
    assert releases.read(operator, case_id).pending is None
    monkeypatch.setattr(releases.delivery, "merge", real_merge)
    assert releases.advance("merge", run, case_id, approve_release(releases, operator, case_id))


def test_u5_merge_provar_underlaget_vid_sjalva_mutationen(release_case, monkeypatch):
    _, releases, operator, case_id, run, candidate = release_case
    approval = approve_release(releases, operator, case_id)
    merge = releases.delivery.merge

    def change_before_merge(operation, reviewed):
        releases.delivery.stage(candidate.model_copy(update={"head": "d" * 40}))
        return merge(operation, reviewed)

    monkeypatch.setattr(releases.delivery, "merge", change_before_merge)
    with pytest.raises(ConflictError, match="före merge"):
        releases.advance("merge", run, case_id, approval)
    assert releases.delivery.lookup_merge(f"merge/{case_id}/{approval}") is None
    with pytest.raises(ConflictError, match="Ingen merge hittades"):
        releases.advance("merge", run, case_id, approval)
    assert releases.requests.get(operator, case_id).status == "waiting_review"


def test_u5_inforande_och_verifiering_ar_skilda_utfall(release_case):
    app, releases, operator, case_id, run, candidate = release_case
    detail_url = f"{BASE}/{case_id}"
    with client_for(app) as client:
        login(client)
        page = client.get(detail_url)
        token = page.context["operator_csrf"]
        assert candidate.head in page.text and candidate.diff in page.text and "provkörning 1" in page.text
        assert post_action(client, detail_url, "inforande/approve", token,
                           review=page.context["release"].preview.fingerprint).status_code == 303
        approval = client.get(detail_url).context["release"].approval.id
        assert post_action(client, detail_url, "inforande/deploy", token, approval_id=approval).status_code == 409
        assert releases.advance("merge", run, case_id, approval)
        page = client.get(detail_url)
        merged = page.context["release"].merge
        assert page.context["item"].status == "merged" and page.context["release"].deployment is None
        assert merged.version in page.text and "Mergekvitto" in page.text
        assert post_action(client, detail_url, "inforande/deploy", token, approval_id=approval).status_code == 303
        page = client.get(detail_url)
        assert page.context["item"].status == "deployed" and page.context["release"].check is None
        deployment = page.context["release"].deployment
        assert deployment.version == merged.version
        assert "Observerad version vid införande" in page.text

        for observed, status in ((TargetState(version="0" * 40, ready=True), "deployed"),
                                 (TargetState(version=merged.version, ready=False), "deployed"),
                                 (TargetState(version=merged.version, ready=True), "verified")):
            with releases.delivery._transaction(write=True) as connection:
                releases.delivery._put(connection, deployment.target, observed)
            assert post_action(client, detail_url, "inforande/verify", token, approval_id=approval).status_code == 303
            page = client.get(detail_url)
            assert page.context["item"].status == status
            assert ("Underkänd" in page.text) == (status == "deployed")
        assert page.context["item"].status == "verified" and page.context["release"].check.version == merged.version
        assert [item.id for item in client.get(BASE).context["columns"]["verified"]] == [case_id]


@pytest.fixture
def quote_sandbox(tmp_path):
    """Betrodd provmiljö för u6-quote-discount/v1, med Git-objekt och fast kodprov."""
    repo = tmp_path / "quote-repo"
    repo.mkdir()
    test_input = tmp_path / "committed-quote"
    test_input.mkdir()

    def git(*args):
        return _git(repo, monotonic() + 10, *args)

    def commit():
        git("-c", "user.name=U6 test", "-c", "user.email=demo@example.invalid", "commit",
            "--no-gpg-sign", "-m", "Syntetisk offert")

    git("init", "--template=", "--object-format=sha1", "--initial-branch=proposal")
    quote = repo / FILE
    quote.write_bytes(b"SELECT :price + :discount;\n")
    git("add", "--", FILE)
    commit()
    base = git("rev-parse", "HEAD")
    git("branch", "main", base)
    before = git("hash-object", "--no-filters", FILE)
    quote.write_bytes(b"SELECT :price - :discount;\n")
    after = git("hash-object", "--no-filters", FILE)
    git("add", "--", FILE)
    commit()

    def observe(case_id, run_id):
        head = git("rev-parse", "refs/heads/proposal")
        if (git("rev-parse", "refs/heads/main") != base
                or git("show", "-s", "--format=%P", head) != base
                or git("ls-tree", "-r", "-t", base) != f"100644 blob {before}\t{FILE}"
                or git("ls-tree", "-r", "-t", head) != f"100644 blob {after}\t{FILE}"):
            return None
        diff = git("diff", "--no-ext-diff", "--no-textconv", "--no-renames", base, head, "--")
        (test_input / FILE).write_bytes((git("cat-file", "blob", f"{head}:{FILE}") + "\n").encode())
        proof = verify_quote(test_input)
        if not proof.passed:
            return None
        result = CodingResult(run_id=run_id, case_id=case_id, base_commit=base, head_commit=head,
                              branch="proposal", outcome="tests_passed",
                              attempts=(CodingAttempt(plan="Rätta fiktiv offert", diff=diff, tests=proof),))
        refs = result.review()
        return Candidate(pull_request=case_id, base=base, head=head, diff=diff, references=refs,
                         checks=(Evidence(name="kodprov", reference=refs.test_ref,
                                          passed=True, summary=proof.summary),))

    return repo, git, commit, observe


def prepare_quote_review(settings, observe, *, rule_change=False):
    releases = create_app(settings=settings).state.change_releases
    store = releases.requests
    operator = Actor.human("karl")
    if rule_change:
        order = ChangeRequestOrder(
            **(DRAFT.model_dump() | {"kind": "rule_change", "motivation": "Ny pensionslogik",
                                    "decision_ref": "syntetiskt regelbeslut", "rule_version": "v2"}),
            origin=ChangeRequestOrigin(channel="rule_change_code", reference="FLOW-TEST/order"),
        )
        item = store.submit_order(operator, order)
    else:
        item = store.create(operator, uuid4(), DRAFT)
    run = demo_scope(item.id)
    store.claim(run, item.id)
    candidate = observe(item.id, run.run_id)
    assert candidate is not None
    store.handoff(run, item.id, candidate.references)
    releases.delivery.stage(candidate)
    return releases, operator, run, candidate


@pytest.mark.parametrize("change", ["extra_file", "mode", "sql_bytes", "base_ref", "parent"])
def test_u6_sandladeforslaget_ger_avslag_for_andrad_git_kandidat(quote_sandbox, change):
    repo, git, commit, observe = quote_sandbox
    case_id, run_id = uuid4(), uuid4()
    assert observe(case_id, run_id) is not None
    if change == "base_ref":
        git("branch", "-f", "main", "HEAD")
    elif change == "parent":
        git("-c", "user.name=U6 test", "-c", "user.email=demo@example.invalid", "commit",
            "--allow-empty", "--no-gpg-sign", "-m", "Extra förälder")
    else:
        git("reset", "--soft", "refs/heads/main")
        if change == "extra_file":
            (repo / "verify.py").write_bytes(b"assert True\n")
            git("add", "--", "verify.py")
        elif change == "mode":
            git("update-index", "--chmod=+x", FILE)
        else:
            (repo / FILE).write_bytes(b"SELECT :price - :discount;\n\n")
            git("add", "--", FILE)
        commit()
    assert observe(case_id, run_id) is None


@pytest.mark.parametrize("field", ["diff", "head", "checks", "branch", "repository"])
def test_u6_granskningsvagen_binder_faktisk_commit_och_bevis(settings, quote_sandbox, field):
    observe = quote_sandbox[-1]
    releases, operator, run, candidate = prepare_quote_review(settings, observe)
    case_id = candidate.pull_request
    assert releases.read(operator, case_id, preview=True).preview.candidate == observe(case_id, run.run_id)
    approval = approve_release(releases, operator, case_id)
    changes = {"diff": "förändrad diff", "head": "b" * 40, "branch": "annan-branch", "repository": "extern/repo",
               "checks": (candidate.checks[0].model_copy(update={"reference": "annat testbevis"}),)}
    replacement = candidate.model_copy(update={field: changes[field]})
    releases.delivery.stage(replacement)
    assert replacement != observe(case_id, run.run_id)
    with pytest.raises(ConflictError):
        releases.advance("merge", run, case_id, approval)
    assert releases.requests.get(operator, case_id).status == "waiting_review"
    assert releases.delivery.lookup_merge(f"merge/{case_id}/{approval}") is None


@pytest.mark.parametrize("rule_change", [False, True], ids=["synthetic_defect", "pension_rule"])
def test_u6_ordinarie_granskning_kravs_med_eller_utan_syntetiskt_arende(settings, quote_sandbox, rule_change):
    observe = quote_sandbox[-1]
    releases, operator, run, candidate = prepare_quote_review(settings, observe, rule_change=rule_change)
    case_id = candidate.pull_request
    item = releases.requests.get(operator, case_id)
    if rule_change:
        assert item.draft.kind == "rule_change" and item.origin.channel == "rule_change_code"
    assert candidate == observe(case_id, run.run_id)
    assert releases.read(operator, case_id).approval is None
    with pytest.raises(AccessDeniedError):
        releases.advance("merge", demo_scope(case_id), case_id, 1)
    with pytest.raises(ConflictError, match="mänskligt beslut"):
        releases.advance("merge", run, case_id, 1)
    assert releases.requests.get(operator, case_id).status == "waiting_review"
    assert releases.delivery.lookup_merge(f"merge/{case_id}/1") is None


def test_u6_offertprov_stams_av_fore_dubbelanrop_och_inforande(settings, quote_sandbox, monkeypatch):
    releases, operator, run, candidate = prepare_quote_review(settings, quote_sandbox[-1])
    case_id = candidate.pull_request
    approval = approve_release(releases, operator, case_id)
    operation = f"merge/{case_id}/{approval}"
    merge = releases.delivery.merge
    calls = []

    def lose_response(key, expected):
        calls.append(key)
        merge(key, expected)
        raise OutcomeUnknown("Mergebeskedet uteblev.")

    monkeypatch.setattr(releases.delivery, "merge", lose_response)
    with pytest.raises(OutcomeUnknown):
        releases.advance("merge", run, case_id, approval)
    assert releases.read(operator, case_id).pending == "merge_pending"

    resumed = create_app(settings=settings).state.change_releases
    lookup = resumed.delivery.lookup_merge

    def unavailable(_):
        raise OutcomeUnknown("Källan svarar ännu inte.")

    monkeypatch.setattr(resumed.delivery, "merge", lose_response)
    monkeypatch.setattr(resumed.delivery, "lookup_merge", unavailable)
    with pytest.raises(OutcomeUnknown):
        resumed.advance("merge", run, case_id, approval)
    assert resumed.read(operator, case_id).pending == "merge_pending"

    monkeypatch.setattr(resumed.delivery, "lookup_merge", lookup)
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = [executor.submit(resumed.advance, "merge", run, case_id, approval) for _ in range(2)]
        assert all(job.result(timeout=10) for job in jobs)
    view = resumed.read(operator, case_id)
    assert calls == [operation] and view.merge == lookup(operation)
    assert view.deployment is None and view.check is None
    assert resumed.advance("deploy", operator, case_id, approval)
    assert resumed.read(operator, case_id).check is None
    assert resumed.advance("verify", operator, case_id, approval)
    verified = resumed.read(operator, case_id)
    assert verified.check.passed and verified.check.version == verified.deployment.version == view.merge.version
