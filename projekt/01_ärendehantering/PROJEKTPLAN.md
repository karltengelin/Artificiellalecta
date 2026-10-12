# Projekt 1: Ärendehantering & handläggar-UI

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, B-024).

## Scope

Ett gränssnitt där en handläggare kan se och hantera ärenden, och en backend som gör att handläggningen
faktiskt påverkar systemen och databaserna bakom: policys, förmåner, tillståndsperioder och premier.

## Status

🟡 **Handläggar-UI v1 byggt (Fas 4, 2026-10-12)**, lokalt och utan inloggning. Ärenden (`cases`), inbyggd
Claude och handläggaragent återstår. Byggs enligt B-020 före kundportalen (projekt 3).

Handläggaren kan i v1:
- söka en försäkrad på personnummer eller försäkringsnummer och se översikt, löneunderlag, premiehistorik
  och händelser;
- ansluta en ny anställd och registrera en arbetsgivare;
- ändra aktuell lön och kontaktuppgifter;
- registrera löneunderlag, sätta fribrev och rätta premier;
- godkänna eller avslå agentförslag och läsa händelseloggen.

Allt går via tjänstelagret och loggas. Beskrivning: `02_system/handläggar-ui.md`.

| Steg | Innehåll | Status |
|---|---|---|
| S1 | Grund, sök, översikt, löneunderlag, premiehistorik | ✅ |
| S2 | Formulär för de befintliga skrivoperationerna | ✅ |
| S3 | Godkännandekö och händelselogg | ✅ |
| S4 | Designstopp: nya operationer, se [OPERATIONER_BESLUTSFORSLAG.md](OPERATIONER_BESLUTSFORSLAG.md) | ✅ Godkänt, beslutsnumret sätts av operatören |
| S5 | Anslutning, aktuell lön, kontaktuppgifter, arbetsgivare | ✅ |
| S6 | Skarp verifiering i Lakebase | Väntar på backup och operatörens OK |

## Beroenden

- **Tjänstelagret (Fas 1f, B-028).** UI:t anropar bara dess operationer. Se `02_system/tjänstelager.md`.
- **Fas 3 (AI-abstraktionslagret, B-009)** ✅ byggdes 2026-10-11 i `src/ai/`.
  - Den inbyggda Claude-chatten och handläggaragenten kräver dessutom harness (Fas 3b). Harness byggs
    efter UI:t (B-028), se `02_system/agentekosystem.md` §12 och `ATT_GORA.md`.
- **`cases`-tabellen** finns inte än. Att definiera den ingår i det här projektets scope (jfr `databasschema.md`).
  `OperationContext.case_id` finns redan i tjänstelagret.

## Befintlig grund i repot

- Kod: `src/web/` (FastAPI + Jinja2 + HTMX) och `src/services/` (tjänstelagret)
- Start: `python scripts/web/start_ui.py`, och `.claude/launch.json` i Claude-appen
- Tester: `tests/test_web_*.py`, plus tjänstelagrets tester
- Beslut: B-020 (handläggar-UI före kundportal), B-017 (människa som fullständig operatör), B-028 (tjänstelager),
  B-030 (de första skrivoperationerna)
- Datamodell: `02_system/databasschema.md`, `src/models/`
- AI-lager och agentramverk: `02_system/ai_abstraktion.md`, `02_system/agentekosystem.md` (team `forsakring`)

## Nästa steg

- S6, skarp verifiering i Lakebase, efter backup och OK.
- Följdpunkterna i `ATT_GORA.md` under Fas 4:
  - anställningshistorik
  - lönehistorik
  - namnbyte
  - arbetsgivarens uppgifter och avslut
  - försäkringsbesked
  - interna id:n i adresserna
- `cases`-tabell och ärendeflöde, tillsammans med handläggaragenten (Fas 5).
- Inbyggd Claude efter harness (Fas 3b).

## Öppna designfrågor

Se `ATT_GORA.md` 🔵:
- **Sessionshistorik** för chatten.
- **Filrättigheter.**
- **Autentisering.** I v1 körs UI:t bara lokalt utan inloggning, och verklig autentisering behövs före
  kundportalen.
- **Delad backend med kundportalen.** Tjänstelagret är redan gemensamt.
