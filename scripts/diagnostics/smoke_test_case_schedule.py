"""Röktest av dagligt urval, stoppvägar och uppföljning mot riktig modell (F5-7, B-043).

Skriptet kör arbetarens eget varv (`CaseWorkspace.tick`) som den schemalagda `--once` gör,
med den levererade ärendepolicyn. Det agerar handläggare, märkt `rooktest`, och avgör förslagen
som handläggaren gör i `/godkannanden`. Uppföljningen efter beslutet sker i nästa varv.

| `--db`     | Databas                                                    | Agentens roll |
|------------|------------------------------------------------------------|---------------|
| `demo`     | Demobeståndet i SQLite i minnet                            | simulerad     |
| `svc_test` | Demobeståndet i ett eget schema, tas bort efteråt          | begränsad testroll, när den finns |
| `lakebase` | Beståndet; ärenden, förslag och registreringar finns kvar  | den riktiga rollen |

Delar:

1. **Urval** med den levererade policyn: ett ärende från arbetsgivaren väljs, ett manuellt
   underlag för samma person och månad väljs inte. Förslaget godkänns och nästa varv stänger
   ärendet. Med `--avslag` (alltid i demo och `svc_test`) väljs även en rättelse, som avslås,
   går till handläggaren och stängs av handläggaren.
2. **Stoppvägar**, bara demo och `svc_test`, utan modellanrop: schemataket, dagens försök och
   policybyte medan uppdraget står i kö. Policyn ändras i en tillfällig kopia.
3. **Automatisk slutbehandling**, bara demo och `svc_test`, med tillfällig `review_required: false`:
   en ny arbetsgivarrapport stängs av `case_automation`, en rättelse stannar för granskning.

Mot Lakebase krävs `--pnr`, `--arbetsgivare`, `--manad` och `--lon` för en märkt
verifieringsperson. Utan `--run` görs bara en läsande förkontroll: inga öppna löneärenden och
inga aktiva uppdrag får finnas, eftersom urvalet annars kan ta andra ärenden. `--run` skriver
i beståndet och görs efter backup och operatörens OK (AGENTS.md §4.5). Urvalet gäller från
07.00 Europe/Stockholm; före det stoppar skriptet.

Användning (från repo-roten, i .venv):
    python scripts/diagnostics/smoke_test_case_schedule.py                 # plan, ingen kostnad
    python scripts/diagnostics/smoke_test_case_schedule.py --run           # demo
    python scripts/diagnostics/smoke_test_case_schedule.py --run --db svc_test
    python scripts/diagnostics/smoke_test_case_schedule.py --db lakebase --pnr 199204171236 --arbetsgivare 5552871575 --manad 2026-10-01 --lon 41500
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from smoke_test_case_flow import (
    DEMO_SUBJECT,
    REPO_ROOT,
    STANDARD_MODEL,
    TEAM,
    build,
    case_details,
    compare_counts,
    current_report,
    describe,
    get_case_view,
    journal_tools,
    lakebase_database,
    previous_month,
    row_counts,
)

from testing.smoke import Report, demo_database, svc_test_database

OPERATOR_ID = "rooktest"
#: Demobeståndets Bertil Berg; premier finns till och med 2026-09 (del 3, ny rapport)
SECOND_SUBJECT = ("197203034561", "5560000001", Decimal(72000))


class Run:
    """Gemensamt läge för ett röktest: databas, adapter, märkning och rapport."""

    def __init__(self, db, trusted, workspace, subject, *, stamp, journal_dir, report, now):
        from services import Actor

        self.db, self.trusted, self.workspace, self.subject = db, trusted, workspace, subject
        self.stamp, self.journal_dir, self.report, self.now = stamp, journal_dir, report, now
        self.human = Actor.human(OPERATOR_ID)
        self.own: set[str] = set()

    def ctx(self, number=None, reason=None):
        from services import OperationContext

        return OperationContext(actor=self.human, case_id=number, reason=reason)

    def create(self, label, month, salary, source="employer", person=None):
        person = person or self.subject
        subject = SimpleNamespace(pnr=person.pnr, employer=person.employer, month=month)
        details = {**case_details(self.db.factory, subject, salary), "source": source}
        reference = f"ROOKTEST-F5-7-{self.stamp}-{label}"
        number = self.trusted.execute("create_case", self.ctx(reason="Märkt röktest av dagligt urval (F5-7)"), {
            "case_type": "salary_report", "personal_id_number": subject.pnr,
            "employer_org_number": subject.employer, "period_month": month.isoformat(),
            "received_date": date.today().isoformat(), "source_reference": reference, "details": details,
        }).output.case_number
        self.own.add(number)
        print(f"  Ärende {label} {number}: {describe(details)}, källa {source}")
        return number

    def works(self, number):
        return self.workspace.view(number, self.human)["works"]

    def daily(self, number):
        return [w for w in self.works(number) if w["submitted_by"] == "daily_worker"]

    def tick(self):
        processed = self.workspace.tick(now=self.now)
        print(f"  Varv: {processed} köposter behandlade")
        return processed

    def follow_up(self):
        return {n: s for n, s in self.workspace.follow_up().items() if n in self.own}

    def record_run(self, work):
        usage = (work["result"] or {}).get("usage", {})
        self.report.cost += usage.get("cost_usd", 0.0)
        run = (work["result"] or {}).get("run", {})
        print(f"  Körning {work['run_id']}: {run.get('status')}, {usage.get('tool_calls')} verktygsanrop, "
              f"{usage.get('cost_usd', 0):.4f} USD")
        print(f"  Sammanfattning: {run.get('summary', '')[:400]}")

    def pending(self, number):
        return [p for p in self.trusted.approvals.list("pending") if p.case_id == number]

    def prepared(self, number, label):
        """Agentens förberedelse av ett ärende som schemat valt: läst ärende och ett exakt förslag."""
        from services.case_review import expected_salary
        from services.operations.salary import SalaryReportInput

        work = self.daily(number)[-1]
        self.record_run(work)
        self.report.check("verksamhet", f"{label}: uppdraget väntar på godkännande",
                          work["status"] == "waiting_approval", work["status"])
        tools, journal = journal_tools(self.journal_dir / f"{work['run_id']}.jsonl")
        self.report.check("verksamhet", f"{label}: agenten läste ärendet", "get_case" in tools, ", ".join(tools))
        self.report.check("verksamhet", f"{label}: journalen saknar personnummer",
                          bool(journal) and self.subject.pnr not in journal)
        pending = self.pending(number)
        ok = self.report.check("facit", f"{label}: ett förslag som motsvarar ärendet exakt", len(pending) == 1
                               and SalaryReportInput.model_validate(pending[0].input)
                               == expected_salary(get_case_view(self.trusted, number)), str(len(pending)))
        return work, (pending[0] if ok else None)

    def close(self, number, outcome, note):
        self.trusted.execute("close_case", self.ctx(number, f"Röktest F5-7: {note}"),
                             {"case_number": number, "outcome": outcome, "closing_note": note})


def write_policy(path: Path, *, schedule=None, **rule) -> Path:
    import yaml

    from agents.case_policy import DEFAULT_POLICY

    data = yaml.safe_load(DEFAULT_POLICY.read_text(encoding="utf-8"))
    salary = data["case_types"]["salary_report"]
    salary.update(rule)
    salary["schedule"].update(schedule or {})
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def selection(run: Run, *, month, salary, reject: bool) -> int:
    """Del 1 med den levererade policyn. Returnerar antal registrerade löneunderlag."""
    print("\n== Del 1: urval med levererad policy")
    first = run.create("A", month, salary)
    manual = run.create("M", month, salary, source="manual")
    before = current_report(run.db.factory, run.subject.pnr, run.subject.employer, month)
    run.tick()
    run.report.check("verksamhet", "A valdes av schemat", len(run.daily(first)) == 1)
    run.report.check("verksamhet", "manuellt underlag valdes inte", not run.works(manual))
    work, proposal = run.prepared(first, "A")
    after = current_report(run.db.factory, run.subject.pnr, run.subject.employer, month)
    run.report.check("verksamhet", "ingen registrering före beslutet", (before and before.id) == (after and after.id))
    run.report.check("verksamhet", "uppföljningen visar A som väntande",
                     run.follow_up() == {first: "waiting_approval"}, str(run.follow_up()))
    registered = 0
    if proposal:
        run.trusted.approve(proposal.id, run.ctx(first), "Röktest F5-7: underlaget stämmer med ärendet")
        run.tick()
        case = get_case_view(run.trusted, first)
        run.report.check("verksamhet", "nästa varv stänger A som godkänt",
                         (case.status, case.outcome, case.closed_by) == ("closed", "approved", "case_worker"),
                         f"{case.status}, {case.outcome}, {case.closed_by}")
        registered = 1
    run.report.check("verksamhet", "ett nytt varv väljer inget mer",
                     run.tick() == 0 and len(run.daily(first)) == 1 and not run.works(manual))
    if reject:
        corrected = run.create("R", month, salary + 500)
        run.tick()
        run.report.check("verksamhet", "rättelsen R valdes av schemat", len(run.daily(corrected)) == 1)
        work, proposal = run.prepared(corrected, "R")
        if proposal:
            run.trusted.reject(proposal.id, run.ctx(corrected), "Röktest F5-7: avslås för att pröva uppföljningen")
            run.tick()
            work = run.daily(corrected)[-1]
            run.report.check("verksamhet", "R går till handläggaren efter avslaget", work["status"] == "needs_human",
                             work["status"])
            run.report.check("verksamhet", "uppföljningen visar R", run.follow_up().get(corrected) == "needs_human",
                             str(run.follow_up()))
        run.close(corrected, "rejected", "Avslaget i röktestet; inget underlag registrerat.")
        run.report.check("verksamhet", "stängt ärende lämnar uppföljningen", corrected not in run.follow_up())
    run.close(manual, "no_action", "Manuellt underlag i röktestet; handläggs inte här.")
    return registered


def stops(run: Run, *, month, salary, policy_dir: Path) -> None:
    """Del 2 utan modellanrop: schemataket, dagens försök och policybyte."""
    from sqlalchemy import func, select

    from agents.case_workspace import DAILY_PREFIX
    from models import Case, CaseWork, CaseWorkDay

    print("\n== Del 2: stoppvägar (tillfällig policy, inga modellanrop)")
    first = run.create("T1", month, salary)
    second = run.create("T2", month, salary)
    local = run.now.astimezone(ZoneInfo("Europe/Stockholm"))
    with run.db.factory() as session:
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        selected = session.scalar(select(func.count()).select_from(CaseWork).join(
            Case, Case.case_number == CaseWork.case_number).where(
            CaseWork.submission_key.startswith(DAILY_PREFIX), CaseWork.created_at >= midnight))
    run.workspace.policy_path = write_policy(policy_dir / "tak.yaml", schedule={"max_cases": selected + 1})
    added = run.workspace.enqueue_daily(now=run.now)
    queued = [w for n in (first, second) for w in run.daily(n)]
    run.report.check("verksamhet", "schemataket släpper bara ett ärende till", added == 1 and len(queued) == 1,
                     f"{added} valda")
    if queued:
        run.workspace.action(queued[0]["case_number"], queued[0]["id"], "takeover", actor=run.human,
                             revision=queued[0]["revision"])
    run.report.check("verksamhet", "taket är nått även när uppdraget återtagits",
                     run.workspace.enqueue_daily(now=run.now) == 0)

    with run.db.factory() as session:
        day = session.get(CaseWorkDay, f"{local.date().isoformat()}:salary_report")
        attempts = day.attempts if day else 0
    run.workspace.policy_path = write_policy(policy_dir / "forsok.yaml", max_jobs_per_day=max(attempts, 1))
    ident = run.workspace.submit(second, "Undersök underlaget", actor=run.human, key=f"rooktest-{run.stamp}-budget")
    stopped = not run.workspace.process(ident, now=run.now)
    work = next(w for w in run.works(second) if w["id"] == ident)
    run.report.check("verksamhet", "dagens försök stoppar handläggarens uppdrag före modellanrop",
                     stopped and work["status"] == "needs_human" and not work["result"].get("usage"), work["status"])

    run.workspace.policy_path = write_policy(policy_dir / "fore.yaml")
    ident = run.workspace.submit(second, "Undersök underlaget", actor=run.human, key=f"rooktest-{run.stamp}-policy")
    run.workspace.policy_path = write_policy(policy_dir / "efter.yaml", schedule={"max_cases": 4})
    stopped = not run.workspace.process(ident, now=run.now)
    work = next(w for w in run.works(second) if w["id"] == ident)
    run.report.check("verksamhet", "policybyte stoppar köat uppdrag före modellanrop",
                     stopped and work["status"] == "needs_human" and not work["result"].get("usage"), work["status"])
    for number in (first, second):
        run.close(number, "no_action", "Stoppvägar i röktestet.")


def automatic(run: Run, *, person, new_month, corrected_month, salary, policy_dir: Path) -> int:
    """Del 3: automatisk slutbehandling av ny arbetsgivarrapport; rättelsen stannar för granskning.

    Den nya rapporten gäller en annan person och en månad utan fakturerad premie: en lön som
    avviker från en redan fakturerad premie är ett avvikelsefall som agenten ska lämna till handläggare.
    """
    print("\n== Del 3: automatisk slutbehandling (tillfällig review_required: false)")
    run.workspace.policy_path = write_policy(policy_dir / "automatik.yaml", review_required=False,
                                             schedule={"max_cases": 20})
    fresh = run.create("N", new_month, person.salary, person=person)
    corrected = run.create("K", corrected_month, salary + 1000)
    run.tick()
    work = run.daily(fresh)[-1] if run.daily(fresh) else None
    registered = 0
    if run.report.check("verksamhet", "N valdes av schemat", work is not None):
        run.record_run(work)
        case = get_case_view(run.trusted, fresh)
        decided = [p for p in run.trusted.approvals.list("approved") if p.case_id == fresh]
        run.report.check("verksamhet", "N stängdes automatiskt som godkänt",
                         (work["status"], case.status, case.outcome) == ("completed", "closed", "approved"),
                         f"{work['status']}, {case.status}, {case.outcome}")
        run.report.check("verksamhet", "maskinbeslutet är märkt case_automation",
                         [p.decided_by for p in decided] == ["case_automation"], str([p.decided_by for p in decided]))
        registered = 1 if case.status == "closed" else 0
    work, proposal = run.prepared(corrected, "K") if run.daily(corrected) else (None, None)
    run.report.check("verksamhet", "rättelsen K stoppades för mänsklig granskning",
                     work is not None and work["result"].get("automatic_stopped") is True)
    if proposal:
        run.trusted.reject(proposal.id, run.ctx(corrected), "Röktest F5-7: rättelser granskas av handläggare")
        run.tick()
    run.close(corrected, "rejected", "Rättelse i röktestet; avslagen.")
    return registered


def free_months(factory, subject, start: date, count: int) -> list[date]:
    months, month = [], start
    for _ in range(24):
        if current_report(factory, subject.pnr, subject.employer, month) is None:
            months.append(month)
            if len(months) == count:
                return months
        month = previous_month(month)
    raise SystemExit("Hittade inga lediga rapportmånader för demopersonen")


def preflight(factory) -> list[str]:
    """Andra öppna löneärenden eller aktiva uppdrag skulle påverka urvalet."""
    from sqlalchemy import select

    from agents.case_workspace import ACTIVE
    from models import Case, CaseWork

    with factory() as session:
        cases = session.scalars(select(Case.case_number).where(Case.case_type == "salary_report",
                                                                Case.status != "closed")).all()
        works = session.scalars(select(CaseWork.case_number).where(CaseWork.status.in_(ACTIVE))).all()
    return [f"öppet ärende {n}" for n in cases] + [f"aktivt uppdrag i {n}" for n in works]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="store_true", help="Gör riktiga modellanrop (kostar)")
    parser.add_argument("--db", choices=("demo", "svc_test", "lakebase"), default="demo")
    parser.add_argument("--provider", choices=sorted(STANDARD_MODEL), help="Peka rollen standard på leverantörens modell")
    parser.add_argument("--avslag", action="store_true", help="Mot Lakebase: pröva även avslag av en rättelse")
    parser.add_argument("--pnr", help="Märkt verifieringsperson, 12 siffror (krävs mot Lakebase)")
    parser.add_argument("--arbetsgivare", help="Arbetsgivarens organisationsnummer, 10 siffror")
    parser.add_argument("--manad", type=date.fromisoformat, help="Rapportmånad, ÅÅÅÅ-MM-01")
    parser.add_argument("--lon", type=Decimal, help="Pensionsmedförande lön i ärende A")
    parser.add_argument("--logs-dir", type=Path, help="Loggmapp för körjournaler; annars repots logs/")
    args = parser.parse_args()

    lakebase = args.db == "lakebase"
    if lakebase and not (args.pnr and args.arbetsgivare and args.manad and args.lon):
        parser.error("mot Lakebase krävs --pnr, --arbetsgivare, --manad och --lon för en märkt verifieringsperson")
    now = datetime.now(UTC)
    local = now.astimezone(ZoneInfo("Europe/Stockholm"))
    if (local.hour, local.minute) < (7, 0):
        print("Urvalet gäller från 07.00 Europe/Stockholm. Kör efter det.")
        return 1
    pnr, employer, salary = DEMO_SUBJECT
    subject = SimpleNamespace(pnr=args.pnr or pnr, employer=args.arbetsgivare or employer)
    salary = args.lon or salary

    from ai import AIClient, MissingKeyError
    from ai.keys import resolve_api_key

    environ = dict(os.environ)
    if args.provider:
        environ["AI_ROLE_STANDARD"] = STANDARD_MODEL[args.provider]
    ai = AIClient(environ=environ)
    primary = environ.get("AI_ROLE_STANDARD", "").strip() or ai.config.roles["standard"].model
    print(f"Rollen standard: {primary}")
    try:
        _, key_env = resolve_api_key(ai.config.providers[primary.split(":")[0]], TEAM)
        print(f"{TEAM}: nyckel i {key_env}")
    except MissingKeyError as exc:
        print(f"{TEAM}: {exc}")
        return 1
    parts = "del 1" + (" med avslag" if args.avslag or not lakebase else "") + ("" if lakebase else ", del 2 och del 3")
    print(f"Plan: {args.db}, {parts}, levererad policy i del 1.")
    databases = {"demo": demo_database, "svc_test": lambda: svc_test_database((TEAM,)),
                 "lakebase": lakebase_database}
    if not args.run:
        if lakebase:
            print("Förkontroll mot Lakebase, bara läsning:")
            with lakebase_database() as db:
                counts = row_counts(db.factory)
                print(f"  Totalt {sum(counts.values())} rader i {len(counts)} tabeller")
                hinder = preflight(db.factory)
                print("  Hinder för urvalet: " + (", ".join(hinder) or "inga"))
                current = current_report(db.factory, subject.pnr, subject.employer, args.manad)
                print(f"  Gällande rapport {args.manad:%Y-%m}: "
                      + (f"version {current.version}, {current.pensionable_salary_sek} kr" if current else "ingen"))
        print("Inga modellanrop gjorda. Kör med --run för att genomföra röktestet.")
        return 0

    import tempfile

    report = Report()
    journal_dir = (args.logs_dir or REPO_ROOT / "logs") / "agent_runs"
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    with databases[args.db]() as db, tempfile.TemporaryDirectory() as policy_dir:
        print(f"Databas: {db.label}; agenten: {'begränsad roll' if TEAM in db.team_factories else 'simulerad roll'}")
        hinder = preflight(db.factory)
        if hinder:
            print("Avbryter: " + ", ".join(hinder))
            return 1
        trusted, workspace = build(db, ai, journal_dir)
        run = Run(db, trusted, workspace, subject, stamp=stamp, journal_dir=journal_dir, report=report, now=now)
        before = row_counts(db.factory)
        if lakebase:
            registered = selection(run, month=args.manad, salary=salary, reject=args.avslag)
        else:
            first, second = free_months(db.factory, subject, args.manad or previous_month(date.today()), 2)
            registered = selection(run, month=first, salary=salary, reject=True)
            stops(run, month=second, salary=salary, policy_dir=Path(policy_dir))
            other = SimpleNamespace(pnr=SECOND_SUBJECT[0], employer=SECOND_SUBJECT[1], salary=SECOND_SUBJECT[2])
            registered += automatic(run, person=other, new_month=free_months(db.factory, other, first, 1)[0],
                                    corrected_month=first, salary=salary, policy_dir=Path(policy_dir))
        run.report.check("verksamhet", "inga egna ärenden kvar att följa upp", not run.follow_up(), str(run.follow_up()))
        compare_counts(before, row_counts(db.factory), registered, report)

    failed = [(kind, label) for kind, label, passed, _ in report.checks if not passed]
    print(f"\nTotalt {report.cost:.4f} USD, {len(report.checks)} kontroller, {len(failed)} fel.")
    for kind, label in failed:
        print(f"  FEL ({kind}): {label}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
