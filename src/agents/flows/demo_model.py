"""Skriptad modell för flödesdemon i handläggar-UI:t (Fas 3c 3c-3, B-035).

I demo och `svc_test` körs agentstegen i `rule_change_parameter` mot en FakeProvider med
förskrivna svar för den fiktiva källan K-SIM-ITP-2027: inga modellanrop, ingen nyckel och
ingen kostnad. Svaren går genom samma harness som en riktig modell – profil, dispatcher,
gateways, mandat, resultatscheman och körjournal – så att verktygen faktiskt körs och
bevisen (lästa källor, skrivna utkast, beräkningen) kommer ur körningen, inte ur skriptet.
Röktest mot riktig modell hör till 3c-V.

    model = DemoModel()
    model.load(script_for("tolkning", flow))   # före *Kör nästa steg*
"""

from __future__ import annotations

import json
from typing import Any

from ai import AIClient, AIConfig
from ai.providers.fake import FakeProvider, ScriptItem, text_result, tool_call_result
from ai.tracing import MemoryTraceSink

#: Källan skriptet är skrivet för – andra källor kräver en riktig modell (3c-V)
DEMO_SOURCE = "K-SIM-ITP-2027"
MODEL_LABEL = "skriptad demomodell (FakeProvider) – inga modellanrop"

_CONFIG = {
    "providers": {"demo": {"type": "fake"}},
    "models": {"demo:skriptad": {"price": {"input": 0.0, "output": 0.0},
                                 "capabilities": {"tools": True, "structured_output": True}}},
    "roles": {"deep": {"model": "demo:skriptad"}, "standard": {"model": "demo:skriptad"}},
}


class DemoModel(FakeProvider):
    """FakeProvider vars skript byts före varje agentsteg."""

    def load(self, items: list[ScriptItem]) -> None:
        self._script = list(items)

    def client(self) -> AIClient:
        return AIClient(AIConfig.from_dict(_CONFIG), sink=MemoryTraceSink(), provider_overrides={"demo": self},
                        environ={})


