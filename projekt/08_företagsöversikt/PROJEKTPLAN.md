# Projekt 8: Företagsöversikt

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, B-024).

## Scope

En HTML-sida (eller liknande) för Karl som projektledare – en drillbar översikt av hela
låtsasbolagets uppbyggnad: övergripande områden att gå in i på djupet, förklaringar och enkla
skisser över hur systemen hänger ihop. Detta är ett verktyg åt projektledaren, inte en del av det
simulerade bolaget självt.

**Gräns mot projekt 10 (2026-10-25):** [operatörscentralen](../10_operatörscentral/PROJEKTPLAN.md)
är den planerade arbetsytan för Karl som VD, med löpande bolagsläge, team,
agentkostnader, datafrågor och styrning. Projekt 8 behåller projektledarens
förklarande karta över organisation, system, byggstatus och beroenden.
Den befintliga statiska HTML-översikten görs inte om till ett driftsgränssnitt.

## Status

🟡 Första version 2026-10-12; senast uppdaterad 2026-10-25:
[foretagsoversikt.html](foretagsoversikt.html), läget på main @ 5fd10ab.
Öppnas direkt i webbläsaren. Den innehåller en klickbar bolagskarta, delprojektens status,
byggordning, tjänstelagrets flöde, regelkedjan, datamodellen, agentekosystemet, kod, skript
och luckor. Sidan är statisk och uppdateras manuellt; siffror och status gäller per datumet i
sidhuvudet. Naturligt att uppdatera i takt med att övriga delprojekt tar form – annars blir
översikten inaktuell.

**Uppdatering 25 oktober:** båda HTML-filerna visar nu 25 tjänsteoperationer,
tre agentprofiler, fem poddar och 13 mappade verktyg, ärendestödet, versionerade
produktparametrar och den lokala flödesmotorn. De tio delprojekten omfattar även
operatörscentralen och teamområdena. Diagram, detaljrutor, test- och kodinventering
skiljer byggt stöd från kvarstående verifiering och verksamhetsbygge.

B-037:s verksamhetsdrivna målbild styr beskrivningen. Ett visningsscenario är
inget eget byggmål; det avgränsade parameterflödet beskrivs med sina begränsningar.
HTML är fortsatt en daterad statisk ögonblicksbild, utan liveanslutning till
Lakebase. Grunddokumenten och projektplanerna är underlaget för senare ändringar.
Källor, verifiering och avgränsningar finns i
[uppdateringsunderlaget för 25 oktober](UPPDATERING_2026-10-25.md).
[Underlaget för 24 oktober](UPPDATERING_2026-10-24.md) bevaras som historik.

En fristående leveranskopia finns även i projektroten:
[foretagsoversikt.html](../../foretagsoversikt.html), på operatörens begäran.
Vid kommande uppdateringar ska båda HTML-filerna hållas synkroniserade;
rotkopians hänvisning till uppdateringsunderlaget utgår från projektroten.

## Beroenden

Ingen hård beroende, men innehållet blir mer värdefullt ju fler av projekt 1–7 som är igång.

## Befintlig grund i repot

- `02_system/agentkarta.md`, `02_system/databasschema.md` – källmaterial att visualisera
- MASTER_CONTEXT.md själv är den nuvarande "företagsöversikten" i textform

## Öppna designfrågor

- Statisk sida som uppdateras manuellt, eller genereras den ur repots dokument/beslutslogg?
