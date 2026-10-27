# Beslutslogg – ITP1 Administrationsplattform

> Löpande logg över beslut som fattas i projektet. Varje beslut har en motivering så att framtida Claude (och framtida du) förstår *varför* något bestämdes, inte bara *vad*.
>
> **Format:** Nya beslut läggs överst. Ändra inte gamla poster – om ett beslut ändras, lägg in ett nytt och referera till det gamla.

---

## Beslut

### B-040 | 2026-10-27 | Postgres-prov körs efter aktivt val och pekas ut per ändring

**Beslut:** Operatören godkände i chatten 2026-10-27 förslagen B–D efter mätningen av
testsviten: ”Ja, genomför B–D enligt förslaget och formulera beslutsposten för godkännande.”

1. **Aktivt val.** Prov med markören `postgres` körs bara när `RUN_POSTGRES_TESTS=1` är satt
   i skalet eller med `run_tests.py --postgres`. Anslutningsadresser i `.env` räcker inte,
   och valet får inte ligga i `.env`. Det gäller också när pytest körs direkt.
2. **Ändringsstyrt urval.** Postgres-regler i `tests/suites.toml` pekar ut vilka Postgres-prov
   en ändring berör: migreringar och modeller, tjänstelagrets transaktioner och låsning,
   databasroller och åtkomstregister, demobeståndet och testfiler med Postgres-prov.
   Körverktyget varnar när berörda prov inte körts. De ska köras med `--postgres` före leverans.
3. **Bred kontroll.** `--all --postgres` körs före migrering eller seed mot Lakebase och som
   regelbunden kontroll.
4. **Klassificering.** En testfil som skapar scheman i testdatabasen ska ha markören
   `postgres`, och katalogkontrollen stoppar annars.

**Motivering:** Mätningen 2026-10-27 visade att Postgres-proven mot den isolerade
testdatabasen tog 496 av sviten 614 sekunder. Det berodde på nätverksrundor för schema,
DDL och seed, inte på antalet tester. De körde varje gång eftersom adresserna finns i
`.env`, också för ändringar som inte rör databasen. Proven behövs för radlås, roller och
migreringar, så de behålls men körs när de är relevanta.

**Övervägda alternativ:** Att ta bort eller slå ihop Postgres-prov, att bygga fixturer en
gång per session, att köra parallellt med pytest-xdist och att låta verktyget köra berörda
Postgres-prov automatiskt. Det sista valdes bort eftersom körningar mot Lakebase-projektet
samordnas enligt AGENTS.md §4.5.

**Konsekvenser:**
- Den lokala sviten tar cirka 2 minuter i stället för cirka 10.
- Ett grönt lokalt resultat bevisar inte Postgres-beteende. Redovisningen ska skilja
  bortvalda Postgres-prov från godkända, som teststrategin redan kräver.
- Ingen databasändring, ny roll eller extern tjänst.

**Preciserar:** `02_system/teststrategi.md` (infört 2026-10-25) och AGENTS.md §4.4 och §4.5.

---

### B-039 | 2026-10-27 | 3c-1: delegering mellan team

**Beslut:** Operatören godkände rekommendationerna A0 och A–K i
`02_system/delegering_beslutsforslag.md` version 0.1 i chatten 2026-10-27:
”Jag godkänner rekommendationerna A0 och A–K. Logga beslutet och börja bygga.”
Inga avvikelser angavs.

1. **Bygg nu, avgränsat (A0).** Delegeringen är avstängd som standard. Flödets
   regressionstester ska gå gröna före merge, eftersom loopen och dispatchern ändras
   före 3c-V:s körning mot Lakebase.
2. **Första paret (A, K).** Compliance → aktuarie, utan personuppgifter och utan
   förslag som väntar på godkännande. Aktuarieteamets mandat omfattar granskning och
   beräkningsunderlag på beställning av compliance, utan nya poddar eller verktyg.
   Forsakring → compliance (B-011:s eskalering) öppnas i en senare leverans efter F5-6.
3. **Mandat och synlighet (B, C).** Barnet får bara mandat som betrodd kod redan
   utfärdat; modellen skapar inga mandat. Verktyget `delegate_to_team` visas bara när
   det betrodda uppdraget anger tillåtna mål (`delegation_targets`); standard är stängt.
4. **Personuppgifter (D).** En körning med synliga PII-verktyg delegerar inte till ett
   team utan PII-mandat. Par 2 kräver en strukturerad PII-fri fråga som prövas mot
   ärendets kända identifierare.
5. **Körning och budget (E, F).** Synkron och sekventiell körning. Betrodd kod sätter
   barnets tak ur mottagarprofilen och det som återstår av rotbudgeten; förbrukningen
   bokförs i en gemensam budgetbok per rot.
6. **Resultat, idempotens och väntan (G–I).** Föräldern får barnets strukturerade
   resultat, inte dess arbetsyta. `task_id` härleds ur förälderns run-id och call-id och
   ger samma barn vid upprepning. Barnets väntan, stopp och avstämningskrav sprids till
   föräldern; fortsättning genom kedjan byggs när ett par kan vänta.
7. **Spårbarhet (J).** Händelserna `delegation_requested`, `delegation_denied`,
   `delegation_started` och `delegation_returned` i förälderns körjournal; barnets
   journal bär `parent_run_id`, `root_run_id`, `depth` och `task_id`.

**Motivering:** Paret utan personuppgifter och utan väntan prövar hela mekaniken –
identitet, budgetbok, resultat, journal, idempotens och nekanden – med minsta risk.
Den större verksamhetsnyttan (OC-3 och handläggarens regelfrågor) kan sedan öppnas
genom granskad konfiguration i stället för ny motor.

**Övervägda alternativ:** Att vänta på konkret behov i OC-3 eller F5-6, att öppna
båda paren direkt, att låta operatören godkänna nya mandat vid delegering, att visa
verktyget i alla körningar, asynkron körning via bakgrundsarbetaren och att låta
modellen föreslå budget. Se underlagets §2.

**Konsekvenser:**
- Bygget sker i harness (`src/agents/`), utan databasändring, ny databasroll eller extern tjänst.
- Röktest mot riktig modell görs i demo och `svc_test` med befintliga teamroller.
- Kända flerteamprocesser med grindar fortsätter i flödesmotorn.

**Preciserar:** B-016 och B-026:s dynamiska delegering och `harness.md` §10.2.
Avviker från B-035:s byggordning (3c-1 efter 3c-V) genom att bygget börjar före 3c-V:s
körning mot Lakebase, med villkoret i punkt 1. B-038 val M består tills OC-3 använder delegeringen.

---

### B-038 | 2026-10-26 | OC-0: operatörscentralens kontrakt och gemensamma modell-/budgetpolicy

**Beslut:** Operatören godkände rekommendationerna A–X i
`02_system/operatörscentral_beslutsforslag.md` version 0.1 i chatten
2026-10-26: ”jag tycker dina rekommendationer verkar bra. kör på denna planen”.
Inga avvikelser eller uppskjutna val angavs. Underlagets kontrakt och
införandegrindar gäller som design för fortsatt bygge:

1. **Ledningsyta och mått (A–F).** Läsbar överblick införs först. Projekt 2 och
   domänägaren förvaltar gemensamma, versionssatta mått. Observationer binder
   källa, miljö, period, grund och kvalitet; saknat underlag blir inte noll.
   Centralen använder granskade aggregat med skydd mot små personsegment.
2. **Händelser, kostnad och kvalitet (G–J).** Sanerade läsprojektioner har stabila
   originalreferenser och idempotent import. Varje synligt AI-försök räknas en
   gång. Känd kostnad, okänd möjlig debitering och täckning särredovisas utan
   dubbelräkning av rot/barn/fortsättningar. Leverans och godkänd kvalitet skiljs åt.
3. **Ledningseskaleringar (K–L).** Versionerade sandboxtrösklar och egna
   ledningsunderlag används för systematiska avvikelser och inriktningsbeslut,
   med ägare, alternativ, underlagsbindning och uppföljning. Rutinärenden
   stannar hos specialisten. Inriktning ersätter inget domängodkännande.
4. **Frågerouting (M–O).** Första ingången använder ett uttryckligen valt team
   och dess befintliga ledande agent. Betrodd kod binder identitet, miljö,
   period, källor, mandat och budget. Svar är källbundna och visar luckor.
   Obyggda förmågor ger ingen låtsaskörning; automatisk flerteamrouting kräver 3c-1.
5. **Autentisering (P–Q).** Nya bolagsfrågor och styrfunktioner använder en
   verifierad lokal operatörssession, serverkontrollerade rättigheter och
   sessionsbundet formulärskydd enligt underlaget. Styraktivering kräver
   förhandsgranskning och nylig återautentisering. B-036:s befintliga väg
   för flödessteg via FlowConsole och domänkö kvarstår utan krav på OC-5-inloggning.
6. **En policykälla för OC-5 och 3b-9 (R–W).** Harness får ett gemensamt,
   varaktigt PolicyStore med oföränderliga versioner och atomisk aktivering
   per miljö, med Lakebase som lagringsinriktning. Efter kontrollerad migrering
   äger det operativa modellval och körbudgetar; Git-konfiguration äger fortsatt
   befogenheter och modellkatalog. Ingen dold YAML/env-överstyrning tillåts i
   hanterat läge. Exklusiv leverantörspolicy gäller hela modellkedjan; synliga
   teamundantag får inte kringgå den. Rot, barn och fortsättningar behåller
   modell-/budgetversion och förbrukning. Periodbudget är inte aktiverad som
   standard och kräver en gemensam verifierad reservationsbok.
7. **Stegvis införande (X).** OC-1 med en smal OC-2 är nästa byggleverans.
   Senare frågor, styrning, ekonomiska mått och flerteamrouting öppnas först
   när respektive autentisering, verktyg, motor och kontraktsprov verifierats.

**Motivering:** Gemensamma definitioner, stabila bevisreferenser och en enda
styrkälla gör bolagsläge, kostnad och beslut jämförbara och spårbara utan att
centralen bygger parallella domänmotorer eller vidgar agenternas befogenheter.

**Övervägda alternativ:** Alternativen per val A–X finns i underlagets §1.
Bland annat övervägdes enbart Git/YAML för driftval, enbart nya loggar med
försöks-id, manuella ledningseskaleringar och att vänta ut alla körningar
före policybyte. Rekommendationerna valdes i samtliga fall.

**Konsekvenser:**
- OC-0:s dokument- och designleverans är klar. OC-1–8 och 3b-9 är fortsatt byggarbete med underlagets beroenden och acceptansfall.
- Ingen kod, migration, extern tjänst, databasroll eller runtimepolicy aktiveras genom beslutet. Dagens YAML/env gäller tills övergången är implementerad och verifierad.
- Måttadaptrar och kontrollregler verifieras av respektive ägare. Beslutet inför inga rättsliga trösklar eller löften om exakta kostnadshårdtak.
- Dokumentstatus och hänvisningar samordnas i projektplan, MASTER_CONTEXT, README, ATT_GORA, harness-, AI-, team- och BI-underlag. Ingen merge till main godkänns genom designbeslutet.

**Preciserar:** B-025:s roll-/reservpolicy, B-026:s körpolicy och teamingångar,
B-029:s gemensamma analysunderlag samt B-036:s operatörscentral. B-017/B-028:s
domänvägar och B-037:s verksamhetsdrivna byggordning består.

---

### B-037 | 2026-10-25 | Verksamhetsdrivet AI-native tjänstepensionsföretag

