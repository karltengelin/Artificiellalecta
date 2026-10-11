# Projekt 1: Ärendehantering & handläggar-UI

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, B-024).

## Scope

Ett gränssnitt där en handläggare kan gå in och se/hantera ärenden, samt backend som gör att
handläggning faktiskt påverkar systemen och de underliggande databaserna (policys, förmåner,
tillståndsperioder, premier).

## Status

🟡 Utredning klar (se `ATT_GORA.md` 🔵), inget byggt ännu. Byggs enligt B-020 före kundportalen
(projekt 3).

## Beroenden

- Fas 3 (AI-abstraktionslager, B-009) ✅ byggd 2026-10-11 i `src/ai/`. Agentdelen (handläggaragent) kräver dessutom harness – Fas 3b enligt B-026, se `02_system/agentekosystem.md` §12 och `ATT_GORA.md`
- `cases`-tabell finns inte än – del av detta projekts scope att definiera (jfr `databasschema.md`)

## Befintlig grund i repot

- Utredning: `ATT_GORA.md` 🔵 (admin-UI med inbyggd Claude)
- Beslut: B-020 (handläggar-UI före kundportal), B-017 (människa som fullständig operatör)
- Datamodell: `02_system/databasschema.md`, `src/models/`
- AI-lager och agentramverk: `02_system/ai_abstraktion.md`, `02_system/agentekosystem.md` (team `forsakring`)

## Öppna designfrågor

Se `ATT_GORA.md` 🔵 – sessionshistorik, filrättigheter, autentisering, delad backend med
kundportalen.
