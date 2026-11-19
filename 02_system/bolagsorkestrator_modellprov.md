# Bolagsorkestratören i Fråga bolaget – modellprov och driftval

**19 november 2026.** GitHubs `refs/heads/main` verifierades till
`6c0bcaba5cda85ab8e40cae9400d668f4c84bdec`, med pilotmergen `cdd1d4f` i historiken.
Provet kördes i en separat arbetskopia på `codex/bolagsorkestrator-modellprov`.

Det skriptade SQLite-provet gick från beställning till verifierad schemaläggning
och källbundet slutsvar. Samma webbväg med projektets modellkonfiguration
stannade vid autentiseringen i det första segmentet. Båda hostade alternativen
stannade också vid autentiseringen. Jämförelsen ger ett verifierat facit för
verksamhetskedjan och en avgränsning för nästa prov. Tid och kostnad per
slutfört uppdrag med riktiga modeller återstår att mäta.

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

## Lokal körning med projektets modellkonfiguration

Fråga bolaget registrerade uppdrag `BO-f45ea8d1b64a40faa9833406ac954693`.
Första segmentet använde rollen `standard` och skickade ett anrop till
`anthropic:claude-sonnet-5` via Messages API. Anthropic SDK 1.13.0 loggade
HTTP 401 `invalid x-api-key` med request-id `req_011ChCgvmbzT9NQTMdu7ti3w`.
Konfigurerat reservval var `openai:gpt-6.1-sol`. Vid autentiseringsfel stannar
AI-klienten och inget reservanrop registrerades. Compliance och aktuarien hade
rollen `deep` med primär `anthropic:claude-opus-5` och reserv
`openai:gpt-6-astra`, men kom aldrig till start.

Uppdraget stannade i `needs_human`, med misslyckat körspår
`run-f45ea8d1b64a40faa9833406ac954693`. Det fanns noll verktygsanrop,
specialistbeställningar, beslut och kvitton. Körtiden var 3,635 s, varav
2,946 s i segmentet och cirka 213 ms i det loggade API-försöket.
Inga in- eller uttokens rapporterades, och harness bokförde 0 USD.
Modellens faktiska svarkvalitet och versionsidentifierare gick inte att observera.

## Hostad agentloop – åtkomst och jämförelse

Åtkomstkontrollerna använde enbart läsanrop med de befintliga nycklarna, utan
uppdragsdata. Båda tjänsterna gav HTTP 401. Därför saknas ett hostat
uppdragsresultat, en sessionsreferens och mätvärden för modellen och hosten.

| Tjänst | Läsprov | Svar |
|---|---|---|
| Claude Managed Agents | `GET /v1/agents?limit=1` med beta `managed-agents-2026-04-01` | 401 `invalid x-api-key`, `req_011ChCgUBkK1vpYfSKvyKGY2`. Modellistan gav också 401, `req_011ChCgUCJne8hpkyJ5Wh8nx`. |
| OpenAI Agents API | `GET /v1/agents/sessions?limit=1` med beta `agents=v1` | 401 `expired_secret_key`, `req_01d3fa8d0f4e461198a9db1d2f7bd566`. Modellistan gav också 401, `0d2b4a08-a4d8-4771-a385-799f0d6aa474`. |

**Första kandidat när åtkomsten fungerar.** Claude Managed Agents kan enligt
dokumentationen köra Claude-modeller i sin hostade loop. Det ger möjlighet att
köra samma `claude-sonnet-5` för orkestratören i båda försöken och behålla
projektets lokala specialistprofiler. Leverantören håller sessionen, skickar
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

### Vad som kan flyttas och vad som måste verifieras