**Beslut:** Operatören godkände beslutstexten i `02_system/bolagsvision_beslutsforslag.md` i chatten 2026-10-25. Följande gäller för fortsatt arbete:

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

**Konsekvenser:**
- MASTER_CONTEXT §1 och berörda planer utgår från verksamhetsbehov; ett visningsscenario har ingen egen prioritet i byggordningen.
- Verifiering av byggda funktioner skiljs från senare visningsmanus. Scenariobundet teststöd behöver avgränsas före integration i ordinarie arbetsytor.
- Beslutet ändrar ingen körkod, databas, produktregel, behörighet eller godkännandegräns. Tidigare beslut bevaras i loggen.

---

### B-036 | 2026-10-25 | En plattform med teamområden och operatörscentralen som nav

**Beslut:** Operatören godkände inriktningen i chatten 2026-10-25 och bad om att beslutet loggas.

1. **En plattform.** Bolagets gränssnitt är en gemensam webbplattform med operatörscentralen som startsida och ett område per team, inte en app per team.
2. **Bara teamets egen agent.** I ett teamområde nås bara teamets egen agent. Handläggar-UI:t är försäkringsteamets område, med handläggaragenten.
3. **Flöden från centralen.** Flöden över flera team, först regeländringsflödet, och produktparametrarna startas och drivs från operatörscentralen. `/floden` och `/parametrar` i handläggar-UI:t är tillfälliga. Flödena når motorn genom adaptern `FlowConsole` och behöver inte styrvägens autentisering.
4. **Självständiga agenter.** Agenter får ta uppdrag självständigt, till exempel handläggaragenten när ett ärende registreras. Mandat och budget är desamma som när en människa startar dem, och skrivningar godkänns i kön.

**Motivering:**
- Ett gränssnitt per verksamhetsområde ger tydliga behörighetsgränser.
- En regeländring är ett bolagsbeslut på ledningsnivå och kör compliance och aktuarie, inte handläggaragenten.
- En plattform undviker dubblerad inloggning, design och drift.

**Övervägda alternativ:** *Separata appar per team* – hårdare gränser, men dubblerad inloggning, design och drift. Avvisat. *Flöden kvar i handläggar-UI:t* – fungerar tekniskt, men blandar handläggning av enskilda försäkrade med bolagsbeslut och andra teams agenter. Avvisat.

**Konsekvenser:**
- OC-7 (flöden och produktparametrar) och OC-8 (plattform och teamområden) i projekt 10.
- F5-7 (självständiga ärendekörningar) och en bakgrundsarbetare för agentkörningar i harness.
- `/floden` och `/parametrar` flyttar från handläggar-UI:t till centralen.
- Uppdaterat: `projekt/10_operatörscentral/PROJEKTPLAN.md`, `operatörscentral.md`, `handläggar-ui.md`, `agentekosystem.md`, `flaggskeppsflöde.md` och ATT_GORA.

**Preciserar:** B-017 (människa som fullständig operatör), B-026 (agentekosystemet), B-033 (val D, synkrona körningar, kompletteras med självständiga) och B-035 (UI-sidorna `/floden` och `/parametrar`).

---

### B-035 | 2026-10-25 | Fas 3c: flödesmotor, parametrar som data och en minimal flaggskeppsdemo

**Beslut:** Operatören godkände beslutsförslaget `02_system/flaggskeppsflöde.md` i chatten 2026-10-25, med valen A–L enligt rekommendationerna, och bad om att beslutet loggas. Fas 3c byggs med en minimal flaggskeppsdemo som första mål:

1. **Scenario:** en fiktiv ändring där ordinarie ITP1-premie betalas till och med månaden före 67 år i stället för 66, för premiemånader från 2027-01-01 (val A). Källan är en märkt simuleringskälla, `K-SIM-ITP-2027`, i källregistret och `04_regulatoriskt/03_bevakning/` (val L).
2. **Parametrar som versionerad data:** värden som styr premieberäkningen (premieålder, premiesatser, brytpunkter) lagras i tabellen `product_parameters` med giltighetsintervall, produktregel, källa och beslut. Premiemotorn tar parametrarna som indata och tjänstelagret slår upp dem per premiemånad. Ändringar görs med `schedule_product_parameter_change` (`APPROVAL`) och dras tillbaka med `withdraw_product_parameter_change` (`HUMAN_ONLY`); läsning med `get_product_parameters` (`AGENT`) (val B).
3. **Aktiveringen** läggs av flödesmotorn som förslag under compliance-agentens identitet, länkat till tolkningskörningen, och godkänns i `/godkannanden` (val C).
4. **Ordning:** tolkning → grind → beståndsinsikt → grind (regelbeslut) → operatören för in regeltexten → aktivering → verifiering i systemet (val D). Compliance skriver bara utkast; operatören för in regeltexten (val H).
5. **Flödesmotorn** får egna tabeller i harness – `flows`, `flow_steps` och `flow_gate_decisions` – utanför försäkringstjänstelagret. Grindar binder hashen av det underlag som godkänts (val E). Agentsteg körs synkront när operatören klickar (val F). Körjournalen förblir JSONL och länkas via `run_id` (val J).
6. **Team och poddar:** `compliance` och `aktuarie` med gatewayerna `regelverk` (läsning), `dokument` (utkast) och `bestand` (aggregat i betrodd kod med undertryckning av celler under 10).
7. **Data:** aggregattjänsten provas först i demo och `svc_test` med simulerad roll; operatören skapar `agent_aktuarie` före skarp demo i Lakebase (val I). Demobeståndet utökas med en fiktiv äldre kohort födda 1959–1962, först i demo och `svc_test`, i Lakebase efter backup och OK (val K).
8. **Delegering mellan team (3c-1)** byggs efter demon (val G). Utvecklings- och kommunikationsteamen ingår inte i demon.

**Motivering:**
- Den kortaste vägen till ett visbart flöde från regelverksändring till produktion med människa i loopen.
- Premieåldern och satserna är i dag konstanter i koden, så en antagen regeländring kan bara nå produktion genom en kodändring. Parametrar som data stänger den luckan utan att agenter får ändra kod eller gällande dokument.
- Grindar som binder underlaget gör varje mänskligt beslut spårbart till exakt det som granskades.

**Övervägda alternativ:**

*IBB 2027 som demo* (förslaget i `kallandringar.md`) – minst bygge, men ingen produktregel ändras. *Höjd premiesats under brytpunkten* – berör alla aktiva direkt men är ett avtalsval snarare än nationellt regelverk. Båda kan köras i samma flöde senare.

*Behåll konstanterna och låt utvecklingsteamet ändra koden* – det fullständiga flaggskeppet, men kräver isolerad patch- och releasemiljö. Senare.

*Flödesoperationer i tjänstelagret* – en logg, men blandar verksamhetsområden (`harness.md` §4.3). Avvisat.

*Bygga delegering före demon* – byggordningen i `agentekosystem.md` §12, men demon behöver bara team i följd. Senare.

**Konsekvenser:**
- Byggsteg 3c-P1, 3c-P2, 3c-G, 3c-B, 3c-T, 3c-2, 3c-3 och 3c-V enligt förslagets §11, därefter 3c-1.
- Nya tabeller med migrationer mot Lakebase först efter backup och operatörens OK (AGENTS.md §4.5).
- `databasschema.md`, `tjänstelager.md`, `harness.md`, `agentekosystem.md`, `handläggar-ui.md`, skillkatalogen och operationsförteckningen uppdateras när respektive steg byggs.

**Preciserar:** B-016 (flöden), B-026 (agentekosystemet) och B-028 (tjänstelagret).

---

### B-034 | 2026-10-24 | Digital klarhet som bolagets gemensamma grafiska design

**Beslut:** Operatören valde i chatten 2026-10-24 förslaget **Digital klarhet**
efter en jämförelse av fyra grafiska riktningar och bad uttryckligen att
designspråket sparas i projektet och valet förs in i beslutsloggen.

1. Digital klarhet är bolagets gemensamma grafiska riktning för hemsidor,
   kundportal, handläggargränssnitt, rapporter, dokumentation och presentationer.
2. Uttrycket bygger på indigo, ljusa innehållsytor, DM Sans, tydlig typografisk
   hierarki och mjukare former. Mörka indigoytor kan användas i presentationer.
3. Designgrunden dokumenteras i `06_design/designsprak.md`, med den valda
   visuella referensen i `06_design/digital_klarhet.html`. Första gemensamma
   designvärden finns i `src/design/digital_clarity.tokens.json`.
4. Kommande mallar och gemensamma dokument-/presentationsskills återanvänder
   samma grund oavsett team. Innehåll och detaljnivå anpassas till uppgiften.
5. Införandet sker stegvis. Befintliga gränssnitt anpassas när de vidareutvecklas;
   teknisk webbarkitektur och övrig byggordning består.

**Motivering:**
- Operatören föredrog Digital klarhet bland Nordisk precision, Redaktionell
  elegans, Digital klarhet och Arkitektonisk minimalism.
- Bolaget behöver ett professionellt, modernt och sammanhållet uttryck i alla
  kanaler, även när olika människor eller agenter producerar materialet.
- En dokumenterad grund med gemensamma designvärden minskar risken att varje
  gränssnitt, rapport och presentation får egna stilar.

**Konsekvenser:**
- Designspecifikation v1.0, tokenfil och visuell referens sparas i repot.
- MASTER_CONTEXT, README, agentekosystemets dokumentationsförmåga och ATT_GORA
  hänvisar till den valda grunden.
- Produktionsmallar, gemensamma skills, fullständigt logotyppaket och införande
  i befintliga ytor återstår. Referensen innehåller endast exempeldata.
- B-012 (Markdown som arbetsformat), B-015 (mappstruktur), B-026 (delade poddar)
  och B-029 (Databricks-dashboard) kvarstår; inga externa publiceringar eller
  ändringar i det aktiva handläggargränssnittet görs genom detta beslut.

---

### B-033 | 2026-10-24 | Ärenden (`cases`) som handläggaragentens arbetsenhet och mandat (Fas 5)

**Beslut:** Operatören godkände beslutsförslaget `projekt/01_ärendehantering/ARENDEN_BESLUTSFORSLAG.md` i chatten 2026-10-24, med valen A–H enligt rekommendationerna, och bad om att beslutet loggas. Ärenden införs i försäkringssystemet:

1. **Tabellen `cases`** med typ, status (`open`, `in_progress`, `waiting_approval`, `waiting_info`, `closed`), utfall (`approved`, `rejected`, `supplement_requested`, `manual_review`, `no_action`), berörd försäkrad, försäkring och arbetsgivare, period, kanal, mottagningsdag, referens, tidsfrist och typens uppgifter. Ärendenumret `CASE-NNNNNN` är det som står i `case_id` i tjänstelagrets kontext, godkännandekö och händelselogg.
2. **Historiken** står i `operation_events` via `case_id`; ingen separat händelsetabell (val A).
3. **Typens uppgifter** lagras i `details` (JSONB) och valideras mot en Pydantic-modell per typ (val F). Första och enda typen i v1 är `salary_report` (val C).
4. **Operationer i tjänstelagret:** `create_case`, `list_cases`, `update_case_status` och `close_case` är `HUMAN_ONLY`; handläggaren skapar ärenden i UI:t (val B). `get_case` är `AGENT` och når bara körningens ärende (val G). Agenten kan inte skapa, ändra eller stänga ärenden; harness skriver status efter en körning som systemaktör.
5. **Ärendet är agentens mandat.** Resursmandatet byggs ur ärendet (`scope_for_case`): dess person, försäkringar och arbetsgivare och högst 24 månader. En körning gäller ett ärende.
6. **Första flödet, nytt löneunderlag:** handläggaren registrerar ärendet och startar agenten med en knapp; körningen går synkront i UI:t (val D). Agenten läser, räknar och föreslår registrering. Handläggaren godkänner i kön och stänger ärendet; agentens sammanfattning efter beslutet är en valfri fortsättning (val E).
7. **Demoläget.** Agenten får köras mot UI:ts demobestånd med simulerad databasroll, tydligt märkt (val H).

