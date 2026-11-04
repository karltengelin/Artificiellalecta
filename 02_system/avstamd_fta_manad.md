# Avstämd syntetisk FTA-månad

**Beställt:** 2026-11-02. **Design:** [P6-MANAD-001](../projekt/06_avdelningsfunktioner/AVSTAMD_FTA_MANAD_DESIGNSTOPP.md),
D1–D6 godkända av Karl i chatten 2026-11-03. Ingen ny beslutsloggspost.
**Införandestatus:** mergat till main; tre journaltabeller införda tomma i Lakebase
2026-11-03 och arbetsbänken aktiverad. Månadsförsöket är godkänt lokalt.
Rapporten uppdaterad 2026-11-04. Externt modellanrop i införandeprovet väntar på särskilt OK.

## Vad leveransen gör

Den första leveransen avser ett fryst S-04-bestånd per 2026-10-31 och syntetiska
novemberhändelser. Kapital och historiska garantidelar överförs till en journal
utan dubbel ekonomisk effekt. Mottagen nettopremie skapar eget kapitalursprung
och egen garantidel på mottagningsmånadens SIM-G. Månadens kapital rullas fram
med befintlig avräkning, och A6 beräknar utgående FTA oberoende av förklaringen.

A1:s versionerade stegordning skiljer premie, garanti-/värderingsskillnad, tid,
kurva och övriga antaganden. Varje mellanläge och post binds till källor,
grund-/parameterversion, metod och kontrollsumma. Oförklarat måste vara exakt
noll på sex decimaler och i öresredovisningen. Den generella 0,5 %-tröskeln
används inte som godkännandetolerans för denna analys.

Detta är två scenariovärderingar, aldrig låsta baser. SIM-V gäller alltjämt från
2026-12-31 och en bas kräver kvartalsslut. Underlaget är uttryckligen syntetiskt;
betalmarkeringen i äldre premiehistorik bevisar inte bankmottagning. Utbetalningar,
dödsfall, återtag, nya försäkringar, planändringar, full fakturering, tillgångssida,
huvudbok, ALM och solvens ingår inte. Projekt 5 är pausat.

## Kod och källkontrakt

| Del | Implementation |
|---|---|
| Frysta underlag, käll-/beloppsvalidering och allokering | `services/premium_month_inputs.py` |
| Skrivskyddad förberedelse från S-04 | `services/premium_month_preparation.py` |
| Kapitalspår per ursprung | `skills/calculation/premium_origin_ledger.py` |
| Mottagning, stängning, återläsning och analysgodkännande | `services/operations/premium_month.py` |
| FTA-steg och öresvisning | `services/premium_month_analysis.py` |
| A6-adapter | `compute_valuation(..., extract=...)`, endast scenario med kontrollerat journalutdrag |
| Dialoganalys | `perform_actuarial_analysis`: `monthly_fta_change` |
| Mänsklig grind | `agents/flows/definitions/premium_month_review.py`, befintlig `FlowEngine` |

Källpaketet innehåller originalutdraget med hash, frysta grunder och
produktparametrar med innehåll och kontrollsummor, faktura-/premieunderlag samt
bankhändelser. Varje källa binds till eget innehåll, version och syntetisk
märkning. En annan transportfil är inte en ny bankhändelse. Samma original med
ändrat innehåll ger konflikt. Bara händelser i det granskade källpaketet får
verkställas i försöket, i fryst datum-/originalordning.

Källans premieperiod och mottagningsdagen är olika fält. Den syntetiska
förberedelsen använder befintlig premiemotor med premieperiodens IBB och
parametrar. Värdedatum är mottagningsmånadens slut. Ingen garanti före
mottagning och ingen retroaktiv marknadsavkastning uppstår.

Mottaget netto fördelas till fakturans positiva öppna rader med befintlig
största-bråkrest-funktion. Delbetalning ger bara garanti för den mottagna delen.
Okänd faktura, fel betalare och belopp över öppet utrymme redovisas oallokerat,
utan G/C-effekt. Nollnetto ger ett kvitto utan positiv kapital-/garantieffekt.

## Tjänster och åtkomst

