# Leveranskontroll – produktpaket PR-ITP1 v1.0

> **Kontrolldatum:** 2026-10-11 | **Status:** Dokumentmodell och räkneexempel kontrollerade.
> Detta är ingen verifiering av implementerad regelkod, databas eller verklig bolagstariff.

## 1. Täckning och läsordning

[Villkor v2.0](../../01_domän/försäkringsvillkor.md) →
[regelkatalog](../../01_domän/produktregler/README.md) →
[aktuariell grund](../../01_domän/aktuariell_grund.md) →
[parametrar](../../01_domän/parametrar/PARAMETERREGISTER.md).
Käll-ID och tolkning/villkorskoppling finns i varje PR-fil.

| Produktområde | Villkor | Produktregler | Tolkning |
|---|---|---|---|
| Produkt, parter, tillhörighet | §1–2 | 012 | T-006/008 |
| Lön, ålder, trappa | §3 | 001, 013–014 | T-001/006 |
| Komplettering och extern premie | §3 | 016 | T-006 |
| Faktura, allokering, netto, rättelse | §4/13 | 015, 017–019 | T-006/008 |
| Avkastning, kostnad, kapital, skatt | §5 | 020–023 | T-004/007 |
| Intjänad garanti och finansiering | §6 | 008, 028 | T-004 |
| Fribrev och ny premie under pension | §7 | 013, 018, 025 | T-002/006 |
| Start, uppskov, deluttag | §8 | 002–003, 024–025 | T-002 |
| Tid och pensionsbelopp | §9 | 006, 009 | T-003/004 |
| Paus, återstart, förlängning | §10 | 004–005, 007 | T-002/003 |
| Bank, inkomstskatt, sista rätt | §11 | 026–027 | T-003/007 |
| Dödsfall och faktisk arvsvinst | §12 | 010–011 | T-005 |
| Förfoganden/rättelser | §13 | 019, 033 | T-008 |
| Besked, data och produktstyrning | §14 | 029, 031, 034 | T-008/010 |
| Ändring, klagomål, tvist | §15 | 030 | T-008 |
| Giltighet och historia | §16 | 032 | T-009 |

Alla 34 PR-ID och tio T-ID finns. Reglerna täcker premiefria perioder,
uppskjuten/påbörjad/pausad pension och betalningshinder separat.
Ett manuellt utfall är definierat för okända externa beslut; det är inte
en fri möjlighet att göra undantag från lag eller ett lämnat produktval.

## 2. Datakälla och numerisk metod

[Dödlighetstabellen](../../01_domän/parametrar/DODLIGHET_SCB_2025.md)
har 101 åldersrader 0–100, män/kvinnor och innehållskod **BE0101A¤**.
API-urval och enhet finns i filen. BE0101AW är risktid, inte dödsrisk.
En ny API-jämförelse 2026-10-11 verifierade samtliga 202 sparade tal
och SCB:s innehålls-/åldersbeteckning utan avvikelser. Källan har även
101–110; den valda modellgränsen 100 är uttrycklig, inte en saknad rad.

SHA256 för hela tabellfilen, UTF-8 utan BOM och normaliserade LF-radslut:

`d0b6872d317b975cdec57f09cd66afb65c5365000f3f5cc253889a785d31dd5d`

Räkneexemplen beräknades i en fristående tillfällig månadsberäkning,
utan ny produktionskod eller tester i repot. Ålder vid första dagen,
kalenderårsvis förbättring, månatlig överlevnad, 0 % ränta och svansens
exakta geometriska summa följer aktuariell grund. Kontrollpunkterna är
första månadens vikt=1, positiv/ändlig A, full bevarad garantivärdering och
att ingen faktisk kund avslutas vid tabellens högsta ålder.

## 3. Resultat med vald SIM-grund

Person född **1960-11-01**, värdering **2026-10-31**, första rätt
**2026-11**, SIM-G/B-2026-01. Ingen väntetid i första exemplet.
Belopp/faktorer nedan visar avrundade resultat; mellanvärden behöll hög precision.

| Beräkning | Resultat |
|---|---:|
| SIM-R årlig dödsrisk, ålder 66 år 2026 | 0,710185 % |
| SIM-G/B månadsrisk november 2026 | 0,0474694047 % |
| A för 60 livsberoende månadsrätter | 59,019956697 |
| A för livsvarigt | 293,440405905 |
| G för 100 000 kr och 60 månaders plan | 1 694,34 kr/mån |
| G för 100 000 kr och livsvarig plan | 340,78 kr/mån |
| Livsvarig A, ytterligare 20 % lägre dödlighet med omräknad svans | 316,675957776 |

