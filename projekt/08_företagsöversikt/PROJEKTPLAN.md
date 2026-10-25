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

🟡 Första version 2026-10-12; uppdaterad 2026-10-24:
[foretagsoversikt.html](foretagsoversikt.html), läget på main @ a2cfc60.
Öppnas direkt i webbläsaren. Den innehåller en klickbar bolagskarta, delprojektens status,
byggordning, tjänstelagrets flöde, regelkedjan, datamodellen, agentekosystemet, kod, skript
och luckor. Sidan är statisk och uppdateras manuellt; siffror och status gäller per datumet i
sidhuvudet. Naturligt att uppdatera i takt med att övriga delprojekt tar form – annars blir
översikten inaktuell.

Uppdateringen 24 oktober omfattar handläggar-UI v1, samtliga 15 tjänsteoperationer,
harness 3b-1–6 och den införda databasrollen, kapitalets beslutsutkast och lokala
modeller samt kod- och testinventeringen. Byggt lokalt, infört i Lakebase och
återstående arbete anges separat. Källor och avgränsningar finns i
[uppdateringsunderlaget](UPPDATERING_2026-10-24.md).

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
