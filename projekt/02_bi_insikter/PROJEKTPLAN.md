# Projekt 2: BI & insikter

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, B-024).

## Scope

Koppla ihop försäkringssystemet och de underliggande databasmodellerna till ett sätt att ta ut
indikatorer och nyckeltal, och göra det möjligt för en agent att svara på frågor i datat
(t.ex. "hur påverkar en regelverksändring beståndet?").

Inriktningen är en gemensam analys- och rapporteringsförmåga: definierade mått och vyer
som försörjer operatörens dashboard, Genie/agentfrågor och kontrollerade rapporteringsunderlag.
Regeländringar är ett användningsfall bland flera. Se
[DASHBOARD_DESIGN.md](DASHBOARD_DESIGN.md) för första förslaget till frågor, mått och dataflöde.

## Status

🟡 Första avgränsade analysen implementerad och mergad till main: premieeffekt av ett
hypotetiskt IBB för en vald månad. Karl har godkänt detta BI-spår parallellt med Claude Codes
tjänstearbete. Ren beräkning, offline-backup och Markdownrapport; inga databasskrivningar.

Se [ANALYSDESIGN.md](ANALYSDESIGN.md) för antaganden, datakvalitet och fortsatt integration,
och [EXEMPELANALYS.md](EXEMPELANALYS.md) för ett helt syntetiskt exempel.
Dashboarden i Databricks AI/BI, gemensamma mått och Genie för insikter är beslutad inriktning
(B-029). Detaljerad dataväg, historik, lagringslösning och agentintegration återstår.
Databricks är vald databasplattform (B-018); inget separat BI-lager väljs här.
Dashboard och Genie-integration är ännu inte driftsatta; dashboardens konkreta mått är förslag.

### Nästa steg

- Fastställ dashboardens måttdefinitioner, värderingsgrunder och första rapportmottagare.
- Verifiera Unity Catalog, SQL Warehouse och Genie-stöd i den faktiska Databricks-miljön.
- Integrera läsning genom gemensamma tjänster när Claudes T3/T4-arbete är integrerat.
- Fastställ historisk arbetsgivarkoppling och löneunderlagens betydelse vid flera försäkringar.
- Utöka till hela beståndet, månadstrender och kvalitetskontroller som inkluderar saknade premier.
- Bestäm åtkomst och rapportkontrakt innan insikter exponeras för agenter.
- Visualisera flöden och ansvar tillsammans med [Projekt 9: Processkartor](../09_processkartor/PROJEKTPLAN.md).

## Beroenden

- Data att analysera finns redan (Fas 1: policys, premier). Fler delprojekt (5 kapitalförvaltning,
  1 ärendehantering) genererar mer data att koppla in efter hand.

## Befintlig grund i repot

- B-018 (Databricks Lakebase som databas)
- B-029 (Databricks AI/BI-dashboard, gemensamma mått och Genie)
- `02_system/databasschema.md`

## Öppna designfrågor

- Hur används Databricks konkret för BI – separat lagringslager, direkta queries mot Lakebase,
  eller något annat?
- Hur exponeras insikter för en agent (verktyg/skill vs. färdiga rapporter)?
- Relation till det tvärgående agentekosystemet (`02_system/agentekosystem.md`) – är
  BI-agenten en egen agent eller en skill på en befintlig? Ekosystemramverket (B-026) lutar mot
  en skill-pod `bestand` (aggregerade nyckeltal) + Data scientist-agenten i team `aktuarie`.