G-raderna visar grundens högprecisionsbelopp avrundat för läsning.
Det utbetalningsbara garantigolvet är 1 694,35 respektive 340,79 kr/mån
enligt PR-009:s uppåtrundning. Detta får inte blandas med internt G.
Sextiomånadersfaktorn är mindre än 60 och större än noll.
Ett förenklat exempel med A=60 får inte ersätta denna tariff.
Livsvarigt stressvärde för internt G blir cirka 107 918,32 kr, över C=100 000.
Med öresgolvets buffert blir värdet cirka 107 920,00 kr.
Det visar att PR-028:s bolagsbuffert faktiskt behövs. Med enda pågående
belopp 340,79 blir minsta initiala scenariobuffert cirka 12 009,48 kr
enligt den valda gap- plus tolvmånadersformeln. Detta är inte bevis på solvens.

Efter **12 förbrukade rättigheter**, värdering 2027-10-31:

| Ändring av ursprunglig 60-månadersplan | Faktor/värde |
|---|---:|
| Gamla 48 kvarvarande rättigheter från 2027-11 | A = 47,316383622 |
| Kvarvarande garanti med oförändrad historisk grund | V_g = 80 170,14 kr |
| Förlängning till totalt 120 rättigheter, 108 kvar | A = 103,923811079 |
| Ny garantipension vid förlängningen | G = 771,43 kr/mån |
| Tre månaders paus, återstart 2028-02, fortsatt 48 kvar | A = 47,223338160 |
| Omräknad garanti vid den pausplanen | G = 1 697,68 kr/mån |

Båda omräkningarna bevarar V_g när faktorerna multipliceras med de nya,
oavrundade garantibeloppen. Pausen förbrukar inte tre rättigheter.
Den lilla ökningen beror på uppskjutet livsberoende kassaflöde,
inte konstruerad avkastning eller ny premie. Total M prövas dessutom mot PR-009.

För person född **2001-11-01**, nettopremie 1 000 värderad **2026-11-30**,
referensstart **2067-11**: A = 347,157063780 och G ≈ 2,880540552 kr/mån.
Referensfaktorn inkluderar överlevnad under hela väntetiden, inte bara tiden
efter pensionering. Den ger inget utbetalt belopp vid 25.

## 4. Pengar, månader och undantag

| Kontroll | Förväntat dokumentutfall |
|---|---|
| L=52 125 år 2026 | Delavrundad ordinarie premie 2 345,63 |
| L=52 125,05 | 2 345,65; hög/låg del avrundas separat |
| L=80 000 | 10 708,13 |
| L=208 500 respektive 250 000 | Båda 49 258,13; taket stoppar extra ordinarie premie |
| IBB 2023 | Exakt B1=46 437,50 före avrundning |
| Två försäkringar, 60/40 av 10 708,13 | 6 424,88 + 4 283,25 = 10 708,13, en trappa |
| Pool 0,02, tre lika vikter | 0,01/0,01/0,00 med stabil ID-ordning |
| C0=100 000, r=1 %, premie=1 000, rätt=2 000, arvsvinst=90 | C_slut=100 043,83 efter avgift 16,67/skatt 29,50; skuld 2 000 separat |
| Ny premie under månaden | Ingen avkastning den mottagningsmånaden; inte infogad i pågående ändlig plan |
| C=1 000, dödsmånadsrätt 100 ej debiterad | Skuld 100, pool 900 |
| C=900, samma rätt redan debiterad | Pool 900, skulden kvar; ingen andra kapitaldebit |
| C=80, rätt 100 | Bolagskapital −20, finansierad pension 100; ingen skapad tillgång |
| Sista tidsbegränsade rätt, M=100 och C=140 efter kostnader | En ordinarie sista rätt 140; C=0 och ingen ny poolandel |
| 60 rättigheter från 2026-11 utan paus | Sista rätt 2031-10 |
| Samma plan med tre pausmånader efter tolv rättigheter | 48 kvar, sista rätt 2032-01 |
| Förlängning till totalt 120 efter tolv rättigheter | 108 kvar, sista rätt 2036-10 |
| Bankavvisning/okänd status | En skuld; avstämning före nytt försök, inget nytt N-avdrag |
| Svensk sidoinkomst 1 001,50, inget undantag | Avdrag 300 kr, netto 701,50; ören i skatteavdrag bortfaller |
| Två delar 60+60, förväntat årsbelopp minst 1 000 | Pröva 120 tillsammans; inget <100-undantag per del |
| Förväntad årsutbetalning 999 kontra 1 000, A-skatt | Undantaget gäller 999; 1 000 kräver vanlig prövning |
| Pension 2026, person född 1960 | Kolumn 6 även efter 66-årsdagen; individuellt beslut kan styra |
| Decemberrätt betald i januari | Januariårets beslut/sats; rättighetsår och betalningsår skiljs |
| Verifierad SINK 2026 | 22,5 %, inte gammal 25 %-sats eller adressbaserat antagande |
| 1 000 i rättsligt dröjsmål i tio dagar, referensränta 2 % | Ränta 2,74 från bolaget enligt ACT/365, ingen C-debit |
| Samma ränta 2,74 till obegränsat skattskyldig | KU20-underlag, 30 %-beräkning ger 0 hela kr i avdrag; räntan göms inte i KU18 |
| Avliden första dagen, redan pågående ej pausad pension | Hela dödsmånaden |
| Avliden första dagen vid beslutad ny start/återstart | Hela rättighetsmånaden; samma datumkonvention som pågående pension |
| Avliden sista dagen månaden före start/återstart | Ingen ny rätt i startmånaden |
| C=0 men G>0, kund vill deluttag | Garantirätt kan delas enligt vald proportion, ingen division med noll |
| G=0,004 kr, positiv rätt | Minst 0,01 kr i månadsbrutto; högprecision behålls för planomräkning |
| G=100,001 och B=99 | Utbetalningsbart garantigolv 100,01, aldrig nedrundat under garantin |

