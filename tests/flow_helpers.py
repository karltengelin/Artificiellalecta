"""Testdata för parameterändringsflödet. Importeras aldrig av verksamhetskoden.

FakeProvider levererar kontrollerade verktygsanrop för regressionstester;
beräkningar, behörighetskontroll och godkännanden körs av de riktiga komponenterna.
"""

import json

from ai import AIClient, AIConfig
from ai.providers.fake import FakeProvider, text_result, tool_call_result
from ai.tracing import MemoryTraceSink

SOURCE = "K-SIM-ITP-2027"
CHANGE = {"key": "premium_age_end", "current_value": "66", "new_value": "67",
          "valid_from": "2027-01-01", "rule_id": "PR-ITP1-013", "rationale": "Testunderlag"}


def call(name, data, number, reason=None):
    return tool_call_result(name, {"data": data, "reason": reason}, call_id=f"test_{number}")


def interpretation_script(source=SOURCE, change=None):
    change = change or CHANGE
    rules = list(dict.fromkeys([change["rule_id"], "PR-ITP1-016"]))
    reads = [call("read_regulatory_document", {"handle": h, "section": None, "offset": 0}, n)
             for n, h in enumerate([source, *rules], 1)]
    answer = {
        "summary": f"Teständring: {change['key']} från {change['current_value']} till {change['new_value']}",
        "affected_rules": rules, "parameter_changes": [change], "customer_impact": "Se beräkningen",
        "uncertainties": [], "source_handles": [source, *rules],
        "draft_names": ["konsekvensanalys.md", "regeldiff.md"],
    }
    return [*reads,
            call("write_draft", {"name": "konsekvensanalys.md", "title": "Konsekvensanalys",
                                 "content": f"# Konsekvensanalys – {source}"}, 4, "Testutkast"),
            call("write_draft", {"name": "regeldiff.md", "title": "Regeldiff",
                                 "content": f"# Regeldiff\n{change['rule_id']}"}, 5, "Testutkast"),
            text_result(json.dumps(answer, ensure_ascii=False))]


def impact_script(change=None):
    change = change or CHANGE
    answer = {"insight": "Testresultat; beloppen hämtas från beräkningsverktyget",
              "key_findings": ["Se beräkningen"], "uncertainties": [], "source_handles": [],
              "draft_names": ["bestandsinsikt.md"]}
    return [call("estimate_parameter_change_impact", {
                "key": change["key"], "value": change["new_value"],
                "valid_from": change["valid_from"], "horizon_years": 10}, 1, "Testberäkning"),
            call("write_draft", {"name": "bestandsinsikt.md", "title": "Beståndsinsikt",
                                 "content": "# Beståndsinsikt\nSe beräkningsresultatet."}, 2, "Testutkast"),
            text_result(json.dumps(answer, ensure_ascii=False))]


def flow_client(*, source=SOURCE, change=None, interpretation_responses=None):
    responses = interpretation_script(source, change) if interpretation_responses is None else interpretation_responses
    fake = FakeProvider([*responses, *impact_script(change)])
    config = AIConfig.from_dict({
        "providers": {"test": {"type": "fake"}},
        "models": {"test:flow": {"price": {"input": 0.0, "output": 0.0},
                                  "capabilities": {"tools": True, "structured_output": True}}},
        "roles": {"deep": {"model": "test:flow"}, "standard": {"model": "test:flow"}},
    })
    return AIClient(config, sink=MemoryTraceSink(), provider_overrides={"test": fake}, environ={})
