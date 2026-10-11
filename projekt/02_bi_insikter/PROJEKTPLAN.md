# Projekt 2: BI & insikter

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, förslag B-024).

## Scope

Koppla ihop försäkringssystemet och de underliggande databasmodellerna till ett sätt att ta ut
indikatorer och nyckeltal, och göra det möjligt för en agent att svara på frågor i datat
(t.ex. "hur påverkar en regelverksändring beståndet?").

## Status

🔲 Ej påbörjat. Tilltänkt att använda Databricks (redan vald databasplattform, B-018) för
lagring/analys av insiktsdata, men arkitekturen är inte bestämd ännu – ska bollas med Karl innan
något byggs.

## Beroenden

- Data att analysera finns redan (Fas 1: policys, premier). Fler delprojekt (5 kapitalförvaltning,
  1 ärendehantering) genererar mer data att koppla in efter hand.

## Befintlig grund i repot

- B-018 (Databricks Lakebase som databas)
- `02_system/databasschema.md`

## Öppna designfrågor

- Hur används Databricks konkret för BI – separat lagringslager, direkta queries mot Lakebase,
  eller något annat?
- Hur exponeras insikter för en agent (verktyg/skill vs. färdiga rapporter)?
- Relation till det tvärgående agentekosystemet (`02_system/agentekosystem.md`, kommer) – är
  BI-agenten en egen agent eller en skill på en befintlig?
