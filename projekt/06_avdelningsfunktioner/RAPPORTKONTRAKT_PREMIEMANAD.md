# V-12 · Intern månadsrapport om premier och betalningar

**Kontrakt 1.0 · 2026-11-22 · projekt 6 och projekt 2.** Första tillämpningen är Paket C:s isolerade, syntetiska novembermånad. I democentralen kan operatören bereda rapporten, fatta rapportbeslut och kvittera den godkända versionen.

## 1. Mottagare och beslut

Ekonomiansvarig ska vid månadsslutet kunna besvara tre frågor. Hur mycket har fakturerats och kommit in? Vad återstår att driva in eller utreda? Går beloppen att godkänna mot bankunderlaget ned till sista öret?

| Roll | Ansvar vid rapporttillfället |
|---|---|
| Försäkringsadministration, projekt 1 | Äger källhändelser och radspår. Utreder felaktig matchning och bevakar förfall i handläggarytan. |
| Ekonomi/rapportering, projekt 6 | Tar fram rapporten, stämmer av mot källorna och anger ansvarig funktion och nästa kontroll för varje öppen post. |
| BI, projekt 2 | Förvaltar måttdefinitionerna med domänägaren. Samma definition och tidsgrund ska följa ett mått som återanvänds i ledningsöversikten. |
| **Operatören i rollen som ekonomiansvarig** | Granskar och godkänner eller återremitterar en bestämd rapportversion. En person kan i simuleringen utföra både beredning och granskning. Registrera då den faktiska aktören i båda rollerna. |
| VD/operatörscentralen, projekt 10 | Intern mottagare av godkänd sammanfattning med totalsaldon, öppna frågor och ansvarig funktion. Individrader, personnummer, OCR och fullständigt källunderlag hör till den behöriga specialistgranskningen. |

## 2. Period, avgränsning och källpaket

Rapporten avser **en körning, ett scenario och en avslutad rapportmånad**. Ange ursprunglig löneperiod, rapportperiod med exklusivt slut, simulerad avstämningsdag och sista behandlade händelse. Exemplet avser oktoberlöner och intervallet `[2026-11-01, 2026-12-01)`. Frys november efter månadens sista planerade bankleverans och förfallobevakning. Ett besked per 29 december får egen daterad uppföljning med hänvisning till november.

Paket C börjar med nollsaldo. `get_receivables` läser den isolerade databasens **sammanlagda** belopp vid anropet och saknar periodfilter. Läs därför den frysta novemberobservationen. För verklig flermånadsdrift krävs avstämd ingående balans, periodens daterade rörelser och utgående balans. En decemberavläsning av samma databas kan inte återskapa november. [Paket C:s körväg](../../02_system/manadssimulator_designstopp.md) · [Fordringsoperationen](../../src/services/operations/payments.py)

| Underlag från körkatalogen | Vad granskaren binder till rapporten |
|---|---|
| `manifest.json` | Körningens scenario, seed, startbild, kodrevision, källkodssumma, regelpaket, parameterversioner och facitversion. Stäm av manifestets kanoniska summa mot `manifest_hash` i rapportunderlaget. |
| `2026-11-30.json` | `run`, `period`, `as_of`, `observed`, `hash`, `failures` och `unverified`. Verifiera affärsutfallets normaliserade summa med C:s `business_hash`. Behörig granskare kan följa varje rad i `observed.traces` till lön, premie, faktura, händelse och allokering. |
| Motpartsfiler och bankkvitton | Stäm av `file_checksums` mot A:s innehållssummor för lön och bank, även eventuell återleverans. Räkna unika betalningar på källsystem och händelse-ID. Använd simulatorns separata facit som jämförelse. |
| `2026-11-30.md` och decemberunderlaget | Novemberfilen är befintligt läsbart specialistprotokoll. Hämta decemberuppföljningen ur `2026-12-29.json`. Ledningssammanfattningen ska kunna läsas utan att öppna specialistbilagorna. |

Detta är ett internt rapportkontrakt. Extern rapportering prövas separat per mottagare, period, tillämplighet och leveranskvitto. Kapital, garanti, FTA, portfölj och huvudbok visas som **ej prövat** i denna version.

## 3. Mått och kontroller

Penningbelopp anges i SEK med två decimaler. Jämför heltalsören eller decimalbelopp med exakt öresprecision. Saknat eller oläsbart underlag markeras **saknas** och stoppar godkännande om det behövs för en obligatorisk kontroll.

