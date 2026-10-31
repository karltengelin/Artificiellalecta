# Öppna frågor till teamen och bolaget

> **Datum:** 2026-10-31. **Status:** operatörens målbild är uttryckligen angiven
> i chatten; lösningen och byggordningen nedan är ett förslag.
> **Omfattning:** designunderlag för fortsatt OC-3/OC-8 och harness.
> Underlaget ändrar ingen körpolicy, databas eller kod och loggar inget beslut.
> Bygger på B-026, B-036–039 och den första rapportkedjan B-041.

## 1. Operatörens målbild

Det ska efterlikna att gå till en avdelning och ställa en öppen fråga.
Användaren ska inte välja en fördefinierad frågetyp eller behöva känna till
vilket verktyg som kan ge svaret. Det gäller även internt: en klassificerare
som bara väljer mellan ett slutet antal tillåtna frågor uppfyller inte kravet.

Två ingångar behövs:

- **Hos teamet:** ett öppet samtal med teamets ledande agent. Användaren kan
  ställa följdfrågor, precisera och beställa vidare arbete i samma samtal.
- **Fråga bolaget:** ett öppet samtal med en samordnande LLM-funktion i
  centralen. Den kan svara på vem som ansvarar för något, beställa bidrag från
  ett eller flera team, följa upp dem och sammanställa ett bolagssvar.

En begäran om utredning ska leda till faktiskt arbete hos tillgängliga team;
att enbart föreslå ett team och lämna över arbetet till användaren räcker inte.
Större frågor ska kunna kräva samarbete och flera omgångar mellan teamen.

## 2. Vad som finns och vad som behöver ändras

| Del | Nuläge | Nästa behov |
|---|---|---|
| Mänsklig frågeingång | OC-3a: `portfolio_overview`, vald månad och fritext som precisering av just den frågan | Fritext som själva uppdraget; period efterfrågas när den behövs |
| Teamkontakt | Aktuariens uppdragslista och rapportgranskning; ingen allmän dialog | Sparat samtal med teamledaren och länkade uppdrag/resultat |
| Bolagssamordning | Ingen samordnande körprofil ansluten till frågeingången | En avgränsad orkestrerare i centralen, med egen spårbar köridentitet |
| Samarbete | `delegate_to_team` finns; bara compliance → aktuarie är aktivt | Centralens tillåtna teamingångar samt uppföljning av flera teams bidrag |
| Återstart och väntan | Första delegeringens budgetbok och idempotens är i minnet; länkad fortsättning genom kedjan återstår | Varaktiga deluppdrag, budget och väntan för längre samarbete |
| Leverans | OC-3a:s källbundna, granskade Markdown/PDF finns | Samtalssvar och vid behov gemensam rapport över flera teams underlag |

