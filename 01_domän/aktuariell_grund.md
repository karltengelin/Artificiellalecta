# Aktuariell grund – ITP1 ålderspension

> **Version:** 0.1 | **Status:** Modellutkast; produktinriktning beslutad i B-027, tariff ej antagen eller driftsatt
> **Ägare:** Operatören | **Upprättad:** 2026-10-11
> **Teknisk implementation:** Saknas | **Kalibrerade tariffer:** Saknas

## 1. Syfte och avgränsning

Beskriva en reproducerbar modell för intjänad garanti och pensionsbelopp
inom ITP1 ålderspension. Källgrund och bolagsval finns i
[T-ITP1-004](../04_regulatoriskt/tolkningar/T-ITP1-004-garanti-och-aktuariell-grund.md).
Dokumentet är underlag för framtida försäkringstekniska riktlinjer och
beräkningsunderlag; det ersätter inte dessa styrdokument.

Ordinarie ITP1-premie bestäms av avtalet enligt PR-ITP1-001. Denna grund
bestämmer hur tillförda premier översätts till pensionsförmåner; den ändrar
inte avtalets premiesatser. Sjukpension, familjeskydd, flytt och
återbetalningsskydd ingår inte.

## 2. Fyra beräkningar och tre värden

| Beräkning | Antaganden och resultat |
|---|---|
| Garantitariff | Versionslåsta antaganden per intjänad del; garanterad pension `G` för vald plan |
| Utbetalningsgrund | Beslutade aktuella antaganden; kapitalbaserad pension `B` och rörligt tillägg |
| Kundprognos | Tydliga scenariosatser; ingen utfästelse eller bokförd tillgång |
| Skuldvärdering | Separat grund enligt tillämpliga solvens-/redovisningsregler; ingår inte i formlerna här |

`C` är pensionskapital från transaktioner. `G` är garanterat brutto-
månadsbelopp för den aktuella utbetalningsplanen. `V_g` är garantins
produkttekniska värde vid en beräkningsdag med den egna garantitariffen.
De tre är inte utbytbara: `C` kan vara lägre än `V_g` och garantin kan då
kräva finansiering från bolaget. `V_g` är inte regulatorisk avsättning.

## 3. Tariffregister och parametrar

Varje grund ska ha ID/version, syfte, giltighet från/till, beslutsreferens,
källversion, full parameteruppsättning, beräkningsmetod och kontrollsumma.
Grund som saknas, inte är godkänd eller inte täcker beräkningsdagen får
inte ersättas med dagens grund eller ett standardvärde.

| Parameter | Arbetsförslag/status |
|---|---|
| Garantigrundande premieandel `alpha` | 1,00, beslutat produktval enligt B-027 |
| Årlig effektiv nettoränta garanti `i_g` | 0,00, beslutat produktval enligt B-027 efter tariffens kostnads-/skatteantaganden |
| Kapitalavgift | B-021: 0,20 % per år, månadsvis; transaktionsbas och ordningsföljd ska preciseras |
| Dödlighet `q` | Unisexmodell med ålder och eventuellt födelsekohort; ej kalibrerad |
| Livslängdsmarginal/förbättring | Kräver kalibrering och godkännande; inte antagen som noll |
| Utbetalningsränta `i_b` | Ej fastställd; håll isär från garanti- och prognosränta |
| Avkastningsskatt/kostnader | Kräver separata årsparametrar och kontroll mot netto-/bruttoantaganden |
| Utbetalning | Månadsvis i efterskott; månadsrätt inklusive dödsmånaden behöver egen avräkningsrutin |
| Referensplan för ny garanti | Livsvarigt från 66-årsmånaden, om inte annan godkänd plan gäller |
| Garantiförstärkning | Ingen automatisk förstärkning i första modellen enligt B-027; eget framtida regelområde |