**Motivering:**
- Agenten behöver en avgränsad arbetsenhet med strukturerade uppgifter i stället för fri text, och handläggningen behöver status och utfall.
- Mandatet ur ärendet gör kundscopet spårbart till ett registrerat underlag.
- Spåren finns redan (`case_id` i kö och logg), så bara tabellen och operationerna tillkommer.
- Utfallen följer regelpaketets ingång (godkänd, avslagen med regelgrund, komplettering, manuell prövning), och avslag och negativa beslut avgörs av handläggaren (PR-ITP1-031).

**Övervägda alternativ:**

*Egen tabell `case_events`* – mer läsbar historik i UI:t, men en andra logg att hålla i synk med `operation_events`. Avvisat i v1.

*Agenten skapar ärenden som förslag, eller automatisk import av arbetsgivarfil* – kräver filformat och inkommande kanal. Senare.

*Agenten startas automatiskt eller i en bakgrundsarbetare* – behövs för flera användare och för att kunna avbryta pågående modellanrop (`harness.md` §6.3). Senare.

*Egna kolumner eller tabell per ärendetyp* – starkare databaskontroll men en schemaändring per ny typ. Avvisat.

*Ärendets uppgifter i uppdragstexten i stället för verktyget `get_case`* – uppgifterna skulle bli fri text i stället för strukturerat verktygssvar. Avvisat.

**Konsekvenser:**
- Byggsteg F5-1–F5-6 enligt förslagets §7: tabell och migration, operationer, harness (`scope_for_case`, `case_number` i resurskontrollen, uppdragsmall), UI-sidor `/arenden`, rättigheter för `agent_forsakring` på `cases` och skarp verifiering i Lakebase, röktest av hela flödet.
- Schemaändringen körs mot Lakebase först efter backup och operatörens OK (AGENTS.md §4.5).
- `databasschema.md`, `tjänstelager.md`, `harness.md`, `handläggar-ui.md`, skillkatalogen och operationsförteckningen uppdateras när respektive steg byggs.
- Ärendetyperna `complaint` och `general`, inkommande kanaler, regelstyrda ärenden (PR-ITP1-017), bakgrundsarbetare, besked till kund och lagringspolicy för ärendenas uppgifter läggs i ATT_GORA.

**Preciserar:** B-020 (handläggar-UI före kundportal), B-026 (handläggaragenten) och B-028 (tjänstelagret).

---

### B-032 | 2026-10-12 | Tjänstelagrets operationer för anslutning, stamdata och arbetsgivare (Fas 4)

**Beslut:** Operatören godkände beslutsförslaget `projekt/01_ärendehantering/OPERATIONER_BESLUTSFORSLAG.md` i chatten 2026-10-12. Modellvalen A–D följde rekommendationerna, och operatören bad om att beslutet loggas. Tjänstelagret (B-028) utökas för handläggar-UI:t (Fas 4) med följande operationer:

1. **`enroll_insured_person`** (`write`, PR-ITP1-012/013, `APPROVAL`). Ansluter en ny anställd. Den försäkrade, en försäkring, förmånen ålderspension och läget `premium_paying` skapas i en transaktion. Försäkringens `signed_date` och `start_date` sätts till den dokumenterade ITP1-tillhörighetsdagen. En person under 25 år ansluts med `premium_paying` från tillhörighetens start, och ordinarie premie börjar i 25-årsmånaden (val A). Anslutningen skapar ingen premie och skickar inget försäkringsbesked.
2. **`update_current_salary`** (`write`, ingen produktregel, `HUMAN_ONLY`). Aktuell lön på personen är stamdata och hålls isär från pensionsmedförande lön (PR-ITP1-014, B-030). Ändringen skapar varken löneunderlag eller premie (val C).
3. **`update_contact_details`** (`write`, PR-ITP1-031, `HUMAN_ONLY`). Gäller e-post och telefon. Namn och personnummer ändras inte här.
4. **`register_employer`** (`write`, PR-ITP1-012, `HUMAN_ONLY`) och **`list_employers`** (`read`, `AGENT`, utan kontaktpersoner). Ändring av arbetsgivarens uppgifter skjuts upp (val D).
5. **Blockeras med skäl och regel** (val B):
   - återanställning och arbetsgivarbyte, eftersom anställningshistorik saknas;
   - anslutning av VD, ägare, utlandsanställd eller den som avstått, som kräver uttryckligt beslut;
   - framtida datum;
   - anslutning från 66 år (PR-ITP1-016).
6. **Ingen schemaändring.**

**Motivering:**
- Handläggar-UI:t får bara anropa tjänstelagret (B-028), och de här åtgärderna behövs för vardaglig handläggning.
- Modellen bär operationerna utan schemaändring. Det som kräver anställnings- eller lönehistorik blockeras i stället för att skriva över data.
- Om aktuell lön blandades ihop med pensionsmedförande lön skulle premieunderlaget bli fel, och det avvisade B-030 redan.
- Byte av kontaktuppgifter och nya försäkringstagare är känsliga respektive avtalsmässiga. De avgörs av en människa tills det finns verklig autentisering och en produktregel.

**Övervägda alternativ:**

*Blockera anslutning under 25 år, eller införa ett nytt läge före premieåldern* – den första varianten strider mot PR-ITP1-012, där avtal får registreras före premieåldern. Den andra kräver schemaändring utan motsvarande nytta, eftersom premiemotorns åldersfönster redan ger noll premie. Avvisat.

*Skriva över arbetsgivare och datum vid återanställning* – historiken skulle tappas. Avvisat.

*Ge aktuell lön en egen regel så att agenter kan uppdatera den* – kräver en dataregel från delprojekt 4. Avvaktar.

**Konsekvenser:**
- Åtkomstregistret har fått fem rader och förteckningen `tjänstelager_operationer.md` är genererad om. Stödda och blockerade fall står i `02_system/tjänstelager.md` §9.2 och sidorna i `02_system/handläggar-ui.md`.
- **Verifierat 2026-10-12.** Testat mot SQLite och mot den isolerade Postgres-databasen `svc_test`, inklusive samtidiga anslutningar. Därefter skarpt i Lakebase efter backup `backups/20261012T193537Z`, med verifieringsposten AL-000499.
- **Läsoperationer för kön och loggen.** I samma leverans byggdes `list_approval_requests`, `count_approval_requests` och `get_operation_events`, alla `HUMAN_ONLY`. Det skedde inom ramen för Fas 4: listor och sökningar i UI:t ska vara läsoperationer med rad i registret.
- **Följdpunkter i ATT_GORA:**
  - anställningshistorik
  - lönehistorik för aktuell lön
  - namnbyte
  - ändring och avslut av arbetsgivare
  - försäkringsbesked vid anslutning
- Genomfört i commits `7f6cb34`–`244d58a` på branch `claude/handlaggare-ui-v1-1fa1e7`.

**Preciserar:** B-028 (tjänstelagrets operationer och registret) och B-030 (skillnaden mellan aktuell lön och löneunderlag).

---

### B-031 | 2026-10-12 | Produktpaket PR-ITP1 v1.0 infört, gäller från 2026-11-01

**Beslut:** Operatören antog i chatten 2026-10-12 det samlade införandeförslaget i `projekt/04_produktregelverk/PAKET_BESLUTSFORSLAG.md` (”ja”). Artificiellalectas produktunderlag för traditionell ITP1 ålderspension fastställs som produktpaket PR-ITP1 v1.0:

1. **Innehåll:** produktregler PR-ITP1-001–034, försäkringsvillkor v2.0, aktuariell grund v1.0 och parameterregistret. Endast ålderspension utan efterlevande- eller återbetalningsskydd erbjuds. B-002, B-003, B-021, B-022 och B-027 består.
2. **Grunder:** SIM-G-2026-01 (garanti), SIM-B-2026-01 (utbetalning) och SIM-R-2026-01 (arvsvinst): SCB:s dödsrisker 2025, unisex 50/50, 1,5 % årlig förbättring, 20 % extra livslängdsmarginal för garanti och utbetalning, noll nettoränta och explicit oändlig högålderssvans. Grunderna är bestämda simuleringsantaganden, inte professionellt kalibrerade marknadstariffer.
3. **Produktval:** de val som listas i paketförslagets tabell, bland annat tidigaste uttag månaden efter 55 år med pensioneringsprövning före 66, minst 60 månaders tidsbegränsad utbetalning, högst tre deluttag, paus i hela månader utan avgift, utbetalning första bankdagen efter pensionsmånaden, arvsvinst bara av faktiskt frigjort kapital, och att bolaget finansierar garantiunderskott med separat bokfört eget kapital.
4. **Giltighet:** paketet gäller nya produktbeslut och händelser i simuleringen från **2026-11-01**. Till dess är reglerna *kommande*. Äldre transaktioner skrivs inte om; importerad rätt behåller sin ursprungsgrund. SIM-HIST används bara vid separat, uttryckligt beslutad omgenerering av ett märkt syntetiskt scenario.
5. **Registrering:** raden `**Införandebeslut:** B-031 | **Gäller från:** 2026-11-01` i `01_domän/produktregler/README.md`. Tjänstelagret (`services/rules.py`) läser raden, så att inga PR-filer behöver godkännas separat.

**Motivering:**
- Paketet är ett sammanhängande kontrakt; att anta det som helhet undviker motsägelser mellan delvis godkända regler (PR-ITP1-032).
- Tjänstelagret kräver godkända och giltiga produktregler innan agenter får röra skrivande operationer (B-028). Utan införande hade skrivoperationerna förblivit *endast handläggare* för agenter oavsett registret.
- 2026-11-01 är den dag villkor v2.0, aktuariell grund och leveranskontrollens räkneexempel utgår från. Ett datum framåt ger en tydlig gräns mot den genererade historiken 2023–2026.

**Övervägda alternativ:**

*Gälla från beslutsdagen* – snabbare, men bryter mot dokumentens datum och räkneexemplen. Avvisat.

*Godkänna regel för regel* – reglerna förutsätter varandra (bland annat premie-, pensions- och betalningsförlopp), och delvis godkända paket kan ge motsägelser. Avvisat.

**Konsekvenser:**
- Från 2026-11-01 gäller registrets nivåer för agenter: `register_salary_report` och `set_policy_paid_up` blir `APPROVAL`, `correct_premium_transaction` förblir `HUMAN_ONLY`. Före dess är reglerna *kommande* och skrivningarna *endast handläggare* för agenter. Handläggare påverkas inte (B-017). Inga agenter är byggda än, så ändringen märks först med harness (Fas 3b).
- Händelseloggen anger från och med nu att paketet är infört genom B-031.
- Beslutet ändrar ingen kod, inget databasschema och inga befintliga data. Regelstyrda operationer (uttag, paus, garanti, pensionsbelopp, avslut) är fortfarande obyggda; reglerna är nu godkända specifikationer för det bygget.
- Ingen verklig produkt lanseras. Professionell tariff-, bestånds- och solvensvalidering och verkligt tillstånd hör till separata verksamhetsprocesser.
- Den genererade förteckningen `02_system/tjänstelager_operationer.md` beror på dagens datum och genereras om 2026-11-01 (ATT_GORA).
- Status är uppdaterad i paketets README, villkoren, den aktuariella grunden, paketförslaget, delprojekt 4:s plan, MASTER_CONTEXT, ATT_GORA och tjänstelagrets dokumentation.

