# Beslutsförslag: datamodell för paper trading (Fas 2c)

> **Status:** Förslag för operatörens beslut. Steg 1 levererat; steg 2 inväntar uttryckligt OK.
> **Datum:** 2026-10-24 | **Bas:** `origin/main` vid `6445074`, hämtad 2026-10-24; harness 3b-1/3b-2 ingår.
> **Underlag:** [SD-KAP-001 v0.1](../../05_styrdokument/03_riktlinjer/placeringsriktlinje.md), särskilt §§2–8 och 10; [harness](../../02_system/harness.md) §§1, 4.3 och 9.5; [databasschema](../../02_system/databasschema.md) §§2 och 8.
> **Bygger på:** B-003, B-019, B-021/B-022 och B-028; PR-ITP1-020/028 i produktpaketet B-031.
> **Avgränsning:** Tre tabeller och deras kontrakt. Ingen Lakebase-körning, marknadsdatahämtning, förvaltningslogik, gateway eller ändring av `src/services/`, dess åtkomstregister eller `src/agents/`.

## 1. Varför och vad beslutet omfattar

B-019 anger en simulerad portfölj med startkassa, innehav och avslut. SD-KAP-001
preciserar nu vad datamodellen behöver kunna bära: fyra allokeringsdelar,
kassareservationer, spårbara prisunderlag och mänskligt godkännande av varje affär.
Riktlinjen är fortfarande **ett ej antaget utkast**. Ett modellbeslut eller en
merge antar inte riktlinjen och öppnar inte handel.

Förslaget skiljer på beständiga fakta och beräknade saldon. Det följer B-022:s
princip att kapital härleds ur transaktioner, men likställer inte försäkringens
premiesumma med portföljens marknadsvärde. Portföljen är kollektiv enligt B-021;
inga person-, försäkrings- eller förmånsrelationer läggs i kapitalmodellen.

## 2. Förslaget i korthet

| Tabell | Beständiga fakta | Härleds senare, lagras inte som parallellt saldo |
|---|---|---|
| `portfolios` | Scenario, SEK som basvaluta, explicit startkassa och finansieringsunderlag, riktlinjeversion | Bokförd/fri kassa, NAV och avkastning |
| `portfolio_holdings` | Portföljens registrerade instrument/andelsklasser, allokeringsdel och versionsbundet instrumentunderlag | Antal andelar, marknadsvärde, vikter och riskexponeringar |
| `trades` | Ett oföränderligt affärsförslag med separata, bevarade kvittenser för godkännande, utförande eller avslag | Innehavsförändring och kassaeffekt, endast från utförda affärer |

`portfolio_holdings` är därmed ett instrumentregister per portfölj, även när
antalet andelar är noll. Namnet behålls från B-019. En registrerad rad är inte
bevis på ett positivt innehav eller att instrumentet är tillåtet för köp.

### Modellval att godkänna

| Val | Fråga | Rekommendation | Huvudsaklig konsekvens |
|---|---|---|---|
| A | Kassa som innehav eller eget fält? | Separat, oföränderlig `opening_cash_sek`; aktuell kassa härleds | Ingen påhittad fondandel för SEK och inget ändringsbart kassasaldo |
| B | Lagrat eller härlett innehav? | Registrera instrument; härled antal ur utförda avslut | Ingen saldouppdatering som kan glida från affärshistoriken |
| C | Avslutets livscykel | En rad per förslag med fyra statusar och separata kvittenser | Godkännande och utförande är olika steg; ursprungligt förslag bevaras |
| D | Kursreferens | Spara separata ögonblicksbilder för prövningskurs och avslutspris, inklusive valuta | Historiken beror inte på dagens kurs eller leverantörens senare rättelser |
| E | Värdering och avveckling | Ingen lagrad NAV i 2c; reservera godkända köp och modellera utförande som atomisk simulerad avveckling | Verklig fondavveckling och full §6-värdering kräver senare utbyggnad |
| F | Premier till insättningar | Separat kassaflödesjournal senare, med avstämda och idempotenta batcher | Inga premier importeras och inga insättningar maskeras som värdepappersaffärer i 2c |

## 3. Alternativ och motivering

### A. Kassa

