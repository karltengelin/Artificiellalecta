# Paket C – designstopp för den första premiemånaden

**Godkänt för bygge 2026-11-22.** Underlaget är granskat mot `main` på `63a26b2`. Karl godkände en enda ej startad uttagsdel per förmån och slutpunkt vid Paket A:s allokeringar. Efter genomgången av C1–C4 i §7 gav Karl klartecken till byggstart i chatten. Den lokala körvägen beskrivs nedan.

### Kör premiemånaden

Från reporoten med projektets Pythonmiljö:

```powershell
python scripts/simulation/premium_calendar.py start partial
python scripts/simulation/premium_calendar.py status <kör-id>
python scripts/simulation/premium_calendar.py approve <kör-id> --revision 1 --digest <granskad-summa> --note "Två giltiga oktoberlöner granskade"
```

`start` visar kör-ID, rader, summering och beslutsunderlag. `status` gör om den aktuella filgranskningen. Använd revisionen och summan som hör till den visningen. `reject` tar samma argument och registrerar avslag med skäl. Den lokala operatörens identitet hämtas från operativsystemet. För att fortsätta efter processavbrott körs `resume <kör-id>`. Ett nytt `start` återställer läget genom att skapa en ny kopia. Tillgängliga betalningsfall är `full`, `partial`, `duplicate`, `twice` och `unknown`.

Under `logs/simulation/paket-c/<kör-id>/` finns den lokala databasen, körmanifestet, motpartsfiler med separat filfacit och rapporterna `2026-11-30.md` och `2026-12-29.md` med källspår i JSON. Ett avslag ger ett eget beslutsprotokoll. Statuskommandot kan återskapa filerna ur databasen efter avbrott. En avvikelse i öresfacitet ger underkänt protokoll och felkod. Ett avstämt delbelopp med öppen fordran är ett giltigt utfall.

**Genomförande av S-05.** Varje kalendersteg tar ett skrivlås i körningens SQLite-kopia. Ordinarie tjänsteanrop, tjänstelagrets händelselogg och kalenderkvittot avslutas i samma yttre transaktion. En process som dör mitt i steget lämnar föregående revision intakt. Vid fortsatt körning kontrolleras startbilden, versionen och domänspåren för redan genomförda beslut och banksteg. Rapporterna identifierar mottagaren med försäkringsnummer eftersom A:s tekniska fakturaradnummer kan variera mellan försök.

**Verifierat lokalt 2026-11-22.** I [kalenderproven](../tests/test_premium_calendar.py) gav två försök per betalningsfall samma affärsutfall för november och december. Vid delbetalning blev beloppen 1 203,01 och 2 796,99 kr, med 2 733,13 kr kvar. Förfalloärendet öppnades den 29 december. Återleveransen gav en unik bankhändelse. Separata prov täcker konkurrerande beslut, nekad agent, avslag, ändrat facit med ett öre, avbrott före kvittens, motstridigt bankunderlag vid återstart och återgivning av rapporter från körningens databas. Detta avser den lokala premiemånaden på Paket A. Delbetalningens fortsättning till B:s stängning för sparandet beskrivs nedan. Samprov för en full pensionsmånad återstår.

### Samprova delbetalningen med sparandets novemberstängning

Använd projektets Python från reporoten. Varje beslut visar vilket kommando, kör-ID, revision och granskningssumma som gäller för nästa bokning. Läs kontrollerna i terminalen. `status` hämtar den aktuella granskningen igen och `resume` återgår till samma beslut efter ett avbrott.

```powershell
python scripts/simulation/premium_calendar.py start partial --savings
python scripts/simulation/premium_calendar.py open-ledger <kör-id> --revision <revision> --digest <öppningssumma> --note "Oktober-IB granskad"
python scripts/simulation/premium_calendar.py approve <kör-id> --revision <revision> --digest <filsumma> --note "Oktoberlöner granskade"
python scripts/simulation/premium_calendar.py close-month <kör-id> --revision <revision> --digest <stängningssumma> --note "Novemberpremier och kapitalbrygga granskade"
```

