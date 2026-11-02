"""Röktest av hela ärendeflödet mot riktig modell (Fas 5 F5-6, B-033).

Ärende → agent → förslag → beslut → stängt, genom samma adapter som webbens ärendepanel
(`CaseWorkspace`). Skriptet agerar handläggare, märkt `rooktest`: det registrerar ett ärende om
löneunderlag, lämnar över det till handläggaragenten (*Låt agenten handlägga ärendet*) och
avgör agentens förslag. Agentens verktyg och databasroll är desamma som i webben.

| `--db`     | Databas                                                                  | Agentens roll |
|------------|--------------------------------------------------------------------------|---------------|
| `demo`     | Demobeståndet i en SQLite-databas i minnet                               | simulerad     |
| `svc_test` | Demobeståndet i ett eget schema i SERVICES_TEST_POSTGRES_URL, tas bort efteråt | riktig begränsad roll med `agent_forsakring`s rättigheter, när en testroll finns |
| `lakebase` | Beståndet via DATABASE_URL; ärenden, förslag och registreringar finns kvar | den riktiga rollen via AGENT_FORSAKRING_DATABASE_URL |

Scenarier:

1. **Godkänt.** Agenten ska föreslå `register_salary_report` som exakt motsvarar ärendet.
   Handläggaren godkänner, och betrodd kod stänger ärendet som `approved` enligt ärendepolicyn.
2. **Avslag** (`--avslag`). Ett nytt ärende för samma person och månad med annan lön. Handläggaren
   avslår förslaget, uppdraget går till handläggaren och ingenting registreras. Handläggaren
   stänger ärendet som `rejected`.

Finns redan en rapport för månaden blir ärendet en rättelse av den gällande versionen, annars
en ny rapport. Före och efter jämförs radantalen i alla tabeller. Bara ärenden, uppdrag, dialog,
dagsbudget, förslag, händelselogg och (vid godkännande) löneunderlag får ändras.

Mot Lakebase krävs en märkt verifieringsperson (`--pnr`, `--arbetsgivare`, `--lon`). Utan `--run`
görs en förkontroll som bara läser: radantal, personens rapporter och vilken rapport ärendet
skulle bli. `--run` skriver i beståndet och görs efter backup och operatörens OK (AGENTS.md §4.5).

Utan --run görs inga modellanrop. Kostnaden begränsas av försäkringsteamets tak i ecosystem.yaml
(0,50 USD per uppdrag). Nycklar läses ur .env och skrivs aldrig ut. Körjournalerna hamnar i
logs/agent_runs/ eller under `--logs-dir`, så att webben mot Lakebase kan öppna dem.

Användning (från repo-roten, i .venv):
    python scripts/diagnostics/smoke_test_case_flow.py                        # plan, ingen kostnad
    python scripts/diagnostics/smoke_test_case_flow.py --run --avslag         # demo
    python scripts/diagnostics/smoke_test_case_flow.py --run --db svc_test --avslag
    python scripts/diagnostics/smoke_test_case_flow.py --db lakebase --pnr 199204171236 --arbetsgivare 5552871575 --lon 40000
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from smoke_test_flow import REPO_ROOT, Report, demo_database, svc_test_database

OPERATOR_ID = "rooktest"
TEAM = "forsakring"
STANDARD_MODEL = {"anthropic": "anthropic:claude-sonnet-5", "openai": "openai:gpt-6.1-sol"}
#: Demobeståndets aktiva försäkrade Anna Andersson; premier finns till och med 2026-09
DEMO_SUBJECT = ("198505151236", "5560000001", Decimal(46000))
#: Tabeller som flödet får ändra; alla andra ska ha samma radantal efteråt
CHANGING = {"cases", "case_work", "case_messages", "case_work_days", "approval_requests", "operation_events"}
INSTRUCTION = "Handlägg ärendet om löneunderlag och föreslå registreringen om underlaget stämmer."


def previous_month(today: date) -> date:
    return date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)


@contextmanager
def lakebase_database() -> Iterator[SimpleNamespace]:
    """Beståndet med betrodd anslutning och handläggaragentens riktiga roll – aldrig den betrodda som reserv."""
    from services.db import AGENT_ROLES, database_session_factory

    role_env = AGENT_ROLES[TEAM][1]
    for env in ("DATABASE_URL", role_env):
        if not os.environ.get(env):
            raise SystemExit(f"{env} saknas i .env")
    if os.environ[role_env] == os.environ["DATABASE_URL"]:
        raise SystemExit(f"{role_env} är DATABASE_URL – agenten ska ha sin begränsade roll")
    yield SimpleNamespace(label="Lakebase – beståndet (ärendena finns kvar)", factory=database_session_factory(),
                          team_factories={TEAM: database_session_factory(role_env)})


def row_counts(factory) -> dict[str, int]:
    from sqlalchemy import inspect

    with factory() as session:
        names = sorted(inspect(session.connection()).get_table_names())
        return {name: session.connection().exec_driver_sql(f'SELECT count(*) FROM "{name}"').scalar_one()
                for name in names}


def current_report(factory, pnr: str, employer: str, month: date):
    """Gällande rapport läst direkt, så att förkontrollen inte skriver läshändelser."""
    from sqlalchemy import select

    from models import Employer, InsuredPerson, SalaryReport

    with factory() as session:
        return session.scalar(
            select(SalaryReport).join(InsuredPerson, InsuredPerson.id == SalaryReport.insured_person_id)
            .join(Employer, Employer.id == SalaryReport.employer_id)
            .where(InsuredPerson.personal_id_number == pnr, Employer.org_number == employer,
                   SalaryReport.period_month == month)
            .order_by(SalaryReport.version.desc()).limit(1))


def case_details(factory, subject, salary: Decimal) -> dict:
    current = current_report(factory, subject.pnr, subject.employer, subject.month)
    if current is None:
        return {"pensionable_salary_sek": str(salary), "kind": "new", "source": "employer"}
    return {"pensionable_salary_sek": str(salary), "kind": "correction", "corrects_version": current.version,
            "source": "employer"}


def describe(details: dict) -> str:
    if details["kind"] == "new":
        return f"ny rapport, {details['pensionable_salary_sek']} kr"
    return f"rättelse av version {details['corrects_version']} till {details['pensionable_salary_sek']} kr"


def build(db, ai, journal_dir: Path | None):
    from agents.case_workspace import CaseWorkspace
    from services import ServiceLayer
    from web.agent import CaseAgent

    trusted = ServiceLayer(session_factory=db.factory)
    own = db.team_factories.get(TEAM)
    agent = CaseAgent(
        agent_service_factory=lambda: ServiceLayer(session_factory=own or db.factory,
            validation_session_factory=db.factory, agent_role="agent_forsakring"),
        simulated_role=own is None, ai_factory=lambda: ai, journal_dir=journal_dir)
    return trusted, CaseWorkspace.build(trusted, agent, journal_dir=journal_dir)


def journal_tools(path: Path) -> tuple[list[str], str]:
    import json

    if not path.exists():
        return [], ""
    text = path.read_text(encoding="utf-8")
    events = [json.loads(line) for line in text.splitlines() if line.strip()]
    return [e["skill"] for e in events if e.get("type") == "tool_intent"], text


def scenario(trusted, workspace, db, subject, *, label: str, salary: Decimal, approve: bool,
             journal_dir: Path, stamp: str, report: Report) -> None:
    from services import Actor, OperationContext
    from services.case_review import expected_salary
    from services.operations.salary import SalaryReportInput

    human = Actor.human(OPERATOR_ID)
    details = case_details(db.factory, subject, salary)
    reference = f"ROOKTEST-F5-6-{stamp}-{label}"
    print(f"\n== {label}: {'godkänns' if approve else 'avslås'} – {describe(details)}, referens {reference}")
    before = current_report(db.factory, subject.pnr, subject.employer, subject.month)
    number = trusted.execute("create_case", OperationContext(actor=human, reason="Märkt röktest av ärendeflödet (F5-6)"), {
        "case_type": "salary_report", "personal_id_number": subject.pnr, "employer_org_number": subject.employer,
        "period_month": subject.month.isoformat(), "received_date": date.today().isoformat(),
        "source_reference": reference, "details": details,
    }).output.case_number
    report.check("verksamhet", f"ärendet {number} registrerat", bool(number))

    ident = workspace.submit(number, INSTRUCTION, actor=human, key=f"rooktest-{stamp}-{label}", mode="handle")
    processed = workspace.process(ident)
    view = workspace.view(number, human)
    work = next(w for w in view["works"] if w["id"] == ident)
    usage = (work["result"] or {}).get("usage", {})
    report.cost += usage.get("cost_usd", 0.0)
    run = (work["result"] or {}).get("run", {})
    print(f"  Körning {work['run_id']}: {run.get('status')}, {usage.get('steps')} steg, "
          f"{usage.get('tool_calls')} verktygsanrop, {usage.get('cost_usd', 0):.4f} USD")
    print(f"  Sammanfattning: {run.get('summary', '')[:300]}")
    report.check("verksamhet", "agentkörningen slutförd", processed, work["status"])
    report.check("verksamhet", "uppdraget väntar på godkännande", work["status"] == "waiting_approval", work["status"])
    case = trusted.execute("get_case", OperationContext(actor=human), {"case_number": number}).output
    report.check("verksamhet", "ärendet väntar på godkännande efter körningen", case.status == "waiting_approval",
                 case.status)

    tools, journal = journal_tools(journal_dir / f"{work['run_id']}.jsonl")
    report.check("verksamhet", "agenten läste ärendet med get_case", "get_case" in tools, ", ".join(tools))
    report.check("verksamhet", "journalen saknar personnummer",
                 bool(journal) and subject.pnr not in journal and f"{subject.pnr[:8]}-{subject.pnr[8:]}" not in journal)
    pending = [p for p in trusted.approvals.list("pending") if p.case_id == number]
    report.check("verksamhet", "exakt ett väntande förslag i ärendet", len(pending) == 1, str(len(pending)))
    if len(pending) != 1:
        return
    proposal = pending[0]
    report.check("verksamhet", "förslaget är register_salary_report från handläggaragenten i körningen",
                 (proposal.operation, proposal.proposed_by, proposal.run_id)
                 == ("register_salary_report", "case_handler", work["run_id"]),
                 f"{proposal.operation}, {proposal.proposed_by}, {proposal.run_id}")
    stored = get_case_view(trusted, number)
    report.check("facit", "förslagets indata motsvarar ärendet exakt",
                 SalaryReportInput.model_validate(proposal.input) == expected_salary(stored))
    unchanged = current_report(db.factory, subject.pnr, subject.employer, subject.month)
    report.check("verksamhet", "ingen registrering före beslutet",
                 (before and before.id) == (unchanged and unchanged.id))

    decision = OperationContext(actor=human, case_id=number)
    if approve:
        trusted.approve(proposal.id, decision, "Röktest F5-6: underlaget stämmer med ärendet")
    else:
        trusted.reject(proposal.id, decision, "Röktest F5-6: avslås för att pröva avslagsvägen")
    workspace.settle(ident)
    work = next(w for w in workspace.view(number, human)["works"] if w["id"] == ident)
    after = current_report(db.factory, subject.pnr, subject.employer, subject.month)
    if approve:
        expected_version = 1 if details["kind"] == "new" else details["corrects_version"] + 1
        report.check("facit", f"löneunderlaget registrerat som version {expected_version}",
                     after is not None and after.version == expected_version
                     and Decimal(after.pensionable_salary_sek) == salary and after.source_reference == reference,
                     f"version {after and after.version}, {after and after.pensionable_salary_sek} kr")
        report.check("verksamhet", "uppdraget klart efter beslutet", work["status"] == "completed", work["status"])
        case = get_case_view(trusted, number)
        report.check("verksamhet", "ärendet stängt som godkänt av betrodd kod",
                     (case.status, case.outcome, case.closed_by) == ("closed", "approved", "case_worker"),
                     f"{case.status}, {case.outcome}, {case.closed_by}")
    else:
        report.check("facit", "ingen registrering efter avslaget",
                     (before and before.id) == (after and after.id))
        report.check("verksamhet", "uppdraget går till handläggaren", work["status"] == "needs_human", work["status"])
        trusted.execute("close_case", OperationContext(actor=human, case_id=number,
                        reason="Röktest F5-6: förslaget avslogs"),
                        {"case_number": number, "outcome": "rejected",
                         "closing_note": "Avslaget i röktestet; inget underlag registrerat."})
        case = get_case_view(trusted, number)
        report.check("verksamhet", "handläggaren stänger ärendet som avslaget",
                     (case.status, case.outcome, case.closed_by) == ("closed", "rejected", OPERATOR_ID),
                     f"{case.status}, {case.outcome}, {case.closed_by}")


def get_case_view(trusted, number: str):
    from services import Actor, OperationContext

    return trusted.execute("get_case", OperationContext(actor=Actor.human(OPERATOR_ID)),
                           {"case_number": number}).output


def compare_counts(before: dict[str, int], after: dict[str, int], approved: int, report: Report) -> None:
    changed = {name: (before.get(name, 0), after.get(name, 0)) for name in set(before) | set(after)
               if before.get(name, 0) != after.get(name, 0)}
    print("\nRadantal som ändrats: " + (", ".join(f"{n} {a}→{b}" for n, (a, b) in sorted(changed.items())) or "inga"))
    unexpected = {n: v for n, v in changed.items() if n not in CHANGING | {"salary_reports"}}
    report.check("facit", "övriga tabellers radantal oförändrade", not unexpected,
                 ", ".join(f"{n} {a}→{b}" for n, (a, b) in sorted(unexpected.items())))
    reports = after.get("salary_reports", 0) - before.get("salary_reports", 0)
    report.check("facit", f"löneunderlagen ökade med {approved}", reports == approved, str(reports))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="store_true", help="Gör riktiga modellanrop (kostar)")
    parser.add_argument("--db", choices=("demo", "svc_test", "lakebase"), default="demo")
    parser.add_argument("--provider", choices=sorted(STANDARD_MODEL), help="Peka rollen standard på leverantörens modell")
    parser.add_argument("--avslag", action="store_true", help="Pröva även avslagsvägen i ett andra ärende")
    parser.add_argument("--pnr", help="Märkt verifieringsperson, 12 siffror (krävs mot Lakebase)")
    parser.add_argument("--arbetsgivare", help="Arbetsgivarens organisationsnummer, 10 siffror")
    parser.add_argument("--manad", type=date.fromisoformat, help="Rapportmånad, ÅÅÅÅ-MM-01 (standard: förra månaden)")
    parser.add_argument("--lon", type=Decimal, help="Pensionsmedförande lön i det godkända ärendet")
    parser.add_argument("--logs-dir", type=Path, help="Loggmapp för körjournaler, t.ex. webbens; annars repots logs/")
    args = parser.parse_args()

    if args.db == "lakebase" and not (args.pnr and args.arbetsgivare and args.lon):
        parser.error("mot Lakebase krävs --pnr, --arbetsgivare och --lon för en märkt verifieringsperson")
    pnr, employer, salary = DEMO_SUBJECT
    subject = SimpleNamespace(pnr=args.pnr or pnr, employer=args.arbetsgivare or employer,
                              month=args.manad or previous_month(date.today()))
    salary = args.lon or salary

    from ai import AIClient, MissingKeyError
    from ai.keys import resolve_api_key

    environ = dict(os.environ)
    if args.provider:
        environ["AI_ROLE_STANDARD"] = STANDARD_MODEL[args.provider]
    ai = AIClient(environ=environ)
    role = ai.config.roles["standard"]
    primary = environ.get("AI_ROLE_STANDARD", "").strip() or role.model
    print(f"Rollen standard: {primary}, reserv {', '.join(role.fallbacks) or '–'}")
    provider = primary.split(":")[0]
    try:
        _, key_env = resolve_api_key(ai.config.providers[provider], TEAM)
        print(f"{TEAM}: nyckel för {provider} i {key_env}")
    except MissingKeyError as exc:
        print(f"{TEAM}: {exc}")
        return 1
    scenarios = [("A", salary, True)] + ([("B", salary + 500, False)] if args.avslag else [])
    print(f"Plan: {args.db}, {subject.month:%Y-%m}, " + ", ".join(
        f"ärende {label} {amount} kr {'godkänns' if ok else 'avslås'}" for label, amount, ok in scenarios) + ".")
    databases = {"demo": demo_database, "svc_test": lambda: svc_test_database((TEAM,)),
                 "lakebase": lakebase_database}
    if not args.run:
        if args.db == "lakebase":
            print("Förkontroll mot Lakebase, bara läsning:")
            with lakebase_database() as db:
                counts = row_counts(db.factory)
                print("  " + ", ".join(f"{n} {c}" for n, c in counts.items()))
                print(f"  Totalt {sum(counts.values())} rader")
                current = current_report(db.factory, subject.pnr, subject.employer, subject.month)
                print(f"  Gällande rapport {subject.month:%Y-%m}: "
                      + (f"version {current.version}, {current.pensionable_salary_sek} kr" if current else "ingen"))
                print(f"  Ärende A blir: {describe(case_details(db.factory, subject, salary))}")
        print("Inga modellanrop gjorda. Kör med --run för att genomföra röktestet.")
        return 0

    report = Report()
    journal_dir = (args.logs_dir or REPO_ROOT / "logs") / "agent_runs"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    with databases[args.db]() as db:
        print(f"Databas: {db.label}; agenten: {'begränsad roll' if TEAM in db.team_factories else 'simulerad roll'}")
        trusted, workspace = build(db, ai, journal_dir)
        before = row_counts(db.factory)
        for label, amount, approve in scenarios:
            scenario(trusted, workspace, db, subject, label=label, salary=amount, approve=approve,
                     journal_dir=journal_dir, stamp=stamp, report=report)
        compare_counts(before, row_counts(db.factory), 1, report)

    failed = [(kind, label) for kind, label, passed, _ in report.checks if not passed]
    print(f"\nTotalt {report.cost:.4f} USD, {len(report.checks)} kontroller, {len(failed)} fel, {len(report.notes)} iakttagelser.")
    for kind, label in failed:
        print(f"  FEL ({kind}): {label}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
