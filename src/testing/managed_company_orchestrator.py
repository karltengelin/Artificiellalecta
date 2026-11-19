"""Claude Managed Agents-brygga för det isolerade bolagsprovet."""

import json
from pathlib import Path
from time import monotonic, sleep

from pydantic import ValidationError

from agents.assignments import run_assignment
from agents.company_tools import SKILL, TEAM
from agents.dispatcher import CallStatus, Dispatcher
from agents.journal import FileJournal, mask, text_ref
from agents.loop import RunOutcome, build_context
from agents.profile import compile_profile
from agents.results import CoordinationAnswer, ResultError, verify
from agents.run import RunResult, RunStatus
from ai import ToolCall
from ai.keys import resolve_api_key
from ai.providers.anthropic_managed import ManagedAPIError, managed_client
from utils.checksums import canonical_hash


RESPONSE_RULES = (
    "Svara med högst tre korta meningar i summary. Använd bara siffror där när du svarar direkt "
    "ur ett läst dokument. När ett uppdrag har en premieanalys skriver du slutsatsen i ord och "
    "hänvisar till tabellen. Skriv då inga datum, tal eller id:n i summary. "
    "I assignment_refs kopierar du exakt id för de aktuella deluppdrag som du har läst med status. "
    "I source_handles får du bara ta med handtag som du själv har öppnat med read_regulatory_document "
    "i just detta segment. Utelämna övriga handtag även om de finns i specialistens källista."
)


def user_message(text):
    return {"type": "user.message", "content": [{"type": "text", "text": text}]}


