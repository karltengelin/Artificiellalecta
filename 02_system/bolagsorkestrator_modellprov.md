# Bolagsorkestratören i Fråga bolaget – modellprov och driftval

**19 november 2026.** GitHubs `refs/heads/main` verifierades till
`6c0bcaba5cda85ab8e40cae9400d668f4c84bdec`, med pilotmergen `cdd1d4f` i historiken.
Provet kördes i en separat arbetskopia på `codex/bolagsorkestrator-modellprov`.

Det skriptade SQLite-provet gav ett facit från beställning till verifierad
schemaläggning och källbundet svar. Efter byte av API-nycklar gick det att
köra projektets ordinarie Claude-modeller och Claude Managed Agents med
samma källa, demobestånd och lokala verksamhetskontroller. Den lokala
modellen nådde `answered`. Två hostade uppdrag nådde rätt domänkvitto men
stoppades av resultatverifieringen i slutsvaret. Ett hostat omprov stannade
på Compliance-tolkningen före godkännande.

Provet följer upplägget i *Vem ska köra våra agenter?* från 14 november,
sidan 7, med det beställda parameterfallet. Rapportens andra fall,
regler som kräver en kodändring, ligger utanför detta modellprov.

## Provfall

- Uppdraget var ”Utred den här nya regeln, visa premieeffekten om den behövs för
  beslutet och förbered genomförandet.” I fritexten bifogades `Källa K-SIM-PARAM-2027`,
  version 1.0, källans kontrollsumma `b4d79938aaa1a024` enligt källverktyget.
  Den fiktiva regeln ändrar `premium_rate_low` från 4,5 till 5 procent från
  lönemånaden januari 2027. [Fiktiv källa](../04_regulatoriskt/03_bevakning/K-SIM-PARAM-2027-premiesats.md)
- Varje körning fick en ny SQLite-fil med det ordinarie syntetiska demobeståndet
  och datasetreferensen `demo:bolagsorkestrator-modellprov`. Provets affärsdatum
  var låst till 2026-11-15, som i pilotens webbprov. Seedningen av ett orelaterat
  löneunderlagsförslag avvisades som framtida med det fasta datumet.
- Inloggningen använde pilotprovets lokala testidentitet `karl`. Alla tre
  godkännanden var simulerade och märkta i protokollet. `abcdef1` är pilotprovets
  fiktiva regeltextreferens för version 1.1. Tjänstelagret sparade
  schemaläggningen i demofilen. Regeltexterna låg kvar som utkast.