**Rekommendation:** startkassan är ett eget fält på portföljen, med dokumenterad
källa och operatörsbeslut. Den ändras inte när köp eller försäljningar sker.
Aktuell kassa räknas från denna startpunkt och utförda affärer. Beloppet anges
uttryckligt; ingen dold standardinsättning på 1 000 kr.

| Alternativ | Fördelar | Nackdelar |
|---|---|---|
| Eget startfält, härlett löpande saldo **(rekommenderas i 2c)** | Enkel SEK-kassa, reproducerbar och ingen dubbel saldosanning | Kräver separat kassaflödesjournal före ytterligare insättningar/uttag |
| Kassa som rad i `portfolio_holdings` | Samma liststruktur för alla tillgångar | Kräver specialinstrument med kurs 1; reservationer och likvid blir ändå specialfall |
| Ändringsbar `cash_balance_sek` | Snabb saldoläsning | Historiken kan motsäga saldot; varje bokning måste uppdatera två sanningar atomiskt |
| Kassaflödesjournal redan nu | Alla likvidhändelser kan spåras enhetligt från start | Utökar uppdraget med minst en tabell och bokningskontrakt innan premie-/betalningskopplingen är beslutad |

Startkassa får i första versionen bara finansiera ett **fristående portföljtest,
inte åtagandetäckning**. Ändrad finansiering kräver ett nytt dokumenterat scenario
eller den framtida journalen, aldrig redigering av startfältet efter scenariostart.

### B. Innehav

**Rekommendation:** lagra instrumentidentitet och klassificering, härled antal
andelar som utförda köp minus utförda försäljningar. `proposed`, `approved` och
`rejected` ändrar inte innehavet. Inga ingående värdepapper i 2c; positioner
byggs från noll genom dokumenterade köp. Fullt sålda instrument behålls för historik.

| Alternativ | Fördelar | Nackdelar |
|---|---|---|
| Härled antal ur avslut **(rekommenderas)** | Samma princip som B-022:s betalda premier; kan räknas om vid valfri tidpunkt | Summering behövs; bolagshändelser kräver fler händelsetyper senare |
| Lagra aktuellt antal som enda källa | Enkel läsning och import | Förlorar hur innehavet uppstod och kan inte återskapa historiken |
| Lagra antal som återbyggbar projektion | Snabb läsning med transaktioner som grund | Kräver vattenmärke, ombyggnad och atomisk uppdatering; omotiverat i denna skala |

Ingen genomsnittlig anskaffningskurs eller latent vinst lagras som auktoritativt
värde. Metod för realiserat resultat beslutas när rapportering byggs.
Fondsplit, utdelning och andra bolagshändelser får inte bokas som falska köp
eller hanteras genom att skriva om gamla avslut.

### C. Livscykel och mänskligt godkännande

**Rekommendation:** en rad per exakt förslag. Förslagets instrument, sida,
kvantitet, prisvillkor, underlag och versioner låses vid registrering. Därefter
fylls separata kvittensfält i exakt en gång per steg. Följande vägar tillåts:

```text
proposed → approved → executed
proposed → rejected
approved → rejected   (återkallat, utgånget eller ändrade förutsättningar; skäl sparas)
```

| Alternativ | Fördelar | Nackdelar |
|---|---|---|
| Ett låst förslag med separata kvittenser **(rekommenderas)** | Tre tabeller räcker; tid, aktör och underlag för varje steg finns kvar | Behöver skrivskydd för befintliga fält och övergångskontroll i framtida gateway |
| Bara en status och ett `updated_at` | Minst antal kolumner | Tappar tidigare steg, identiteter och vad människan faktiskt godkände |
| Separata tabeller för order, beslut och exekveringar/händelser | Ren append-only historik; stöder delavslut, flera beslut och verklig avveckling | Större modell än det avgränsade första paper trading-kontraktet |

`approved` betyder ett mänskligt beslut om det låsta förslaget, inte utförd
affär. Agentförslag får aldrig godkännas av en agent. Operatören kan själv
förbereda och godkänna ett förslag i simuleringen; faktisk fyrögonskontroll
utlovas inte. Den framtida gatewayen hämtar beslutsidentitet och roll ur
betrodd operatörskontext, aldrig ur modellens argument.

