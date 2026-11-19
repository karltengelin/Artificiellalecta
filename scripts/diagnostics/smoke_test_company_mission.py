"""Prova Fråga bolaget med fiktiv källa och två processer mot samma SQLite-fil."""

import argparse
import json
import os
import sys
from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from argon2 import PasswordHasher
from dotenv import dotenv_values
from fastapi.testclient import TestClient

from agents.company_capabilities import ACTIVATE, APPROVE_INTERPRETATION, IMPACT, INTERPRET, parameter_on
from agents.gateways import ReadRegulatoryDocumentInput
from ai import AIClient
from ai.tracing import JsonlTraceSink
from services import Actor, OperationContext
from services.errors import ApprovalError
from services.operations import common
from tests.flow_helpers import call, impact_script
from tests.test_company_missions import (
    CHANGE, OPERATOR, ORIGIN, PASSWORD, QUESTION, SOURCE, Demo, answer, client, interpretation, login, order, tool,
)
from utils.checksums import canonical_hash
from web.app import create_app
from web.config import WebSettings
from web.routes.company_missions import BASE

AS_OF = date(2026, 11, 15)
SIMULATED = "Simulerat operatörsbeslut för modellprovet."


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


class Probe(Demo):
    def __init__(self, directory, live_client):
        settings = WebSettings(demo_path=directory / "demo.db", allowed_hosts=("testserver",),
                               operator_dataset_id="demo:bolagsorkestrator-modellprov",
                               operator_password_hash=PasswordHasher().hash(PASSWORD))
        super().__init__(settings, directory)
        self.live_client = live_client
        self.app = create_app(settings=settings, company_ai=live_client or client())
        self.web = TestClient(self.app, base_url="https://testserver", follow_redirects=False)
        login(self.web)
        self.pilot = self.app.state.company_missions
        self.pilot.journal_dir = directory / "runs"

    def website(self, *responses):
        if self.live_client is None:
            super().website(*responses)

    def segment(self, *responses, to):
        self.process(*responses)
        check(self.state["status"] == to,
              f"Väntade {to}, fick {self.state['status']}. Läs protokoll och körjournal.")

    def assignment(self, capability, team):
        items = [a for a in self.state["assignments"].values() if a["capability"] == capability]
        check(len(items) == 1 and items[0]["team"] == team, f"Väntade en beställning till {team}")
        return items[0]

    def review_binding(self, kind, interpretation_item, effect=None):
        review, = self.state["reviews"]
        check(review["kind"] == kind and review["basis"] == interpretation_item["id"]
              and review["basis_hash"] == canonical_hash(interpretation_item["result"])
              and review["effect"] == (effect["id"] if effect else None)
              and review["effect_hash"] == (canonical_hash(effect["result"]) if effect else None)
              and review["hash"] == canonical_hash({k: v for k, v in review.items() if k != "hash"}),
              "Granskningen gäller ett annat underlag")
        return review

    def verify_interpretation(self, item):
        output = item["result"]["output"]
        proposal = output["result"]
        expected = {key: value for key, value in CHANGE.items() if key != "rationale"}
        change, = proposal["parameter_changes"]
        observed = {key: change[key] for key in expected}
        for key in ("current_value", "new_value"):
            observed[key], expected[key] = Decimal(observed[key]), Decimal(expected[key])
        check(observed == expected and proposal["effective_on"] == CHANGE["valid_from"]
              and proposal["change_kind"] == "parameter", "Compliance ändrade det fiktiva regelunderlaget")
        source = self.pilot.gateways.regulatory.read_document(ReadRegulatoryDocumentInput(handle=SOURCE)).document
        evidence = {entry["handle"]: entry for entry in output["evidence"]["sources"]}
        check(source.fictional and SOURCE in evidence and CHANGE["rule_id"] in evidence
              and source.sha256 == evidence[SOURCE]["sha256"], "Källbevis för källan eller produktregeln saknas")
        drafts = output["evidence"]["drafts"]
        check(len(drafts) >= 2, "Compliance behöver lämna konsekvensanalys och regeltext")
        for draft in drafts:
            check(self.web.get(f"{self.url}/utkast/{item['id']}/{draft['name']}").status_code == 200,
                  "Utkastet går inte att öppna")