**Preciserar:** B-027 (garantimodellen, vars tariff och införande nu är beslutade genom SIM-G-2026-01) och B-028 (regelgolvet för agentåtkomst). B-021:s villkor v1.0 ersätts av v2.0 från 2026-11-01; B-021:s förenklingar består.

---

### B-030 | 2026-10-11 | Tjänstelagrets första skrivoperationer: löneunderlag, fribrev och premierättelse (Fas 1f T3)

**Beslut:** Operatören valde modell och avgränsning för de första skrivoperationerna i tjänstelagret (B-028) i chatten 2026-10-11 och bad att beslutet loggas.

1. **Löneunderlag.** `register_salary_report` ersätter den planerade `register_salary_change` och skriver till en ny tabell `salary_reports`. Tabellen innehåller pensionsmedförande lön (PR-ITP1-014) per person, arbetsgivare och utbetalningsmånad. Den är append-only och versionerad: en rättelse är en ny version som pekar på den den ersätter. En uttryckligen rapporterad noll skiljs från en saknad rapport. Underlaget hålls isär från aktuell lön på personen och från premien. Registreringen skapar ingen premie och räknar inte om gamla premier.
2. **Fribrev.** `set_policy_paid_up` registrerar arbetsgivarens avanmälan (anställningens sista dag) och fribrev från dagen efter, i samma transaktion och i befintlig `policy_states`. Operationen gäller bara försäkringar vars pension inte har startat, och den tillåter ingen framtidsdatering.
3. **Premierättelse.** `correct_premium_transaction` bevarar ursprungsraden och skapar en länkad `adjustment`-rad via den nya kolumnen `premium_transactions.corrects_transaction_id`. Premien räknas om med premiemånadens IBB. Operationen stöder ej mottagen premie och tillägg på mottagen premie. Minskning av redan mottagen premie blockeras tills kapitalandel och historisk garantidel spåras. Operationen är *endast handläggare* (`HUMAN_ONLY`).
4. **`terminate_policy` skjuts upp.** Slutavräkning (PR-ITP1-027) och dödsfallsavräkning (PR-ITP1-010) byggs med pensions- och betalningsmotorn, inte som en lägesändring.
5. **Verifiering.** Postgres-specifika tester körs mot en isolerad testdatabas, `svc_test`, i Lakebase-projektet. Migrationen mot Lakebase körs efter granskning. Inget skrivprov görs mot beståndet.

I åtkomstregistret är `register_salary_report` och `set_policy_paid_up` `APPROVAL`. Genom B-028:s golv är de ändå `HUMAN_ONLY` för agenter tills PR-ITP1 v1.0 är infört.

**Motivering:**
- PR-ITP1-014 avser faktiskt utbetald lön per månad. En avtalad lön från ett visst datum är inte pensionsmedförande underlag, och PR-ITP1-014/017 kräver versioner och uttrycklig noll.
- Fribrev utan registrerat anställningsslut skulle ge motsägande data. Ett läge per försäkring kan inte uttrycka fribrev under pågående pension (UTTAG_GEMENSAMT), så avgränsningen hindrar att pensionsrätten skrivs över.
- En kolumn ger en uttrycklig länk mellan rättelse och ursprung som databasen kan säkra, och den skyddar mot dubbel rättelse. Återtag av mottagen premie kräver underlag som modellen saknar (PR-ITP1-019 p.3, PR-ITP1-020). Det är bättre att blockera än att gissa en andel av dagens kapital.
- Ett avslut genom att sätta läget `terminated` skulle kunna dölja kapital och uppkomna anspråk.

**Övervägda alternativ:**

*Bara aktuell lön på personen* – det är inte underlag enligt PR-ITP1-014, och utan produktregel hade operationen blivit `HUMAN_ONLY`. Avvisat.

*Bara lägesändring för fribrev* – anställningen hade sett ut att fortsätta. Avvisat.

*Separat premieläge nu* – korrekt, men hör ihop med uttagsmodellen och tas där.

*Länk bara i `calculation_basis`* – ingen schemaändring, men länken kan inte säkras i databasen. Avvisat.

**Konsekvenser:**
- `databasschema.md` §8 och §8b och `tjänstelager.md` §6.1 och §9.1 (stödda och blockerade fall) är uppdaterade. Den genererade förteckningen `tjänstelager_operationer.md` visar effektiv agentnivå per operation.
- Migrerat i Lakebase 2026-10-11 efter backup `20261011T151353Z`. Det gjordes med det kontrollerade skriptet `scripts/migrate_t3_schema.py` och inte med Alembic, som `databasschema.md` §12 planerade. Alembic föreslås som ett eget steg.
- Godkännandets transaktionsgräns rättades i samma leverans: en transaktion per anrop, utan schemaändring.
- ATT_GORA följer upp separat premieläge, premie ur löneunderlag, `terminate_policy` och ett godkännandegränssnitt för handläggaren.
- Genomfört i commits `a17a174`–`4419bb4` på branch `claude/service-layer-write-ops-7c7602` och mergat till main.

**Preciserar:** B-028 (T3:s operationer). B-022:s försäkringsmodell kvarstår.

---

### B-029 | 2026-10-11 | Databricks AI/BI-dashboard med gemensamma mått och Genie för insikter

**Beslut:** Operatören godkände inriktningen i chatten 2026-10-11 och bad att den sparas i beslutsloggen.

1. Bolagets dashboard byggs i Databricks AI/BI. Den används först direkt i Databricks och kan senare bäddas in som en flik i operatörsgränssnittet.
2. Ett gemensamt, granskat analysunderlag med definierade vyer och mått försörjer dashboarden, Genie/agentfrågor och kontrollerade rapporteringsunderlag. Definitionerna ska versionshanteras och vara spårbara till källa, datum/period och beräkningsgrund.
3. Försäkringssystemet levererar bestånd och betalningar, kapitalförvaltningen levererar kapitalvärden och aktuariella beräkningar levererar bland annat FTA, åtaganden och riskmått. Dashboardens frågor och uppdateringar läser dessa underlag; de ersätter inte beräkningsmotorerna.
4. Genie används för följdfrågor, undersökning och förklaring över det definierade underlaget. Bolagets agenter använder en behörighetsstyrd integration enligt tjänste-/skillarkitekturen. Genie Code kan hjälpa att föreslå vyer och dashboards; gemensamma definitioner granskas före publicering.
5. Scenarioverktyg beräknar och sparar resultat med antaganden och version, varefter dashboarden kan jämföra bas och scenario och Genie hjälpa till att förklara effekten. Regeländring är ett av flera användningsfall för denna förmåga.
6. Formell rapportering använder kontrollerat underlag för en bestämd period och mottagare. Granskning och operatörens godkännande krävs före extern inlämning enligt befintliga regler.

**Motivering:**
- En gemensam grund ger samma betydelse åt nyckeltal i dashboard, agentsvar och rapporter.
- Databricks kan hantera analysfrågor och visualiseringar, så projektet kan fokusera på datakvalitet, beräkningar och användbara insikter.
- Genie ger möjlighet att undersöka förändringar och ställa följdfrågor utöver fördefinierade diagram.
- Återanvändbar analys och rapportering stödjer bolagsvisionen bättre än fristående verktyg för enskilda regelscenarier.

**Konsekvenser och kvarstående frågor:**
- Projekt 2 äger BI-inriktningen; detaljerade dashboardmått beskrivs som förslag i `projekt/02_bi_insikter/DASHBOARD_DESIGN.md`.
- Funktioner, behörigheter, kostnader, SQL Warehouse och Genie-stöd verifieras i den faktiska Databricks-miljön före implementation. Beslutet skapar inga konton eller resurser.
- Direkt läsning kontra historiska ögonblicksbilder, datamodell, metric views, uppdateringsfrekvens, agentintegration och inbäddningslösning preciseras i fortsatt design. B-009/B-025 och B-028 kvarstår; teknisk Genie-integration ska hantera relationen till dessa principer.
- FTA-/riskgrunder, tillämpliga kapitalkrav, konsolideringsmodell, rapportmottagare och leveransformat beslutas separat. Saknade beräkningar visas som ej beräknade, inte som noll.
- Det befintliga IBB-verktyget är ett avgränsat scenarioexempel, inte hela BI-arkitekturen. Ingen Databricks-dashboard eller Genie-integration är driftsatt genom detta beslut.

**Preciserar:** Den öppna BI-arkitekturfrågan i B-024. Produktscope och byggordning ändras inte.

---

### B-028 | 2026-10-11 | Byggordning och tjänstelager: försäkringssystem före agentlager, en väg in för människor och agenter

**Beslut:**
1. Byggordningen blir: försäkringssystemets kärna (Fas 1 inkl. tjänstelagret, Fas 1f) → handläggar-UI (Fas 4) → agentlagret (harness, Fas 3b, därefter handläggaragenten, Fas 5) → delegering och flöden (Fas 3c). Kapitalförvaltningen (Fas 2) går parallellt. Fasnumren behålls.
2. Alla operationer mot försäkringssystemet går via ett gemensamt tjänstelager (`src/services/`) som används av handläggar-UI:t, agenter (via skills i harness) och skript. Varje operation deklarerar indatamodell, typ (`read`/`compute`/`write`/`external`), produktregler den implementerar och PII.
3. Agentåtkomst per operation i tre nivåer: `AGENT` (agent får utföra), `APPROVAL` (agent får föreslå, handläggare godkänner) och `HUMAN_ONLY` (endast handläggare). Nivåerna anges i **ett centralt register** (`src/services/access_register.yaml`) så att de kan ändras på ett ställe utan att röra operationskoden; ändringar går via commit och merge. Effektiv nivå är den strängaste av registrets nivå och tre golv: operation som saknas i registret → `HUMAN_ONLY`; `external` → minst `APPROVAL`; `write`/`external` vars produktregler inte har granskningsstatus `godkänd` → `HUMAN_ONLY`. Verkställs i tjänstelagret vid varje anrop och i harness (`HUMAN_ONLY` visas aldrig som verktyg).
4. Godkännandekön och en append-only händelselogg (aktör, förslagsställare, godkännande, produktregler, motivering) ligger i tjänstelagret. Det justerar B-026, där harness skapade godkännandeärenden.
5. Tjänstelagret byggs i den tvärgående chatten; Codex fortsätter med produktreglerna i delprojekt 4. Regelspecifika operationer byggs när reglerna är godkända.

**Motivering:**
- Agentverktyg ska kapsla in operationer som redan finns och används av människor, inte gissade kontrakt – en harness byggd först hade bara haft premiemotorn att koppla in
- B-017: allt en agent kan göra ska handläggaren kunna göra – operationerna behöver finnas för människan först, och samma väg in ger samma spår
- Behörighet i strukturen: flaggan *endast handläggare* verkställs i tjänstelagret oavsett hur anropet kommer, inte bara i harness eller prompt
- Ett centralt register gör agentgränserna lätta att överblicka och ändra vid ett senare tillfälle, utan att leta i koden
- Kopplingen till regelstatus gör att agenter bara rör det som vilar på en godkänd produktregel – arbetet i delprojekt 4 styr direkt vad agenter får göra
- En implementation per affärsregel, spårbar till produktregel-id – grunden för flaggskeppsflödet regel → kod
- Händelseloggen ger BI (delprojekt 2) historik att analysera

