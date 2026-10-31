# Operatörscentral – första läsleveransen OC-1/OC-2

**Datum:** 2026-10-26. **Design:** B-038, [OC-0](operatörscentral_beslutsforslag.md).
**Status:** lokalt byggd och verifierad läsimplementation; inte verifierad mot Lakebase.

## Öppna och använda

Starta befintlig webbserver enligt [handläggar-UI:t](handläggar-ui.md) och öppna
`/central`. Länken **Centralen** finns i huvudmenyn. Fyra vyer delar vald
kalendermånad: överblick, team, agentkostnader och underlag. Vanliga
handläggarsidor ligger kvar på sina adresser. Plattformens startsida och
fullständiga teamområden flyttas i OC-8; flöden/parametrar flyttas i OC-7.

OC-3a har nu avgränsade [fråge- och uppdragsvyer](fragekedja_webb.md) på
`/central/fragor` och `/team/aktuarie`, med gemensam detalj och PDF-granskning.
De ansluts uttryckligen; riktig modell och Lakebase verifieras separat.

Läsvyn anropar inga modeller och innehåller inga styrskrivningar.
Läsning av försäkringsaggregat går genom `get_company_metrics` i tjänstelagret, utan PII
i resultatet. Sedan B-041 (2026-10-27) är operationen `AGENT` och monterad för aktuarieteamet
i fråge-/rapportkedjan, med kolumnbegränsad läsrätt för rollen `agent_aktuarie`; centralens
egen läsning är oförändrad. Kolumnrätterna är satta i Lakebase sedan 2026-10-31.

## Mått och underlag

- `insured_registered_count`: registrerade personer av alla statusar vid
  aktuell läsning. Ingen bakdaterad beståndshistorik.
- `premium_paid_recorded_sek`: signerade `premium`/`adjustment` med `paid_date`
  i vald hel månad och `status=paid`; avgifter exkluderas. Detta är
  betalmarkeringar, inte bankavstämda premier. `paid` utan datum eller med
  framtida betaldatum underkänner kontrollen, även om raden annars skulle
  falla utanför periodfiltret.
- Kapital, FTA, konsolidering och likviditet visas som **ej beräknat**.
  Leveransantal och godkänd kvalitet är **ej uppmätt**; journalens `completed`
  används inte som ersättning för accepterad leverans eller kvalitetskontroll.

SQL-aggregaten hämtas i ett enda SELECT för ett gemensamt databasögonblick.
Personceller med 1–9 individer undertrycks före resultatet lämnar tjänstelagret.
Ingen segmentering eller individuellt datumurval finns; bara aktuell månad
och de elva föregående. Verifierad tom betalpopulation i ett tillräckligt
stort, läsbart bestånd kan ge noll. Saknat/underkänt underlag ger aldrig noll.
Detta är dataminimering och småcellsskydd, inte ett allmänt anonymitetsbevis.

Definitionerna finns i `management.metrics`. Underlagsvyn visar definition,
version, ägare, kontroll, datum, miljö/dataset och observationens hashreferens.
Observationerna skapas vid läsning och arkiveras inte som en historisk serie.
OC-3a bevarar det enskilda uppdragets rapport och underlag via harness.
Generell varaktig observationshistorik återstår i BI-projektet.
Ingen Databricks-dashboard eller Genie-integration driftsätts här.

## Deklarera loggkällor

Utan manifest är kostnad och körläge okända. Standardfilen `ai_calls.jsonl`
antas inte tillhöra den miljö som råkar vara vald i webben.

Operatören anger lokalt `OPERATOR_TELEMETRY_MANIFEST` till en JSON-fil.
Manifestet ska ligga i en separat gitignorerad loggmapp. Sökvägar till
JSONL-källor är relativa till den mappen och får inte lämna den. Manifestet
är driftkonfiguration; det kan inte skickas från webben eller skrivas av modellen.

Exempel på **format**, inte en konfiguration som kopplas in automatiskt:

```json
{
  "schema_version": 1,
  "sources": [
    {
      "source_id": "ai-original-01",
      "path": "ai_calls.jsonl",
      "kind": "calls",
      "environment_id": "demo",
      "dataset_ref": "demo:current"
    },
    {
      "source_id": "journal-original-01",
      "path": "agent_runs/run-example.jsonl",
      "kind": "journal",
      "environment_id": "demo",
      "dataset_ref": "demo:current"
    },
    {
      "source_id": "older-unallocated-01",
      "path": "older_calls.jsonl",
      "kind": "calls"
    }
  ]
}
```

Miljö och dataset får bara deklareras när ursprunget kan styrkas. Äldre
blandade filer måste delas/avstämmas med bevarad källidentitet innan de kan
miljöbindas; att filen finns i en worktree är inte tillräckligt bevis.
Utan deklarerad miljö visas posterna separat som **oallokerat underlag**.
Andra miljöers poster ingår inte i vald miljös siffror.