Godkännandet gäller `proposal_hash`, exakt instrument/kvantitet, köpets högsta
totallikvid eller försäljningens lägsta nettolikvid, prisvillkor, kostnadstak,
underlag, riktlinje- och instrumentversion samt giltighetstid. Det kopplas
inte till försäkringens `approval_requests`. En samlad UI-vy kan senare visa
referensen `kapital/trade/<id>` utan att flytta ägarskapet till tjänstelagret.

Prövningskursen förblir en bevarad ögonblicksbild. Inför utförande krävs ett nytt,
färskt prisunderlag inom godkända villkor samt nya kontroller av mandat,
portfölj, kassa och limiter. Förändrade förutsättningar som kräver ny prövning
leder till avslag på det gamla förslaget och ett nytt länkat förslag.
`supersedes_trade_id` anger kopplingen. En utgången reservation får inte tyst
frigöras genom att bara filtrera på klockan: förslaget avslås beständigt.

Utfört eller avslaget är slutligt. Förslag och tidigare kvittenser ändras
eller raderas aldrig. Rättelse av ett utfört avslut kräver en ny, godkänd
kompenserande affär med `corrects_trade_id` och skäl; den gamla affären består.
Detta stöder vanlig köp-/säljkompensation, inte generell bokföringsreversering.
Delavslut, flera godkännandeomgångar och gruppgodkännande ingår inte i v1.
Ett `order_group_reference` kan knyta ihop rebalanseringsförslag, men varje
rad måste godkännas för sig och framtida kontroller ska pröva gruppens helhet.

### D. Pris, källa och tid

**Rekommendation:** två separata strukturer: `proposal_price_basis` och
`execution_price_basis`. I båda krävs instrument/andelsklass, leverantör,
källreferens, prisets observationstid, hämtningstid, relevant marknad/kalender,
kurstyp (t.ex. stängningskurs eller fond-NAV), prisvaluta och kurs.
Valutaomräkning sparas med kurs uttryckt som **SEK per enhet prisvaluta**,
egen källa och observationstid. För SEK är faktorn 1, märkt som identitet.

| Alternativ | Fördelar | Nackdelar |
|---|---|---|
| Bevarade underlag per affär **(rekommenderas)** | Affären kan förklaras efteråt även om källan ändras | Viss duplicering av data |
| Bara ticker och avslutsdatum | Litet schema | Saknar andelsklass, tid, prisvillkor och reproducerbart underlag |
| FK till framtida kurstabell | Återanvändning och strukturerade prisfrågor | Kopplar 2c till obyggda 2d; en redigerbar kursrad kan ändra affärens historik |

Prövningspriset och det faktiskt använda simulerade avslutspriset kan skilja
sig åt och lagras separat. Avslutspris, valutafaktor, kostnad och bokförd
SEK-bruttolikvid finns dessutom som typade kolumner för saldoberäkning.
JSON-underlaget ska stämma med dessa kolumner; validering sker vid bokning.
En framtida kurstabell får komplettera med referenser, men ersätter inte kvittot.

Alla tidpunkter anges i UTC, med skilda fält för observation, hämtning,
förslag, godkännande och utförande. `created_at` ersätter inget av dessa.
Färskhet enligt §6 avser relevant avslutad handelsdag, **inte 24 timmar**.
Marknadskalender och färskhetsvalidering byggs i 2d/2e; inga API-anrop görs i 2c.

### E. NAV, reservationer och avveckling

**Rekommendation:** v1 använder endast simulerad samtidig leverans av andelar
och likvid vid `executed_at`; `settlement_model = 'instant_simulated'` gör
förenklingen synlig. Ingen mellanliggande fordran/skuld eller framtida
försäljningslikvid får då räknas som tillgänglig. En föreslagen eller godkänd
försäljning finansierar inte ett köp innan försäljningen faktiskt utförts.

| Alternativ | Fördelar | Nackdelar |
|---|---|---|
| Explicit omedelbar simulerad avveckling **(rekommenderas i 2c)** | Likvid och andelar byter ägare exakt en gång; tre tabeller räcker | Återger inte fonders verkliga avveckling eller femdagarsfördröjningen i riktlinjens stressprov |
| Full avvecklingsjournal från start | Kan beskriva fordringar, skulder och likviddagar | Kräver fler händelser, tabeller och regler före bokningsmotorn |
| Ett lagrat `total_value_sek` utan värderingsgrund | Snabb visning | Blandar anskaffning, marknadsvärde och likvid; otillräckligt för §6 |