Kandidat för statistik är SCB BE0101AW, dödsrisker per ålder i promille.
Statistik ska konverteras till sannolikhet genom division med 1 000.
En periodtabell är inte en prognos för en födelsekohort eller färdig tariff.
Unisexviktning, urvalseffekter och livslängdsförbättring ska dokumenteras.
Individens kön får inte styra pensionsbeloppet i denna ITP1-modell.

För konstant dödsintensitet inom ett åldersår föreslås månadsomräkningen
`q_m = 1 − (1 − q_år)^(1/12)`; andra interpolationsmetoder kräver egen
grundversion. Överlevnad över flera månader är produkten av deras
överlevnadssannolikheter. Detta är ett metodförslag, inte en SCB-regel.

En livsvarig beräkning måste hantera den återstående svansen vid höga
åldrar. Ingen faktisk kundutbetalning får avslutas bara för att
statistikens sista ålder eller ett beräkningsindex nås. Saknad svansmodell
blockerar livsvariga automatiska beräkningar.

## 4. Annuitetsfaktor och intjänande

Låt `t` vara värderingstidpunkten och `D` den fullständiga listan av framtida
utbetalningsmånader. Listan styrs av start, form, återstående tid och paus.
För en godkänd grund `b` definieras:

```text
A_b(t, D) = summa över d i D av w_b(t, d) × v_b(t, d)
v_b(t, d) = (1 + i_b)^(-antal månader till betalningen / 12)
```

`w_b(t,d)` är sannolikheten vid `t` för att månadsrätt föreligger i `d`.
För förslaget med pension även för dödsmånaden används överlevnad till
utbetalningsmånadens början, medan betalningen diskonteras till månadens
slut. Exakt intramånadsmetod och ordningsföljd för premie/dödsfall måste
kalibreras. För livsvarig form summeras även den modellerade svansen.
För tidsbegränsad form används de återstående avtalade månadsrätterna.

Varje mottagen nettopremie `P_j` skapar en garantidel vid `t_j`:

```text
G_j = alpha_j × P_j / A_gj(t_j, D_j)
G   = summa G_j för den aktuella planen
```

Faktorn omfattar vid uppskjuten start också tiden från premie till
utbetalning. Varje del sparar sin premie, referensplan, belopp och grund.
Alla månader i en ny garantidels plan ska ligga efter värderingstidpunkten.
Premie mottagen efter ordinarie pensionsålder eller under pågående uttag
kräver en uttrycklig plan för tillkommande förmån; en passerad 66-årsstart
får inte användas. Den kombinationen går till manuell utredning tills
premie-/uttagsmodellen är specificerad.
Ränta/dödlighet för en ny premie får ändras för framtida intjänande, men
en ny version ersätter inte historiska delars grund automatiskt.
Premieåtertag kräver en spårbar korrigering av just den del som återtas;
det får inte behandlas som vanligt marknadsfall.

## 5. Ändrad plan och garanti

Föreslagen värdebevarande omräkning, del för del vid ändringstid `t`:

```text
V_j(t) = G_j_gammal × A_gj(t, D_gammal_kvar)
G_j_ny = V_j(t) / A_gj(t, D_ny_kvar)
```

Samma ursprungliga tariff används på båda sidor. Redan förbrukade
månadsrätter ingår inte i någon av listorna; pausmånader är inte
förbrukade. Första faktiska start behålls. Omräkning kan ge annat
månadsbelopp men får inte skriva över det gamla beslutets underlag.
Metoden är ett bolagsförslag att aktuariellt granska, inte en avskriven
formel från Alecta. Faktorer ska vara ändliga och positiva.

Paus ger inga månadsbelopp under pausperioden. Garantin kvarstår som
ett åtagande enligt ändrad plan, inte som retroaktiv rätt till pausbelopp.
Marknadsförlust utan ändrad plan sänker inte garantidelarna. Varje ändring
prövas också mot skatte-/avtalskrav enligt uttagsreglerna.

## 6. Kapitalbaserad pension och garantiunderskott

Föreslagen modell vid start, återstart och beslutad årlig omräkning:

