# Designstopp – paket A: från löneunderlag till mottagen nettopremie

> **ID:** P1-PREMIE-001 | **Version:** 0.1 | **Datum:** 2026-11-07
> **Status:** PA1–PA10 godkända enligt rekommendationerna av Karl i chatten
> 2026-11-07: ”Ja, godkänn alla”. Byggstart enligt §12 är därmed godkänd, med separat
> OK före varje Lakebase-ingrepp (§11). Loggat som **B-046** samma dag.
> **Byggstatus:** steg 1 (bankdagskalender och premieunderlag ur löneunderlag) byggt och
> testat lokalt 2026-11-07, se [tjänstelager §9.9](../../02_system/tjänstelager.md). Ingen schemaändring och inget i Lakebase.
> Steg 2 (filintag och granskning) byggt och testat lokalt 2026-11-07, se [tjänstelager §9.10](../../02_system/tjänstelager.md).
> Tabellen `salary_files` finns lokalt och migreras i steg 8. **Avvikelse från §4.2, godkänd av Karl i chatten 2026-11-07 (”Ja, godkänn och mergea”):** avvikelser
> utan lön eller känd person (saknad rad, okänd person, avslagen fil m.fl.) blir den nya ärendetypen
> `salary_file_deviation`, som bara handläggaren avgör. Rättelserelaterade avvikelser blir `salary_report` som i §4.2.
> Steg 3 (faktura och förfall) byggt och testat lokalt 2026-11-07, se [tjänstelager §9.11](../../02_system/tjänstelager.md).
> Tabellerna `invoices` och `invoice_lines` migreras i steg 8. **Avvikelse från §5, godkänd av Karl i chatten 2026-11-07 (”Ja, godkänn och mergea”):** inga nya
> kolumner i `premium_transactions` ännu. Fakturaraden pekar på premieraden, och en ny kolumn i modellen skulle
> göra läsningar mot Lakebase ogiltiga före migrationen. Kolumnen för löneunderlag avgörs i steg 8.
> Steg 4 (bank och matchning) byggt och testat lokalt 2026-11-07, se [tjänstelager §9.12](../../02_system/tjänstelager.md).
> Tabellerna `bank_events` och `payment_allocations` migreras i steg 8. Ett `payment_unmatched`-ärende från en
> okänd betalare saknar både försäkrad och arbetsgivare; CHECK-villkoret på `cases` tillåter det för typen
> (ny ärendetyp och lättat CHECK-villkor godkända av Karl i chatten 2026-11-07, ”Godkänn och mergea”).
> En delbetald premie som rättas går till manuell prövning i stället för kredit och ny debet.
> **Uppdrag:** [ATT_GORA, paket A](../../ATT_GORA.md#-månadssimulering--byggluckor-och-samordning)
> och raden *Kommande verksamhetsuppdrag*; gap V-01–03 i
> [processöversikten](../../01_domän/processer_översikt.md#3-gap-i-verksamhetsförmågorna).
> Karl gav uppdraget i chatten 2026-11-07.
> **Utgångspunkt:** `main` vid `e1e5dc8`, arbetsbranch `claude/paket-a-designstopp`.

## 1. Godkända val

Bygg bolagets ordinarie premieflöde, ett led i taget:

arbetsgivarens löneunderlagsfil → granskade löneunderlag → beräknade premier →
faktura per arbetsgivare och period → inbetalning från banken → matchning och
fördelning → **mottagen nettopremie per förmån**.

Flödet slutar vid ett mottagningskvitto i exakt det format som den avstämda
FTA-månaden redan tar emot ([P6-MANAD-001 §4.1](../06_avdelningsfunktioner/AVSTAMD_FTA_MANAD_DESIGNSTOPP.md#41-gräns-mot-paket-a)).
Kapitalet och garantidelarna skapas alltså av den befintliga månadsjournalen, inte av en ny
motor. Arbetsgivare och bank är simulerade motparter, men deras filer går genom
samma intag och kontroller som riktiga filer skulle göra.

| Val | Godkänt 2026-11-07 |
|---|---|
| **PA1: startperiod och historikgap** | Första operativa premieperiod blir **2026-10**. Juli–september 2026 saknar underlag och redovisas som en märkt startlucka. Ingen kontroll av saknade rapporter görs före 2026-10. Luckan kan senare köras som sen rapportering genom samma flöde (§10) |
| **PA2: intag av löneunderlag** | En fil per arbetsgivare och period valideras i betrodd kod. Handläggaren godkänner filens giltiga rader i ett hashbundet steg. Avvikande rader blir ärenden som F5-7:s arbetare och handläggaren tar hand om |
| **PA3: premieunderlag** | Vid godkännandet beräknar premiemotorn premien per person, arbetsgivare och månad. Den fördelas enligt PR-015 och sparas som rader i befintliga `premium_transactions`, med koppling till löneunderlaget. Rättelser blir länkade `adjustment`-rader |
| **PA4: faktura** | En faktura per arbetsgivare och premieperiod, med förfallodag 30 dagar och flytt till nästa svenska bankdag. Varje faktura får en OCR-referens. Rättelser ger tilläggs- eller kreditfaktura. Fakturan skapas internt; ingen extern sändning ingår |
| **PA5: bank och matchning** | En simulerad bankfil importeras. Varje inbetalning matchas på OCR och betalare och fördelas med befintlig `allocate_receipt`. Överskott och okänd referens hamnar på avstämningskonto med ett ärende till handläggaren. Ingen återbetalning i första versionen |
| **PA6: betalstatus** | Mottagningsallokeringarna är sanningskällan. `status='paid'` och `paid_date` sätts först när en premierad är fullt betald, så att befintliga läsare fortsätter att fungera |
| **PA7: överlämning till kapital/garanti** | Paket A levererar mottagningskvitton som källa till `open_premium_month`/`receive_premium_payment` i stället för syntetiska underlag. En operativ kapitaljournal hör till paket B (V-05) |
| **PA8: simulerade motparter** | En liten, separat motpartssimulator i `src/simulation/` skapar arbetsgivarfiler och bankfiler ur beståndet, med seed och uttryckliga avvikelser. Den skriver aldrig i affärstabellerna |
| **PA9: anställningar** | Första versionen behåller en anställning per person. Fall som kräver anställningshistorik blir ärenden. Tabellen `employments` byggs som eget senare steg inom V-01 |
| **PA10: byggordning och Lakebase** | Ordningen i §12, med separat OK före varje Lakebase-ingrepp (backup, torrkörning, bekräftelse att ingen annan agent kör) |

Valen är godkänd bygginriktning. De ändrar inga produktregler: PR-ITP1-013–019 är
godkända sedan 2026-11-01 (B-031). Valen ger inte heller agenter nya befogenheter
utöver dem som anges i §6.

## 2. Varför paket A nu och vad som redan finns

**Verksamhetsnytta:** Bolaget kan i dag registrera löneunderlag men inte få betalt
för dem. Utan premieflödet:

- skapar `register_salary_report` ingen premie (ATT_GORA, *Premie ur löneunderlag*);
- räknar FTA-månaden på syntetiska mottagningar;
- går ärendearbetaren med tom kö, eftersom ärenden bara kommer in när
  handläggaren registrerar dem för hand (B-043 val D).

Paket A ger alla tre ett riktigt underlag.

**Nuläge i Lakebase**, läst med skrivskyddad anslutning 2026-11-07, bara aggregat:

| Område | Läge |
|---|---|
| Premier | 15 097 rader `premium`, alla `paid`, premieperioder 2023-01–2026-06 (471 per månad på slutet), senaste `paid_date` 2026-07-15. Historiken är genererad ur aktuell lön, inte ur löneunderlag |
| Löneunderlag | 4 rader, alla för 2026-10 och verifieringspersonen (F5-5–F5-7) |
| Bestånd | 20 arbetsgivare; 471 premiebetalande och 28 fribrev; en försäkring och en förmån per person |
| Fakturor, bankhändelser, fordringar | Finns inte |
| Månadsjournal | Tabellerna `premium_month_journals`, `premium_receipts` och `premium_month_closes` är införda tomma (2026-11-03) |

**Återanvänds:**

| Del | Användning i paket A |
|---|---|
| Premiemotorn `calculate_itp1_premium` och `product_parameters` | Premie per period med periodens IBB och parameterversion (PR-001, 3c-P1) |
| `register_salary_report` och `salary_reports` | Version, rättelsekedja, källreferens och dubblettskydd per arbetsgivare finns redan |
| `correct_premium_transaction` | Länkad rättelse av ej mottagen premie och tillägg på mottagen premie; nedrättning av mottagen premie är blockerad |
| `premium_month_inputs` | `InvoiceInput`/`InvoiceLine`/`ReceiptInput`, `allocate_receipt` och idempotensnyckeln är redan kontraktet för mottagning |
| `allocate_cents` | Största bråkrest för delbetalning och fördelning (PR-015/018) |
| Tjänstelagret, godkännandekön och `operation_events` | Alla nya operationer läggs här med åtkomstrad, transaktion och händelselogg (B-028) |
| Ärenden, ärendearbetaren och handläggaragenten | Avvikelser blir ärenden; F5-7 väljer dem enligt policyn (B-033, B-043) |
| Flödesmotorn | Hashbundet godkännande av en fil med samma mönster som grindarna (3c-2) |

## 3. Omfattning

**Ingår:**
- ordinarie ITP1-premie för premieperioder från 2026-10;
- löneunderlag per arbetsgivare och period, med uttrycklig noll, saknad rad,
  dubblett och rättelse;
- fakturering, förfall, påminnelseärende och eskalering enligt PR-017;
- inbetalning, matchning, delbetalning, överbetalning och okänd referens enligt PR-018;
- överlämning av mottagen nettopremie till den befintliga månadsjournalen;
- en minimal motpartssimulator för arbetsgivare och bank.

**Ingår inte**, och var det hör hemma:

| Utanför | Var |
|---|---|
| Kompletterande och externa premier (PR-016), löneväxling | Senare steg i paket A, med signerad instruktion |
| Återtag av mottagen premie och återbetalning till betalare (PR-019 p. 3–4) | Kräver kapitalspår och rättslig prövning; paket B |
| Operativ kapitaljournal, avkastning, avgift, skatt och pensioner (V-04–06) | Paket B |
| Bokföring, kundfordringar i huvudbok, månadsbokslut (V-10) | Projekt 6 |
| Placering av inbetalda medel, likviditet och portfölj | Projekt 5, pausat; pengarna stannar på det simulerade bankkontot |
| Anställningshistorik (`employments`), återanställning, flera arbetsgivare | V-01, eget steg (PA9) |
| Extern sändning av faktura eller påminnelse och kundbrev (V-09) | Kommunikationsflödet; kräver mänskligt godkännande (§3.5) |
| Simuleringsklocka, scenariomotor och full månadssimulator (S-01–06) | Paket C |

## 4. Flödet steg för steg

Varje steg sker genom tjänstelagret. Inget steg ändrar data direkt från webben,
agenten eller simulatorn.

### 4.1 Löneunderlagsfil (PR-014, PR-013)

Arbetsgivaren lämnar en fil per period, med en rad per anställd och period:
personnummer, utbetalningsmånad, pensionsmedförande lön efter löneväxling,
radtyp (`new` eller `correction`) och vid rättelse den rättade versionen. Filen har
arbetsgivarens organisationsnummer, sin egen referens, en mottagningsdag och en
kontrollsumma över innehållet.

`import_salary_file` validerar filen i betrodd kod utan att registrera något:

- **Giltiga rader:** personen är ansluten hos arbetsgivaren, månaden ligger inom
  anställningen eller är dess avslutsmånad, lönen är noll eller större, och ingen
  version finns redan för samma person, arbetsgivare och månad.
- **Avvikande rader:** okänd person, annan arbetsgivare, månad utanför
  anställningen, negativ lön, en `new` som redan finns, en rättelse utan grundrad,
  eller en dubblettrad i filen.
- **Saknade rader:** premiebetalande personer hos arbetsgivaren som inte finns i
  filen. Kontrollen görs bara för perioder från 2026-10 (PA1). Uttrycklig noll
  är en giltig rad, inte en saknad rad (PR-014, PR-017).

Samma filreferens med samma kontrollsumma ger samma intagskvitto. Samma referens
med ändrat innehåll ger konflikt och stopp. En korrigerad fil får en ny referens
och hanteras som rättelser.

### 4.2 Granskning av filen (PA2)

Handläggaren ser filens sammanställning: antal rader per utfall, lönesumma,
förhandsberäknad premiesumma och varje avvikelse med skäl. `approve_salary_file`
binder den kontrollsumma handläggaren såg, på samma sätt som flödesmotorns grindar.
Ändrat underlag mellan visning och godkännande stoppar åtgärden.

Vid godkännandet, i en transaktion:
1. registreras varje giltig rad med befintliga `register_salary_report`
   (källa `employer`, filens referens och radens nummer som källreferens);
2. skapas premieunderlaget enligt §4.3;
3. skapas ett ärende `salary_report` per avvikande eller saknad rad, med filen
   som ursprung (§8).

Avslag av hela filen registrerar ingenting och skapar ett ärende för uppföljning
med arbetsgivaren. Någon extern sändning sker inte.

### 4.3 Premieunderlag (PR-001, PR-015, PR-013, PA3)

För varje registrerad rad beräknas ordinarie premie **en gång** per person,
arbetsgivare och månad, med periodens IBB och parameterversion. Utanför
åldersfönstret blir premien noll (25-årsmånaden till och med månaden före 66).
Premien fördelas på personens ännu inte startade premiedelar enligt PR-015. I dag
har varje försäkring en förmån, så den blir ensam mottagare med vikt 1. Finns
ingen behörig mottagare stoppas raden och blir ett ärende. Den fördelas inte lika av misstag.

Resultatet sparas som en `premium`-rad per förmån och månad i `premium_transactions`,
med `status='pending'`. `calculation_basis` kompletteras med löneunderlagets id och
version, filens referens och PR-paketets version. Noll premie sparas som underlag
men ger ingen fakturarad.

Rättelse av löneunderlaget räknar om just den ursprungliga månaden med dess IBB
(PR-019 p. 1). Skillnaden blir en länkad `adjustment`-rad med befintlig rättelselogik:
- **Inte fakturerad:** underlaget rättas före faktureringen.
- **Fakturerad men inte betald:** gamla raden krediteras och den nya debiteras (PR-017).
- **Betald, rättning uppåt:** tilläggspremie på en ny faktura. Ny garanti uppstår
  först när tillägget är mottaget.
- **Betald, rättning nedåt:** blockeras och blir ett ärende för handläggaren.
  Återtag ingår inte (PR-019 p. 3).

### 4.4 Faktura (PR-017, PA4)

`create_invoice` samlar arbetsgivarens öppna premieunderlag för en premieperiod:
ordinarie rader, tillägg och krediter redovisade var för sig, med försäkring,
förmån, period och rättelselänk per rad. Förmånen identifierar personen, men
personnumret står inte på fakturan.

- **Fakturadatum:** dagen då fakturan skapas. **Förfallodag:** fakturadatum plus 30
  kalenderdagar, flyttad till nästa svenska bankdag. Bankdagskalendern byggs som en ren
  funktion för svenska helgdagar, midsommarafton, julafton och nyårsafton. Den är
  första delen av S-01.
- **OCR-referens:** unik per faktura, med kontrollsiffra enligt modulus 10.
- **Rader:** ordinarie premie och tillägg är positiva fakturarader. En kredit är en
  egen kreditfaktura som avräknas separat (PR-018). Fakturan kan exporteras som
  `InvoiceInput` med bunden källa och kontrollsumma, och då får månadsjournalen
  exakt samma innehåll.
- **Status för premieraderna:** `invoiced`. En faktura ändras aldrig efter
  skapandet; omfakturering sker med kredit och ny debet.

Saknade eller avvikande rader stoppar inte fakturan för de rader som är oberoende
och korrekta. Avvikelsen och en senare tilläggsfaktura ska synas (PR-017).

### 4.5 Förfall och påminnelse (PR-017)

Bevakningen körs dagligen som ett systemsteg. Det kan ske i ärendearbetarens
befintliga varv eller i ett eget `--once`-steg; valet görs vid bygget utan ny schemaläggare.

- **1 dag efter förfallodagen:** ärende `payment_overdue` till handläggaren med
  faktura, belopp och dagar.
- **30 dagars dröjsmål:** samma ärende eskaleras till operatören.
- Ingen påminnelseavgift och ingen dröjsmålsränta tas ut.
- Förfallna premier är fordringar, inte kapital. Ingen uppsägning, inget
  pensionsstopp och ingen ändring av redan intjänad garanti.

### 4.6 Inbetalning och matchning (PR-018, PA5)

`import_bank_file` läser en simulerad bankfil med inbetalningar. Varje händelse har
bankens händelse-ID, mottagningsdag, belopp, betalarens organisationsnummer och
angiven referens. Händelsen sparas en gång per bankens identitet. Samma händelse i en
ny fil ger samma kvitto, och samma identitet med ändrat innehåll ger konflikt.

Matchningen sker deterministiskt i samma transaktion:
1. OCR-referensen pekar ut fakturan, och betalaren ska vara fakturans arbetsgivare.
2. Nettot fördelas på fakturans återstående positiva rader med `allocate_receipt`:
   proportionellt efter återstående belopp, med största bråkrest och stabil radordning.
3. Belopp över fakturans återstående belopp, okänd referens och fel betalare blir
   en **oallokerad post** på avstämningskontot. Den får ingen kapital- eller garantieffekt,
   och ett ärende `payment_unmatched` skapas till handläggaren.
4. Intern simulering har ingen valcentral: brutto = netto och externt avdrag = 0 (PR-018).

`allocate_unmatched_payment` låter handläggaren fördela en oallokerad post till rätt
faktura när betalaren är verifierad. Operationen är `HUMAN_ONLY`. Återbetalning är
en extern handling och ingår inte i första versionen.

### 4.7 Mottagen nettopremie och överlämning (PA6, PA7)

Varje allokering är ett mottagningskvitto med fakturarad, förmån, ursprunglig
premieperiod, mottagningsdag, värdedatum (mottagningsmånadens slut) och belopp.
När en premierad är fullt betald sätts `status='paid'` och `paid_date` (sista
mottagningsdagen). En delbetald rad behåller `invoiced`, och dess mottagna del finns
i allokeringarna.

För en premiemånad exporteras perioden som ett källpaket till befintliga
`open_premium_month`: fakturor som `InvoiceInput` och inbetalningar som `ReceiptInput`,
märkta som simulerad motpart men inte som syntetiska facit. Därefter skapar
månadsjournalen kapitalursprung och garantidel på mottagningsmånadens tariff
(PR-018, PR-020 steg 4). Paket A skapar alltså ingen garanti och ändrar inget kapital.

## 5. Datamodell – verksamhetsinnehåll

Detta är kontraktsinnehåll, inte SQL. Alla belopp är i hela ören och alla
poster är oföränderliga. Rättelser är nya, länkade poster.

| Ny tabell | Innehåll |
|---|---|
| `salary_files` | Arbetsgivare, period, arbetsgivarens referens, mottagningsdag, innehåll och kontrollsumma, valideringsresultat, status (`received`, `approved`, `rejected`), granskare och tidpunkt |
| `invoices` | Arbetsgivare, premieperiod, typ (`debit`, `credit`), OCR, fakturadatum, förfallodag, summa, länk till krediterad faktura, kontrollsumma |
| `invoice_lines` | Faktura, premierad (`premium_transactions.id`), förmån, försäkring, period, belopp, radtyp (ordinarie, tillägg, kredit) |
| `bank_events` | Bankens händelse-ID, källfil och kontrollsumma, mottagningsdag, belopp, betalare, angiven referens; unik på källsystem och händelse-ID |
| `payment_allocations` | Bankhändelse, fakturarad eller avstämningskonto, belopp, fördelningsgrund och version, aktör, idempotensnyckel |

**Ändring av befintlig tabell:** `premium_transactions` får nullbara kolumner för
löneunderlag (`salary_report_id`) och fakturarad. Historiska rader lämnas orörda
och får ingen konstruerad faktura. Statusvärdena finns redan.

**Påverkan på befintliga läsare:**
- OC-3a:s mått *Registrerat betalda premier* summerar rader med `status='paid'`. Med
  PA6 behåller det sin betydelse, fullt betalda rader. Delbetalningar syns först i ett
  senare mått för mottagen nettopremie, som projekt 2 äger.
- Översiktens kapital är i dag summan av betalda premier (V-05). Det förblir en
  förenkling tills paket B.
- Datakontraktet för frågekedjan ändras inte i detta steg.

## 6. Operationer och åtkomst

| Operation | Typ | Agentnivå | Kommentar |
|---|---|---|---|
| `import_salary_file` | skrivning, PII | HUMAN_ONLY | Sparar fil och valideringsresultat, registrerar inga löner |
| `approve_salary_file` | skrivning, PII | HUMAN_ONLY | Hashbundet; registrerar rader, premieunderlag och avvikelseärenden |
| `reject_salary_file` | skrivning | HUMAN_ONLY | Med skäl; ingen registrering |
| `create_invoice` | skrivning | HUMAN_ONLY | Även systemsteg efter godkänd fil |
| `import_bank_file` | skrivning | HUMAN_ONLY | Även systemsteg; matchar i samma transaktion |
| `allocate_unmatched_payment` | skrivning | HUMAN_ONLY | Verifierad betalare krävs |
| `check_overdue_invoices` | skrivning (ärenden) | HUMAN_ONLY | Systemsteg dagligen |
| `get_salary_file`, `list_invoices`, `get_invoice`, `get_receivables` | läsning | AGENT för aggregat utan PII; HUMAN_ONLY för individrader | Poddmontering prövas när ett agentuppdrag behöver dem |

Alla skrivande operationer är `HUMAN_ONLY` för agenter i första versionen. Agenten
arbetar i de ärenden som uppstår, med befintliga verktyg (§8). Agenter föreslår
inga fakturor eller betalningar. Systemaktörens steg körs i betrodd kod och skrivs
i `operation_events` som `system`, på samma sätt som `case_worker`.

`create_case` är i dag `HUMAN_ONLY`. Avvikelseärenden från filintaget och
bevakningen skapas av betrodd kod som systemaktör i samma transaktion som sitt ursprung.
Det är en ny systemväg att granska vid bygget, inte en agentbefogenhet.

## 7. Normal- och avvikelsefall för verifiering

Beloppen gäller premieperiod 2026-10, IBB 83 400 kr och dagens produktparametrar.
De är kontrollerade med premiemotorn och `allocate_cents`.

| # | Fall | Väntat utfall |
|---|---|---|
| 1 | Lön 45 000 kr, full betalning | Premie 2 025,00; fakturarad 2 025,00; kvitto 2 025,00; raden `paid` |
| 2 | Lön 60 000 kr | Premie 4 708,13 (2 345,63 + 2 362,50) |
| 3 | Uttrycklig lön 0 kr | Premieunderlag 0,00, ingen fakturarad, inget saknad-ärende |
| 4 | Premiebetalande person saknas i filen | Ärende för saknad rapport; ingen premie och inget antagande om förra månadens lön; övriga rader faktureras |
| 5 | Okänd person eller annan arbetsgivare | Avvikande rad, ärende, ingen registrering |
| 6 | Samma fil igen | Samma intagskvitto, inga nya poster |
| 7 | Samma filreferens med ändrat innehåll | Konflikt, inget registreras |
| 8 | Rättelse 45 000 → 50 000 före fakturering | Underlaget rättas till 2 250,00 |
| 9 | Samma rättelse efter fakturering men före betalning | Kreditfaktura 2 025,00 och ny debet 2 250,00 |
| 10 | Samma rättelse efter full betalning | Tilläggsfaktura 225,00; ny garanti först när tillägget är mottaget |
| 11 | Rättelse nedåt efter betalning | Blockeras, ärende till handläggaren, ingen effekt |
| 12 | Faktura med 2 025,00 och 4 708,13 (6 733,13); inbetalning 4 000,00 | Allokering 1 203,01 och 2 796,99; öppen fordran 2 733,13; raderna förblir `invoiced` |
| 13 | Inbetalning 7 000,00 på samma faktura | 6 733,13 allokeras; 266,87 till avstämningskontot och ärende |
| 14 | Okänd OCR eller fel betalare | Hela beloppet till avstämningskontot och ärende; ingen garanti |
| 15 | Samma bankhändelse i två filer | Ett kvitto; ingen dubbel allokering |
| 16 | Fakturadatum 2026-11-25 | Förfallodag 2026-12-28 (25–27 december är inga bankdagar) |
| 17 | Ingen betalning 1 respektive 30 dagar efter förfallodagen | Påminnelseärende och därefter eskalering; fordran kvar; ingen garanti; inget pensionsstopp |
| 18 | Person i 66-årsmånaden | Premie 0,00 (PR-013) |
| 19 | Slutlön i avslutsmånaden efter avanmälan | Registreras om befintlig anställningskontroll godtar den; annars ärende (PA9) |
| 20 | Export av period 2026-10 till månadsjournalen | `open_premium_month` godtar källpaketet; journalens kvitton motsvarar allokeringarna exakt i ören |

Acceptans för hela leveransen:
- Summan av allokeringar och oallokerade poster är lika med summan av bankhändelser.
- Fakturornas summa minus allokerat är lika med öppna fordringar.
- Varje premie går att spåra till löneunderlag, fil, regel och parameterversion.
- Inget fall ger dubbel ekonomisk effekt.

## 8. Människans och agentens arbetsväg

**Handläggaren:**
- granskar och godkänner varje löneunderlagsfil;
- skapar fakturor och importerar bankfiler;
- avgör avvikelser och oallokerade inbetalningar;
- följer upp förfallna fakturor.

Ny sida i handläggar-UI:t: *Premier och betalningar*, med filer, fakturor,
inbetalningar och avstämningskonto. Den följer Digital klarhet.

**Handläggaragenten** arbetar i de ärenden som uppstår, på samma sätt som i dag.
Arbetsgivarens rättelser i en fil blir `salary_report`-ärenden. B-043:s urval
väljer dem redan, och agenten förbereder förslaget med befintliga verktyg; varje förslag
granskas. Saknade rader, betalningsärenden och avvikelser som kräver kontakt
med arbetsgivaren går till handläggaren. Extern komplettering är inte byggd.
Därmed får F5-7 riktiga ärenden utan att agentens mandat vidgas.

**Operatören (Karl)** godkänner designen och varje Lakebase-ingrepp och tar emot
eskaleringar efter 30 dagar. Månadens granskning sker genom befintlig
`approve_premium_month`.

## 9. Simulerade motparter (PA8)

En minimal simulator i `src/simulation/`, skild från verksamhetskoden, skapar
filer som om de kom utifrån:

- **Arbetsgivarfil per period:** utgår från beståndets aktuella lön, med
  seedbunden variation och uttryckliga avvikelser i ett scenario, till exempel en
  saknad rad, en nolla, en rättelse eller en okänd person.
- **Bankfil:** arbetsgivarens betalningsbeteende per scenario, till exempel betalar
  i tid, delbetalar, betalar sent, anger fel OCR eller betalar två gånger.

Simulatorn läser bara beståndet och skriver bara filer. Filerna lämnas till
`import_salary_file` och `import_bank_file` som vilken fil som helst. Varje fil
märks med simulatorns version och seed. Facit för verifieringen hålls separat från
affärstabellerna, enligt processöversikten §4. Det här är den första avgränsade delen av S-02 och S-03.
Ingen inbyggd demoknapp införs (B-037).

## 10. Startläge och historikgap (PA1)

Den genererade historiken slutar med premieperiod 2026-06. Det finns inga premier
eller löneunderlag för juli–september 2026, utom verifieringspersonens oktober.
Den avstämda S-04 per oktober, som FTA-månaden bygger på, utgår från den historiken.

**Rekommendation:** starta det operativa flödet med premieperiod 2026-10.
- Juli–september redovisas som en uttrycklig startlucka i simuleringen, i
  premieöversikten och i månadsjournalens manifest. Ingen premie konstrueras för dem.
- Kontrollen av saknade rapporter gäller först från 2026-10. Annars skulle 471
  personer ge tre saknad-ärenden var direkt.
- Luckan kan senare köras som **sen rapportering** genom samma flöde. Det är ett
  bra prov på PR-018: premieperioden styr IBB och trappa, mottagningen styr tariffen,
  och ingen retroaktiv avkastning ges.

**Alternativ:**
- Fyll juli–september med generatorn som historik. Det ändrar den avstämda S-04
  och blandar facit med affärsdata.
- Kör juli–september genom flödet nu. Då blir det tre extra filomgångar innan
  oktober fungerar.

## 11. Lakebase

Inget i detta designstopp skriver till Lakebase. När bygget är verifierat lokalt
och i `svc_test`:

1. Ta backup och torrkör migrationen för de fem nya tabellerna och de två nya
   kolumnerna. Bekräfta att ingen annan agent kör mot databasen (AGENTS.md §4.5).
2. Efter separat OK: skapa tabellerna tomma och kontrollera att övriga radantal är oförändrade.
3. Efter ytterligare OK: kör första operativa perioden 2026-10 med simulerade filer
   för en eller ett par arbetsgivare och kontrollera fallen i §7 i skrivskyddad läsning.

Agentrollerna får inga rättigheter på de nya tabellerna i första versionen.

## 12. Föreslagen byggordning

Ett bygge i taget. Varje steg ska vara testat och fungera innan nästa börjar.

1. **Bankdagskalender och premieunderlag:** helgdagsfunktionen, premie ur
   registrerat löneunderlag (PR-001/013/015) och rättelselänk. Fall 1–3, 8, 18.
2. **Filintag och granskning:** `salary_files`, validering, hashbundet godkännande
   och avvikelseärenden. Fall 4–7, 19.
3. **Faktura och förfall:** `invoices`, `invoice_lines`, OCR, kredit och tillägg samt
   förfallobevakning. Fall 9–11, 16–17.
4. **Bank och matchning:** `bank_events`, `payment_allocations`, avstämningskonto
   och manuell fördelning. Fall 12–15.
5. **Motpartssimulatorn** (PA8) och hela kedjan i demo och `svc_test`.
6. **Överlämning till månadsjournalen:** export till `open_premium_month`. Fall 20.
7. **Handläggarsidan** *Premier och betalningar* med webbkontroll.
8. **Lakebase** enligt §11, med separat OK för varje steg.

Postgres-prov körs där ändringen kräver det (B-040). Steg 1–4 kan delas mellan
Claude och Codex först när kontrakten i §5 är fastställda. De delar datamodell
och får inte byggas parallellt utan avstämning (AGENTS.md §4.2).

## 13. Öppna frågor till bygget

- **Systemaktörens ärendeskapande:** en granskad systemväg för `create_case` från
  intaget och bevakningen (§6). Behöver bekräftas i åtkomstregistret och
  tjänstelagrets dokumentation.
- **Fakturans bevakningsvarv:** i ärendearbetarens befintliga `--once` eller ett eget
  systemsteg i samma schemauppgift. Ingen ny schemaläggare.
- **Lön och anställning:** `insured_persons.monthly_salary_sek` är aktuell lön.
  Ska ett godkänt löneunderlag uppdatera den? Förslag: nej, de är olika begrepp
  (ATT_GORA, *Lönehistorik för aktuell lön*).
- **Mått för mottagen nettopremie:** projekt 2 avgör namn och definition innan
  centralen visar delbetalningar.
- **Beslutslogg:** loggat som B-046 efter Karls OK 2026-11-07.
