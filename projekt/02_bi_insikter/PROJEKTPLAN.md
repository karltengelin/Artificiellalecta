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

**Samordning med projekt 10 (2026-10-25):** den planerade
[operatörscentralen](../10_operatörscentral/PROJEKTPLAN.md) samlar VD-överblick,
team/agentkostnader, frågor mot data och inriktningsbeslut. Projekt 2 äger
fortsatt BI-mått, historik och Databricks-dashboard enligt B-029. Samma granskade
mått försörjer central och fördjupning; konsolidering visas som ej beräknad tills
modellunderlaget finns. Rutinärenden och deras godkännanden ligger i specialistvyer.

## Status

🟡 Första avgränsade analysen implementerad och mergad till main: premieeffekt av ett
hypotetiskt IBB för en vald månad. Karl har godkänt detta BI-spår parallellt med Claude Codes
tjänstearbete. Ren beräkning, offline-backup och Markdownrapport; inga databasskrivningar.

Sedan Fas 3c finns dessutom `src/analytics/parameter_impact.py` och tjänsteoperationen
`estimate_parameter_change_impact`, monterad i podden `bestand` för Aktuarieagenten.
Den räknar godkända parameterändringars premieeffekt per år med aggregat och
sekretessgräns. Det är en återanvändbar analysgrund, inte samlad ekonomisk BI.

Se [ANALYSDESIGN.md](ANALYSDESIGN.md) för antaganden, datakvalitet och fortsatt integration,
och [EXEMPELANALYS.md](EXEMPELANALYS.md) för ett helt syntetiskt exempel.
Dashboarden i Databricks AI/BI, gemensamma mått och Genie för insikter är beslutad inriktning
(B-029). Detaljerad dataväg, historik, lagringslösning och agentintegration återstår.
Databricks är vald databasplattform (B-018); inget separat BI-lager väljs här.
Dashboard och Genie-integration är ännu inte driftsatta; dashboardens konkreta mått är förslag.

**2026-10-27: Datakontrakt för första fråge-/rapportkedjan** finns i
[DATAKONTRAKT_FRAGEKEDJA.md](DATAKONTRAKT_FRAGEKEDJA.md), med versionssatta
definitioner, operationsgränser, lokalt demofacit, avvikelseprov och rapportfält.
Första datavägen är **Lakebase via tjänstelagrets `get_company_metrics`**, med
definitionerna i `src/management/metrics.py`, samma som centralen. Lakebase-värden
är inte verifierade i denna leverans. Databricks AI/BI och Genie hålls isär från
denna dataväg och kommer i en senare avgränsning enligt B-029.

### Nästa steg

**Närmaste planeringsleverans, godkänd 2026-10-27:** förbered projekt 2:s del av
[första fråge-/rapportkedjan i projekt 10](../10_operatörscentral/PROJEKTPLAN.md).
Dokument- och testunderlaget är framtaget enligt kontraktet ovan. Ingen webb-
eller agentfunktion aktiveras genom denna leverans; det samlade designstoppet
för kedjan ska godkännas före webbbygget.

Första frågan gäller registrerade försäkrade vid läsdatum och betalmarkerade
premier i en vald avslutad kalendermånad. Återanvänd definitionerna
`insured_registered_count` och `premium_paid_recorded_sek`. Det senare måttet
avser signerade premie-/rättelseposter med giltigt betaldatum i perioden,
exklusive avgifter; det är ingen bankavstämning. Beståndsmåttet är ingen
historisk månadsslutspopulation. Använd samma definitioner i central, teamyta
och rapport och märk dem med version och datum.

Projekt 2 ska leverera följande underlag före byggstart:

- Lakebase via tjänstelagret som första dataväg, inklusive käll-/miljöidentitet,
  population, period, aktualitet och kvalitet. Verifiering i faktisk Lakebase-miljö
  återstår; BI-dashboard och Genie är separata senare integrationer. B-029 består.
- Ett avgränsat läs-/analyskontrakt för det avsedda teamet, utan personuppgifter
  och med småcellsskydd. **Operatörens besked 2026-10-27:** `get_company_metrics`
  är inte känslig (`pii=False`, endast aggregat med småcellsskydd) och ska vara
  `AGENT`-läsning för aktuarieteamet. Claude genomför tjänstelager-/åtkomständring
  och granskad verktygsmontering i körpolicyn i sitt designstopp. Denna
  dokumentleverans ändrar inte runtimebehörigheten.
- Förväntade värden och avvikelsefall för kända underlag: noll, saknat eller
  underkänt underlag, undertryckt cell, felaktig period och misslyckad läsning.
- Rapportunderlag med definitioner, läsdatum/period, källreferenser och
  begränsningar som kan användas av gemensam dokumentgenerering.

Projekt 10 samordnar den mänskliga arbetsvägen, aktuarieteamet analysuppdraget,
och utveckling/kommunikation den tekniska exporten respektive mallen.
Framtida FTA-rapporter bygger på ett separat värderingskontrakt i projekt 6;
premieeffektanalysen ersätter inte värderingsunderlaget.

**Fortsatt BI-arbete och beroenden:**

- Fastställ dashboardens måttdefinitioner, värderingsgrunder och första rapportmottagare.
- Verifiera Unity Catalog, SQL Warehouse och Genie-stöd i den faktiska Databricks-miljön.
- Integrera återstående BI-läsning genom det byggda tjänstelagret (T1–T4 klara). Återanvänd befintliga analysfunktioner och `bestand`-verktyget där definitioner och mandat passar.
- Fastställ historisk arbetsgivarkoppling och löneunderlagens betydelse vid flera försäkringar.
- Utöka till hela beståndet, månadstrender och kvalitetskontroller som inkluderar saknade premier.
- Bestäm åtkomst och rapportkontrakt innan insikter exponeras för agenter.
- För månadssimuleringen: konkretisera V-12 och S-06 i [processöversikten](../../01_domän/processer_översikt.md). Definiera periodlåst intern månadsrapport med ekonomiskt underlag, öppna avvikelser, handläggning och agentkostnad. Samordna med projekt 6; dashboard och rapportmall ersätter inte bokföring, kapital- eller reservmotorer. Fastställ externa mottagare och tillämplighet separat
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
- Hur exponeras fler insikter genom verktyg och rapporter med gemensamma mått och mandat? Ett första `bestand`-verktyg finns redan för Aktuarieagenten.
- Utgå från B-026:s teamstruktur och skills före nya agenter. Precisera arbetsdelningen mellan befintlig Aktuarieagent, planerad Data scientist-specialist och nya analysverktyg; en separat BI-agent är inte beslutad. Kopplingen till Genie återstår att utforma och verifiera.