Samprovet har en egen fryst SQLite-bild. De två försäkringarna i §3 har där varsin historisk septemberpremie, mottagen den 30 oktober, om 10 000,00 respektive 20 000,00 kr. Bilden innehåller produktparametrarna, de antagna SIM-grunderna och B-050:s syntetiska novemberavkastning på +0,20 % (AVK-SIM-2026-02). Handläggaren granskar B:s S-04-öppning per 31 oktober och bokar den i körkopian. Efter lönebeslutet läses sista bankfilen den 30 november. Kalendern fryser A:s novemberprotokoll och stannar för granskning på nästa bankdag, den **1 december**. B räknar då november med värdedag 30 november. `close_policy_month` kontrollerar underlaget på nytt vid bokning.

| Försäkring | IB | Avkastning | Kapitalavgift | Skattebelastning på kapital | Nettopremie | UB |
|---|---:|---:|---:|---:|---:|---:|
| AL-000001 | 10 000,00 | 20,00 | −1,67 | −2,95 | 1 203,01 | 11 218,39 |
| AL-000002 | 20 000,00 | 40,00 | −3,33 | −5,90 | 2 796,99 | 22 827,76 |
| **Totalt, kr** | **30 000,00** | **60,00** | **−5,00** | **−8,85** | **4 000,00** | **34 046,15** |

Årsavgiften 0,20 % och den årliga skattebelastningen 0,354 % tas på IB med en tolftedel, avrundat per del. Premierna går in vid månadsslut. Fakturans 6 733,13 kr fördelar sig på 4 000,00 kr mottaget och 2 733,13 kr öppen premiefordran. B:s garantigrund och kapitaltillskott blir exakt 1 203,01 respektive 2 796,99 kr. Pensionsutbetalningens preliminära skatt, bankuppdrag, dödsfall och arvsvinst hör till senare samprov.

I `logs/simulation/paket-c/<kör-id>/` finns A:s frysta `2026-11-30.md` med JSON och B:s bokade `sparande.md`. `sparande.json` innehåller den granskade stängningens verifikation och kontroller samt varje källkedja från bankhändelse och fakturarad via allokering och uttagsdel till kapitalpost och garantidel. Allokerings-ID:t knyter ihop rapporterna. Kördatabasen bevarar tjänstehändelser och kalenderkvitton. [Öresfacit och verifierare](../src/simulation/savings_verification.py) · [Prov av två körningar, inaktuell summa och ombokning](../tests/test_premium_calendar.py)

För att upprepa samprovet tillsammans med simuleringsgruppens övriga prov:

```powershell
python scripts/testing/run_tests.py --suite simulation --dependents --run
```

Provet startar två körningar med samma bildsumma och jämför det ekonomiska utfallet. Efter varje stängning anropas B:s bokningsoperation igen med samma granskade summa. Den ska återge samma verifikation och samma uppsättning kapitalposter, garantidelar och kontrollposter.

**Verifierat 2026-11-24.** Båda körningarna gav tabellens öresutfall. Ombokningen gav samma verifikation och noll nya poster. Ändringsurvalet gav 108 godkända och ett bortvalt Postgres-prov. Simuleringsgruppen med beroenden, kompletterad med Postgres-proven för S-04-öppning och novemberstängning, gav 111 godkända med en lokal PostgreSQL 16-instans och databasen `svc_test`.

## 1. Vad månaden ska visa

En operatör ska kunna följa två oktoberlöner från arbetsgivarens fil till en novemberfaktura, bankens betalning och ett avstämt belopp per fakturarad. Operatören ska också kunna se vad som återstår att betala om banken bara har fått en delbetalning. Samma händelser ska ge samma ekonomiska utfall efter en omkörning.

**Tre datum styr olika frågor.** Lönemånaden oktober 2026 bestämmer premieunderlaget. November är mottagnings- och rapportmånad. En kort uppföljning i december visar vad som händer med en öppen fordran vid förfall. Novemberutfallet sparas innan kalendern går vidare. Uppföljningen redovisas separat. Samtliga datum och belopp avser ett nytt, lokalt syntetiskt bestånd.

