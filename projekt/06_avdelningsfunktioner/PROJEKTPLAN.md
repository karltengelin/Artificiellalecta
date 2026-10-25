# Projekt 6: Avdelningsfunktioner

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, B-024).

## Scope

Bygga ut funktioner för bolagets övriga avdelningar (se "Bolagets funktionsområden",
MASTER_CONTEXT §4), i första hand en **aktuariell modul** där agenter kan hantera premiesättning
utifrån krav och koppla till regelverk från Finansinspektionen. Omfattar både att förstå/tolka
regelverk och svensk lag, och att organisera låtsasbolaget (avdelningar, mandat) så det stämmer
överens.

## Status

🔲 Ej påbörjat.

## Beroenden

- Delar av tolkningsarbetet överlappar projekt 4 (produktregelverk) – avstäm innan parallellt
  arbete påbörjas (jfr AGENTS.md §4.2)

## Befintlig grund i repot

- "Bolagets funktionsområden"-tabellen, `MASTER_CONTEXT.md` §4
- `02_system/agentkarta.md` (tio agentskelett, kan redan innehålla tankar om avdelningsindelning)

## Öppna designfrågor

### Konkretisering för månadssimulering

Behoven är samlade i [processöversikten](../../01_domän/processer_översikt.md).
De här delarna ska avgränsas till bygguppdrag innan en full pensionsmånad kan verifieras:

- **V-10, ekonomi:** bokföring och avstämningsunderlag för premier, placeringar, pension,
  avgifter, skatt och eget kapital; ingående balans och månadsbokslut.
- **V-11, aktuarie/risk:** garanti-/reserv-/FTA-/ALM- och finansieringskontroller med
  verifierade motorer. Den dokumenterade SIM-grunden är metodunderlag, inte färdig beräkningskod.
- **V-12, rapportering:** välj tillsammans med projekt 2 första interna månadsrapporten,
  därefter tillämpliga skatte-/tillsyns-/partsrapporter med bestämd mottagare och period.
- **Paket B och S-04:** föreslagen samordning med projekt 1 och 5 för pensions-/månadsavräkning
  och ett ekonomiskt avstämt startbestånd. Byggansvaret behöver fastställas vid designstart.

Målbilden ovan innebär inga nya agentmandat, rapporteringskrav eller flytt av beslutat projektscope.

**Leverans till VD-överblicken (2026-10-25):** projekt 6:s verifierade ekonomi-,
värderings- och riskunderlag ska genom projekt 2:s gemensamma mått försörja
[operatörscentralen](../10_operatörscentral/PROJEKTPLAN.md). Konsolidering kräver
en definierad fördelnings-/återbäringsmodell och rätt värderingsunderlag. Projekt 10
visar saknade mått som ej beräknade och bygger inga parallella domänmotorer.

### Organisation

- Ett delprojekt per avdelning, eller en gemensam modul som växer per avdelning? (Karl nämner att
  det kan behövas ett projekt per viktig avdelning)
- Hur mappas verkliga tjänstepensionsbolags avdelningsstruktur till det simulerade bolaget?
