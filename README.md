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
- `src/` – Python-kod
- `tests/`, `data/`, `scripts/` – Tester, mockdata, engångsskript

## Teknisk stack

- Python ≥ 3.11
- Supabase (PostgreSQL) via SQLAlchemy
- Modellagnostisk AI-arkitektur (OpenAI + Anthropic)
- Markdown som primärt informationsformat
- Git + GitHub för versionskontroll
