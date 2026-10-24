# Rapportmall – Digital klarhet

**Mallversion:** 1.0 | **Designgrund:** Digital klarhet 1.0, B-034

Den återanvändbara A4-mallen finns i
[`src/reporting/template.py`](../src/reporting/template.py).
Den innehåller sidhuvud, sidfot, sidnummer, rubriker, brödtext, nyckeltalskort,
tabeller, placering av vektordiagram och ett valfritt omslag. Färger,
designversion och brödtextstorlek läses från den gemensamma
[tokenfilen](../src/design/digital_clarity.tokens.json).

Rapportens fakta, beräkningar, diagramserier och redaktionella kolumnbredder
ägs av användaren av mallen. [Agentnyttjandeexemplet](exempel/README.md) visar
hur den används för en fullständig rapport. Dess extra seriefärger hör till
exemplet och utökar inte den gemensamma paletten.

Detta är lokal rapportgenerering. Dokumentgateway, agentverktyg,
genereringsskill, kundbrev, presentationer och en generell Markdown-konverterare
återstår. Extern inlämning eller publicering följer ordinarie godkännanden.

## Beroenden och typsnitt

`reportlab` ingår i projektets vanliga beroenden. Installera projektet med
`python -m pip install -e ".[dev]"` för utveckling och tester.

För den ordinarie designen registreras lokala, statiska DM Sans-filer med
`register_dm_sans(font_dir)`: `DM-Sans-Regular.ttf`, `DM-Sans-Medium.ttf` och
`DM-Sans-Bold.ttf`. Saknade filer ger ett tydligt fel; ingen nedladdning eller
tyst ersättning görs. Fontfiler ingår inte i repot.

`Fonts.helvetica()` väljer uttryckligen ReportLabs inbyggda Helvetica och
Helvetica Bold. Det gör att tester och tekniska prov kan köras utan fontfiler.
Det valet ändrar textmått och radbrytningar och ska framgå när en sådan export
levereras. Samma `Fonts` ska användas i rapporten och diagrammens `ChartStyle`.

## Minsta användning

Koden körs i en installerad projektmiljö. Produktionsrapporter använder normalt
`fonts = register_dm_sans(Path("tmp/pdfs/fonts"))`; här väljs inbyggda typsnitt
för att exemplet ska gå att prova utan externa filer.

```python
from pathlib import Path

from reportlab.graphics.shapes import Drawing
from reporting.template import C, CW, ChartStyle, Fonts, Report, ReportMetadata

fonts = Fonts.helvetica()
style = ChartStyle(fonts)
chart = Drawing(CW, 90)
style.line(chart, 0, 20, CW, 20)
style.rect(chart, 0, 20, 120, 35, C["brand"])
style.text(chart, 130, 30, "120 uppdrag", bold=True)
style.legend(chart, [("Uppdrag", C["brand"])], 5)

content = """<!-- page: overview | 01 / ÖVERBLICK | Månadens resultat -->
**Slutsats:** Ett illustrativt resultat, med källa och antaganden nedan.

<!-- kpis: summary -->

## Underlag

| Mått | Värde |
| --- | ---: |
| Uppdrag | 120 |

![Uppdrag](figures/volume.svg)

- Källa: syntetiskt exempel. Period: september 2026.
"""

path = Path("output/pdf/manadsrapport.pdf")
path.parent.mkdir(parents=True, exist_ok=True)
report = Report(path, ReportMetadata(
    title="Månadsrapport",
    header="SEPTEMBER 2026",
    footer="UTKAST / SYNTETISKT UNDERLAG / HELVETICA",
), fonts=fonts)
report.render(content, drawings={"volume": chart},
              kpis=[("Uppdrag", "120", "Syntetiskt underlag")])
```

## Innehåll och layout

- `ReportMetadata` styr PDF-metadata, avsändare, sidhuvud och sidfot.
- Varje sida börjar med `<!-- page: unikt-id | överrubrik | titel -->`.
  Mallen skapar bokmärken och sidnummer. `render()` sparar PDF-filen.
- Brödtext, `**fetstil**`, `## underrubriker`, enkla `-`-listor och enkla
  pipe-tabeller stöds. HTML behandlas som text. Detta är en avgränsad delmängd
  av Markdown; länkar, nästlade listor och escaped pipe-tecken i tabellceller
  har ingen särskild tolkning.
- `<!-- kpis: summary -->` placerar anroparens lista med
  `(etikett, värde, kommentar)`. Direktanropet `report.kpis(items, columns=3)`
  stöder en till tre kolumner och valfritt antal rader som ryms på sidan.
- Tabeller får lika breda kolumner som standard och numeriska celler högerställs.
  `report.table(lines, widths=[...])` anger bredder i punkter, med summan `CW`.
  `render(..., table_widths=callback)` låter rapporten välja bredder från
  rubrikcellerna, som i agentnyttjandeexemplet.
- `![Beskrivning](figures/nyckel.svg)` placerar motsvarande `Drawing` från
  `drawings`. Ingen bildfil läses av PDF-mallen. `ChartStyle` ger gemensam text,
  stödlinje, rektangel och teckenförklaring; data, skalor och enheter anges av
  rapporten. SVG-export görs separat med ReportLabs `renderSVG`.
- `cover` är reserverat sid-id för det valfria omslaget. `Cover` skickas till
  `render(..., cover=...)` och innehåller all omslagstext, en till tre titelrader,
  ett framhävt mått och tre sammanfattande mått. Se exemplet för fälten.

Mallen använder fasta A4-marginaler och explicita sidbrytningar. Innehåll som
når sidfoten ger `ValueError`; lägg då till en sida eller korta innehållet.
Tabeller delas inte automatiskt. Nyckeltal, sidhuvud och omslagsfält behöver
korta texter som passar respektive yta. Kontrollera alltid slutlig export
visuellt, särskilt efter byte av typsnitt eller innehåll.

`report.audit` visar sid-id, sidnummer och återstående utrymme ovanför sidfoten.
Det är en layoutkontroll, inte en faktagranskning.

## Tester och regression

Kör `python -m pytest tests/test_reporting_template.py tests/test_reporting_agent_usage_example.py`.
Testerna använder inbyggda typsnitt och verifierar PDF/SVG, en fristående rapports
komponenter, formatfel, utrymmesgränser och hela exempelrapportens 16 sidor.
Exemplets Markdown och layout jämförs med resultatet före utbrytningen.

Vid utbrytningen jämfördes även ordinarie DM Sans-export före och efter:
PDF, Markdown och samtliga tio SVG-diagram gav samma resultat.
