# Presentationsmall – Digital klarhet

**Mallversion:** 1.0 | **Designgrund:** Digital klarhet 1.0, B-034

Den återanvändbara 16:9-mallen finns i
[`src/reporting/presentation.py`](../src/reporting/presentation.py).
Den innehåller titelbild, innehållssida, nyckeltal, tabell och stapeldiagram.
[Exempelunderlaget](exempel/presentationsunderlag.md) visar samtliga fem
bildtyper med syntetiska värden;
[PDF-exemplet](../output/pdf/presentationsmall_exempel.pdf) är en genererad leverans.
Allt innehåll, inklusive metadata, nyckeltal och diagramvärden, redigeras i Markdown.

Detta är en lokal mall och ett körverktyg. Agentverktyg, gemensam genereringsskill,
dokumentgateway, externa konton och publicering ingår inte. Kundbrev, formella
dokumenttyper och en generell Markdown-konverterare återstår.

## Format- och verktygsval

**Markdown → PDF med befintliga ReportLab** väljs för version 1.0. Det ger
en fast 16:9-yta, inbäddad DM Sans och skarpa vektordiagram utan nya
projektberoenden. Befintliga PyYAML läser metadata. Bildstorleken är
960 × 540 punkter; förhållandet är exakt 16:9 och PDF-läsaren kan visa
presentationen i helskärm. PDF är leveransformat, Markdown är arbetsformat
enligt B-012.

En PPTX-mall skulle ge redigering direkt i PowerPoint men kräva en separat
exportimplementation och sannolikt ett nytt beroende. HTML skulle kräva en
separat layoutmotor för att återanvända rapportens font- och diagramhantering.
Inget av dessa format införs i denna avgränsning. PDF-exemplet har granskats som
renderade PDF-bilder, inte i PowerPoint. Animationer, anteckningsvy och
redigerbara PowerPoint-objekt ingår inte.

## Gemensam design och typsnitt

Mallen importerar `Fonts`, `register_dm_sans`, `ChartStyle`, `TOKENS`, `C`
och Markdown-fetstilshanteringen från rapportmallen. Tokenfilen
[`src/design/digital_clarity.tokens.json`](../src/design/digital_clarity.tokens.json)
är enda färgkälla. Ingen kategoripalett från agentnyttjandeexemplet används.

- Titelbild: `presentation_dark.background`, `text` och `text_muted`.
- Innehåll: `color.surface`, `text` och `text_muted`.
- Markör och diagramserie: `color.brand`; diagrammets stödlinjer: `color.border`.
- Nyckeltal och tabellhuvud: `color.accent_soft`; kortens radie hämtas från tokenfilen.
- Brödtext: `typography.presentation_body_pt` (24 pt), radavstånd från tokenfilen.
  Rubrik 36 pt, titelbild 40 pt, tabeller 20 pt, nyckeltalsvärden 38 pt.
  Diagrametiketter 18–20 pt, kortkommentarer 18 pt, källtext 12 pt, sidfot 11 pt.

