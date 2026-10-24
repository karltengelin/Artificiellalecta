# Artificiellalecta

Simulerat tjänstepensionsbolag för utbildnings- och utvecklingsändamål. Bolaget administrerar **ålderspension inom kollektivavtalet ITP1** och drivs som en sandbox för att utforska hur ett tjänstepensionsbolag fungerar – med stöd av AI-agenter och automatiserade processer.

**Detta är inte ett riktigt försäkringsbolag.** Inga riktiga kunder, ingen riktig data, inget riktigt kapital.

## Kom igång

Läs dessa dokument i ordning:

1. [`MASTER_CONTEXT.md`](MASTER_CONTEXT.md) – Projektets fundament: vision, scope, designprinciper, arkitektur
2. [`BESLUTSLOGG.md`](BESLUTSLOGG.md) – Alla beslut med motivering
3. [`ATT_GORA.md`](ATT_GORA.md) – Aktuell backlog

## Mappstruktur (sammanfattning)

Se MASTER_CONTEXT §7 för fullständig översikt.

- `01_domän/` – Domänkunskap (ITP1, aktuariell grund, försäkringsvillkor, processer)
- `02_system/` – Systemdokumentation och agentbeskrivningar
- `03_skills/` – Skill-instruktioner (markdown)
- `04_regulatoriskt/` – Regelverkskällor (lager 1)
- `05_styrdokument/` – Interna styrdokument (lager 3)
- [`06_design/`](06_design/README.md) – Digital klarhet: bolagets gemensamma designspråk och visuella referens (B-034)
- `projekt/` – Delprojektens projektplaner (B-024)
- `src/` – Python-kod
- `tests/`, `data/`, `scripts/` – Tester, mockdata och kategoriserade körverktyg

Se [kodbas och skriptkatalog](02_system/skriptkatalog.md) för verktyg, beroenden,
körordning och vilka kommandon som läser eller ändrar data.

## Grafisk design

**Digital klarhet** är bolagets valda grafiska riktning (B-034): indigo, ljusa
ytor, DM Sans och mjukare former. Se [designspecifikationen](06_design/designsprak.md)
och [den visuella referensen](06_design/digital_klarhet.html) för rapport, slide
och handläggarvy. Designgrunden är dokumenterad; mallar och införande i befintliga
gränssnitt sker stegvis enligt ATT_GORA.

## Teknisk stack

- Python ≥ 3.11
- Databricks Lakebase (serverless Postgres) via SQLAlchemy (B-018)
- Modellagnostisk AI-arkitektur (OpenAI + Anthropic) via eget abstraktionslager i `src/ai/`
- Handläggar-UI: FastAPI + Jinja2 + HTMX ovanpå tjänstelagret, bara lokalt (`python scripts/web/start_ui.py` eller skrivbordsgenvägen från `scripts/web/install_desktop_shortcut.py`, se `02_system/handläggar-ui.md`)
- Markdown som primärt informationsformat
- Git + GitHub för versionskontroll
