# Avstämd syntetisk FTA-månad

**Beställt:** 2026-11-02. **Design:** [P6-MANAD-001](../projekt/06_avdelningsfunktioner/AVSTAMD_FTA_MANAD_DESIGNSTOPP.md),
D1–D6 godkända av Karl i chatten 2026-11-03. Ingen ny beslutsloggspost.
**Införandestatus:** lokalt byggt och verifierat även mot PostgreSQL; införande i beståndsdatabasen återstår.

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

Tre tabeller i `src/models/premium_journal.py`, alla **ej införda i Lakebase**:

| Tabell | Innehåll och integritet |
|---|---|
| `premium_month_journals` | Scenario-ID som PK, fryst källpaket, rekonstruerade ursprungssaldon och replay-/metodhash, IB-körningsreferens, SHA-256, aktör och tid. Innehållet ändras inte |
| `premium_receipts` | Deterministiskt ekonomiskt ID som PK, journal-FK, unik `(journal_id, source_system, source_event_id)`, datum, originalkälla/allokeringar/G/C-spår, SHA-256 och registrerande aktör/tid |
| `premium_month_closes` | Deterministiskt period-ID, journal-FK, unik `(journal_id, period_end)`, fulla poster/ursprung/utdrag/analys med SHA-256 samt separat mänsklig granskningsmetadata |

Samtidiga mottagningar serialiseras på journalens radlås; unika nycklar ger
dessutom databasskydd. A6:s sparande serialiserar versionsnummer per datum med
ett transaktionsbundet advisory-lås i Postgres, gemensamt för webben och journalen.

`scripts/migrations/migrate_premium_journal.py` är förberett men inte kört mot
Lakebase. Det skapar endast de tre tomma tabellerna, med torrkörning som
standard, förutsättningskontroll, stopp vid partiellt schema och kontroll av
övriga radantal. `--apply` kräver verifierbar backupreferens. Inga grunder,
premier, journalposter eller agenträttigheter införs av migrationen.

Dialogens fyra tabeller saknas också fortfarande i Lakebase. De har sin redan
förberedda migration och eget införandefönster enligt designstoppet §9.
Godkännandet av D1–D6 är inte ett OK till backup, migration,
andra Lakebase-skrivningar eller omstart av den gemensamma webben.
Karl godkände separat PostgreSQL-proven i `svc_test` i chatten 2026-11-03
och bekräftade att ingen annan körde mot databasen. Godkännandet omfattar
provets egna testscheman, inklusive skapande, rättighetsprov och borttagning;
det omfattar inte införande i beståndsdatabasen eller merge till main.

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
förslagstext och inloggningslänken; de är bevarade. Inget har mergats till main.

**2026-11-03, separat godkänd PostgreSQL-verifiering:**
`run_tests.py --changed --base 93bad9e --run --postgres`, med
`PYTEST_ADDOPTS='-m postgres -p no:cacheprovider --basetemp=tmp/pytest-month-pg-approved --tb=short'`,
gav **101 godkända, 1 608 lokala prov bortvalda**, inga fel eller överhoppade prov
(19 min 26 s). Den redan godkända lokala sviten kördes alltså inte om.
Före körningen kontrollerades att samtliga konfigurerade testanslutningar pekade
på `svc_test` och att tjänsternas testanslutning skilde sig från beståndets.
Proven skapade och tog bort egna isolerade testscheman. Beståndsdatabasen
användes inte för skrivning, backup eller migration.

Det frysta Lakebase-utdraget kördes enbart i en ny lokal SQLite-databas:
492 försäkringar och 12 syntetiska betalningar, totalt 24 300,00 kr.
Premiehistoriken i ursprungskällan ändrades inte. Grundfallet blev:

```text
15 895 579,24 + 24 300,00 − 16 896,84 + 26 700,19 = 15 929 682,59 SEK
IB-FTA         premie       tariff→FTA     tid          oberoende UB-FTA
```

Oanalyserat är 0,000000 SEK. Räntekurva +50 bp, driftkostnad +10 % och
kombinationen gav också nollrest. Utgående C är 42 176 267,71 kr. Den lokala
rapporten har status `review_required`; inget faktiskt analysgodkännande eller
baslås har registrerats för leveransen. Rapport och fulla källreferenser finns
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

Efter lokal och PostgreSQL-verifiering återstår eventuell integration
till main efter separat OK och först därefter samordnat Lakebase-införande.
Riktig fakturering/intagskanal, fler månader och verksamhetsfall, A8:s fulla
boksluts-/FI-kedja samt decemberbasen är fortsatt egna steg med sina beroenden.

**Noterad dokumentdrift utanför uppdraget:** README:s äldre inledning säger
fortfarande att fråge-/rapportkedjan inte är implementerad. Den har inte rättats här.
