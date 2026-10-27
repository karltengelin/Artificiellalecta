# Designspecifikation – Digital klarhet

**Version:** 1.0 | **Datum:** 2026-10-24 | **Beslut:** B-034

## Syfte och tillämpning

Alla bolagets visuella leveranser ska kännas som Artificiellalecta, oavsett vilken
agent, avdelning eller människa som tar fram dem. Samma grund används för webb,
handläggning, rapporter, dokumentation och slides. Informationsmängd och disposition
anpassas till mottagaren och formatet.

Valet gäller formspråket och denna första designgrund. Det ändrar inte affärsregler,
behörigheter, teknisk webbarkitektur eller kraven på godkännande av externa handlingar.

## Visuell karaktär

- Ljusa, rena innehållsytor på en svagt tonad bakgrund.
- Indigo som igenkänning, aktiv markering och huvudfärg i diagram.
- Mjukare hörn, tydlig gruppering och gott om luft.
- Tydliga rubriker, läsbara tabeller och återhållsam dekoration.
- Mörkt indigo kan användas för presentationsbilder och särskilt framhävda avsnitt.

Den valda [visuella referensen](digital_klarhet.html) visar samma uttryck i tre
format. Uppgifterna där är exempeldata och får inte användas som rapportunderlag.

## Färger

Grundvärdena finns i [tokenfilen](../src/design/digital_clarity.tokens.json).
Tabellen beskriver deras användning i det ljusa grundutförandet.

| Roll | Token | Värde | Användning |
|---|---|---|---|
| Indigo | `color.brand` | `#6951CF` | Primär handling, markör, huvudserie i diagram |
| Länk/aktiv text | `color.link` | `#5E42C6` | Länkar och aktiv navigering på ljusa ytor |
| Huvudtext | `color.text` | `#252440` | Rubriker, brödtext och värden |
| Sekundär text | `color.text_muted` | `#65627D` | Metadata, källor, etiketter och hjälpinformation |
| Bakgrund | `color.background` | `#EEEDF6` | Sidans bakgrund och lugna sekundära ytor |
| Innehållsyta | `color.surface` | `#FFFFFF` | Dokument, formulär och huvudsakligt innehåll |
| Ljus indigo | `color.accent_soft` | `#EEEBFF` | Utvalda nyckeltal och diskreta markeringar |
| Skiljelinje | `color.border` | `#DEDCED` | Diskreta avgränsningar; används inte som enda fokusmarkering |

För mörka presentationsytor används `presentation_dark`: bakgrund `#252440`,
huvudtext `#F4F2FF`, sekundär text `#C4BFD8`, framhävt värde `#D2C5FF` och
diagram `#A991F2`. Dessa är avsedda parningar, inte färger att blanda fritt mellan
ljusa och mörka ytor. Ljust tema är grundutförandet för dokument och webb;
ett komplett mörkt webbtema prövas som en egen införandeuppgift.

Status har en annan uppgift än varumärkesfärgen. Klart, varning och fel ska ha
stabila betydelser, med text eller symbol utöver färg. Startvärden finns under
`status` i tokenfilen. En varning får inte ges indigo enbart för att passa profilen.

## Typografi och ordmärke

**DM Sans** används för rubriker, brödtext, tabeller och ordmärket Artificiellalecta.
Reserv är `system-ui`, därefter `Segoe UI` och generisk sans-serif. Normal text har
vikt 400, etiketter 500 och rubriker 700; 600 kan användas för viktiga tabellvärden.
Belopp i tabeller högerställs och använder tabellsiffror.

Startvärden vid implementation:

| Format | Brödtext | Rubrik | Princip |
|---|---|---|---|
| Webb | 16 px, radavstånd 1,5 | 24–36 px | Text kan förstoras och flödar om på smala skärmar |
| Rapport/A4 | 11 pt, radavstånd 1,5 | 24–32 pt | Metadata minst 9 pt; tabeller får egna sidor vid behov |
| Presentation/16:9 | 20–24 pt | 32–40 pt | En huvudpoäng per bild; få, läsbara värden |

Storlekarna är startvärden för riktiga mallar. De små förhandsvisningarna i
referensen är inte en specifikation av slutlig tryck- eller presentationsstorlek.
Typsnitt ska finnas i exportmiljön innan dokument genereras; vald reserv ska synas
i leveranskontrollen om DM Sans saknas. Fontfiler paketeras separat vid behov.

