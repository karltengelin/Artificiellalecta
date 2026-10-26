"""Röktest av parameterändringsflödet mot riktig modell (Fas 3c 3c-V, flaggskeppsflöde.md §7 och §11).

Kör flödet `rule_change_parameter` genom samma adapter som UI:t (`FlowConsole`) med riktiga
modeller för compliance (tolkning) och aktuarie (beståndsinsikt). Skriptet agerar operatör i
grindarna och det manuella steget, märkt `rooktest`. Inget körs mot beståndet i Lakebase:

| `--db`     | Databas                                                                 | Teamens roller |
|------------|-------------------------------------------------------------------------|----------------|
| `demo`     | Demobeståndet i en SQLite-databas i minnet                              | simulerade     |
| `svc_test` | Demobeståndet i ett eget schema i SERVICES_TEST_POSTGRES_URL, tas bort efteråt | riktiga begränsade roller med `agent_aktuarie`s och `agent_compliance`s rättigheter, när testroller finns |

Testrollerna är SERVICES_TEST_AKTUARIE_POSTGRES_URL och SERVICES_TEST_COMPLIANCE_POSTGRES_URL.
Saknas de lånas SERVICES_TEST_AGENT_POSTGRES_URL för ett av teamen; ett team utan egen
inloggning kör då med simulerad roll.

Kontrollerna skiljer **verksamhetskontroller** (flödet, grindarna, mandatet, rollen och
verifieringen ska fungera för alla källor) från **facit för scenariot** (vad just
K-SIM-ITP-2027 ska ge). Ett godkänt röktest bevisar inte fullständig regeländringshantering.

Regelpaketet PR-ITP1 v1.0 gäller från 2026-11-01. Före dess stoppar regelgolvet aktiveringen,
och röktestet kontrollerar just det stoppet. `--regeldatum 2026-11-01` provar hela vägen till
verifieringen i den tillfälliga databasen; det ändrar bara regelkatalogens datum i röktestet.

`--avvikelser` tolkar även två fiktiva testkällor ur `tests/data/regelverk_avvikelser/` (i en
tillfällig kopia av regelverksdokumenten): en ändring utan parameter och en med två parametrar.
Grind 1 ska då vägra godkänna och flödena avslås.

Utan --run görs inga modellanrop. Kostnaden begränsas av teamens tak i ecosystem.yaml
(compliance 1,50 USD, aktuarie 1,00 USD per körning). Nycklar läses ur .env och skrivs aldrig ut.
Körjournalerna hamnar i logs/agent_runs/, utkasten i logs/agent_artifacts/.

Användning (från repo-roten, i .venv):
    python scripts/diagnostics/smoke_test_flow.py                              # plan, ingen kostnad
    python scripts/diagnostics/smoke_test_flow.py --run                        # demo, konfigurerade modeller
    python scripts/diagnostics/smoke_test_flow.py --run --db svc_test --provider openai
    python scripts/diagnostics/smoke_test_flow.py --run --regeldatum 2026-11-01 --avvikelser
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

DEEP_MODEL = {"anthropic": "anthropic:claude-opus-5", "openai": "openai:gpt-6-astra"}
RULES_IN_FORCE = date(2026, 11, 1)
OPERATOR_ID = "rooktest"

# --- facit för scenariona (testunderlag, inte verksamhetslogik) ---------------------------------

SOURCE = "K-SIM-ITP-2027"
EXPECTED_CHANGE = {"key": "premium_age_end", "new_value": Decimal("67"), "valid_from": date(2027, 1, 1)}
EXPECTED_FIRST_YEAR = 2027  # demobeståndets äldre kohort (B-035 val K)
DEVIATION_DIR = REPO_ROOT / "tests" / "data" / "regelverk_avvikelser"
DEVIATIONS = {
    "K-SIM-INFO-2028": (0, "ändring utan produktparameter"),
    "K-SIM-SATS-2028": (2, "två parameterändringar i samma källa"),
}


@dataclass
class Report:
    checks: list[tuple[str, str, bool, str]] = field(default_factory=list)  # (slag, kontroll, ok, detalj)
    notes: list[str] = field(default_factory=list)
    cost: float = 0.0

    def check(self, kind: str, label: str, passed: bool, detail: str = "") -> bool:
        self.checks.append((kind, label, passed, detail))
        print(f"  [{'OK' if passed else 'FEL'}] {kind}: {label}" + (f" – {detail}" if detail else ""))
        return passed

    def note(self, text: str) -> None:
        self.notes.append(text)
        print(f"  [obs] {text}")

    @property
    def ok(self) -> bool:
        return all(passed for _, _, passed, _ in self.checks)


# --- databaser -----------------------------------------------------------------------------------


@contextmanager
def demo_database() -> Iterator[SimpleNamespace]:
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from services.db import session_factory_for
    from utils.demo_data import create_demo_database

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    create_demo_database(engine, with_proposals=False)
    try:
        yield SimpleNamespace(label="demo (SQLite i minnet)", factory=session_factory_for(engine), team_factories={})
    finally:
        engine.dispose()


@contextmanager
def svc_test_database() -> Iterator[SimpleNamespace]:
    """Eget schema i den isolerade testdatabasen, med teamens rättigheter på testrollerna."""
    from sqlalchemy import create_engine

    from services.db import session_factory_for
    from utils.agent_roles import ROLE_GRANTS
    from utils.demo_data import create_demo_database

    url = os.environ.get("SERVICES_TEST_POSTGRES_URL")
    if not url:
        raise SystemExit("SERVICES_TEST_POSTGRES_URL saknas i .env")
    if url == os.environ.get("DATABASE_URL"):
        raise SystemExit("SERVICES_TEST_POSTGRES_URL är DATABASE_URL – röktestet körs aldrig mot beståndet")
    shared = os.environ.get("SERVICES_TEST_AGENT_POSTGRES_URL")
    candidates = {team: os.environ.get(f"SERVICES_TEST_{team.upper()}_POSTGRES_URL") for team in ("aktuarie", "compliance")}
    production = {os.environ.get(f"AGENT_{t.upper()}_DATABASE_URL") for t in ROLE_GRANTS} - {None}
    if production & ({shared, *candidates.values()} - {None}):
        raise SystemExit("En testrolls anslutning pekar på beståndet")

    name = f"rooktest_{uuid.uuid4().hex[:12]}"
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{name}"')
    engine = create_engine(url, connect_args={"options": f"-csearch_path={name}"})
    agent_engines = []
    try:
        create_demo_database(engine, with_proposals=False)
        team_factories, used = {}, set()
        for team, own in candidates.items():
            agent_url = own or shared
            if not agent_url:
                continue
            agent_engine = create_engine(agent_url, connect_args={"options": f"-csearch_path={name}"})
            agent_engines.append(agent_engine)
            with agent_engine.connect() as conn:
                login = conn.exec_driver_sql("SELECT current_user").scalar_one()
            if login in used:  # samma inloggning kan bara bära ett teams rättigheter i schemat
                continue
            used.add(login)
            with engine.begin() as conn:
                for statement in replace(ROLE_GRANTS[team], role=login).statements(name):
                    conn.exec_driver_sql(statement)
            team_factories[team] = session_factory_for(agent_engine)
        yield SimpleNamespace(label=f"svc_test, schema {name} (tas bort efteråt)", factory=session_factory_for(engine),
                              team_factories=team_factories)
    finally:
        for agent_engine in agent_engines:
            agent_engine.dispose()
        engine.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA "{name}" CASCADE')
        admin.dispose()


@contextmanager
def deviation_root() -> Iterator[Path]:
    """Tillfällig kopia av regelverksdokumenten med avvikelsekällorna i bevakningen."""
    with tempfile.TemporaryDirectory(prefix="rooktest_regelverk_") as tmp:
        root = Path(tmp)
        shutil.copytree(REPO_ROOT / "04_regulatoriskt", root / "04_regulatoriskt")
        shutil.copytree(REPO_ROOT / "01_domän", root / "01_domän")
        for path in DEVIATION_DIR.glob("K-SIM-*.md"):
            shutil.copy(path, root / "04_regulatoriskt" / "03_bevakning" / path.name)
        yield root


# --- flödet --------------------------------------------------------------------------------------


def build_console(db, ai, rules_date: date, regulatory=None):
    from agents.flows.console import FlowConsole
    from services import ProductRuleCatalog, ServiceLayer

    rules = ProductRuleCatalog(today=rules_date)
    trusted = ServiceLayer(session_factory=db.factory, rules=rules)
    teams = {
        team: ServiceLayer(session_factory=db.team_factories.get(team, db.factory), validation_session_factory=db.factory,
                           agent_role=f"agent_{team}", rules=rules)
        for team in ("compliance", "aktuarie")
    }
    console = FlowConsole.build(db.factory, trusted=trusted, agent_service=teams["compliance"], team_services=teams,
                                simulated_role=not db.team_factories, ai=ai, regulatory=regulatory)
    return console, trusted


def agent_step(console, flow, key: str, report: Report):
    from services import Actor

    flow = console.run_next(flow.flow_id, flow.version, Actor.human(OPERATOR_ID))
    step = flow.step(key)
    run = (step.result or {}).get("run", {})
    report.cost += run.get("cost_usd") or 0.0
    models = sorted({e["model"] for e in console.journal(flow.flow_id, key) if e.get("type") == "model_returned"}) \
        if step.run_id else []
    tools = [e["skill"] for e in console.journal(flow.flow_id, key) if e.get("type") == "tool_intent"] \
        if step.run_id else []
    print(f"  {key}: {step.status}, körning {step.run_id}, {run.get('cost_usd', 0):.4f} USD, modell {', '.join(models) or '–'}")
    print(f"    verktyg: {', '.join(tools) or '–'}")
    if step.error:
        print(f"    fel: {step.error}")
    return flow, step, tools


def stored_value(trusted, key: str, on: date) -> Decimal | None:
    from services import Actor, OperationContext

    listing = trusted.execute("get_product_parameters", OperationContext(actor=Actor.system("rooktest")),
                              {"on_date": on.isoformat()}).output
    return next((v.value for v in listing.versions if v.key == key and v.state == "gällande"), None)


def approve_gate(console, flow, gate: str, details=None):
    from services import Actor

    return console.decide(flow.flow_id, flow.version, Actor.human(OPERATOR_ID), decision="approved",
                          seen_hash=flow.gate_hashes[gate], note="Röktest", details=details)


def reject_gate(console, flow, gate: str, note: str):
    from services import Actor

    return console.decide(flow.flow_id, flow.version, Actor.human(OPERATOR_ID), decision="rejected",
                          seen_hash=flow.gate_hashes[gate], note=note)


def check_interpretation(trusted, step, report: Report) -> list[dict]:
    """Verksamhetskontroller för en tolkning – gäller oavsett källa."""
    output = (step.result or {}).get("output") or {}
    result = output.get("result", {})
    changes = result.get("parameter_changes", [])
    sources = [s["handle"] for s in output.get("evidence", {}).get("sources", [])]
    drafts = [d["name"] for d in output.get("evidence", {}).get("drafts", [])]
    print(f"    sammanfattning: {result.get('summary', '–')}")
    print(f"    berörda regler: {', '.join(result.get('affected_rules', [])) or '–'}; lästa källor: {', '.join(sources) or '–'}")
    print(f"    utkast: {', '.join(drafts) or '–'}; osäkerheter: {len(result.get('uncertainties', []))}")
    for change in changes:
        print(f"    ändring: {change['key']} {change['current_value']} → {change['new_value']} från {change['valid_from']} ({change['rule_id']})")
        valid_from = date.fromisoformat(change["valid_from"])
        stored = stored_value(trusted, change["key"], valid_from - timedelta(days=1))
        report.check("verksamhet", f"nuvarande värde för {change['key']} stämmer med lagrad parameter",
                     stored is not None and Decimal(str(change["current_value"])) == stored,
                     f"tolkningen {change['current_value']}, lagrat {stored}")
        report.check("verksamhet", f"{change['key']} gäller från en månadsförsta", valid_from.day == 1, str(valid_from))
    return changes


def main_scenario(db, ai, rules_date: date, report: Report) -> None:
    from agents.flows.store import FlowError
    from services import Actor, OperationContext

    console, trusted = build_console(db, ai, rules_date)
    operator = Actor.human(OPERATOR_ID)
    print(f"\n== Huvudscenario {SOURCE}")
    flow = console.start(SOURCE, operator)
    flow, step, tools = agent_step(console, flow, "tolkning", report)
    if not report.check("verksamhet", "tolkningen är klar och prövad mot körningen", step.status == "completed",
                        step.error or ""):
        return
    if "get_product_parameters" not in tools:
        report.note("tolkningen anropade inte get_product_parameters – nuvarande värde är inte läst i körningen")
    changes = check_interpretation(trusted, step, report)
    rules = (step.result["output"]["result"].get("affected_rules") or [])
    if "PR-ITP1-016" not in rules:
        report.note("tolkningen nämner inte PR-ITP1-016 (frivillig premie 66–67), som ändringen berör")

    exact = report.check("facit", "exakt en parameterändring", len(changes) == 1, f"{len(changes)} st")
    if exact:
        c = changes[0]
        report.check("facit", "premium_age_end 66 → 67 från 2027-01-01",
                     (c["key"], Decimal(str(c["new_value"])), date.fromisoformat(c["valid_from"]))
                     == tuple(EXPECTED_CHANGE.values()), f"{c['key']} → {c['new_value']} från {c['valid_from']}")
    if not exact:
        reject_gate(console, flow, "g1", "Röktest: tolkningen gav inte exakt en ändring")
        return

    flow = approve_gate(console, flow, "g1")
    flow, step, _ = agent_step(console, flow, "insikt", report)
    if not report.check("verksamhet", "beståndsinsikten är klar och bär beräkningen ur betrodd kod",
                        step.status == "completed", step.error or ""):
        return
    output = step.result["output"]
    estimate = output["evidence"]["estimate"]
    print(f"    insikt: {output['result']['insight']}")
    for year in estimate["years"][:3]:
        print(f"    {year['year']}: {year['status']}, berörda {year.get('affected_persons')}, "
              f"extra premie {year.get('extra_premium_volume_sek')} kr")
    change = changes[0]
    report.check("verksamhet", "beräkningen gäller den godkända ändringen",
                 (estimate["key"], Decimal(str(estimate["value"])), estimate["valid_from"])
                 == (change["key"], Decimal(str(change["new_value"])), change["valid_from"]))
    report.check("facit", f"första berörda år {EXPECTED_FIRST_YEAR}", estimate["first_affected_year"] == EXPECTED_FIRST_YEAR,
                 str(estimate["first_affected_year"]))

    flow = approve_gate(console, flow, "g2", details={"rule_version": "1.1", "valid_from": change["valid_from"],
                                                      "decision_number": None})
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                            text=True, check=True).stdout.strip()
    flow = console.complete_manual(flow.flow_id, flow.version, operator,
                                   {"commit": commit, "note": "Röktest – ingen regeltext införd"})
    flow = console.run_next(flow.flow_id, flow.version, operator)
    activation = flow.step("aktivering")
    if rules_date < RULES_IN_FORCE:
        report.check("verksamhet", "regelgolvet stoppar aktiveringen före 2026-11-01",
                     flow.status == "reconciliation_required" and "2026-11-01" in (activation.error or "")
                     and activation.approval_id is None, flow.status)
        return
    if not report.check("verksamhet", "aktiveringen ligger i godkännandekön under compliance-agenten",
                        flow.status == "waiting_approval" and activation.approval_id is not None, flow.status):
        return
    request = trusted.approvals.get(activation.approval_id)
    report.check("verksamhet", "förslaget är länkat till tolkningens körning",
                 (request.proposed_by, request.run_id) == ("compliance_agent", flow.step("tolkning").run_id))
    trusted.approve(activation.approval_id, OperationContext(actor=operator), note="Röktest")
    flow = console.run_next(flow.flow_id, flow.version, operator)
    try:
        flow = console.run_next(flow.flow_id, flow.version, operator)
    except FlowError as exc:
        report.check("verksamhet", "verifieringen kördes", False, str(exc))
        return
    evidence = (flow.step("verifiering").result or {}).get("evidence", {})
    report.check("verksamhet", "verifieringen stämmer lagrade versioner mot beslutet",
                 flow.status == "completed" and evidence.get("verified") is True,
                 "; ".join(evidence.get("problems", [])) or flow.status)


def deviation_scenarios(db, ai, rules_date: date, report: Report) -> None:
    from agents.flows.store import FlowError
    from agents.gateways import RegulatoryGateway
    from services import Actor

    with deviation_root() as root:
        console, trusted = build_console(db, ai, rules_date, regulatory=RegulatoryGateway(root))
        for source, (expected, label) in DEVIATIONS.items():
            print(f"\n== Avvikelse {source}: {label}")
            flow = console.start(source, Actor.human(OPERATOR_ID))
            flow, step, _ = agent_step(console, flow, "tolkning", report)
            if not report.check("verksamhet", "tolkningen är klar och prövad mot körningen", step.status == "completed",
                                step.error or ""):
                continue
            changes = check_interpretation(trusted, step, report)
            report.check("facit", f"{expected} parameterändringar", len(changes) == expected, f"{len(changes)} st")
            if len(changes) == 1:
                report.note("en enda ändring – grind 1 skulle godkänna; flödet avslås i röktestet")
                reject_gate(console, flow, "g1", "Röktest")
                continue
            try:
                approve_gate(console, flow, "g1")
                report.check("verksamhet", "grind 1 vägrar godkänna annat än exakt en ändring", False)
            except FlowError as exc:
                report.check("verksamhet", "grind 1 vägrar godkänna annat än exakt en ändring", True, str(exc)[:90])
            flow = reject_gate(console, console.get(flow.flow_id), "g1", "Röktest: inte exakt en parameterändring")
            report.check("verksamhet", "avslaget stoppar flödet", flow.status == "rejected", flow.status)


# --- körning ---------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="store_true", help="Gör riktiga modellanrop (kostar)")
    parser.add_argument("--db", choices=("demo", "svc_test"), default="demo")
    parser.add_argument("--provider", choices=sorted(DEEP_MODEL), help="Peka rollen deep på leverantörens modell")
    parser.add_argument("--regeldatum", type=date.fromisoformat, default=date.today(),
                        help="Regelkatalogens datum i röktestet (standard: i dag)")
    parser.add_argument("--avvikelser", action="store_true", help="Tolka även de två avvikande testkällorna")
    args = parser.parse_args()

    from ai import AIClient, MissingKeyError
    from ai.keys import resolve_api_key

    environ = dict(os.environ)
    if args.provider:
        environ["AI_ROLE_DEEP"] = DEEP_MODEL[args.provider]
    ai = AIClient(environ=environ)
    role = ai.config.roles["deep"]
    primary = environ.get("AI_ROLE_DEEP", "").strip() or role.model
    print(f"Rollen deep: {primary}, reserv {', '.join(role.fallbacks) or '–'}")
    for team in ("compliance", "aktuarie"):
        provider = primary.split(":")[0]
        try:
            _, key_env = resolve_api_key(ai.config.providers[provider], team)
            print(f"{team}: nyckel för {provider} i {key_env}")
        except MissingKeyError as exc:
            print(f"{team}: {exc}")
            return 1
    stop = "verifiering" if args.regeldatum >= RULES_IN_FORCE else "aktivering (regelgolvet före 2026-11-01)"
    print(f"Plan: {args.db}, {SOURCE} till {stop}" + (", plus två avvikelsekällor" if args.avvikelser else "")
          + f". Regeldatum {args.regeldatum}.")
    if not args.run:
        print("Inga modellanrop gjorda. Kör med --run för att genomföra röktestet.")
        return 0

    report = Report()
    with (demo_database() if args.db == "demo" else svc_test_database()) as db:
        roles = ", ".join(f"{t} {'begränsad testroll' if t in db.team_factories else 'simulerad'}"
                          for t in ("compliance", "aktuarie"))
        print(f"Databas: {db.label}; roller: {roles}")
        main_scenario(db, ai, args.regeldatum, report)
        if args.avvikelser:
            deviation_scenarios(db, ai, args.regeldatum, report)

    failed = [(kind, label) for kind, label, passed, _ in report.checks if not passed]
    print(f"\nTotalt {report.cost:.4f} USD, {len(report.checks)} kontroller, {len(failed)} fel, {len(report.notes)} iakttagelser.")
    for kind, label in failed:
        print(f"  FEL ({kind}): {label}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
