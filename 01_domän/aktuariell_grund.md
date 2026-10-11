# Aktuariell grund – ITP1 ålderspension

> **Version:** 1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Fullständigt specificerad simuleringsmodell, med valda antaganden.
> **Införande:** Föreslaget 2026-11-01 enligt produktpaketet. Ingen kod eller myndighetsvaliderad tariff ingår.

## 1. Värden och grunder

`C` är individuellt pensionskapital, `G` garanterad bruttopension per månad
för en viss uttagsplan och `V_g` återstående produkttekniskt garantivärde.
`V_g` är varken kundkapital eller en regulatorisk försäkringsteknisk avsättning.
Premietrappan styr tillförd premie; denna grund bestämmer pension för premien.

Garantigrund SIM-G-2026-01, utbetalningsgrund SIM-B-2026-01 och riskgrund
SIM-R-2026-01 är låsta genom [parameterregistret](parametrar/PARAMETERREGISTER.md).
Historiska garantidelar sparar sin grund och byts inte vid tariffändring.
Skuldvärdering enligt LTF/redovisning kräver en separat grund i ekonomi-/riskprojektet.

## 2. Unisexdödlighet och oändlig svans

Låt `Q_x = (SCB_män_x + SCB_kvinnor_x) / 2000`, där tabellvärdena är
dödsrisker i promille. Källan är [SCB 2025](parametrar/DODLIGHET_SCB_2025.md),
**BE0101A¤**; BE0101AW avser risktid och får inte användas som dödsrisk.
Ålder `x` är fyllda år vid månadens första dag. Kön är inte individuell
beräkningsindata. Ålder, kalenderår och födelseår påverkar samma modell för alla.

För ålder 0–100 och kalenderår `y`:

```text
q_r(x,y) = Q_x × 0,985^max(0,y−2025)
q_g(x,y) = q_b(x,y) = 0,80 × q_r(x,y)
q_m = 1 − (1 − q_år)^(1/12)
```

För ålder över 100 låses förbättringen vid kalenderåret då personen fyller
100. Denna gräns är eget modellval: SCB har också åldersrader 101–110,
men SIM använder 0–100 och en explicit jämn svans i stället för dessa rader.
För svansen används
`y100 = födelseår + 100`. För respektive grund räknas ankaret
`q100` enligt formeln ovan och `mu100 = −ln(1−q100)`. Svansen är:

```text
mu(x) = mu100 × 1,10^(x−100)
q(x) = min(0,995, 1 − exp(−mu(x)))
```

Detta är egna försiktiga simuleringsantaganden. 50/50, 1,5 %, 0,80 och
svansens 10 % är inte statistiskt kalibrerade branschvärden. Svansen gör
förväntad livslängd ändlig även med noll diskonteringsränta. Taket är en
modell för dödsrisk, aldrig en faktisk slutålder. En levande försäkrad får
livsvarig pension oavsett sin ålder.

När årsrisken nått 0,995 för samtliga efterföljande åldrar blir månads-
överlevnaden konstant `p = (1−0,995)^(1/12)`. Återstående oändlig summa
beräknas exakt som en geometrisk serie. Annars kan numerisk summering
användas om en bevisad övre gräns för bortklippt svans ger högst 0,000001 kr
effekt på månadsbeloppet. En godtycklig slutålder är inte tillåten.

## 3. Månadsmodell och annuitetsfaktor

Premie värderas vid mottagningsmånadens slut och får avkastning från nästa
månad. Planändring och pensionsbelopp värderas vid föregående månadsslut.
Månadsrätt uppkommer vid månadens början och betalas första svenska bankdagen
efter månaden, när värderingen är stängd. För en
redan påbörjad pension omfattar månadsrätten dödsmånaden.

Låt `D` vara framtida **betalningsmånader**, exklusive pausmånader och
redan förbrukade månadsrätter. Överlevnad under en paus ingår ändå i
vikten för senare rätt. `t` är värdering vid månadsslut:

```text
A_b(t,D) = summa(d i D) w_b(t,d) × (1+i_b)^(-n_d/12)
w_b(t,d) = produkt av månadsöverlevnad fram till början av d
```

För första månad omedelbart efter `t` är `w = 1`. Senare månader viktas
med överlevnad för mellanliggande månader. `n_d` är antal månader från
`t` till rättighetsmånadens slut. Betalningen sker närmast följande bankdag.
För SIM-G och SIM-B är `i = 0` netto; bankdagarnas förskjutning ändrar
därför ingen diskonteringsfaktor. En framtida grund med annan ränta måste
uttryckligen värdera kassaflödets verkliga tidpunkt.
Skatt och avgift dras faktiskt från kapitalet; de dras inte en andra gång
från denna nollränta. Vid ny premie under en redan pågående månad skapas
ingen retroaktiv månadsrätt. Dödsfall före första rätt bedöms enligt PR-010.

