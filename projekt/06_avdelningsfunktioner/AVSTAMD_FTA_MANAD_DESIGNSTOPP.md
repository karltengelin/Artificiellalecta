# Designstopp – avstämd månad från mottagen premie till förklarad FTA

> **ID:** P6-MANAD-001 | **Version:** 0.1 | **Datum:** 2026-11-03
> **Status:** D1–D6 godkända av Karl i chatten 2026-11-03: ”jag godkänner”.
> Byggstart enligt §10 är godkänd. Separat OK krävs fortfarande enligt §9 för Lakebase.
> Ingen ny post har förts in i beslutsloggen.
> **Uppdrag:** [ATT_GORA, nästa bygguppdrag](../../ATT_GORA.md#nästa-bygguppdrag--avstämd-månad-från-mottagen-premie-till-förklarad-fta-förändring), prioriterat 2026-11-02.
> **Utgångspunkt:** `origin/main` vid `b22804b`, arbetsbranch `codex/avstamd-fta-manad`.

## 1. Förslag att godkänna

Bygg en intern, uttryckligen syntetisk **novembermånad 2026**, med ingående läge
2026-10-31 och utgående läge 2026-11-30. Leveransen är en granskad månadsanalys med
mottagningsunderlag, kapital-/garantijournal och en fullständigt förklarad FTA-brygga
för det avgränsade beståndet. Alla beräkningar görs i befintliga domänmotorer.

Båda värderingarna är **scenarier på uttryckligen vald SIM-V**, aldrig låsta
basvärderingar. November är ännu inte avslutad vid detta designstopp; periodens
betalningar, avkastning och alternativa antaganden blir simuleringsunderlag, inte
observerat novemberutfall. Godkännandet av analysleveransen är skilt från
`lock_valuation`. A1:s kvartalsbas och SIM-V:s giltighet ändras inte.

| Val för Karl | Rekommendation |
|---|---|
| D1: månad och leveransstatus | November 2026 som intern scenarioanalys; ingen ändrad giltighet eller låsning av scenario |
| D2: mottagningsgräns | Identifierad, verifierad positiv nettopremie enligt §4; syntetiska motpartsunderlag i första leveransen. Paket A:s fulla filintag/fakturering byggs separat |
| D3: journal och start | Frys avstämt S-04 per oktober, rekonstruera ursprungsspår och anslut nya mottagningar exakt en gång (§5) |
| D4: förklaring och avrundning | A1:s stegordning med uttrycklig mottagningstidpunkt och noll oförklarat; differenser mellan avrundade mellanlägen (§6) |
| D5: grunder för försöket | Ny, oföränderlig AVK-version med bevarad historik och föreslaget novembervärde +0,20 %. Grundfall med oförändrad FI-SIM/SIM-V, separata scenariovarianter ränta +50 bp och driftkostnad +10 % |
| D6: nästa byggsteg | Ordningen i §10, med separat OK för varje Lakebase-ingrepp enligt §9 |

Valen är godkänd bygginriktning. Registrering och antagande av nya grunder görs
fortfarande genom ordinarie tjänster; godkännandet skriver inga data till Lakebase.

## 2. Omfattning, ansvar och befintliga delar

Första sammanhängande körningen använder oktoberutdragets 492 försäkringar med
garanti/kapital och endast stödda, ej påbörjade referensplaner. Syntetiska
premieallokeringar väljs bland dessa försäkringar efter kontroll av förmån,
anställning/premierätt och betalare. Fribrev hindrar inte en verifierad sen premie
för tidigare giltig premieperiod. Nya försäkringar eller planändringar ingår inte i
första månadsfacit. De sju försäkringarna utan garanti/kapital redovisas separat;
de faller inte bort tyst. Oförklarad populationsförändring stoppar leveransen.

Utbetalningar, påbörjat/pausat uttag, dödsfall, återtag av mottagen premie,
automatisk garantiförstärkning, full huvudbok, ALM och solvens ingår inte.
Projekt 5 är pausat: ingen portfölj-, handels-, marknadsdata- eller tillgångskod byggs.

| Ansvar/befintlig del | Återanvändning och verklig lucka |
|---|---|
| Projekt 1, [paket A](../01_ärendehantering/PROJEKTPLAN.md#nästa-steg) | `salary_reports`, premiehistorik och premierättelse finns. `register_salary_report` skapar ingen premie. Bankhändelser, fakturor, delbetalningar och mottagningsallokering saknas som sammanhängande tjänst |
| Projekt 4, B-027/B-031 | PR-008/015/017–023 styr premie, garanti, historik och månadsordning. Inga nya produktregler behövs för att göra netto till garanti |
| `src/services/` (B-028) | Befintlig transaktion, godkännandekö, åtkomstregister och `operation_events`. Alla nya verksamhetsoperationer läggs här, inga direkta webb-/agent-DML |
| A4, `valuation_bases` | Läsning, förslag och mänskligt antagande med kontrollsummor finns. Ingen ny grundkatalog eller parallell källa |
| A5, `valuation_extract.py` | S-04, garantidelar per betald premierad och kapitalavräkning finns. Varaktig journal per ursprung och en journalbaserad utdragsväg saknas |
| `actuarial_annuity.py`, `capital_rollforward.py` | Befintlig garantifaktor, månadsavräkning och största bråkrest återanvänds. Ursprungsfördelning ska bevara befintlig avrundningsnivå (§5.2) |
| A6, `fta_valuation.py`, `valuation.py` | FTA, K, VÅ, U, versionerade utdrag/körningar, scenario och mänskligt baslås finns. Behöver kunna ta journalens frysta underlag utan att åter rekonstruera samma premie |
| [Aktuariedialogen](../../02_system/aktuarie_dialog.md) | `ActuarialDialogue`, `actuarial_workbench`, `perform_actuarial_analysis`, källbundna diagram/rapporter och skyddade aggregat finns. `compare_valuations` isolerar bara samlad grundeffekt; bestånd/tid är ännu oförklarat |
| Harness och flödesmotor | Befintliga systemsteg, hashbundna grindar, avbrott och återhämtning används. `valuation_close` är planerat i A8, inte en redan implementerad flödesdefinition |
| Karl | Godkänner design, grunder och analysunderlag. Bara människa fastställer basvärdering och beslutar om Lakebase-införande |

Ingen ny agent, dialogmotor, generell schemaläggare, alternativ FTA-motor eller
uppgiftsspecifik analysknapp ingår. Claude arbetar parallellt med F5-7; dess
prompt, schemaläggare, `src/agents/case_*` och F5-7-raderna i ATT_GORA lämnas åt Claude.

## 3. Datum, grunder och avstämt ingående bestånd

### 3.1 Varför november och vilka datum stöds?

| Datum | Stöd och användning |
|---|---|
| 2026-09-30 | Tidigare dokumenterat scenario; SIM-V och kurva måste anges uttryckligen. Inget låst IB |
| **2026-10-31** | Vald IB. Komplett befintlig AVK-serie. FI-SIM gäller, SIM-V väljs uttryckligen som scenario |
| **2026-11-30** | Vald UB, scenario. Nya premier använder gällande SIM-G. Blockerat tills november finns i en antagen AVK-version |
| 2026-12-31 | Första möjliga kvartalsbas på nuvarande SIM-V. Kräver avkastning för både november och december, full datakontroll och separat mänskligt lås |
| 2027-01-31 | Inte valt: dessutom krävs beslutad `customer_tax_rate` för 2027; 2026 års sats får inte förlängas tyst. Januari är enligt A1 scenario, inte kvartalsbas |

November är den första hela månaden efter produktpaketets start 2026-11-01.
Oktober-IB är möjlig att kontrollera nu, nya premier kan få SIM-G i stället för
SIM-HIST och endast en saknad avkastningsmånad behöver tillföras för försöket.
December väljs inte som första månad eftersom november-IB fortfarande saknar
gällande SIM-V och avkastningen då behöver förlängas två månader. Två formella,
låsta månadsbaser går inte att få enligt nuvarande A1; det är inte acceptansformen här.

### 3.2 Grundval

| Storhet | Grund och hantering |
|---|---|
| Intjänad garanti i IB | SIM-HIST-2023-01 för mottagningar 2023-01–2026-10. Bevaras per garantidel, även när ny tariff gäller |
| Ny garanti i november | SIM-G-2026-01, giltig från 2026-11-01; mottagning styr tariff, premieperiod styr premietrappa/IBB |
| FTA vid IB och grundfallets UB | SIM-V-2026-01, antagen men giltig först 2026-12-31; explicit scenarioanvändning på båda datumen |
| Diskontering | FI-SIM-2026-10, syntetisk, giltig från 2026-10-31. Oförändrad i grundfallet; +50 bp-variant mäter steg 7 separat |
| Övriga värderingsantaganden | Samma SIM-V i grundfallet. +10 % driftkostnad i separat variant mäter steg 8; historisk garanti ändras inte |
| Avkastning på C | AVK-SIM-2026-01 finns bara t.o.m. oktober. Föreslagen ny kod AVK-SIM-2026-02 med identiska 2023-01–2026-10-värden och november +0,002, uttryckligen syntetisk |
| Kapitalavgift och skattebelastning | Månadens faktiska versioner från `product_parameters`; 2026 års nominella årssatser 0,002 respektive 0,00354. Historiska år behåller sina versioner |

AVK-versionen föreslås via befintliga `propose_valuation_basis` och antas av Karl
via `adopt_valuation_basis`, med giltighet från 2026-11-01 i den isolerade
simuleringen. Den ska inte ersätta innehållet i AVK-SIM-2026-01. Befintlig tjänst
stänger den gamla versionens giltighet dagen före den nya. Oktoberutdraget binds
till sin ursprungliga AVK-hash och får aldrig räknas om med ändrad historik.

Ränte-/kostnadsvarianterna använder befintligt scenariokontrakt för skift/faktor,
med en egen scenariohash. De är inte antagna nya FI-SIM-/SIM-V-grunder. Byggsteget
ska ge mellanlägena till samma motor. Om en verkligt ny grund senare ska gälla
används A4:s ordinarie förslags-/antagandeväg. Inga ändrade giltighetsdagar här.

### 3.3 Genomförd skrivskyddad avstämning 2026-11-03

Befintliga `scripts/diagnostics/valuation_summary.py` kördes mot Lakebase per
2026-10-31 som scenario med uttrycklig grund/kurva. S-04 och registermetadata
kontrollerades därefter i en `REPEATABLE READ READ ONLY`-transaktion. Båda
avläsningarna gav samma utdragshash. Transaktionerna avslutades med rollback.
Ingen backup, migration, observation, journal eller värdering sparades.

| Kontroll/mått | Avläst resultat |
|---|---:|
| Registrerade försäkrade / försäkringar | 501 / 499 |
| Värderade / utan garanti och kapital / ej beräknade | 492 / 7 / 0 |
| Betalmarkerade premierader = rekonstruerade garantidelar | 15 097 |
| Summa betalmarkerade premier = garantidelarnas premieunderlag | 39 044 115,80 kr |
| S-04:s sju kvalitetskontroller | 7 av 7 godkända |
| Motorns data-, K1-, K10- och antalskontroll | 4 av 4 godkända |
| Sparade värderingskörningar | 0; ingen tidigare låst UB att åberopa |
| Pensionskapital C | 42 087 223,57 kr |
| Garanterad pension G, hög precision | 119 195,6502916268 kr/mån |
| FTA, visat till öre | 15 895 579,24 kr |
| Därav garantins kapitalvärde / driftkostnad K | 11 411 206,29 / 4 484 372,95 kr |
| VÅ / U, separat avrundade visningsvärden | 26 232 775,02 / 41 130,68 kr |

Kapitalet stämmer från historiens början:

```text
39 044 115,80 + 3 435 439,23 − 145 105,78 − 247 225,68 = 42 087 223,57 SEK
premier          avkastning      kapitalavgift   kundskatt      utgående C

Oktober: 42 022 578,75 + 84 045,16 − 7 003,74 − 12 396,60 + 0,00 = 42 087 223,57
```

Avstådd avgift och skatt är båda 0,00 kr. K10 på sex decimaler ger i båda leden
26 191 644,333178 kr. **Separat öresavrundning av VÅ och U ovan ger däremot
26 191 644,34, medan C − FTA ger 26 191 644,33.** Det är en identifierad
visningsavrundning på 0,01 kr, inte en ekonomisk rörelse eller en godkänd restpost.
§6.3 föreslår hur månadsleveransen ska visa och avstämma detta.

Kontrollsummor (SHA-256) och kodversion för den genomförda kontrollen:

| Underlag | Kontrollsumma/version |
|---|---|
| Oktoberutdrag | `023946257ca8e184028d9727e52756cc9ec541fe9c5922dcd2f9b9b8c053fefa` |
| Oktoberresultat | `228893c46a5978b5c0dd17b6d906e1efe106200e7857f8c4e879118632d6e604` |
| SIM-HIST och SIM-G, identiskt antagandeinnehåll men olika kod/giltighet | `d35b6acc0baeb30760e30346b93b9f1ef05543d85d3fa06e02d2a85b4892ceed` |
| SIM-V-2026-01 | `d892781a64f5cbf330bd97170b8fcc529c3caed15e11eb3caa97bc544a24d712` |
| FI-SIM-2026-10 | `259033c2e398408f3ea350e7ed00a71942884d7cc201e973d2cddc82df3ef491` |
| AVK-SIM-2026-01 | `c66818630b90c2489c8ef83e7c9d26310e5f466348f26a1d5e2288ee08d583b0` |
| Motor | `fta-1.0+4aaf49381bce` |

Beståndet är därmed numeriskt avstämt **som rekonstruerat S-04-scenario**.
Betalmarkeringarna är syntetisk premiehistorik, inte bevis för verkliga
bankmottagningar. S-04 saknar en varaktig kapitaljournal per ursprung och ett
komplett ekonomiskt startläge med tillgångar, fordringar och eget kapital.
Sådan ekonomisk/bankmässig avstämning påstås inte vara gjord. Vid senare start
måste hash/antal kontrolleras igen; ändrat bestånd kräver ny granskning.

## 4. Kontrakt för mottagen nettopremie

### 4.1 Gräns mot paket A

Paket A äger löneunderlag → premieberäkning/faktura → mottagen betalning →
matchning och fördelning. Denna leverans börjar vid ett verifierbart mottagnings-
och matchningsunderlag, med stöd även för syntetisk bank/faktura. Ett importerat
underlag har exakt samma validering och godkännandekrav som en senare dataproducent.
Enbart `status=paid`, en registrerad lön eller en beräknad premie räcker inte.

Den nya mottagningstjänsten ska i en transaktion kontrollera betalningsunderlag,
återstående allokerbart netto och premieutrymme, skapa mottagningsallokeringarna,
kapitalets insättningsspår och garantidelarna samt skriva idempotenskvitto och
`operation_events`. Granskning av agentförslag återanvänder befintlig kö.
Skrivoperationen föreslås högst APPROVAL, med B-028:s regelgolv; inga nya
handläggaragentverktyg aktiveras i detta uppdrag.

Minimikontraktet nedan är ett förslag till verksamhetsunderlag, inte ny SQL eller API-kod.

| Fältgrupp | Obligatoriskt innehåll |
|---|---|
| Identitet | Miljö, scenario/körning, källsystem, stabilt källhändelse-ID, betalningsreferens, underlagsversion, innehållshash |
| Betalning | Verifierad ursprunglig betalare, bank-/simuleringshändelse och dess källhash, mottagningsdag, valuta SEK |
| Belopp | Mottaget brutto, identifierat externt avdrag, faktiskt netto; alla i hela ören, brutto − avdrag = netto ≥ 0 |
| Matchning | Faktura-/premieunderlag med version/hash, ursprunglig premieperiod och berörd positiv öppen premierad |
| Allokering | Stabilt allokerings-ID, förmån och försäkring, tilldelat netto, fördelningsgrund/version och kvarvarande belopp |
| Tid | Premieperiod, faktisk mottagningsdag, värdedatum = mottagningsmånadens slut, bokningsperiod samt verklig registreringstid var för sig |
| Regel/grund | PR-paket och premieberäkningens IBB-/parameterversion; garantigrundens kod, giltighet och hash vid mottagning |
| Ursprung/rättelse | Länk till premierad och eventuell positiv justering/original. Ny positiv tilläggspremie kräver egen verifierad mottagning |
| Kontroll/beslut | Kontrollutfall, aktör, skäl, besluts-/approvalreferens, transaktionskvitto och ekonomisk effektidentitet |
| Datakvalitet | `synthetic` och `reconstructed_s04` när tillämpligt, definition och källa; blandade källor märks per post och i hela leveransen |

Intern simulering: brutto = netto, externt avdrag = 0; ingen Collectumavgift
hittas på. Vid dokumenterad extern import är endast faktiskt förmedlat netto
garantigrundande. Kapitalavgift och kundskatt är senare kapitalrörelser, inte
ytterligare avdrag från garantigrundande premie (PR-018/022/023).

### 4.2 Normal- och avvikelsefall

| Fall | Effekt och kontroll |
|---|---|
| Full betalning | Bara verifierat/allokerat netto tillför C och en ny garantidel per allokering vid månadsslut |
| Delbetalning | Fördela på fakturans positiva öppna rader med största bråkrest och sedan PR-015. Varje mottagning ger sitt eget spår. Obetald rest ger ingen garanti; boolesk `paid` får inte representera partiellt mottaget belopp |
| Sen premie | Ursprunglig premieperiod styr IBB/trappa, mottagningsmånad styr tariff/garanti och avkastningsstart. Ingen retroaktiv avkastning |
| Okänd betalare/försäkring, oförklarat avdrag eller överbetalning | Kvar i avstämningsunderlag, ingen kapital-/garantieffekt. Återbetalning kräver separat beslut och ingår inte här |
| Nollnetto | Dokumenterat nollkvitto, ingen garantidel och inget kapitalspår med positiv effekt |
| Negativ premie/återtag, påbörjad pension eller saknad historisk grund | Blockeras för manuell prövning; ingen gissad kapitalandel eller ersättningsgrund |
| Samma händelse igen, även via annan fil | Samma ekonomiska originalnyckel ger samma kvitto utan nya poster. Ny filhash får inte skapa ny betalning |
| Samma nyckel med ändrat innehåll | Konflikt och stopp, inte ett andra utfall. Rättelse kräver uttrycklig länkad rättelseprocess |

Första positiva månadsfacit kräver identifierade fullbetalningar och delbetalningar
med frysta syntetiska premie-/fakturaunderlag. Automatisk fakturering, generell
arbetsgivarfil och bankintegration är kvar i paket A; de får senare producera
samma kontrakt. Därmed visas inte novemberförsöket som ett redan komplett paket A.

## 5. Kapital-/garantijournal och övergång från S-04

### 5.1 Gemensam, oföränderlig verksamhetsjournal

Journalen ägs av tjänstelagret i projekt 1/6, inte av agentens körlogg eller
projekt 5. Kapital och garanti är två åtskilda posttyper med gemensamt ursprung.
De är inte dubbla penningbokningar: G mäts i kr/mån, C i SEK och FTA beräknas separat.

| Del | Kontraktsinnehåll |
|---|---|
| Journalomgång | ID, miljö/scenario, period, IB-manifest/hash, källornas stoppunkt, kodversion, postmanifest/hash, kontroller, status och ersättningslänk |
| Gemensam postmetadata | Stabilt post-ID och ekonomiskt original-ID, källa med version/hash, händelse/mottagning/värde/period, försäkring/förmån/ursprung, tillämpad grund-/parameterreferens med hash, metodversion och syntetisk märkning |
| Kapitalpost | Orsak (premie, avkastning, avgift, kundskatt), tecken, SEK-belopp i ören, kapitalspår, ingående/utgående spårsaldo och länk till kollektivets avräkning |
| Garantidel | Mottagningsallokering, P_j, mottagningsmånad/värdedatum, ursprunglig premieperiod, fryst referensplan, historisk garantigrund/hash, A_g och G_j med A5:s precision |
| Kontrollpost | Avstämningens led, skillnad, källreferenser, underlagets hash, utfall och beslutsbindning; ingen ekonomisk effekt |

Garantidel: `G_j = P_j / A_g(j)`. Historiska delar förändras aldrig av ny
avkastning, avgift, skatt, räntekurva eller värderingsgrund. Avkastning ger ingen
ny garanti. Garantins tariffvärde är inte en ytterligare insättning av P_j i C.
FTA lagras som A6-resultat med hänvisning till journalutdraget, inte som kapitalpost.

### 5.2 Bevara kapitalets avrundning och spårbarhet

För varje försäkring och månad återanvänds `close_month` på dess öppningskapital:
avkastning → kapitalavgift → kundskatt → mottagna nettopremier vid månadsslut.
Premien får ingen avkastning, avgift eller skatt under mottagningsmånaden.

Den befintliga motorn fördelar först kollektivets avkastning i ören mellan
försäkringar. Dessa fastställda försäkringsbelopp delas därefter mellan
ursprungsspåren med befintlig `allocate_cents`, stabil ID-ordning och PR-020:s
baser: avkastning efter öppningskapital, debiteringar efter tillgängligt positivt
kapital vid respektive steg. Debiteringen begränsas av spårets saldo. Avstådd
avgift/skatt redovisas separat och blir ingen kundskuld.

**Kör inte `close_month` som om varje ursprungspremie vore en egen försäkring.**
Det skulle ändra avgifts-/skatteavrundning och kan ändra S-04:s redan avstämda C.
Summan av spår ska vid varje steg vara lika med försäkringens befintliga belopp.
Ett tömt kapitalspår innebär inte att motsvarande pensionsgaranti försvinner.

### 5.3 Ingående journal och exakt en källa efter övergången

1. Frys oktoberutdraget, dess premierads-ID:n, garantidelar, planer, grunder,
   parameterreferenser och källornas kontrollsummor i ett IB-manifest.
2. Återskapa kapitalspår från 2023-01 med samma historiska premie-, avkastnings-,
   avgifts- och skattesteg. Använd de redan beräknade garantidelarna. S-04:s
   sammanlagda C och varje försäkrings C ska bevaras exakt i ören.
3. Om ursprungsspåren inte summerar till S-04: stoppa. Fördela inte dagens C
   efter dagens premieandel som en genväg (PR-019/020).
4. Märk importen `reconstructed_s04`, med koppling från varje historisk premierad
   till journalens original-ID. Den skapar inga nya mottagningar eller garantier
   ovanpå S-04 och lämnar historiska `premium_transactions` oförändrade.
5. Efter stoppunkten är mottagningsjournalens verifierade allokeringar källa för
   nya G/C. En journaladapter bygger samma A6-indata från fryst IB + nya poster.
   S-04-rekonstruktion och journal får aldrig summeras som två källor för samma premie.

`ValuationExtract.source` har redan `ledger`, men först när adaptern är byggd kan
det användas för ett journalutdrag. Märkningen ersätter inte ursprunget: rekonstruerat
IB och syntetiska novemberposter ska fortsatt synas i manifest och rapport. Den
befintliga beskrivningen av `ledger` som bokförda värden behöver då preciseras så
att den inte påstår huvudbok eller bankavstämning för detta underlag.

### 5.4 Idempotens, omkörning och transaktionsgräns

Ekonomisk originalnyckel binds till miljö, källsystem och bank-/simuleringshändelsens
stabila identitet. Allokeringarnas nycklar binds under denna, inte bara till ett
importförsök, agent-run-id, filnamn eller ny underlagsversion. Samma händelse som
når systemet från två kanaler ska kunna identifieras som samma original.

Databasen säkrar unika original-/allokeringsnycklar. Tjänsten låser mottagning och
öppna premiesaldon, prövar total fördelning och genomför hela effekten med befintlig
transaktionshantering. Netto = tilldelat netto + ännu ej allokerat netto; mottaget
belopp eller öppet premieutrymme får aldrig överskridas av samtidiga anrop.

En krasch före commit ger ingen effekt; efter commit återfås samma kvitto. Okänt
utfall ska läsas tillbaka före nytt försök. Periodavräkningens nyckel binder period,
IB, källstoppunkt och samtliga grunder. Samma innehåll återanvänder resultatet;
ändrat innehåll kräver ny omgång och granskning. En stängd månads rättelse är en
ny länkad version med motposter, aldrig ny körning ovanpå samma saldon. Negativa
mottagningsrättelser ligger kvar utanför första omfattningen.

## 6. Förklarad FTA med exakt avstämning

### 6.1 Stegordning och mottagningstidpunkt

Utgå från [A1 §8](VARDERINGSKONTRAKT.md#8-förklaring-förändringsanalysens-beräkning).
Följande precisering föreslås som `A1-v1/manad-v1`, utan att ändra dess ordning.
FI-radkopplingarna är kvar som interna referenser; de är inte en verifierad
FI-rapport. Compliancekontrollen M6 och A8 ligger utanför denna leverans.

Låt `V(t, O, B)` vara befintliga A6:s FTA för gamla beståndet O vid t på grundpaket B,
inklusive K exakt en gång per försäkring. `N` är månadens nya garantidelar. `t0` är
oktober-IB och `t1` november-UB; nya delar uppstår vid t1 enligt månadsmodellen.
Grundpaketet B0 fryser IB:s kurva, dödlighet, kostnad och skatteparameter.

| Steg | Beräknat mellanläge/effekt och källa |
|---|---|
| 0 IB | Sparat/granskat scenarioresultat `S0 = V(t0, O, B0)` och fryst IB-manifest. Ingen påstådd tidigare låst bas |
| 1 Premier på garantigrund | `S1 = S0 + ΣP_j`. P_j är nya garantidelars tariffvärde vid mottagningsmånadens slut, länkat till varje mottagningsallokering |
| 2 Garanti- till FTA-grund | `S2 = S0 + [V(t1, O+N, B0) − V(t1, O, B0)]`. Effekten är marginalvärdet på IB:s FTA-grund minus steg 1:s P. Den gamla kostnadsavsättningen debiteras inte en gång till |
| 3 Utbetalningar/slutavräkning | Ej tillämpligt i verifierat försöksbestånd. Noll bara om frånvaron styrks av population/händelsemanifest; annars stopp |
| 4 Tid/förräntning | Lägg till `V(t1, O, B0) − V(t0, O, B0)`. Nu är `S4 = V(t1, O+N, B0)`. K-frigörelse och skatt i diskonteringen ingår; faktisk AVK på C ingår inte |
| 5 Dödsfall | Verifierat inga sådana i försöket; annars stopp |
| 6 Planändring | Verifierat inga sådana i försöket; annars stopp |
| 7 Ändrad räntekurva | Värdera O+N vid t1 med UB-kurvan, övrigt B0. Skillnad mot föregående läge. Egen scenariohash vid +50 bp-varianten |
| 8 Övriga antaganden | Byt till UB:s övriga antaganden, med kurvan kvar från steg 7. Varje ändrad komponent och källa redovisas; kostnadsvarianten +10 % har egen hash |
| 9 Modell/data | Samma kodversion och avstämda källor i försöket ger noll. En verklig data-/modellrättelse kräver egen källa, omvärdering och granskning; ingen uppsamlingsrad |
| 10 Oanalyserat | Oberoende beräknad UB minus sista förklarade läge. Måste vara exakt noll, även före öresvisningen |
| UB | Separat A6-körning från utgående journalutdrag med UB:s grundpaket. Ska inte konstrueras genom att bara summera bryggan |

Mellanlägena 1–2 är analytiska hybridlägen: gammalt bestånd står kvar på t0,
nya delar tas upp vid sitt verkliga värdedatum t1. De är inte bank-/journalposter
eller faktiska garantier i oktober. Därmed får en premie vid novemberstängning
ingen extra månads FTA-förräntning. Skillnaden i steg 4 gäller bara befintligt
åtagande. Datumkonventionen behöver godkännas i D4 innan A7-kod skrivs.

Första försöket har fast population. Vid senare nytillträde måste marginalens
nya K få en identifierad källa i steg 2; den får inte läggas både i premiedelen
och som en andra kostnadsavsättning. Påbörjade uttag och flyttade referensplaner
är blockerade tills respektive kontrakt stöds.

### 6.2 Spår och godkännandestopp

Varje steg, även ett verifierat nollsteg, bär period, storhet/enhet, föregående och
nytt mellanläges-ID/hash, postmanifest med originalreferenser, grund-/kurv-/
parameterkod och hash, kod-/stegordningsversion, scenariohash och kontrollutfall.
En enskild premierad ska kunna följas genom mottagning → kapitalspår/garantidel →
utdrag → värdering → steg. Historiska grundreferenser följer delen, även om deras
antagandehash är lika med en senare grunds hash.

Acceptansen är `FTA_IB + Σ identifierade förändringar = FTA_UB` exakt på lagrad
precision och i öresredovisningen. **Varje oförklarad differens stoppar godkännandet.**
B-042:s/A6:s befintliga 0,5 %-tröskel finns kvar som granskningssignal för andra
analyser men är ingen tolerans i detta uppdrag. Mänsklig kommentar får inte
omvandla en differens till en identifierad post utan källunderlag och beräkning.

### 6.3 Precision och den identifierade visningsdifferensen

A6 ger belopp med sex decimaler; A5 bevarar G/faktor med tio decimaler. C och
mottagningar är i ören. Behåll detta. För FTA-bryggan används samma
ROUND_HALF_UP-funktion `Q` för alla mellanlägen:

```text
steg_i i rapporten = Q(S_i) − Q(S_i−1)
Q(IB) + summan av stegen = Q(sista läget) = Q(oberoende UB)
```

Skillnaden mot att avrunda varje högprecisionsdelta för sig sparas som beräknad
avrundningsmetadata per steg. Om steg fördelas på poster/kohorter ska deras ören
summera till stegets fastställda belopp med stabil största bråkrest. Oavrundade
värden och kontroller bevaras. En differens som försvinner vid avrundning är
fortfarande oförklarad och stoppar kontrollen på sex decimaler.

För C/VÅ/U-kontrollen ska rapporten visa både motorns oförändrade belopp och
öresövergången. Förslaget är att visa U som Q(U), FTA som Q(FTA), C som C, och
en avstämd VÅ-visning `C − Q(FTA) + Q(U)` med sin uttryckliga avrundningsjustering
mot Q(VÅ). Oktober blir då VÅ 26 232 775,01 kr, med visningsjustering −0,01 kr
mot det separat avrundade motortalet 26 232 775,02. Ingen journalpost, kundrätt
eller sparad A6-värdering ändras av visningen. Samma regel används vid IB och UB.

Detta är en avgränsad rapportkonvention att godkänna i D4. Den befintliga
visningsdriften i A6-underlag flaggas här; dagens uppdrag rättar ingen befintlig
rapportkod eller äldre dokumentation.

## 7. Acceptansfall för byggleveransen

Facitunderlagen ska vara versionsbundna och beräknade oberoende av den nya
orkestreringen. Befintliga K1–K10 och garantifaciten återanvänds, men de ersätter
inte händelsekedjans nya kontroller. Tabellen beskriver kommande verifiering,
inte tester som körts i dagens dokumentuppdrag.

| Prov | Krävt utfall |
|---|---|
| IB-källa | Ny avläsning matchar godkänt IB-manifest; rekonstruerade spår summerar exakt till varje försäkrings C och historiska G. Ingen ändrad historik |
| Kapitalfacit PR-020 | C0=100 000, r=1 %, premie=1 000, f=0,002 och s=0,00354 ger avkastning 1 000, avgift 16,67, skatt 29,50 och C1=101 953,83. G skapas bara på 1 000, ingen avkastning på ny premie |
| Nettopremie | Intern 1 000 → P=1 000. Dokumenterad import brutto 1 000, avdrag 5,50 → P=994,50. Ingen dubbel extern avgift |
| Delbetalning | Fakturarader 600/400, mottaget 333,33 → 200,00/133,33; nästa betalning får bara avräkna återstående utrymme. Summering till mottaget netto på öret |
| Sen betalning | Premieperiod 2025, mottagning november 2026 → IBB/parametrar för premieperioden, SIM-G-2026-01 vid mottagning, ingen retroaktiv avkastning |
| Bank-/matchningsavstämning | Mottaget netto = allokerat + oallokerat. Allokerat = nya kapitalinsättningar = P-underlag till nya garantidelar. Oallokerat ger ingen G/C-effekt |
| Ursprungsspår | Flera historiska premier i samma försäkring; förlust, avgift, skatt och bråkrest. Spårens summor stämmer vid varje steg och inget spår blir negativt |
| Återinläsning | Samma underlag, annan fil med samma original, dubbelklick och två samtidiga anrop ger exakt ett ekonomiskt utfall. Samma nyckel med annat innehåll stoppas |
| Krasch/okänt utfall | Avbrott före/efter commit och läsning av kvitto; ingen halv garanti/kapitalpost och ingen dubbel effekt |
| FTA-brygga utan grundbyte | Premier, tariff-/värderingsskillnad och tid förklaras separat. Ny premie vid t1 får inte tidseffekt för t0–t1. UB beräknas oberoende |
| Ändrad kurva respektive kostnad | Befintligt scenariokontrakt ger separat steg 7 respektive 8, inga ändrade historiska G. Kombinerad variant använder samma fasta ordning |
| Avkastningsvariant | Ändrad faktisk AVK ändrar C/VÅ/U men lämnar FTA oförändrad när garanti, datum och FTA-grunder är desamma |
| Oförklarat | Konstruerad rest på 0,01 kr och på 0,000001 kr stoppar båda, även om de ligger under 0,5 %. Saknad källa eller hash stoppar också |
| Öresvisning | Oktobers kända 0,01-visningsskillnad förklaras genom §6.3. FTA-steg och fördelade poster summerar exakt; ingen fritt vald balanspost |
| Frånvaro och ej stödda fall | Inga betalningar/dödsfall/planändringar styrks mot manifest. Ett faktiskt sådant fall markeras ej beräknat och stoppar hela försöksgodkännandet |
| Periodkedja | Nästa försöksmånads IB refererar exakt till föregående godkända UB/hash. En ny grund-/dataversion kan inte bytas in tyst |
| Behörighet och leverans | Agenten får skyddade aggregat, inga individjournaler; småcellsskydd omfattar även differenser. Ändrad granskningshash stoppar beslut. Scenarier kan aldrig låsas som bas |

Månadsrapporten har tre separata avstämningar: C-rörelse, G-rörelse och
FTA-brygga, samt `VÅ − U = C − FTA`. Ingen av dem bevisar att en tillgångssida,
huvudbok, bankförbindelse, konsolidering eller solvens redan finns.

## 8. Människans och agentens arbetsväg

Karl ger månadsuppdraget i befintliga `/team/aktuarie/dialog`. Dialogen binder
miljö, period, IB-manifest och scenario. Agenten kan upptäcka och beställa den nya
förändringsanalysen i arbetsbänken; betrodd systemkod läser journal/individutdrag,
anropar motorerna och sparar endast källbundna analysresultat för dialogen.

Mottagningsförslag granskas genom befintlig godkännandekö. Granskning av periodens
slutresultat binder hela manifestets kontrollsumma: IB/UB, mottagningar,
journalomgång, grunder, scenario, kod/stegordning, kontroller och rapport. En
ändring kräver ny granskning. En godkänd syntetisk analys blir inte `locked` bas.
Källbundna diagram och Markdown-rapport använder befintlig leveransväg och Digital
klarhet; PDF kan genereras vid behov. Rapporten visar nollstegens bevis och kända
begränsningar. Enbart agentstatus `completed` innebär inte godkänd månad.

Systemsteg och granskningsgrindar återanvänder befintlig flödesmotor. Den minsta
periodkedjan för denna analys ska anslutas inom A7/A8; fulla `valuation_close`
med ekonomiförslag och FI-underlag byggs först med respektive kontrakt. En ny
generell körmotor eller egen bakgrundsarbetare behövs inte för månadsförsöket.

### Kassaflödesgränsen mot pausat projekt 5

Publicerbart underlag till framtida projekt 5 är verifierat mottaget netto,
valuta, faktisk mottagningsdag, period, stabil ekonomisk originalreferens,
käll-/allokeringsmanifest och kontrollsumma, samt mottagningskvitto när en
mottagare finns. Projekt 5 ska då avräkna originalet en gång. Ingen handelsorder,
insättning i portfölj eller fabricerat mottagarkvitto skapas nu. Bankinflödet
ska inte räknas två gånger när en senare tillgångssida kopplas in.

Motsatt framtida gräns är en versionsbunden realiserad avkastningsleverans med
period, definition efter direkta placeringskostnader men före kundavgift/skatt,
källa och hash. Tills dess äger aktuarien syntetisk AVK enligt B-042. Den
syntetiska banan är inte förvaltarens resultat eller en beräknad tillgångssida.

## 9. Lakebase – separat införande efter OK

Den skrivskyddade kontrollen bekräftade att `actuarial_datasets`,
`actuarial_conversations`, `actuarial_turns` och `actuarial_analyses` fortfarande
saknas. Befintliga värderingstabeller och grunder finns. Dagens designarbete
körde ingen migration, backup eller skrivning mot Lakebase och ändrade inte
webbprocessen.

**Föreslagen tid:** separat införandepass efter designgodkännande, tidigast
2026-11-04 efter kl. 10.00 Europe/Stockholm. Det är ett tidsförslag, ingen
bokning eller auktorisation. Arbetaren börjar gå vardagar 07.05 från 2026-11-04;
kontrollera även efter 10.00 att inget fördröjt/aktivt handläggararbete eller
annan agent använder databasen. Klockslaget ensamt är inte en exklusivitetskontroll.

Föreslagen ordning, först när Karl har gett uttryckligt OK i chatten för passet:

1. Synka aktuell main och stäm av exklusivt införandefönster med Karl/Claude.
   Kör tillämpliga lokala kontroller och `run_tests.py --all --run --postgres`
   före migration enligt B-040, i isolerad testdatabas och samordnat.
2. Ta backup med befintligt verktyg. Kör förberedd
   `scripts/migrations/migrate_actuarial_workspace.py` i torrkörning och granska
   diff/antal. Stoppa vid partiellt schema eller oväntad förändring.
3. Kör samma migrering med `--apply --backup <verifierad backupmapp>`.
   Kontrollera de fyra tomma tabellerna, index/villkor och oförändrade radantal
   i övriga tabeller. Inga nya agenttabellrättigheter behövs.
4. Samordna omstart av webben med `--actuary-workspace` så att inget pågående
   uppdrag bryts. Verifiera begränsad roll och dialogen med märkt syntetiskt
   uppdrag, följdfråga, leverans och återöppning. Dessa skrivprov ingår i det
   separata OK:t, inte i dagens mandat.

Detta inför bara den redan byggda dialogen. Nya mottagnings-/journaltabeller och
AVK-versionen följer ett senare, separat granskat schema-/datainförande efter
lokal verifiering och nytt OK. Kör inte `create_tables.py` som genväg; det kan
även skapa modeller för andra projekt. Ingen seed eller ändring av befintligt
bestånd ska följa med dialogmigrationen.

## 10. Föreslagen nästa byggordning

| Ordning | Avgränsad leverans och utgångsgrind |
|---|---|
| 0 | Karl godkänner D1–D6 eller anger ändringar. Inget kodarbete före detta |
| 1 | Versionsbundet lokalt försöksunderlag: fryst oktober-IB, syntetiska premie-/betalningskällor, AVK-förlängning och scenarioändringar. Granska källor, mottagningsrätt och förväntade utfall innan ekonomisk effekt |
| 2 | Tjänstekontrakt och varaktig mottagnings-/allokeringsjournal med atomär, idempotent effekt. Fullbetalning, delbetalning, sen betalning, okänd betalning och samtidighet verifieras |
| 3 | Kapital-/garantijournal per ursprung, S-04-övergång och A6-adapter. Historiskt C/G och samtliga ören bevaras; ingen dubbel inläsning |
| 4 | A7:s fulla förändringsanalys som betrott systemsteg med A1-ordning, oberoende UB och strikt nollrest. Kontrollera grundfall, ränta, övriga antaganden och kombination |
| 5 | Anslut tjänsten till befintlig arbetsbänk/dialog och hashbunden mänsklig analysgranskning. Källbundna rapporter/diagram och periodkedja; ingen ny agent |
| 6 | Efter relevant lokal/isolerdatabasverifiering: separat granskat Lakebase-införande av nya journaler/data, med backup och uttryckligt OK. Dialogens befintliga fyra tabeller kan införas tidigare enligt §9 |
| 7 | Senare: förläng AVK även till december och förbered första kvartalsbas 2026-12-31 på gällande grund, separat fastställande. Därefter avgränsas A8, fulla paket A/B och ekonomins mottagning efter sina beroenden |

Kodändringar verifieras med `scripts/testing/run_tests.py`: `--changed` under
arbete, berörda grupper med beroenden före leverans, berörda Postgres-prov efter
samordning och hel lokal svit inför integration. Resultat ska skilja godkända,
bortvalda och överhoppade prov. Projekt 5 förblir pausat genom hela ordningen.

## 11. Öppna frågor och föreslagna beslut

Frågorna nedan ställdes vid designstoppet. Karl godkände D1–D6 i §1 utan
ändringar i chatten 2026-11-03. De bevaras som beslutsunderlag:

- Är en syntetisk novemberanalys med två scenariovärderingar rätt första acceptans,
  med decemberbas som separat nästa mål? En låst månadsbas skulle kräva nytt A1-beslut.
- Godtas mottagningsgränsen med frysta syntetiska faktura-/betalningsunderlag,
  medan full fakturering/intag fortsätter i paket A?
- Godtas novemberavkastning +0,20 % som simuleringsval, och de separata
  ränte-/kostnadsvarianterna? Beloppen är föreslagna, inte införda grunder.
- Godtas hybridlägenas datumkonvention och öresvisningen i §6, inklusive att den
  identifierade visningsjusteringen inte blir en ekonomisk journalpost?

**Beslutsloggsförslag, först efter Karls godkännande:** precisera B-042 för den
avgränsade interna månadsanalysen: scenario-IB/UB med frysta underlag, kapital och
garanti per ursprung, mottagningsmånadens nya delar utan extra tidseffekt,
versionerad A1-stegordning samt noll oförklarat på lagrad precision och på öret.
Bevara kvartalsbasens regler och grunderna/giltigheterna. D2/D3 konkretiserar
PR-018/020; de ersätter inte produktspecifikationen. Ingen post har lagts i
`BESLUTSLOGG.md`.

**Senare separat godkännande:** Lakebase-passet i §9, samt införande av nya
journaler/AVK efter byggverifiering. Ett designgodkännande är inte OK till
migration, backup, dataskrivning eller merge till main.

### Underlag och dagens verifieringsgräns

Styrande: [AGENTS](../../AGENTS.md), [B-027/B-028/B-031/B-040/B-042](../../BESLUTSLOGG.md),
[A1](VARDERINGSKONTRAKT.md), [aktuarieteamets plan](AKTUARIETEAM_PLAN.md),
[projekt 1/paket A](../01_ärendehantering/PROJEKTPLAN.md),
[projekt 6](PROJEKTPLAN.md), [produktreglerna](../../01_domän/produktregler/README.md),
[värderingsdriften](../../02_system/aktuarie_varderingar.md) och
[dialogens införandestatus](../../02_system/aktuarie_dialog.md#verifiering-och-införandestatus-2026-11-02).

Dagens faktaverifiering omfattar repo-/kodläsning och skrivskyddade
bestånds-/värderingskontroller enligt §3.3. Dokumentet inför inga ändrade
juridiska tolkningar, FI-radkoder eller externa marknadsantaganden. Kommande
acceptansprov i §7 är inte genomförda. Länk-/diffkontroll redovisas vid leverans;
en dokumentändring ger inte ett godkänt resultat från Python-sviten.