Exemplen kontrollerar specifikationen och ekonomisk bevaring, inte befintlig
kods beteende. Normalskatt kräver också årets faktiska tabell/individuella beslut.

## 5. Gränssnitt till bygg- och verksamhetsarbete

| Mottagande arbete | Vad paketet kräver |
|---|---|
| Försäkringssystem | Tre separata förlopp, historiska garantidelar, planer, månadsrätter och enskilda ekonomiska händelser |
| Kapitalförvaltning | Faktisk månadsavkastning efter direkta kostnader; inga påhittade återbäringstransaktioner; hållbarhetsriskunderlag |
| Ekonomi/risk/aktuariellt | Separat bolagskapital, finansierat stöd, skatt/redovisning och regulatorisk värdering skild från V_g |
| Handläggning/portal | Behöriga val, tydliga frister, dokumenterade kompletteringar och mänskliga negativa beslut |
| Rapportering/bank | Faktiskt betalningsdatum, bankavstämning, skattebeslut och KU-/utbetalarunderlag; ingen dubbelrapportering |
| Dataskydd/systemstyrning | Uppgiftskategorier/grunder, bevarande/gallring, återställning och IKT-processer |
| AI-ekosystem | Låsta deterministiska beräkningar och begränsat beslutsmandat; användningsfallsprövning före verkligt bruk |

Komplett dokumentunderlag betyder inte att alla dessa system och
verksamhetsfunktioner redan finns. Operatörens uppdrag utesluter implementation;
professionell tariffkalibrering för verklig verksamhet är inte gjord.
Det finns inga kvarvarande öppna egna produktval F-001–008 i paketet.

## 6. Dokumentkontroll och samordning

Slutlig dokumentkontroll 2026-10-11:

- Totalt 76 Markdown-filer i produkt-/regelverks-/projektunderlaget inklusive schemahänvisningen
  kontrollerade: inga brutna lokala Markdown-länkar eller teckenkodningsfel.
- PR-001–034, T-001–010 och villkorens §1–16 finns; alla regelblad har
  käll-/tolknings-/villkorskoppling och kontrollfall. Alla käll-ID i regelbladen finns.
- Månadsordning, bankdag, G-öresgolv, dödsmånadsgräns och numeriska
  exempel har stämts av mellan paketets dokument. SCB-kontrollsumman ovan stämmer.
- 75 ändrade/nya filer är enbart Markdown. Inga ändringar i kod, tester,
  miljöfiler, beslutslogg eller delade programdokument. Git diff-kontroll utan fel.

Schemafilen har bara korrigerade villkorshänvisningar och en tydlig markering
av att nuvarande modell inte redan genomför hela paketet. Ingen migration gjordes.

[Samordningsunderlaget](SAMORDNING.md) innehåller avgränsade uppdateringar
till delade programdokument. De görs vid integration på senaste main enligt
AGENTS §4.3, eftersom andra agentspår arbetar i dessa filer.
Ingen ny beslutsloggspost eller kod ändras av leveransen.
