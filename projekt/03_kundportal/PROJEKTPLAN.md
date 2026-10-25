# Projekt 3: Kundportal

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, B-024).

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
- Uttags-/utbetalningslogik (pausa/skjuta upp) finns inte än. Behovet ingår i portalens scope,
  men motorerna måste samordnas som gemensamma försäkringsoperationer för handläggare, agent
  och portal; portalbygget får inte få en separat implementation av produktreglerna
- Endast ålderspensionsförmånen (`retirement_dc`) ingår i portalens produktfunktioner.
  TGL/familjeskydd är tekniskt förberedda i datamodellen (B-022), men ingår inte i uppdraget

## Befintlig grund i repot

- B-002/B-021 (produktscope och produktförenklingar)
- B-020 (gemensam backend för handläggare och kund)
- B-022 (försäkringsmodell: policies → policy_benefits → policy_states)

## Öppna designfrågor

- Avgränsa portalens gränssnitt mot det föreslagna paket B i
  [processöversikten](../../01_domän/processer_översikt.md) (V-04–06).
  Byggansvar och kontrakt stäms av med projekt 1/6 före start. En intern månadssimulering
  kan använda definierade kundmeddelanden innan portalen finns (S-03).

- Kundautentisering – vad räcker för en sandbox?
- Vilka uppgifter om ålderspensionen ska visas i första versionen?
