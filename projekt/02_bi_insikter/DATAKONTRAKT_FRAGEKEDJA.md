# Datakontrakt: första beståndsfrågan till rapport

> **Kontrakt:** P2-FRAGA-001, version 1.0, 2026-10-27.
> **Status:** dokument- och lokalt testunderlag till Claudes designstopp för
> projekt 10/2. Ingen ny webb-/agentfunktion eller Lakebase-verifiering.
> **Grund:** B-029 (gemensamma mått), B-038 (OC-0, källbundna observationer),
> B-040 (testurval), operatörens uppdrag och åtkomstbesked 2026-10-27.
> **Kodbas för kontrollen:** `origin/main` vid `5afffef`.

## 1. Dataväg, ansvar och avgränsning

Första datavägen är **Lakebase → gemensamt tjänstelager →
`get_company_metrics` → måttobservationer → rapportunderlag**. Operationen i
[`src/services/operations/management.py`](../../src/services/operations/management.py)
gör aggregaten i betrodd kod. Definitionerna i
[`src/management/metrics.py`](../../src/management/metrics.py) är samma som
operatörscentralen använder; ingen separat SQL- eller måttimplementation ska
byggas i agenten eller rapportgeneratorn.

**Lakebase, Databricks AI/BI och Genie har skilda integrationsstatusar.**
B-029:s dashboard och Genie kommer i en senare avgränsning. Detta kontrakt
förutsätter varken SQL Warehouse, Unity Catalog, metric views eller Genie.
Inget nytt BI-lager väljs. Lokal demo verifierar definitionerna med syntetiska
data; den ersätter aldrig tyst en misslyckad Lakebase-läsning.

Projekt 2 förvaltar måttkontraktet tillsammans med domänägaren `forsakring`.
Aktuarieteamet analyserar underlaget; projekt 10 binder uppdrag, identitet,
miljö, period och återfinnbar leverans. Kommunikation äger mallen och
utveckling genereringen. Se [projekt 10:s byggavgränsning](../10_operatörscentral/PROJEKTPLAN.md).

**Operatörens besked 2026-10-27:** operationen är inte känslig (`pii=False`),
ger endast aggregat med småcellsskydd och ska bli `AGENT`-läsning för
aktuarieteamet. Basversionens `HUMAN_ONLY` är ett befintligt konfigurationsläge,
inte ett krav i detta kontrakt. Claude ändrar tjänstelager, åtkomstregister,
körpolicy och tillhörande åtkomstprov i sitt designstopp. Här verifieras
databeteendet genom mänsklig tjänsteaktör, utan att föregripa agentmonteringen.
Ingen allmän SQL-åtkomst, personlista eller segmentering följer av beskedet.

Kapitalförvaltning, FTA, ekonomisk avstämning, historiska beståndsserier,
tidsjämförelser och presentationsgenerering ingår inte i första datakontraktet.
Operatörsinloggning, uppdragsvy och aktuariens teamyta byggs efter godkänt
designstopp; dokumentet aktiverar dem inte.

## 2. Måttdefinitioner, version 1.0

Båda definitionerna har `schema_version=1`, `definition_version="1.0"`,
`owner_team="forsakring"`, `review_ref="B-038 / OC-0 §3.3"`, inga dimensioner
och deklarerad aktualitetsgräns `freshness_seconds=86400`. Kontraktsversionen
ovan och måttens definitionsversioner är separata. Ändrad måttbetydelse kräver
en granskad definitionsversion och samordning mellan central, teamyta och rapport.