**Övervägda alternativ:**

*Harness först (Fas 3b direkt efter AI-lagret)* – avvisat: bygger verktygskontrakt utan riktiga operationer.

*Flaggan bara i harness eller `ecosystem.yaml`* – avvisat: skyddar bara agentvägen; en felkopplad skill eller ett skript kunde kringgå den.

*Nivån i koden vid varje operation* – avvisat: spritt över många filer, svårare att överblicka och ändra.

*Två nivåer (tillåten/förbjuden)* – avvisat: förslag med godkännande behövs för vardagsärenden (t.ex. lönändring) så att agenter kan förbereda arbete utan att utföra det.

**Konsekvenser:**
- `02_system/tjänstelager.md`, ny sektion Fas 1f i `ATT_GORA.md` (T1–T4), fasplanen och `agentekosystem.md` §12 uppdaterade; ny designprincip MASTER_CONTEXT §3.8
- Handläggare får utföra alla operationer (B-017); registret kan senare utökas med handläggarroller om bolaget får fler personer
- Tjänstelagret läser produktreglernas granskningsstatus (`utkast`/`godkänd`/`ersatt`) ur `01_domän/produktregler/` – formatet ägs av delprojekt 4 och bör inte ändras utan att tjänstelagret anpassas
- Nya tabeller `operation_events` och `approval_requests` – dokumenteras i `databasschema.md` innan de skapas (AGENTS.md §4.5)
- Punkt 3 (registret och regelgolvet) tillkom vid operatörens godkännande av förslaget

---

### B-027 | 2026-10-11 | Premiebaserad garanti för traditionell ITP1-pension

**Beslut:** Operatören godkände garantiförslaget i chatten 2026-10-11 (”vi går på ditt förslag”). Den traditionella ITP1-produkten ska ha en intjänad pensionsgaranti. Hela den mottagna nettopremien är garantigrundande med 0 % nettoränta i garantitariffen. Garantin avser pensionsförmånen för avtalad plan, inte ett oföränderligt kontosaldo eller återbetalning till efterlevande.

Varje garantidel behåller sina ursprungliga antaganden. Ändrad uttagsplan ska ge en spårbar omräkning enligt en granskad aktuariell metod. Kapital, garanterad pension och möjligt rörligt pensionstillägg hålls åtskilda. Automatisk garantiförstärkning ingår inte i första modellen. Kapitalavgiften enligt B-021 och produktscope enligt B-002/B-022 kvarstår.

**Motivering:**
- Premiebestämdhet anger hur premien bestäms och utesluter inte en garanti i traditionell försäkring.
- En garantigrund på hela nettopremien ger ett begripligt produktval för simuleringen; nivån är bolagets val, inte ett här fastställt universellt ITP-krav.
- Versionsspårade garantidelar skyddar tidigare intjänande när antaganden för nya premier ändras.

**Konsekvenser:**
- Produktinriktningen är beslutad; `01_domän/aktuariell_grund.md` och PR-ITP1-008/009 är fortfarande modell-/regelutkast som kräver parameter- och riskgranskning före införande.
- Unisexdödlighet, livslängdsmarginal, högåldersmodell, utbetalningsgrund, kostnad/skatt, dödsfall/arvsvinster och underskottsfinansiering återstår.
- Giltighetsdag och behandling av befintlig mockhistorik beslutas separat. Beslutet skapar inte garantier retroaktivt och godkänner ingen databasändring eller driftsättning.
- §2.3 i villkorsversion 1.0 ska ersättas när en ny villkorsversion införs. Villkorstext och kvarstående införandekrav finns i `projekt/04_produktregelverk/GARANTI_BESLUTSFORSLAG.md`; ingen ny villkorsversion träder i kraft genom detta beslut.

**Förtydligar:** B-021:s traditionella sparform. Övriga produktavgränsningar och avgifter ändras inte.

---

### B-026 | 2026-10-11 | Agentekosystem: team med ledande agent som orkestrerare, skill-poddar som behörighetsenhet

**Beslut:**
1. Agenter organiseras i team per funktionsområde. Teamets orkestrerare är dess ledande agent – inga separata chefsagenter. Andra team och flöden når ett team via den ledande agenten; eskalering till compliance är alltid tillåten (B-011). Teamindelning: sju team (`forsakring`, `kommunikation`, `kapital`, `aktuarie`, `compliance`, `ekonomi`, `utveckling`) för de tio befintliga agenterna.
2. Skills paketeras i skill-poddar som är behörighetsenheten i körning: gemensam dataåtkomst, PII-klass, högsta sidoeffektsklass och ägarteam. Agenter får poddar, inte enskilda skills.
3. Varje skill deklarerar sidoeffektsklass (`read`/`compute`/`write`/`external`). `external` körs aldrig direkt av en agent utan blir ett godkännandeärende (§3.5).
4. Samverkan sker genom strukturerad delegering mellan ledande agenter och deterministiska flöden med persisterat tillstånd och godkännandesteg (B-016).
5. Modellval via roller per agent och flödessteg; nycklar per team via AI-lagret (B-025); poddar kan exponeras som MCP-servrar för operatören och externa AI-verktyg (B-017, B-024).

**Motivering:**
- Speglar avdelningar i ett riktigt bolag utan att bryta B-008 – ledande agent som orkestrerare ger ingen extra agent och ingen extra överlämning
- Behörighet ligger i struktur (monterade poddar, databasroller), inte i prompt (B-006/B-007)
- Spårbarhet och mänsklig kontroll: körjournal per körning, externa handlingar godkänns av operatören (B-016, §3.5)
- Samma förmågor för operatören och externa AI-agenter genom MCP-exponering (B-017, B-024)

**Övervägda alternativ:**

*Separat chefsagent per team* – fördubblar antalet agenter, lägger en överlämning med kontextförlust framför varje uppgift och bryter B-008. Avvisat.

*Behörighet per enskild skill* – tio agenter × alla skills blir ohanterligt att granska. Avvisat till förmån för poddar (enskilda skills kan fortfarande nekas).

*Kommunikationsagenten under `forsakring`* – tvingar andra team att gå via handläggaragenten för att nå utgående kanaler. Avvisat; kommunikation blir eget enagentsteam och bolagets enda väg ut.

**Konsekvenser:**
- Ramverket beskrivs i `02_system/agentekosystem.md`
- Byggordning: Fas 3b (agent-runtime v1: `ecosystem.yaml`, skill-register, poddar, agentloop, körjournal, godkännandekö) före Fas 5; Fas 3c (delegering + flödesmotor med persisterat tillstånd) inför flaggskeppsscenariot
- Skillkatalogen får en pod-kolumn när runtime byggs
- En egen Lakebase-roll för PII-poddar sätts upp av operatören när den första sådana podden byggs
- Öppna frågor (internrevision som eget team, lagring av journal och godkännandekö, format för agentdefinitioner) listas i `agentekosystem.md` §13
- Genomfört i commits `5de60bc` och `cdc1021` på branch `claude/ai-abstraktionslager-b69434`

---

### B-025 | 2026-10-11 | AI-abstraktionslager: egen tunn wrapper ovanpå officiella SDK:er

**Beslut:** AI-abstraktionslagret (B-009) byggs som en egen tunn wrapper i `src/ai/` ovanpå leverantörernas officiella SDK:er – Anthropic (Messages API) och OpenAI (Responses API). Agent- och skillkod anropar bara `ai`-paketet och väljer modellroll (`fast`/`standard`/`deep`), aldrig modell-ID. Rollerna mappas till modeller i `src/ai/ai_config.yaml`, var och en med reservmodell hos den andra leverantören. API-nycklar följer konventionen `<NYCKELVARIABEL>_<TEAM>` med den gemensamma nyckeln som reserv.

**Motivering:**
- LiteLLM: stort beroendeträd och en supply chain-incident på PyPI i mars 2026 (versioner som stal hemligheter) – lagret hanterar per definition våra API-nycklar. OpenAI-formatet som minsta gemensamma nämnare läcker Anthropic-specifika parametrar till anropande kod
- OpenRouter: tredje part i dataflödet för alla promptar (biträde, jfr B-006), avgift, ersätter direkta leverantörsnycklar
- Egen wrapper: ca 1 000 rader, bara officiella SDK:er som beroenden, nativa funktioner per leverantör, testbar med fejkleverantör, bygger vidare på agent-factory
- Två leverantörer motiverar inte ett bredare ramverk

**Övervägda alternativ:**

*LiteLLM (SDK eller proxyserver)* och *OpenRouter* – avvisade enligt ovan. Båda kan läggas till senare som adapter bakom samma gränssnitt utan att agentkod påverkas.

**Konsekvenser:**
- `src/ai/` med kanoniska typer, adaptrar, konfiguration, anropslogg (`logs/ai_calls.jsonl`) och 81 tester; specifikation och utvärdering i `02_system/ai_abstraktion.md`
- Beroenden `anthropic>=1.13,<2`, `openai>=3.28,<4`, `pydantic`, `pyyaml`; SDK:erna får bara importeras i `src/ai/providers/`
- Röktest mot riktiga API:er (`scripts/smoke_test_ai.py`) godkänt 2026-10-11: båda leverantörerna, strukturerade svar, verktygsloop och fortsättning hos andra leverantören mitt i en verktygsloop (kostnad ca 0,02 USD)
- Omprövas om fler än 3–4 leverantörer behövs eller om nycklar ska delas centralt av många användare
- Genomfört i commits `b9f1cac` och `37d4623` på branch `claude/ai-abstraktionslager-b69434`

---

### B-024 | 2026-10-11 | Programvision utökad till AI-native bolag + delprojektstruktur

**Beslut:**
1. Projektets vision utökas från att bara bygga produkten (ålderspension ITP1, B-002 oförändrat som produktscope) till att också bygga och visa upp ett **AI-native tjänstepensionsbolag** – en organisation där agentteam utför avdelningarnas löpande arbete, med ett **flaggskeppsscenario**: en regelverksändring tolkas till produktregler, produktregler produktionssätts i försäkringssystemet, och agenter tar fram en business insight om hur ändringen påverkar det befintliga beståndet.
2. Arbetet struktureras i åtta namngivna delprojekt (ärendehantering, BI & insikter, kundportal, produktregelverk, kapitalförvaltning, avdelningsfunktioner, kundchattbot, företagsöversikt – se `MASTER_CONTEXT.md` §4b). Agentekosystem-design (orkestrerare, skill-poddar, modellval/nycklar) är inte ett nionde delprojekt utan ett tvärgående arkitekturramverk alla delprojekt ska byggas enligt.
3. Delprojekt får en fysisk projektmapp i repo-roten (`projekt/<nr>_<namn>/`) med egen `PROJEKTPLAN.md` (scope, status, beroenden, öppna frågor). Redan påbörjade delprojekt (1 ärendehantering, 4 produktregelverk, 5 kapitalförvaltning) flyttar inte redan byggd dokumentation/kod dit – projektmappen pekar bara till var den befintliga grunden ligger. Ny kod för alla delprojekt läggs ändå i det centrala `src/`-trädet (B-015), inte i egna per-projekt-src-mappar.

