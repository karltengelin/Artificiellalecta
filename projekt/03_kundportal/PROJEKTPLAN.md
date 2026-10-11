# Projekt 3: Kundportal

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, förslag B-024).

## Scope

Låtsas-hemsida där en försäkrad kan logga in och se sin ITP1 ålderspension: saldo, status
och försäkringsuppgifter, samt pausa eller skjuta upp sin utbetalning.

Portalen omfattar endast ITP1 ålderspension enligt B-002. Sjukpension, TGL och familjeskydd
ingår inte; inte heller återbetalningsskydd i den beslutade produktversionen (B-021).
De tekniska förberedelserna i B-022 utökar inte produktscope. Fler förmånstyper får tas in
i portalen först efter ett nytt uttryckligt beslut om utökat scope och uppdaterade villkor.

## Status

🔲 Ej påbörjat. Byggs efter handläggar-UI:t (projekt 1) enligt B-020, ovanpå samma backend.

## Beroenden

- Samma FastAPI-backend som projekt 1 (B-020) – API:t ska redan vara designat för två klienter
- Uttags-/utbetalningslogik (pausa/skjuta upp) finns inte än – del av detta projekts scope
- Endast ålderspensionsförmånen (`retirement_dc`) ingår i portalens produktfunktioner.
  TGL/familjeskydd är tekniskt förberedda i datamodellen (B-022), men ingår inte i uppdraget

## Befintlig grund i repot

- B-002/B-021 (produktscope och produktförenklingar)
- B-020 (gemensam backend för handläggare och kund)
- B-022 (försäkringsmodell: policies → policy_benefits → policy_states)

## Öppna designfrågor

- Kundautentisering – vad räcker för en sandbox?
- Vilka uppgifter om ålderspensionen ska visas i första versionen?
