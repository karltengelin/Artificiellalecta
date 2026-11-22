"""Kör en isolerad premiemånad, ett atomärt kalendersteg åt gången."""

import json
import subprocess
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BankEvent, OperationEventRecord, SalaryFile
from services import Actor, OperationContext, ProductRuleCatalog, ServiceLayer
from services.db import session_factory_for
from services.operations.common import business_day
from services.operations.payments import bank_file_checksum
from simulation import counterparties as cp
from simulation.premium_opening import (
    DB,
    EMPLOYER,
    OPENING,
    PERIOD,
    copy_opening,
    digest,
    local_engine,
)
from simulation.premium_verification import (
    FACIT,
    FACIT_VERSION,
    business_hash,
    observation,
    verify,
)
from utils.checksums import canonical_hash

VERSION = "premium-calendar-v1"
ISSUE = date(2026, 11, 25)
CUTOFF = date(2026, 11, 30)
END = date(2026, 12, 29)
SCENARIOS = {"full": "on_time", "partial": "partial", "duplicate": "on_time",
             "twice": "twice", "unknown": "wrong_reference"}
SYSTEM = Actor.system("system:premium_simulation")
REPO = Path(__file__).resolve().parents[2]


def schedule(scenario):
    steps = [(ISSUE, "salary"), (ISSUE, "review"), (ISSUE, "invoice")]
    day = ISSUE + timedelta(days=1)
    while day <= END:
        if day == CUTOFF:
            steps.append((day, "bank"))
            if scenario == "duplicate":
                steps.append((day, "redelivery"))
        steps.append((day, "monitor"))
        if day in (CUTOFF, END):
            steps.append((day, "report"))
        day += timedelta(days=1)
    return [(d.isoformat(), name) for d, name in steps]


def now():
    return datetime.now(UTC).isoformat()


def code_revision():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def source_hash():
    """Bind även lokala ändringar i verksamhetskod och produktregler till körningen."""
    paths = [REPO / "scripts/simulation/premium_calendar.py"]
    for directory in ("simulation", "services", "models", "skills/calculation", "utils"):
        paths.extend((REPO / "src" / directory).rglob("*.py"))
    paths.extend((REPO / "01_domän/produktregler").glob("*.md"))
    paths.append(REPO / "src/services/access_register.yaml")
    return canonical_hash({p.relative_to(REPO).as_posix(): digest(p) for p in paths})


def start(root, scenario):
    if scenario not in SCENARIOS:
        raise ValueError("Okänt betalningsscenario")
    root = Path(root).resolve()
    root.mkdir(exist_ok=True, parents=True)
    ident = uuid4().hex
    with TemporaryDirectory(dir=root) as tmp:
        stage = Path(tmp) / ident
        stage.mkdir()
        opening = copy_opening(root, stage / DB)
        steps = schedule(scenario)
        manifest = {"opening": opening, "scenario": scenario, "version": VERSION, "seed": 1, "steps": steps,
                    "payment": {"kind": SCENARIOS[scenario], "share": "0.594077", "days_after_invoice": 5},
                    "simulator": cp.VERSION, "facit": FACIT_VERSION, "facit_hash": canonical_hash(FACIT),
                    "code": code_revision(), "source_hash": source_hash(),
                    "rule_package": ProductRuleCatalog(today=ISSUE).package,
                    "model": None, "instructions": None}
        state = {"id": ident, "manifest": manifest, "manifest_hash": canonical_hash(manifest),
                 "cursor": 0, "status": "ready", "day": "2026-11-01", "journal": [], "files": {},
                 "reports": {}, "active_seconds": 0.0, "wait_seconds": 0.0, "started_at": now()}
        engine = local_engine(stage / DB)
        try:
            with engine.begin() as conn:
                conn.exec_driver_sql("CREATE TABLE simulation_run (id TEXT PRIMARY KEY, state TEXT NOT NULL)")
                conn.exec_driver_sql("INSERT INTO simulation_run VALUES (?, ?)", (ident, json.dumps(state)))
        finally:
            engine.dispose()
        stage.rename(root / ident)
    return ident


@contextmanager
def run_connection(root, ident, *, write=False):
    root = Path(root).resolve()
    if UUID(ident).hex != ident:
        raise ValueError("Ogiltigt kör-ID")
    path = root / ident / DB
    if not path.is_file() or path.resolve() != path:
        raise ValueError("Körningens lokala SQLite-fil saknas")
    engine = local_engine(path)
    try:
        with engine.connect() as conn:
            # Ett skrivanspråk för hela steget, även under domänanropet och dess audit.
            if write:
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            state = json.loads(conn.exec_driver_sql("SELECT state FROM simulation_run WHERE id=?", (ident,)).scalar_one())
            if state["id"] != ident or canonical_hash(state["manifest"]) != state["manifest_hash"]:
                raise ValueError("Körningens identitet eller manifest har ändrats")
            yield conn, state
            if write:
                conn.exec_driver_sql("UPDATE simulation_run SET state=? WHERE id=?",
                                     (json.dumps(state, ensure_ascii=False, default=str), ident))
                conn.commit()
    finally:
        engine.dispose()


