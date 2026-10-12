"""Handläggar-UI:t (Fas 4, delprojekt 1, B-020/B-028).

Ett lokalt webbgränssnitt (FastAPI + Jinja2 + HTMX) där handläggaren anropar
tjänstelagret. Webbkoden anropar bara `ServiceLayer` – execute, approve,
reject och läsoperationerna – och rör aldrig modeller eller sessioner direkt,
så att varje läsning av personuppgifter och varje ändring loggas på samma sätt
som för agenter och skript.

    python -m web                       # demodatabas (SQLite), http://127.0.0.1:8765
    HANDLAGGARE_DB=svc_test python -m web

Specifikation: projekt/01_ärendehantering/PROJEKTPLAN.md, 02_system/handläggar-ui.md.
"""

from web.app import create_app

__all__ = ["create_app"]