| Operation | Innehåll och agentnivå |
|---|---|
| `open_premium_month` | HUMAN_ONLY. `{inputs_json, reviewed_checksum}`. Validerar det frysta underlaget, återskapar ursprungsspår och sparar IB som scenarioutkast |
| `receive_premium_payment` | APPROVAL, omonterad för agenter. `{journal_id, receipt}`. Låser journalen, kontrollerar återstående utrymme och sparar mottagningskvitto, allokeringar, C-ursprung och G-del tillsammans |
| `close_premium_month` | HUMAN_ONLY/systemsteg. `{journal_id}`. Kräver alla källhändelser och antagen AVK med oförändrad historik; sparar kapitaljournal, journalutdrag, oberoende A6-UB och strikt avstämd brygga |
| `get_premium_month` | HUMAN_ONLY. `{journal_id, include_sources?}`. Status och granskningssumma; endast mänsklig aktör kan begära individjournalens fulla underlag |
| `approve_premium_month` | HUMAN_ONLY. `{journal_id, reviewed_checksum}`. Kontrollerar exakt granskat underlag och oförändrade mottagningskällor. Godkänner analys, aldrig basvärdering |

Befintlig tjänstetransaktion sparar affärseffekt och `operation_events` tillsammans.
Ett avbrott före commit lämnar ingen halv garanti-/kapitalpost. Efter commit
återfås samma ekonomiska kvitto. Ett stängt försök tar inte emot nya effekter;
rättelse blir ett nytt uttryckligt versionerat försök. Negativa rättelser av
mottagen premie är fortsatt blockerade.

Ursprungsmodellen återskapar alla historiska månader med samma `close_month` som
S-04. Fastställda försäkringsbelopp fördelas sedan på ursprungsspår. Avgift får
inte räknas och avrundas separat per premie. Varje försäkrings C och G samt
kollektivets ören bevaras. Ett kapitalspår kan bli noll utan att G försvinner.

Journalen och dess mottagningar är källa efter stoppunkten. De läggs aldrig
ovanpå en andra S-04-rekonstruktion av samma premier. `ledger` betyder här
journalfört underlag med bevarad ursprungsmärkning, inte verifierad huvudbok.

## Arbetsbänk, rapport och granskning

Den befintliga arbetsbänkens katalog visar tillgängliga månadsjournaler och
analysen `monthly_fta_change`, som tar `journal_id` och samma ränte-/dödlighets-/
kostnadseffekter som befintliga scenarier. Systemarbetaren räknar och lämnar
skyddade aggregat. Agentrollen får inga rättigheter till de nya tabellerna.
Diagram och rapport kan skapas från sparad analys genom befintlig dialog.

Även en stor population kan ha en liten premieeffekt: om bara 1–9 försäkringar
bidrar undertrycks hela analysens belopp. Den allmänna arbetsbänken får aldrig
individspår. Människan kan använda `get_premium_month(include_sources=true)`
genom tjänstelagret för granskning av fulla källor och poster.

`premium_month_review_definition()` ansluts till befintlig `FlowEngine`.
Systemsteget verifierar och visar analysen, grinden binder resultatets hash och
det sista steget registrerar godkännandet under den människa som fattade det
varaktiga grindbeslutet. Aktörsidentitet tas aldrig ur modelltext eller indata.
Definitionen är körbar via motorn; den är inte automatiskt monterad i den
gemensamma webbens FlowConsole. Ingen ny schemaläggare eller agent införs.

FTA-steg redovisas som `Q(nytt mellanläge) − Q(föregående mellanläge)`, med
ROUND_HALF_UP. Differensen mot separat avrundat delta är spårbar metadata, inte
fri balanspost. VÅ:s avstämda öresvisning härleds som `C − Q(FTA) + Q(U)` och
visar sin justering mot separat avrundat VÅ. Sparade motorvärden ändras inte.
Den tidigare identifierade oktoberskillnaden på 0,01 kr finns kvar i äldre
visningsvägar; denna leverans ändrar inte deras historiska resultat.

## Lokal körning

`scripts/analysis/prepare_premium_month.py` läser Lakebase i en uttrycklig
`REPEATABLE READ READ ONLY`-transaktion och sparar bara en lokal fil. Ange
förväntad, redan granskad IB-kontrollsumma. Verktyget får inte skriva över ett
fryst underlag. Individreferenser hålls under ignorerade `tmp/premium_month/`.

```powershell
python scripts/analysis/prepare_premium_month.py --db lakebase --scenario november-2026-v1 --expected-opening-checksum <IB-hash> --output tmp/premium_month/november-2026-v1.json
python scripts/analysis/run_premium_month.py --inputs tmp/premium_month/november-2026-v1.json --expected-checksum <kallpaketets-hash>
python scripts/analysis/run_premium_month.py --inputs tmp/premium_month/november-2026-v1.json --expected-checksum <kallpaketets-hash> --database tmp/premium_month/november.sqlite --operator karl --execute
```