def status(root, ident):
    with run_connection(root, ident) as (_, state):
        return state


def review(root, ident, actor):
    """Läs om A:s granskning vid ändrat underlag, med verklig operatör i läsloggen."""
    if actor.type != "human":
        raise ValueError("Filgranskning kräver handläggare")
    with run_connection(root, ident, write=True) as (conn, state):
        if state["status"] == "waiting_review":
            day = date.fromisoformat(state["day"])
            service = ServiceLayer(session_factory=session_factory_for(conn), rules=ProductRuleCatalog(today=day))
            with business_day(day):
                view = service.execute("get_salary_file", OperationContext(actor=actor, run_id=ident),
                                       {"employer_org_number": EMPLOYER,
                                        "file_reference": state["review"]["file_reference"]}).output
            state["review"] = view.model_dump(mode="json")
        return state


def _check_checkpoint(conn, state):
    """Vid fortsatt körning ska sparat beslut och bankkvitton ha sina domänspår."""
    with Session(conn) as session:
        if "review" in state:
            file = session.scalars(select(SalaryFile).where(
                SalaryFile.file_reference == state["review"]["file_reference"])).one()
            decision = state.get("decision")
            expected = decision["receipt"]["status"] if decision else "received"
            if file.checksum != state["files"]["salary"]["payload"]["checksum"] or file.status != expected:
                raise ValueError("Lönefilens domänkvitto kräver manuell avstämning")
            if decision and (file.decided_by != decision["actor"] or
                             (expected == "approved" and file.review_digest != decision["digest"])):
                raise ValueError("Filbeslutet kräver manuell avstämning")
        bank_entries = [e for e in state["journal"] if e["step"] in ("bank", "redelivery")]
        for entry in bank_entries:
            event = session.scalars(select(OperationEventRecord).where(
                OperationEventRecord.run_id == entry["key"], OperationEventRecord.operation == "import_bank_file",
                OperationEventRecord.outcome == "executed")).one_or_none()
            if event is None:
                raise ValueError("Banksteget saknar domänkvitto och kräver manuell avstämning")
            payload = state["files"][entry["step"]]["payload"]
            for expected in payload["events"]:
                received = session.scalars(select(BankEvent).where(
                    BankEvent.source_system == payload["source_system"],
                    BankEvent.event_id == expected["event_id"])).one_or_none()
                if (received is None or received.amount_sek != Decimal(expected["amount_sek"])
                        or str(received.received_date) != expected["received_date"]
                        or received.reference != expected["reference"]
                        or received.payer_org_number != expected["payer_org_number"]):
                    raise ValueError("Bankhändelsen kräver manuell avstämning")


def _freeze(state, key, file):
    state["files"][key] = {"payload": file.payload, "label": file.label, "facit": file.facit}


def _report(conn, state, call, day, rejected=False):
    balances = call("get_receivables", {})
    with Session(conn) as session:
        observed = observation(session, balances)
    # JSON-formatet är också formatet efter omstart.
    observed = json.loads(json.dumps(observed, default=str))
    scenario = state["manifest"]["scenario"]
    failures = verify(observed, scenario, december=day == END, rejected=rejected)
    if not rejected:
        files = state["files"]
        salary_check = files["salary"]["facit"]["expected"]
        summary = state["review"]["summary"]
        if any(summary[k] != v for k, v in salary_check.items()):
            failures.append("Löneintaget avviker från arbetsgivarens filfacit")
        if Decimal(files["bank"]["facit"]["total_sek"]) != Decimal(balances["bank_total_sek"]):
            failures.append("Bankutfallet avviker från bankens filfacit")
    return {"as_of": day.isoformat(), "period": "2026-11", "hash": business_hash(observed),
            "run": state["id"], "manifest_hash": state["manifest_hash"],
            "file_checksums": {key: item["payload"]["checksum"] for key, item in state["files"].items()},
            "decision": state["decision"],
            "reviews": int("decision" in state), "rejections": int(state["decision"]["verdict"] == "reject"),
            "observed": observed, "failures": failures, "model_calls": 0, "model_cost_usd": 0,
            "redeliveries": sum(r["already_received"] for r in state.get("bank_receipts", [])),
            "active_seconds": state["active_seconds"], "wait_seconds": state["wait_seconds"],
            "unverified": ["agentkvalitet", "kapital", "garanti", "FTA", "portfölj", "huvudbok"]}


