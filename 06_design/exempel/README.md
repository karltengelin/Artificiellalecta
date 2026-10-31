# Exempelrapport: agentnyttjande

För presentationsmallens separata exempel med fem bildtyper, se
[presentationsunderlaget](presentationsunderlag.md) och
[mallens dokumentation](../presentationsmall.md).
[Introduktionen för nya medarbetare](introduktion_nya_medarbetare.md) är ett
exempel på samma mall med verkligt projektinnehåll per 2026-10-31: principer,
avgränsningar, organisation och byggstatus. Den har ingen incheckad PDF; bygg
den med `scripts/documentation/build_presentation.py` enligt mallens dokumentation.

En beställd demonstration av **Digital klarhet v1.0** med utförlig rapporttext,
tio diagram, tabeller och metodavsnitt. Allt mätunderlag är påhittat. September
2026 är en illustrativ rapportmånad i ett tänkt moget driftläge, inte verklig drift
eller en beskrivning av vilka agenter som är implementerade.

- [Läs PDF-rapporten](../../output/pdf/agentnyttjande_september_2026.pdf).
- [Läs den genererade Markdown-rapporten](../../output/pdf/agentnyttjande_september_2026.md).
- [Redaktionellt underlag](rapportunderlag_agentnyttjande.md) är Markdown med platshållare för beräknade mått och tabeller.
- [Scenariodata](../../data/examples/agent_usage_2026_09.json) innehåller samtliga mätvärden, rollpriser och tidsantaganden.
- [Generator](../../scripts/documentation/build_agent_usage_example.py) kontrollerar samband och producerar PDF, Markdown och SVG-diagram.
- [Gemensam rapportmall](../rapportmall.md) används för layouten; beräkningar, rapportinnehåll och diagramserier finns i `src/reporting/agent_usage_example.py`.

Detta är ett exempel, inte en aktiverad dokumentgateway eller den framtida
gemensamma skillen. Ingen faktisk agent-, databas- eller modellkörning behövs.
Rapporten ändrar inte backloggens införandeplan eller beslutad byggordning.

## Återskapa

`reportlab` installeras med projektets beroenden. Lägg DM Sans Regular, Medium och Bold som statiska
TTF-filer i `tmp/pdfs/fonts/`, med namnen `DM-Sans-Regular.ttf`,
`DM-Sans-Medium.ttf` och `DM-Sans-Bold.ttf`. Alternativ fontmapp anges med
`--font-dir`. Typsnittet finns via Google Fonts; det laddas inte ned automatiskt
av generatorn och fontfilerna ingår inte i repot.

Kör från repots rot:

```powershell
python scripts/documentation/build_agent_usage_example.py
```

Resultatet läggs i `output/pdf/`, med diagram under `figures/`. Generatorns
beräknings- och layoutkontroll skrivs till `tmp/pdfs/agent_usage_validation.json`.
Den använder projektets gemensamma färg-, typografi- och radievärden från
`src/design/digital_clarity.tokens.json`. Diagrammens extra seriefärger är lokala
exempelvärden och fastställer inte en utökad bolagspalett.

Layouten i `src/reporting/template.py` kan återanvändas utan exemplets data.
Testerna under `tests/test_reporting_*.py` använder inbyggda Helvetica och
kräver inga DM Sans-filer. Ordinarie exempelrapport använder fortsatt DM Sans.

PDF-sidorna ska renderas och granskas visuellt efter ändringar. Kostnader,
tidsvinster och kvalitetsutfall får inte presenteras som verkliga mätresultat.
