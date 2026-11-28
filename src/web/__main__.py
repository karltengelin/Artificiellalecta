"""Startar handläggar-UI:t lokalt: python -m web [--db demo|svc_test|lakebase] [--port PORT] [--reset-demo].

Provkörning av ett scenario (paket B steg 8, Z13), bara mot den lokala demodatabasen:
`--demo-fil KOPIA.db` öppnar en kopia av en provbild (t.ex. paket C:s startbild), `--behall-schema` lämnar dess
schema som det är och `--affarsdag ÅÅÅÅ-MM-DD` kör varje förfrågan på en simulerad affärsdag.

Servern binds alltid till 127.0.0.1. Certa är entré till de lokala arbetsytorna.
Databasen väljs med HANDLAGGARE_DB (standard: demo).
Accessloggen är avstängd: adresserna innehåller personnummer.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import replace
from datetime import date
from pathlib import Path

import uvicorn

from services.development_demo import DemoDelivery
from web.app import create_app
from web.config import DATABASES, DEFAULT_PORTS, WebSettings

HOST = "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Handläggar-UI:t (Fas 4)")
    parser.add_argument("--db", choices=list(DATABASES), help="Databas (överstyr HANDLAGGARE_DB, standard demo)")
    parser.add_argument("--port", type=int, help="Port (Lakebase 8765, test 8766, demo 8767)")
    parser.add_argument("--actuary-workspace", action=argparse.BooleanOptionalAction,
                        help="Överstyr WEB_ACTUARY_WORKSPACE för denna start")
    parser.add_argument("--company-orchestrator", action=argparse.BooleanOptionalAction,
                        help="Öppna bolagspiloten i demo med konfigurerad AI-klient och operatörsinloggning")
    parser.add_argument("--report-font-dir", type=Path, help="Överstyr WEB_REPORT_FONT_DIR för denna start")
    parser.add_argument(
        "--reset-demo", action="store_true",
        help="Ta bort den lokala demodatabasen och skapa den på nytt (bara HANDLAGGARE_DB=demo)",
    )
    parser.add_argument("--affarsdag", type=date.fromisoformat, metavar="ÅÅÅÅ-MM-DD",
                        help="Simulerad affärsdag för varje förfrågan (bara demo, paket B steg 8)")
    parser.add_argument("--demo-fil", type=Path, metavar="FIL",
                        help="Öppna en befintlig SQLite-fil i stället för data/handlaggare_demo.db (bara demo)")
    parser.add_argument("--behall-schema", action="store_true",
                        help="Lägg inte till saknade tabeller i demofilen – för prov utan paket B:s steg 4–7")
    args = parser.parse_args()

    settings = WebSettings.from_env()
    if args.db:
        settings = replace(settings, database=args.db)
    if (args.affarsdag or args.demo_fil or args.behall_schema) and settings.database != "demo":
        parser.error("--affarsdag, --demo-fil och --behall-schema gäller bara den lokala demodatabasen")
    if args.demo_fil is not None:
        if args.reset_demo:
            parser.error("--reset-demo och --demo-fil går inte att kombinera")
        if not args.demo_fil.is_file():
            parser.error(f"{args.demo_fil} finns inte")
        settings = replace(settings, demo_path=args.demo_fil.resolve())
    if args.affarsdag or args.behall_schema:
        settings = replace(settings, business_day=args.affarsdag, keep_schema=args.behall_schema)
    company_ai = None
    if args.company_orchestrator and (settings.database != "demo" or settings.operator_password_hash is None):
        parser.error("--company-orchestrator kräver demo och konfigurerad operatörsinloggning")
    company_enabled = settings.company_orchestrator if args.company_orchestrator is None else args.company_orchestrator
    if company_enabled and settings.database == "demo" and settings.operator_password_hash is not None:
        from ai import AIClient

        company_ai = AIClient()
    port = args.port if args.port is not None else DEFAULT_PORTS[settings.database]
    if args.reset_demo:
        if settings.database != "demo":
            parser.error("--reset-demo gäller bara demodatabasen")
        settings.demo_path.unlink(missing_ok=True)
        DemoDelivery(settings.demo_path).path.unlink(missing_ok=True)
    actuary_enabled = settings.actuary_workspace if args.actuary_workspace is None else args.actuary_workspace
    if actuary_enabled:
        from agents.actuarial_dialogue import ActuarialDialogue
        from ai import AIClient
        from reporting.template import register_dm_sans
        from services.errors import ServiceConfigError
        from web.database import build_actuary_service, build_services

        font_dir = args.report_font_dir or Path(os.environ.get("WEB_REPORT_FONT_DIR") or "tmp/pdfs/fonts")
        service, agent = build_services(settings)
        dialogue = None
        try:
            register_dm_sans(font_dir)
            dialogue = ActuarialDialogue(service, build_actuary_service(settings, service), AIClient(),
                                         environment_id=settings.database, dataset_ref=settings.dataset_ref)
        except (FileNotFoundError, ServiceConfigError):
            if args.actuary_workspace:
                raise
            print("Aktuariedialogen är avstängd: kontrollera lokala rapporttypsnitt och aktuarierollen.", flush=True)
        app = create_app(service=service, settings=settings, case_agent=agent,
                         actuarial_dialogue_console=dialogue, company_ai=company_ai)
    else:
        app = create_app(settings=settings, company_ai=company_ai)
    day = f"  ·  simulerad affärsdag {settings.business_day}" if settings.business_day else ""
    print(f"Bolagets webb: http://{HOST}:{port}  ·  {settings.database_label}{day}",
          flush=True)
    uvicorn.run(app, host=HOST, port=port, access_log=False, proxy_headers=False)


if __name__ == "__main__":
    main()