def _action(data: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
    return {"data": data, "reason": reason}


def _read(handle: str, n: int) -> ScriptItem:
    return tool_call_result("read_regulatory_document", _action({"handle": handle, "section": None, "offset": 0}),
                            call_id=f"call_{n}")


def _draft(name: str, title: str, content: str, n: int) -> ScriptItem:
    return tool_call_result("write_draft", _action({"name": name, "title": title, "content": content},
                                                   "Utkast för operatörens granskning"), call_id=f"call_{n}")


ANALYSIS = """# Konsekvensanalys – K-SIM-ITP-2027 (fiktiv källa)

> Skriptat demosvar i handläggar-UI:t. Ingen modell har körts.

## Ändringen
Ordinarie premie betalas till och med månaden före den månad den anställde fyller **67 år** i stället
för 66, för premiemånader från och med **2027-01-01** (punkt 1–2 i källan).

## Berörda regler
- **PR-ITP1-013** premieperioder: premieåldern till ändras från 66 till 67 år. Parametern
  `premium_age_end` får en ny version från 2027-01-01.
- **PR-ITP1-016** kompletterande premier: den frivilliga grenen 66–67 år blir överflödig för
  ordinarie premie och bör ses över. Källan lämnar frågan öppen (punkt 4).

## Kundpåverkan
Anställda som fyller 66 år under 2027 eller senare får tolv premiemånader till. Enligt
övergångsregeln (punkt 3) återupptas premien från januari 2027 för den som fyllt 66 före dess.

## Osäkerheter
- Övergångsregeln förutsätter att anställningen pågår; försäkringar som blivit fribrev tas inte upp.
- PR-ITP1-016 behöver ett eget regelbeslut.
"""

RULE_DIFF = """# Förslag till ändrad regeltext – PR-ITP1-013 v1.1

> Utkast. Operatören för in texten i `01_domän/produktregler/` och parameterregistret (steg 3).

```diff
- Premie betalas t.o.m. månaden före den månad den försäkrade fyller 66 år.
+ Premie betalas t.o.m. månaden före den månad den försäkrade fyller 67 år
+ (premiemånader från 2027-01-01, K-SIM-ITP-2027).
```

Parameterregistret: `premium_age_end` = 67 år från 2027-01-01, regel PR-ITP1-013 v1.1.
"""

IMPACT_REPORT = """# Beståndsinsikt – premieålder 66 → 67 år från 2027-01-01

> Skriptat demosvar i handläggar-UI:t. Talen står i beräkningen i flödets steg, inte här.

Beräkningen gjordes i betrodd kod med premiemotorn, baslinje mot scenario per år. Volymen gäller
dagens lönenivå utan lönetillväxt och utan avkastning. Celler med färre än tio försäkrade är dolda.
"""


def interpretation_script(source: str) -> list[ScriptItem]:
    answer = {
        "summary": "Premieåldern i ITP1 höjs från 66 till 67 år för premiemånader från 2027-01-01 (fiktiv källa).",
        "affected_rules": ["PR-ITP1-013", "PR-ITP1-016"],
        "parameter_changes": [{
            "key": "premium_age_end", "current_value": "66", "new_value": "67", "valid_from": "2027-01-01",
            "rule_id": "PR-ITP1-013",
            "rationale": "Punkt 1 och 2 i källan: premie t.o.m. månaden före 67 år från januari 2027.",
        }],
        "customer_impact": "Anställda får premie ett år längre; den som fyllt 66 före 2027 återupptar premien.",
        "uncertainties": ["Övergången för fribrev anges inte i källan",
                          "PR-ITP1-016:s frivilliga gren 66–67 år behöver ett eget beslut"],
        "source_handles": [source, "PR-ITP1-013", "PR-ITP1-016"],
        "draft_names": ["konsekvensanalys.md", "regeldiff-pr-itp1-013.md"],
    }
    return [
        _read(source, 1),
        _read("PR-ITP1-013", 2),
        _read("PR-ITP1-016", 3),
        tool_call_result("get_product_parameters", _action({"on_date": None}), call_id="call_4"),
        _draft("konsekvensanalys.md", "Konsekvensanalys K-SIM-ITP-2027", ANALYSIS, 5),
        _draft("regeldiff-pr-itp1-013.md", "Förslag till PR-ITP1-013 v1.1", RULE_DIFF, 6),
        text_result(json.dumps(answer, ensure_ascii=False)),
    ]


def impact_script(change: dict[str, Any], horizon_years: int = 10) -> list[ScriptItem]:
    answer = {
        "insight": ("Höjningen ger extra premiemånader för aktiva som fyller 66 efter giltighetsdagen. "
                    "Antal berörda och extra premievolym per år står i beräkningen."),
        "key_findings": [f"Första berörda år och volym enligt beräkningen för {change['key']} = {change['new_value']}"],
        "uncertainties": ["Dagens lönenivå utan lönetillväxt och utan avkastning", "Dolda celler är inte noll"],
        "source_handles": [],
        "draft_names": ["bestandsinsikt.md"],
    }
    return [
        tool_call_result("estimate_parameter_change_impact", _action({
            "key": change["key"], "value": str(change["new_value"]), "valid_from": change["valid_from"],
            "horizon_years": horizon_years,
        }, "Beståndsinsikt för den godkända ändringen"), call_id="call_1"),
        _draft("bestandsinsikt.md", "Beståndsinsikt", IMPACT_REPORT, 2),
        text_result(json.dumps(answer, ensure_ascii=False)),
    ]


def script_for(step_key: str, flow) -> list[ScriptItem]:
    """Skriptet för flödets nästa agentsteg (`flow` är en FlowView)."""
    if step_key == "tolkning":
        return interpretation_script(flow.input["source_handle"])
    if step_key == "insikt":
        change = flow.step("tolkning").result["output"]["result"]["parameter_changes"][0]
        return impact_script(change)
    raise ValueError(f"Inget demoskript för steget '{step_key}'")