| Egenskap | `insured_registered_count` | `premium_paid_recorded_sek` |
|---|---|---|
| Namn/enhet | Registrerade försäkrade, personer (heltal) | Registrerat betalda premier, SEK (`Decimal`, två decimaler i visningen) |
| Population | Alla rader i `insured_persons` i vald datakälla, unika genom primärnyckeln | Transaktionsrader i `premium_transactions` med koppling via `policy_benefits` och `policies` till försäkrad |
| Inkludering | Alla registrerade statusar, även avslutade och pensionerade; person utan försäkring räknas också | Endast `status=paid` och `transaction_type` i `premium`, `adjustment`; belopp summeras med sina positiva/negativa tecken |
| Exkludering | Ingen filtrering på aktiv anställning, premiebetalande försäkring, ålder eller historisk giltighet | `fee` och alla andra typer/statusar; poster med betaldatum utanför perioden |
| Tidsgrund | `as_of`: registrerat bestånd vid läsningen, med `as_of_date` | `period`: betaldatum `>= period_from` och `< period_to` |
| Periodens betydelse | Den valda premiemånaden ändrar inte beståndspopulationen | Hel kalendermånad efter `paid_date`, **inte** `period_month` (intjänande-/premiemånad) |
| Källa | Försäkringstjänsten · `insured_persons` | Försäkringstjänsten · `premium_transactions` |
| Kvalitet i centralens observation | `verified` för det kontrollerade registrerade antalet vid lyckad läsning, även om det undertrycks | `provisional` vid `available`/`suppressed`; `failed` vid underkänt betaldatum |

**Registrerat bestånd vid läsdatum är inte månadsslutsbestånd.** Inga
historiska personögonblicksbilder läses. Ett septemberval med läsdatum i
oktober visar oktoberläsningens personantal, inte personantalet den 30 september.

**Betalmarkerat är inte bankavstämt.** "Signerade" belopp betyder här att
rättelsernas plus-/minustecken bevaras, inte att posterna är digitalt signerade
eller bankverifierade. Varje kvalificerande transaktionsrad räknas en gång;
originalpremie och rättelse är separata rader. Operationen granskar inte
bankkvitton, rättelsekedjors fullständighet, saknade fakturor/premier eller
förväntat betalningsbehov. Det finns inget ytterligare produkt-, förmånstyps-
eller arbetsgivarfilter i operationen; vald datakälla måste vara rätt bestånd.

`read_at` sätts som tidszonsmedveten UTC-tid efter SQL-läsningen.
`as_of_date` kommer från tjänstens `common.today()` (dagens datum i normal drift).
Alla fyra SQL-aggregat hämtas i **ett SELECT**, alltså samma läsögonblick:
personantal, periodsumma, antal unika betalberörda personer och antal ogiltiga
betalmarkeringar. Det är inte en sparad databasögonblicksbild med återläsnings-id.
`data_through` sätts i centralens observationshjälpare till `read_at`; det
bevisar lästid, inte senaste bankavstämning eller att inläsningen är komplett.

## 3. Operationsgränser och svar utanför dem

Indata är enbart `month`, ett giltigt datum på första dagen i månaden
(exempel `{"month": "2026-09-01"}`). Extra fält avvisas (`extra="forbid"`).
Det finns inga person-/arbetsgivarfilter, fria från-/tilldatum eller val av
historiskt beståndsdatum.

Operationen tillåter **aktuell månad och elva föregående**, inklusive båda
ändpunkterna. Vid läsdatum **2026-10-27** är intervallet **2025-11–2026-10**.
Utdata använder halvöppen period, exempelvis `[2026-09-01, 2026-10-01)`.
December slutar den 1 januari följande år.

Den första rapportkedjan ska enligt projekt 10 välja en **avslutad** månad.
Vid samma läsdatum blir dess tillåtna val därför **2025-11–2026-09**. Att
operationen tekniskt tillåter oktober gör inte oktober avslutad. Den kommande
betrodda uppdragsvägen måste kontrollera detta; kontrollen byggs inte här.

En fråga utanför fönstret besvaras exempelvis: "Underlaget stöder aktuell
månad och elva föregående. För denna rapport kan en avslutad månad
2025-11–2026-09 väljas. Den efterfrågade perioden kan inte besvaras med detta
underlag." `InvalidInputError` ger inget måttvärde. Frågan får inte tyst
kortas, flyttas till en annan månad, få noll eller besvaras med demo/BI/Genie.
En fråga om historiskt månadsslutsbestånd eller bankavstämt inflöde kräver
annat underlag även om månaden ligger inom fönstret.

## 4. Småcellsskydd och tillstånd

Småcellsgränsen är **10 unika personer**. Varken dolda värden eller exakta
småcellspopulationer ska återges eller räknas fram ur andra uppgifter i rapporten.