Ordmärket skrivs **Artificiellalecta**. Den lilla indigorutan i referensen kan
användas som enkel grafisk markör i v1. Ett komplett logotyppaket med vektororiginal,
frizon och exportvarianter är ett senare arbete.

## Layout, komponenter och bildspråk

Avstånd bygger på skalan 4, 8, 12, 16, 24, 32, 48 och 64. Gruppera det som hör
ihop; använd större mellanrum mellan avsnitt än mellan etikett och värde.
Tokenfilens avstånd anges i px för webb och översätts proportionerligt i dokument.

- Kontroller: cirka 8 px hörnradie. Kort: 12 px. Större presentationsytor: 14 px.
- Formulär har tydliga etiketter, hjälpinformation, fel vid rätt fält och synlig fokusmarkering.
- Tabeller har lugna avgränsningar, tydliga kolumnrubriker och högerställda belopp med enhet.
- Nyckeltal får ljus indigo eller neutral bakgrund; betona få värden åt gången.
- Ikoner är enkla och konsekventa. Betydelsen ska också framgå av text.
- Bilder används när de bidrar till innehållet. Grafer och typografi är primära
  bärare i rapporter; dekorativa effekter får inte tränga undan information.

Webbkomponenter ska återanvändas inom FastAPI/Jinja2/HTMX. Designspråket kräver
inget nytt frontendramverk. Databricks-dashboarden följer grunden inom plattformens
möjligheter; begränsningar dokumenteras enligt B-029.

## Diagram och redaktionell struktur

Indigo är huvudserie. Bakgrund, axlar och stödlinjer hålls lugna. Ytterligare
serier får konsekventa, läsbara färger och skiljs även med etiketter eller linjestil;
en utökad kategoripalett fastställs när den behövs. Gradienter, 3D och dekorativa
ramar runt staplar ingår inte i grundutförandet.

Visa enheter, period, källa och antaganden. Skilj utfall från prognos och scenario.
Saknat underlag visas som ej beräknat, aldrig som noll. Diagrammens skala får inte
förändra innebörden i underlaget.

Rapporter har svar/slutsats först, därefter underlag och källor,
antaganden/osäkerhet och eventuella nästa steg. Presentationer använder samma
innehållslogik med en huvudpoäng per bild. Dokumentmetadata omfattar titel,
datum/period, version, ansvarig och underlag; formella dokument följer även sin
styrdokumentsmall.

## Användning av människor och agenter

1. Läs denna specifikation och återanvänd tokenfilen och den aktuella mallen.
2. Domänagenten ansvarar för fakta, beräkningar, källor och mottagaranpassning.
3. De planerade skillsen `create_documentation` och `create_presentation` använder
   samma designversion, oavsett team. Kommunikation äger mallarna; utveckling
   ansvarar för teknisk generering, enligt `02_system/agentekosystem.md` §5.5.
4. Kontrollera resultatet visuellt i det slutliga formatet: text, sidbrytningar,
   tabeller, diagram, kontrast, fokus och smala skärmar. Normal webbtext ska nå
   minst 4,5:1 i kontrast och stor text minst 3:1. Den faktiska komponenten prövas
   före införande; färgpaletten ensam garanterar inte tillgänglighet.
5. Spara design-/mallversion med leveransen. Ändra specifikation och tokenfil
   tillsammans när designgrunden utvecklas; bevara versionsspåret.

Den bevarade HTML-referensen är historiskt jämförelsematerial, med egna frysta
stilvärden. Produktionsmallar ska använda den gemensamma tokenfilen, så att den
historiska referensen inte blir en andra källa för dagens värden.

## Införande och kvarstående arbete

Vald riktning, specifikation v1.0 och första tokenfil är dokumenterade. En första
[återanvändbar A4-rapportmall](rapportmall.md) med exempelrapport och en
[16:9-presentationsmall](presentationsmall.md) med syntetiskt exempel finns.
Övriga mallar, gemensamma skills, fullständigt logotyppaket och anpassning
av befintliga gränssnitt återstår i `ATT_GORA.md`. Införandet sker stegvis med
en representativ handläggarvy, en rapport och en presentation som gemensam kontroll.

| Version | Datum | Ändring |
|---|---|---|
| 1.0 | 2026-10-24 | Första dokumenterade designgrunden efter operatörens val (B-034). |
