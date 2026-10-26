# Artificiellalecta

Simulerat tjänstepensionsbolag för utbildnings- och utvecklingsändamål. Bolaget administrerar **ålderspension inom kollektivavtalet ITP1** och drivs som en sandbox för att utforska hur ett tjänstepensionsbolag fungerar – med stöd av AI-agenter och automatiserade processer.

Målet är ett **artificiellt men hypotetiskt fungerande, AI-native tjänstepensionsföretag**.
Verksamhetens behov styr bygget. Regeländringshantering är en generell verksamhetsförmåga;
framtida demonstrationer visar den tillsammans med andra ordinarie förmågor. Företaget
ska inte anpassas till ett bestämt demoscenario eller få en hårdkodad demo-knapp.
Se [visionen och avgränsningen av demonstrationer](MASTER_CONTEXT.md#1-vision-och-syfte).

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

## Tester

Testerna kan köras per verksamhetsområde, teknisk del eller efter Git-ändringar med
kända beroenden. Se [teststrategin](02_system/teststrategi.md) för grupper, miljöer och
när hela sviten behövs. Framtida områden utan tester redovisas uttryckligen.

```powershell
python scripts/testing/run_tests.py --list
python scripts/testing/run_tests.py --changed --base origin/main
python scripts/testing/run_tests.py --suite reporting --run
```

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
- Handläggar-UI: FastAPI + Jinja2 + HTMX ovanpå tjänstelagret, bara lokalt. Vanlig skrivbordsgenväg använder Lakebase (8765); separat DEMO-genväg och `python scripts/web/start_ui.py` använder lokal övningsdata (8767). Installera genvägarna med `python scripts/web/install_desktop_shortcut.py`. Ingen synkning mellan miljöerna; se [handläggar-ui.md](02_system/handläggar-ui.md)
- Markdown som primärt informationsformat
- Git + GitHub för versionskontroll

I handläggargränssnittets sidhuvud kan du välja **Datakälla** och växla mellan Lakebase
(Postgres) och lokal demo (SQLite). Valet öppnar den andra miljöns startsida i samma flik;
databaserna förblir separata. Se [miljövalet](02_system/handläggar-ui.md#byta-datakälla-i-gränssnittet).

Menyvalet **Bestånd** visar försäkrade i vald datakälla. Sök på namn eller nummer, filtrera på
arbetsgivare och nuvarande försäkringsläge och öppna personens översikt från listan. Antal och
sidindelning avser personer; läsningarna loggas via tjänstelagret.

## Planerad operatörscentral

[Projekt 10](projekt/10_operatörscentral/PROJEKTPLAN.md) planerar Karls arbetsyta
på VD-nivå: bolagsläge och konsolidering när underlagen finns, teamens arbete,
agentkostnader, frågor mot data samt inriktningsbeslut om modellpolicy och budget.
Handläggarärenden hanteras fortsatt i specialistgränssnitt. Plan och
[första interaktiva skiss](projekt/10_operatörscentral/SKISS.md) finns;
[OC-0:s beslutsförslag med val A–X](02_system/operatörscentral_beslutsforslag.md)
är framtaget 2026-10-26 och väntar på godkännande. Operatörscentralen är ännu inte driftsatt.