Det andra verktyget har ingen Lakebase-flagga. Utan `--execute` validerar det
bara källpaketet. Databassökvägen vid verkställighet måste ligga under repots
`tmp/premium_month/` och vara en SQLite-fil. Endast utpekade lokala tabeller
skapas; inga kapitalförvaltningsmodeller tas med. AVK-förslaget och antagandet
sker via A4:s befintliga tjänster, endast i denna lokala databas.

Körningen lämnar analysen `review_required` och skriver en aggregatrapport som
JSON och Markdown bredvid SQLite-filen. En senare explicit
`--approve-checksum <granskad-hash>` kan registrera människans analysbeslut
genom samma tjänstelager. Verktyget godkänner aldrig sin egen analys automatiskt.

## Tabeller och Lakebase-gräns

Tre tabeller i `src/models/premium_journal.py`, **införda tomma i Lakebase 2026-11-03**:

| Tabell | Innehåll och integritet |
|---|---|
| `premium_month_journals` | Scenario-ID som PK, fryst källpaket, rekonstruerade ursprungssaldon och replay-/metodhash, IB-körningsreferens, SHA-256, aktör och tid. Innehållet ändras inte |
| `premium_receipts` | Deterministiskt ekonomiskt ID som PK, journal-FK, unik `(journal_id, source_system, source_event_id)`, datum, originalkälla/allokeringar/G/C-spår, SHA-256 och registrerande aktör/tid |
| `premium_month_closes` | Deterministiskt period-ID, journal-FK, unik `(journal_id, period_end)`, fulla poster/ursprung/utdrag/analys med SHA-256 samt separat mänsklig granskningsmetadata |

Samtidiga mottagningar serialiseras på journalens radlås; unika nycklar ger
dessutom databasskydd. A6:s sparande serialiserar versionsnummer per datum med
ett transaktionsbundet advisory-lås i Postgres, gemensamt för webben och journalen.

`scripts/migrations/migrate_premium_journal.py` kördes mot Lakebase 2026-11-03
efter separat OK och verifierad backup. Det skapar endast de tre tomma tabellerna, med torrkörning som
standard, förutsättningskontroll, stopp vid partiellt schema och kontroll av
övriga radantal. `--apply` kräver verifierbar backupreferens. Inga grunder,
premier, journalposter eller agenträttigheter införs av migrationen.

Dialogens fyra tabeller infördes separat 2026-11-03 efter backup
`backups/20261103T203424Z`. Senaste main och skrivskyddad schemakontroll
bekräftar att deras kolumner, nycklar, index och villkor stämmer.
Godkännandet av D1–D6 är inte ett OK till backup, migration,
andra Lakebase-skrivningar eller omstart av den gemensamma webben.
Karl godkände separat PostgreSQL-proven i `svc_test` i chatten 2026-11-03
och bekräftade att ingen annan körde mot databasen. Godkännandet omfattar
provets egna testscheman, inklusive skapande, rättighetsprov och borttagning;
det omfattar inte införande i beståndsdatabasen eller merge till main.

Karl granskade därefter månadsrapporten och godkände uttryckligen merge och
samordnat Lakebase-införande i chatten 2026-11-03. Införandet omfattar backup,
de tre tomma journaltabellerna, webbomstart med befintlig arbetsbänk och ett
märkt dialogprov. Den syntetiska novemberjournalen och AVK-förlängningen ligger
kvar lokalt; inga syntetiska mottagningar införs i beståndsdatabasen i detta pass.

## Verifiering och kvarstående arbete

**2026-11-03, lokal verifiering:** `run_tests.py --all --run` på den färdiga
lokala implementationen gav **1 607 godkända, 101 PostgreSQL-prov bortvalda**,
inga fel eller överhoppade prov. Ett riktat urval efter kontrollsummeflytten gav
143 godkända och två PostgreSQL-prov bortvalda. Nya Pythonfiler passerar Ruff;
diff, testkatalog och dokumentlänkar är kontrollerade. Två äldre lintanmärkningar
i orörda rader i `valuation_bases.py` (RUF007/C408) har lämnats utanför uppdraget.

Efter att main `93bad9e` förts in i arbetsbranchen kördes hela den lokala sviten
på det sammanslagna kodläget: **1 608 godkända, 101 PostgreSQL-prov bortvalda**,
inga fel eller överhoppade prov. Main-tilläggen rör F5-7:s driftstatus,
förslagstext och inloggningslänken; de är bevarade. Detta föregick integrationen nedan.