Beräkningskontrakt för den senare motorn, där `gross_sek` är positivt:

```text
andelar(i, t) = Σ utförda köp(i, ≤t).quantity − Σ utförda sälj(i, ≤t).quantity
bokförd kassa(t) = opening_cash_sek
                 − Σ utförda köp(≤t).gross_sek + Σ utförda sälj(≤t).gross_sek
                 − Σ alla utförda affärer(≤t).cost_sek
fri kassa = bokförd kassa − Σ godkända, ej utförda köp.max_cash_sek
fri säljbar kvantitet = innehav − Σ godkända, ej utförda sälj.quantity
```

Beloppen för godkända köp reserverar högsta totalkostnaden inklusive kostnadstak.
Förslag reserverar inget. Försäljningsreservationer hindrar dubbel försäljning.
Övergång till utfört tar bort reservationen och tillför den faktiska effekten
i samma transaktion. Avslag frigör reservationen. Kassa, fri kassa och fri
säljbar kvantitet får aldrig bli negativa; detta är kontroller över flera rader.

Exempel: start 1 000 kr, godkänt köp med högst 102 kr ger bokförd kassa 1 000
och fri kassa 898. Utförande av 2 andelar à 50 kr med kostnad 1 kr ger
innehav 2, bokförd/fri kassa 899. Avslag före utförande hade lämnat 1 000 kr
och noll andelar. Detta är bara ett saldokontrollfall, ingen tillåten allokering.

Full NAV enligt SD-KAP-001 §6 är marknadsvärden + kassa + säkra fordringar −
skulder − upplupna placeringskostnader. En förenklad summa av andelsvärden och
kassa gäller bara när övriga komponenter uttryckligen är noll i scenariot.
Saknade priser eller komponenter ger **ej beräknat**, aldrig noll. Dagliga
värderingar, totalavkastning, utdelningar, upplupna kostnader/skatt och
avvecklingsstress återstår; 2c levererar inget NAV- eller avkastningsmått.
Verklig fördröjd avveckling kräver utbyggnad före motsvarande test eller handel.

### F. Premieinflöde till senare insättningar

**Rekommendation:** en separat framtida `portfolio_cash_flows`-journal för
insättningar, uttag och andra likvidhändelser. Den byggs med premie-/betalningskopplingen,
inte i steg 2 av detta uppdrag. Ett fält för aktuell kassa eller `trades` med
låtsasinstrument ska inte ersätta den journalen.

| Alternativ | Fördelar | Nackdelar |
|---|---|---|
| Separat journal med avstämda batcher **(rekommenderas senare)** | Skiljer extern finansiering från avkastning och handel; kan göras idempotent | Ytterligare schema och integrationsbeslut behövs före beståndskoppling |
| `deposit`/`withdrawal` som typer i `trades` | Färre tabeller | Blandar kassaflöden med instrument, kvantitet, pris och affärsgodkännande |
| Sätt kassan till summan av betalda premier | Direkt koppling till B-022:s saldo | Dubbelräknar vid återkörning; missar handel, finansiering, avgifter och pensionsflöden |

Det framtida flödet ska:

1. Hämta ett granskat försäkringsaggregat av faktiskt betalda ålderspensionspremier
   och tillämpliga rättelser. `pending`/`invoiced`, andra förmånstyper och `fee`
   är inte nya premieinsättningar. Period, mottagningsdag, bryttid och regelversion sparas.
2. Stämma av vilka likvida medel som faktiskt tilldelas portföljen. B-022:s
   nuvarande `SUM(amount_sek) WHERE status='paid'` beskriver försäkringskapital,
   inte automatiskt överförbar portföljlikvid. Avgifter, betalningsskulder,
   arvsvinstpool och bolagsmedel får inte blandas enligt PR-028.
3. Skapa en dokumenterad batch med belopp, innehållshash och globalt unik
   källreferens. En försäkringsnära avstämning bevarar ingående transaktions-id:n
   och hindrar att samma premie ingår i flera batcher. Kapitaldelen får aggregat
   och ogenomskinlig avstämningsreferens, inga individuppgifter.
4. Kräva mänskligt godkännande för portföljinsättningen och boka högst en gång.
   Även två olika batch-id:n med överlappande källrader ska stoppas. Ändrat
   betalt underlag ger en länkad differens/rättelse, aldrig omskriven historik.
