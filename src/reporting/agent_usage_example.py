"""Bygg en helt fiktiv exempelrapport i Digital klarhet.

Läser endast det versionshanterade exempelunderlaget. Ingen databas, modell eller
logg läses. Kräver reportlab och lokala DM Sans-TTF-filer i --font-dir.
Utdata: output/pdf/agentnyttjande_september_2026.{pdf,md} och SVG-diagram.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

from reportlab.graphics import renderSVG
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors

from reporting.template import (
    CW,
    DEFAULT_FONTS,
    NAVY,
    PURPLE,
    TOKENS,
    WHITE,
    C,
    ChartStyle,
    Cover,
    Report,
    ReportMetadata,
    register_dm_sans,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/examples/agent_usage_2026_09.json"
SOURCE = ROOT / "06_design/exempel/rapportunderlag_agentnyttjande.md"
OUT = ROOT / "output/pdf"
NAME = "agentnyttjande_september_2026"
# Extra category colors belong to this example, not the shared brand palette.
MID = colors.HexColor("#B6A4ED")
GREY = colors.HexColor("#B9B5CD")
GREEN = colors.HexColor(TOKENS["status"]["success"]["text"])
MODES = {
    "manual": "Manuellt",
    "supported": "Agentstöd",
    "internal": "Agentutfört internt",
}
MODE_COLORS = [GREY, MID, PURPLE]
CHART_STYLE = ChartStyle()


def num(value, decimals=0):
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",")


def pct(value, decimals=1):
    return num(value * 100, decimals) + " %"


def mdtable(headers, rows):
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]
        + ["| " + " | ".join(map(str, row)) + " |" for row in rows]
    )


def metrics(d):
    assert d["synthetic"] is True
    agents = d["agents"]
    ids = {a["id"]: a for a in agents}
    role = {r: Counter() for r in d["roles"]}
    for agent in agents:
        result = Counter()
        for r, volume in agent["role_tokens_m"].items():
            cfg = d["roles"][r]
            inp = volume * cfg["input_share"]
            cache = inp * cfg["cached_input_share"]
            output = volume - inp
            cost = (
                (inp - cache) * cfg["sek_per_m_uncached_input"]
                + cache * cfg["sek_per_m_cached_input"]
                + output * cfg["sek_per_m_output"]
            )
            row = {
                "input": inp,
                "cache": cache,
                "output": output,
                "tokens": volume,
                "cost": cost,
            }
            role[r].update(row)
            result.update(row)
        agent.update(result)
    totals = Counter()
    for a in agents:
        totals.update(
            {
                k: a[k]
                for k in [
                    "input",
                    "cache",
                    "output",
                    "tokens",
                    "cost",
                    "runs",
                    "calls",
                    "root_runs",
                ]
            }
        )
    cases = Counter({mode: sum(t[mode] for t in d["case_types"]) for mode in MODES})
    total_cases = sum(cases.values())
    ai_cases = cases["supported"] + cases["internal"]
    for mode in MODES:
        assert cases[mode] == sum(w[mode] for w in d["weeks"])
    assert math.isclose(sum(w["tokens_m"] for w in d["weeks"]), totals["tokens"])
    incoming = Counter()
    for sender, receiver, n in d["delegations"]:
        assert sender in ids and receiver in ids and sender != receiver and n > 0
        incoming[receiver] += n
        # Cross-team jobs are routed to that team's leading agent.
        if ids[sender]["team"] != ids[receiver]["team"]:
            assert receiver not in {"data", "rapportering", "inkop"}
    for a in agents:
        assert a["runs"] == a["root_runs"] + incoming[a["id"]]
    delegation_total = sum(incoming.values())
    assert (
        totals["runs"]
        == totals["root_runs"] + delegation_total
        == sum(d["run_outcomes"].values())
    )
    assert sum(q["errors"] for q in d["quality"]) == sum(d["quality_severity"].values())
    assert sum(d["retry_causes"].values()) == 2022
    base = (
        sum(sum(t[m] for m in MODES) * t["manual_minutes"] for t in d["case_types"])
        / 60
    )
    actual = (
        sum(sum(t[m] * t[m + "_minutes"] for m in MODES) for t in d["case_types"]) / 60
    )
    assumptions = d["assumptions"]
    extra = assumptions["governance_hours"] + assumptions["platform_hours"]
    gross = base - actual
    net = gross - extra
    human = actual + extra
    auto_hours = (
        sum(
            d["automation_scenario"].get(t["name"], 0)
            * (t["supported_minutes"] - t["internal_minutes"])
            for t in d["case_types"]
        )
        / 60
    )
    within = sum(n for s, t, n in d["delegations"] if ids[s]["team"] == ids[t]["team"])
    pair = sum(
        n for s, t, n in d["delegations"] if {s, t} == {"handlaggning", "kommunikation"}
    )
    cache_saving = 0
    for r, v in role.items():
        cfg = d["roles"][r]
        additional = (v["input"] - v["cache"]) * 0.30
        cache_saving += additional * (
            cfg["sek_per_m_uncached_input"] - cfg["sek_per_m_cached_input"]
        )
    role_switch_saving = (
        role["deep"]["tokens"]
        * 0.25
        * (
            role["deep"]["cost"] / role["deep"]["tokens"]
            - role["standard"]["cost"] / role["standard"]["tokens"]
        )
    )
    return {
        "d": d,
        "agents": agents,
        "ids": ids,
        "role": role,
        "totals": totals,
        "cases": cases,
        "total_cases": total_cases,
        "ai_cases": ai_cases,
        "delegations": delegation_total,
        "within": within,
        "pair": pair,
        "base": base,
        "actual": actual,
        "extra": extra,
        "gross": gross,
        "net": net,
        "human": human,
        "auto_hours": auto_hours,
        "cache_saving": cache_saving,
        "role_switch_saving": role_switch_saving,
    }


def replacements(x):
    d = x["d"]
    t = x["totals"]
    a = d["assumptions"]
    case_cost = t["cost"] * d["case_attributed_share"]
    values = {
        "cases": num(x["total_cases"]),
        "ai_share": pct(x["ai_cases"] / x["total_cases"], 0),
        "internal_share": pct(x["cases"]["internal"] / x["total_cases"], 0),
        "gross_hours": num(x["gross"]),
        "extra_hours": num(x["extra"]),
        "net_hours": num(x["net"]),
        "human_hours": num(x["human"], 1),
        "direct_hours": num(x["actual"], 1),
        "baseline_hours": num(x["base"], 1),
        "capacity_gap": num(x["human"] - a["capacity_hours"], 1),
        "pair_share": pct(x["pair"] / x["delegations"]),
        "deep_token_share": pct(x["role"]["deep"]["tokens"] / t["tokens"]),
        "deep_cost_share": pct(x["role"]["deep"]["cost"] / t["cost"]),
        "tokens_m": num(t["tokens"]),
        "top3_token_share": pct(
            sum(
                z["tokens"]
                for z in sorted(x["agents"], key=lambda z: z["tokens"], reverse=True)[
                    :3
                ]
            )
            / t["tokens"]
        ),
        "specialist_cost_share": pct(
            (x["ids"]["compliance"]["cost"] + x["ids"]["aktuarie"]["cost"]) / t["cost"]
        ),
        "runs": num(t["runs"]),
        "calls": num(t["calls"]),
        "delegations": num(x["delegations"]),
        "cross_team": num(x["delegations"] - x["within"]),
        "within_team": num(x["within"]),
        "retries": num(sum(d["retry_causes"].values())),
        "retry_call_share": pct(sum(d["retry_causes"].values()) / t["calls"]),
        "sla_breaches": num(sum(q["sla_breaches"] for q in d["quality"])),
        "model_cost": num(t["cost"]),
        "overhead_value": num(x["extra"] * a["hourly_value_sek"]),
        "net_value": num(
            x["net"] * a["hourly_value_sek"] - t["cost"] - a["platform_cost_sek"]
        ),
        "case_model_cost": num(case_cost),
        "ai_cases": num(x["ai_cases"]),
        "cost_per_ai_case": num(case_cost / x["ai_cases"], 2),
        "automation_hours": num(x["auto_hours"], 1),
        "automation_human_hours": num(x["human"] - x["auto_hours"], 1),
    }
    values["table_modes"] = mdtable(
        ["Arbetssätt", "Ärenden", "Andel", "Förändring mot aug."],
        [
            ["Manuellt", num(x["cases"]["manual"]), "26 %", "-9 procentenheter"],
            ["Agentstöd", num(x["cases"]["supported"]), "44 %", "-1 procentenhet"],
            [
                "Agentutfört internt",
                num(x["cases"]["internal"]),
                "30 %",
                "+10 procentenheter",
            ],
            ["Totalt", num(x["total_cases"]), "100 %", "+200 ärenden"],
        ],
    )
    values["table_process"] = mdtable(
        ["Process", "Totalt", "Agentberört", "Agentutfört internt"],
        [
            [
                z["name"],
                num(sum(z[m] for m in MODES)),
                pct((z["supported"] + z["internal"]) / sum(z[m] for m in MODES), 0),
                pct(z["internal"] / sum(z[m] for m in MODES), 0),
            ]
            for z in d["case_types"]
        ],
    )
    values["table_token_scope"] = mdtable(
        ["Avgränsning", "Tokens", "Modellkostnad"],
        [
            ["Ärendehänfört", "142,8 miljoner", num(case_cost) + " kr"],
            ["Fristående uppdrag", "25,2 miljoner", num(t["cost"] - case_cost) + " kr"],
            [
                "Per agentberört ärende",
                num(142.8e6 / x["ai_cases"] / 1000, 1) + " tusen",
                num(case_cost / x["ai_cases"], 2) + " kr",
            ],
        ],
    )
    values["table_agents"] = mdtable(
        ["Agent", "Tokens, M", "Cache, M", "Körningar", "Modellanrop", "Kostnad, kr"],
        [
            [
                z["short"],
                num(z["tokens"], 1),
                num(z["cache"], 1),
                num(z["runs"]),
                num(z["calls"]),
                num(z["cost"]),
            ]
            for z in x["agents"]
        ]
        + [
            [
                "Totalt",
                num(t["tokens"], 1),
                num(t["cache"], 1),
                num(t["runs"]),
                num(t["calls"]),
                num(t["cost"]),
            ]
        ],
    )
    values["table_prices"] = mdtable(
        ["Modellroll", "Input utan cache", "Cachelagrad input", "Output"],
        [
            [
                r,
                num(v["sek_per_m_uncached_input"]),
                num(v["sek_per_m_cached_input"]),
                num(v["sek_per_m_output"]),
            ]
            for r, v in d["roles"].items()
        ],
    )
    values["table_role_totals"] = mdtable(
        ["Modellroll", "Tokens, M", "Kostnad, kr", "Kostnadsandel"],
        [
            [r, num(v["tokens"], 1), num(v["cost"]), pct(v["cost"] / t["cost"])]
            for r, v in x["role"].items()
        ],
    )
    approvals = d["approvals"]
    n = sum(approvals[k] for k in ["approved", "rejected", "withdrawn", "pending"])
    values["table_approvals"] = mdtable(
        ["Unika förslag", "Antal", "Andel av 820"],
        [
            [label, num(approvals[k]), pct(approvals[k] / n)]
            for k, label in [
                ("approved", "Godkända"),
                ("rejected", "Avslagna"),
                ("withdrawn", "Återtagna"),
                ("pending", "Öppna vid periodslut"),
            ]
        ],
    )
    values["table_sla"] = mdtable(
        ["Ärendekohort", "Median, tim", "P95, tim", "SLA-brott", "Andel"],
        [
            [
                MODES[q["mode"]],
                num(q["median_hours"], 1),
                num(q["p95_hours"], 1),
                num(q["sla_breaches"]),
                pct(q["sla_breaches"] / x["cases"][q["mode"]]),
            ]
            for q in d["quality"]
        ],
    )
    values["table_hours"] = mdtable(
        ["Mänskligt arbete", "Timmar", "Mätgrund"],
        [
            ["Manuell baslinje", num(x["base"], 1), "Samma processmix, antagna tider"],
            [
                "Direkt handläggning med agenter",
                num(x["actual"], 1),
                "Antagna tider per arbetssätt",
            ],
            [
                "Tillkommande centrala aktiviteter",
                num(x["extra"]),
                "96 timmar kontroll + 40 drift",
            ],
            [
                "Total belastning",
                num(x["human"], 1),
                "Direkt arbete + centrala aktiviteter",
            ],
            ["Nettopotential", num(x["net"]), "Baslinje minus total belastning"],
        ],
    )
    values["table_economics"] = mdtable(
        ["Illustrativ kalkylpost", "Belopp, kr", "Tolkning"],
        [
            [
                "Bruttotidens kapacitetsvärde",
                num(x["gross"] * a["hourly_value_sek"]),
                num(x["gross"]) + " timmar x 600 kr",
            ],
            [
                "Tillkommande mänskligt arbete",
                "-" + num(x["extra"] * a["hourly_value_sek"]),
                "136 timmar x 600 kr",
            ],
            ["Modellkostnad", "-" + num(t["cost"]), "Fiktiva rollpriser"],
            [
                "Plattform",
                "-" + num(a["platform_cost_sek"]),
                "Antaget tillkommande månadsbelopp",
            ],
            [
                "Teoretisk nettopotential",
                values["net_value"],
                "Inte realiserad kassabesparing",
            ],
        ],
    )
    retry_saving = t["cost"] * d["retry_token_and_cost_share"] * 0.5
    values["table_optimization"] = mdtable(
        ["Fristående alternativ", "Antagande", "Potential, kr/mån"],
        [
            [
                "Högre cacheandel",
                "50 till 65 % av input",
                num(x["cache_saving"])
                + " ("
                + pct(x["cache_saving"] / t["cost"])
                + ")",
            ],
            [
                "Mindre deep",
                "25 % av deep till standard",
                num(x["role_switch_saving"])
                + " ("
                + pct(x["role_switch_saving"] / t["cost"])
                + ")",
            ],
            [
                "Färre omtag",
                "Halvera omtagens volym och kostnad",
                num(retry_saving) + " (" + pct(retry_saving / t["cost"]) + ")",
            ],
        ],
    )
    values["table_actions"] = mdtable(
        ["Horisont", "Åtgärd", "Ansvar i scenariot", "Kontrollmått"],
        [
            [
                "0-30 dagar",
                "Bind ihop ärende, rotkörning, anrop och beslut",
                "Utveckling + processägare",
                "Täckning och avstämda totalsummor",
            ],
            [
                "0-30 dagar",
                "Minska schema- och verktygsfel vid omtag",
                "Utveckling",
                "Omtag per anrop, första-gången-rätt",
            ],
            [
                "0-30 dagar",
                "Standardisera beställningar mellan handläggning och kommunikation",
                "Försäkring + Kommunikation",
                "Kompletteringsvarv och ledtid",
            ],
            [
                "31-60 dagar",
                "Pröva cache och enklare modellroll på jämförbara uppgifter",
                "Utveckling + fackansvariga",
                "Kostnad per accepterat resultat",
            ],
            [
                "31-60 dagar",
                "Pilot för 360 ytterligare interna avslut",
                "Processägare + Compliance",
                "Kvalitet, avlastning och undantag",
            ],
            [
                "61-90 dagar",
                "Validera faktiskt tidsutfall och kapacitet",
                "Operatör + Ekonomi",
                "Mätta minuter och kvarvarande belastning",
            ],
        ],
    )
    values["table_reconciliation"] = mdtable(
        ["Kontroll", "Avstämt samband"],
        [
            ["Ärenden", "624 + 1 056 + 720 = 2 400"],
            ["Körningar", "2 000 rotkörningar + 9 000 barnkörningar = 11 000"],
            [
                "Mottagna uppdrag",
                "Varje agents körningar = egna rötter + inkommande delegeringar",
            ],
            ["Tokens", "140 M input + 28 M output = 168 M; cache 70 M ingår i input"],
            ["Modellroller", "90 M fast + 60 M standard + 18 M deep = 168 M"],
            ["Modellkostnad", "3 960 + 10 360 + 11 500 = 25 820 kr"],
            ["Granskat urval", "90 + 120 + 90 = 300; 9 + 6 + 3 = 18 avvikelser"],
            [
                "Kapacitet",
                num(x["base"], 1)
                + " - "
                + num(x["gross"])
                + " + 96 + 40 = "
                + num(x["human"], 1)
                + " timmar",
            ],
        ],
    )
    return values


def chart_weekly(x, style=CHART_STYLE):
    d = Drawing(CW, 227)
    left = 35
    bottom = 42
    top = 193
    plotw = CW - 45
    for tick in [0, 200, 400, 600]:
        y = bottom + tick / 650 * (top - bottom)
        style.line(d, left, y, CW, y)
        style.text(d, left - 8, y - 3, tick, 9, C["text_muted"], "end")
    bw = 48
    for i, w in enumerate(x["d"]["weeks"]):
        xx = left + 25 + i * (plotw / 5)
        y = bottom
        for mode, color in zip(MODES, MODE_COLORS):
            h = w[mode] / 650 * (top - bottom)
            style.rect(d, xx, y, bw, h, color)
            y += h
        style.text(
            d,
            xx + bw / 2,
            y + 6,
            sum(w[m] for m in MODES),
            10,
            anchor="middle",
            bold=True,
        )
        style.text(d, xx + bw / 2, bottom - 17, w["label"], 9, anchor="middle")
    style.text(d, 0, 211, "Antal stängda ärenden", 10, bold=True)
    style.legend(d, list(zip(MODES.values(), MODE_COLORS)), 3)
    return d


def chart_process(x, style=CHART_STYLE):
    d = Drawing(CW, 244)
    left = 160
    width = CW - left - 23
    style.legend(d, list(zip(MODES.values(), MODE_COLORS)), 228)
    for i, p in enumerate(x["d"]["case_types"]):
        y = 195 - i * 29
        style.text(d, 0, y + 4, p["name"], 9)
        xx = left
        for mode, color in zip(MODES, MODE_COLORS):
            ww = p[mode] / 960 * width
            style.rect(d, xx, y, ww, 15, color)
            xx += ww
        style.text(d, xx + 5, y + 3, num(sum(p[m] for m in MODES)), 9)
    for tick in [0, 240, 480, 720, 960]:
        xx = left + tick / 960 * width
        style.text(d, xx, 12, tick, 9, C["text_muted"], "middle")
    style.text(d, left, 0, "Antal ärenden", 9, C["text_muted"])
    return d


def chart_tokens(x, style=CHART_STYLE):
    d = Drawing(CW, 255)
    left = 112
    width = CW - left - 30
    style.legend(
        d,
        [("Input utan cache", MID), ("Cachelagrad input", PURPLE), ("Output", NAVY)],
        238,
    )
    for i, a in enumerate(sorted(x["agents"], key=lambda a: a["tokens"], reverse=True)):
        y = 212 - i * 18
        style.text(d, 0, y + 3, a["short"], 9)
        xx = left
        for volume, color in [
            (a["input"] - a["cache"], MID),
            (a["cache"], PURPLE),
            (a["output"], NAVY),
        ]:
            ww = volume / 48 * width
            style.rect(d, xx, y, ww, 12, color)
            xx += ww
        style.text(d, xx + 5, y + 2, num(a["tokens"]), 9, bold=True)
    for tick in [0, 12, 24, 36, 48]:
        style.text(d, left + tick / 48 * width, 26, tick, 9, C["text_muted"], "middle")
    style.text(d, left, 9, "Miljoner tokens - cache ingår i input", 9, C["text_muted"])
    return d


def chart_role(x, style=CHART_STYLE):
    d = Drawing(CW, 203)
    left = 80
    width = CW - left - 45
    style.legend(d, [("Andel tokens", MID), ("Andel modellkostnad", PURPLE)], 187)
    for i, (name, r) in enumerate(x["role"].items()):
        y = 149 - i * 48
        style.text(d, 0, y, name, 11, bold=True)
        for yy, share, color in [
            (y + 3, r["tokens"] / x["totals"]["tokens"], MID),
            (y - 13, r["cost"] / x["totals"]["cost"], PURPLE),
        ]:
            ww = share / 0.6 * width
            style.rect(d, left, yy, ww, 11, color)
            style.text(d, left + ww + 5, yy + 1, pct(share), 9)
    style.text(d, left, 3, "Andel inom respektive mått", 9, C["text_muted"])
    return d


def chart_matrix(x, style=CHART_STYLE):
    d = Drawing(CW, 370)
    cell = 32
    left = 135
    bottom = 25
    values = {(s, t): n for s, t, n in x["d"]["delegations"]}
    for i, a in enumerate(x["agents"]):
        y = bottom + (9 - i) * cell
        style.text(d, left - 10, y + 11, a["short"], 9, anchor="end")
        style.text(
            d,
            left + i * cell + cell / 2,
            bottom + 10 * cell + 10,
            a["abbr"],
            9,
            anchor="middle",
            bold=True,
        )
        for j, b in enumerate(x["agents"]):
            xx = left + j * cell
            n = values.get((a["id"], b["id"]), 0)
            if i == j:
                style.rect(d, xx, y, cell - 2, cell - 2, C["background"])
                style.text(d, xx + 15, y + 10, "-", 9, C["text_muted"], "middle")
            elif n:
                weight = 0.12 + 0.88 * (n / 1400)
                col = colors.Color(
                    1 + (PURPLE.red - 1) * weight,
                    1 + (PURPLE.green - 1) * weight,
                    1 + (PURPLE.blue - 1) * weight,
                )
                style.rect(d, xx, y, cell - 2, cell - 2, col)
                style.text(
                    d,
                    xx + 15,
                    y + 10,
                    n,
                    9,
                    WHITE if n >= 650 else NAVY,
                    "middle",
                    bold=n >= 650,
                )
    style.text(
        d,
        left,
        5,
        "Mottagare i kolumn / avsändare i rad / antal uppdrag",
        9,
        C["text_muted"],
    )
    return d


def chart_top(x, style=CHART_STYLE):
    d = Drawing(CW, 281)
    left = 255
    width = CW - left - 35
    for i, (s, t, n) in enumerate(
        sorted(x["d"]["delegations"], key=lambda z: z[2], reverse=True)[:8]
    ):
        y = 249 - i * 29
        style.text(d, 0, y + 3, x["ids"][s]["short"] + " > " + x["ids"][t]["short"], 9)
        style.rect(d, left, y, n / 1400 * width, 15, PURPLE if i < 2 else MID)
        style.text(d, left + n / 1400 * width + 5, y + 3, num(n), 9, bold=True)
    style.text(d, 0, 270, "Antal riktade delegeringar", 10, bold=True)
    style.text(d, left, 0, "Uppdrag, inte enskilda meddelanden", 9, C["text_muted"])
    return d


def chart_outcomes(x, style=CHART_STYLE):
    d = Drawing(CW, 163)
    left = 140
    width = CW - left - 75
    labels = {
        "completed": "Completed",
        "waiting_approval": "Waiting approval",
        "needs_human": "Needs human",
        "blocked": "Blocked",
        "failed": "Failed",
    }
    for i, (name, n) in enumerate(x["d"]["run_outcomes"].items()):
        y = 133 - i * 27
        style.text(d, 0, y + 3, labels[name], 9)
        style.rect(
            d,
            left,
            y,
            n / x["totals"]["runs"] * width,
            13,
            PURPLE if name == "completed" else MID,
        )
        style.text(
            d, CW, y + 2, num(n) + " / " + pct(n / x["totals"]["runs"]), 9, anchor="end"
        )
    return d


def chart_quality(x, style=CHART_STYLE):
    d = Drawing(CW, 140)
    left = 150
    width = CW - left - 100
    for i, q in enumerate(x["d"]["quality"]):
        y = 106 - i * 35
        rate = q["errors"] / q["sample"]
        style.text(d, 0, y + 3, MODES[q["mode"]], 9)
        style.rect(d, left, y, rate / 0.12 * width, 17, MODE_COLORS[i])
        style.text(
            d,
            CW,
            y + 3,
            f"{q['errors']} / {q['sample']} = " + pct(rate),
            10,
            anchor="end",
            bold=True,
        )
    style.text(
        d, 0, 130, "Andel granskade ärenden med minst en avvikelse", 10, bold=True
    )
    return d


def chart_capacity(x, style=CHART_STYLE):
    d = Drawing(CW, 211)
    left = 35
    bottom = 38
    height = 145
    maximum = 1800
    for v in [0, 400, 800, 1200, 1600]:
        y = bottom + v / maximum * height
        style.line(d, left, y, CW, y)
        style.text(d, left - 7, y - 3, num(v), 9, C["text_muted"], "end")
    vals = [
        ("Baslinje", 0, x["base"], PURPLE, num(x["base"])),
        ("Avlastning", x["actual"], x["gross"], MID, "-" + num(x["gross"])),
        ("Kontroll", x["actual"], 96, MID, "+96"),
        ("Plattform", x["actual"] + 96, 40, MID, "+40"),
        ("Kvarstår", 0, x["human"], NAVY, num(x["human"])),
    ]
    for i, (label, base, delta, color, value) in enumerate(vals):
        xx = left + 20 + i * 91
        style.rect(
            d, xx, bottom + base / maximum * height, 49, delta / maximum * height, color
        )
        style.text(
            d,
            xx + 24.5,
            bottom + (base + delta) / maximum * height + 7,
            value,
            10,
            anchor="middle",
            bold=True,
        )
        style.text(d, xx + 24.5, 20, label, 9, anchor="middle")
    style.text(d, 0, 199, "Mänskliga timmar - modellerad månad", 10, bold=True)
    return d


def chart_program_cost(x, style=CHART_STYLE):
    d = Drawing(CW, 127)
    total = (
        x["totals"]["cost"]
        + x["d"]["assumptions"]["platform_cost_sek"]
        + x["extra"] * 600
    )
    segments = [
        ("Modellanrop", x["totals"]["cost"], PURPLE),
        ("Plattform", 6000, MID),
        ("Mänskligt tilläggsarbete", x["extra"] * 600, NAVY),
    ]
    xx = 0
    for label, value, color in segments:
        ww = value / total * CW
        style.rect(d, xx, 71, ww, 26, color)
        xx += ww
    for i, (label, value, color) in enumerate(segments):
        style.rect(d, 0, 47 - i * 19, 8, 8, color)
        style.text(d, 14, 47 - i * 19, label, 9)
        style.text(d, CW, 47 - i * 19, num(value) + " kr", 9, anchor="end")
    style.text(
        d,
        0,
        112,
        "Tillkommande resurskostnad i kalkylen: " + num(total) + " kr",
        10,
        bold=True,
    )
    return d


CHARTS = {
    "cases_weekly": chart_weekly,
    "cases_process": chart_process,
    "tokens_agent": chart_tokens,
    "role_share": chart_role,
    "delegation_matrix": chart_matrix,
    "top_delegations": chart_top,
    "run_outcomes": chart_outcomes,
    "quality_sample": chart_quality,
    "human_capacity": chart_capacity,
    "program_cost": chart_program_cost,
}


def table_widths(headers):
    """Editorial column widths for this report's particular tables."""
    n = len(headers)
    if n == 6:
        widths = [132, 64, 64, 70, 82, CW - 412]
    elif n == 5:
        widths = [164, 75, 75, 75, CW - 389]
    elif n == 4:
        widths = [155, 110, 115, CW - 380]
        if headers[0] == "Horisont":
            widths = [61, 179, 112, CW - 352]
    elif n == 3:
        widths = [205, 104, CW - 309]
        if headers[0] == "Illustrativ kalkylpost":
            widths = [201, 90, CW - 291]
        if headers[0] == "Fristående alternativ":
            widths = [143, 210, CW - 353]
    else:
        widths = [140, CW - 140]
    return widths