**2026-11-03, separat godkänd PostgreSQL-verifiering:**
`run_tests.py --changed --base 93bad9e --run --postgres`, med
`PYTEST_ADDOPTS='-m postgres -p no:cacheprovider --basetemp=tmp/pytest-month-pg-approved --tb=short'`,
gav **101 godkända, 1 608 lokala prov bortvalda**, inga fel eller överhoppade prov
(19 min 26 s). Den redan godkända lokala sviten kördes alltså inte om.
Före körningen kontrollerades att samtliga konfigurerade testanslutningar pekade
på `svc_test` och att tjänsternas testanslutning skilde sig från beståndets.
Proven skapade och tog bort egna isolerade testscheman. Beståndsdatabasen
användes inte för skrivning, backup eller migration.

**Inför integration mot main `e6f81f8`:** synken tog också med B-044:s
rättningsvarv och dokumentationen om dialogens tidigare schemainförande.
`run_tests.py --all --run --postgres` gav **1 711 godkända och ett fel**.
Felet låg i `test_underkant_utdrag_stoppar_vardering`: ett ospecificerat UUID-urval
kunde radera ett historiskt läge som inte gällde värderingsdagen. Provet väljer
nu ett läge som gäller dagen. Beräkningsspärren ändrades inte. Rättningen finns i
`23493e8` (`test: stabilisera utdragskontroll inför FTA-införande`) och passerar Ruff.

Efter rättningen verifierades kodläget med två kompletterande urval genom
`run_tests.py` och `PYTEST_ADDOPTS`:

| Körning | Godkända | Bortvalda | Omfattning |
|---|---:|---:|---|
| `--all --run --postgres`, `-k "not postgres or test_valuation_runs"` | 1 598 | 114 | Lokala prov samt testfilens tre PostgreSQL-prov; namnfiltreringen tog även bort lokala prov med `postgres` i namnet |
| `--all --run`, `-k "postgres and not test_valuation_runs"` | 16 | 1 696 | De återstående lokala proven; PostgreSQL-markören var bortvald |

Tillsammans täcker urvalen **alla 1 611 lokala prov och de tre berörda
PostgreSQL-proven**. Övriga 98 PostgreSQL-prov passerade i helkörningen och deras
kod var oförändrad. Inga fel eller överhoppade prov i omkörningarna.

Det frysta Lakebase-utdraget kördes enbart i en ny lokal SQLite-databas:
492 försäkringar och 12 syntetiska betalningar, totalt 24 300,00 kr.
Premiehistoriken i ursprungskällan ändrades inte. Grundfallet blev:

```text
15 895 579,24 + 24 300,00 − 16 896,84 + 26 700,19 = 15 929 682,59 SEK
IB-FTA         premie       tariff→FTA     tid          oberoende UB-FTA
```

Oanalyserat är 0,000000 SEK. Räntekurva +50 bp, driftkostnad +10 % och
kombinationen gav också nollrest. Utgående C är 42 176 267,71 kr. Karl granskade
månadsrapporten och godkände den i chatten 2026-11-03. Godkännandet har
registrerats genom tjänstelagret i den lokala databasen som `approved_analysis`,
med oförändrad granskningshash. Inget baslås har registrerats.
Rapport och fulla källreferenser finns
under ignorerade `tmp/premium_month/november-2026-release.report.md` respektive
`.json`. Granskningshash:
`2bb86253731d465de23e2d3fd0ff0da4ecadc4f3f7233ab5a00283d90891aeb6`.

En separat skrivskyddad kontroll av den lokala SQLite-filen verifierade alla
45 303 kapitalposters och de 12 nya garantidelarnas egna SHA-256-summor,
oförändrat innehåll för samtliga 15 097 historiska garantidelar och exakt summa
för de utgående kapitalspåren. Körverktyget skapade inga projekt-5-tabeller.

`tests/test_premium_month.py` provar frysta källor, beloppsallokering,
återleverans, historisk rekonstruktion, PR-020:s oberoende kronfacit,
godkännandekö, atomisk rollback vid loggfel, FTA-steg och separata scenarier,
småcellsskydd, ändrade underlag och flödesmotorns mänskliga grind.
Postgres-provet omfattar tom/idempotent migration och samtidiga mottagningar
mot eget schema i `svc_test`, samt verifiering att aktuariens begränsade roll
saknar direkt läsrätt på de tre nya tabellerna. Det passerade i den samordnade
körningen ovan, tillsammans med befintliga migrations-, behörighets- och
samtidighetsprov för tjänsterna, dialogen och A6.

## Införande i Lakebase 2026-11-03