5. Lägga journalens nettokassaflöden till kassaformeln och klassificera
   insättningar/uttag som externa flöden i tidsviktad avkastning. Startkassan
   hålls som separat startpunkt; om den senare migreras till en öppningspost
   måste startfältets bidrag tas bort samtidigt så beloppet räknas exakt en gång.

Gamla premiesummor importeras inte retroaktivt till ett scenario med 1 000 kr.
Beståndskoppling kräver först avstämda starttillgångar, finansiering, pensioner,
bolagsbuffert och ALM enligt SD-KAP-001 §§2/7 och PR-028. Aggregatgateway,
batchjournal och mottagnings-/rättelsekontrakt är uttryckliga senare beroenden.

## 4. Föreslaget kolumnkontrakt för steg 2

Detta är modellförslaget; det aktuella databasschemat ändras först efter OK.
Alla tre tabeller får UUID-nyckel och basmodellens `created_at`/`updated_at`.
FK:er använder `ON DELETE RESTRICT`. Pengar är `Numeric(18,2)`, kvantitet/pris
och SEK-valutafaktor `Numeric(24,10)`, beräknat med `Decimal`. Belopp i SEK
avrundas till ören en gång per bokförd likvid med `ROUND_HALF_UP`.
JSON-underlag använder befintligt `JSON().with_variant(JSONB(), 'postgresql')`.
SQLite-tester ger inte samma precisions- eller tidszonsskydd som Postgres;
UTC-normalisering och beloppsberäkning måste därför säkras i bokningskoden
och senare också verifieras mot en uttryckligen tillåten Postgres-testmiljö.

### 4.1 `portfolios`

| Fältgrupp | Kolumner och regler |
|---|---|
| Identitet | `id`, unik `scenario_code`, `name`, `scenario_description` |
| Avgränsning | `mode='paper'`, `scenario_type='standalone'`, `base_currency='SEK'`, `settlement_model='instant_simulated'`; CHECK låser första modellens scope |
| Start | `starts_at` (UTC), `opening_cash_sek ≥ 0`, obligatoriskt `funding_basis` med källa, belopp, tid och mänsklig beslutsreferens; ingen automatisk finansiering |
| Styrgrund | `guideline_reference`, `guideline_version`, `guideline_hash`; godkänd uppbyggnadsplan och scenariobeslut i `scenario_basis` |

En scenariorad ger ingen körbehörighet. Första versionen kan inte markeras
beståndskopplad. Uppbyggnadsskedets högst fem handelsdagar och 100 % kassa
är en tidsbegränsad, godkänd plan enligt §8, inte en allmän dispens.

### 4.2 `portfolio_holdings`

| Fältgrupp | Kolumner och regler |
|---|---|
| Relation | `id`, `portfolio_id`; unik `(portfolio_id, instrument_key)` |
| Instrument | `instrument_key` (entydig andelsklass, normalt ISIN), `name`, valfri `market_symbol` och `market_reference`; ticker är inte ensam identitet |
| Allokering | `allocation_bucket` med CHECK för `sek_fixed_income`, `global_equity`, `swedish_equity`; ingen kassainstrumentrad |
| Underlag | `price_currency`, `instrument_basis_reference`, `instrument_basis_hash`, `instrument_basis` (JSON med versionsbundet mandat, godkännande och genomlysningsunderlag) |

Instrumentets identitet och allokeringsdel låses efter första affärsförslaget.
Förändrat fondmandat/andelsklass kräver ny prövning och spårbar version; gamla
trades behåller en egen kopia av det underlag som gällde. Aktuell riskinformation
får inte härledas ur ett gammalt köpunderlag.

Delarna motsvarar mål **55/25/10 %**, med separat **10 % kassa**; räntor
45–70 %, aktier totalt 25–45 %, globaldel 20–35 %, svensk del 5–15 % och
kassa 5–20 %. Procenttal dupliceras inte som ändringsbara modellstandarder.
Fem procentenheters målavvikelse vid månadsslut skiljs från ett hårt limitbrott.