**Den föreslagna byggleveransen** omfattar en lokalt styrbar körning, ett fryst startbestånd, versionsbundna scenariofiler, ett oberoende beloppsfacit och ett läsbart avstämningsprotokoll. Projekt 1 äger premieoperationerna, projekt 4 produktreglerna och projekt 6 de efterföljande ekonomiska och aktuariella kontrollerna. C ansvarar för kalender, isolering och bevis för förloppet. Projekt 9 kan dokumentera den verifierade processen. [Processöversikt §§4–6](../01_domän/processer_översikt.md) · [Backlog för S-01–06](../ATT_GORA.md)

## 2. Befintliga delar och de luckor C behöver fylla

| Del | Återanvändning i första körningen | Vad C tillför |
|---|---|---|
| Arbetsgivare och bank, Paket A steg 5 | `salary_file` läser beståndet. `bank_file` läser öppna fakturor och tar `as_of`, seed och betalningsbeteende. `SimulatedFile.write` sparar indata och filfacit var för sig. `load_payload` ger tjänstens indata. | Planera och frysa varje leverans en gång vid dess beroende. En bankfil får skapas först när fakturan finns. Vid återleverans används den sparade händelsen. Ny generering ur en ändrad restfordran kan skapa en annan betalning. [Motpartssimulatorn](../src/simulation/counterparties.py) |
| Intag och faktura | `ServiceLayer.execute` anropar `import_salary_file`, `get_salary_file` och efter handläggarbeslut `approve_salary_file` eller `reject_salary_file`. Godkännande registrerar löner, skapar premieunderlag och eventuella ärenden i samma transaktion. `create_invoice` skapar faktura och OCR. | Binda kalenderhändelse, granskat underlag, aktör och domänkvitto till körningen. Visa utfall för varje lönerad före fakturering. [Filintag](../src/services/operations/salary_files.py) · [Premieunderlag](../src/services/operations/premium_basis.py) · [Fakturering och bevakning](../src/services/operations/invoices.py) |
| Bank och avstämning | `import_bank_file` matchar OCR och betalare, fördelar på öppna rader med största bråkrest och känner igen bankens identitet. `get_invoice`, `list_bank_events` och `get_receivables` ger utfall, ärendereferenser och saldon. | Jämföra verkligt tjänsteutfall både med filfacit och med i förväg granskade öresbelopp. Ett balanserat resultat kan fortfarande bygga på en felaktig faktura. [Betalningar och fordringar](../src/services/operations/payments.py) · [Befintliga räknefall](../tests/test_payments.py) |
| Kalender och tidigare körskript | `invoice_due_date` och `next_bank_day` innehåller A:s bankdagsregler. Oktoberskripten visar ordning och kontroller för en verklig kalenderkörning mot Lakebase. | Tillföra körningsbundet affärsdatum. Periodskripten använder dagens datum och en gemensam utdatakatalog. C behöver en egen lokal startväg. [Bankkalender](../src/utils/bank_calendar.py) · [Tidigare körning](../scripts/simulation/period_2026_10/) |
| Flödesmotor och harness | B-035:s fasta motor avvecklades i `40c92ee`. Sparade `FLOW`-uppdrag är läsbara i arkivet. Dagens lokala bolagsorkestratör har revisionskontroll, anspråk på ett körsteg och avstämning mot domänkvitton. `MissionStore` är knuten till operatör, dataset, SQLite och bolagsuppdragets tillstånd. | En tunn kalenderdrivare får verkställa en fast lista scenariohändelser genom tjänstelagret. Återanvänd kontrollsummor och vid behov den generella delen av revisions-/anspråkskontrollen. Domänbeslutet ligger kvar i Paket A. Första körningen behöver inga modellsteg. En senare agentinsats använder befintlig harness, mandat, budget och körjournal. [Dagens arbetsväg och arkiv](bolagsorkestrator_pilot.md) · [Körlagring](../src/agents/company_store.py) · [Domänkvitton och återupptagning](bolagsorkestrator_modellprov.md) |

## 3. Ett startbestånd, tre betalningsförlopp