def start(probe):
    data = probe.start(goal=f"{QUESTION} Källa {SOURCE}")
    replay = probe.web.post(BASE, data=data, headers=ORIGIN)
    check(replay.status_code == 303 and replay.headers["location"] == probe.url, "Dubbel beställning")
    probe.segment(tool("catalog"), order(), order(), answer(), to="queued")
    check(len(probe.state["assignments"]) == 1, "Första segmentet ska bara beställa Compliance")
    probe.segment(*interpretation(), to="queued")
    item = probe.assignment(INTERPRET, "compliance")
    probe.verify_interpretation(item)
    probe.segment(tool("status"), tool("review", review_kind=APPROVE_INTERPRETATION, basis=item["id"]),
                  answer(assignments=[item["id"]]), to="waiting_review")
    probe.review_binding(APPROVE_INTERPRETATION, item)


def finish(probe):
    item = probe.assignment(INTERPRET, "compliance")
    probe.verify_interpretation(item)
    review = probe.review_binding(APPROVE_INTERPRETATION, item)
    probe.action("granska", expected=409, verdict="approved", seen="fel kontrollsumma")
    probe.decide(note=SIMULATED)
    check(probe.state["decisions"][-1]["hash"] == review["hash"], "Tolkningen bands inte till beslutet")
    probe.segment(tool("catalog"), tool("order", target_team="aktuarie", key="premie", basis=item["id"]),
                  answer(), to="queued")
    probe.segment(*impact_script(CHANGE), to="queued")
    impact = probe.assignment(IMPACT, "aktuarie")
    query = {"key": CHANGE["key"], "value": CHANGE["new_value"], "valid_from": CHANGE["valid_from"],
             "horizon_years": 10}
    trusted = probe.pilot.trusted
    expected = trusted.execute("estimate_parameter_change_impact", OperationContext(actor=Actor.system("modellprov")),
                               query).output.model_dump(mode="json")
    estimate = impact["result"]["output"]["evidence"]["estimate"]
    check(estimate == expected, "Premieeffekten avviker från en separat körning av tjänsteoperationen")
    probe.segment(tool("status"), tool("review", review_kind=ACTIVATE, basis=item["id"]),
                  answer(assignments=[item["id"], impact["id"]]), to="waiting_review")
    review = probe.review_binding(ACTIVATE, item, impact)
    probe.action("granska", expected=409, verdict="approved", seen="fel kontrollsumma")
    probe.decide(rule_version="1.1", valid_from=CHANGE["valid_from"], commit="abcdef1",
                 note=SIMULATED + " abcdef1 är en fiktiv regeltextreferens från pilotens test.")
    check(probe.state["decisions"][-1]["hash"] == review["hash"], "Regelbeslutet bands inte till underlaget")
    probe.segment(to="waiting_external")
    task = probe.state["external"]
    probe.segment(to="waiting_external")
    proposals = [a for a in trusted.approvals.list() if a.input.get("decision_ref") == task["request"]["decision_ref"]]
    check(len(proposals) == 1 and proposals[0].id == task["receipt"] and proposals[0].input == task["request"],
          "Förslaget är dubblerat eller gäller ett annat beslut")
    try:
        trusted.approve(task["receipt"], OperationContext(actor=Actor.agent("company_orchestrator")))
    except ApprovalError:
        pass
    else:
        raise RuntimeError("Agenten kunde godkänna förslaget")
    approval = probe.web.post(f"/godkannanden/{task['receipt']}/godkann",
                              data={"csrf_token": probe.session_csrf, "note": SIMULATED}, headers=ORIGIN)
    receipt = trusted.approvals.get(task["receipt"])
    check(approval.status_code == 200 and receipt.status == "approved" and receipt.decision_note == SIMULATED,
          "Simulerat operatörsgodkännande saknas i tjänstelagret")
    probe.segment(to="queued")
    effect, = probe.state["effects"]
    before = parameter_on(trusted, CHANGE["key"], date(2026, 12, 31))
    after = parameter_on(trusted, CHANGE["key"], date(2027, 1, 1))
    check(effect["receipt"] == task["receipt"] and effect["observed"]["effect"]["verified"]
          and before["value"] == Decimal("0.045") and after["value"] == Decimal("0.05")
          and after["rule_version"] == "1.1" and after["decision_ref"] == task["request"]["decision_ref"],
          "Tjänstelagret bekräftar inte datumgränsen eller beslutet")
    for month, amount in (("2026-12-01", Decimal("2025")), ("2027-01-01", Decimal("2250"))):
        preview = trusted.execute(
            "calculate_premium_preview", OperationContext(actor=Actor.system("modellprov")),
            {"monthly_salary_sek": "45000", "period_month": month, "latest_base_amount": True},
        ).output
        check(preview.total_premium_sek == amount, f"Premiemotorn använder fel sats för {month}")
    read_source = call("read_regulatory_document", {"handle": SOURCE, "section": None, "offset": 0}, "finish")
    probe.segment(read_source, tool("status"), answer("answered", sources=[SOURCE],
                  assignments=[item["id"], impact["id"]],
                  summary="Den fiktiva premiesatsen höjs. Se tolkningen och tabellen för premieeffekten. "
                          "Den framtida schemaläggningen är verifierad i parameterregistret."), to="answered")
    final = probe.state["messages"][-1]["answer"]["output"]
    check(set(final["result"]["assignment_refs"]) == {item["id"], impact["id"]},
          "Slutsvaret måste hänvisa till båda specialistresultaten")
    check(SOURCE in final["result"]["source_handles"]
          or SOURCE in {source["handle"] for result in final["evidence"]["assignments"] for source in result["sources"]},
          "Slutsvaret saknar källstöd")
    check(len(probe.state["assignments"]) == 2 and len(probe.state["decisions"]) == 2
          and len(probe.state["effects"]) == 1, "Oväntat antal beställningar, beslut eller kvitton")
    check(all(probe.web.get(f"{probe.url}/spar/{entry['run']}").status_code == 200 for entry in probe.state["runs"]),
          "Alla segment ska ha läsbara körspår")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("start", "finish"))
    parser.add_argument("--output-dir", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--scripted", action="store_true")
    mode.add_argument("--run-model", action="store_true")
    mode.add_argument("--managed", action="store_true", help="Claude Managed Agents för enbart bolagsorkestratören")
    parser.add_argument("--env-file", type=Path, help="Befintlig .env för modellnycklar och modellkonfiguration")
    args = parser.parse_args()
    mode_name = "scripted" if args.scripted else "managed" if args.managed else "model"
    directory = args.output_dir.resolve()
    checkpoint = directory / "restart.json"
    if args.phase == "start":
        directory.mkdir(parents=True, exist_ok=False)
    else:
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        saved_mode = saved.get("mode") or ("scripted" if saved["scripted"] else "model")
        check(saved_mode == mode_name, "Fortsätt med samma modelläge som vid starten")
        check(saved["pid"] != os.getpid(), "Fortsätt i en ny process")
    live, roles = None, {}
    if not args.scripted:
        env = {**(dotenv_values(args.env_file) if args.env_file else {}), **os.environ, "AI_LOG_CONTENT": "false"}
        live = AIClient(sink=JsonlTraceSink(directory / "ai_calls.jsonl"), environ=env)
        for role in ("standard", "deep"):
            resolution = live.config.resolve(role, env)
            roles[role] = {"models": [model.ref for model in resolution.chain], "effort": resolution.effort,
                           "max_output_tokens": resolution.max_output_tokens}
    if args.phase == "finish":
        check(saved["roles"] == roles, "Fortsätt med samma modellroller som vid starten")
    runner = nullcontext()
    if args.managed:
        from testing.managed_company_orchestrator import ManagedCompanyOrchestrator

        runner = patch("agents.company_missions.run_assignment", ManagedCompanyOrchestrator(live, env, directory))
    began = perf_counter()
    outcome = "avbrutet"
    with patch.object(common, "today", return_value=AS_OF), runner:
        probe = Probe(directory, live)
        try:
            if args.phase == "start":
                start(probe)
                checkpoint.write_text(json.dumps({"url": probe.url, "revision": probe.row["revision"],
                                                  "pid": os.getpid(), "mode": mode_name, "roles": roles}),
                                      encoding="utf-8")
            else:
                probe.url = saved["url"]
                check(probe.row["revision"] == saved["revision"] and probe.state["status"] == "waiting_review",
                      "Den sparade granskningsversionen ändrades mellan processerna")
                finish(probe)
            outcome = "godkänt"
        finally:
            if probe.url:
                protocol = {"phase": args.phase, "mode": mode_name,
                            "simulated_operator": OPERATOR.id, "domain_today": AS_OF.isoformat(),
                            "elapsed_seconds": round(perf_counter() - began, 3), "outcome": outcome,
                            "pid": os.getpid(), "url": probe.url, "roles": roles, "state": probe.state}
                (directory / f"{args.phase}.json").write_text(
                    json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"{args.phase}: {outcome} / {probe.state['status']} / {probe.url} / {protocol['elapsed_seconds']} s")


if __name__ == "__main__":
    main()
