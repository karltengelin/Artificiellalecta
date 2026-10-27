# Projekt 10: Operatörscentral på VD-nivå

> Planeringsuppdrag från Karl i chatten 2026-10-25. Ingår i programmet
> AI-native tjänstepensionsbolag. Inget nytt beslutsnummer loggas genom planen.
> **Status:** OC-0:s rekommendationer A–X godkända 2026-10-26 genom B-038.
> Design- och dokumentleveransen är klar. OC-1 med en smal OC-2 är lokalt byggd
> och verifierad; fullständig logg-/BI-integration, Lakebase-verifiering och senare paket återstår.

## Syfte och avgränsning

Ge Karl en gemensam arbetsyta som VD: följa bolagets ekonomiska utveckling,
förstå teamens arbete och kostnader, ställa frågor mot data och fatta
inriktningsbeslut om prioriteringar, agentbudget och modellpolicy.

Operatörscentralens arbetsenhet är ett bolagsmått, ett team, ett analysuppdrag
eller ett ledningsbeslut. Enskilda handläggarärenden och deras godkännanden
hanteras i specialiserade gränssnitt. Här visas sammanlagda volymer, trender,
flaskhalsar och systematiska avvikelser. Länkar öppnar rätt specialistvy när
Karl vill arbeta vidare. Befintliga domängodkännanden gäller även fortsättningsvis.

Karl är högsta beslutsfattare. Den gemensamma frågeingången samordnar uppdrag
via teamens ledande agenter och sammanställer underlag; den får inget eget
VD-mandat och inga utökade data- eller skrivrättigheter.

**En plattform med teamområden (B-036).** Bolaget får
en gemensam webbplattform, inte en app per team. Samma server, Digital klarhet,
formulärskydd och, när den finns, inloggning.

- **Operatörscentralen är startsida och nav.** Härifrån startar och följer Karl
  bolagsflöden, till exempel regeländringar. Härifrån når han också varje teams område.
- **Varje team har ett eget område:** försäkring (handläggning, dagens
  handläggar-UI), compliance, aktuarie och senare utveckling, kommunikation och
  kapitalförvaltning. Området visar teamets uppdrag, körningar, utkast, resultat
  och de förslag i godkännandekön som rör teamets domän.
- **I ett teamområde nås bara teamets egen agent.** I handläggningen är det
  handläggaragenten, inte compliance eller aktuarie. Arbete över flera team går
  genom flöden från centralen eller genom delegering (3c-1), aldrig genom att ett
  teamområde startar ett annat teams agent.
- **Agenter kan arbeta självständigt.** En agent kan ta uppdrag automatiskt,
  till exempel när ett ärende registreras. Gränserna är desamma som när en människa
  startar den: mandat, budget och godkännande av skrivningar i kön. Självständig
  betyder att agenten börjar arbeta själv, inte att den beslutar själv.

## Produktens sex delar

| Del | Fråga som ska besvaras | Första avgränsning |
|---|---|---|
| Bolagsläge | Hur mår bolaget och vad har ändrats? | Bestånd/premier från verifierade mått; konsolidering, kapital, FTA och likviditet när beräkningsunderlagen finns |
| Team och leveranser | Vad gör teamen, vad levererar de och vad hindrar dem? | Körstatus, avslutade uppdrag, fel/stopp och sammanfattade hinder; skilj konfigurerat team från körande team |
| Agentekonomi | Vad kostar agentarbetet och vilken nytta ger det? | Uppskattad kostnad per period, team, modell och uppdrag; resultat och kvalitet bredvid kostnad |
| Ledningsfrågor | Vad behöver Karl bestämma om riktningen? | Underlag för modellpolicy, budget, prioriteringar och väsentliga avvikelser; inget generellt inflöde av handläggarärenden |
| Fråga bolaget | Varför ändrades ett mått, och vad bör vi undersöka? | En fråga med vald period och datakälla till rätt team; svar med källor, antaganden och begränsningar |
| Styrning | Hur ska agenterna arbeta framåt? | Förhandsgranska global modellpolicy och undantag, därefter kontrollerad aktivering; koppling till harnessens körgränser |