| Fall vid lyckad läsning | Rått operationsresultat | Observation enligt centralens befintliga mappning |
|---|---|---|
| Bestånd 0 eller minst 10 | `insured_count=antal`, `insured_suppressed=False` | `availability=available`, `quality=verified` |
| Bestånd 1–9 | `insured_count=null`, `insured_suppressed=True` | `availability=suppressed`, `value=null`, `quality=verified` |
| Giltiga betaldata, bestånd ej undertryckt, 0 eller minst 10 betalberörda | `paid_state=available`, `paid_sek=summa` | `availability=available`, `quality=provisional` |
| Bestånd 1–9 **eller** 1–9 unika betalberörda | `paid_state=suppressed`, `paid_sek=null` | `availability=suppressed`, `quality=provisional` |
| Minst en `paid`-rad av typ `premium`/`adjustment` utan betaldatum eller med betaldatum efter läsdagen | `paid_state=failed`, `paid_sek=null` | `availability=missing`, `quality=failed` |

Kontrollen av ogiltigt betaldatum gäller **hela datakällan**, även utanför
vald period. Den gäller inte avgifter eller andra betalstatusar. `failed`
har företräde framför `suppressed` för premiemåttet. Personantalet kan vara
tillgängligt även när premiemåttet fallerar. Antalet betalberörda är unika
personer, inte antal transaktioner, försäkringar eller förmåner.

En framgångsrik läsning med tom betalpopulation och bestånd på minst 10 ger
`available` och **0,00 SEK**. Det säger bara att inga kvalificerande rader
fanns, inte att alla premier har kommit in. Ett tomt bestånd ger också
tillgängliga nollor. Ett litet bestånd undertrycker även en tom betalcell.
Nettosumma noll från minst tio betalberörda är också ett talvärde, inte saknat.

**Misslyckad läsning är ett separat fall:** operationen kastar fel och lämnar
inget `CompanyMetrics`-resultat. Centralen visar båda måtten som
`availability=missing`, `quality=unknown`, `value=null`, utan källbevis för
lyckad läsning. Rapporten måste ange läsfel med sanerat skäl. `failed` är
alltså rå premiestatus/kvalitet, inte ett nytt värde i observationens
`availability`-enum. Saknat eller underkänt underlag blir aldrig noll.

## 5. Lokalt facit och avvikelseprov

Facit gäller ny **SQLite i minnet**, byggd av
[`create_demo_database`](../../src/utils/demo_data.py) med
`with_older_cohort=True`, `with_proposals=False`, tjänstens läsdatum låst till
**2026-10-27**. Detta är inte den genererade Lakebase-populationen eller en
eventuellt manuellt ändrad lokal demofil.

Demobeståndet har fyra grundpersoner och 31 personer i den äldre kohorten:
**35 registrerade**, inklusive avslutad/pensionerad status. Premiefacit har
kontrollräknats separat ur fixturelöner, 2025 års löneskalning `1/1,025`,
IBB 80 600/83 400, satser 4,5 %/30 %, brytpunkt 7,5 IBB/12 och
25–66-årsfönstret. Låg/hög premiedel avrundas var för sig till öre.
Testerna använder fasta belopp, inte en ny summering med operationens filter.

| Period | Bestånd vid läsning | Betalberörda (endast stort lokalt facit) | Premiemått | Tillstånd |
|---|---:|---:|---:|---|
| 2025-11 | 35 | 31 | 145 971,41 SEK | `available` |
| 2025-12 | 35 | 31 | 145 971,41 SEK | `available` |
| 2026-08 | 35 | 26 | 124 541,34 SEK | `available` |
| 2026-09 | 35 | 0 | 0,00 SEK | `available`; fakturerade rader är inte betalmarkerade |

[`tests/test_management.py`](../../tests/test_management.py) täcker dessutom:

- Kontrollerat separat testbestånd: 10 personer och 10 betalberörda ger
  **10 850,00 SEK** = 10 000 + 9 × 100 − 50. Avgiften −200 exkluderas.
- Betaldatum på första/sista dagen ingår; nästa månads första dag exkluderas.
  Premiemånad i annan månad påverkar inte urvalet, `invoiced` exkluderas.
  Med testtilläggen +25 och −10 blir facit **10 865,00 SEK**.