**Motivering:**
- Karl vill kunna demonstrera ett strömlinjeformat, säkert flöde från nationell regelverksändring till produktionssatt systemändring och affärsinsikt – det kräver att fler funktionsområden (BI, kundportal, kapitalförvaltningsanalys, avdelningsfunktioner) faktiskt byggs, inte bara premiemotorn
- Fysisk mappisolering per delprojekt ger ett avgränsat uppdrag som kan ges till Codex eller en egen Claude Code-session utan att den behöver känna till hela repot
- Att inte flytta redan byggd kod/dokumentation undviker att riva upp fungerande Fas 1/Fas 2/regelverksarbete bara för att passa en ny mappkonvention
- Att göra agentekosystem-design till ett tvärgående ramverk istället för ett nionde delprojekt undviker cirkularitet (vem bygger det åt sig själv)
- Kod kvar i det centrala `src/`-trädet bevarar B-015:s princip om en enda importerbar paketrot – annars hade projektmapparna brutit mot den separationen

**Övervägda alternativ:**

*Bara dokumentera i ATT_GORA, ingen ny mappstruktur* – enklast, men ger inget fysiskt avgränsat uppdrag att lämna över till Codex/Claude Code. Avvisat.

*Flytta all befintlig kod/dokumentation in i de nya projektmapparna direkt* – mest konsekvent mappstruktur, men stor omstrukturering utan tillräcklig nytta just nu för redan fungerande delar (Fas 1/Fas 2). Kan omprövas senare om projektmapparna visar sig behöva äga mer än bara planeringsdokument.

**Konsekvenser:**
- `MASTER_CONTEXT.md` uppdaterat: ny programvision + flaggskeppsscenario (§1), ny delprojektöversikt (§4b), ny mappstruktur-post för `projekt/` (§7)
- `ATT_GORA.md` kompletterat med en mappning mellan befintlig fasplan och de nya delprojekten, utan att prioritetslistorna i övrigt ändrats
- Ny mapp `projekt/` med en `PROJEKTPLAN.md` per delprojekt (1–8)
- BI-arkitektur (delprojekt 2), kapitalförvaltningens analysgränssnitt (delprojekt 5) och agentekosystem-designen (ramverket) är uttryckligen öppna frågor som inte löses av detta beslut – de tas i kommande sessioner
- Redan genomfört i commit `9bbbc48` på branch `claude/att-gora-lista-innehal-da0702`

---

### B-023 | 2026-10-11 | Parallellt arbete mellan Claude Code och Codex + git-skrivningar tillåtna för agenter

**Beslut:**
1. En gemensam regelfil `AGENTS.md` införs för parallellt arbete mellan flera AI-verktyg (Claude Code/Cowork och Codex) i samma repo. Filen innehåller Codex-specifika arbetsregler (motsvarande `CLAUDE.md`) samt ett gemensamt avsnitt (§4) med regler för: branch per uppgift, uppdelning av arbete efter beroenden (inte bara filer/mappar), hantering av delade dokument (MASTER_CONTEXT/BESLUTSLOGG/ATT_GORA), synk mot main innan beroende uppgifter, databaskoordinering mot Lakebase, och integration till main. `CLAUDE.md` hänvisar till `AGENTS.md` i sin läslista (§1).
2. Regeln "inga git-skrivningar från Cowork-sandboxen" tas bort. Claude Code och Codex får köra `add`/`commit`/`push` på sin egen arbetsbranch utan att vänta på godkännande i förväg, och mergea in i `main` själva – men bara efter ett explicit muntligt OK från operatören i chatten för den specifika mergen. Force-push och historieomskrivning kräver fortfarande explicit instruktion per åtgärd.

**Motivering:**
- Karl vill jobba parallellt med Claude Code och Codex utan att de krockar, och utan att manuellt klippa-och-klistra git-kommandon för varje ändring – det bromsar ett projekt där målet är att vara snabbfotad
- Den gamla git-skrivningsregeln byggde på ett specifikt tekniskt problem i Cowork-sandboxens Linux-mount (stale lockfiler). Det är inte visat att samma begränsning gäller i andra miljöer, och ett verifieringsförsök i den aktuella Claude Code-miljön (commit + push + merge + push till main) visade inga problem
- Sandbox-scope (B-003) gör risken av en felaktig commit/merge låg jämfört med ett produktionssystem med verkliga konsekvenser
- Mänsklig kontroll bevaras där det är viktigast: main-merge kräver fortsatt explicit muntligt godkännande, destruktiva git-operationer kräver fortsatt explicit instruktion per åtgärd

**Övervägda alternativ:**

*Full autonomi även till main* – agenten hade mergat utan godkännande alls. Snabbast, men ingen mänsklig kontrollpunkt innan en ändring når main. Avvisat.

*Fortsatt manuell klipp-och-klistra för alla git-kommandon* – säkrast, men för långsamt med två parallella AI-verktyg.

**Konsekvenser:**
- `CLAUDE.md` och `AGENTS.md` uppdaterade och mergade till main (commit `ecefc17`)
- Codex-worktreen måste själv hämta in senaste main för att få de nya reglerna (se instruktion given till Codex samma dag)
- Om stale lockfiler eller korrupt index trots allt dyker upp i en specifik miljö: agenten stoppar omedelbart och flaggar, återställer inte den gamla regeln på eget bevåg

---

### B-022 | 2026-07-12 | Försäkringsmodell med förmåner och tillståndsperioder

**Beslut:** Försäkringsdatamodellen struktureras i tre nivåer med en parallell tidslinje:

1. **`policies` (försäkringar):** en person kan ha **flera** försäkringar. Tabellen bär identitet (försäkringsnummer, produktkod, tecknings- och ikraftträdandedatum) – **ingen statuskolumn**.
2. **`policy_benefits` (förmåner):** försäkringens innehåll modelleras som förmåner med egna start-/slutdatum, typspecifika parametrar (JSONB) och **egna premietransaktioner** (`premium_transactions.benefit_id`). I nuläget endast premiebestämd ålderspension (`retirement_dc`); TGL och familjeskydd är förberedda som typer.
3. **`policy_states` (lägen):** försäkringens läge över tid som tillståndsperioder (`premium_paying`, `paid_up`, `in_payout`, `payout_paused`, `terminated`) med `valid_from`/`valid_to`. Öppen rad = nuläge.

**Motivering:**
- Speglar hur verkliga försäkringssystem modellerar: försäkring → förmåner → tillstånd. När TGL/familjeskydd läggs till krävs ingen schemaändring, och deras premier blandas inte med pensionspremier
- Tillståndsperioder svarar direkt på "vilket läge hade försäkringen vid tidpunkt T?" – krav för handläggning, revision och kundhistorik
- Ingen statuskolumn på `policies` eliminerar risken för dubbla sanningar (status som motsäger lägeshistoriken)
- Uppslagskedjan person → försäkringar → förmåner → premier är rena FK-joins – handläggar-UI:t (B-020) kan bygga vyer utan specialfall

**Övervägda alternativ:**

*Händelselogg i stället för tillståndsperioder* – mer granulär revision, men läget vid en tidpunkt måste härledas ur händelsekedjan. Kan införas senare som komplement (t.ex. i samband med `cases`).

*Premier kvar på försäkringsnivå* – enklare nu, men skulle kräva ombyggnad när fler förmånstyper tillkommer.

**Konsekvenser:**
- Tabellerna byggdes om via `scripts/rebuild_insurance_tables.py`; genererad data återskapas med `scripts/generate_premium_history.py`
- Integritetsregler: max ett öppet läge per försäkring, max en pågående förmån per typ och försäkring, max en ordinarie premie per förmån och månad (partiella unika index). Överlappande lägesperioder valideras på applikationsnivå
- Förmånens kapital = summan av dess betalda transaktioner; försäkringens = summan över förmåner; personens = summan över försäkringar

**Ersätter:** B-021:s regel om ett avtal per försäkrad (UNIQUE på `insured_person_id`). Övriga delar av B-021 (endast traditionell förvaltning, kapitalavgift 0,20 %, ingen flytträtt/efterlevandeskydd i v1.0) kvarstår oförändrade.

---

### B-021 | 2026-07-12 | Produktförenklingar i försäkringsvillkor version 1.0

**Beslut:** Bolagets försäkringsvillkor för ålderspension ITP1 (`01_domän/försäkringsvillkor.md` v1.0) gör tre medvetna förenklingar gentemot det verkliga ITP1-systemet:

1. **Endast traditionell förvaltning** – inget fondval, ingen valcentral. Allt pensionskapital förvaltas kollektivt enligt bolagets placeringsriktlinje.
2. **Kapitalavgift 0,20 % per år** (debiteras månadsvis med 1/12), ingen fast avgift.
3. **Ingen flytträtt och inget efterlevandeskydd** i version 1.0.

**Motivering:**
- Kollektiv traditionell förvaltning gör Fas 2 (paper trading, B-019) till *en* portfölj att förvalta i stället för individuella val – premieinflödet kan kopplas direkt till portföljen utan valcentralslogik
- I verkligheten ligger dessa roller dessutom hos skilda aktörer (Collectum som valcentral, flera valbara bolag) – att simulera hela den strukturen tillför komplexitet utan motsvarande lärvärde i detta skede
- En kapitalavgift ger bolaget en intäktsström, vilket behövs för att ekonomiagenten (framtida fas) ska ha något att bokföra; 0,20 % ligger i paritet med verkliga ITP1-upphandlade bolag
- Efterlevandeskydd är redan utanför scope (B-002); flytträtt kräver motpartslogik som saknar mening i en simulering med ett enda bolag

**Konsekvenser:**
- `policies`-tabellen (Fas 1b) behöver inte kolumner för sparform eller fondval i första versionen
- Avgiftsuttag ska implementeras när kapitalberäkning byggs (kapitalavgift som månatlig transaktion)
- Fondval, valcentralsroll och flytträtt är kandidater för senare versioner – återinförs i så fall genom nytt beslut och ny villkorsversion
- Villkorens ändringslogg och detta beslut ska hållas i synk vid framtida versioner

---

### B-020 | 2026-07-12 | Handläggar-UI byggs före kundportalen

**Beslut:** Av de två planerade webbgränssnitten byggs **handläggargränssnittet först** (admin-UI enligt utredningen i ATT_GORA: FastAPI-backend, tabellvyer mot Lakebase, inbyggd Claude-agent). Kundportalen (se pensionssaldo, pausa uttag m.m.) byggs senare, ovanpå samma FastAPI-backend.

**Motivering:**
- Utredningen för admin-UI:t är redan gjord (ATT_GORA 🔵) – arkitektur, komponenter och designfrågor är kartlagda
- Handläggar-UI:t kräver ingen kundautentisering – för en sandbox räcker enkelt skydd, medan en kundportal väcker autentiserings- och behörighetsfrågor som inte behöver lösas nu
- Kundportalens kärnfunktioner (t.ex. pausa uttag) kräver uttags-/utbetalningslogik som inte finns än – handläggar-UI:t behöver bara läsa och redigera data som redan finns i databasen
- Operatörsprincipen (B-017) gynnas direkt: handläggar-UI:t blir operatörens gränssnitt mot bolaget
- Gemensam backend gör att kundportalen sedan blir ett frontend-tillägg, inte ett nytt systembygge

**Övervägda alternativ:**

*Alternativ 1: Kundportalen först* – mer synligt demoresultat, men blockeras av saknad uttagslogik och autentiseringsfrågor.

*Alternativ 2: Båda parallellt* – enhetlig arkitektur från start men mest arbete och delad fokus; avvisat i detta skede.

**Konsekvenser:**
- Fas 4 i ATT_GORA:s fasplan avser handläggar-UI:t; kundportalen läggs som senare fas
- Backenden designas från start för två klienter (handläggare, kund) – API:t ska inte anta att anroparen är intern
- Utestående designfrågor i ATT_GORA-utredningen (sessionshistorik, filrättigheter, autentisering) beslutas när Fas 4 påbörjas