| Mått | Definition vid avstämningsdagen | Fält i fryst observation |
|---|---|---|
| Nettofakturerat | Debetfakturor efter kreditfakturor för körningens arbetsgivare. | `balances.invoiced_sek` |
| Bankinbetalningar | Summa unika inkommande bankhändelser, även belopp som väntar på utredning. | `balances.bank_total_sek`, antal i `counts.bank_events` |
| Mottaget på fakturarader | Faktiskt fördelat belopp, inklusive delbetalningar på rader med status `invoiced`. Projekt 2:s befintliga mått *registrerat betalda premier* använder fullbetalda rader och betaldatum. | `balances.allocated_sek`, `rows[].allocated`, `traces[].receipts` |
| Avstämningskonto | Oallokerade bankmedel, exempelvis okänd OCR eller överskott. Redovisa skäl, ärendereferens och ansvarig funktion. | `balances.suspense_sek`, `cases` och bankkvittot |
| Öppen och därav förfallen fordran | Återstående debet efter krediter och radallokeringar. Därav förfallet är öppet belopp för fakturor med `due_date < as_of`. På förfallodagen är fakturan fortfarande i tid. | `balances.receivables_sek`, `balances.open_invoices[].open_sek/due_date` |
| Handläggning och modellkostnad | Antal granskade lönefilbeslut, avslag, återlevererade bankhändelser och ärenden per typ/status. Redovisa faktisk aktiv körtid och väntetid på filbeslut i sekunder. Modellanrop i antal och kostnad i USD. | `reviews`, `rejections`, `redeliveries`, `observed.cases`, `active_seconds`, `wait_seconds`, `model_calls`, `model_cost_usd` |

Fälten i de fem första raderna ligger under `observed`. Tiderna avser räknarna vid rapportsteget. Rapportgranskarens eget beslut registreras separat i §5. [Måttkontrakt för registrerat betalda premier](../02_bi_insikter/DATAKONTRAKT_FRAGEKEDJA.md) · [C:s observation och beloppsfacit](../../src/simulation/premium_verification.py)

**Godkänt kräver samtliga fyra kontroller.**

1. Period, kör-ID, startbild, källsummor och affärsutfall går att verifiera. `failures` är tom och obligatoriska fält finns.
2. Bankinbetalningar minus radallokeringar minus avstämningskonto är **0,00 kr**. Nettofakturerat minus radallokeringar minus öppna fordringar är **0,00 kr** för detta nollställda bestånd.
3. Summera mottagna belopp per fakturarad och öppna belopp per faktura. Båda summorna ska stämma med respektive total och radutfallen med det oberoende scenariefacitet. Ett öres fel på en rad stoppar även om totalen balanserar.
4. Varje öppen post har belopp, orsak, ansvarig funktion och nästa kontroll. En förklarad restfordran eller oallokerad betalning kan redovisas i en godkänd rapport. Oförklarad differens, fel datum eller saknad källa ger återremiss till producenten.

## 4. Kontrollfall och exempel till mottagaren

**November 2026, delbetalning.** En faktura på **6 733,13 kr** utfärdades den 25 november. En bankbetalning på **4 000,00 kr** kom in den 30 november. Hela beloppet fördelades på två fakturarader, 1 203,01 respektive 2 796,99 kr. Båda avstämningarna gav **0,00 kr** i differens.

| Vid avläsningen | Öppen fordran | Därav förfallen | Avstämningskonto | Ärende och nästa åtgärd |
|---|---:|---:|---:|---|
| 30 november | 2 733,13 kr | 0,00 kr | 0,00 kr | Inga öppna ärenden. Försäkringsadministrationen bevakar fakturan med förfallodag 28 december. |
| 29 december, daterat tillägg | 2 733,13 kr | 2 733,13 kr | 0,00 kr | Ett öppet förfalloärende, `CASE-000001`. Handläggaren följer upp kvarstående belopp i ärendet. |

Novemberunderlaget visar ett granskat lönefilbeslut, noll avslag, noll återleveranser, noll modellanrop och 0 USD i modellkostnad. Referenskörning `57f2d1f6fb1f4b8598858ab4e50b1d89`, kod `387722a`, scenario `partial`. Affärssumman börjar med `84f084b49f8b` i november och `8a446b67f75e` i december. Fulla summor finns i de daterade JSON-underlagen. Exemplet belägger källutfallet. Rapportbeslut och mottagarkvitto återstår i den föreslagna arbetsvägen.