Nuläget framgår av [webbdriften](fragekedja_webb.md),
[harness §10](harness.md#10-delegering-och-flöden-det-fas-3b-behöver-bära-från-start),
`src/agents/assignments.py`, `src/agents/delegation.py` och `ecosystem.yaml`.
OC-3a:s verifierade beståndsläsning ska återanvändas som en förmåga, inte som
mall för alla framtida frågor. Att bara ta bort väljaren ändrar inte dagens
fasta uppdragsmall och resultatschema.

## 3. Samtalet med ett team

Teamytan binder mottagaren till teamets egen ledande agent. Fritextfältet
anger användarens uppdrag inom teamets mandat; det är inte bara bakgrund till
ett förutbestämt mål. Agenten kan besvara en förklaringsfråga med tillgängliga
dokument, läsa data med sina verktyg eller be om ett nödvändigt förtydligande.
Alla frågor behöver inte en ny beräkningsoperation.

Period, scenario och antaganden blir synliga preciseringar när de behövs.
En saknad period ska inte hindra en allmän begreppsfråga. Vid flera rimliga
tolkningar med väsentligt olika resultat ska agenten fråga användaren.

Teamledaren kan beställa ett tillåtet bidrag från ett annat team. Användaren
fortsätter tala med den ursprungliga teamledaren och ser vilka andra team som
deltar. Teamytan blir inte en väg att direkt starta valfri annan agent. Detta
följer B-036:s skillnad mellan teamingång och delegering.

## 4. Fråga bolaget och samarbete

Orkestreraren har ett eget samordningsmandat: förstå frågan, dela upp arbetet,
välja tillgängliga team, följa upp beroenden och sammanställa svar. Den är
ingen ytterligare chef ovanpå varje team och övertar inga verksamhetsbeslut.
Karl är fortsatt beslutsfattare. Teamledarna ansvarar för sina sakunderlag.

Den synliga arbetsgången är:

1. Ta emot frågan och eventuell tidigare dialog. Ställ en motfråga om ett
   avgörande mål eller antagande saknas; annars börja arbeta inom uppdragets budget.
2. Läs teamens aktuella mandat och tillgängliga förmågor. Välj vilka bidrag
   som behövs för just denna fråga och visa en kort arbetsplan.
3. Beställ avgränsade bidrag genom teamens ledande agenter. Varje team använder
   egen identitet, profil och behöriga underlag.
4. Låt ett annat team granska eller bygga vidare på ett bidrag när frågan
   kräver det. Hantera motsägelser genom en riktad följdfråga till berört team.
5. Sammanställ slutsats, bidrag, källor, antaganden, osäkerheter, återstående
   arbete och kostnad. Visa ett ofullständigt svar som ofullständigt.

Första införandet kan låta centralen hålla i dessa omgångar sekventiellt.
Ett nytt uppdrag till samma team efter ett annat teams svar är en synlig
uppföljning, inte fri rekursion mellan agenter. Parallella deluppdrag kan
komma senare när budgetreservation och varaktig status stöder det.

En förmågeförteckning beskriver vilka verktyg och team som faktiskt kan
anropas. Den är ingen katalog över vilka frågor användaren får ställa.
Förmågor kan tillkomma utan att användarens frågeform behöver byggas om.

**Exempel, inte en särskild frågetyp:** ”Vad behöver vi utreda om vi vill
ändra garantin för framtida premier?” Aktuarien kan bidra med metod och
beräkningsbehov; compliance med avtal, regler och dokumentkonsekvenser.
Bolagssvaret kan behöva en ny omgång där aktuarien bedömer compliance-teamets
villkor. Om verifierade ekonomi- eller kapitalförmågor saknas visas deras
bidrag som luckor. Orkestreraren får inte fabricera dessa teams arbete eller
göra en ändring av garantin.

## 5. Kontrakt som behövs bakom den öppna ingången

Öppen frågeställning ersätter inte kontroller av faktiska operationer.
Strukturerade verktygsargument och källbundna resultat behövs fortsatt.
Följande är föreslagna kontrakt att precisera före kod:

| Kontrakt | Innehåll och ansvar |
|---|---|
| Samtal | Stabil referens, beställare, ingång/team, miljö, användar- och agentsvar samt länkar till uppdrag. Modellens privata resonemang är inte samtalshistorik |
| Uppdrag | Frågetext, förtydliganden, mål, betrott mandat, budget och policyversion. En förklaringsfråga kräver ingen månad eller något mått-id |
| Deluppdrag | Beställande agent, mottagande teamledare, mål, relevanta underlag, beroenden, status, kostnad och resultatref. Överförda referenser ger ingen ny läsrätt |
| Teamresultat | Slutsats, belagda fakta/beräkningar, definitioner och datum där relevanta, källor, antaganden, luckor och motsägelser. Inte låst till OC-3a:s två observationer |
| Bolagssvar | Hänvisningar till de bidrag som slutsatsen bygger på, kvarstående oenighet, saknade bidrag och samlad kostnad utan dubbelräkning |
| Leverans | Kort svar i samtalet; rapport när användaren begär den eller godtar ett rapportförslag. Rapporter behåller versionsbindning och mänsklig granskning |

Samtal, verksamhetsuppdrag och modellkörning är skilda enheter. Ett
förtydligande fortsätter ett väntande uppdrag. En följdfråga som beställer
nytt arbete kan skapa ett nytt länkat uppdrag i samma samtal. Automatiska
följdomgångar får inte återställa rotbudgeten. En ny läsning gör inte gamla
rapporter aktuella och skriver inte om deras innehåll.

Den nuvarande harnessmodellen binder varje agent till ett team.
**Rekommendation:** modellera centralens orkestrerare som en teknisk
ingångsprofil i harness, utan att uppfinna ett åttonde verksamhetsteam.
Profilens identitet, tillåtna teamingångar, modellroll och budget behöver
få uttryckligt stöd i konfigurationsvalidering, körjournal och kostnadsbild.
Det är en kontraktsutökning, inte en funktion som redan kan slås på i YAML.

## 6. Befintliga gränser och kontroller

- Orkestreraren får ingen sammanslagning av teamens databaspoddar. Den
  beställer behöriga teamresultat; tal och verksamhetsfakta kommer från
  identifierbara underlag och beräkningar.
- Frågetext, tidigare svar och dokument kan inte utfärda resursmandat,
  ändra miljö eller ge rätt till en skrivoperation. Båda riktningarna i en
  överlämning behöver kontroll av vilka uppgifter som får lämnas ut.
- Första öppna införandet kan vara utan kundpersonuppgifter och utan
  affärsskrivningar. Senare sådant arbete kräver befintliga domänmandat och
  godkännanden, även om frågan ställs i ett fritt samtal.
- Klassificering, planering, teamanrop, följdomgångar och syntes räknas inom
  samma uppdragsbudget. Tak ska stoppa arbete med ett begripligt delresultat.
- Väntan, avbrott, fel och okänt utfall ska vara varaktiga. Inga tysta
  omkörningar efter omstart. Barnens väntan och godkännanden måste gå att följa.
- Kända, granskade verksamhetsprocesser behåller flödesmotorn och sina grindar.
  Fri samordning ersätter inte exempelvis en regeländrings godkännandesteg.

## 7. Byggordning och verifierbart resultat

1. **Lås samtals- och samordningskontrakten.** Profil/identitet för centralen,
   lagring, budget, resultat och återstart preciseras tillsammans med harnessägaren.
   Förslaget innebär ingen egen ändring av Lakebase eller dess rättigheter.
2. **Bygg öppen teamdialog och gemensam uppdragshistorik.** Börja med tillgängliga
   aktuarie- och compliance-förmågor. Bevara OC-3a som regression för beståndsläsning
   och rapportleverans. Användaren väljer aldrig frågetyp.
3. **Bygg centralens samordning med minst två verkliga team.** Centralen ska kunna
   beställa, jämföra och följa upp bidrag inom samma uppdrag. Att bara öppna fri
   text eller returnera ett teamnamn är inte leveransen.
4. **Verifiera samtal, samarbete och återhämtning som ett helt förlopp.** Därefter
   fler teamingångar och eventuell parallell körning när deras förmågor finns.

Acceptansen ska minst visa en öppen begreppsfråga utan period, en motfråga och
fortsättning, en datafråga med belagda tal, en fråga som kräver två teams bidrag
och en följdomgång, motstridiga eller saknade underlag, en obyggd teamförmåga,
budgetstopp, omstart utan dubbel körning samt en rapport som går att granska
och återfinna. Frågorna ska varieras; inget hårdkodat visningsscenario eller
obligatorisk uppräkning av godkända frågeformuleringar.

## 8. Relation till tidigare beslut och samordning

Operatörens krav ersätter en meny över frågetyper som långsiktig målbild.
B-041 bevaras som beslutet om den första avgränsade kedjan. B-038:s första
en-team-ingång behöver utvecklas för den nya bolagssamordningen. B-039:s
aktiva delegeringspar och synkrona begränsningar är nuläge, inte färdigt stöd
för denna leverans. B-026:s teamingångar och B-036:s teamytor består.

De föreslagna interna valen ovan behöver ingå i nästa gemensamma bygguppdrag;
det tidigare uppdraget begränsat till `src/web` och `src/reporting` räcker inte.
Harness/AI äger körning och samordning, projekt 10 samtalsupplevelsen och
teamytorna, och respektive team sina sakförmågor. Projekt 2 och den gemensamma
rapportförmågan återanvänds där frågan kräver dem.

`MASTER_CONTEXT.md`, `BESLUTSLOGG.md` och `ATT_GORA.md` lämnas orörda enligt
samordningsregeln. För en senare godkänd lösning föreslås en beslutspost om
öppna teamingångar, centralens samordningsprofil, uppdrags-/samtalskontrakt,
budget och verifiering. Inget nytt beslutsnummer tilldelas i detta underlag.