def inline_tool_schema(schema):
    """Managed Agents saknar stöd för referenser i de tre verktygsschemana."""
    definitions = schema.get("$defs", {})

    def expand(node):
        if isinstance(node, list):
            return [expand(value) for value in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            name = node["$ref"].removeprefix("#/$defs/")
            node = {**definitions[name], **{key: value for key, value in node.items() if key != "$ref"}}
        return {key: expand(value) for key, value in node.items() if key != "$defs"}

    return expand(schema)


class ManagedCompanyOrchestrator:
    def __init__(self, ai, environ, directory: Path):
        choice = ai.config.resolve("standard", environ)
        primary = choice.chain[0]
        if primary.provider != "anthropic":
            raise ValueError("Välj samma Claude-modell för standardrollen i båda proven")
        self.model, self.effort = primary.model, choice.effort
        self.key, _ = resolve_api_key(ai.config.providers[primary.provider], TEAM, environ)
        self.directory = directory
        self.resources = directory / "managed-resources.json"

    def setup(self, api, system, tools):
        config = {"model": {"id": self.model, "effort": self.effort}, "system": system,
                  "tools": [{"type": "custom", "name": t.name, "description": t.description,
                             "input_schema": inline_tool_schema(t.parameters)} for t in tools]}
        fingerprint = canonical_hash(config)
        if self.resources.exists():
            resources = json.loads(self.resources.read_text(encoding="utf-8"))
            if resources["fingerprint"] != fingerprint:
                raise RuntimeError("Den hostade agentens konfiguration ändrades mellan segment")
            return resources
        name = "Artificiellalecta – syntetiskt bolagsprov"
        environment = api.environments.create(name=name, config={
            "type": "cloud",
            "networking": {"type": "limited", "allowed_hosts": [], "allow_package_managers": False},
        })
        agent = api.agents.create(name=name, **config)
        resources = {"fingerprint": fingerprint, "agent": agent.id, "version": agent.version,
                     "environment": environment.id}
        self.resources.write_text(json.dumps(resources, indent=2), encoding="utf-8")
        return resources

    def __call__(self, ai, ecosystem, skills, service, request, *, gateways, run_id, journal_dir, **kwargs):
        if request.target_team != TEAM:
            return run_assignment(ai, ecosystem, skills, service, request, gateways=gateways, run_id=run_id,
                                  journal_dir=journal_dir, **kwargs)
        if any(kwargs.values()) or request.result_schema != "CoordinationAnswer":
            raise ValueError("Bryggan stöder bara samordningsprofilen i demoprovet")
        profile = compile_profile(ecosystem, skills, service, request=request)
        tools = profile.tool_specs()
        if {t.name for t in tools} != {SKILL, "list_regulatory_documents", "read_regulatory_document"}:
            raise ValueError("Den hostade samordningsprofilens verktyg har ändrats")
        system, first = build_context(profile, request)
        host_system = system + (
            "\n\nReturnera slutsvaret som ett ensamt JSON-objekt utan kodstaket. Använd exakt detta schema:\n"
            + json.dumps(CoordinationAnswer.model_json_schema(), ensure_ascii=False)
            + "\n\n" + RESPONSE_RULES
        )
        journal = FileJournal(journal_dir, run_id=run_id, root_run_id=request.root_run_id,
                              team=profile.team, agent=profile.agent_id)
        began = monotonic()
        journal.append("run_started", task_id=request.task_id, goal=text_ref(request.goal),
                       model_role=profile.model_role, limits=profile.limits.model_dump())
        journal.append("policy_resolved", tools=[{"skill": t.name} for t in tools], hidden=[])
        dispatcher = Dispatcher(profile, service, run_id=run_id, gateways=gateways, observer=journal.append)
        dispatches = []
        session = usage = output = None
        steps = calls = 0
        status, summary = RunStatus.FAILED, "Managed Agents kunde inte slutföra samordningssegmentet."
        try:
            with managed_client(self.key) as api:
                resources = self.setup(api, host_system, tools)
                cents = int(profile.limits.max_cost_usd * 100)
                if cents < 1:
                    raise RuntimeError("Kvarvarande kostnadstak är mindre än en cent")
                session = api.sessions.create(
                    agent={"id": resources["agent"], "version": resources["version"], "type": "agent"},
                    environment_id=resources["environment"],
                    budget={"type": "limit", "max_list_cost": {"amount": str(cents), "currency": "USD"}},
                    initial_events=[user_message(first.text)],
                    metadata={"probe": "artificiellalecta-synthetic", "local_run_id": run_id},
                    title="Fråga bolaget – syntetiskt modellprov",
                )
                journal.append("managed_session_started", session_id=session.id, agent_id=resources["agent"],
                               agent_version=resources["version"], model=session.agent.model.id, effort=self.effort)
                processed = set()
                corrected = False
                while monotonic() - began < profile.limits.max_wall_seconds:
                    events = list(api.sessions.events.list(session.id, limit=100, order="asc"))
                    by_id = {event.id: event for event in events}
                    snapshots = [event.usage for event in events if event.type == "session.usage"]
                    if snapshots:
                        usage = snapshots[-1]
                    if monotonic() - began >= profile.limits.max_wall_seconds:
                        status, summary = RunStatus.LIMIT_REACHED, "Det hostade segmentet nådde sitt tidstak."
                        break
                    idle = next((ev for ev in reversed(events) if ev.type == "session.status_idle"), None)
                    if idle is None or idle.id in processed:
                        sleep(1)
                        continue
                    processed.add(idle.id)
                    steps += 1
                    details = idle.stop_reason
                    journal.append("managed_session_idle", step=steps, session_id=session.id, event_id_ref=idle.id,
                                   stop_reason=details.type, usage=usage.model_dump(mode="json") if usage else None)
                    if usage is None or usage.list_cost is None:
                        raise RuntimeError("Managed Agents rapporterade ingen verifierbar segmentkostnad")
                    if (details.type == "budget_reached" or cost_usd(usage) > profile.limits.max_cost_usd
                            or (details.type == "requires_action" and steps >= profile.limits.max_steps)):
                        status, summary = RunStatus.LIMIT_REACHED, "Det hostade samordningssegmentet nådde sitt körtak."
                        break
                    if details.type == "requires_action":
                        tool_events = [by_id[event_id] for event_id in details.event_ids]
                        if not all(ev.type == "agent.custom_tool_use" for ev in tool_events):
                            status, summary = RunStatus.BLOCKED, "Managed Agents begärde ett oväntat verktyg."
                            break
                        if calls + len(tool_events) > profile.limits.max_tool_calls:
                            status, summary = RunStatus.LIMIT_REACHED, "Det hostade segmentet nådde sitt verktygstak."
                            break
                        result = dispatcher.dispatch([ToolCall(id=ev.id, name=ev.name, arguments=ev.input)
                                                      for ev in tool_events])
                        dispatches.append(result)
                        calls += len(tool_events)
                        if result.denied:
                            status, summary = RunStatus.BLOCKED, "Den lokala dispatchern nekade ett hostat verktygsanrop."
                            break
                        if self.reconnect_order(session.id, idle, tool_events):
                            journal.append("managed_order_reconnected", session_id=session.id, event_id_ref=idle.id)
                        api.sessions.events.send(session.id, events=[
                            {"type": "user.custom_tool_result", "custom_tool_use_id": part.call_id,
                             "content": [{"type": "text", "text": part.content}]}
                            for part in result.results
                        ])
                        continue
                    if details.type != "end_turn":
                        break
                    try:
                        output = verify(CoordinationAnswer.model_validate_json(final_message(events, idle)),
                                        profile, dispatches)
                    except (ResultError, ValidationError) as exc:
                        problems = exc.problems if isinstance(exc, ResultError) else ("Använd exakt JSON-schemat.",)
                        journal.append("result_rejected", step=steps, problems=list(problems))
                        if corrected or steps >= profile.limits.max_steps:
                            status, summary = RunStatus.NEEDS_HUMAN, "Det hostade svaret kunde inte verifieras."
                            break
                        corrected = True
                        api.sessions.events.send(session.id, events=[
                            user_message("Rätta slutsvaret en gång med exakt samma JSON-schema och redan läst underlag. "
                                         "Fortsätt med ett slutsvar utan nya verktygsanrop. "
                                         + RESPONSE_RULES + "\nVerifieraren gav dessa skäl: " + " ".join(problems))
                        ])
                        continue
                    status, summary = RunStatus.COMPLETED, output["result"]["summary"]
                    break
                else:
                    status, summary = RunStatus.LIMIT_REACHED, "Det hostade segmentet nådde sitt tidstak."
                if status != RunStatus.COMPLETED:
                    api.sessions.events.send(session.id, events=[{"type": "user.interrupt"}])
        except ManagedAPIError as exc:
            journal.append("managed_api_error", error_type=str(exc), http_status=exc.status_code,
                           request_id=exc.request_id, detail=mask(exc.detail[:500]) if exc.detail else None)
            summary = f"Managed Agents-anropet misslyckades: {exc}."
            if session is not None:
                # Ett domänanrop kan redan vara sparat före ett transportfel. Lämna anspråket för avstämning.
                raise RuntimeError(summary) from None
        finally:
            elapsed = monotonic() - began
            cost = cost_usd(usage)
            evidence = tuple(f"{c.call_id}:{c.skill}" for d in dispatches for c in d.calls if c.status == CallStatus.DONE)
            journal.append("run_ended", status=status.value, summary=text_ref(summary), evidence_refs=list(evidence),
                           usage={"steps": steps, "tool_calls": calls, "cost_usd": cost if usage or session is None else None,
                                  "elapsed_seconds": elapsed})
            journal.close()
        outcome = RunResult(task_id=request.task_id, run_id=run_id, status=status, summary=summary,
                            evidence_refs=evidence, cost_usd=cost, output=output)
        return RunOutcome(outcome, system, (first,), tuple(dispatches), steps, calls, elapsed)

    def reconnect_order(self, session_id, idle, tool_events):
        marker = self.directory / "managed-reconnect.json"
        if marker.exists():
            return False
        order = next((event for event in tool_events if event.name == SKILL
                      and event.input.get("data", {}).get("action") == "order"), None)
        if order is None:
            return False
        # Efter dispatch, före kvittering. Hämta samma väntande anrop från en ny klient.
        with managed_client(self.key) as fresh:
            events = list(fresh.sessions.events.list(session_id, limit=100, order="asc"))
        pending = next(event for event in reversed(events) if event.type == "session.status_idle")
        repeated = next(event for event in events if event.id == order.id)
        if pending.id != idle.id or repeated.input != order.input:
            raise RuntimeError("Återanslutningens väntande verktygsanrop stämde inte")
        marker.write_text(json.dumps({"session": session_id, "idle_event": idle.id, "order_event": order.id}),
                          encoding="utf-8")
        return True


def cost_usd(usage):
    return int(usage.list_cost.amount) / 100 if usage and usage.list_cost else 0.0


def final_message(events, idle):
    for event in reversed(events[:events.index(idle)]):
        if event.type == "agent.message":
            return "".join(block.text for block in event.content if block.type == "text")
        if event.type == "user.message":
            break
    return ""