Rating/duration, minst 50 % svenska staten i räntedelen, UCITS, fysisk replikering,
fondtak 60 %, emittent-/grupptak 5/10 %, valutaexponering högst 35 %, likviditet,
arbetsgivarkoppling och hållbarhetsunderlag kräver instrumentprövning och
genomlysning enligt riktlinjen. Prisvaluta eller allokeringskod bevisar inte
dessa egenskaper. Genomlysningsdatum/källa och osäkerhet ska följa underlaget;
data äldre än tre månader eller saknade uppgifter är **ej verifierade**.
2c skapar inga instrument och ingen motor som intygar limituppfyllelse.

### 4.3 `trades`

| Fältgrupp | Kolumner och regler |
|---|---|
| Relation | `id`, `portfolio_holding_id` (portfölj via innehavsraden); ingen oberoende `portfolio_id` som kan peka på fel portfölj |
| Låst förslag | `side` (`buy`/`sell`), `quantity > 0`, `proposed_at`, `proposed_by`, `proposer_type` (`human`/`agent`), `reason`, valfri `run_reference` |
| Villkor | `limit_price > 0`, `max_cost_sek ≥ 0`, `max_cash_sek > 0` bara för köp, `min_proceeds_sek ≥ 0` bara för sälj, `valid_until > proposed_at` |
| Versionsbindning | `proposal_hash`, `proposal_price_basis`, `proposal_basis` med riktlinje-/instrumenthash, kontrollunderlag, portföljens prövningstid och eventuellt gruppunderlag |
| Status | CHECK för `proposed`, `approved`, `executed`, `rejected`; default `proposed` |
| Mänskligt godkännande | `approved_at`, `approved_by`, `approval_role`, `approved_proposal_hash`, `approval_basis`; obligatoriska i `approved`/`executed` |
| Utförandekvitto | `executed_at`, `execution_price > 0`, `execution_fx_rate > 0`, `gross_sek > 0`, `cost_sek ≥ 0`, `execution_price_basis`, `execution_basis`; obligatoriska endast i `executed` |
| Avslagskvitto | `rejected_at`, `rejected_by`, `rejection_reason`; obligatoriska endast i `rejected`. Ett tidigare godkännande bevaras vid avslag efter godkännande |
| Länkar | Valfria `order_group_reference`, `supersedes_trade_id`, `corrects_trade_id` (själv-FK, inte samma id) |

Prisvillkoret är högsta köppris respektive lägsta säljpris i instrumentets
prisvaluta. Totallikvidvillkoret begränsar samtidigt SEK-effekten efter valuta
och kostnad. `gross_sek` avser `quantity × execution_price × execution_fx_rate`
avrundat till ören; `cost_sek` dras exakt en gång, för båda sidor. Samma kvantitet
måste utföras helt eller affären avslås; inget separat fält för delavslut.
Nollkostnad måste vara ett explicit scenarioantagande.

Godkännande och utförande måste ligga senast vid `valid_until`, med
`proposed_at ≤ approved_at ≤ executed_at`. Avslag efter ett godkännande ska
ligga efter detta och får ske efter giltighetstidens slut. JSON-underlagens
hash beräknas senare av betrodd kod med versionsbestämd kanonisering; en
matchande lagrad hash bevisar ensam inte underlagets riktighet.

Index föreslås på `(portfolio_holding_id, executed_at)` och `(status, proposed_at)`.
Ett trade-id identifierar ett förslag och ett möjligt utförande; återförsök får
inte skapa en ny rad för samma förslag. Den senare gatewayen behöver även en
unik anropsnyckel innan automatisk återspelning kan tillåtas.

## 5. Vad databasen säkrar och vad som återstår

Steg 2 ska med FK, UNIQUE och CHECK säkra referenser, tillåtna värden,
beloppstecken, sidspecifika fält, statusfältens fullständighet, sammanhängande
godkännandekvittens, matchande förslagshash och kronologi. SQL:s NULL-semantik
ska hanteras uttryckligt så att ett halvt kvitto inte kan passera en CHECK.

En SQLAlchemy-modell och en CHECK kan inte bevisa att identiteten är en
autentiserad människa, att tidigare värden aldrig skrivits över eller att en
övergång faktiskt gick via föregående status. Följande kräver den senare
kapitalgatewayen och dess journal/transaktionskontroll:

- låsning av förslag och redan fyllda kvittenser, inga raderingar och inga
  tillbakagångar från slutstatus; utförande bara från ett giltigt godkännande;
