"""Jämför novembers stängning med main:s kod och den här checkoutens kod på samma databas (B-052, paket B steg 7, Y13).

Novembers stängning körs med den kod som ligger på main. Utan steg 7:s tabeller ska den vara identisk med
main i alla lägen: samma granskningssumma, samma verifikation, samma rader, samma ärenden och samma
blockering. Skriptet prövar det på en **lokal SQLite-kopia** av testbeståndet (paket A:s oktoberpremier som
betalas i november, journalen öppnad från S-04), inte mot Lakebase:

    python scripts/simulation/paket_b_steg7/compare_main.py --main <mapp med main:s src/ och tests/>

`--main` är en utpackad kopia av main, t.ex. `git archive main | tar -x -C <mapp>`. Databasen byggs
med main:s kod, så steg 7:s tabeller finns aldrig i den. Därefter körs granskning och bokning i separata
processer: en gång med main:s kod och en gång med den här checkoutens, på var sin kopia av samma databasfil.
Steg 6:s fem lägen och två nya:

- `steg3`: steg 4:s, 5:s och 6:s tabeller borttagna, B fyller 66 i november och C har passerat 66;
- `steg4`: steg 4:s tabeller, inga av steg 5:s eller 6:s; C har passerat 66;
- `steg5`: steg 5:s tabeller, inga av steg 6:s; B fyller 66 och bolagskontot har en startinsättning, så
  novembers stängning bokar den första månadsrätten;
- `steg5-ung`: som `steg5` men utan någon som fyllt 66 och utan insättning;
- `steg5-66`: som `steg5` med C som passerat 66 utan plan (ärendet `payout_review`);
- `steg6`: alla main:s tabeller (som Lakebase efter steg 6:s migration) och den första månadsrätten;
- `steg6-avliden`: som `steg6` med B registrerad som avliden utan besked – standardstarten blockeras.

Granskningssumman bygger på testbeståndets slumpade id och kan bara jämföras inom samma bygge. Det som inte
beror på id:na – godkänd, kontrollerna, sektionerna, summafälten och antalet rader – skrivs med
`--write-shape` till `main_shape.json` och låses av tests/test_death_reports.py. Skriver i övrigt ingenting
utanför den tillfälliga mappen och rör ingen delad databas.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[3]
SHAPE = HERE.with_name("main_shape.json")
SCENARIOS = {
    "steg3": {"births": {"B": "19601103", "C": "19580315"}, "drop": "step4"},
    "steg4": {"births": {"C": "19580315"}, "drop": "step5"},
    "steg5": {"births": {"B": "19601103"}, "drop": "step6", "capital": "50000.00"},
    "steg5-ung": {"births": {}, "drop": "step6"},
    "steg5-66": {"births": {"B": "19601103", "C": "19580315"}, "drop": "step6", "capital": "50000.00"},
    "steg6": {"births": {"B": "19601103"}, "drop": "step7", "capital": "50000.00"},
    "steg6-avliden": {"births": {"B": "19601103"}, "drop": "step7", "capital": "50000.00", "deceased": ["B"]},
}
#: Steg 7:s tabeller finns inte i main:s modeller; listan gör att en databas byggd med branchens kod också går
STEP7 = ("estate_authorities", "pension_claim_reversals", "death_settlements", "death_reports")
STEP6 = ("payout_receipts", "payout_order_lines", "payout_orders", "payout_files", "payout_accounts", "tax_statuses")
STEP5 = ("pension_claim_fundings", "pension_claims", "payout_amounts")
STEP4 = ("payout_splits", "payout_plans", "payout_requests")
#: Väggklockans tidsstämplar skiljer mellan körningarna och jämförs inte
TIMESTAMPS = ("created_at", "updated_at")


def _child(root: Path, args: list[str]) -> dict:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(root / "src"), str(root)]), "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run([sys.executable, "-B", str(HERE), *args], check=False, env=env, capture_output=True,
                         text=True, encoding="utf-8", cwd=str(root))
    if out.returncode != 0:
        raise SystemExit(f"Barnprocessen ({root}) misslyckades:\n{out.stdout}\n{out.stderr}")
    return json.loads(out.stdout.strip().splitlines()[-1])


# --- barnprocesserna: körs med den kod som PYTHONPATH pekar på ----------------------------------------


def _build(db: str, scenario: str) -> dict:
    """Testbeståndet (samma steg som `tests.test_premium_month_export.chain`) med journalen öppnad per 2026-10-31."""
    from datetime import date
    from decimal import Decimal
    from types import SimpleNamespace

    from sqlalchemy import create_engine, select

    from models import Base, BaseAmount, Employer, InsuredPerson, ValuationBasis
    from services import parameters
    from services import valuation_bases as vb
    from services.db import session_factory_for
    from services.operations import common
    from tests import test_premium_month_export as t

    state = SimpleNamespace(today=t.START)
    common.today = lambda: state.today
    engine = create_engine(f"sqlite:///{db}")
    Base.metadata.create_all(engine)
    factory = session_factory_for(engine)
    with factory() as s:
        parameters.add_missing_defaults(s)
        vb.add_missing_defaults(s)
        s.add_all([BaseAmount(year=2023, income_base_amount_sek=Decimal(74300)),
                   BaseAmount(year=2026, income_base_amount_sek=Decimal(83400))])
        employer = Employer(org_number=t.EMPLOYER, name="Testbolaget AB", affiliation_date=date(2010, 1, 1))
        s.add(employer)
        s.flush()
        for number, pnr in enumerate(t.PERSONS.values(), start=1):
            t._person(s, employer, pnr, number)
        s.commit()
    data = SimpleNamespace(engine=engine, factory=factory)
    t.salary_file(data, [t.row(key) for key in t.PERSONS], "LON-2026-10")
    [first] = t.invoice(data)
    t.salary_file(data, [t.row("C", "50000", "correction", 1)], "LON-2026-10-R1")
    _, rebill = t.invoice(data)
    t.bank(data, state, "BANK-11-10", [t.event("E1", "4000.00", first.ocr_reference, "2026-11-10")])
    t.bank(data, state, "BANK-11-16", [t.event("E2", "4758.13", first.ocr_reference, "2026-11-16")])
    t.salary_file(data, [t.row("D", "50000", "correction", 1)], "LON-2026-10-R2")
    [additional] = t.invoice(data)
    t.bank(data, state, "BANK-11-20", [t.event("E3", "2000.00", rebill.ocr_reference, "2026-11-20"),
                                       t.event("E4", "300.00", additional.ocr_reference, "2026-11-20"),
                                       t.event("E5", "100.00", "9999999999", "2026-11-20")])
    t.bank(data, state, "BANK-12-02", [t.event("E6", "250.00", rebill.ocr_reference, "2026-12-02")])
    with factory() as s:
        for key, born in SCENARIOS[scenario]["births"].items():
            person = s.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == t.PERSONS[key]))
            person.personal_id_number = born + t.PERSONS[key][-4:]
        for key in SCENARIOS[scenario].get("deceased", []):  # avliden utan besked, som före steg 7
            s.flush()
            born = SCENARIOS[scenario]["births"].get(key, t.PERSONS[key][:8])
            person = s.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == born + t.PERSONS[key][-4:]))
            person.status = "deceased"
        s.commit()
    review = t.run(data, "preview_ledger_opening", {}).payload
    t.run(data, "open_capital_ledger", {"reviewed_checksum": review["review_checksum"]})
    with factory() as s:
        base = s.scalar(select(ValuationBasis).where(ValuationBasis.code == "AVK-SIM-2026-01")).assumptions
    months = [*vb.normalize("return_series", base)["months"], {"month": "2026-11-01", "rate": "0.002"}]
    t.run(data, "propose_valuation_basis", {"code": "AVK-SIM-2026-02", "title": "Syntetisk avkastning",
                                            "assumptions": vb.normalize("return_series", {**base, "months": months}),
                                            "source_refs": "prov", "supersedes_code": "AVK-SIM-2026-01"})
    t.run(data, "adopt_valuation_basis", {"code": "AVK-SIM-2026-02", "valid_from": "2026-11-01", "decision_ref": "prov"})
    if "capital" in SCENARIOS[scenario]:  # PB11: den första stängningen med en rätt kräver en insättning
        t.run(data, "register_company_capital", {"amount_sek": SCENARIOS[scenario]["capital"],
                                                 "decided_on": "2026-11-20", "document_ref": "Ägarbeslut (prov)"})
    names = set(Base.metadata.tables)
    level = SCENARIOS[scenario]["drop"]
    with engine.begin() as conn:
        drop = [*STEP7, *(STEP6 if level != "step7" else ()), *(STEP5 if level in ("step5", "step4") else ()),
                *(STEP4 if level == "step4" else ())]
        drop = [table for table in drop if table in names]
        for table in drop:
            if table in names:
                conn.exec_driver_sql(f"DROP TABLE {table}")
        if SCENARIOS[scenario]["drop"] == "step4":  # som Lakebase efter steg 3: ingen plankoppling
            conn.exec_driver_sql("DROP INDEX IF EXISTS ix_ledger_guarantee_parts_plan")
    engine.dispose()
    return {"built": db, "dropped": drop}


def _close(db: str) -> dict:
    """Granskar och, om det går, bokar november; svarar med summor och rader att jämföra."""
    from datetime import date

    from sqlalchemy import create_engine, inspect, select

    from models import (
        Case,
        LedgerBatch,
        LedgerCapitalEntry,
        LedgerControl,
        LedgerGuaranteePart,
    )
    from services import month_close as mc
    from services import valuation_bases as vb
    from services.db import session_factory_for

    engine = create_engine(f"sqlite:///{db}")
    factory = session_factory_for(engine)
    today = date(2026, 12, 1)
    with factory() as s:
        plan = mc.plan_month(s, date(2026, 11, 1), today)
        out = {"tables": sorted(inspect(s.connection()).get_table_names()), "review_checksum": plan.checksum,
               "status": plan.status, "passed": plan.passed, "problems": plan.problems,
               "controls": [c.as_dict() for c in plan.controls], "content": plan.content}
    if plan.passed:
        with factory() as s:
            batch, _ = mc.apply_month(s, date(2026, 11, 1), "karl", plan.checksum, today)
            s.commit()
        with factory() as s:
            batch = s.get(LedgerBatch, batch.id)

            def rows(model, *order):
                return [{k: str(v) for k, v in r.__dict__.items() if not k.startswith("_") and k not in TIMESTAMPS}
                        for r in s.scalars(select(model).where(model.batch_id == batch.id).order_by(*order))]
            out["booked"] = {
                "batch_id": str(batch.id), "checksum": batch.checksum, "content_checksum": vb.checksum(batch.content),
                "entries": rows(LedgerCapitalEntry, LedgerCapitalEntry.id),
                "guarantee_parts": rows(LedgerGuaranteePart, LedgerGuaranteePart.id),
                "controls": rows(LedgerControl, LedgerControl.id),
                "cases": [{"id": str(c.id), "case_number": c.case_number, "case_type": c.case_type,
                           "details": c.details} for c in s.scalars(select(Case).order_by(Case.case_number))]}
    engine.dispose()
    return out


def shape(result: dict) -> dict:
    """Det i stängningen som inte beror på testbeståndets slumpade id: godkänd, kontroller, sektioner och antal.

    Granskningssumman bygger på personernas och delarnas id, som är nya för varje bygge. Formen låses därför i
    `main_shape.json` (räknad med main:s kod) och prövas mot branchens kod i tests/test_death_reports.py.
    """
    content = result["content"]
    booked = result.get("booked")
    return {"passed": result["passed"], "problems": len(result["problems"]),
            "controls": [c["step"] for c in result["controls"]], "sections": sorted(content),
            "totals": sorted(content["totals"]), "pension": sorted(content.get("pension", {})),
            "booked": [len(booked[k]) for k in ("entries", "guarantee_parts", "controls", "cases")] if booked else None}


# --- jämförelsen --------------------------------------------------------------------------------------


def _summary(result: dict) -> str:
    booked = result.get("booked")
    return (f"granskningssumma {result['review_checksum'][:16]}…, godkänd {result['passed']}, problem "
            f"{len(result['problems'])}" + (f", {len(booked['entries'])} poster, {len(booked['guarantee_parts'])} "
                                           f"garantidelar, {len(booked['cases'])} ärenden" if booked else ", ej bokad"))


def compare(main_root: Path, scenarios: list[str], shapes: dict | None = None) -> bool:
    ok = True
    with tempfile.TemporaryDirectory(prefix="b052-steg7-") as tmp:
        for scenario in scenarios:
            base = Path(tmp) / f"{scenario}.db"
            _child(main_root, ["--child-build", str(base), "--scenario", scenario])
            results = {}
            for name, root in (("main", main_root), ("branch", REPO_ROOT)):
                copy = Path(tmp) / f"{scenario}-{name}.db"
                shutil.copyfile(base, copy)
                results[name] = _child(root, ["--child-close", str(copy)])
            same = results["main"] == results["branch"]
            if shapes is not None:
                shapes[scenario] = shape(results["main"])
            ok &= same
            print(f"{scenario}: {'IDENTISKT' if same else 'AVVIKER'}")
            for name, result in results.items():
                print(f"  {name}: {_summary(result)}")
            print(f"  granskningssumma {results['main']['review_checksum']}")
            if not same:
                for key in results["main"]:
                    if results["main"][key] != results["branch"].get(key):
                        print(f"  skiljer sig: {key}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--main", type=Path, help="Utpackad kopia av main (git archive main)")
    parser.add_argument("--scenario", action="append", choices=list(SCENARIOS), help="Läge; standard alla")
    parser.add_argument("--write-shape", action="store_true",
                        help="Skriv main:s form per läge till main_shape.json (regressionstestets facit)")
    parser.add_argument("--child-build", help=argparse.SUPPRESS)
    parser.add_argument("--child-close", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child_build:
        print(json.dumps(_build(args.child_build, args.scenario[0]), default=str))
        return
    if args.child_close:
        print(json.dumps(_close(args.child_close), default=str, sort_keys=True))
        return
    if args.main is None or not (args.main / "src").is_dir() or not (args.main / "tests").is_dir():
        raise SystemExit("Ange --main med en utpackad kopia av main (git archive main | tar -x -C <mapp>)")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    shapes: dict = {}
    if not compare(args.main.resolve(), args.scenario or list(SCENARIOS), shapes):
        raise SystemExit("Stängningen skiljer sig mellan main:s och branchens kod (B-052)")
    if args.write_shape:
        SHAPE.write_text(json.dumps(shapes, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Main:s form skriven till {SHAPE.relative_to(REPO_ROOT)}")
    print("Samma granskningssumma, verifikation och rader med main:s och branchens kod i alla lägen (B-052).")


if __name__ == "__main__":
    main()