## Första skissen

[SKISS.md](SKISS.md) beskriver sidornas innehåll, interaktioner och exempeldata.
Den visuella skissen följer Digital klarhet (B-034) och visar föreslagen
användning. Alla kostnadsserier, uppdrag och ledningsunderlag i skissen är
syntetiska. Den gör inga modellanrop och ändrar inga riktiga inställningar.

## Leveranser och byggordning

Detta är arbetspaket inom projekt 10, inte nya programfaser. B-028:s byggordning
består. B-035 beskriver en första avgränsad implementation; fortsatt arbete styrs av
verksamhetsbehoven enligt MASTER_CONTEXT §1 (operatörens förtydligande 2026-10-25).
Centralen ska ge tillgång till ordinarie bolagsförmågor. Scenariobundna testdata,
skriptade modeller och visningsmanus får ingen hårdkodad demo-knapp här.
Läsbar överblick kan byggas innan alla
ekonomiska motorer finns; saknade mått visas som **ej beräknat**.

| Paket | Leverans och klart-kriterium | Beroenden |
|---|---|---|
| OC-0: Avgränsning och kontrakt | Klar som design- och dokumentleverans 2026-10-26: [rekommendationerna A–X](../../02_system/operatörscentral_beslutsforslag.md) godkända genom B-038. Mått/händelser, eskaleringar, routing, autentisering och gemensamt policyregister för OC-5/3b-9 är preciserade; implementation sker i följande paket | Projekt 2, 6 och harness; Karl har godkänt designen |
| OC-1: Läsbar ledningsöversikt | Lokalt byggd 2026-10-26: `/central` med bolagsläge, team, agentkostnader och måttunderlag. Läsadaptern ger granskade bestånds-/premieaggregat utan PII; ekonomiska motorer och leverans-/kvalitetsmått markeras som luckor. [Driftbeskrivning](../../02_system/operatörscentral_drift.md) | FastAPI/Jinja2/HTMX och B-038; integration och Lakebase-verifiering återstår |
| OC-2: Agentekonomi och uppföljning | Smal lokal leverans 2026-10-26: manifest, idempotent metadataindex, kostnad per team/modell/hashat uppdrag, okänd kostnad, källtäckning och journalstatus. Full försöks-/prisavstämning, loggrotation och leverans-/kvalitetsproducenter återstår | AI-logg, harnessjournal och deklarerad käll-/miljöidentitet; delegeringsdata när 3c-1 finns |
| OC-3: Gemensam frågeingång | Fråga routas till rätt teamledare med avgränsat mandat och budget. Svaret visar underlag, datum och ansvarigt team. Saknat underlag blir ett tydligt svar | Befintliga agentprofiler och behöriga analysverktyg; samordnade barnuppdrag kräver 3c-1 |
| OC-4: Ledningsunderlag | Prioriterade, sammanfattade frågor med alternativ, konsekvenser, ägare och beslutsspår. Rutinärenden stannar i specialistvyer. Eskaleringsvillkor granskas före aktivering | OC-1/2; definierade domängränser och rapportkontrakt |
| OC-5: Modellpolicy och budget | Autentiserad Karl kan förhandsgranska och aktivera versionssatt policy för nya körningar: globalt val, rollmappning, teamundantag, reservpolicy och körbudget. Granskning visar berörda team och faktisk effekt | OC-0, AI-lagret och 3b-9; inga styrskrivningar före autentisering och ändringslogg |
| OC-6: Ekonomisk fördjupning och acceptans | Konsolidering, FTA, kapital och likviditet ansluts när respektive modell är verifierad; period- och grundversioner går att följa. Sammanhängande VD-scenario godkänt | Projekt 2, 5 och 6; definierad konsoliderings-/fördelningsmodell |
| OC-7: Flöden och produktparametrar | Bolagsflöden startas och följs här, först regeländringsflödet `rule_change_parameter` (B-035): starta, kör nästa steg, grindbeslut, manuella steg, avstämning, utkast och körjournal. Produktparametrarnas versioner visas här. Förslag i godkännandekön som gäller bolagsbeslut visas också här; kön ägs fortfarande av tjänstelagret. Åtgärderna använder samma operatörsidentitet och formulärskydd som handläggar-UI:t (B-017) och behöver inte vänta på styrvägens autentisering i OC-5. `/floden` och `/parametrar` i handläggar-UI:t tas bort eller blir länkar när de fungerar här | Flödesadaptern `agents.flows.console.FlowConsole` (3c-3); plattformen i OC-8 |
| OC-8: Plattform och teamområden | En gemensam webbplattform med operatörscentralen som startsida och ett område per team. Handläggar-UI:t blir försäkringsteamets område; om dagens adresser behålls eller samlas under ett prefix avgörs här. Compliance och aktuarie får egna områden med teamets uppdrag, körningar, utkast och resultat. Ett område exponerar bara teamets egen agent, och ett test vaktar gränsen. Centralen länkar till varje område och visar dess läge | Befintlig FastAPI/Jinja2/HTMX-grund; teamprofilerna i `ecosystem.yaml`; OC-1 för navet |