| Övrigt acceptansfall | Vad rapporten ska visa |
|---|---|
| Full betalning och samma kvitto i ny fil | 6 733,13 kr mottaget, en unik bankhändelse, två radallokeringar och 0,00 kr öppet. Återleveransen höjer återleveransräknaren med ett. |
| Två verkliga fullbetalningar | Två unika bankhändelser, 13 466,26 kr på banken, 6 733,13 kr på fakturarader och 6 733,13 kr på avstämningskontot. Ett öppet matchningsärende tar hand om överskottet. |
| Okänd OCR | Banken visar 6 733,13 kr, avstämningskontot 6 733,13 kr och fordran 6 733,13 kr. Radallokeringen är 0,00 kr. Specialistunderlaget ska identifiera matchningsärendet. |
| Fel underlag | En ändrad allokeringsrad på ett öre, decemberfil som novemberkälla eller fel kontrollsumma ska ge ett namngivet kontrollfel och blockera rapportbeslutet. |
| Avslagen lönefil | C ger ett särskilt beslutsprotokoll och uppföljningsärende. Märk novemberunderlaget som ej framtaget om körningen avbröts före månadsslut. |

## 5. Granskning, mottagarkvitto och rättelse

1. **Bered.** Ge varje leverans kontraktsversion, rapport-ID, kör-ID, rapportperiod, avstämningsdag, revisionsnummer, producent och verklig tid i UTC. Ange om den är ordinarie rapport, daterad uppföljning eller rättelse. Lås källreferenserna från §2. Skapa ledningssammanfattningen med kontroller och öppna åtgärder.
2. **Granska.** Operatören ser exakt den sammanfattning som ska lämnas till mottagaren och kan öppna behöriga källspår. Spara beslut `godkänd` eller `återremitterad`, aktör, verklig tidpunkt, motivering och en kontrollsumma över den granskade leveransen. Summan ska binda rapportidentitet, revision, levererade texter, mått, kontroller, öppna åtgärder och källreferenser. C:s `hash` täcker affärsutfallet och används som en av dessa referenser.
3. **Kvittera.** När den godkända versionen tagits emot internt sparas mottagare, tidpunkt, rapport-ID, revision och samma leveranssumma. Skilj mellan *godkänd, väntar på kvitto* och *mottagen*. Om operatören har båda rollerna dokumenteras även det. Upprepad kvittens av samma version ger en mottagning.
4. **Följ upp eller rätta.** Ett senare förfall ger ett daterat tillägg enligt §4. Ett fel i novemberrapporten ger ny revision med hänvisning till föregående version, orsak och beloppsskillnad. Den nya versionen granskas och kvitteras på nytt. Granskaren ska kunna återfinna det tidigare utfallet.

## 6. Kör rapportflödet i demo

1. Starta democentralen med `python scripts/web/start_ui.py --db demo` i den arbetskopia där Paket C-körningen finns. Logga in som operatör. [Operatörsinloggning](../../02_system/operator_inloggning.md) · [Kör premiemånaden](../../02_system/manadssimulator_designstopp.md)
2. Gå till **Centralen → Granska och kvittera premiemånadens rapport** (`/central/premierapporter`). Välj kör-ID och 30 november. **Bered för granskning** fryser källspåren och visar belopp, öresdifferenser, åtgärder och samtliga kontroller. En körning som stannat vid lönebeslutet saknar månadsunderlag.
3. Öppna specialistunderlaget vid behov. Motivera beslutet och välj **Godkänn versionen** eller **Återremittera**. Kontrollfel spärrar godkännande. Rätta källan och bered en ny revision vid återremiss. Även en tidigare kvitterad version kan rättas. Ange rättelseorsak på aggregerad nivå och använd kör-ID för det rättade underlaget från samma scenario. Granskaren kan följa länken bakåt till föregående leverans.
4. Under **Intern mottagning** öppnar mottagaren den godkända rapporten och väljer **Kvittera intern mottagning**. Kvittot visar aktör, verklig tid i UTC, revision och leveranssumma. Samma operatör kan utföra båda momenten. Den daterade decemberuppföljningen kan beredas när november har godkänts.

Rapporter, källkopior, beslut och kvitton sparas i `logs/simulation/paket-c/v12.sqlite` i arbetskopian. Bevara den filen tillsammans med körkatalogerna och startbeståndet. Vid omstart loggar operatören in igen och återfinner tidigare revisioner under **Ekonomiansvarigs granskning**.

Pensioner och utgående betalningar knyts senare till Paket B:s egna kvitton. Huvudbok och aktuariell värdering behöver egna avstämda underlag från projekt 6.