- en auktoriserad mänsklig beslutsväg, kontroll av hash/versioner och nytt
  godkännande när underlaget behöver ändras;
- låsning/serialisering per portfölj vid reservation, utförande och avslag så
  samtidiga affärer inte överreserverar kassa eller säljer samma andelar;
- kontroll att ersättnings-/rättelselänkar gäller rätt portfölj och relevant
  tidigare affär, utan cykler eller otillåtna kompensationer;
- färskhet, handelskalender, prisvillkor, rundning, gruppkontroller, negativa
  saldon, riktlinjelimiter, stress och efterkontroll;
- beständigt revisionsspår även för beslut att avstå, passiva limitbrott,
  instrument-/scenariobeslut och andra händelser som inte är en affär.

Tabellerna efter steg 2 är därför **en lokalt testad datagrund, ingen aktiverad
handelsförmåga**. Inga agentverktyg, UI-bokningar eller tillåtande registerrader
tillkommer. Gatewayen ska senare verkställa samma regler även för direkt
mänsklig användning. Harnessjournalen ersätter inte kapitalets affärsspår.

## 6. Genomförande efter operatörens OK

1. Dokumentera det godkända kontraktet i `02_system/databasschema.md`, med status
   modeller byggda/testade lokalt, **ej skapade i Lakebase**.
2. Bygg `Portfolio`, `PortfolioHolding`, `Trade` under `src/models/`, och
   exportera dem i `src/models/__init__.py`. `scripts/setup/create_tables.py`
   importerar redan `Base` därifrån och använder `Base.metadata.create_all`;
   någon separat tabellista behövs inte. Skriptet **körs inte**.
3. Testa lokalt med SQLite och FK-kontroll påslagen: relationer/unikhet,
   giltiga kvittenskombinationer och otillåtna NULL-/status-/beloppsfall,
   hash- och tidskrav, slutna scenariovärden samt JSON/Decimal-rundtur.
   Kontrollera Postgres-DDL genom kompilering utan anslutning.
4. Kör relevanta befintliga tester på resultatet från synkad main, inklusive
   harness 3b-1/3b-2 och försäkringsmodellernas SQLite-användning. Tester som
   ansluter till Postgres/Lakebase eller externa API:er ingår inte.
5. Uppdatera endast egna 2c-punkter i backlog/projektplan, gör konsistenskontroll,
   committa på egen branch och redovisa diff, testutfall och commit-meddelande.

Ingen marknadsdatakoppling (2d), saldomotor/rebalansering/premieintegration (2e),
databasinstallation, tjänsteoperation, harnessändring eller merge till main
ingår i detta OK. Införande av riktlinjen är ett separat beslut.

## 7. Förslag till beslutstext – inte loggat

> **Beslut:** Fas 2c byggs enligt modellval A–F i detta underlag: en fristående,
> simulerad SEK-portfölj med explicit och låst startkassa; registrerade instrument
> vars antal härleds ur utförda köp/sälj; låsta affärsförslag med separata
> mänskliga godkännande-, avslags- och utförandekvittenser samt bevarade pris-,
> valuta- och versionsunderlag. Första avvecklingsmodellen är uttryckligen
> omedelbar och simulerad. Ytterligare likvidhändelser och premiekoppling kräver
> en separat, avstämd kassaflödesjournal senare.
>
> **Motivering:** Modellen ger reproducerbara saldon utan dubbla sanningar,
> skiljer finansiering från avkastning och bevarar vad människan godkände.
> Den följer B-003/B-019, B-021/B-022 och kapitalets egen domängräns i harness.
>
> **Konsekvenser:** Tre portabla SQLAlchemy-modeller, schemadokumentation och
> lokala tester byggs. Modellerna ger ingen handelsbehörighet; kapitalgateway,
> journal, marknadsdata, värdering, kontroller, verklig avvecklingsmodell och
> premieintegration återstår. Ingen Lakebase-körning eller main-merge godkänns
> genom modellbeslutet. SD-KAP-001 är fortsatt ej antaget tills separat beslut fattas.
>
> **Preciserar:** B-019:s första portföljmodell. Ändrar inte B-003, B-021/B-022,
> produktpaketet eller försäkringstjänstelagrets scope.

Inget nytt B-nummer reserveras. Operatören avgör om och när beslutet ska föras
in i `BESLUTSLOGG.md`.
