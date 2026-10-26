# OC-0 – beslutsförslag för operatörscentralens kontrakt

> **Datum:** 2026-10-26. **Version:** 0.1. **Status:** rekommendationerna A–X
> godkända av Karl i chatten 2026-10-26, utan avvikelser, loggat som **B-038**.
> Designen är beslutad; funktionerna är inte implementerade genom dokumentet.
> **Omfattning:** endast Markdown. Ingen kod, databasändring, ny behörighet eller
> styrinställning införs. [B-038](../BESLUTSLOGG.md#b-038--2026-10-26--oc-0-operatörscentralens-kontrakt-och-gemensamma-modell-budgetpolicy)
> dokumenterar operatörens godkännande separat.
> **Ägare:** projekt 10; måttägarskap hos projekt 2 och respektive domän består.

## 1. Godkända beslutsval

Centralen blir bolagets ledningsyta enligt B-036, med gemensamma mått,
spårbara frågor och kontrollerad modell-/budgetstyrning. Karl förblir
beslutsfattare. Frågeingången blir ingen ny agent med VD-befogenheter.
Förslaget preciserar [arkitekturunderlaget](operatörscentral.md) och
[projektplanen](../projekt/10_operatörscentral/PROJEKTPLAN.md).

Tabellen bevarar de rekommendationer och alternativ som Karl granskade.
Samtliga rekommendationer A–X är godkända genom B-038. Detaljer och villkor
i angiven paragraf ingår i respektive val; genomförandet återstår.
Val R–W beskriver en sammanhängande styrväg. Git-alternativet i R/S valdes inte.

| Val | Rekommendation | Alternativ och avvägning | Kontrakt |
|---|---|---|---|
| A | Bygg läsbar ledningsöversikt först; handlingar följer befintliga domängränser | Samla all handläggning i centralen: enklare ingång men blandar mandat och arbetsenheter | §2 |
| B | Ett versionssatt måttkontrakt för BI, central och agentsvar | Egna UI-mått: snabbare första skärm men risk för olika betydelser | §3.1 |
| C | Skilj utfall/prognos/scenario från tillgänglighet och kvalitet | En enda statuslista: kortare men kan dölja att ett scenario är inaktuellt | §3.1 |
| D | Skilj affärsdatum från verklig logg- och budgettid; bind miljö och scenario | En gemensam klocka: enklare men simulerad tid kan påverka budget och färskhet | §3.2 |
| E | Börja med registrerat bestånd, registrerade betalmarkeringar och agentdrift; märk mognad | Vänta på alla ekonomiska motorer: rikare helhet men senare användbar överblick | §3.3 |
| F | Endast granskade aggregat i ledningsytan; minsta cellstorlek 10 | Persondrillning i centralen: mer detalj men ett nytt PII-mandat | §3.4 |
| G | Gemensamt händelsehölje med referens till varje ägares original | Läs varje källa direkt utan index: mindre lagring men långsammare och svårare att avstämma | §4.1 |
| H | Idempotent import med stabil källidentitet; osäker koppling blir datalucka | Importera enbart nya loggar med försöks-id: enklare garanti men äldre historik blir separat underlag | §4.2 |
| I | Summera unika anropsförsök, redovisa känd kostnad och okänt underlag separat | Visa bara leverantörsavstämd kostnad: säkrare fakturabelopp men senare återkoppling och sämre uppdragskoppling | §4.3 |
| J | Skilj leverans från godkänd kvalitet; mät uppdrag och körsegment separat | Räkna varje avslutad körning som lyckad leverans: lättare men missvisande nytta | §4.4 |
| K | Börja med explicita sandboxtrösklar för kostnad, kvalitet och kontrollfel | Endast manuellt beredda ledningsfrågor: färre automatiska signaler men större ansvar att upptäcka avvikelser | §5.1 |
| L | Eget ledningsunderlag med ägare, beslut, genomförandereferens och uppföljning | Använd försäkringens godkännandekö för allt: färre listor men fel domänansvar | §5.2 |
| M | Ett uttryckligen valt team per fråga i första leveransen | Automatisk samordning direkt: smidigare men kräver ännu obyggd 3c-1 | §6.1 |
| N | Betrodd beställning binder period, källor, miljö, scope och budget | Enbart fasta frågemallar med låsta källor: enklare validering men färre möjliga frågor | §6.2 |
| O | Källbundet svar med luckor, körreferens och kostnadstäckning | Enbart länk till granskad BI-fördjupning: mindre modelltolkning men svagare förklaring i centralen | §6.3 |
| P | Lokal namngiven operatörsinloggning med serverlagrad session före styrskrivningar | OIDC före första styrvy: bättre för flera användare men kräver separat identitetsintegration | §7.1 |
| Q | Serverkontrollerad rättighet, sessionsbunden CSRF och nylig återautentisering vid aktivering | Ny inloggning inför varje styråtgärd med samma rättighets-/CSRF-kontroll: kortare behörighetsfönster men fler avbrott | §7.2 |
| R | Ett varaktigt, versionssatt policyregister hos harness för både OC-5 och 3b-9 | Endast Git/YAML med deploy: enklare drift men ingen direkt varaktig operatörsaktivering | §8.1 |
| S | YAML äger befogenheter och modellkatalog; registret äger migrerade driftval och budgetar | Behåll även driftvalen enbart i Git/YAML: tydlig källkedja men operatörsändringar kräver deploy, som alternativ R | §8.2 |
| T | Tillåtna leverantörer begränsar hela modellkedjan; undantag är synliga och begränsade | Erbjud endast blandad godkänd policy: färre valideringsfall men inget exklusivt leverantörsval | §8.3 |
| U | Förhandsgranskning och atomisk aktivering mot förväntad basversion | Granskad release för varje policybyte: befintlig Git-kontroll men långsammare styrning | §8.4 |
| V | Bind modell-/budgetversion till rot, barn och fortsättning; återställ med ny aktivering | Vänta ut eller avsluta alla rötter före byte: en aktiv version i drift men väntande uppdrag fördröjer bytet | §8.5 |
| W | Återanvänd körgränser via 3b-9; periodbudget öppnas först med gemensam reservationsbok | Behåll periodbudget som enbart uppföljningsmål: mindre runtime men ingen automatisk periodspärr | §8.6 |
| X | Inför stegvis med dokumenterade kontraktsprov och tydliga beroendegrindar | Bygg hela ytan innan verifiering: färre delöverlämningar men större integrationsrisk | §9 |

## 2. Beslutad grund och verifierat nuläge

B-017/B-028:s operatörs- och domänvägar, B-025/B-026:s AI-lager och team,
B-029:s gemensamma BI-underlag, B-034:s Digital klarhet och B-036:s plattform
består. B-037 styr verksamhetsförmågor och avgränsning av test-/demostöd.
Centralen bygger inga egna kapital-, FTA-, premie- eller bokföringsmotorer.
Den visar inte rutinärenden som VD-beslut. Bolagsförslag kan visas här men
avgörs fortfarande av den domän som äger dem.

Granskning mot main `952d9de`, hämtad och avstämd 2026-10-26:

| Finns | Saknas för detta förslag |
|---|---|
| `CallRecord` med run/team/modell, utfall och möjlig kostnad | Eget försöks-id, prisversion, full spårning av SDK-omförsök och miljöbindning |
| JSONL-journal med event-id, sekvens och rot-/fortsättningsreferenser | Gemensam import/indexering, uppdragsleveranser och ledningseskaleringar |
| `RunRequest`, begränsade profiler och länkad fortsättning | VD-frågeadapter, allmänna BI-verktyg och 3c-1-delegering |
| Körgränser i `ecosystem.yaml`, rollmappning/priser i `ai_config.yaml` och env-överstyrning | 3b-9:s inställningsvy, policyregister, atomisk aktivering och periodbudgetbok |
| Lokal konfigurerad handläggaridentitet, Host-kontroll och formulärtoken | Verifierad operatörsinloggning och behörighet för modell-/budgetstyrning |
| `FlowConsole`, flödesmotor och tjänstelagrets godkännandekö | Flytt till centralen och verifierad verksamhets-/modellkoppling enligt 3c-V |

Detta är en designleverans. Inget i §3–9 ska läsas som redan implementerat.
Fulla databas-/API-scheman, migration och kod hör till respektive byggpaket.

## 3. Måttkontrakt – B–F

### 3.1 Definition och observation är två olika objekt

Projekt 2 förvaltar den gemensamma katalogen. Domänägaren granskar beräkning
och tillämplighet; projekt 10 ansvarar för presentationen. Samma `metric_id`
och definitionsversion används i dashboard, central, rapport och agentsvar.

| Objekt | Obligatoriskt innehåll |
|---|---|
| `MetricDefinition` | `schema_version`, stabilt `metric_id`, `definition_version`, svenskt namn, definition/formel, enhet/valuta, population och undantag, datum-/periodtyp, tillåtna dimensioner, additivitet, källkontrakt, ägarteam, granskningsreferens, färskhetsgräns, kvalitetskontroller och sekretessregel |
| `MetricObservation` | `observation_id`, definitionens id/version, `environment_id`, `dataset_ref` med version/hash, affärsdatum eller period, dimensioner, `kind`, `availability`, `quality`, `value`, `computed_at`, `data_through`, underlags-/beräkningsreferenser och tillämpade modell-/grundversioner |

`kind` är `actual`, `forecast` eller `scenario`; scenario kräver `scenario_id`
och versionsbundna antaganden. `availability` är `available`, `not_calculated`,
`missing`, `stale`, `not_applicable` eller `suppressed`. `quality` är
`verified`, `provisional`, `failed` eller `unknown`, med kontrollreferenser.
`verified` kräver godkända definierade kontroller, inte bara en lyckad SQL-fråga.

`value` är decimaltal som sträng för belopp/kvot, heltal för antal, eller null.
Null är obligatoriskt för `not_calculated`, `missing`, `not_applicable` och
`suppressed`. Ett gammalt värde får visas med `stale`, tydlig datering och utan
grön kvalitetsmarkering. Ett verifierat nollvärde kräver komplett population;
tomt eller trasigt underlag är aldrig noll. Kvot med nollnämnare får null och skäl.
Ingen procent, differens eller jämförelse räknas om saknade/jämförbara grunder
inte kan styrkas. Status får inte förmedlas enbart med färg.

Brytande definitionsändring ger ny version och explicit jämförbarhetsbesked.
En rättad observation får nytt id och `supersedes_observation_id`; underlag
och tidigare publicerat resultat bevaras. Läsyta använder senaste giltiga
revision, medan frysta rapporter behåller sina ursprungliga referenser.

### 3.2 Tid, miljö och färskhet

Affärsperioder använder halvöppet intervall `[from, to)` med datum och
`Europe/Stockholm`. Datumvärden har `as_of_date` och får inte summeras över tid.
UTC-tider med tidszon används för `computed_at`, `ingested_at`, händelser,
sessioner och kostnadsbudget. Simuleringsdatum ändrar aldrig dessa klockor.

Miljö är en betrodd datasetidentitet, inte en etikett modellen väljer:
`demo`, `svc_test` och `lakebase` binds till respektive datauppsättning; ingen
av dem innebär riktiga kunder. Återställda/scenariobundna dataset får egen
identitet/version. Olika miljöer, valutor, definitioner eller scenarier slås
inte ihop. Aggregat summeras bara över disjunkta populationer enligt katalogen.

Föreslagna startgränser: drifts-/kostnadsimport är inaktuell efter 15 minuter
utan lyckad kontroll av källans vattenmärke; aktuellt bestånd efter 24 timmar
utan verifierad läsning. En stillastående men kontrollerad logg är färsk även
utan nya körningar. Historiska stängda perioder bedöms mot sin frysta
underlagsversion; ett gammalt affärsdatum är inte i sig ett importfel.
Öppna perioder märks preliminära och visar genom vilken tid data ingår.

### 3.3 Första måttkatalogen

Definitionerna är godkända som design genom B-038; projekt 2 och domänägaren
verifierar läsadaptrar och beräkningskontroller före publicering. Senare ekonomiska mått kräver
egna versionssatta definitioner innan de får talvärden.

| Mått-id | Population, beräkning och period | Ägare och mognad |
|---|---|---|
| `insured_registered_count` | Antal unika `insured_persons.id` i daterad ögonblicksbild, alla registrerade statusar; inga namn/id i resultatet. Ett datumvärde, inte antal aktiva pensionsavtal | Försäkring granskar; projekt 2 publicerar. Tabell finns. Historisk serie kräver sparade ögonblicksbilder, inte dagens status bakdaterad |
| `premium_paid_recorded_sek` | Summa `amount_sek` för `premium` och signerade `adjustment` med `status=paid` och `paid_date` inom vald period; `fee` exkluderas. SEK, periodflöde. Rättelser räknas en gång som egna rader, inte genom att skriva över originalet | Försäkring. Avser registrerat betald premie, inte bankavstämt kassainflöde. `paid` utan datum underkänner kontrollen; historik binds till ögonblicksbild |
| `agent_cost_known_usd` | Summa känd försökskostnad enligt §4.3 i verklig tidsperiod; även fel och reservförsök | Harness/AI. Prisuppskattning i USD med täckningsmått, inte faktura |
| `agent_unknown_attempts_count` | Antal unika synliga försök med okänd möjlig debitering; heltal för samma period som kostnaden | Harness/AI. Dolda SDK-försök går inte att räkna; redovisa dessutom ofullständig täckning |
| `tasks_delivered_count` | Unika `task_id` med accepterad leveransreferens under perioden; fortsättning eller flera filer ökar inte antalet | Ansvarigt team; leveranskontraktet i §4.4 behöver byggas |
| `task_quality_pass_rate` | Godkända slutliga kvalitetskontroller / alla uppdrag med avgjord kontroll i perioden. Visa täljare/nämnare och antal utan avgjord kontroll separat | Ansvarigt team. Ingen kvot vid noll avgjorda; kräver kontrollversion och definierad uppdragstyp |
| `capital_market_value_sek`, `fta_sek`, `consolidation_ratio`, `liquidity_coverage` | Ingen formel införs här. Ingen kvot får härledas ur premiehistorik | Projekt 5/6 och projekt 2; `not_calculated` tills grunder, avstämningar och motorer verifierats. Tillämplighet beslutas av domänen |

Premier per premiemånad är ett annat mått än betalmarkeringar per betaldatum.
Periodjämförelser kräver samma definition och lika långt, fullständigt underlag.
Saknade bank-/faktura-/förväntansunderlag ger inga påståenden om förfallna premier.

### 3.4 Aggregat och åtkomst

Individdata, ärendenummer, råa prompter och fritext ur försäkringsärenden visas
inte i centralens bolags-/kostnadsvyer. Granskad adapter gör dataminimering före
resultatet når modell eller webbläsare. Personbaserade segment med färre än
10 individer undertrycks; kompletterande undertryckning hindrar att totaler
och differenser röjer små celler. Om skyddet inte kan upprätthållas nekas
segmentfrågan. Tröskeln är ett föreslaget sandboxskydd, ingen garanti för anonymitet.
Teamens tekniska körantal följer separat åtkomstregel och är inte personsegment.

Länkar till specialistytor ger inga nya rättigheter. Källreferenser är säkra
handtag, inte godtyckliga sökvägar eller publika länkar till skyddad data.

## 4. Händelser, agentekonomi och leveranser – G–J

### 4.1 Gemensamt hölje, skilda original

Ett `CentralEvent` är en sanerad läsprojektion. Domänens original är fortsatt
auktoritativt: `operation_events` för försäkringshandlingar, harnessjournalen
för körning, AI-loggen för synliga modellförsök, flödeslagringen för grindar
och det föreslagna policyregistret för aktiveringar.

| Fältgrupp | Kontrakt |
|---|---|
| Identitet/version | `schema_version`, `event_id`, `event_type`, `source_system`, `source_event_ref`, `source_schema_version`, `payload_hash` |
| Tid/avgränsning | `occurred_at` i UTC, `ingested_at`, `environment_id`, `dataset_ref`; affärsdatum/period separat när relevant |
| Samband | `task_id`, `run_id`, `root_run_id`, `parent_run_id`, `continuation_of`, `flow_id`, `flow_step_id`, `attempt_id` när de finns; null med kopplingsstatus när de saknas |
| Ansvar/bevis | team/agent, betrott aktörs-id eller systemidentitet, `policy_version`, `status`, sanerad orsakskod, `evidence_refs`, eventuell `supersedes_event_id` |

Händelsetyper i projektionen: `run_started`, `run_status_changed`,
`model_attempt_recorded`, `delivery_recorded`, `quality_checked`,
`escalation_opened`, `management_decision_recorded`, `policy_activated`
och `reconciliation_required`. Mappning från originaltyp versionshanteras;
nya namn innebär inte att originalproducenten redan emitterar dem.

Endast källsystemets beslut kan ge statusen verkställd. Ett modellsvar eller
en ledningsinriktning är inte utförandekvitto. Originalens godkännande- och
händelsereferenser bevaras i skyddat underlag och projiceras efter behörighet.

### 4.2 Import, ordning och dubbletter

Harnesshändelser dedupliceras på källsystem, miljö/dataset och originalets
`event_id`. Samma id med annan hash är konflikt, inte en tyst uppdatering.
Sekvensordning gäller inom journalen; ingen global ordning antas mellan källor.
Försenade händelser räknas till sin ursprungstid och ger ny observationsrevision.
Skadad rad eller sekvenslucka ger ofullständig täckning och avstämningsbehov.

För äldre AI-JSONL utan event-id tilldelar importen en beständig källidentitet
och bevarar den över flytt/rotation. Nyckeln blir källidentitet + radens
byteposition, med hash för integritetskontroll. Kopierad/överlappande logg
måste registreras som samma ursprung med positionsmappning; okänt ursprung
sätts i karantän före totalsummering. Identiska försök på olika positioner
räknas separat. En innehållshash, tidsstämpel eller leverantörens `request_id`
ensam används aldrig som allmän dedupliceringsnyckel.

En framtida AI-kontraktsutökning tilldelar `attempt_id` före varje synligt
försök och binder det till run, steg, miljö, policy- och prisversion. Saknade
historiska uppgifter gissas inte: äldre priser/policy markeras okända om
kopplingen inte kan styrkas. Körningar utan miljöbindning hålls i en egen
oallokerad avstämningspost, skild från miljöernas totalsummor.

Importen är återkörbar och håller vattenmärken per källa. Ett källstopp eller
en okänd schemaversion visas som datalucka; tidigare observationer märks med
täckningsstatus. Index/projektion kan byggas om från original och importmanifest.
Original gallras inte genom OC-0; retention och skydd följer sina ägare och
[harnessens lagringsgränser](harness.md#81-format-och-skydd).

### 4.3 Kostnadskontrakt och avstämning

Kostnadsunderlaget innehåller per försök: identitet, run/steg/team/agent,
leverantör/modell, tidsstämpel, token-/cacheuppgifter när kända,
`cost_usd` eller null, `price_version`, `cost_basis`, utfall och reservkedja.
`cost_basis` anger exempelvis prisuppskattning eller avstämd leverantörspost.
Belopp lagras/beräknas med decimalprecision; avrundning sker sist för visning.

`known_cost = summa unika försök med känd kostnad`. För ett uppdrag hämtas
alla dess segment och, när 3c-1 finns, barn. Kostnaden hänförs till teamet som
gjorde försöket. Uppdragstotalen är en alternativ gruppering av samma poster,
ingen extra kostnadsrad. `RunResult.cost_usd` och fortsättningens ackumulerade
belopp får inte adderas till AI-försöken. Misslyckade primärförsök och lyckad
reserv räknas var för sig. Leverantörsfakturans avstämning redovisar differens
och period; den ersätter inte tyst tidigare prisuppskattningar.

Ett fel med nullkostnad är okänd möjlig debitering. `skipped` kan räknas som
noll bara när det styrks att inget anrop skickades. Saknad tokenmetadata får
inte fyllas med noll för att skapa en kostnad. SDK-omförsök kan vara dolda
inom ett synligt försök; deras antal/kostnad får inte påstås vara känt.

Varje kostnadssummering visar känd USD-summa, antal synliga försök med okänd
kostnad, antal oallokerade poster, importfärskhet, prisgrund och
`coverage=complete|partial|unknown`. `complete` kräver även verifierad
försökstäckning; en lyckad import av alla tillgängliga rader räcker inte.
Med okänt underlag märks summan som känd del, inte total eller kostnadsfri.
SEK-visning kräver separat versionsbundet kursunderlag och kursdatum.

Avstämningsexempel, syntetiska USD-belopp, inte aktuella modellpriser:

| Underlag | Förväntad summering |
|---|---|
| Rotförsök 0,10; felande primär 0,02; reserv 0,03; fortsättning 0,04; framtida barn 0,05 | Känd del 0,24 USD, fem unika försök. Rot-/segmentresultat adderas inte |
| Samma rader importeras igen | Fortfarande 0,24 USD och fem försök |
| Ytterligare timeout med okänd debitering | 0,24 USD känd del, ett okänt försök, ofullständig täckning |
| Verifierat överhoppad, oskickad modell | Oförändrad kostnad, eget händelsespår; inget okänt debiterat försök |
| Kostnad saknar säker run-/miljökoppling | Oallokerad avstämningspost; inte fördelad efter gissning |

### 4.4 Uppdrag, teamstatus och kvalitet

Teamets mognad (`planned`, `configured`, `verified`) är skild från körläget
(`running`, `waiting`, `stopped`, `idle`, `unknown`). Ingen körning betyder
inte felfri drift. Körresultatens befintliga `RunStatus` bevaras; de slås inte
ihop till ett grönt slutläge. `waiting_approval` är väntan, inte genomförande.
Segment kan vara avslutade medan uppdraget fortfarande väntar på fortsatt arbete.

`Delivery` binder `delivery_id`, `task_id`, version, ägarteam, leveransslag,
artifact-/resultathandtag, datum, källor, run-referenser och accepterad version.
`QualityCheck` binder kontroll-id/version, uppdragstyp, granskare eller betrodd
kontroll, `pass|fail|not_reviewed`, underlag, tid och leveransversion.
Omarbetningar ersätter en leveransversion, de räknas inte som nya uppdrag.
Registrerat mottagande av en leverans innebär inte godkänd kvalitet.
I kvalitetskvoten räknas varje uppdrag en gång utifrån senaste avgjorda
kontrollen av aktuell leveransversion, med den kontrollens tid som periodgrund.
En senare omgranskning ger en ny observationsrevision, inte en extra kontroll
i samma nämnare. Tidigare publicerad kvot kan fortfarande följas till sitt underlag.
Kostnad/leverans anger kohort och inkluderar misslyckat arbete i samma kohort;
periodkostnad delas inte okritiskt med leveranser från en annan period.

## 5. Ledningseskaleringar – K–L

### 5.1 Föreslagna trösklar

Trösklarna är sandboxval för ledningsuppmärksamhet. De inför inga legala
gränsvärden eller nya automatiska handlingar. Versionerade regler prövas av
betrodd kod på avgränsade, tillräckliga data. En agent kan föreslå en fråga;
systemet måste kontrollera bevis och minimera innehållet innan den visas.

| Trigger | Villkor och tidsfönster | Ägare och hantering |
|---|---|---|
| Kontroll-/behörighetsfel | Ett styrkt brott mot identitet, tillåten modellkedja eller godkännandegräns | Utveckling, med compliance vid mandatfråga. Omedelbart ledningsunderlag; befintlig skyddskod nekar handlingen oberoende av eskalering |
| Kostnadstäckning | Minst ett synligt försök med okänd möjlig debitering eller import äldre än 15 minuter | Utveckling/AI. Omedelbar uppmärksamhet; inga säkra budgetmarginaler visas på ofullständigt underlag |
| Återkommande körstopp | Minst tre olika rotuppdrag i samma team med `failed`, `blocked`, `limit_reached` eller `reconciliation_required` inom rullande 24 verkliga timmar | Teamägaren. Barn/fortsättningar räknas inte som fler rötter; operatörens rutinavslag är inte körfel |
| Kvalitet | Minst tio uppdrag med avgjord kontroll och över 10 % underkända inom rullande sju verkliga dygn, samma team/uppdragstyp/kontrollversion | Teamägaren. Ej granskade leveranser visas separat; inga slutsatser ur för liten nämnare |
| Periodbudget, senare | Känd kostnad + öppna konservativa reservationer når 80 % av beslutad periodgräns; nya reservationer som skulle överstiga 100 % nekas | Teamägaren. Först efter verifierad reservationsbok i §8.6, ingen sådan spärr utlovas nu |
| Ekonomisk/domänmässig avvikelse | Domänägaren lämnar ett granskat underlag med egen väsentlighet, tidsfrist och grundversion | Rätt domänteam. Inga automatiska FTA-/konsolideringströsklar innan måtten finns |

Enstaka löneärenden, vanliga godkännanden och kompletteringar stannar hos
specialisten. Systematiskt hinder, ändrad inriktning, kontrollfel eller
överskridande risk kan bli ett aggregerat ledningsunderlag. Vid otillräcklig
data visas dataluckan; frånvaro av eskalering är inte bevis på gott bolagsläge.

### 5.2 Objekt, beslut och uppföljning

`ManagementIssue` innehåller id/version, kategori, triggerregel/version,
miljö, period, ägarteam, allvar, frågeställning, underlagsreferenser och hash,
alternativ (inklusive avvakta), rekommendation, konsekvenser, osäkerhet,
beslutsfrist med grund, uppföljningsdatum och säkra specialistlänkar.

Livscykel: `open → acknowledged → decided → implementing → followed_up → closed`.
`deferred` kräver skäl och nytt granskningsdatum; återöppning ger nytt versionsspår.
Beslutet binder exakt underlagsversion, valt alternativ, Karl som verifierad
beslutsfattare, tid och skäl. Ändrat underlag kräver nytt ställningstagande.

Dubblettnyckel är regel/version + team + miljö + berört problem/period.
Upprepade mätningar uppdaterar samma öppna frågas bevis, inte en ny fråga vid
varje skärmladdning. Allvarlig försämring eller ny period efter stängning kan
öppna en länkad fråga. Kvittering stänger inte problemet. Ägaren föreslår
avslut med uppföljningsbevis; Karl stänger eller begär mer underlag.

Ett inriktningsbeslut ger ett genomförandeuppdrag eller en policydraft.
Försäkringsändringar kräver fortfarande tjänstelagrets godkännande,
flöden sina hashbundna grindar och andra domäner sina beslut. `decision_id`
länkas till respektive genomförandekvitto. Ingen ny generell godkännandekö
byggs i `src/services/`, och ett klick på inriktning aktiverar ingen policy.

## 6. Frågerouting och svar – M–O

### 6.1 Ett team åt gången

Första frågeingången låter Karl välja team. Ett versionssatt routingregister
kan föreslå team enligt tabellen; förslaget ger inga befogenheter och kör
ingen modell. Vid tvetydighet visas möjliga ansvar och begäran om precisering.

| Frågeområde | Föreslaget ansvar | Tillgänglighetsgräns |
|---|---|---|
| Regel, tillämplighet, styrdokument | `compliance` via konfigurerad teamledare | Källäsning/utkast finns för avgränsade uppdrag; ingen komplett regelbevakning |
| Beräkningsgrund, beståndseffekt | `aktuarie` via teamledare | Befintlig parameteranalys kräver uttryckligt mandat; ingen allmän FTA-motor |
| Registrerat bestånd/premier | `forsakring` via teamledare | Ärendemandatet i dag är inte ett VD-mandat för hela beståndet; ny granskad aggregatförmåga krävs |
| Agentkostnad, drift, teknik | `utveckling` när profil och analysverktyg är verifierade | Loggar finns, men allmän frågeagent/verktyg för detta saknas |
| Kapital/allokering; ekonomi/bokslut; kommunikation | `kapital`; `ekonomi`; `kommunikation` | Konfigurerade namn är inte verifierade förmågor; ingen körning utan profil och rätt verktyg |

Upplösning till teamledare sker från granskad körprofil, inte hårdkodad
ny chefsagent. Obyggd förmåga ger `unavailable` med nästa beroende och utan
modellanrop. En fråga om två team avgränsas till ett eller blir två
operatörsbeställda uppdrag; ingen dold delegering/syntes i första leveransen.
Kända flerteamprocesser använder befintlig flödesmotor. Automatisk samordning
kräver 3c-1 med barnreferenser, gemensam rotbudget och djup-/antalstak.
Compliance-eskalering enligt B-026 kvarstår; den är inte en genväg till obegränsad routing.

### 6.2 Beställning och validering

`CompanyQuestion` binder id, textreferens, beställaridentitet, valt team,
period/datum, miljö/dataset, mått-id/definitionsversioner, tillåtna
källhandtag, önskat svarsslag, kostnads-/steggränser och policyversion.
Betrodd adapter validerar detta och skapar befintligt `RunRequest` med
`task_id`, `target_team`, referenser och enbart skärpande gränser.
Miljöbindning och policyversion kräver en versionssatt kontraktsutökning;
de får inte bara skrivas som obevakade instruktioner i `goal`.
Före OC-5 kan körbilden vara en oföränderlig, hashbunden bild av dagens
effektiva YAML/env-konfiguration, utan hemlighetsvärden och utan styrskrivningar.
OC-3 behöver alltså autentisering och körbindning men inte en färdig styrpanel.
Övergången till PolicyStore ersätter sedan den källan enligt §8.2.

Centralens generella frågor får bara använda granskade `read`/`compute`-
verktyg för det valda teamet. Inget PII-scope tilldelas från frågetexten.
Parameteranalys med `ParameterChangeMandate` startas som eget domänuppdrag,
inte genom att modellen hittar på ett mandat. Skrivande utkast kan införas
senare via dokumentgatewayen med dess befintliga avgränsningar.

Kostnadsbärande klassificering/syntes, om det senare införs, räknas in i
uppdragets budget och kostnad. Ingen fri SQL, fil, shell eller nätverksväg
tillkommer. Källtext är data och kan inte ändra identitet, team eller verktyg.
Teamområden får bara starta sin egen agent även om ett annat team-id skickas
direkt till servern. Byte av team från centralen skapar ny beställning.

### 6.3 Svarskontrakt

`CompanyAnswer` binder fråge-/uppdrags-id, team/agent, run-/rotreferenser,
status (`answered`, `partial`, `unavailable`, `needs_clarification`, `failed`),
kort slutsats, källreferenser, måttobservationer, datum/period, miljö,
antaganden, begränsningar, motstridiga underlag, nästa steg samt kostnad och
täckning enligt §4.3. Körningens `RunStatus` visas separat; ett färdigt
chatsvar betyder inte att en affärshandling utförts.

Ekonomiska tal kommer från godkända observationer/beräkningsresultat, aldrig
språklig huvudräkning i svaret. Saknad konsolideringsgrund ger exempelvis
”ej beräknat; fördelningsmodell och värderingsunderlag saknas”, inte en
gissad orsak till en nedgång. ”Varför ökade agentkostnaden?” kräver jämförbara
perioder och redovisad täckning. Källkonflikter och ofullständig täckning
hindrar ett kategoriskt fullständigt svar. Centralen kan visa ett kort svar;
rapporter återanvänder gemensam dokumentförmåga när den är byggd.

## 7. Autentisering och rättigheter – P–Q

### 7.1 Namngiven lokal operatör

Rekommendationen för första styrleveransen är en lokalt provisionerad
användare `karl`, lösenfras med Argon2id-hash och etablerat autentiseringsbibliotek,
utan självregistrering eller externt konto. Operatören sätter hemligheten
utanför Git; OC-0 skapar inget konto eller lösenord. Återställning sker manuellt
av operatören och ogiltigförklarar gamla sessioner. OIDC/flera användare blir
ett separat införande med verifierad identitetsmappning.

Servern skapar ogenomskinligt sessions-id efter verifierad inloggning och
lagrar identitet, rättigheter, utfärdande-/aktivitetstid och återautentiseringstid.
Sessionen roteras vid inloggning/återautentisering, upphör efter 15 minuters
inaktivitet eller åtta timmar totalt och återkallas serverledes vid utloggning.
Styrning kräver HTTPS även lokalt före lösenordsinmatning, `Secure`, `HttpOnly`
och `SameSite=Strict` för cookie samt sessionbunden CSRF-token. Lokal TLS och
dess certifikathantering måste verifieras i OC-5; ingen nätverksexponering
eller extern identitetstjänst införs genom förslaget.

Inloggningsförsök begränsas per konto och klient, med generell feltext och
sanerad logg. Föreslagen startnivå är högst fem misslyckanden på fem minuter,
därefter fem minuters väntan; gränserna provas med operatörens återställningsväg.
Lösenord, sessions-id, CSRF-token och nyckelvärden hamnar aldrig i analyslogg.

Tidsvärdena är projektets föreslagna sandboxval. Serverstyrda sessionstider
och säker cookiehantering följer principerna i
[OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
Autentisering och känsliga ändringar stöds av
[OWASP Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).

### 7.2 Kontroll per handling

| Handling | Betrodd kontroll |
|---|---|
| Läsöversikt OC-1/2 | Kan införas i dagens lokala läge med dataminimering och Host-/ursprungsskydd; ger ingen styrbehörighet |
| Starta bolagsfråga | Verifierad operatörssession och CSRF; servern binder beställaren och kontrollerar team, datakällor, effektklasser och budget. Ingen fri aktör från formulär/modell |
| Förhandsgranska/aktivera modell- eller budgetpolicy, även via 3b-9 | Verifierad session och särskild rättighet `policy_admin`; agent/systemidentitet godtas inte som människa |
| Aktivering, återställning och bindande nytt ledningsbeslut | Samma kontroller, CSRF och återautentisering högst fem minuter gammal; beslut binder underlag/version |
| OC-7:s flöden och produktparametrar | B-036 består: befintlig operatörsidentitet, formulärskydd, FlowConsole, hashbundna grindar och domänkö. Flytten blockeras inte av OC-5:s nya autentisering |

`HANDLAGGARE_ID=karl` och `Actor.human("karl")` är inte inloggningsbevis.
Varken GET, chatttext eller ett dolt UI-fält får aktivera policy. Alla
styrskrivningar kräver serverkontroll även vid direkt HTTP-anrop. Formulär
binds till session och exakt tillåtet ursprung; fel Host/Origin eller CSRF
nekas. `SameSite` ersätter inte CSRF-skydd enligt
[OWASP CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

Rättigheten `policy_admin` ger inte nya poddar, PII-resurser, databasroller,
försäkringsbehörigheter eller externa godkännanden. Läsbar överblick kan
levereras före autentisering; nya styrskrivningar hålls stängda tills §7/8
är verifierade. Det ändrar inte B-036:s uttryckliga undantag för flödesstegen.

## 8. En auktoritativ modell-/budgetpolicy – R–W

### 8.1 Lagring och ansvar

Rekommendationen är ett `PolicyStore` hos harness med versionssatta,
oföränderliga policydokument och en aktiv pekare per miljö. Varaktig lagring
föreslås i Lakebase under harnessens ansvar, skild från försäkringsoperationer.
Policyversion, aktiv pekare och lyckad aktiveringslogg måste kunna skrivas
i samma transaktion. Inga tabeller eller databasroller skapas i OC-0;
schema dokumenteras före senare migration och AGENTS.md §4.5 gäller.

OC-5 och **3b-9 är två vyer av samma läs-/förhandsgransknings-/aktiveringskontrakt**.
3b-9 äger körgränsernas validering och effektiva arv, AI-lagret modellupplösning,
och OC-5 den samlade operatörsupplevelsen. Ingen egen budgetfil eller andra
skrivväg skapas för någon vy. CLI/Cowork kan senare använda samma betrodda
adapter med motsvarande autentisering, inte kringgå den med fri filskrivning.

Policydokumentet binder `schema_version`, `policy_version`, innehållshash,
miljö, basversion, skapare/tid/skäl/beslutsreferens, global leverantörspolicy,
rollkedjor, explicita teamundantag och körgränser på global/team/agent/rotnivå.
Det refererar också till granskad befogenhetskonfiguration, modellkatalog,
förmågeunderlag och prisversion genom hash/version. Saknad referens stoppar
valideringen. Första versionen importeras från dagens granskade konfiguration;
startgränserna i harness §6.3 ändras inte genom detta förslag.

### 8.2 Källa per inställning och övergång från YAML/env

| Inställning | Före införande, dagens källa | Föreslagen källa efter kontrollerad övergång |
|---|---|---|
| Team, lead, poddar, nekanden, effekter, mandat och datarättigheter | `ecosystem.yaml`, tjänstelagrets register och respektive gateway | Oförändrat granskad Git-konfiguration; får inte vidgas från styrvyn |
| Modellkatalog, adapter, förmågor och priser | `ai_config.yaml` | Granskad versionsbunden katalog från samma fil; aktiv policy refererar till en oföränderlig katalogbild |
| Vald global modellpolicy, rollkedjor och teamundantag | Rollval i YAML och möjliga `AI_ROLE_*`-överstyrningar | Endast aktiv policyversion i `PolicyStore` |
| Operativa körgränser globalt/team/agent/rot | `ecosystem.yaml` och skärpande uppdrag | Endast policyversionens gränser, därefter skärpande uppdrag och återstående rotbudget |
| Periodbudget och reservationer, när byggt | Ingen verkställd periodbudget | Policyversion anger periodregler; en gemensam budgetbok äger förbrukning/reservationer |
| API-nycklar, anslutningar och lokala inloggningshemligheter | `.env`/skyddad driftmiljö | Fortsatt utanför Git och policyinnehåll; endast namn på tillåtna hemlighetsreferenser |

Övergången är ett separat verifierat införandesteg: importera dagens effektiva
värden, visa diff, bind katalog-/befogenhetsversion, aktivera hanterat läge och
ta bort migrerade operativa fält ur den aktiva YAML-läsningen. Samma inställning
får inte fortsätta ha en redigerbar default som kan vinna i bakgrunden.
Granskade säkerhetsgränser ligger utanför operatörens driftval och visas som
sådana; nya tillåtna poddar/modeller/förmågor kräver separat kod-/konfigurationsgranskning.

I hanterat läge nekas `AI_ROLE_*` och alternativa `AI_CONFIG_FILE` som kan
ändra aktiv upplösning. Katalogladdning sker från den bundna versionen,
utan ett andra env-resolve-steg. Övriga körvägar som är tillgängliga från
plattformen måste använda samma policyadapter, även explicita modellreferenser.
Isolerade utvecklings-/testkörningar får ha eget läge, tydligt märkt och skilt
från hanterad verksamhet. Före övergången är YAML/env fortsatt dagens källa;
detta dokument inför ingen överlagring i befintlig kod.

Om aktiv policy eller katalog inte kan verifieras nekas nya rotuppdrag.
Ingen tyst återgång till YAML/env får öppna ett annat leverantörsval eller tak.

### 8.3 Modeller, undantag och reservpolicy

`mixed` använder granskade rollkedjor; `prefer_openai`/`prefer_anthropic`
väljer godkända primärer hos vald leverantör. Reserv hos den andra leverantören
kräver ett separat uttryckligt val. `only_openai`/`only_anthropic` begränsar
hela kedjan, inklusive explicit modellreferens, omförsök och reserv.
Standard vid exklusivt byte är ingen reserv hos annan leverantör.

Teamundantag kräver namngivet team, skäl och synlig roll-/reservmappning.
De får ändra rollkedja inom globalt tillåten leverantörsmängd och granskad
katalog, aldrig kringgå ett exklusivt globalt val. Ett gammalt oförenligt
undantag måste ändras eller tas bort före aktivering. Inget dolt undantag
är standard. Förmågekontroller gäller verktyg, strukturerade svar och
resultatscheman; inkompatibel kedja avvisas. Saknad nyckel ger förklarat
fel, aldrig en otillåten leverantör som reserv.

Detta preciserar B-025:s ursprungliga korsleverantörsreserv för framtida
operatörsval. Ändringen behöver godkännas; dagens reservkedja ändras inte nu.
Prisjämförelse är en uppskattning på jämförbar historisk användning med
prisversion, inte ett löfte om kvalitet eller faktisk framtida kostnad.

### 8.4 Förhandsgranskning, aktivering och ändringslogg

1. Autentiserad Karl skapar ett utkast mot `expected_active_version` för en
   uttryckligt vald miljö. Okända fält, fel arv, otillåtna katalogreferenser
   eller försök att ändra befogenheter avvisas.
2. Servern producerar `preview_id`, full innehållshash, bas-/katalog-/
   befogenhetsversion, effektiva gränser och modeller per team/agent, reserv,
   undantag, nyckeltillgänglighet utan värden och prisjämförelsens begränsningar.
   Ange att endast nya rötter påverkas och visa väntande gamla rötter.
3. Förhandsgranskningen binds till session, miljö och exakt innehåll, är giltig
   i tio minuter och kräver ny granskning efter ändring eller versionsbyte.
4. Aktivering kräver `policy_admin`, CSRF, nylig återautentisering, skäl,
   engångs-/idempotensnyckel och oförändrad bas. Samma begäran ger samma kvitto;
   samma nyckel med annat innehåll nekas.
5. Policyversion, pekarbyte och revisionspost skrivs atomiskt. Två samtidiga
   aktiveringar mot samma bas kan inte båda vinna. Förloraren får konflikt
   och måste förhandsgranska mot den nya versionen. Loggfel rullar tillbaka
   aktiveringen. Avvisade försök loggas separat med sanerad orsak.

`PolicyActivation` sparar aktör, UTC-tid, miljö, skäl/beslut, gammal/ny version,
hashar, previewreferens, begärans-id och utfall. Lyckat kvitto innebär att
pekaren är ändrad; det innebär inte att pågående körningar bytt policy.
Driftläget visar både aktiv version och vilka versioner körningar använder.
Återställning kopierar tidigare granskat innehåll till ny policyversion och
ny aktivering efter aktuell validering; historiken skrivs aldrig över.

### 8.5 Bindning till rot, barn och fortsättningar

Vid ny rot binds policy-, katalog-, pris- och befogenhetsreferenser atomiskt
till uppdragets körbild. Barn och länkade fortsättningar använder samma
modell-/budgetversion och kvarvarande rotbudget. De läser inte den senaste
globala driftpolicyn som om de vore nya rötter. Förbrukningen nollställs inte.
Vanlig aktivering eller återställning ändrar därför inte en väntande rots villkor.

Detta fryser inte datarättigheter, produktregelstatus eller godkännanden:
befintlig kontroll görs vid varje handling, och ett nytt säkerhetsnekande
vinner. Om en bunden version inte kan laddas eller blivit otillåten stoppas
körningen för mänsklig hantering. Nytt mandat krävs för byte/höjning; en
fortsättning får aldrig användas för att kringgå tak eller leverantörsval.

### 8.6 Körbudget kontra periodbudget – koppling till 3b-9

3b-9 validerar samma `max_steps`, `max_tool_calls`, `max_cost_usd`,
`max_output_tokens`, `max_context_bytes`, `max_wall_seconds` och kommande
delegeringstak som harness. Effektivt tak är minimum av globalt, team, agent,
uppdrag och återstående rotutrymme. Uppdrag/modell får bara sänka. Gränser
måste vara positiva och respektera arv; inaktivering av nya uppdrag är ett
uttryckligt tillstånd, inte budget 0 med oklar betydelse.

Dagens loop summerar svarskostnad efter anrop och stoppar vid okänd kostnad
eller passerat tak. Den ger inte ett exakt hårt kostnadstak eller en delad
samtidig reservationsbok. 3b-9:s vy får inte påstå att dessa skydd redan finns.
Aktiv tid och simulerad affärstid hålls isär; godkännandeväntan är ingen ny budget.

Föreslagen senare periodbudget är per team/miljö och verklig kalendermånad
i UTC, med beslutad USD-gräns. Den är **inte aktiverad som standard**.
Före admission av modellförsök reserverar samma budgetbok utrymme för rot
och teamperiod atomiskt, inklusive konservativ reserv-/omförsökskedja.
Försökens faktiska tid avgör period; fortsättning i ny månad behåller
rotversion och rotförbrukning men måste också få plats i den nya periodens
aktuellt beslutade teamgräns. Periodregler är admissionvillkor för perioden,
inte en ändring av rotens modell-/körpolicy.

Boken har stabil reservationsidentitet, policy-/periodreferens, känd förbrukning,
öppna reservationer och avstämningsstatus. Reservation för okänd debitering
behålls tills avstämning styrker utfall; krasch får inte frigöra den automatiskt.
Ingen dubbel bok för OC-2, OC-5 och 3b-9. Lägre ny periodgräns än redan bunden
förbrukning stoppar nya reservationer och visar övertrassering; den skriver
inte om historik eller lovar att avbryta redan skickade anrop. Exakt monetärt
hårdtak kräver dessutom verifierad försökskontroll inne i AI-lagret. Fram
till dess visas uppskattad förbrukning och kontrollens faktiska begränsning.

## 9. Införande, acceptans och beslutsspår – X

### 9.1 Beroendegrindar

| Byggsteg | Vad måste finnas innan funktionen öppnas? |
|---|---|
| OC-1 + smal OC-2 | Godkända måttdefinitioner, granskade läsadaptrar, miljöbindning, täckningsbesked och idempotent import; inga påhittade ekonomiska värden |
| OC-3 | Operatörssession enligt §7, verifierad målprofil och rätt analysverktyg, betrodd beställning och budget. Ett team åt gången; 3c-1 före automatisk samordning |
| OC-4 | Godkända triggers och underlagskontrakt, ägare och beslutsspår. Bindande nya ledningsbeslut kräver §7:s identitetskontroll |
| OC-5 + 3b-9 | Gemensamt PolicyStore, autentisering, katalog-/konfigurationsmigrering, förhandsgranskning, atomisk logg/aktivering och verifierad rotbindning |
| Periodbudget | En gemensam varaktig reservationsbok och verifierad samtidighet/avstämning. Skild från att inställningsvyn 3b-9 finns |
| OC-6 | Verifierade kapital-/ekonomi-/aktuariella grunder från projekt 2/5/6 |
| OC-7/8 | Befintliga FlowConsole- och teamgränser återanvänds; flödeskoppling verifieras enligt 3c-V. Kräver inte OC-5:s styrinloggning enligt B-036 |

Godkänd design innebär inte godkänd databasändring, driftsättning eller merge.
Byggpaket måste fortfarande avgränsas och samordnas enligt AGENTS.md.

### 9.2 Kontraktsprov inför respektive byggleverans

Följande är acceptansfall för senare implementation, inte tester som redan körts:

| Prov | Förväntat resultat |
|---|---|
| Saknad FTA/konsolidering; tomt underlag; verifierat nollvärde | Tre skilda besked. Ingen gissad kvot eller grön status för luckan |
| Utfall och scenario, demo och Lakebase, datumvärde och periodflöde | Kan visas sida vid sida med tydlig märkning, får inte summeras ihop |
| Historisk beståndsfråga utan ögonblicksbild; `paid` utan betaldatum | Saknat/underkänt underlag, ingen bakdatering eller tyst bortfiltrering |
| Liten cell och total minus stor cell | Ingen personhärledning; undertryck även kompletterande cell eller neka |
| Reservfel, fortsättning, barn, upprepad import och okänd kostnad | §4.3:s syntetiska facit håller; ingen addition av ackumulerade körresultat |
| Två identiska AI-rader som är olika försök; flyttad/kopierad logg | Verkliga försök bevaras; säker ursprungskoppling krävs före import av överlapp |
| Obyggt team, flerteamsfråga, manipulerat team-id, PII i frågetext | Ingen låtsaskörning, ingen dold delegering och inga utökade resurser |
| ”Varför ökade agentkostnaden?” med olika täckning; fråga om konsolideringsfall | Partiellt/källbundet svar respektive tydligt saknad beräkningsgrund |
| Rutinärende kontra tre olika felande rotuppdrag | Ärendet stannar i specialistytan; systematiskt hinder blir en aggregerad fråga |
| Nytt underlag efter ledningsbeslut; kvitterat men olöst problem | Kräver nytt ställningstagande respektive fortsatt öppen uppföljning |
| Förfalskat Actor/id, saknad/utgången session, CSRF eller fel Origin | Ingen styrskrivning, även vid direkt serveranrop |
| Exklusiv leverantör med motstridigt teamundantag/env/explicit modell | Aktivering/anrop nekas före leverantörskontakt; ingen dold korsreserv |
| Två samtidiga aktiveringar, ändrat utkast, utgången preview, loggfel | En vinnare, övriga konflikt/ny granskning; loggfel lämnar aktiv pekare orörd |
| Återställning och redan pågående rot med barn/fortsättning | Ny aktiveringshistorik; gammal rot behåller modell-/budgetversion och förbrukning |
| PolicyStore otillgängligt eller fel kataloghash | Nya rötter nekas; ingen dold YAML/env-reserv |
| Två samtidiga budgetreservationer, okänd debitering och månadsskifte | Gemensamt utrymme överskrids inte genom dubbel admission; okänt utrymme hålls kvar; rotbudget består |
| Flytt av flödesvy till centralen | FlowConsole, grindhash och tjänstelagerkö består; inget nytt krav på OC-5-inloggning för flödesstegen |

Prov byggs först lokalt med syntetiska fixtures/FakeProvider och oberoende
förväntade belopp. Databastransaktioner och verklig integration verifieras
separat när respektive byggpaket är beställt; inget produktionsskript körs nu.

### 9.3 Godkännande och dokumentuppdatering

Karl godkände rekommendationerna 2026-10-26 med ”jag tycker dina
rekommendationer verkar bra. kör på denna planen”. B-038 dokumenterar
godkännandet utan avvikelser. Beslutets innebörd:

> Operatören godkänner OC-0:s rekommendationer A–X enligt dokumentets version
> 0.1 utan avvikelser eller uppskjutna val. Operatörscentralen använder
> gemensamma mått- och händelsekontrakt, aggregerade ledningseskaleringar och
> avgränsad routing via befintliga teamledare. OC-5 och 3b-9 använder samma
> versionssatta policyregister, med autentiserad, förhandsgranskad aktivering
> för nya rötter. Befintliga domängodkännanden, team- och datagränser består.
> Ingen kod, migration, extern tjänst eller runtimepolicy aktiveras genom
> designbeslutet. Periodbudget och flerteamrouting kräver sina verifierade beroenden.

Godkännandet och gränsen mellan beslutad design och befintlig implementation
är införda i BESLUTSLOGG, projektplanen, harness-, AI- och BI-underlagen samt
gemensamma statusdokument. Dagens YAML/env och befintliga körvägar gäller
tills övergången är implementerad och verifierad. OC-0 är klar som design-
och dokumentleverans; OC-1–8 och 3b-9 är fortsatt byggarbete.

## 10. Underlag och avgränsningar

- [MASTER_CONTEXT](../MASTER_CONTEXT.md), [BESLUTSLOGG](../BESLUTSLOGG.md)
  och [ATT_GORA](../ATT_GORA.md), särskilt 3b-9 och OC-0–8.
- [Harness](harness.md) §§3, 6, 8 och 10;
  [agentekosystemet](agentekosystem.md) §§3, 7 och 10.
- [BI-design](../projekt/02_bi_insikter/DASHBOARD_DESIGN.md),
  [projekt 10](../projekt/10_operatörscentral/PROJEKTPLAN.md) och
  [skissen](../projekt/10_operatörscentral/SKISS.md). Skissens värden är syntetiska.
- Kod läst som nulägesbevis: [CallRecord](../src/ai/tracing.py),
  [AI-konfiguration](../src/ai/config.py), [körkontrakt](../src/agents/run.py),
  [journal](../src/agents/journal.py), [loop](../src/agents/loop.py),
  [körpolicy](../src/agents/ecosystem.yaml),
  [premietransaktion](../src/models/premium_transaction.py) och
  [webbidentitet/formulärskydd](../src/web/handler.py).

Externa OWASP-källor i §7 kontrollerades 2026-10-26 för säkerhetsprinciperna.
Trösklar, datakontrakt, lagringsval och exakta sessionstider är projektets egna
beslutsförslag. Inga aktuella modellpriser, nya rättsliga krav eller påståenden
om tillgängliga Databricks-funktioner fastställs här.