- Bestånd på 1 respektive 9 döljer personantal och betalcell; 9 betalberörda
  döljer belopp trots minst 10 transaktionsrader och totalt 10 personer.
- Tom betalpopulation i läsbart stort bestånd ger noll; undertryckt cell
  och `missing`-observation ger `null`.
- `premium` och `adjustment` med saknat eller framtida betaldatum ger
  `failed` även i en annan, annars tom period. Beståndsmåttet är opåverkat.
- Fönstrets ändpunkter tillåts; för gammal/framtida månad, annan dag än
  månadens första, ogiltigt datum och extra personfilter avvisas.
- Misslyckad tjänsteläsning lämnar inget nollresultat. Befintligt prov i
  [`tests/test_web_operator.py`](../../tests/test_web_operator.py) kontrollerar
  sanering och att centralen inte byter datakälla vid läsfel.
- Måttversion 1.0 och observationsskillnaden mellan tillgänglig nolla,
  undertryckt, underkänd och okänd källa.

Lokala prov bevisar inte Postgres-beteende, agentåtkomst eller faktisk
Lakebase-datakvalitet. Testurval och körresultat redovisas i leveransrapporten.

## 6. Underlag som rapportgenereringen måste bevara och visa

Följande är rapportkrav för det kommande bygget, **inte nya fält som redan
returneras av operationen**. Betrodd kod binder metadata; modellen får inte
välja miljöidentitet, fabricera källbevis eller höja kvalitetsstatus.

| Del | Fält och innehåll som rapporten ska visa/bevara |
|---|---|
| Identitet | Rapport-/utkastreferens och version, uppdragsreferens, `run_id`, ansvarigt team, skapandetid, granskningsstatus och mänsklig granskning med datum/referens när den gjorts |
| Kontrakt och definition | `contract_id=P2-FRAGA-001`, kontraktsversion, `metric_id`, `schema_version`, `definition_version`, namn, full betydelse, enhet, population, inkluderat/exkluderat, ägare och `review_ref` |
| Tid | `read_at`/`computed_at` med tidszon, `as_of_date` för beståndet, `period_from`/`period_to` (slutet exklusivt) för premier, `data_through` och dess begränsning; vald period ska vara avslutad |
| Datakälla | Betrott `environment_id` och `dataset_ref`, läsvägens namn `get_company_metrics`, källtabeller/definitionens `source`, kodrevision och identifierbar data-/snapshotreferens när sådan finns |
| Källbevis | `observation_id`, `evidence_refs`, samt bevarat sanerat aggregatresultat och definitioner bundna till rapporten. Centralens nuvarande referens är `service:get_company_metrics:<read_at i ISO-format>` |
| Resultat | `value`, `availability`, `quality` och begriplig `note` per mått. `null` visas med orsak, aldrig som 0 eller tom ruta; undertryckt belopp ska inte hamna i diagram, export eller bilaga |
| Kontroller | Kontroll av tillåten/avslutad månad, samma läsögonblick, måttversion, miljö/dataset, betaldatum och småcellsgräns 10. Ange kontrollresultat per mått och vad som inte kontrollerats |
| Begränsningar | Ingen historisk månadsslutspopulation, ingen bankavstämning, ingen garanti för fullständig premieinläsning, inga tidsjämförelser eller BI/Genie-resultat; eventuellt läsfel/underkänt underlag och kvarstående granskning |
| Leveransformat | Markdown som arbetsunderlag; A4-export använder gemensam mall/design med versionsreferens. Samma värden, statusar, källor och begränsningar följer med exporten |

Råmappning: `insured_count`/`insured_suppressed` → beståndsobservation;
`paid_sek`/`paid_state` → premieobservation enligt §4; `read_at`, `as_of_date`
och periodgränser följer med utan omdatering. `environment_id` och
`dataset_ref` finns inte i `CompanyMetrics`; de binds utanför operationen.
Centralen använder `WebSettings.database` och `dataset_ref` (lokalt
`OPERATOR_DATASET_ID` eller standard `<miljö>:current`). Referensen är en
etikett, inte ett bevis för en oföränderlig databasversion.