```text
B = C / A_b(t, D_kvar)
U = max(0, B − G)
M = G + U = max(G, B)
```

`M` är föreslaget brutto-månadsbelopp, inte nettobelopp efter preliminär
inkomstskatt. `U` är ett rörligt, inte garanterat, tillägg. Kontrollera
skatte-/avtalskrav på beloppsförlopp innan ett nytt belopp beslutas.
Ingen extra ”garantibetalning” läggs ovanpå `M`: garantin är dess golv.

Om `C < V_g` ska avvikelsen synas och prövas mot bolagets finansiering.
En framtida underskottsmodell måste ange kapitalstöd, likviditet och
bokföring; det räcker inte att sätta `M = G` och skapa pengar i kundkontot.
Saknad finansiering blockerar automatisk verkställighet i simuleringen
och skapar ärende, men får inte framställas som upphävd kundgaranti.

Kapitaltransaktioner måste skilja premier, faktiskt fördelad avkastning,
kapitalavgift, avkastningsskatt, arvsvinster, pensionsutbetalning och
bolagets dokumenterade kapitalstöd. Ingen post får räknas dubbelt när
en nettoränta eller nettoavkastning redan inkluderar kostnaden.
Avkastning och möjlig fördelning av överskott behöver samordnas med
kapitalförvaltningens riktlinjer. Förslaget antar ingen gratis finansiering.

## 7. Kontrollerbara metodexempel

Följande är syntetiska räknefall för en tidsbegränsad plan vid start:
ingen dödlighet under perioden och nettoränta noll. De är inte godkända
tariffer eller kundprognoser. Faktorn för 60 månadsrätter blir då 60.

| Fall | Utfall utan betalningsavrundning |
|---|---|
| Garantigrund 1 000 kr, 60 månader | `G = 1 000 / 60 = 16,666666… kr/mån` |
| Samma garanti, kapital 1 200 kr | `B = 20`, `U = 3,333333…`, `M = 20 kr/mån` |
| Samma garanti, kapital 900 kr | `B = 15`, `U = 0`, `M = 16,666666…`; underskott måste finansieras |
| 12 av 60 förbrukade; garanti 16,666666…; ändras till 120 totalt | Garantivärde kvar 800; ny garanti `800 / 108 = 7,407407… kr/mån` |
| Individens kön ändras, övriga indata samma | Oförändrat belopp |
| Ny tariff finns men gammal garantidel saknar version | Fel/manuell utredning, ingen tyst omräkning |

Beräkna med hög precision och avrunda endast beslutad utbetalning till
ören med föreslagen ROUND_HALF_UP. Den aktuariella skillnaden från
avrundning ska spåras; sista utbetalningen får inte godtyckligt ökas eller
sänkas för att tömma kapital. Slutavräkning behöver separat regel.
Livsvarig form med noll dödlighet och noll ränta har oändlig faktor och
är ett felaktigt beräkningsunderlag, inte pension noll kronor.

## 8. Förutsättningar före implementation

1. Produktinriktning är godkänd i B-027; fastställ giltighetsdag och behandling av befintlig mockhistorik.
2. Kalibrera och versionslås unisexdödlighet inklusive marginal och svans.
3. Fastställ utbetalningsgrund, kostnads-/skatteparametrar och överskottsmodell.
4. Bestäm underskottsfinansiering, dödsfall/arvsvinster och slutavräkning.
5. Granska oberoende exempel för start, paus, återstart och ändrad tid samt
   känslighet för längre liv, lägre avkastning och högre kostnader.
6. Specificera transaktioner och historiska garantidelar innan någon migration.

B-027 fastställer premieandel och nettoränta som produktval. Ingen fullständig
tariff blir gällande genom denna fil. Reglerna
[PR-ITP1-008](produktregler/PR-ITP1-008-garanti.md) och
[PR-ITP1-009](produktregler/PR-ITP1-009-pensionsbelopp.md) är utkast.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Modell, parameterregister och syntetiska kontrollfall |
