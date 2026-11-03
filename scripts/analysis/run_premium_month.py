"""Kör P6-MANAD-001 endast i en lokal isolerad databas under tmp/premium_month/.

Utan --execute: kontrollera fryst källpaket och visa planen utan databas.
--execute: registrera/motta/stäng via tjänstelagret och lämna analysen för granskning.
--approve-checksum kräver exakt den granskningshash som föregående körning gav.
Det finns ingen Lakebase-flagga och ingen nätverksanslutning i detta körverktyg.
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from models import Base, ValuationBasis
from services import Actor, OperationContext, ServiceLayer, parameters
from services import valuation_bases as vb
from services.db import session_factory_for
from services.premium_month_inputs import MonthInputs, extended_returns, receipt_key

TABLES = {"product_parameters", "valuation_bases", "operation_events", "approval_requests", "valuation_extracts",
          "valuation_runs", "valuation_results", "premium_month_journals", "premium_receipts", "premium_month_closes"}


def markdown_report(output, summary, analyses):
    def money(value):
        return f"{Decimal(str(value)):,.2f}".replace(",", " ").replace(".", ",")

    base = analyses["base"]
    status = "godkänd analys" if summary["state"] == "approved_analysis" else "för mänsklig granskning"
    lines = ["# Avstämd syntetisk FTA-månad – november 2026", "",
        f"Status: {status}. Två scenariovärderingar; ingen låst bas.", "",
        (f"Ingående bestånd: {output['policies']} försäkringar. Mottagen syntetisk nettopremie: "
         f"{money(output['premiums_sek'])} SEK. Inga delade databasändringar."), "",
        "| FTA-brygga | SEK |", "|---|---:|"]
    lines += [f"| {row['label']} | {money(row['fta_sek'])} |" for row in base["rows"]]
    lines += ["", "Alla steg är källbundna. Oförklarat är noll på sex decimaler och på öret.", "",
              "| Kontroll | Ingående | Utgående |", "|---|---:|---:|"]
    for key, label in (("capital_sek", "Pensionskapital C"), ("surplus_sek", "Avstämd VÅ-visning"),
                        ("deficit_sek", "Underskott U"), ("surplus_display_adjustment_sek", "VÅ:s visningsavrundning")):
        lines.append(f"| {label} | {money(base['opening'][key])} | {money(base['closing'][key])} |")
    lines += ["", "| Separat scenario | Utgående FTA, SEK | Oförklarat, SEK |", "|---|---:|---:|"]
    for name, label in (("rate", "Räntekurva +50 bp"), ("expenses", "Driftkostnad +10 %"),
                        ("combined", "Ränta och driftkostnad")):
        a = analyses[name]
        lines.append(f"| {label} | {money(a['closing']['fta_sek'])} | {money(a['unexplained_sek'])} |")
    lines += ["", "Underlaget är rekonstruerat S-04 med syntetiska novemberbetalningar och syntetisk avkastning.",
        "Kapital, garanti och FTA är separata storheter. Inga utbetalningar, dödsfall, ALM eller solvens ingår.",
        "Grunderna är simuleringsval. Historiska garantidelar har bevarats.", "",
        f"Källpaket: `{output['inputs_checksum']}`", f"IB-utdrag: `{output['opening_checksum']}`",
        f"Granskningssumma: `{summary['review_checksum']}`", "",
        "Fullständiga steg, grundreferenser och kontrollsummor finns i JSON-underlaget bredvid denna rapport."]
    return "\n".join(lines)+"\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--expected-checksum", required=True)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--operator")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--approve-checksum")
    args = parser.parse_args()
    p = MonthInputs.model_validate_json(args.inputs.read_text(encoding="utf-8"))
    if p.checksum != args.expected_checksum:
        parser.error("Källpaketet motsvarar inte den granskade kontrollsumman")
    output = {"scenario_id": p.scenario_id, "synthetic": True, "inputs_checksum": p.checksum,
        "opening_checksum": p.opening.checksum, "policies": len(p.opening.policies),
        "premiums_sek": str(sum((r.net_sek for r in p.receipts), Decimal(0))), "shared_database_writes": False}
    if not args.execute:
        if args.approve_checksum:
            parser.error("Godkännande kräver --execute, lokal --database och namngiven --operator")
        print(json.dumps({**output, "plan_only": True}, ensure_ascii=True, indent=2))
        return
    if not args.database or not args.operator:
        parser.error("--execute kräver lokal --database och namngiven --operator")
    target = args.database.resolve()
    allowed = (ROOT / "tmp" / "premium_month").resolve()
    if not target.is_relative_to(allowed) or target.suffix not in (".db", ".sqlite", ".sqlite3"):
        parser.error("Databasen ska ligga i repots tmp/premium_month/ och ha SQLite-suffix")
    target.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{target}")
    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name in TABLES])
    factory = session_factory_for(engine)
    with factory() as s:
        parameters.add_missing_defaults(s)
        vb.add_missing_defaults(s)
    service = ServiceLayer(session_factory=factory)
    actor = Actor.human(args.operator)
    ctx = OperationContext(actor=actor, reason="Godkänt lokalt syntetiskt månadsförsök P6-MANAD-001")

    def call(name, data):
        result = service.execute(name, ctx, data)
        if result.pending:
            raise RuntimeError("Oväntat väntande förslag; körningen stoppas")
        return result.output

    print("Öppnar fryst S-04 och rekonstruerar kapitalspår...", flush=True)
    call("open_premium_month", {"inputs_json": p.model_dump_json(), "reviewed_checksum": p.checksum})
    print("Registrerar syntetiska mottagningar via tjänstelagret...", flush=True)
    for receipt in sorted(p.receipts, key=lambda r: (r.received_date, receipt_key(p.scenario_id, r))):
        call("receive_premium_payment", {"journal_id": p.scenario_id, "receipt": receipt.model_dump(mode="json")})
    # A4:s befintliga förslags-/antagandeväg, bara i den lokala databasen.
    with Session(engine) as s:
        avk = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "AVK-SIM-2026-02"))
        if avk is not None and vb.checksum(avk.assumptions) != vb.checksum(extended_returns(p)):
            raise ValueError("Den lokala AVK-versionen har annat innehåll")
    if avk is None:
        call("propose_valuation_basis", {"code": "AVK-SIM-2026-02", "title": "Syntetisk novemberbana",
            "assumptions": extended_returns(p), "source_refs": p.checksum, "supersedes_code": "AVK-SIM-2026-01"})
        call("adopt_valuation_basis", {"code": "AVK-SIM-2026-02", "valid_from": "2026-11-01",
                                        "decision_ref": "P6-MANAD-001 D5"})
    print("Stänger månaden och räknar oberoende A6-UB samt FTA-brygga...", flush=True)
    summary = call("close_premium_month", {"journal_id": p.scenario_id}).payload
    analyses = {}
    for name, effects in (("base", {}), ("rate", {"rate_shift_bp": 50}),
                          ("expenses", {"expense_factor": 1.1}),
                          ("combined", {"rate_shift_bp": 50, "expense_factor": 1.1})):
        print(f"Kontrollerar scenario: {name}...", flush=True)
        analyses[name] = call("perform_actuarial_analysis", {"analysis": "monthly_fta_change",
            "parameters_json": json.dumps({"journal_id": p.scenario_id, **effects})}).payload
    if args.approve_checksum:
        summary = call("approve_premium_month", {"journal_id": p.scenario_id,
                        "reviewed_checksum": args.approve_checksum}).payload
    report = target.with_suffix(".report.json")
    report.write_text(json.dumps({**output, "summary": summary, "analyses": analyses}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    report.with_suffix(".md").write_text(markdown_report(output, summary, analyses), encoding="utf-8")
    print(json.dumps({**output, "summary": summary, "report": str(report)}, ensure_ascii=True, indent=2))
    engine.dispose()


if __name__ == "__main__":
    main()