def key_figures(x):
    return [
        ("Agentberörda ärenden", "74 %", "1 776 av 2 400"),
        ("Agentutförda internt", "30 %", "720 av 2 400"),
        ("Modellkostnad", num(x["totals"]["cost"]) + " kr", "Fiktiva rollpriser"),
        ("Tokenvolym", "168 M", "Inklusive 70 M cache"),
        ("Nettopotential", num(x["net"]) + " tim", "Efter 136 tim tillägg"),
        ("Mänskligt arbete", num(x["human"]) + " tim", "Mot 800 tim kapacitet"),
    ]


COVER = Cover(
    eyebrow="EXEMPELRAPPORT / SIMULERAD MÅNAD",
    title_lines=("När agenterna", "blir en del", "av arbetet."),
    description="Agentnyttjande, kostnad, kvalitet och samverkan. En ledningsrapport med september 2026 som fiktiv rapportmånad.",
    highlight_value="74 %",
    highlight_label="av ärendena berör en agent.",
    highlight_detail="30 % är agentutförda interna flöden.",
    highlight_note="Användning är inte samma sak som autonomi.",
    metrics=(
        ("2 400", "stängda ärenden"),
        ("168 M", "tokens totalt"),
        ("25 820 kr", "modellkostnad"),
    ),
    note="Helt påhittade data för ett tänkt moget driftläge. Ingen verklig drift, kunddata eller aktuell leverantörsprislista har använts.",
    footer="24 oktober 2026 / Rapport 1.0 / Digital klarhet 1.0",
)