def _execute(conn, state, day, step, decision):
    manifest = state["manifest"]
    service = ServiceLayer(session_factory=session_factory_for(conn), rules=ProductRuleCatalog(today=day))
    key = f"{state['id']}/{state['cursor']}"
    entry = {"step": step, "day": str(day), "key": key, "operations": [], "at": now()}

    def call(name, data, actor=SYSTEM, reason=None):
        ctx = OperationContext(actor=actor, run_id=key, reason=reason or f"Premiesimulering {step} {day}")
        result = service.execute(name, ctx, data).output.model_dump(mode="json")
        entry["operations"].append({"name": name, "actor": actor.id, "receipt": canonical_hash(result)})
        return result

    seed = manifest["seed"]
    employer_period = {"employer_org_number": EMPLOYER, "period_month": PERIOD.isoformat()}
    if step == "salary":
        with Session(conn) as session:
            file = cp.salary_file(session, EMPLOYER, PERIOD, received_date=day, seed=seed)
        _freeze(state, "salary", file)
        state["review"] = call("import_salary_file", file.payload)
        state["status"] = "waiting_review"
        state["waiting_since"] = now()
    elif step == "review":
        actor, verdict, reviewed, note = decision
        if actor.type != "human" or not actor.id.strip() or verdict not in ("approve", "reject") or not note.strip():
            raise ValueError("Ett uttryckligt handläggarbeslut med motivering krävs")
        ref = {"employer_org_number": EMPLOYER, "file_reference": state["review"]["file_reference"]}
        actual = call("get_salary_file", ref, actor)
        if (actual["status"] != "received" or reviewed != actual["review_digest"]
                or reviewed != state["review"]["review_digest"]):
            raise ValueError("Granskningsunderlaget har ändrats. Granska den aktuella filen.")
        if verdict == "approve":
            receipt = call("approve_salary_file", {**ref, "expected_digest": reviewed}, actor, note)
            state["status"] = "ready"
        else:
            receipt = call("reject_salary_file", {**ref, "decision_note": note}, actor, note)
            state["status"] = "rejected"
        state["decision"] = {"actor": actor.id, "verdict": verdict, "digest": reviewed, "note": note, "receipt": receipt}
        state["wait_seconds"] += (datetime.now(UTC) - datetime.fromisoformat(state.pop("waiting_since"))).total_seconds()
        if verdict == "reject":
            state["reports"]["decision"] = _report(conn, state, call, day, rejected=True)
    elif step == "invoice":
        result = call("create_invoice", employer_period)
        if len(result["invoices"]) != 1 or result["skipped"]:
            raise ValueError("Faktureringen avvek från det granskade underlaget")
        state["invoice"] = result["invoices"][0]
    elif step in ("bank", "redelivery"):
        if step == "bank":
            payment = manifest["payment"]
            behaviour = cp.PaymentBehaviour(kind=payment["kind"], share=Decimal(payment["share"]),
                                            days_after_invoice=payment["days_after_invoice"])
            with Session(conn) as session:
                file = cp.bank_file(session, PERIOD, {EMPLOYER: behaviour}, as_of=day, seed=seed)
            _freeze(state, step, file)
            payload = file.payload
        else:
            original = state["files"]["bank"]
            payload = {**original["payload"], "file_reference": original["payload"]["file_reference"] + "-R"}
            payload["checksum"] = bank_file_checksum(payload["source_system"], payload["file_reference"], payload["events"])
            state["files"][step] = {**original, "payload": payload}
        receipt = call("import_bank_file", payload)
        state.setdefault("bank_receipts", []).append(receipt)
        if step == "redelivery" and (receipt["already_received"] != 1 or receipt["new_events"] or
                                      Decimal(receipt["allocated_sek"]) or Decimal(receipt["unallocated_sek"])):
            raise ValueError("Återleveransen gav en ny bankeffekt")
    elif step == "monitor":
        entry["actions"] = call("check_overdue_invoices", {})["actions"]
    elif step == "report":
        report = _report(conn, state, call, day)
        state["reports"][str(day)] = report
        if report["failures"]:
            state["status"] = "failed"
        elif day == END:
            state["status"] = "completed"
    else:
        raise ValueError("Okänt kalendersteg")
    state["journal"].append(entry)


def advance(root, ident, *, decision=None, revision=None, one=False):
    """Varje steg kvitteras tillsammans med affärsskrivningen eller rullas helt tillbaka."""
    checked = False
    while True:
        with run_connection(root, ident, write=True) as (conn, state):
            manifest = state["manifest"]
            if not checked:
                if (manifest["version"] != VERSION or manifest["code"] != code_revision()
                        or manifest["source_hash"] != source_hash()
                        or manifest["facit_hash"] != canonical_hash(FACIT)
                        or digest(Path(root) / OPENING / DB) != manifest["opening"]["sha256"]):
                    raise ValueError("Startbild, kod eller facit har ändrats sedan körstart")
                _check_checkpoint(conn, state)
                checked = True
            if decision is not None and (state["status"] != "waiting_review" or state["cursor"] != revision):
                raise ValueError("Beslutet gäller en äldre körrevision")
            if state["status"] in ("completed", "failed", "rejected") or (
                state["status"] == "waiting_review" and decision is None
            ):
                return state
            day_text, step = manifest["steps"][state["cursor"]]
            day = date.fromisoformat(day_text)
            started = perf_counter()
            with business_day(day):
                _execute(conn, state, day, step, decision)
            state["active_seconds"] += perf_counter() - started
            state["cursor"] += 1
            state["day"] = day_text
            decision = None
        if one:
            return state