| Jämförelsepunkt | Lokalt observerat | Hostat prov efter fungerande åtkomst |
|---|---|---|
| Resultat och mandat | Två specialistuppdrag, två granskningsbeslut och ett verifierat kvitto med skriptad modell. | Ersätt bara orkestratörens loop. Anslut dess befintliga tre verktyg via samma dispatcher, med verktygsscheman och mandat från den lokala profilen. Använd samma indata, specialister och beslut. Kör resultatverifieraren lokalt även för hostade svar. |
| Granskning och spår | Webbens granskningssummor, körspår och domänkvitton verifierades lokalt. | Lokal uppdragsstatus ska styra när en körning får fortsätta och vilket anspråk verktygen får använda. Bind leverantörens session, tur och verktygsanrop till lokal uppdragsrevision och kör-id. Kör samma negativa prov för beslut, källa och mandat. |
| Återupptagning | Ny lokal process läste samma väntande granskning. Omfråga gav ett domänkvitto. | Bryt anslutningen vid ett väntande verktygsanrop och efter att verktyget har skrivit lokalt före kvitteringen till hosten. Återanslut, stäm av det väntande anropet och återsänd det sparade svaret. Visa att ett återspel ger en enda lokal beställning med rätt underlag. |
| Tid och kostnad | Skriptad tid och tid till autentiseringsfel är uppmätta. | Mät total tid, aktiv orkestratörs- och specialisttid, väntetid, token, hostens avgift och eventuella omförsök per slutfört uppdrag. |
| Underhåll | Pythonloopen betjänar fortfarande även specialisterna. | Hostens loop, komprimering och tekniska sessionsåterupptagning kan ersätta motsvarande arbete för orkestratören. Verktygsbryggan, lokala budgetgränser, händelseavstämning och spårlänkning tillkommer. Verifiera vilken lokal orkestratörskod som faktiskt kan tas ur drift. |

Den minsta integrationen hör hemma vid orkestratörsgrenen i
`CompanyMissions._run`. Kör en hostad tur per lokalt samordningssegment och
låt det lokala anspråket avgöra vilka pågående verktygsanrop som får verkställas.
Sätt ett hostat kostnadstak där tjänsten erbjuder det och boka användningen
mot samma lokala rotbudget. Verifiera länkning och eventåterspel innan
domänskrivningar tillåts. Specialistkörningar och domänbeslut kan använda
samma befintliga vägar i både baslinje och jämförelse.

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
```

`start.json` och `finish.json` innehåller status, id:n, beslutsbindningar,
aggregat, tider och segmentkostnader. `runs/` innehåller segmentjournaler.
I modelläge innehåller `ai_calls.jsonl` dessutom faktisk modellreferens,
request-id, token, anropstid och kostnad när leverantören returnerar dem.
Utkast ligger i arbetskopians `logs/agent_artifacts/`. Granska modellens
utkast och slutsats manuellt mot källan och tabellen vid ett lyckat modellprov.
En ny körning får nya uppdrags-, gransknings- och kvitto-id:n.

För ett hostat prov behöver operatören lägga in minst en giltig nyckel för
både modell- och sessions-API:t. Börja med listanropen i åtkomsttabellen.
Verifiera sedan rätt att skapa en session och stöd för den modell som ska
användas innan verktygsbryggan ansluts. Använd den skriptade körningen som
facit och upprepa båda riktiga körsätten med samma källversion och demoseed.

## Regressionstest

Hela lokala sviten via `scripts/testing/run_tests.py --all --run` gav 1 732
godkända och 113 bortvalda. Ändringsurvalet med beroenden via
`--changed --base origin/main --run` gav 1 137 godkända och 89 bortvalda.
Båda körningarna hade noll överhoppade och noll fel. Det befintliga pilotprovet
simulerar dessutom ett förlorat svar efter att aktiveringsförslaget har
sparats. Avstämningen hittar samma förslag. Ett annat pilotprov kontrollerar
att ändrat eller saknat källunderlag stoppar fortsatt godkännande.
[Pilotproven](../tests/test_company_missions.py) · [Teststrategin](teststrategi.md)

På Windows användes `TEMP` och `TMP` i den skrivbara arbetskopian. En
gitignorerad `.env` utan värden avgränsade den från huvudkatalogens
Postgres-konfiguration, som annars gav fel i ett prov av testkörarens
miljöval. Ändringsurvalet pekade inte ut några Postgres-prov.

## Förslag till beslut

Behåll den lokala loopen som baslinje tills en hostad körning har klarat samma
kontroller med riktiga modeller. Pröva Claude Managed Agents först om
modell- och sessionsåtkomsten kan återställas för samma Claude-modell.
Underlaget för ett eventuellt byte bör visa både ett korrekt och återupptaget
verksamhetsutfall och vilken egen drift eller kod som faktiskt kan tas bort.