Frys ett lokalt SQLite-underlag per **31 oktober 2026**. Det innehåller en fiktiv arbetsgivare och två anställda inom premieåldern, med varsin premiebetalande försäkring, förmån och ej startad uttagsdel 1. Båda omfattas hela oktober. Lönerna är 45 000 respektive 60 000 kr. Frys IBB 83 400 kr för 2026 och de premieparametrar som A använder för oktober. Kontrollera bestånd, mottagare, regelpaket, parameterversioner och kontrollsummor före första händelsen. Startvärden för periodens lönerapporter, premierader, fakturor, bankhändelser, allokeringar och öppna premieärenden är noll. Personernas avtalade löner finns redan i stamdata.

Vid oförändrad lön och seed 1 ska filen ge två giltiga rader, noll saknade och noll avvikande. Första lönen ger 2 025,00 kr. För den andra ger brytpunkten 52 125 kr två avrundade delpremier, 2 345,63 och 2 362,50 kr. Fakturan har därmed två debetrader och summan **6 733,13 kr**. Före byggstart kan dessa värden granskas direkt mot Paket A:s fall 1, 2 och 12. [Paket A:s designstopp §7](../projekt/01_ärendehantering/PREMIEFLODE_DESIGNSTOPP.md)

Varje rad nedan är en egen körning från samma startkopia. Beloppen är SEK per 30 november. Kolumnen *bank* avser summan av unika inkommande händelser.

| Förlopp | Bank | Allokerat på rad 1 / rad 2 | Öppen fordran | Avstämningskonto | Kvitto och premierader |
|---|---:|---:|---:|---:|---|
| Full betalning med rätt OCR och betalare | 6 733,13 | 2 025,00 / 4 708,13 | 0,00 | 0,00 | En bankhändelse, två allokeringar, båda raderna `paid` med betaldag 30 november. |
| En delbetalning på 4 000,00 | 4 000,00 | 1 203,01 / 2 796,99 | 2 733,13 | 0,00 | En bankhändelse, två allokeringar, båda raderna kvar som `invoiced`. Hela det mottagna beloppet ska synas. |
| Dubbelt bankkvitto för full betalning | 6 733,13 | 2 025,00 / 4 708,13 | 0,00 | 0,00 | Samma källa, händelse-ID och innehåll i en andra fil med ny filreferens och giltig filsumma. Andra intaget ger `already_received = 1`, noll nya händelser och 0,00 kr ny fördelning. |

Använd A:s `on_time` och `partial`. För just denna låsta faktura ger `share=0.594077` efter avrundning 4 000,00 kr. Dubblettfilen återanvänder den frysta händelsen. A:s beteende `twice` avser däremot två verkliga inbetalningar med skilda ID:n. Som kontroll av skillnaden ger två fulla betalningar 13 466,26 kr i bank, 6 733,13 kr på raderna och 6 733,13 kr på avstämningskontot med ett `payment_unmatched`-ärende. Samma ID med ändrat belopp och korrekt omräknad filsumma ska ge konflikt och rulla tillbaka hela filintaget.

## 4. Kalender, beslut och omkörning

| Simulerad dag | Ordning och villkor |
|---|---|
| 1 november | Verifiera startkopian och manifestet. Öppna rapportperioden november. Bevara A:s märkta historiklucka före första operativa premieperiod. |
| 25 november | Arbetsgivaren lämnar oktoberfilen. Intaget sparar den. Visa aktuell filgranskning och stanna före registrering. Vid godkännande använder handläggaren granskningens `expected_digest`. Först efter kvitto om godkänd fil kan faktureringen ske. Fakturadagen blir 25 november. |
| 26–29 november | Kör daglig förfallobevakning. Bankens händelse, planerad fem dagar efter fakturadagen, får vänta till den 30:e. Spara väntande leverans som sådan. |
| 30 november | Importera bankfilen, därefter eventuell återleverans. Läs avstämningen, kör dagens bevakning och frys novembers rapport efter sista planerade bankfilen. |
| 1–29 december | Fortsätt bevakningen dag för dag. A:s 30-dagarsvillkor ger 25 december, flyttat till bankdagen **28 december**. Inget förfalloärende den 28:e. Vid kvarstående rest den **29 december** ska exakt ett `payment_overdue` på 2 733,13 kr öppnas. Ett nytt varv samma dag ska återfinna samma ärende. Fullbetalda körningar har noll sådana ärenden. |