**Första byggleveransen enligt B-038, nu lokalt byggd:** OC-1 och en smal OC-2:
bolagsöversikt med ärligt markerade dataluckor, teamstatus samt agentkostnader ur
befintliga loggar. Därefter frågor till ett team åt gången. Automatisk
samordning över flera team och skrivande styrning öppnas först med sina beroenden.
Inga kalendertider är beslutade. Närmaste fortsättning preciseras nedan genom
operatörens godkända dokument- och prioriteringsarbete 2026-10-27.

## Nästa bygguppdrag att förbereda: beståndsfråga till granskad rapport

**Planeringsprioritet godkänd 2026-10-27; designstoppet godkänt som B-041. Harness- och
tjänstedelen är byggd lokalt; inloggning, rendering och vyer återstår.**
Detta avgränsar OC-3 och den del av OC-8 som behövs för ett första användbart
arbetsförlopp, tillsammans med projekt 2 och gemensam dokumentgenerering.
Det inför inget nytt projekt, ingen generell router och inga nya befogenheter.

### Fråga och leverans

Första avgränsningen är en källbunden beståndsöversikt:
*Hur många försäkrade är registrerade vid läsningen, hur mycket premier är
betalmarkerade för en vald avslutad kalendermånad och vilka begränsningar har underlaget?*

Använd definitionerna `insured_registered_count` och `premium_paid_recorded_sek`
från de gemensamma ledningsmåtten, efter projekt 2:s kontroll av dataväg och
kvalitet. Registrerat bestånd avser läsdatum och alla statusar; det är ingen
historisk beståndsserie. Betalmarkeringar är inte bankavstämt kassainflöde.
Jämförelser över tid, FTA, kapitalvärdering och strategiska effektmodeller
ingår i senare avgränsningar när motsvarande underlag finns.

Arbetsförloppet ska hålla ihop fråga, ansvarigt team, underlag, körning,
utkast, mänsklig granskning och återfinnbar leverans. Användaren ska kunna
följa det både från centralen och i det valda teamets arbetsyta. Börja med
aktuarieteamet som avsedd mottagare utifrån dess analysansvar; dagens profil
är smalare och dess framtida verktygsmontering måste granskas före aktivering.

Minsta leverans är en Markdownrapport med slutsats, definitioner, datum/period,
datakälla och miljö, värden, kontroller, källreferenser och begränsningar samt
export i den gemensamma A4-mallen. Befintlig presentationsmall ska kunna
återanvändas när presentationsgenereringen kopplas in; den krävs inte för att
den första rapportkedjan ska kunna godtas. Inga dokument skickas eller publiceras.

### Ansvar och beroenden före byggstart