def build_report(path, x, content, drawings, *, fonts=DEFAULT_FONTS):
    report = Report(
        path,
        ReportMetadata(
            title="Agentnyttjande - fiktiv exempelrapport - september 2026",
            header="AGENT INSIGHT / SEPTEMBER 2026",
            footer="FIKTIVT SCENARIO - EJ DRIFTSTATISTIK",
            subject="Digital klarhet v1.0 / B-034. Helt fiktivt scenario.",
        ),
        fonts=fonts,
    )
    report.render(
        content,
        drawings=drawings,
        kpis=key_figures(x),
        cover=COVER,
        table_widths=table_widths,
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path, default=ROOT / "tmp/pdfs/fonts")
    args = parser.parse_args()
    try:
        fonts = register_dm_sans(args.font_dir)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    x = metrics(json.loads(DATA.read_text(encoding="utf-8")))
    content = SOURCE.read_text(encoding="utf-8")
    for name, value in replacements(x).items():
        content = content.replace("{{" + name + "}}", value)
    assert "{{" not in content, re.findall(r"\{\{.+?\}\}", content)
    OUT.mkdir(parents=True, exist_ok=True)
    figures = OUT / "figures"
    figures.mkdir(exist_ok=True)
    (OUT / (NAME + ".md")).write_text(content, encoding="utf-8")
    drawings = {name: func(x, ChartStyle(fonts)) for name, func in CHARTS.items()}
    for name, drawing in drawings.items():
        renderSVG.drawToFile(drawing, str(figures / (name + ".svg")))
    report = build_report(OUT / (NAME + ".pdf"), x, content, drawings, fonts=fonts)
    audit = {
        "synthetic": True,
        "pages": report.audit,
        "totals": dict(x["totals"]),
        "hours": {
            k: x[k] for k in ["base", "actual", "extra", "gross", "net", "human"]
        },
        "checks": "Case/weekly totals, tokens, root/child run graph, quality totals and cross-team routing validated",
        "fonts": ["DM Sans Regular", "DM Sans Medium", "DM Sans Bold"],
    }
    (ROOT / "tmp/pdfs").mkdir(parents=True, exist_ok=True)
    (ROOT / "tmp/pdfs/agent_usage_validation.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "pdf": str(OUT / (NAME + ".pdf")),
                "pages": len(report.audit),
                "lowest_remaining_space_pt": min(
                    z["remaining_pt"] for z in report.audit if z["id"] != "cover"
                ),
                "cost_sek": x["totals"]["cost"],
                "human_hours": x["human"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