För tidsbegränsad plan summeras alla återstående månadsrätter; livsvarig
plan använder hela svansen. Faktoren måste vara positiv och ändlig.
Tidsbegränsad livsberoende faktor är normalt lägre än antalet månader,
eftersom senare rätt förutsätter överlevnad. `A = 60` är därför endast
ett förenklat exempel med dödsrisk noll, inte den valda tariffen.

## 4. Intjänad garanti och ändrad plan

Varje faktiskt mottagen nettopremie `P_j` ger enligt B-027:

```text
G_j = P_j / A_gj(t_j,D_referens)
G = summa G_j
```

Referensplan är livsvarigt från 66-årsmånaden. Om den månaden är passerad
är start tidigast nästa månad efter mottagning. Premier under pågående
uttag går till en separat ännu inte startad del enligt PR-018/025.
En premie kan inte garantera redan förbrukade månadsrätter.

Vid delning fördelas varje garantidel proportionellt, utan ny värdering.
Vid annan ändring, del för del på ursprunglig grund:

```text
V_j(t) = G_j_gammal × A_gj(t,D_gammal_kvar)
G_j_ny = V_j(t) / A_gj(t,D_ny_kvar)
```

Framtida start, paus, återstart och förlängning kan ge annat månadsbelopp
genom den nya planen. Marknadsfall får inte ändra `G_j` för samma plan.
Ingen automatisk garantiförstärkning av avkastning/arvsvinst sker.
Återtag korrigerar exakt den spårade garantidelen enligt PR-019.
Beräkningsbeslut sparar gamla och nya planer, faktorer och delbelopp.

## 5. Pension och beloppsgolv

Vid start, januari, återstart eller planändring:

```text
B = C / A_b(t,D_kvar)
M_kandidat = max(G,B)
M = max(M_kandidat, skatterättsligt/avtalat beloppsgolv)
rörligt tillägg = M − G
```

Avrunda slutligt beslutat `M` till ören med ROUND_HALF_UP, men höj vid
behov till `ceil(G × 100)/100` och gällande bindande beloppsgolv.
G är summan av garantidelar för samma uttagsdel, inte varje delavrundning
var för sig. En positiv rätt ger minst ett öre i månadsbrutto.
Garantin betalas inte igen ovanpå
`M`. Månadsbeloppet ligger normalt fast mellan omräkningar. Planens
skatterättsliga gren och eventuellt tidigare beloppsgolv kommer från
PR-009, inte från att tillägget kallas rörligt.

Bolagets faktiska kapitalstöd i PR-028 finansierar garanterat och låst
belopp när kundkapitalet inte räcker. Avgifter/skatt, betalningsskuld och
arvsvinstpool särredovisas. Produktformeln skapar inga tillgångar.

## 6. Faktiska arvsvinster och kapitalbevarande

Ett kollektiv omfattar endast denna produkt utan återbetalningsskydd.
PR-010 reserverar obetalda rättigheter före frigjort kapital.
PR-011 fördelar bara faktiskt frigjorda tillgångar. Riskvikten är
`C_vid_månadsbörjan × q_m/(1−q_m)` för levande mottagare med hel månads
exponering. Paus/fribrev deltar. Dödlighet i annuitetsfaktorn är värdering,
inte ytterligare bokförd arvsvinst. Fördelning ger ingen ny garanti.
Ingen förutbetald schablonarvsvinst eller utjämningsreserv används i v1.0.

## 7. Prognos och ekonomiska kontrollfall

Kundprognos använder 0/3/5 % nominell bruttoavkastning, sedan avgift/skatt,
och samma dokumenterade dödlighet. Kommande premier ingår endast om det
anges. Visa garanti för samma plan samt osäkerheten i scenario, dödlighet
och skatt. Prognos är inget betalningsbeslut eller en tillgång.

[Leveranskontrollen](../projekt/04_produktregelverk/LEVERANSKONTROLL.md)
innehåller numeriska resultat med denna tabell och modellen, bevarande-
exempel och dokumentkontroller. De ersätter inte byggsessionens tester.
Modellen är specificerad för simuleringen; en verklig lansering kräver
aktuariell validering mot bestånd, urval och solvens samt erforderliga
styrdokument. Dessa verksamhetskrav hör till risk-/ekonomiprojekten.

| Version | Datum | Ändring |
|---|---|---|
| 0.1–0.2 | 2026-10-11 | Tidigare metodutkast med öppna parametrar |
| 1.0 | 2026-10-11 | Valda grunder, låst statistik, svans och full beräkningsordning |