---

### B-019 | 2026-07-12 | Kapitalförvaltning som paper trading – inget riktigt kapital

**Beslut:** Kapitalförvaltningen byggs som **paper trading**: en simulerad wallet/portfölj i databasen (startkassa t.ex. 1 000 kr, simulerade), riktiga marknadsdata via gratis-API (t.ex. yfinance), och förvaltningslogik som placerar enligt en intern placeringsriktlinje i `05_styrdokument/` – skriven som om ett verkligt tjänstepensionsbolag investerade. Inget riktigt kapital används.

**Motivering:**
- Bekräftar B-003 (sandbox, inget riktigt kapital) – helautomatisk AI-handel med riktiga pengar hade rivit upp den principen
- §3.5 (människa-i-loopen) kräver ändå manuellt godkännande av transaktioner – helautomatisk exekvering med riktiga pengar vore dubbelt oförenlig med befintliga principer
- Läroeffekten är nästan identisk: portföljlogik, riktlinjeefterlevnad, rebalansering och beslutsloggning byggs och testas lika väl mot simulerad kassa med riktiga kurser
- Slipper mäklar-API, depåavtal och regulatorisk gråzon kring automatiserad handel
- Premieinflödet från försäkringssystemet (Fas 1) kan kopplas som insättningar till portföljen – bolaget hänger ihop end-to-end utan externa beroenden

**Övervägda alternativ:**

*Alternativ 1: Riktiga 1 000 kr, operatören exekverar* – agenten föreslår ordrar, operatören lägger dem manuellt hos mäklare. Förenligt med §3.5 men manuellt arbete per order och kräver depå; ger marginellt mervärde över paper trading. Kan omprövas senare när förvaltningslogiken är beprövad.

*Alternativ 2: Helautomatisk handel med riktigt kapital* – avvisat: bryter B-003 och §3.5.

**Konsekvenser:**
- Fasplanens Fas 2 i ATT_GORA: styrdokumentshierarki (minimal) + placeringsriktlinje, tabellerna `portfolios`/`portfolio_holdings`/`trades`, marknadsdata-skill, regelstyrd förvaltningslogik
- Första versionen av förvaltningslogiken är regelstyrd kod (ingen LLM) – agentautonomi införs efter att AI-abstraktionslagret (B-009, Fas 3) är byggt
- Varje förvaltningsbeslut loggas med motivering (spårbarhetskrav, jfr B-016)
- Om riktigt kapital någonsin införs krävs ett nytt beslut som uttryckligen ersätter både detta och B-003

---

### B-018 | 2026-07-08 | Databricks Lakebase ersätter Supabase som databas

**Beslut:** Som databas används **Databricks Lakebase** (serverless Postgres, Free Edition) istället för Supabase. All databasåtkomst i Python sker fortfarande via **SQLAlchemy** – ingen ändring av ORM-lagret eftersom Lakebase är Postgres-kompatibel över standardprotokollet.

**Motivering:**
- Projektet är ett PoC för en "AI-first"-strategi i tjänstepensionsbranschen – Databricks ekosystem (BI, analys, framtida ML/aktuariella modeller) passar den ambitionen bättre än Supabase, som bara är en databas
- Karl har befintlig vana vid Databricks, vilket sänker tröskeln för att bygga vidare på analys-/rapporteringssidan
- Lakebase är Postgres-kompatibel "under huven" – SQLAlchemy-modellerna som redan är skrivna (`employers`, `insured_persons`) kräver ingen omskrivning, till skillnad från klassiska Databricks Delta-tabeller (som saknar riktig auto-increment, CHECK-constraints, Enum-stöd)
- Free Edition är gratis (icke-kommersiellt bruk), i linje med B-003 (sandbox/simulering) och B-014:s ursprungliga kostnadsresonemang

**Övervägda alternativ:**

*Alternativ 1: Behåll Supabase (B-014 oförändrat)*
Fördelar: redan uppsatt, väldokumenterat, inga öppna frågor kvar. Nackdelar: inget naturligt BI/analyslager, mindre i linje med AI-first-ambitionen.

*Alternativ 2: Klassiskt Databricks (Delta Lake + SQL Warehouse)*
Fördelar: helt Databricks-nativt. Nackdelar: SQLAlchemy-dialekten saknar stöd för centrala OLTP-mönster (auto-increment, constraints) – dåligt pass för transaktionella tabeller som `premium_transactions` och `cases`.

**Konsekvenser:**
- `DATABASE_URL` i `.env` byts från Supabase pooler-URI till Lakebase-instansens Postgres-anslutningssträng (`postgresql://...@ep-....databricks.com/databricks_postgres?sslmode=require`)
- ATT_GÖRA:s hög-prioritetspunkt om Supabase connection pooler görs om till motsvarande Lakebase-uppgift (skapa instans, hämta connection string, kör `seed_supabase.py` – döps eventuellt om)
- **Öppen riskpunkt att verifiera praktiskt innan seed körs:** (1) om extern SQLAlchemy-anslutning med enkel användarnamn/lösenord fungerar i Free Edition utan kontonivå-service principal, (2) om fair-use-kvoten i Free Edition kan stänga av en aktiv databasinstans mitt i drift
- MASTER_CONTEXT §5 (teknisk stack) uppdateras: raden "Databas" ändras från "Supabase (managed PostgreSQL)" till "Databricks Lakebase (serverless Postgres, Free Edition)"

**Ersätter:** B-014

---

### B-017 | 2026-05-16 | Människa som fullständig operatör

**Beslut:** Systemet designas för dual-mode: agenter kör normalt på autopilot, men operatören kan när som helst ta manuell kontroll och utföra samma åtgärder direkt – via Cowork, MCP-kopplingar eller annat gränssnitt. Ingen åtgärd ska vara agentexklusiv.

**Motivering:**
- Sänker tröskeln för att komma igång – operatören kan agera manuellt tidigt medan automatiseringen byggs upp stegvis
- Möjliggör undantag och krissituationer utan att behöva vänta på att en agent triggas
- Cowork + Supabase MCP ger operatören ett naturligt gränssnitt för direkta databasoperationer, utan att skriva kod
- Speglar hur verkliga bolag fungerar: system och människor agerar parallellt, inte i serie

**Konsekvenser:**
- MCP-koppling till Supabase prioriteras även för operatörens direkta bruk, inte bara för agentdrift
- Gränssnitt och behörigheter designas så att manuella och automatiserade åtgärder lämnar samma spår i databasen (samma tabeller, samma loggning)
- Dokumenterat i MASTER_CONTEXT §3.7 som stående designprincip

---

### B-016 | 2026-05-15 | Hybrid orchestration som agentarkitektur

**Beslut:** Agentsamverkan i systemet struktureras som en hybrid mellan två mönster:

- **Dynamisk samverkan** – agenter känner till varandras gränssnitt och kan anlita varandra ad hoc för ostrukturerade, oförutsägbara uppgifter i vardagsarbetet.
- **Orkestrerade flöden** – fördefinierade, sekventiella workflows för kända processer med tydliga triggers. Dokumenteras i `02_system/Agentsystem/`, en MD-fil per flöde.

Orkestrerade flöden används när processen (a) involverar flera agenter i en känd ordning, (b) är compliance-kritisk och måste vara granskningsbar, eller (c) kräver manuellt godkännande vid varje etapp.

**Motivering:**
- Regelverksförändringar, ORSA-processen och rapporteringscykler måste vara deterministiska och fullt spårbara – en tillsynsmyndighet ska kunna följa exakt vad som hände i vilken ordning. Det utesluter ren dynamisk samverkan för dessa processer.
- Dynamisk samverkan är tillräcklig och mer flexibel för ad hoc-uppgifter där utfallet inte är förutsägbart i förväg.
- Hybrid-modellen är etablerad best practice i multi-agent-system (jfr LangGraph, Autogen, CrewAI) och kombinerar spårbarhet med flexibilitet.

**Övervägda alternativ:**

*Alternativ 1: Ren dynamisk samverkan*
Agenter har kopplingar och avgör själva när och hur de anlitar varandra. Fördelar: flexibelt, hanterar oförutsedda situationer bra. Nackdelar: svårt att granska i efterhand, oförutsägbart beteende i compliance-kritiska processer, svårare att felsöka.

*Alternativ 2: Ren orkestrering*
Alla agentinteraktioner definieras i förväg som strukturerade flöden. Fördelar: maximalt spårbart och deterministiskt. Nackdelar: orimlig overhead för vardagsarbete, skalerar dåligt – varje ny interaktionstyp kräver ett nytt dokumenterat flöde.

**Konsekvenser:**
- `02_system/Agentsystem/` skapas för orkestrerade flöden (en MD-fil per flöde)
- Kända kandidater för orkestrerade flöden: regelförändringsflödet, ORSA-processen, rapporteringscykeln
- Varje orkestrerat flöde dokumenterar trigger, inblandade agenter, godkännandesteg och spårbarhetskrav

---

### B-015 | 2026-05-14 | Mappstruktur: dokumentation och kod separerade

**Beslut:** Projektets mappstruktur separerar dokumentation (svenska namn, numrerade mappar i roten) från Python-kod (i `src/`, engelska namn).

- **Dokumentation:** `01_domän/`, `02_system/`, `03_skills/`, `04_regulatoriskt/`, `05_styrdokument/` – svenska namn OK
- **Kod:** `src/agents/`, `src/skills/`, `src/models/`, `src/ai/`, `src/utils/` – engelska namn
- **Övrigt:** `tests/`, `data/`, `scripts/` på rotnivå

För skills och agenter används mönstret att *instruktion (MD)* ligger i dokumentationsmappen och *implementation (Python)* ligger i `src/`. En skill identifieras alltså av två filer:

- `03_skills/data/hämta-kunddata.md` (instruktion)
- `src/skills/data/get_customer_data.py` (implementation)

**Motivering:**
- Pythons modulnamn klarar inte svenska tecken (`å`, `ä`, `ö`) – `import skills.beräkning` är ogiltigt
- Att bygga ihop instruktion och kod i samma mapp (alternativ "skill = en mapp") fungerar inte med svenska kategorinamn
- Separationen bevarar svensk dokumentationsestetik utan att kompromissa med kodens importerbarhet
- Mappning mellan svenska och engelska kategorinamn dokumenteras i MASTER_CONTEXT §7

**Mappning skill-kategorier:**
| Dokumentation (sv) | Kod (en) |
|--------------------|----------|
| `03_skills/data/` | `src/skills/data/` |
| `03_skills/beräkning/` | `src/skills/calculation/` |
| `03_skills/kommunikation/` | `src/skills/communication/` |
| `03_skills/regelverk/` | `src/skills/regulatory/` |

**Konsekvenser:**
- `pyproject.toml` pekar på `src/` som paketrot
- `__init__.py` finns i alla Python-paket
- Skillkatalogen (`03_skills/skillkatalog.md`) listar både MD- och Python-filens sökväg per skill

---

### B-014 | 2026-05-14 | Supabase + SQLAlchemy som databaslager

**Beslut:** Som databas används **Supabase** (managed PostgreSQL i molnet). All databasåtkomst i Python sker via **SQLAlchemy** som ORM/abstraktionslager. Tabeller definieras som Python-klasser, inte som rå SQL.