**Två klockor.** Sätt affärsdatum i betrodd körkontext per steg. Låt A:s datumhjälpare och giltighetskontrollen i `ProductRuleCatalog` använda samma affärsdag för denna körning. Lönernas IBB och premieparametrar väljs fortsatt för ursprungsperioden. Tjänstelagrets motiveringskrav, mandat och granskningskrav gäller vid varje anrop. UTC-tid för audit och beslut samt verklig aktiv tid för eventuella agentbudgetar följer ordinarie klockor. Möjligheten att välja simuleringsdag begränsas till körningens lokala tjänsteinstans. [Datumhjälpare](../src/services/operations/common.py) · [Regelkatalog](../src/services/rules.py)

**Operatörens arbetsväg.** Föreslagen första ingång är ett lokalt körverktyg med start, status, kör till nästa beslut och återuppta. Filgranskningen visar A:s aktuella granskningsunderlag och kräver ett uttryckligt beslut av identifierad handläggare i samma isolerade miljö. Körjournalen kopplar beslutet till filens domänkvitto. Motparternas läsning och filgenerering ger dem inget skrivmandat. Betrodda systemsteg får bara anropa sina angivna operationer med identifierad aktör och motivering.

**Pausen är varaktig.** Spara kör-ID, scenarioversion, affärsdag, ordningsnummer, händelsenyckel, aktuell revision, fryst filreferens, kontrollsumma och väntat kvitto. En enda arbetare får äga ett steg åt gången. Vid filgranskningen binder körningen operatörens identitet och beslut till aktuell revision och granskningssumma. Ändrat underlag kräver ny granskning. Vid avslag kör handläggaren `reject_salary_file` med skäl. Förväntat utfall är ett uppföljningsärende, noll registrerade löner och noll fakturor. Operatörens väntetid förbrukar ingen aktiv körbudget. Samma paus går att öppna efter omstart.

**Avbrott mellan skrivning och kvittens.** Spara anspråket före tjänsteanropet. Efter omstart läser drivaren först domänens utfall via filreferens och status, faktura per arbetsgivare och period eller bankens källsystem och händelse-ID. Bind även innehåll och belopp till den sparade avsikten. Entydig redan genomförd åtgärd kvitteras i körjournalen. En bevisat outförd, idempotent operation kan göras om. Motstridiga eller oklara underlag pausar kalendern för manuell avstämning. Ingen generell omstart får godkänna en fil i någon annans namn.

**Återställning skapar en ny körning.** Varje försök kopierar den stängda och kontrollsummerade lokala startdatabasen till en ny körkatalog med egen databas, journal, indata och rapport. Bara körningens databas får bindas till tjänstelagret. Behåll tidigare körning som jämförelse. Varianter får egna scenario-ID:n. En repetition får nytt kör-ID och samma scenario, seed, startbild och beslut. Jämför normaliserade ekonomiska poster på affärsnycklar. Slumpade interna UUID:n, verkliga tidsstämplar och kör-ID:n får skilja sig. Projektets backupmanifest och kontrollsummor är förebilder. Återställningsskriptet för den delade databasen har ett annat mål. [Backup och återställning](../scripts/maintenance/restore_database.py)

## 5. Byggordning och prov för godkänd första månad

| Ordning | Byggdel | Klart för nästa steg när |
|---|---|---|
| 1 | S-04, avstämt startbestånd för premiedelen | Beståndet och nollsaldona i §3 har en version och en granskad kontrollsumma. Ett extra öppet underlag stoppar starten. Fullt ingående bolag återstår. |
| 2 | S-05, isolering och köridentitet | Två försök kan starta från samma bild med olika kataloger. En koppling till delad demo eller Lakebase avvisas före första skrivning. |
| 3 | S-01, affärskalender | Datumen i §4 kan köras oberoende av datorns datum. Två samtidiga lokala körningar på olika affärsdagar påverkar inte varandra. |
| 4 | S-02, scenario och fryst facit | Manifestet binder ordning, beroenden, en arbetsgivare, två löner, betalningsbeteende, seed och förväntade belopp. Frys S-06:s förväntningar före första körning. |
| 5 | S-03 och återstående S-05, motparter och beslut | Filerna når A:s ordinarie tjänsteingång. Avslag, inaktuell granskning, dubbelklick och avbrott efter affärsskrivning kan provas. |
| 6 | S-06, utvärdering och reproduktion | Alla tillämpliga prov nedan passerar i varje relevant variant. Rapporten särskiljer godkänt, underkänt och ej prövat. |