`OPERATOR_DATASET_ID` kan ange en egen stabil datasetreferens. Standard är
`demo:current`, `svc_test:current` respektive `lakebase:current`. Efter
återställning eller byte till ett separat scenario ska en ny uttrycklig
datasetreferens anges och loggmanifestets bindning avstämmas. Webben gör ingen
automatisk identifiering av en återställd databas och påstår ingen sådan historik.

## Lokal import, dubbletter och fel

Importen bygger ett härlett SQLite-index `operator_index.db` bredvid
manifestet. Det är ingen andra affärslogg eller budgetbok. Den sparar bara
validerade metadata; promptinnehåll, modell-/ärendesammanfattningar,
feltexter, nycklar och rå uppdragstext tas inte med. Uppdrag får en stabil
hashreferens. Modellnamn visas bara om de finns i aktuell granskad katalog.

Äldre AI-rader identifieras med `source_id` och byteposition, nya rader med
`attempt_id` när det finns. Journaler använder ursprungligt event-id och
kontrollerad sekvens. Samma original som kopieras/flyttas behåller samma
`source_id` och bytepositioner; kopian får inte deklareras som nytt ursprung.
Rotations-/delningsverktyg med ändrade positioner kräver ett separat
positionsmappningskontrakt och stöds inte av denna första import.

En vanlig återimport ger samma summa. Två identiska verkliga rader på olika
positioner räknas separat. Samma identitet med ändrat innehåll eller ändrad
miljö/dataset sätts i beständig karantän och utesluts från summeringen tills
operatören stämt av originalen. Indexet skriver aldrig om originalfilerna.
Ett index kan återskapas från avstämda original och deras manifest; gör inte
det för att kringgå en olöst källkonflikt.

Saknad fil, trasig rad, sekvenslucka och okänd schemaversion visas som
täckningsproblem. Tidigare verifierade indexposter kan fortsatt visas som
**känd del**. Senaste lyckade källkontroll lagras; underlag äldre än 15 minuter
utan lyckad kontroll märks inaktuellt. Ett tyst men framgångsrikt kontrollerat
original är färskt även utan nya händelser. Gränser: 20 källdeklarationer,
16 MiB per fil, 64 MiB per läsning och 1 MiB per rad.

## Kostnadens betydelse

Summeringen utgår enbart från unika synliga anropsförsök. Fel/reservförsök
med känd kostnad ingår. Nullkostnad räknas separat som okänd möjlig
debitering, även för en överhoppad modell om utebliven debitering inte kan
styrkas. `RunResult`, `usage` och `root_usage` adderas aldrig till försöken.
En journal knyter `run_id` till ett hashat uppdrag och en körstatus, inte
till ytterligare kostnadsrader.

Belopp är kända prisuppskattningar i USD, inte en komplett kostnad eller
avstämd faktura. Dagens logg bevisar inte full täckning av SDK-omförsök eller
historisk prisversion. Därför kan första leveransen aldrig visa komplett
täckning eller säker återstående budget. Ingen SEK-konvertering görs.

## Verifiering och kvarstående steg

Lokala tester täcker signerade rättelser/avgiftsundantag, noll kontra saknat,
småceller, felaktigt betaldatum, avvisad agentåtkomst, återimport, kopierade
original, identiska verkliga försök, källkonflikt, miljöisolering, okänd
kostnad, journalens ackumulerade belopp och sanering. HTTP-proven täcker
de fyra vyerna, avvisade perioder, uteblivna styrskrivningar och databasfel.

Leveranskontroll 2026-10-26: bred lokal regression mot den integrerade grunden
gav 1 106 godkända, 22 överhoppade och 36 bortvalda tester (inga Postgres-/liveprov).
Därefter passerade 105 berörda regressionsprov och, efter sista måttändringen,
23 riktade prov för ledningsfunktion, HTTP och designvärden. Ruff och diffkontroll
är godkända. De fyra vyerna, navigationen och utfällbart måttunderlag granskades
i webbläsaren vid 499 px bredd. Kostnadstabellen med fixtureunderlag verifierades
via HTTP-test; ingen syntetisk kostnadskälla kopplades in i den vanliga läsvyn.
Inför integrationen med compliance-rollens uppdaterade main passerade
1 110 lokala tester; 42 överhoppades och 36 valdes bort. Inga databas-/liveprov kördes.

Verifiering mot Lakebase, gemensam loggdrift/rotation, komplett försöks- och
prisversionering, historiska mått, leverans-/kvalitetsproducenter och
fullständig OC-2-avstämning återstår. OC-3–8 och 3b-9 är separata byggpaket.
MASTER_CONTEXT och ATT_GORA har uppdaterats vid samordnad integration efter
att compliance-rollens 3c-V-ändringar hämtats in. Ingen sådan databasändring
utförs av operatörscentralen.