**Motivering:**
- **Supabase free-tier** räcker för sandbox-skala (500 MB databas, 50 000 MAUs, obegränsade API-anrop) och kostar 0 kr
- Riktig PostgreSQL → projektmiljön speglar verkligheten (i linje med projektets simuleringssyfte)
- Inget Docker eller lokal serveruppsättning krävs
- Webb-UI för att kika på data direkt – bra för debugging och inspektion under utveckling
- **SQLAlchemy** abstraherar bort databasleverantören: schemat följer med vid byte. Samma princip som vår modellagnostiska AI-arkitektur (B-009)
- Schema-versionering via Alembic blir naturlig nästa steg

**Konsekvenser:**
- Skapa Supabase-konto och projekt (se ATT_GORA)
- Spara connection string och API-nycklar säkert – aldrig i Git (skäl till att `.gitignore` är prioriterat)
- All ny kod som rör data skrivs mot SQLAlchemy-modeller, inte direkt SQL
- Backup-strategi behövs på sikt (free-tier saknar automatisk backup)
- **Notera:** Projekt på free-tier pausas efter 7 dagars inaktivitet men kan startas manuellt igen utan dataförlust

---

### B-013 | 2026-05-14 | Git + GitHub som versionskontroll

**Beslut:** Git används som versionskontrollsystem. Hela projektets kodbas och dokumentation lagras i GitHub-repot [Artificiellalecta](https://github.com/karltengelin/Artificiellalecta.git). Cowork kopplas till repot via GitHub-connector.

**Motivering:**
- Git är de facto-standard – stort ekosystem, väl integrerat med Cowork och alla större verktyg
- GitHub ger versionshistorik, ändringsspårning och möjlighet till samarbete på sikt
- Markdown-filer (B-012) diffas bra i Git – passar perfekt med vår dokumentstrategi
- Cowork har inbyggd connector som möjliggör att agenter och utvecklare jobbar mot samma repo

**Konsekvenser:**
- All kod och alla dokument (inkl. MASTER_CONTEXT, beslutslogg, styrdokument, regelverk) versioneras i samma repo
- `.gitignore` måste sättas upp för att exkludera API-nycklar, `.env`-filer, databasfiler etc. (tas vid behov, separat post i ATT_GORA)
- Behöver besluta om branch-strategi senare (main + feature branches? Eller direkt mot main i tidigt skede?)

---

### B-012 | 2026-05-14 | Markdown som primärt informationsformat

**Beslut:** All information i projektet sparas i första hand som Markdown-filer. PDF (eller andra format) genereras från Markdown vid behov – när en människa ska läsa formella beslut, rapporter eller utskick.

**Motivering:**
- Markdown är ren text och därmed lätt för LLM att läsa och tolka, till skillnad från PDF som ofta har komplex struktur
- Markdown är versionskontrollerbart (fungerar väl med Git, diffar är läsbara)
- Markdown är mänskligt läsbart även i råform – ingen specialprogramvara krävs
- Markdown konverteras enkelt till PDF, HTML, DOCX vid behov (Pandoc, WeasyPrint m.fl.)
- PDF låser fast layout men förlorar semantisk struktur – passar leverans, inte arbete

**Konsekvenser:**
- Styrdokument, processbeskrivningar, regelverkstolkningar, agentinstruktioner, beslut, journalanteckningar skrivs alltid som Markdown
- En md→PDF-pipeline ska sättas upp för formell dokumentgenerering
- Mallar (styrdokumentsmallar etc.) skrivs som Markdown med metadata-block i toppen

---

### B-011 | 2026-05-14 | Compliance-agent äger både regelverk och styrdokument

**Beslut:** En enda compliance-agent ansvarar för både regelverkskunskap och styrdokumentsstruktur. Ingen separat styrdokuments-agent skapas.

**Motivering:**
- Regelverk och styrdokument är tätt sammankopplade – ändras en regel kan styrdokument behöva uppdateras, och vice versa
- Att splittra ansvaret skulle skapa agent-till-agent-kommunikation som vi vill undvika (se B-008)
- Skillsbiblioteket räcker för att täcka olika operationer (slå upp regelverk, granska styrdokument, kontrollera efterlevnad etc.)

**Konsekvenser:**
- Compliance-agenten får skills för både regelverksuppslag och styrdokumentshantering
- Andra agenter kan eskalera till compliance-agenten vid juridiskt tveksamma fall – ett av undantagen från B-008

---

### B-010 | 2026-05-14 | Fyrlagermodell för regelefterlevnad

**Beslut:** Regelefterlevnad i projektet struktureras i fyra lager:
1. **Regelverkskällor** (`04_regulatoriskt/`) – ursprungliga lagar, förordningar, föreskrifter
2. **Tolkningar** – översättning av regelverk till operativa konsekvenser för bolaget
3. **Styrdokument** (`05_styrdokument/`) – interna policies, riktlinjer, processer
4. **Operativt arbete** – det dagliga arbetet som agenter och människor utför

Styrdokument ska alltid referera tillbaka till de regelverk de implementerar.

**Motivering:**
- Speglar hur verkliga tjänstepensionsbolag arbetar (LTF/FFFS 2019:21 förutsätter denna struktur)
- Möjliggör spårbarhet – varje regel går att följa till sitt ursprung
- Skiljer på "vad lagen säger" och "vad vi har bestämt" – båda måste vara dokumenterade men inte i samma fil
- Förenklar uppdatering vid regelverksförändringar – tydligt vad som måste revideras

**Konsekvenser:**
- Två separata mappstrukturer i projektet: `04_regulatoriskt/` och `05_styrdokument/`
- Varje styrdokument ska ha standardiserad metadata i toppen (syfte, ägare, beslutas av, refererade regelverk, versionshistorik)

---

### B-009 | 2026-05-14 | Modellagnostisk arkitektur via abstraktionslager

**Beslut:** All kod som anropar AI-modeller ska gå via ett abstraktionslager, inte direkt mot en specifik leverantörs SDK. Det ska gå att byta modell eller leverantör (OpenAI ↔ Anthropic ↔ andra) genom konfiguration, utan att ändra agentkod eller skills.

**Motivering:**
- Undviker inlåsning hos en enskild leverantör
- Modeller utvecklas snabbt – nya, bättre eller billigare modeller kommer löpande
- Olika modeller passar olika uppgifter (en agent kan använda en kraftfull modell, en annan en billigare för enklare uppgifter)
- API-priser och tillgänglighet ändras över tid
- Möjliggör jämförande utvärdering av modellers prestanda inom projektet

**Konsekvenser:**
- Inga direktanrop till `openai.ChatCompletion` eller `anthropic.messages.create` i agent- eller skillkod
- Modellval, API-nyckel och provider hanteras via konfigurationsfil eller miljövariabler
- Prompter skrivs så generiskt som möjligt – leverantörsspecifika finesser kapslas in i abstraktionslagret
- Behöver utvärdera färdiga lösningar (LiteLLM, OpenRouter) eller bygga egen wrapper
- Lägg till `02_system/ai_abstraktion.md` för att specificera lagret

---

### B-008 | 2026-05-14 | Arkitekturprincip: hellre fler skills än fler agenter

**Beslut:** När en ny funktion ska byggas, default är att skapa en eller flera skills som en befintlig agent får tillgång till. Skapa inte en ny agent om det inte krävs ett distinkt mandat eller ansvar.

**Motivering:**
- Agent-till-agent-kommunikation riskerar att tappa kontext vid varje överlämning
- Multi-agent-flöden innebär fler LLM-anrop, vilket är dyrare och långsammare
- Färre agenter = enklare felsökning (tydligt vem som fattade vilket beslut)
- Skills är återanvändbara mellan agenter; en ny agent är en helt ny enhet att underhålla

**Undantag:** Multi-agent är motiverat när olika delar av arbetet kräver fundamentalt olika mandat (t.ex. handläggare som eskalerar till compliance), när parallellt arbete är meningsfullt, eller när det finns behörighetsskillnader.

---

### B-007 | 2026-05-14 | Delat skillsbibliotek med behörighetsmodell

**Beslut:** Alla skills ligger i ett centralt bibliotek (`03_skills/`). Varje agent har en deklarerad lista över vilka skills den får använda – inte alla agenter får tillgång till alla skills.

**Motivering:**
- Delat bibliotek undviker duplicering – en uppdatering slår igenom överallt
- Centralt index gör skills upptäckbara, så samma funktion inte byggs två gånger
- Behörighetsmodellen behövs för GDPR-efterlevnad och säkerhetshygien (se B-006)
- Tydlig agentdefinition: man ser direkt vad varje agent har för verktygslåda

---

### B-006 | 2026-05-14 | Skills med kunddataåtkomst ska ha begränsad behörighet

**Beslut:** Skills som hämtar, ändrar eller exponerar personuppgifter får inte vara tillgängliga för alla agenter. Varje sådan skill ska ha en uttrycklig lista över vilka agenter som är behöriga.

**Motivering:**
- GDPR: dataminimeringsprincipen kräver att endast den som faktiskt behöver data får åtkomst
- Exempel: Kapitalförvaltningsagenten behöver aggregerade portfölj­data, inte enskilda kunders personuppgifter
- Säkerhetshygien: minskar attackytan om en agent kompromiteras eller får felaktiga instruktioner
- Internrevision/spårbarhet: tydligt vem som hade rätt att se vad

---

### B-005 | 2026-05-14 | Hybrid dataarkitektur: databas + dokumentlager

**Beslut:** Strukturerad data (kunder, policys, transaktioner) lagras i en databas. Regler, processer, villkor och instruktioner lagras som textfiler.

**Motivering:**
- Speglar hur verkliga bolag arbetar
- Databas ger frågbarhet och dataintegritet för operativa flöden
- Dokumentlager ger versionerbara, läsbara regelverk som både människor och AI kan tolka

---

### B-004 | 2026-05-14 | Python som primärt programspråk

**Beslut:** All kod skrivs i Python där inte annat motiveras.

**Motivering:**
- Bred ekosystem för dataanalys, aktuariella beräkningar, API-integrationer
- Användarens preferens
- God Claude-kompetens i språket

---

### B-003 | 2026-05-14 | Sandbox/simulering, inga riktiga kunder

**Beslut:** Plattformen byggs som ett simulerat bolag med fiktiv data. Inga riktiga kunder eller riktigt kapital hanteras.

**Motivering:**
- Möjliggör experiment och felsteg utan reglerings- eller skaderisk
- Kringgår tillståndskrav från Finansinspektionen
- Möjliggör utveckling av processer som speglar verkligheten

---

### B-002 | 2026-05-14 | Scope begränsat till ITP1 ålderspension

**Beslut:** Endast ålderspension inom kollektivavtalet ITP1 ingår. Sjukpension, familjepension, ITPK, andra kollektivavtal och individuella lösningar är utanför scope.

**Motivering:**
- Begränsar komplexitet till en hanterbar nivå
- Möjliggör djupare detaljerings­grad inom ett tydligt avgränsat område
- ITP1 är en välanvänd och väldokumenterad produkt – bra för simulering

---

### B-001 | 2026-05-14 | Master-kontextdokument som projektets fundament

**Beslut:** `MASTER_CONTEXT.md` är det dokument som alla Claude-sessioner och agenter ska läsa först. Det innehåller vision, scope, arkitektur och status.

**Motivering:**
- Garanterar att varje ny session har samma utgångspunkt
- Förebygger drift och inkonsekvenser mellan sessioner
- Fungerar som onboardingdokument för framtida agenter

---

## Mall för nya beslut

```
### B-XXX | YYYY-MM-DD | [Kort titel]

**Beslut:** [Vad bestämdes]

**Motivering:**
- [Varför]
- [Varför]

**Konsekvenser:** [Vad det innebär praktiskt, om relevant]

**Ersätter:** [Referens till tidigare beslut om det är en ändring]
```