| Del | Ansvar och startvillkor |
|---|---|
| Mänsklig arbetsväg | Projekt 10 avgränsar central, nödvändig teamyta, uppdragsstatus och återfinnbar leverans. Nya bolagsfrågor kräver B-038:s verifierade operatörssession, serverrättigheter och formulärskydd |
| Mått och data | Projekt 2 preciserar dataväg, population, period, kvalitetskontroller och behörigt analysverktyg. `get_company_metrics` är i dag `HUMAN_ONLY`. Operatören angav 2026-10-27 att den inte är känslig och godkände [designstoppets](../../02_system/fragekedja_beslutsforslag.md) val C–D: nivån `AGENT` för aktuarien med kolumnbegränsad läsrätt för rollen. Kolumnrätterna sätts i Lakebase efter operatörens OK |
| Analys och mandat | Aktuarieteamets avgränsade uppdrag och eventuella nya läsverktyg prövas mot målmandat och körpolicy. Befintlig parametermandatbunden premieeffektanalys ger inte åtkomst till generell beståndsanalys |
| Körning och spår | Harness återanvänds för identitet, mandat, budget och körjournal. Befintliga uppdrags-, ärende-, flödes-, körnings- och utkastreferenser behåller sina syften. Generell flerteamrouting och bakgrundskörning krävs inte för första kedjan |
| Dokumentleverans | Kommunikation äger gemensam mall/användning och utveckling den tekniska genereringen. Avgränsa skyddad lagring, data-/resursgränser, versionsreferenser och granskningsstatus inom befintlig dokumentförmåga. Lokal PDF-export är inte i sig ett monterat agentverktyg |
| Databricks | Verifiera vald dataväg i den faktiska miljön enligt B-029. Lakebase, BI-dashboard och Genie har skilda integrationsstatusar. Ingen tyst reserv till en annan datakälla eller nytt BI-lager |

Startvillkoren konkretiseras i samma bygguppdrag innan kod påbörjas. De öppnar
inte ett allmänt SQL-, fil- eller nätverksmandat. Förslaget till val och gränssnitt finns i
[designstoppet för fråge-/rapportkedjan](../../02_system/fragekedja_beslutsforslag.md) (2026-10-27). Befintlig FlowConsole-väg
för domänåtgärder behöver fortsatt inte vänta på OC-5:s styrfunktioner.

### Acceptansvillkor för den kommande implementationen

1. En verifierad operatör kan ställa den avgränsade frågan, välja miljö och
   tillgänglig avslutad kalendermånad samt se ansvarigt team och uppdragsreferens.
2. Samma uppdrag går att följa från central och teamyta: pågående arbete,
   väntan, fel, utkast och granskad leverans skiljs åt. En avslutad körning
   klarmarkerar inte automatiskt leveransens kvalitet.
3. Alla värden kommer från behöriga verktyg med samma definitioner som BI och
   centralen. Läsdatum, period och källversioner framgår. Modellen räknar
   inte ersättningsvärden för underlag som saknas eller är dolt.
4. Rapporten kan granskas, öppnas igen och följas till uppdrag och underlag,
   med innehålls-, mall- och designversion. Renderingen kontrolleras visuellt.
5. Tester prövar normalfall, noll kontra saknat, småcellsskydd, nekad åtkomst,
   fel i datakällan, fråga utanför stödet och misslyckad dokumentexport.
   Ett korrekt avgränsat eller nekat svar kan vara ett godkänt utfall.
6. Upprepning eller återhämtning får inte göra en gammal rapport aktuell utan
   nytt underlag eller skapa oklara leveransversioner. Första versionens
   begränsningar anges innan den öppnas för användning.

Premie-/betalningskedjan och FTA förbereds som kommande verksamhetsuppdrag i
projekt 1/4/6 med projekt 5 och 2 vid respektive gränssnitt. Denna plan
startar inte flera parallella implementationer.

**Flöden har tillfälligt hem i handläggar-UI:t.** Regeländringsflödet byggdes i
3c-3 som `/floden` i handläggar-UI:t, eftersom det var det enda gränssnittet med
lokal server, formulärskydd och godkännandekön. En regeländring är ett beslut på
bolagsnivå och inte handläggning av enskilda försäkrade, och flödet kör compliance
och aktuarie, inte handläggaragenten. Därför flyttar flödena hit i OC-7, och
produktparametrarna (`/parametrar`) med dem. Flytten är billig:
motor och verksamhetsdefinition ligger i `src/agents/flows/`, och webben når
dem bara genom adaptern `FlowConsole`. Den kan användas av vilket gränssnitt som
helst, även ett kommandoradsverktyg eller Cowork (B-017). Den tidigare demomodellen
är borttagen enligt B-037; inför integration krävs en verifierad, uttrycklig modell-
och datakoppling. Att flytta UI-koden aktiverar inte den kopplingen.