Merge och push till main genomfördes som `eef4bd6`
(`merge: avstämd syntetisk FTA-månad`) efter verifieringen ovan. Den tidigare
dialogmigrationen bevarades; inga av dess fyra tabeller återskapades.

- **Backup:** `C:/Claude/Artificiellalecta/backups/20261103T212124Z`,
  26 tabeller och 17 442 rader. Alla JSONL-filer validerades, radantalen stämde
  mot beståndet och filerna fick SHA-256-kontrollsummor. Manifestets SHA-256 är
  `fb2be1f2fee70512c57ebfb52adffc47d80ff8e09920df7304f7fbbc904793e3`.
- **Samordning:** skrivskyddade kontroller före backup och tillämpning visade
  inga andra aktiva transaktioner eller köade/pågående handläggar-, dialog- eller
  flödeskörningar. Beståndets radantal och frysta grunder kontrollerades igen
  före skrivning. Införandet skedde på kvällen, utanför arbetarens 07.05-körning.
- **Migration:** torrkörning granskades före `--apply --backup …`. Bara
  `premium_month_journals`, `premium_receipts` och `premium_month_closes` skapades,
  med index och villkor. Alla 26 befintliga tabellers radantal var oförändrade.
  De tre nya tabellerna var tomma. En ny torrkörning gav `already_applied`.
- **Schema och åtkomst:** kolumner, nullbarhet, datatyper, index, unika villkor,
  kontrollvillkor och främmande nycklar verifierades för samtliga sju dialog-/
  journaltabeller. Aktuariens verkliga roll saknar direkt kolumnläsning och
  skrivrätt till dessa sju tabeller samt `valuation_extracts`; SELECT-proven
  nekades med PostgreSQL-felkod `42501`. Inga nya rättigheter gavs.
- **Webb:** port 8765 startades om från main med
  `scripts/web/start_ui.py --db lakebase --port 8765 --actuary-workspace`.
  `/`, `/team/aktuarie` och `/team/aktuarie/dialog` gav HTTP 200.
  Förnyad HTTP-kontroll 2026-11-04 gav samma svar.
  OpenAPI är avsiktligt avstängt och används inte som hälsokontroll.
  Startloggar finns i huvudkatalogens `logs/fta_month_web_20261103T214810Z.*.log`.
  Skrivbordsgenvägen startar fortfarande grundläget; vid ny manuell serverstart
  behövs flaggan ovan för aktuariedialogen.
- **Dialogprov utan extern modell:** ett uttryckligt syntetiskt uppdrag kördes
  genom ordinarie harness och tjänster med lokal `FakeProvider`, verklig
  begränsad databasroll och tom AI-nyckelmiljö. Analys, diagram, rapport,
  följdfråga och återöppning passerade. Båda turerna fick `completed`.
  Dialogen är `5d73367e2197411c90e87ad2f5236ea5`. Antalen ändrades endast för
  `actuarial_conversations` 2→3, `actuarial_turns` 2→4 och `actuarial_analyses` 4→8.
  Övriga tabeller var oförändrade, inklusive 501 försäkrade, 499 försäkringar,
  15 097 premier, sju grunder och tre tomma journaltabeller.

Det riktiga modellanropet avvisades **före körning** av automatisk
godkännandegranskning: införandegodkännandet ansågs inte uttryckligen omfatta
överföring av databasunderlag till en extern modellleverantör. Därför gjordes
ingen extern modellkörning i detta införandeprov. Ett förberett prov med
ordinarie modellpolicy väntar på Karls särskilda OK till att syntetiska
grunddata och skyddade aggregat kan skickas till modellleverantören. Det lokalt
skriptade provet ovan är inte en verifiering av den riktiga modellen.

Verifieringsunderlagen finns under ignorerade `tmp/premium_month/`: `verified-backup.json`,
`journal-migration-applied.json`, `lakebase-after-schema.log`,
`lakebase-dialogue-local-smoke.json` och testloggarna `integration-tests.log`,
`integration-fixed-tests.log` samt `integration-local-complement.log`.

## Kvarstående arbete

Extern modellverifiering med separat OK enligt ovan återstår. Den granskade
syntetiska novemberjournalen och AVK-versionen är fortsatt lokala; inga
syntetiska mottagningar, nya grunder eller sparade värderingar infördes i Lakebase.
Riktig fakturering/intagskanal, fler månader och verksamhetsfall, A8:s fulla
boksluts-/FI-kedja samt decemberbasen är fortsatt egna steg med sina beroenden.

**Noterad dokumentdrift utanför uppdraget:** README:s äldre inledning säger
fortfarande att fråge-/rapportkedjan inte är implementerad. Den har inte rättats här.
