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

🟡 Första version 2026-10-12. [Företagsöversikten](foretagsoversikt.html) är uppdaterad
2026-11-21 mot main @ 9001d0e. Öppna sidan direkt i webbläsaren. Bolagskartan och de
elva delprojekten visar arbetsytor, arkitektur, datamodell, agentmandat, byggstatus och
nästa steg. Sidan är en statisk ögonblicksbild med länkar till projektplaner,
beslutslogg och dokumenterad verifiering.

Novemberuppdateringen beskriver det körda premieflödet, kapital- och garantijournalen,
månadsstängningen och kvarstående pensionssteg. Den följer bytet till Fråga bolagets
fritextpilot, uppdragsarkivet och den lokala agentloopen enligt B-049. Sidan följer
Digital klarhet och beskriver webbens kompakta plattformsmeny från 21 november.
Dokumenterade Lakebase-resultat och lokal demo anges med respektive miljö.

[Uppdateringsunderlaget för 25 oktober](UPPDATERING_2026-10-25.md) och
[underlaget för 24 oktober](UPPDATERING_2026-10-24.md) bevaras som historik.

En fristående leveranskopia finns även i projektroten
([foretagsoversikt.html](../../foretagsoversikt.html)). Håll kopiornas innehåll
synkroniserat och anpassa källänkarna till respektive sökväg.

## Beroenden

Ingen hård beroende, men innehållet blir mer värdefullt ju fler av projekt 1–7 som är igång.

## Befintlig grund i repot

- `02_system/agentkarta.md`, `02_system/databasschema.md` – källmaterial att visualisera
- MASTER_CONTEXT.md själv är den nuvarande "företagsöversikten" i textform

## Öppna designfrågor

- Statisk sida som uppdateras manuellt, eller genereras den ur repots dokument/beslutslogg?
