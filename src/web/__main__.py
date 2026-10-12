"""Startar handläggar-UI:t lokalt: python -m web [--db demo|svc_test|lakebase] [--port 8765] [--reset-demo].

Servern binds alltid till 127.0.0.1 – UI:t saknar inloggning (v1) och ska inte
nås från andra datorer. Databasen väljs med HANDLAGGARE_DB (standard: demo).
Accessloggen är avstängd: adresserna innehåller personnummer.
"""

from __future__ import annotations

import argparse
from dataclasses import replace

import uvicorn

from web.app import create_app
from web.config import DATABASES, WebSettings

HOST = "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Handläggar-UI:t (Fas 4)")
    parser.add_argument("--db", choices=list(DATABASES), help="Databas (överstyr HANDLAGGARE_DB, standard demo)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--reset-demo", action="store_true",
        help="Ta bort den lokala demodatabasen och skapa den på nytt (bara HANDLAGGARE_DB=demo)",
    )
    args = parser.parse_args()

    settings = WebSettings.from_env()
    if args.db:
        settings = replace(settings, database=args.db)
    if args.reset_demo:
        if settings.database != "demo":
            parser.error("--reset-demo gäller bara demodatabasen")
        settings.demo_path.unlink(missing_ok=True)
    app = create_app(settings=settings)
    print(f"Handläggar-UI: http://{HOST}:{args.port}  ·  {settings.database_label}  ·  handläggare {settings.handler_id}", flush=True)
    uvicorn.run(app, host=HOST, port=args.port, access_log=False)


if __name__ == "__main__":
    main()