Följande åtta prov konkretiserar processöversiktens §6. Ett korrekt avslag eller ett väntat öppet ärende kan vara ett godkänt affärsutfall.

1. **Startläge.** Matcha 1 arbetsgivare, 2 försäkrade, 2 behöriga mottagare samt samtliga nollvärden i §3. Kontrollera startbildens hash före och efter varje försök. Fribrev, pensionsskuld och äldre öppna fakturor är utanför detta delprov.
2. **Kalender och mandat.** Före filbeslut ska antalet registrerade löner, premier och fakturor vara 0. Omstart i vänteläget ska ge samma fil och affärsdag. Föråldrad granskningssumma, obehörig agent och konkurrerande beslut ska ge 0 extra affärseffekter. Efter ett giltigt ja ska det finnas 2 löner, 2 premierader och 1 faktura.
3. **Spårbarhet.** Båda fakturaraderna ska gå att följa från scenariohändelse via fil och rad, löneversion, beräkningsgrund, uttagsdel och handläggarbeslut till faktura/OCR och bankallokering. Knyt tjänstens `run_id` och logg till körjournalens steg. Krav: 2 av 2 kompletta kedjor och kvitto för varje mottagen händelse.
4. **Öresavstämning.** För varje variant ska bank = radallokeringar + avstämningskonto och nettofakturerat − radallokeringar = öppna fordringar. Jämför hela den isolerade databasens `get_receivables` och de individuella raderna med §3. Godkänt kräver 0,00 kr rest i båda likheterna och exakt rätt belopp och status på varje rad.
5. **Idempotens.** Återleverans före och efter omstart ska lämna 1 unik bankhändelse och 2 radallokeringar för samma fullbetalning. Prova också ändrat innehåll med samma ID och två betalningar med olika ID:n enligt §3. Vid avbrott efter lyckad bankimport ska exakt samma saldon återfinnas.
6. **Avvikelser och frister.** Verifiera delbetalningens rest och rätt ärendedagar enligt §4. Prova avslag med motivering separat. Vid okänd OCR ska hela provbetalningen på 6 733,13 kr gå till avstämningskontot, fordran vara 6 733,13 kr och exakt ett `payment_unmatched` öppnas vid intaget. Operatören ska kunna lämna posten öppen för utredning.
7. **Rapport.** Frys perioden, sista händelsen, källsummor, referenser, saldon, öppna och avslutade ärenden samt antalet granskningar, avslag och återleveranser. Visa faktisk aktiv tid och väntetid var för sig. Modellanrop = 0 och modellkostnad = 0 USD i den deterministiska körningen. Agentkvalitet, kapital, garanti, FTA, portfölj och huvudbok märks *ej prövat*. Lägg decemberutfallet i ett daterat tillägg.
8. **Omkörning och oberoende.** Kör varje betalningsförlopp två gånger från samma startbild med samma beslut. Kräv identiska affärsnycklar, belopp, frister och ärendeutfall mot det låsta facitet. Protokollet anger Git-revision, regel- och parameterversion, data-, scenario-, simulator- och facitversion samt om modell och instruktioner använts. Ändra en förväntad rad med ett öre i en separat negativ kontroll: verifieraren ska underkänna körningen och peka ut raden. Verifieraren och granskaren läser det oberoende beloppsfacitet. Drivaren läser scenariots händelser och motpartsindata.

## 6. Konkreta beroenden till Claude och den hela månaden

