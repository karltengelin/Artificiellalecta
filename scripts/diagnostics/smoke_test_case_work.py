"""Röktest av ett fritt ärendedeluppdrag mot riktig modell och isolerad lokal demodata.

Utan --run görs ingenting. Inga nätverksdatabaser, testmodeller eller framtida
regelstatusar används. Skrivande ärendehandläggning verifieras separat när reglerna gäller.
"""

import argparse
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import create_engine

from agents.case_workspace import CaseWorkspace
from services import Actor, OperationContext, ServiceLayer
from services.db import session_factory_for
from utils.demo_data import create_demo_database
from web.agent import CaseAgent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Gör riktiga modellanrop inom handläggarens ordinarie tak")
    args = parser.parse_args()
    if not args.run:
        print("Ingen körning. Välj --run för det avgränsade modellprovet.")
        return
    root = ROOT / "logs" / "case_work_smoke"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="run-", dir=root) as temp:
        engine = create_engine(f"sqlite:///{Path(temp) / 'case.db'}")
        create_demo_database(engine, with_proposals=False)
        factory = session_factory_for(engine)
        trusted = ServiceLayer(session_factory=factory)
        agent = CaseAgent(agent_service_factory=lambda: ServiceLayer(session_factory=factory,
            validation_session_factory=factory, agent_role="agent_forsakring"), simulated_role=True)
        console = CaseWorkspace.build(trusted, agent)
        today = date.today()
        number = trusted.execute("create_case", OperationContext(actor=Actor.human("smoke_operator"),
            reason="Märkt syntetiskt modellprov"), {
                "case_type": "salary_report", "personal_id_number": "198505151236",
                "employer_org_number": "5560000001", "period_month": today.replace(day=1).isoformat(),
                "received_date": today.isoformat(), "source_reference": "SMOKE-CASE-WORK",
                "details": {"pensionable_salary_sek": "47000", "kind": "new", "source": "employer"},
            }).output.case_number
        ident = console.submit(number, "Läs ärendet och förklara vilket underlag vi har och vad som återstår "
            "innan löneunderlaget kan registreras. Förhandsberäkna premien med verktyget. Gör inga förslag.",
            actor=Actor.human("smoke_operator"), key="read-only")
        try:
            assert console.process(ident), "Körningen kunde inte slutföras"
            view = console.view(number, Actor.human("smoke_operator"))
            job = view["works"][0]
            assert job["result"]["run"]["status"] == "completed", "Modelluppdraget slutfördes inte"
            assert job["status"] in {"completed", "waiting_info", "needs_human"}, "Oväntad arbetsstatus"
            assert not trusted.approvals.list("pending"), "Läsuppdraget skapade ett förslag"
            assert len(view["messages"]) >= 2, "Dialogen sparades inte"
            print("Godkänt: ärendemandat, fritt uppdrag, modell/verktyg, sparad dialog och inga skrivförslag.")
            print("Arbetsstatus:", job["status"])
            print(f"Kostnad: {job['result']['usage']['cost_usd']:.4f} USD")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
