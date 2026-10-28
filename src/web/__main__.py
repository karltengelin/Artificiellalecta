"""Startar handläggar-UI:t lokalt: python -m web [--db demo|svc_test|lakebase] [--port PORT] [--reset-demo].

Servern binds alltid till 127.0.0.1 – v1-handläggningen saknar inloggning och ska
inte nås från andra datorer. Operatörssessionen är separat för bolagsfrågor.
Databasen väljs med HANDLAGGARE_DB (standard: demo).
Accessloggen är avstängd: adresserna innehåller personnummer.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import uvicorn

from web.app import create_app
from web.config import DATABASES, DEFAULT_PORTS, WebSettings

HOST = "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Handläggar-UI:t (Fas 4)")
    parser.add_argument("--db", choices=list(DATABASES), help="Databas (överstyr HANDLAGGARE_DB, standard demo)")
    parser.add_argument("--port", type=int, help="Port (Lakebase 8765, test 8766, demo 8767)")
    parser.add_argument("--company-questions", action="store_true", help="Anslut OC-3a med konfigurerad AI-klient och aktuarieteam")
    parser.add_argument("--report-font-dir", type=Path, default=Path("tmp/pdfs/fonts"), help="Lokala statiska DM Sans-filer för A4-export")
    parser.add_argument(
        "--reset-demo", action="store_true",
        help="Ta bort den lokala demodatabasen och skapa den på nytt (bara HANDLAGGARE_DB=demo)",
    )
    args = parser.parse_args()

    settings = WebSettings.from_env()
    if args.db:
        settings = replace(settings, database=args.db)
    port = args.port if args.port is not None else DEFAULT_PORTS[settings.database]
    if args.reset_demo:
        if settings.database != "demo":
            parser.error("--reset-demo gäller bara demodatabasen")
        settings.demo_path.unlink(missing_ok=True)
    if args.company_questions:
        from ai import AIClient
        from reporting import render_report
        from reporting.template import register_dm_sans
        from web.database import build_question_services

        register_dm_sans(args.report_font_dir)
        service, agent, questions = build_question_services(settings, ai=AIClient(), renderer=render_report)
        app = create_app(service=service, settings=settings, case_agent=agent, question_console=questions)
    else:
        app = create_app(settings=settings)
    print(f"Handläggar-UI: http://{HOST}:{port}  ·  {settings.database_label}  ·  handläggare {settings.handler_id}", flush=True)
    uvicorn.run(app, host=HOST, port=port, access_log=False, proxy_headers=False)


if __name__ == "__main__":
    main()
