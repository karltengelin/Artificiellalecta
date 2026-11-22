"""Jämför novembers stängning med main:s kod och den här checkoutens kod på samma databas (B-052, paket B steg 5).

Novembers stängning körs med den kod som ligger på main 2026-12-01. Utan steg 4:s och steg 5:s tabeller ska
den vara identisk med steg 3, och med steg 4:s men utan steg 5:s tabeller identisk med steg 4: samma
granskningssumma, samma verifikation och samma rader. Skriptet prövar det på en **lokal SQLite-kopia** av
testbeståndet (paket A:s oktoberpremier som betalas i november, journalen öppnad från S-04), inte mot
Lakebase:

    python scripts/simulation/paket_b_steg5/compare_main.py --main <mapp med main:s src/ och tests/>

`--main` är en utpackad kopia av main, t.ex. `git archive main | tar -x -C <mapp>`. Databasen byggs
med main:s kod. Därefter körs granskning och bokning i separata processer: en gång med main:s kod och en gång
med den här checkoutens, på var sin kopia av samma databasfil. Fyra lägen:

- `steg3`: steg 4:s och steg 5:s tabeller borttagna (som Lakebase i dag), B fyller 66 i november och C har
  passerat 66;
- `steg3-ung`: som `steg3` men utan någon som fyllt 66;
- `steg4`: steg 4:s tabeller, inga av steg 5:s; C har passerat 66 (stängningen kan bokas);
- `steg4-66`: som `steg4` med B som fyller 66 i november (stängningen blockeras lika i båda).

Skriver ingenting utanför den tillfälliga mappen och rör ingen delad databas.
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
SCENARIOS = {
    "steg3": {"births": {"B": "19601103", "C": "19580315"}, "drop": "step4"},
    "steg3-ung": {"births": {}, "drop": "step4"},
    "steg4": {"births": {"C": "19580315"}, "drop": "step5"},
    "steg4-66": {"births": {"B": "19601103", "C": "19580315"}, "drop": "step5"},
}
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
    names = set(Base.metadata.tables)
    with engine.begin() as conn:
        drop = [*(STEP5 if set(STEP5) <= names else ()), *(STEP4 if SCENARIOS[scenario]["drop"] == "step4" else ())]
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


# --- jämförelsen --------------------------------------------------------------------------------------


def _summary(result: dict) -> str:
    booked = result.get("booked")
    return (f"granskningssumma {result['review_checksum'][:16]}…, godkänd {result['passed']}, problem "
            f"{len(result['problems'])}" + (f", {len(booked['entries'])} poster, {len(booked['guarantee_parts'])} "
                                           f"garantidelar, {len(booked['cases'])} ärenden" if booked else ", ej bokad"))


def compare(main_root: Path, scenarios: list[str]) -> bool:
    ok = True
    with tempfile.TemporaryDirectory(prefix="b052-") as tmp:
        for scenario in scenarios:
            base = Path(tmp) / f"{scenario}.db"
            _child(main_root, ["--child-build", str(base), "--scenario", scenario])
            results = {}
            for name, root in (("main", main_root), ("branch", REPO_ROOT)):
                copy = Path(tmp) / f"{scenario}-{name}.db"
                shutil.copyfile(base, copy)
                results[name] = _child(root, ["--child-close", str(copy)])
            same = results["main"] == results["branch"]
            ok &= same
            print(f"{scenario}: {'IDENTISKT' if same else 'AVVIKER'}")
            for name, result in results.items():
                print(f"  {name}: {_summary(result)}")
            if not same:
                for key in results["main"]:
                    if results["main"][key] != results["branch"].get(key):
                        print(f"  skiljer sig: {key}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--main", type=Path, help="Utpackad kopia av main (git archive main)")
    parser.add_argument("--scenario", action="append", choices=list(SCENARIOS), help="Läge; standard alla")
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
    if not compare(args.main.resolve(), args.scenario or list(SCENARIOS)):
        raise SystemExit("Stängningen skiljer sig mellan main:s och branchens kod (B-052)")
    print("Samma granskningssumma, verifikation och rader med main:s och branchens kod i alla lägen (B-052).")


if __name__ == "__main__":
    main()