Observationens hash är en innehållsreferens, inte ett arkiv. Rapportkedjan
måste bevara underlaget/definitionerna som faktiskt granskades och länka dem
till rapportversionen; att köra samma fråga senare ger inte samma bestånd.
Sparad observation behöver aktualitetskontroll mot 86 400 sekunder; gränsen
innebär inte att dagens kod automatiskt gör en sparad rapport inaktuell.
En ny läsning ska ge nytt underlag och ny granskningsbar version.
`verified` på antalet betyder kontrollerat registrerat antal, inte att hela
rapporten har accepterats av operatören.

## 7. Inte verifierat och kvarstående setup

**Inga körningar mot Lakebase har gjorts i detta uppdrag**, varken läsning,
seed, migration, rollprov eller Postgres-prov i `svc_test`. Inga externa
konton, resurser eller rättigheter har skapats. De lokala proven ändrar inte
`src/services/`, `src/agents/`, åtkomstregistret eller körpolicyn.

Före aktivering behöver operatören och Claudes bygguppdrag säkra:

1. Rätt Lakebase-anslutning och betrodd miljö-/datasetidentitet, utan hemligheter
   i Git eller rapport. Befintlig anslutning/roll kontrolleras först; konton
   och eventuella nya externa rättigheter sätts upp manuellt av operatören.
2. Claudes `AGENT`-ändring och montering för aktuarieteamet, med tillhörande
   åtkomst-/körpolicyprov. Detta kontrakt verifierar inte databasrollens
   faktiska rättigheter eller hela agentens fråge-/rapportkörning. Samordna då
   även åtkomsttexten i projekt 10:s plan, `02_system/operatörscentral_drift.md`
   och den genererade operationsförteckningen med den nya runtimebehörigheten.
3. Separat samordnad Lakebase-verifiering enligt AGENTS.md §4.5: population,
   belopp, betaldatumsfel och jämförelse med samma underlag i centralen.
   Demofacit får inte förväntas vara Lakebase-värden.
4. Godkänt designstopp, verifierad operatörssession, uppdrags-/teamyta,
   bevarande av granskat underlag och Markdown/A4-leverans enligt projekt 10.
   Rapportgenerering, lagring, återfinnbarhet och mänsklig granskning är inte
   verifierade av dessa måttprov.

**Senare BI/Genie-avgränsning:** verifiera miljöns Unity Catalog,
SQL Warehouse, stödda dashboard-/Genie-funktioner, rättigheter och dataväg
separat enligt B-029. Inget av detta behövs för att köra de lokala proven.
Val av historik/snapshotlagring och bredare BI-/rapportkontrakt återstår;
denna leverans loggar inget nytt beslut i BESLUTSLOGG.

## 8. Lokal leveranskontroll 2026-10-27

Kört med projektets befintliga Pythonmiljö och `scripts/testing/run_tests.py`:

| Urval | Resultat |
|---|---|
| `--changed --base origin/main --run` | 43 godkända, två ändrade testfiler |
| `--suite insights --suite web --dependents --run` | 904 godkända, 76 bortvalda; 47 testfiler, 117,32 sekunder |
| `--all --run` inför godkänd main-integration | 1 209 godkända, 78 bortvalda; 65 testfiler, 137,38 sekunder |

Leveransurvalet omfattar `agents`, `insights`, `orchestration`, `services`,
`tooling` och `web`. Postgres-proven var bortvalda med `not postgres`, inte
godkända eller körda; ändringsplanen pekade inte ut något berört Postgres-prov.
Helkörningen inför integration verifierade samma filinnehåll som datakontraktsbranchen;
mergen mot oförändrad `origin/main` gav inga konflikter eller nya kodändringar.
Målområden som ännu saknar tester blir inte verifierade genom urvalet.

`PYTHONUTF8=1` användes för läsbar svensk utmatning och `PYTEST_ADDOPTS`
pekade `--basetemp` på en egen katalog under gitignorerade `.pytest_cache/`,
eftersom åtkomst till pytest:s befintliga delade temporärkatalog nekades.
Lokala dokumentlänkar och `git diff --check` är kontrollerade.