| Gränsyta | Ägare och samordning |
|---|---|
| Premieförlopp, förmån och mottagande uttagsdel | Claude äger hela B. Jämförelsen mot `claude/paket-b-steg-4-pension-cd2841` (`b980252`) visar en faktisk ändring i `premium_basis._recipient`: en beslutad primär mottagare kan väljas efter delning. Även `ledger_premiums` ändras för beslutad plan. C:s scenario med en enda mottagare anropar A:s publika tjänst. Efter att B mergats provas samma facit på den gemensamma versionen. Deluttag och planbyten kräver B:s färdiga kontrakt och egna facit. |
| Mottagna premier och bokningsmånad | Överlämningen omfattar allokerings-ID, bankhändelse, faktura/rad, premie, försäkring/förmån, mottagande del, ursprunglig premieperiod, mottagningsdag och belopp. A:s allokeringar är källan även när status är `invoiced`. Oallokerade pengar följer avstämningskontot. B äger `preview_ledger_premiums`, journalföring, värdedatum och sena mottagningar enligt B-047/B-050. A:s `export_premium_month` har ett särskilt gränssnitt mot det syntetiska försöket P6-MANAD-001 med granskat oktober-IB. Det är inget villkor för första C-körningen. [Export](../src/services/operations/premium_export.py) · [Operativt premieintag i B](../src/services/ledger_premiums.py) |
| Kalender och stängning | C:s frysta novemberprotokoll avser premiefordringar och bank. B äger ordningsföljden i PR-020, AVK, verklig stoppunkt, hashbunden stängning och rättelse. Steg 1–3 finns på basrevisionen. För en gemensam månad behövs B:s färdigverifierade öppningsjournal, plan/start, rättigheter, skatt, utgående bankuppdrag och kvitton, paus/återstart samt dödsfall/slutavräkning. Inkommande premiekvitto i C och bankens svar på ett pensionsuppdrag har olika identiteter. |
| Fullt bolag och övriga producenter | S-04 för hela bolaget kräver även fribrev, pensionsfall, ingående skulder/fordringar, historiska garantier, kassa, portfölj och eget kapital. B levererar operativa pensions- och kapitalposter. Portfölj/likviditet förutsätter projekt 5, bokföring, bokslut och aktuariell förklaring projekt 6. Kund- och rapportmottagare behöver egna kontrakt, beslut och kvitton. Dessa led redovisas med egen acceptans när ansvariga producenter finns. [Paket B:s designstopp](../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md) |

Inför implementation jämförs på nytt ändringar i premiemottagare, kalender, tjänsteregister och testkatalog med Claudes aktuella branch. En ändring som kräver gemensamt schema eller nytt publikt kontrakt tas tillbaka till Karl före arbete där. Slutprovet för första månaden körs på den sammanslagna versionen med projektets testverktyg. [Teststrategi](teststrategi.md)

**Avstämning 2026-11-24.** B steg 5 och Claudes steg 6-branch hade samma bas `2ed556d`. Det lokala samprovet ovan använder B:s befintliga öppning, premieintag och stängning för två ej startade delar. Steg 6 tar vid ett pensionsanspråk för att hantera skatt och bankuppdrag. Sparprovet avslutas vid bokad novemberverifikation och använder A:s identitet för inkommande bankhändelse.

## 7. Designval som låg till grund för byggstarten

| Val | Rekommendation | Vad ett ja innebär |
|---|---|---|
| C1. Period och horisont | Oktoberlöner, novemberbetalning och decemberuppföljning enligt §4. | Första leveransen kan godkännas med en öppen men korrekt avstämd restfordran. |
| C2. Start och omkörning | Fryst lokal SQLite-bild med två försäkrade och ny körkatalog per försök. | Små, överblickbara kontrollbelopp och reproducerbara prov helt fristående från Lakebase. |
| C3. Styrning och beslut | En deterministisk lokal kalenderdrivare, manuell filgranskning i A och varaktig paus med avstämning mot domänkvitto. | Ingen modell behövs för baskörningen. Nya scenarier kan senare använda befintlig harness när en agent faktiskt har ett uppdrag. |
| C4. Godkänt resultat | Godkänn byggordningen och de åtta proven, inklusive låst öresfacit, förfall, avslag, överbetalning och återleverans i separat fil. | Första premiemånaden får betecknas verifierad när dess prov passerar. Full pensionsmånad, huvudbok och FTA får egna beslut och prov efter B och övriga producenter. |