Samma lokala statiska fontfiler som för rapportmallen används:
`DM-Sans-Regular.ttf`, `DM-Sans-Medium.ttf` och `DM-Sans-Bold.ttf`.
Lägg dem i `tmp/pdfs/fonts/` eller ange `--font-dir`. Saknade filer stoppar
exporten. Ingen font hämtas automatiskt, installeras globalt eller ersätts tyst.
Fontfiler ingår inte i repot. Statiska original finns hos
[Google Fonts](https://github.com/googlefonts/dm-fonts/tree/main/Sans/fonts/ttf);
originalens `DMSans-*.ttf` behöver ges filnamnen ovan för den befintliga
registreringsfunktionen.

`--helvetica` är ett uttryckligt alternativ för tester och tekniska prov.
Varje bild får då `HELVETICA` i sidfoten. Fontvalet påverkar textmått och
radbrytningar, så ordinarie export ska granskas på nytt med DM Sans.

## Återskapa exemplet

Installera projektets befintliga beroenden, exempelvis med
`python -m pip install -e ".[dev]"`. Kör från reporoten:

```powershell
python scripts/documentation/build_presentation.py 06_design/exempel/presentationsunderlag.md output/pdf/presentationsmall_exempel.pdf
```

Utan lokala fontfiler kan ett separat tekniskt prov skapas:

```powershell
python scripts/documentation/build_presentation.py 06_design/exempel/presentationsunderlag.md tmp/pdfs/presentationsprov_helvetica.pdf --helvetica
```

Inga databaser, modeller, externa bilder eller andra nätresurser läses.
Körverktyget skapar målmappen och skriver PDF-filen när alla bilder klarat
layoutkontrollen. Ett innehållsfel lämnar en befintlig målfil orörd.

## Markdown och layout

Källan börjar med YAML-metadata mellan två rader `---`. Exakt dessa fält krävs
som icke-tomma strängar: `title`, `period`, `date`, `version`, `author`, `source`.
Skriv datum och versionsnummer inom citattecken. `title` används i PDF-metadata;
övriga fält visas i den gemensamma ramen. `source` visas på varje bild.

Varje bild börjar med en egen rad:

```markdown
<!-- slide: unikt-id | content | En tydlig slutsats -->
**Slutsats:** Här följer ett kort svar.

- Ett avgränsat underlag.
- Ett nästa steg.

> Antagande eller osäkerhet som gäller den här bilden.
```

`unikt-id` börjar med en liten engelsk bokstav och fortsätter med små bokstäver,
siffror, bindestreck eller understreck. Alla id:n måste vara unika. Text före
första bildmarkören, okända bildtyper och tomma bilder stoppas. Bildrubriken
kommer från markören. Datum, innehållsversion, designversion, mallversion och
bildnummer visas i sidfoten. PDF:en får bokmärken för bildrubrikerna.

| Bildtyp | Innehåll efter markören | Användning och gräns |
|---|---|---|
| `title` | Korta stycken och valfria enkla listor | Mörk titelbild, rubrik högst två rader om texten ryms |
| `content` | Stycken, `**fetstil**` och enkla `- `-listor | Ljus innehållssida, en huvudpoäng per bild |
| `kpis` | Pipe-tabell med tre kolumner: etikett, värde, kommentar | En till tre datarader blir kort i en rad; håll texterna korta |
| `table` | Pipe-tabell med rubrikrad och separatorrad | En till fem lika breda kolumner; avslutande `:` i separatorn högerställer hela kolumnen |
| `chart` | Pipe-tabell med kategori och numeriskt värde | En serie, en till sex kategorier; värdekolumnens rubrik ska ange enhet |

Varje rad som börjar med `> ` flyttas till käll-/antagandeytan under innehållet.
Den ytan rymmer högst tre korta rader, inklusive den gemensamma källan. Tabeller
kräver inledande och avslutande pipe, icke-tomma celler och samma antal celler
i varje rad. Använd texten `ej beräknat` för saknade värden. Listblock ska ha
en listpunkt per rad; separera stycken med en tom rad.

Detta är en avgränsad Markdown-dialekt. HTML behandlas som text. Länkar,
nästlade listor, inlinekod och escaped pipe-tecken tolkas inte särskilt.
Bilder, kodblock och underrubriker stöds inte i textbilder. Diagram genereras
från tabellvärden, inte från bildreferenser eller filer. Rapportmallens
`<!-- page: ... -->`-markörer och presentationsmallens `slide`-markörer har
skilda layouter och kan inte användas omväxlande.

## Diagram, fakta och begränsningar

Stapeldiagrammet använder rapportens `ChartStyle` för text, staplar och
stödlinjer, med samma `Fonts` som resten av presentationen. Skalan börjar
vid noll och går till högsta kända värdet. Värden visas vid staplarna;
axeln använder decimalkomma. Bara ändliga, icke-negativa tal stöds i denna
bildtyp, med decimalpunkt eller decimalkomma och valfria mellanslag som
tusentalsavskiljare. Negativa värden, oändlighet och NaN stoppas.

`ej beräknat` visar en etikett utan stapel. Ett faktiskt nollvärde visas som
`0`. När alla värden saknas ritas ingen numerisk axel. När alla kända värden
är noll visas en skala från 0 till 1 för att undvika en kollapsad axel.
Prognos, scenario, utfall, period och antaganden ska framgå av rubrik eller
källtext. Det finns inga extra seriefärger eller automatiska prognostolkningar.

Mallen räknar inte fram verksamhetsmått och kontrollerar inte sakuppgifter.
Författaren ansvarar för fakta, samband och jämförbara perioder. Exemplet
använder 2,4, 2,7 och 3,0 Mkr: sammanlagt 8,1 Mkr och 25 % ökning från juli
till september. Testerna kontrollerar dessa samband separat från renderingen.

Innehåll får inte krympa automatiskt för att passa. För lång text, tabeller,
nyckeltalsfält, diagrametiketter eller metadata ger fel. Dela bilden eller
korta innehållet. Även en radbruten rubrik minskar det tillgängliga
innehållsutrymmet. `Presentation.audit` redovisar bild-id, typ, återstående
innehållshöjd och källtextens höjd efter lyckad export.

## Python-användning

```python
from pathlib import Path
from reporting.presentation import Presentation
from reporting.template import register_dm_sans

fonts = register_dm_sans(Path("tmp/pdfs/fonts"))
deck = Presentation(fonts=fonts)
output = Path("output/pdf/presentation.pdf")
output.parent.mkdir(parents=True, exist_ok=True)
deck.render(Path("06_design/exempel/presentationsunderlag.md").read_text(
    encoding="utf-8"
), output)
print(deck.audit)
```

## Tester och leveranskontroll

```powershell
python -m pytest tests/test_reporting_presentation.py tests/test_reporting_template.py tests/test_reporting_agent_usage_example.py
python scripts/testing/run_tests.py --suite reporting --run
```

Testerna använder inbyggda typsnitt. De verifierar verklig PDF-generering,
exakta 16:9-sidmått, alla fem layouter, metadata, bildnummer, bokmärken,
återskapbarhet, fristående innehåll och att rapportens komponenter återanvänds.
Felaktig Markdown, fel tabellstruktur, för stora komponenter, fontbrist,
diagramgränser och skillnaden mellan noll och saknade värden kontrolleras.
Testfilen ingår i testkatalogens `reporting`-grupp.

Vid leveransen 2026-10-27 renderades och granskades samtliga fem bilder med
både uttryckligen vald Helvetica och ordinarie DM Sans. Slutlig exempel-PDF
använder inbäddad DM Sans. Befintliga rapporttester, testurval och
körverktygens startkontroller ingår i regressionen. Layoutkontroll är inte
ett intyg om tillgänglig PDF-struktur eller faktagranskning. Kontrollera
alltid slutlig export visuellt efter innehålls- eller fontbyte.

| Version | Datum | Ändring |
|---|---|---|
| 1.0 | 2026-10-27 | Lokal Markdown → PDF-mall i 16:9 med fem bildtyper, gemensam design, syntetiskt exempel och tester. |