## Ansvar och samordning

| Område | Äger |
|---|---|
| Projekt 10 | VD-upplevelse, navigation, ledningsunderlag och samlad operatörscentral |
| Projekt 2: BI & insikter | Gemensamma mått, historik, analys-/Genie-underlag och Databricks-dashboard enligt B-029 |
| Harness och AI-lagret | Teamrouting, körpolicy, budgetverkställighet, körspår, modellroller och leverantörsval, flödesmotorn och flödesdefinitionerna |
| Projekt 1 och övriga specialistytor | Enskilda ärenden, domänhandlingar och deras godkännanden |
| Projekt 5 och 6 | Kapitalvärdering, ekonomi, aktuariella motorer och underlag för konsolidering/risk |
| Projekt 8 och 9 | Projektkarta respektive processkartor som förklarar hur bolaget hänger ihop |

Projekt 10 bygger inga parallella kapital-, reserv-, bokförings- eller
försäkringsmotorer. Tekniska gränser och planerade kontrakt finns i
[operatörscentralens arkitektur](../../02_system/operatörscentral.md).

## Acceptans ur Karls perspektiv

1. På startsidan kan Karl se bolagets läge och viktigaste förändringar utan att
   läsa personuppgifter eller enskilda handläggarärenden.
2. Ett mått kan följas till definition, datakälla, datum och beräkningsversion.
   Saknad eller gammal data har en egen status och blir aldrig noll eller grönt.
3. Kostnadsförändring kan förklaras per team, modell och uppdrag, inklusive
   fel/reservanrop och vad arbetet levererat. Okänd kostnad framgår.
4. Frågan ”Varför har agentkostnaden ökat?” ger källbundet underlag; ”Varför
   sjönk konsolideringen?” anger tydligt om beräkningsunderlag ännu saknas.
5. ”Använd OpenAI för nya körningar” visar berörda roller, teamundantag och
   reservval före aktivering. Ett exklusivt leverantörsval får ingen dold reserv
   hos den andra leverantören. Pågående rotkörningar behåller sin policyversion.
6. Ett inriktningsbeslut kan följas från underlag till beslutad ändring och
   uppföljning. Det ersätter inte en domäns separata genomförandegodkännande.
7. Alla sidor fungerar med tangentbord och smal skärm. Skissen har inga
   livekopplingar; framtida driftsatt styrning kräver autentiserad operatör.

## Beslutad design och återstående införandeval

[OC-0:s underlag](../../02_system/operatörscentral_beslutsforslag.md)
preciserar kontrakten; rekommendationerna A–X är godkända genom B-038.
Gemensamma mått/händelser, importidentitet, eskaleringströsklar, teamrouting,
autentisering och ett gemensamt PolicyStore för OC-5/3b-9 är därmed designgrund.
Kvar inför respektive byggpaket:

- Hur och när Databricks-dashboarden bäddas in; en gemensam måttdefinition
  ska ligga bakom både översikten och BI-fördjupningen.
- Konkreta läsadaptrar, importmanifest och indexschema som verkställer OC-0:s identitets- och täckningskontrakt.
- Verifiering av de beslutade sandboxtrösklarna och respektive domäns ekonomiska väsentlighet när måtten finns.
- Databasschema, migration och kontrollerad övergång från YAML/env till PolicyStore; autentisering och budgetverkställighet.
- Faktiska granskade modellkedjor, katalog-/prisversioner och eventuella namngivna teamundantag enligt den beslutade reservpolicyn.

Förslaget innehåller också acceptansfall och införandegrindar. Godkända
kontrakt ersätter inte domängodkännanden eller verifiering av läsadaptrar,
3c-1, 3c-V, autentisering och budgetverkställighet i respektive byggpaket.

Beslut som behöver loggas formuleras som förslag till Karl. Denna plan för inte
in nya poster i BESLUTSLOGG och aktiverar inga befogenheter.
