# Projekt 3: Kundportal

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, förslag B-024).

## Scope

Låtsas-hemsida där en försäkrad kan logga in och se sin pension: saldo, status, vilka förmåner
försäkringen innehåller (ålderspension, TGL, familjeskydd, återbetalningsskydd m.m.), samt pausa
eller skjuta upp sin utbetalning.

## Status

🔲 Ej påbörjat. Byggs efter handläggar-UI:t (projekt 1) enligt B-020, ovanpå samma backend.

## Beroenden

- Samma FastAPI-backend som projekt 1 (B-020) – API:t ska redan vara designat för två klienter
- Uttags-/utbetalningslogik (pausa/skjuta upp) finns inte än – del av detta projekts scope
- Endast de förmånstyper som faktiskt finns i datamodellen kan visas (TGL/familjeskydd är
  förberedda men inte implementerade, se B-022)

## Befintlig grund i repot

- B-020 (gemensam backend för handläggare och kund)
- B-022 (försäkringsmodell: policies → policy_benefits → policy_states)

## Öppna designfrågor

- Kundautentisering – vad räcker för en sandbox?
- Vilka förmånstyper ska prioriteras för v1 (bara ålderspension, eller även TGL/familjeskydd)?
