# Projekt 7: Kundchattbot

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, B-024).

## Scope

En chattbot, åtkomlig via kundwebben (projekt 3), som har koll på regelverk och försäkringsvillkor
och kan svara på vad kunden får/inte får göra med sin försäkring.

## Status

🔲 Ej påbörjat. Förutsätter kundportalen (projekt 3) och produktregelverket (projekt 4).

## Beroenden

- Kundportal (projekt 3) för att ha en yta att visa chattboten i
- Produktregelverk & villkor (projekt 4) som kunskapskälla

## Befintlig grund i repot

- Inget specifikt ännu – bygger vidare på modellagnostiska abstraktionslagret (B-009, `src/ai/`) och
  skillsbiblioteket (B-007)

## Öppna designfrågor

- Hur mycket av regelverkstolkningen (projekt 4) ska chattboten ha direkt tillgång till kontra
  via en skill som anropar compliance-agenten (B-011)?
