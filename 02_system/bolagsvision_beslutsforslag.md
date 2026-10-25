# Beslutsunderlag: verksamhetsdrivet AI-native tjänstepensionsföretag

> **Datum:** 2026-10-25
> **Status:** Godkänt av operatören i chatten 2026-10-25 och infört som **B-037**
> i [BESLUTSLOGG.md](../BESLUTSLOGG.md#b-037--2026-10-25--verksamhetsdrivet-ai-native-tjänstepensionsföretag).

## Bakgrund

B-024 beskriver programvisionen och ett flaggskeppsscenario. B-035 valde en
avgränsad parameterändringsdemo som första byggmål för Fas 3c. Det har bidragit
till att projektet kan läsas som ett bygge för en bestämd demonstration.

Operatören har förtydligat att målet är ett artificiellt men hypotetiskt fungerande,
AI-native tjänstepensionsföretag. Regeländringshantering är en av företagets
verksamhetsförmågor. En demonstration väljs senare för att visa vad företaget kan.

## Godkänd beslutstext

1. **Verksamheten styr.** Arkitektur, datamodeller, gränssnitt och prioriteringar
   utgår från företagets verksamhetsbehov, sammanhängande processer och kontroller.
   Agentteam utför arbete genom gemensamma verktyg, med tydliga mandat, spårbarhet
   och mänskliga beslut där det krävs. Produktscope ITP1 ålderspension och sandbox
   med fiktiva kunder och kapital består.
2. **Generell regeländringsförmåga.** Företaget ska kunna upptäcka och tolka
   relevanta lag-, föreskrifts- och avtalsändringar, bedöma konsekvenser och
   förbereda, genomföra och följa upp godkända åtgärder. Bedömningen kan omfatta
   produktregler, villkor, bestånd, beräkningar, system, processer, styrdokument,
   rapportering och kommunikation. Den aktuella ändringen avgör vilka delar
   som berörs. En parameterändring täcker bara en del av denna förmåga.
3. **Demonstrationer visar byggda förmågor.** Regeländringsscenariot är ett av
   flera möjliga exempel att visa när företagets förmågor finns. Ett bestämt
   scenario får inte styra företagets utformning eller ges egen prioritet i
   byggordningen. Ingen hårdkodad demo-knapp eller förutbestämd demoberättelse
   ska byggas in i ordinarie arbetsytor. Vanliga åtgärder för att starta och
   följa verksamhetsuppdrag och flöden ska finnas enligt respektive mandat.
4. **Test och visning avgränsas.** Fiktiva scenariokällor, särskilda testbestånd,
   skriptade modeller och visningsmanus hålls avgränsade från verksamhetslogiken.
   Återanvändbar infrastruktur från tidigare arbete behålls. Byggda funktioner
   verifieras löpande på relevanta normal- och avvikelsefall; en lyckad visning
   bevisar inte att hela verksamhetsförmågan är färdig.

**Motivering:** Ett hypotetiskt fungerande företag behöver kunna hantera löpande
arbete och varierande händelser. Ett utvalt exempel kan visa resultatet men
ger inte ett tillräckligt underlag för företagets arkitektur eller prioritering.

**Relation till tidigare beslut:** Preciserar B-024:s programvision och B-035:s
roll som avgränsad första implementation. B-035:s tidigare demo som första mål
ska inte styra fortsatt bolagsbygge. B-036:s gemensamma plattform och teamområden
består och används för ordinarie verksamhet. Tidigare beslut bevaras i loggen.

## Dokumentation och fortsatt arbete

Operatörens förtydligande har skrivits in i MASTER_CONTEXT §1 och speglats i
README, ATT_GORA, agentekosystemet och planerna för flöden och operatörscentral.
Beslutet är infört som B-037 i BESLUTSLOGG.md. DEMO_ANTECKNINGAR.md är oförändrad.

Vid fortsatt planering skiljs verifiering av det byggda parameterändringsflödet
från ett senare visningsmanus. Scenariobundna antaganden behöver granskas före
integration i ordinarie arbetsytor. Detta dokument ändrar ingen körkod,
databas, produktregel, behörighet eller godkännandegräns.

Operatörens godkännande och införandet som B-037 har följts upp med hänvisningar
från MASTER_CONTEXT, ATT_GORA och det historiska underlaget för B-035.