- Provet driver FastAPI:s ordinarie webbformulär med `TestClient`, inklusive
  inloggning, CSRF och aktuell uppdragsrevision. Produktionens tjänstelager,
  verktygsmappning, profiler och verifierare återanvänds. Skriptat läge
  återanvänder pilotens svarsmallar. I modelläge lämnar modellerna själva alla
  verktygsval och slutsvar. Inga Lakebase-anslutningar användes.
  [Pilotbeskrivning](bolagsorkestrator_pilot.md) · [Projektplan för Fråga bolaget](../projekt/10_operatörscentral/PROJEKTPLAN.md#fråga-bolaget-och-bolagsorkestratören)

Körpolicyn gav uppdraget ett tak på 60 modellsteg, 90 verktygsanrop och
5 USD. Orkestratörens segmenttak var 10 steg, 12 verktygsanrop och 0,50 USD
inom återstående rotbudget. Samma räknare och gränser behöver följas upp
i det hostade försöket.

## Lokal körning med skriptad modell

Uppdrag `BO-c47d888486234d1fb84ac21a70856c05` kördes med `test:flow` i
Python 3.14.2. Stegen nedan använder samma uppdrags-id i båda processerna.
Fullständiga id:n, kontrollsummor och resultat finns i protokollet.

| Steg | Utfall | Spår |
|---|---|---|
| Beställning och samordning | Samma webbnyckel gav samma uppdrag. Två identiska beställningar genom samordningsverktyget gav ett Compliance-deluppdrag. | `run-c47d888486234d1fb84ac21a70856c05` |
| Compliance | Tolkningen band premiesatsen och datumet till den fiktiva källan och PR-ITP1-001. Konsekvensanalys och förslag till regeltext gick att öppna som Markdown. | `run-66cd3a0ecbe845ec9612c7422a670f68` |
| Granskning av tolkning och omstart | Första processen avslutades i `waiting_review`. Ny process, ny app och ny inloggning läste samma uppdragsrevision. Fel granskningssumma gav 409. Det simulerade godkännandet band tolkningens resultatkontrollsumma. | `run-2e866c1db584449f8fc98dacf72fa056`, granskningssumma `3b7c704f…` |
| Beställning och analys | Orkestratören beställde en premieanalys från aktuarien efter tolkningsbeslutet. Tjänsteoperationen `estimate_parameter_change_impact` kördes separat med samma parameter, värde, giltighet och tioårshorisont före schemaläggning. Hela det sparade aggregatet matchade. | `run-e75984f7820346898b6702c0bbe85bb5` och `run-a92231d4cae340998a84ba0753cbef8c` |
| Regelbeslut | Fel granskningssumma gav 409. Det simulerade beslutet band både Compliance-resultatet och analysens id och resultatkontrollsumma. | `run-f1786dfc5236495b8504749c23f1eef5`, granskningssumma `14571196…`, analys `65139f01…` |
| Genomförande och kvitto | Två avläsningar gav ett förslag med exakt beslutad indata. Agenten nekades godkännande. Den simulerade operatören godkände i kön. Tjänstelagret visade 4,5 procent t.o.m. 2026-12-31 och 5 procent fr.o.m. 2027-01-01 med rätt käll- och beslutsreferens. | Kvitto `57fb28260b1157dfbf58cb9d222ba989` och beslut `BO-c47d888486234d1fb84ac21a70856c05/b937d861e8c2` |
| Samlat svar | Slutläge `answered`, med källan, länkar till båda specialistresultaten och besked om verifierad schemaläggning. Beloppen visas ur tjänstelagrets underlag. Webbens körspår gick att öppna för samtliga sju segment. | `run-a82094bb54e54bd1b7ce6707f2bb11bf` |

**Premieeffekt i demot.** 33 aktiva ingick och 26 berördes. År 2027 ökade
premievolymen från 1 169 000 till 1 229 000 kr, en ökning med 60 000 kr.
Total effekt januari 2027 till december 2036 var +131 000 kr och
0 extra premiemånader. Beloppen är avrundade till hela tusental. Årsvisa
effekter därefter skyddas av småcellsreglerna. Kalkylen använder oförändrade
löner, senast fastställt IBB för år utan eget belopp, samt noll avkastning och
avgifter. Den separat anropade tjänsten räknar med samma premiemotor som
specialisten. Likheten kontrollerar dataöverföringen och underlaget som granskas.

**Tid och kostnad.** 1,257 s till första granskningen och 1,644 s för fortsättningen,
totalt 2,901 s inom skriptet. Summa segmenttid 0,738 s, 25 modellsteg och 18
verktygsanrop. `test:flow` har noll modellkostnad. Tiderna inkluderar automatiserade
webbanrop och simulerade beslut. Processstart och operatörens lästid tillkommer i drift.

## Första åtkomstförsöket

Fråga bolaget registrerade uppdrag `BO-f45ea8d1b64a40faa9833406ac954693`.
Första segmentet använde rollen `standard` och skickade ett anrop till
`anthropic:claude-sonnet-5` via Messages API. Anthropic SDK 1.13.0 loggade
HTTP 401 `invalid x-api-key` med request-id `req_011ChCgvmbzT9NQTMdu7ti3w`.
Konfigurerat reservval var `openai:gpt-6.1-sol`. Vid autentiseringsfel stannar
AI-klienten och inget reservanrop registrerades. Compliance och aktuarien hade
rollen `deep` med primär `anthropic:claude-opus-5` och reserv
`openai:gpt-6-astra`, men kom aldrig till start.

Det första uppdraget stannade i `needs_human`, med misslyckat körspår
`run-f45ea8d1b64a40faa9833406ac954693`. Det fanns noll verktygsanrop,
specialistbeställningar, beslut och kvitton. Körtiden var 3,635 s, varav
2,946 s i segmentet och cirka 213 ms i det loggade API-försöket.
Inga in- eller uttokens rapporterades, och harness bokförde 0 USD.
Modellens faktiska svarkvalitet och versionsidentifierare gick inte att observera.

### Åtkomst till hostade tjänster

Åtkomstkontrollerna använde enbart läsanrop med de befintliga nycklarna, utan
uppdragsdata. Båda tjänsterna gav HTTP 401 i det första försöket.

| Tjänst | Läsprov | Svar |
|---|---|---|
| Claude Managed Agents | `GET /v1/agents?limit=1` med beta `managed-agents-2026-04-01` | 401 `invalid x-api-key`, `req_011ChCgUBkK1vpYfSKvyKGY2`. Modellistan gav också 401, `req_011ChCgUCJne8hpkyJ5Wh8nx`. |
| OpenAI Agents API | `GET /v1/agents/sessions?limit=1` med beta `agents=v1` | 401 `expired_secret_key`, `req_01d3fa8d0f4e461198a9db1d2f7bd566`. Modellistan gav också 401, `0d2b4a08-a4d8-4771-a385-799f0d6aa474`. |

De nya nycklarna gav HTTP 200 för båda modellistorna och båda hostade
läsanropen. Modellistorna bekräftade `claude-sonnet-5`, `claude-opus-5`,
`gpt-6.1-sol` och `gpt-6-astra`. Anthropic användes för modelljämförelsen
eftersom orkestratörens ordinarie modell och resonemangsnivå kunde behållas.

**Claude Managed Agents.** Leverantören håller sessionen, skickar
händelser för väntande klientverktyg och fortsätter när klienten svarar.
Sessionshistoriken ligger hos leverantören tills den raderas. Kostnaden består
av modelltoken och 0,08 USD per aktiv sessionstimme enligt listpriset.
[Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview) · [Verktyg och sessionsevent](https://platform.claude.com/docs/en/managed-agents/events-and-streaming) · [Budget och användning](https://platform.claude.com/docs/en/managed-agents/budgets)

**Alternativ med OpenAI.** Agents API kan köras utan exekveringsmiljö med
egna klientfunktioner. En nyckel behöver `api.agents.read`, `api.agents.write`
och `api.responses.write` för provet. Kontrollera först att samma OpenAI-modell
stöds i båda API:erna och ställ den som baslinjens orkestratör via modellrollen
för en rättvis jämförelse. Dokumentationen anger modellpriser samt priser
för eventuella leverantörsverktyg och sandlådor. Sessionslagring omfattas av
Agents API:s datavillkor.
[Agents API](https://developers.openai.com/api/docs/guides/agents-api/overview) · [Åtkomst](https://developers.openai.com/api/docs/guides/agents-api/quickstart) · [Egna funktioner](https://developers.openai.com/api/docs/guides/agents-api/tools/functions)

## Lokal agentloop med riktig modell

`BO-c44f7534b74442b4bbd126d6c2d837dd` nådde `answered`. Orkestratören körde
`claude-sonnet-5` med medelhög resonemangsnivå och båda specialisterna körde
`claude-opus-5` via projektets ordinarie Messages-adapter. Ingen reservmodell
användes. Det behövdes inga promptförtydliganden eller manuella ingrepp utöver
de simulerade operatörsbesluten. Den befintliga resultatverifieraren begärde
ett rättningsvarv i fyra samordningssegment och i aktuarieanalysen, bland
annat för källhänvisningar till underlag som bara lästs i ett annat segment
och tal som skulle visas i analysens tabell.

Compliance läste den fiktiva källan, produktreglerna och parameterregistret
och levererade både konsekvensanalys och föreslagen regeltext. Tolkningen
stämde med källan om premiesats, lönemånad och frånvaro av retroaktiv effekt.
Den markerade att registerkvittot behöver kompletteras med kontroll av hur
premiemotorn väljer sats vid äldre lönerättelser. Aktuariens aggregat stämde
exakt med den oberoende körningen av samma tjänsteoperation, inklusive
avrundning och småcellsskydd. Slutsvaret hänvisade till båda specialistresultaten.

Första processen väntade på granskning efter 232,591 s. Den nya processen
läste samma revision och slutförde uppdraget på 203,845 s. Två felaktiga
granskningssummor avvisades. Agenten nekades godkännande. De simulerade
besluten band tolkning och analys till en verifierad parameterändring på
giltighetsdagen. Omfråga i godkännandekön gav samma förslag. Protokollet
innehåller sammanlagt två specialistbeställningar, två granskningsbeslut
och ett domänkvitto.

| Bevis | Referens |
|---|---|
| Compliance och Aktuarie | `run-473b1a2bdcb14d2e92df0751d1dc4dba` och `run-01390b035ab5401698c4826f14edb463` |
| Granskning och analysbindning | Tolkningssumma `2d394a7324d1…`, regelbeslutets granskningssumma `ca39f96f0963…`, analys `52407b8bc4e7…` |
| Verifierat kvitto | `f590c055feba5973989792344d17d9a2` |
| Slutsvar | `run-0e5094f8d96b4cb7973ae211f1b110f0` |

Protokollen finns i `tmp/modellprov-live-nycklar/`. Total tid inom båda
processerna var **436,436 s**. Orkestratörens fem segment tog 227,760 s
och kostade **0,355268 USD** enligt AI-lagrets tokenpris. Specialisterna tog
206,397 s och kostade 0,782750 USD. Hela uppdraget kostade **1,138018 USD**.
Modelljournalen har 38 lyckade svar, varav 27 för orkestratören.

## Claude Managed Agents för orkestratören

Diagnostiken byter körsätt för de fem samordningssegmenten. Varje segment har
en egen hostad session, precis som varje lokalt segment har en egen
modellkonversation. Båda körsätten hämtar verksamhetsläget från SQLite.
Sessionsstarten använde samma `claude-sonnet-5` och medelhög resonemangsnivå.
Compliance och Aktuarie körde med `claude-opus-5` via samma Messages-adapter
och lokala profiler som i baslinjen.

Hostens agent fick exakt tre lokala klientverktyg från den ordinarie
samordningsprofilen. Inbyggda fil-, webb- och kommandoverktyg var utelämnade.
Miljön hade tom lista över tillåtna värdar och inga monterade resurser.
Den lokala dispatchern prövade varje verktygsanrop. Sessionens id och
verktygshändelser journalfördes tillsammans med lokalt kör-id. Provversionen
av Anthropic SDK var 1.13.0 med beta `managed-agents-2026-04-01`.

Managed Agents avvisade det första verktygsschemat med HTTP 400 på grund av
`$ref`. Bryggan vecklar därför ut schemareferenserna. Den lokala
Pydantic-valideringen är densamma. Hostens svar lämnas som JSON-text enligt
schemat i instruktionen och går igenom den vanliga resultatverifieraren.
Tjänsten rapporterar väntan och avslutade turer som vilohändelser.
Hostens rapporterade steg räknar dessa observerade händelser. Hostens
utdatatak och kontextkomprimering styrs av tjänsten. Bryggan begränsar lokala
verktygsanrop och väntetid. Tjänstens kostnadstak prövas mellan modellanrop
och konsumtionen rapporteras avrundad till cent per session.
[Egna verktyg](https://platform.claude.com/docs/en/managed-agents/tools) · [Sessionshändelser](https://platform.claude.com/docs/en/managed-agents/events-and-streaming) · [Budget och mätning](https://platform.claude.com/docs/en/managed-agents/budgets)

### Första hostade körningen

`BO-47f5603d6608432bab681d69e8ee139c` fortsatte i en ny lokal process från den
sparade granskningen och fick två specialistbeställningar, två granskningar
och ett verifierat genomförandekvitto `6b9a7a507d9f5df2b562715acd6dece5`.
Vid den första beställningen läste en ny API-klient tillbaka samma väntande
händelse efter att beställningen hade sparats lokalt och före kvitteringen
till hosten. Dispatchern körde beställningen en gång.
Session `sesn_015eCvdPG3fG41615isLERbE`, händelse `sevt_01AcTtvzQgD682X4wA6gLVVa`.

Den lokala verifieraren avvisade flera samordningssvar. Sparade domänsteg
gick att fortsätta med. Slutsvaret hänvisade först till deluppdrags-id:n
som verifieraren saknade stöd för och lade in datum och belopp i
sammanfattningen. Rättningen hade fortfarande två sifferuppgifter.
Uppdraget stannade i `needs_human`, som avsett, med verifierat domänkvitto
och utan ett godkänt slutsvar. Slutspåret är
`run-fa07c2502a6240c68dcdf0c673ef75dd` i
session `sesn_01QCrWCei9yFf72PSwdrQuQv`.

Körtiden för det ofullständiga uppdraget var 427,164 s.
Orkestratörens segment tog 250,250 s och kostade cirka 0,44 USD vid listpris.
Specialisterna kostade 0,741045 USD. Summan blev cirka 1,18 USD.
Protokollen finns i `tmp/modellprov-managed-full/`.

### Omprov med tydligare svarskontrakt

Bryggan bad om ett kort JSON-svar, exakta id:n från statusverktyget och
inga sifferuppgifter i sammanfattningen när den hänvisar till en premieanalys.
Samma källa, verktyg och lokala kontroller användes igen.

`BO-51f6a0efc5004dd8a41adc632e461f99` stannade före första godkännandet efter
161,756 s och cirka 0,53 USD. Sats, regel och giltighetsdag stämde, men
Compliance klassade ändringen som blandad (`mixed`) med hänvisning till
regeltextens fasta procentsats och en förmodad kodändring för val av sats
per lönemånad. Det avgränsade parameterprovet kräver en ren parameterändring.
Samma `claude-opus-5` och lokala specialistväg användes som i de tidigare
körningarna. Ingen åtgärd godkändes. Tolkningen finns i
`run-68a5d3f4db8a40748389b486c8d44532` och delprotokollet i
`tmp/modellprov-managed-tydligt-svar/`.

### Replikat med samma tydligare svarskontrakt

`BO-b944b315176748e3bbb88d7a1069e525` nådde första granskningen efter
198,793 s. En ny process fortsatte i 147,117 s. Resultatet var två
specialistbeställningar, två hashbundna granskningar och det verifierade
kvittot `523e2e48010d5354a9f33cb8e19f35de`. Tolkningssumman var
`8c12847fb390…`, regelbeslutets granskningssumma `45c56c7a6d2d…` och
analysens resultatkontrollsumma `7abdfb0720cd…`. Återläsningen av den
första väntande verktygshändelsen lyckades även här, i
`sesn_011cUuunS6qSvaTSJwv2P48d` med händelse `sevt_01Cb17bzAidnRrQ5pwH9s1Vo`.

I slutsegmentet avvisade verifieraren först formatet och sedan hänvisningar
till två deluppdrags-id:n som avvek från de sparade id:na. Orkestratören
hade anropat det lokala statusverktyget. Uppdraget stannade i
`needs_human`. Slutspåret är `run-90540b5ae1d54e9384961e3ca221a4dd` i
`sesn_01V3AsUzgg4WdohKsQvZa2k8`. Compliance- och aktuarieunderlagen finns i
`run-bffd736f07db459996e0d54c3b515c13` respektive
`run-a30f9ead810441a0b62dacca96dccf2f`. Protokoll och samtliga
sessionsreferenser finns i `tmp/modellprov-managed-replikat/`.

**Kontroll av premiemotorn.** Alla tre slutförda aktuarieanalyser hade exakt
samma aggregat. Efter respektive schemaläggning gav den skrivskyddade
tjänsteoperationen `calculate_premium_preview` på en syntetisk månadslön
om 45 000 kr 2 025 kr i december 2026 och 2 250 kr i januari
2027. I båda månaderna användes IBB 83 400 kr. Januari antog
senast fastställt IBB från 2026. Beräkningsunderlaget visar version och
premiesats för respektive månad. Kodläsningen visar att rättelseoperationen
hämtar sats på ursprungstransaktionens premiemånad. Förhandsberäkningen
provade månadsskiftet utan att registrera en lönerättelse.
[Förhandsberäkning](../src/services/operations/premiums.py) · [Premiekorrigering](../src/services/operations/corrections.py)

### Tid och kostnad

| Prov | Utfall | Tid inom provprocesserna | Orkestratörens segment | Orkestratörens kostnad | Kostnad för hela uppdraget |
|---|---|---:|---:|---:|---:|
| Lokal loop med riktiga modeller | Källbundet slutsvar och verifierat kvitto | 436,436 s | 227,760 s | 0,355268 USD | 1,138018 USD |
| Hostad loop, första körningen | Verifierat kvitto, underkänt slutsvar | 427,164 s | 250,250 s | ca 0,44 USD | ca 1,18 USD |
| Hostad loop, tydligare svarskontrakt | Stopp före första godkännandet | 161,756 s | 44,121 s | ca 0,04 USD | ca 0,53 USD |
| Hostad loop, replikat med samma svarskontrakt | Verifierat kvitto, underkänt slutsvar | 345,910 s | 147,349 s | ca 0,24 USD | ca 1,03 USD |

Hostens aktiva tid i de två körningarna som nådde kvitto var 211,915 s
respektive 116,759 s. Lokal orkestratörskostnad kommer från projektets
tokenpris. Hostad kostnad bygger på leverantörens avrundade listkostnad
inklusive sessionstid. Sammanlagt registrerades cirka 3,88 USD i
modell- och sessionskostnad över de fyra försöken. Uppskattad drift- och
operatörstid tillkommer. Resultaten räcker för att jämföra provens faktiska
åtgång. Kostnad per slutfört hostat uppdrag är fortfarande omätt.

### Vad som flyttades i provet

| Jämförelsepunkt | Lokal mekanism | Hostad mekanism i provet |
|---|---|---|
| Modellanrop och kontext | Pythonloopen skickar nästa modellanrop och hanterar historiken. | Managed Agents driver nästa anrop och lagrar kontexten. Bryggan läser sessionens tillstånd och skickar tillbaka klientverktygens svar. |
| Verktyg och granskning | Lokal dispatcher, SQLite, specialistverktyg, granskningssummor och domänkvitton. | Samma lokala komponenter används. Lokal kod prövar vad varje verktyg får göra. Det hostade svaret prövas lokalt innan det visas som en leverans. |
| Återupptagning | Ny lokal process öppnar samma granskning. Lokal avstämning läser ett befintligt domänkvitto. | Samma återupptagning mellan segment. Ett nätverksklientbyte medan ett verktyg väntade verifierades före kvittering. Resultatet hölls i den levande processen. En krasch av den processen mitt i segmentet kräver lokal avstämning och vidare stöd för varaktigt händelseåterspel. |
| Spår och budget | Lokalt spår per modellanrop och budget i projektets AI-lager. | Hostens sessions-id, verktygs-id och listkostnad länkas till samma lokala körjournal. Bryggan behöver konfigurationsöversättning, kostnadsbokföring, händelseavläsning och hantering av transportfel. |
| Kod och drift | Pythonloopen kör både orkestratör och specialister. | Orkestratörens inferensloop och kontexthantering flyttade. Specialisterna använder fortfarande Pythonloopen och wrappern. Provet tog ingen gemensam körkod ur drift. |

Bryggan kopplades in i det diagnostiska anropet till `run_assignment` för
samordningsprofilen. Den ordinarie webbstarten använder sin befintliga
körmotor. Ett produktionsval kräver varaktig koppling mellan sessions- och
verktygshändelser, lokalt köranspråk och det sparade verktygssvaret så att ett
avbrott efter en skrivning kan stämmas av även efter processkrasch.

## Upprepa provet

Kör från arbetskopians reporot med projektets Pythonmiljö inklusive testextras.
Välj en ny katalog för varje `start`. `finish` läser samma katalog i en ny
process. Provet stannar med felkod om en kontroll faller och sparar
delprotokollet för ett registrerat uppdrag. [Röktestet](../scripts/diagnostics/smoke_test_company_mission.py)

```powershell
python scripts/diagnostics/smoke_test_company_mission.py start --scripted --output-dir tmp/prov-scripted
python scripts/diagnostics/smoke_test_company_mission.py finish --scripted --output-dir tmp/prov-scripted

$modellmiljo = 'C:/Claude/Artificiellalecta/.env'
python scripts/diagnostics/smoke_test_company_mission.py start --run-model --output-dir tmp/prov-live --env-file $modellmiljo
# Vid godkänd start, med samma modellkonfiguration och utdata
python scripts/diagnostics/smoke_test_company_mission.py finish --run-model --output-dir tmp/prov-live --env-file $modellmiljo

python scripts/diagnostics/smoke_test_company_mission.py start --managed --output-dir tmp/prov-managed --env-file $modellmiljo
python scripts/diagnostics/smoke_test_company_mission.py finish --managed --output-dir tmp/prov-managed --env-file $modellmiljo
```

`start.json` och `finish.json` innehåller status, id:n, beslutsbindningar,
aggregat, tider och segmentkostnader. `runs/` innehåller segmentjournaler.
Modellanrop via Messages API finns i `ai_calls.jsonl` med modellreferens,
request-id, token, anropstid och kostnad. Hostens sessions-id och
användningsposter finns i segmentjournalerna. `managed-resources.json`
identifierar provets agentversion och miljö. `managed-reconnect.json` länkar
det återlästa väntande verktygsanropet till dess hostade session.
Utkast ligger i arbetskopians `logs/agent_artifacts/`. Granska modellens
utkast och slutsats manuellt mot källan och tabellen vid ett lyckat modellprov.
En ny körning får nya uppdrags-, gransknings- och kvitto-id:n.

För ett hostat prov behövs samma fungerande Anthropic-nyckel för modell-
och sessions-API:t. Skriptet skapar en namngiven testagent och en begränsad
miljö i den befintliga arbetsytan samt en session för varje
samordningssegment. Bara fiktiva underlag får användas i provet.
[Hostad brygga](../src/testing/managed_company_orchestrator.py)

## Regressionstest

Det slutliga ändringsurvalet via `scripts/testing/run_tests.py --changed --base
origin/main --run` täckte hela lokala sviten och gav 1 732 godkända,
113 bortvalda, noll överhoppade och noll fel. Röktestets skriptade
omstart med förhandsberäkningen godkändes separat. Det befintliga pilotprovet
simulerar dessutom ett förlorat svar efter att aktiveringsförslaget har
sparats. Avstämningen hittar samma förslag. Ett annat pilotprov kontrollerar
att ändrat eller saknat källunderlag stoppar fortsatt godkännande.
[Pilotproven](../tests/test_company_missions.py) · [Teststrategin](teststrategi.md)

På Windows användes `TEMP` och `TMP` i den skrivbara arbetskopian. En
gitignorerad `.env` utan värden avgränsade den från huvudkatalogens
Postgres-konfiguration, som annars gav fel i ett prov av testkörarens
miljöval. Ändringsurvalet pekade inte ut några Postgres-prov.

## Förslag till beslut

Behåll den lokala loopen för ordinarie drift. Den hostade loopen kan driva
samordningssegmenten och använda bolagets befintliga verktyg, men provet
visar behovet av lokal verifiering även av svar som kommer efter ett
korrekt genomförandekvitto. Ett eventuellt byte bör bygga på upprepade
godkända uppdrag, varaktigt återspel efter processavbrott och en uppmätt
minskning av egen drift eller kod som behöver förvaltas.
