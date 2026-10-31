# Aktuarieteamet – arbetssätt, harness och arbetsyta (utredning och planförslag)

> **Version:** 0.1 | **Datum:** 2026-10-31 | **Status:** Utredning och förslag. Inget beslut,
> ingen kod, ingen ny behörighet. Underlag för ett kommande designstopp (jfr B-033/B-035/B-041).
> **Hör till:** projekt 6 (aktuariell värdering, FTA) med kopplingar till projekt 2, 10 och
> compliance-teamet. Kompletterar [projektplanen](PROJEKTPLAN.md) och `harness.md` §9.2.

Dokumentet svarar på fyra frågor:

1. Vad kan aktuarieteamet göra i dag? (§1)
2. Hur arbetar en aktuarie på ett svenskt tjänstepensionsföretag, och vad ska tas fram
   kvartalsvis och årsvis till Finansinspektionen? (§2)
3. Hur översätts det till Artificiellalecta: FTA, FTA-analys, FTA-bokföring och
   simulering av antagandeändringar för ITP1-produkten? (§3)
4. Hur ska teamets harness (agenter, poddar, skills, guardrails, flöden) och en arbetsyta för
   en mänsklig aktuarie se ut, inklusive kopplingen till compliance och produktrapporten? (§4–8)

---

## 1. Nuläge – vad aktuarieteamet har i dag

| Del | Finns | Källa |
|---|---|---|
| Team och ledande agent | `aktuarie` med `actuary_agent` (modellroll `deep`), tak 12 steg / 16 verktygsanrop / 1,00 USD | `src/agents/ecosystem.yaml` |
| Poddar | `bestand`, `berakning`, `regelverk`, `dokument` | samma |
| Verktyg | `estimate_parameter_change_impact` (premieeffekt av godkänd parameterändring), `get_company_metrics` (registrerat bestånd, betalmarkerade premier per månad), `calculate_premium_preview`, regel-/källäsning, `get_product_parameters`, `write_draft` | `02_system/agenter/aktuarieagent.md` |
| Flöden där teamet deltar | `rule_change_parameter` (steg 2, beståndsinsikt), `company_question` (OC-3a, beståndsöversikt) | `src/agents/flows/definitions/` |
| Delegering | Tar emot uppdrag från compliance (B-039); delegerar inte själv | `src/agents/delegation.py` |
| Arbetsyta | `/team/aktuarie`: uppdragslista, detalj och granskning för bolagsfrågan – ingen egen aktuariell funktion | `02_system/fragekedja_webb.md` |
| Databasroll | `agent_aktuarie`: läser fem tabeller, inga förslag | `src/utils/agent_roles.py` |
| Metodunderlag | SIM-G/B/R-2026-01, unisexdödlighet SCB 2025, garantiformel, PR-028:s stressbuffert | `01_domän/aktuariell_grund.md`, `PARAMETERREGISTER.md` |
| Specialist | Data scientist-agent: endast beskrivning, ej byggd | `02_system/agenter/data-scientist-agent.md` |

**Det som saknas** (V-11/V-12 i processöversikten): värderingsgrund för FTA, garantidelar och
kundkapital per individ, värderings-, förändringsanalys-, kassaflödes-, scenario- och
kapitalkravsmotorer, antagandebibliotek, rapportunderlag med period och mottagare, bokföringsunderlag
till ekonomi och en arbetsyta där en människa kan göra det aktuariella arbetet.

**Slutsats:** teamet kan i dag svara på frågor om premieflöden och bestånd. Det kan inte
värdera åtaganden. Allt som kallas FTA, solvens eller garantirisk är obyggt.

---

## 2. Hur en aktuarie arbetar på ett tjänstepensionsföretag

### 2.1 Rollerna

I ett svenskt tjänstepensionsföretag (LTF 2019:742, FFFS 2019:21–23) finns i regel två aktuariella roller:

- **Beräknande/ansvarig aktuarie (första linjen).** Tar fram antaganden, beräknar
  försäkringstekniska avsättningar (FTA), gör resultat- och förändringsanalyser, prognoser,
  känslighetsanalyser, prissättning och underlag till bokslut, rapportering och kapitalkrav.
- **Aktuariefunktionen (nyckelfunktion, andra linjen).** Bedömer och kontrollerar beräkningen
  av FTA, antagandenas lämplighet och datakvaliteten. Föreslår ändringar i de
  försäkringstekniska riktlinjerna till styrelsen, som beslutar om dem (jfr KPA:s och Alectas
  publicerade riktlinjer). Rapporterar iakttagelser till styrelsen; FI:s kvalitativa
  rapport har ett eget avsnitt om aktuariefunktionen.

I ett litet bolag kan rollerna dela personer, men granskningen ska vara oberoende av beräkningen.

### 2.2 Arbetsåret

| Rytm | Aktuariens arbete | Mottagare |
|---|---|---|
| **Månad** | Datautdrag och kvalitetskontroll; kontroll av kapitalavräkning, avgifter och arvsvinstfördelning; omvärdering av stressgap och likviditetsbuffert (för oss PR-ITP1-020/011/028) | Ekonomi, ledning |
| **Kvartal** | FTA-värdering per balansdag, förändringsanalys, bokföringsunderlag, solvens- och kapitalkravsuppföljning, kvartalsrapport till FI | Ekonomi, VD/styrelse, FI |
| **År** | Full värdering med årets antaganden; erfarenhetsanalys (utfall mot antagande för dödlighet, kostnader, uttagsbeteende) och antagandeöversyn; aktuariell resultatanalys; kassaflödesprognoser; aktuariefunktionens rapport; underlag till egen risk- och solvensbedömning (ERS/ORSA); översyn av försäkringstekniska riktlinjer; årlig produktöversyn; FI:s årsrapportering | Styrelse, revisor, FI |
| **Löpande** | Konsekvensanalys av regeländringar (t.ex. ändrad diskonteringsränta), prissättning och villkorsändringar, scenario- och känslighetsfrågor från ledningen, väsentliga händelser | Ledning, compliance |

### 2.3 FTA, FTA-analys och FTA-bokföring

- **FTA-beräkning.** Nuvärdet av framtida åtaganden (förmåner och kostnader) med
  försäkringstekniska antaganden. Diskonteringsräntan bestäms enligt FFFS 2019:21 utifrån
  marknadsräntor för ränteswappar; risken för negativa räntor ska inte beaktas (förordning
  2019:809 1 kap. 6 §). *Bevakning:* enligt Realtid 2026-06-16 har FI beslutat att ändra
  metoden för diskonteringsräntan. Det är inte kontrollerat mot FI:s beslut och bör prövas som
  en källändring av compliance.
- **FTA-analys (förändringsanalys).** Förklarar skillnaden mellan ingående och utgående FTA
  stegvis: varje orsak räknas om i motorn i en bestämd ordning, så att stegens summa är exakt
  differensen. Det som inte förklaras ("oanalyserat") ska vara litet och följas upp. Samma
  logik bär FI:s avsnitt F (FTA-rörelse) och E (aktuariell resultatanalys).
- **FTA-bokföring.** Aktuarien levererar avsättningsunderlag per balansdag: utgående FTA,
  förändring per orsak och fördelning på resultat- och balansposter (bl.a. förändring i
  livförsäkringsavsättning). Ekonomi bokför och stämmer av mot aktuariens underlag.
  Redovisningen följer FFFS 2019:23.

### 2.4 Rapportering till Finansinspektionen (FFFS 2019:22)

Sammanställt från föreskriftens text på lagen.nu (ändrad t.o.m. FFFS 2025:1). Radkoder och
fält ska kontrolleras mot den gällande konsoliderade versionen innan ett rapportkontrakt låses
(källregistrets post K-FFFS-RAPPORT).

| Rapport | Frekvens och frist | Innehåll | Aktuariens del |
|---|---|---|---|
| Kvantitativa uppgifter, 4 kap. bilaga 1 | **Kvartal:** balansomslutning < 1 mdkr lämnar avsnitt C, E, F; ≥ 1 mdkr avsnitt A–F. Frister 30 apr, 10 aug, 31 okt, 31 jan | A resultaträkning, B balansräkning, C nyteckning och premier, D kapitalplaceringar, E solvens, F tilläggsförsäkringar | C (premier per produktslag, för oss avgiftsbestämd traditionell, flytt in/ut), FTA i balans- och solvensuppgifter |
| Samma, årsvis | **År**, alla företag, avsnitt A–K; 14 veckor efter 31 dec | Därtill D försäkringsbestånd, **E aktuariell resultatanalys** (resultat per dödlighet, kostnader, garantier, ändrat ränteantagande m.m.), **F FTA** (ingående, inbetalningar, utbetalningar, kostnadsuttag, avkastning tillförd FTA, ändrade antaganden …), G resultatanalys för återbäring, H solvens, **I kassaflödesprognoser**, J infrastruktur, K gränsöverskridande | D, E, F, G (om tillämpligt), H (FTA och försäkringsrisk), I |
| EU-gemensamma uppgifter, 7 kap. (EIOPA PF-/ECB-mallar) | ≥ 25 MEUR: kvartal och år (bl.a. PF.29.05 förändring i FTA, PF.29.06 kassaflöden). < 25 MEUR: endast årligen, avsnitt L–O | Balans, tillgångar, FTA, medlemmar, flöden | FTA-rörelse och kassaflöden |
| Kvalitativ tillsynsrapport, 5 kap. | Små företag: årlig sammanfattning, 18 veckor efter 31 dec | Verksamhet, styrning (inkl. aktuariefunktionen), riskprofil, **värdering av FTA och väsentliga förändringar**, solvens | Värderingsavsnittet och aktuariefunktionens iakttagelser |
| Egen risk- och solvensbedömning, 6 kap. | Inom två veckor efter styrelsens fastställande | Resultatet av bedömningen | Stresser, kapitalbehov, FTA-känslighet |
| Väsentliga händelser, 3 kap. | Så snart som möjligt | Hot mot åtaganden, stabilitet m.m. | T.ex. garantibrist eller väsentligt ändrad FTA |

Kapitalkraven regleras i LTF 8 kap. med ett schablonmässigt minimikapitalkrav och ett
riskkänsligt kapitalkrav (RKK) enligt FI:s kalibrering. RKK bygger på marknads- och
försäkringsrisk med diversifiering plus operativ risk. Stressnivåerna ska hämtas ur FI:s
kalibreringsdokument innan något simulerat RKK byggs.

**För vårt bolag:** med cirka 39 Mkr i premiekapital ligger bolaget under båda trösklarna. Det
lämnar avsnitt C, E och F kvartalsvis, A–K årligen, de små EU-mallarna L–O årligen och en årlig
kvalitativ sammanfattning. Om simuleringen ska öva den fulla rapporteringen behövs ett
uttryckligt val (öppen fråga Q2, §9).

---

## 3. Översättning till Artificiellalecta

### 3.1 Vad FTA betyder för vår produkt

Produkten (B-027, PR-ITP1 v1.0) har tre storheter som aldrig får blandas ihop:
kundkapital `C` med direkt fördelad faktisk avkastning, garanterad pension `G` (0 % nettoränta,
dödlighet × 0,80) och produktens garantivärde `V_g`. Ingen av dem är FTA
(`aktuariell_grund.md` §1). En FTA kräver en egen **värderingsgrund** – här kallad
`SIM-V-2026-01` som arbetsnamn – med diskonteringskurva, bästa skattning eller försiktig
dödlighet, driftkostnadsantagande och skatt.

Metodalternativ (val för designstoppet, inte beslutade här):

| Alternativ | FTA per försäkring | För | Mot |
|---|---|---|---|
| **A** Garanterat åtagande + villkorad återbäring | FTA = garantins värde på värderingsgrunden; `C − FTA` redovisas som villkorad återbäring om positiv, annars som garantibrist mot bolagets kapital | Speglar traditionell försäkring; tydlig garantirisk | Kräver regel för fördelning av villkorad återbäring; C tillhör kunden i vår produkt |
| **B** Kundkapital med garantigolv *(rekommenderat som första steg)* | FTA = max(`C`, garantins värde på värderingsgrunden) + avsättning för framtida driftkostnader utöver avgiften | Följer produktens direkta fördelning; deterministisk; garantigapet blir ett eget, synligt tal | Fångar inte garantins tidsvärde |
| **C** B + tidsvärde för garantin | Som B plus marknadskonsistent värde av garantigolvet ur stokastiska räntescenarier | Mest riktigt ekonomiskt | Kräver scenariogenerator; senare |

Oavsett alternativ ska motorn lämna garantigapet `max(0, V_garanti − C)` per kohort. Det är
samma storhet som PR-028:s stressbuffert redan använder, men värderad på värderingsgrunden.

### 3.2 FTA-analys för vår produkt

Föreslagen stegordning. Varje steg räknas om i motorn, så att summan av stegen är exakt UB − IB:

| Steg | Orsak | FI-koppling (år) |
|---|---|---|
| 0 | IB = föregående låsta värderings UB (hård kontroll) | F1 |
| 1 | Inbetalda nettopremier och nya garantidelar | F2 |
| 2 | Utbetald pension och slutavräkningar | F3 |
| 3 | Kapitalavgift och avkastningsskattebelastning | F4 |
| 4 | Faktisk avkastning tillförd C, jämfört med diskonteringsränta | F5, E15–E16 |
| 5 | Ränteuppräkning (avveckling av diskontering) | F5 |
| 6 | Dödlighetsutfall: avgångar och arvsvinst (PR-010/011) | E1–E2, E29–E48 |
| 7 | Planändringar: uttagsstart, paus, deluttag, fribrev | E11 |
| 8 | Ändrat ränteantagande (ny kurva) | E17, F6 |
| 9 | Ändrade övriga antaganden (dödlighet, kostnad) | E11, F6 |
| 10 | Modell-, metod- och dataändringar (egen rad, aldrig gömd i oanalyserat) | – |
| 11 | Oanalyserat = UB − (IB + steg 1–10). Över tröskel → stopp och mänsklig granskning | E23 |
| 12 | UB = ny värdering | – |

Antagandeändringar (8–9) läggs sist så att de mäts på det faktiska beståndet vid periodens
slut. Ordningen ska vara fast och versionerad, eftersom den påverkar hur differensen fördelas.

### 3.3 FTA-bokföring för oss

Ekonomiteamet och huvudboken finns inte (V-10). Förslag till mellanläge: aktuarien tar fram ett
**avsättningsunderlag** med verifikationsförslag (period, post, belopp, underlagets
kontrollsumma) som godkänns av människa och sparas som underlag. När ekonomi byggs tar dess
bokföringstjänst emot samma underlag. Kontoplanen fastställs av ekonomi; aktuarien levererar
belopp per analyssteg, inte konton.

### 3.4 Simulering av antagandeändringar

Aktuarien och agenten ska kunna köra "tänk om"-scenarier mot en låst basvärdering:

| Scenariodimension | Exempel | Utfall |
|---|---|---|
| Diskonteringsränta | Parallellskift ±50/±100 bp, ny kurva, FI:s ändrade metod | ΔFTA, Δgarantigap, räntekänslighet (duration) |
| Dödlighet | −10/−20 % dödsrisk, annan förbättringstakt, annan unisexvikt | ΔFTA, livslängdsrisk, ΔPR-028-buffert |
| Kostnader | Driftkostnad +10 %, ändrad kapitalavgift (kräver PR-030-prövning) | Kostnadsresultat, avsättning för kostnader |
| Avkastning | Avkastningsbana 0/3/5 % eller chock −20 % aktier | Garantigap per kohort, kapitalbehov |
| Beteende | Andel tidiga uttag, tidsbegränsade uttag, pauser | Kassaflödesprofil, likviditet |
| Produktparametrar | Premieålder, satser, brytpunkter (finns i dag som premieeffekt) | Premieflöden och nya garantidelar |

Varje scenario är en versionerad specifikation med hash. Det skriver aldrig över basen och
visas alltid märkt som scenario. Resultatet är bas mot scenario per år och kohort, med samma
undertryckning av små celler som beståndsinsikten.

### 3.5 Databeroenden

En riktig FTA kräver garantidelar `G_j`, kundkapital `C` och pensionsplaner per försäkring. Det
är paket B (V-04–06) och ett avstämt startbestånd (S-04). I dag finns bara premiehistorik.

Två vägar:

1. **Vänta på paket B.** Rätt men långsamt.
2. **Uttryckligt rekonstruerat startbestånd (S-04) för simuleringen.** `G_j` räknas ur
   premiehistoriken med SIM-HIST-2023-01, som parameterregistret tillåter för uttryckligen
   omgenererad mockhistorik. `C` räknas med en deklarerad avkastningsserie. Resultatet märks
   som rekonstruerat och ersätts när paket B finns.

Avkastningen hämtas inte från kapitalförvaltningen (projekt 5), som är pausat. I sandboxen är
den versionerad scenarioindata som aktuarien äger tills kapitalteamet levererar.

---

## 4. Teamets harness

### 4.1 Agenter och människor

Följ B-008/B-026: skills före agenter.

| Roll | Typ | Mandat |
|---|---|---|
| **Ansvarig aktuarie / aktuariefunktion** | Människa (operatören eller utsedd person) | Fastställer värderingar, föreslår antaganden till styrelsen, signerar rapportunderlag. Nyckelfunktionen innehas aldrig av en agent |
| `actuary_agent` (finns) | Ledande agent | Kör värderingar, analyser och scenarier i betrodd kod, skriver utkast och underlag, svarar på frågor, tar emot delegeringar |
| `data_scientist` (planerad) | Specialist | Datakvalitet, erfarenhetsanalys, beståndsstatistik. Aggregat, ingen fri SQL |
| Granskning ("fyra ögon") | Skill, inte agent | Separat körning med annan leverantör (t.ex. modellroll `deep` hos den andra leverantören) som läser underlaget och letar avvikelser. Kvalitetskontroll som inte ersätter människans granskning |

Rekommendation: ingen egen agent för aktuariefunktionen nu. Granskning och oberoende ligger hos
människan, med second opinion-skillen som stöd.

### 4.2 Poddar och skills

Nya poddar (namn på svenska som i dag; skillnamn på engelska). Alla nya skills lämnar bara
aggregat. Individberäkningen sker i betrodd kod med teamets databasroll.

| Podd | Skill | Sidoeffekt | Föreslagen nivå | Vad den gör |
|---|---|---|---|---|
| `bestand` (finns) | `get_portfolio_snapshot` *(ny)* | read | AGENT | Bestånd per tillstånd (sparande, fribrev, utbetalning), kohort och åldersgrupp, med undertryckning |
| | `get_premium_flows` *(ny)* | read | AGENT | Premier, flytt in/ut per period och produktslag (underlag för FI avsnitt C) |
| `antaganden` *(ny)* | `list_valuation_bases`, `get_valuation_basis` | read | AGENT | Grunder med versioner, källor, kontrollsummor (SIM-G/B/R och värderingsgrunden) |
| | `propose_valuation_basis` | write | APPROVAL | Förslag till ny grundversion med motivering och känslighet. Gör inget gällande |
| | `adopt_valuation_basis` | write | HUMAN_ONLY | Införande efter styrelsebeslut (manuellt steg med beslutsreferens) |
| `aktuariell` *(ny, `harness.md` §9.2)* | `run_valuation` | compute | AGENT | Värderar ett bestånd per datum och grund. Skapar en oföränderlig körning med status *utkast* |
| | `lock_valuation` | write | HUMAN_ONLY | Fastställer värderingen för perioden; rättelse blir ny version |
| | `get_valuation_result` | read | AGENT | Resultat per kohort och tillstånd, kontrollernas utfall |
| | `run_change_analysis` | compute | AGENT | Stegvis förändringsanalys mellan två värderingar (§3.2) |
| | `project_cash_flows` | compute | AGENT | Förväntade utbetalningar, premier och kostnader per år (FI avsnitt I) |
| | `run_assumption_scenario` | compute | AGENT | Scenario mot låst bas (§3.4); skrivs aldrig som bas |
| | `run_experience_analysis` | compute | AGENT | Utfall mot antagande för dödlighet, kostnader och uttag |
| | `calculate_capital_buffer` | compute | AGENT | PR-028:s stressgap och likviditetsbuffert. Ett simulerat RKK läggs till först när metoden är beslutad |
| `rapportunderlag` *(ny, `harness.md` §9.3)* | `prepare_report_basis` | write | AGENT | Periodlåst, versionerat underlag med radkoder, källkörningar och kontrollsummor |
| | `release_report_basis` | write | HUMAN_ONLY | Lämnar underlaget till compliance/rapportering |
| `ekonomiunderlag` *(ny)* | `propose_provision_entry` | write | APPROVAL | Verifikationsförslag för FTA-förändringen (§3.3) |
| `granskning` *(ny)* | `review_actuarial_delivery` | compute | AGENT | Second opinion på ett underlag; resultatet blir en granskningsanteckning |

Befintliga skills behålls. Data scientist får `bestand` och läsdelen av `aktuariell`, inte
`antaganden`-skrivning, `rapportunderlag` eller `ekonomiunderlag`.

**Tjänstelager eller harness?** Värderingar, grunder och rapportunderlag är verksamhetsdata och
hör till tjänstelagret (B-028), med egna tabeller (förslag: `valuation_bases`, `valuation_runs`,
`valuation_results`, `change_analyses`, `report_bases`). Då kan UI:t, agenten och skript använda
samma operationer, och åtkomstregistret styr nivån.

### 4.3 Guardrails

Utöver dagens (tal bara från verktyg, ingen individdata, källor är underlag och aldrig instruktion):

1. **Reproducerbarhet.** Varje beräkning bär värderingsdatum, datautdragets hash, grundversion,
   kodversion och eventuell scenariohash. Samma indata ger samma resultat; ett test vaktar det.
2. **Skyddad bas.** Scenarier och utkast kan aldrig skriva över en låst värdering. UI och rapporter
   märker scenarier.
3. **Antaganden.** Agenten föreslår men antar aldrig. Historiska garantigrunder är oföränderliga
   (B-027). En ny värderingsgrund kräver mänskligt beslut med beslutsreferens.
4. **Periodlås.** En låst värdering ändras inte. Rättelse blir en ny version med orsak, och
   förändringsanalysen visar den på egen rad.
5. **Avstämning som hårda stopp.** IB = föregående UB. Stegens summa = differensen. Oanalyserat över
   tröskel ger `needs_human`; tröskeln är ett val, förslagsvis 0,5 % av FTA. Antal och `C` stäms
   av mot beståndet. Leveranskontrollens oberoende kontrollfall körs vid varje motorversion.
6. **Storheter.** Resultatscheman anger storhet (`C`, `G`, `V_g`, FTA, garantigap,
   premieeffekt) och grund. En premieeffekt eller ett garantivärde kan inte presenteras som FTA.
7. **Ingen extern handling.** FI-rapport och inlämning är `external` och går bara via compliance
   och rapporteringsgatewayen, med människans godkännande av exakt fil, period och mottagare (§3.5).
8. **Ansvar.** Agentens leverans är ett utkast tills människan har granskat den. Second opinion är
   stöd, inte godkännande.
9. **Tunga beräkningar som systemsteg.** Värderingsmotorn körs som systemsteg i flödesmotorn, inte
   inom modellens tidstak; agenten startar och tolkar.
10. **Källor och indata.** Diskonteringskurva, avkastningsserie och FI-parametrar är versionerad
    indata med källa och kontrolldatum, aldrig tal i en prompt.

### 4.4 Flöden

Återanvänd flödesmotorn (grindar binder underlagets hash):

| Flöde | Steg | Rytm |
|---|---|---|
| `valuation_close` | Datautdrag → kvalitetskontroll (system) → värdering (system) → förändringsanalys (system) → agentens kommentar och utkast → **G1 aktuarie granskar och låser** → avsättningsunderlag → **G2** → rapportunderlag till compliance | Kvartal, år |
| `assumption_review` | Erfarenhetsanalys → förslag till ny grund → känslighet mot bas → **G1 aktuarie** → styrelsebeslut (manuellt steg med referens) → införande med giltighetsdag | År, eller vid källändring |
| `product_report` | Datainsamling → beräkningar → utkast (agent) → second opinion → **G1** → leverans till VD/styrelse | År |
| `regulatory_basis` | Aktuariens rapportunderlag → compliance tillämplighetsprövning och sammanställning (rapporteringsagent) → **G** → inlämning via gateway (`external`) | Kvartal, år |
| `monthly_actuarial_check` | PR-028-buffert, arvsvinst- och avgiftskontroll → avvikelser till ledningsunderlag | Månad, efter paket B |

Scenarier är inget flöde. De körs interaktivt i arbetsytan och kan sparas och bifogas till en
rapport eller ett ledningsunderlag.

### 4.5 Delegering

- Finns: compliance → aktuarie (B-039).
- Föreslaget: rapportering (compliance) → aktuarie för rapportunderlag, aktuarie → data scientist,
  och senare aktuarie ↔ ekonomi och aktuarie ↔ kapital (ALM, när projekt 5 återupptas).

---

## 5. Arbetsyta för en mänsklig aktuarie (`/team/aktuarie`)

Enligt B-017/§3.7 ska människan kunna göra allt agenten kan, genom samma tjänsteoperationer.
Teamytan blir aktuariens arbetsplats inom OC-8:s plattform, i Digital klarhet. I teamytan nås bara
teamets egen agent (B-036). Dagens uppdragssidor behålls under *Uppdrag*.

### 5.1 Sidor

| Sida | Innehåll | Handlingar |
|---|---|---|
| **Översikt** | Årshjul med kommande leveranser och FI-frister; senaste låsta värdering; nyckeltal (FTA, kundkapital, garantigap, buffert, oanalyserat); öppna avvikelser; väntande granskningar | Starta periodens flöde |
| **Värderingar** | Lista per datum och grund med status (utkast, låst, rättad); detalj med indata och hashar, resultat per kohort och tillstånd, kontrollernas utfall | Kör värdering, jämför, lås (grind) |
| **FTA-analys** | Vattenfall IB → steg 1–11 → UB, med FI-radkoppling; klick ner till kohort; oanalyserat markerat | Kommentera steg, godkänn analys |
| **Bokföringsunderlag** | Avsättningsunderlag per period, verifikationsförslag, status och avstämning | Godkänn eller avslå förslag |
| **Antaganden** | Grunder och versioner, diff mellan versioner, källor; erfarenhetsanalys | Skapa förslag, se känslighet, för in styrelsebeslut |
| **Scenarier** | Välj bas; skjutreglage och fält för ränta, dödlighet, kostnad, avkastning och beteende; resultat bas mot scenario | Kör, spara, bifoga till rapport |
| **Rapporter** | Katalog: produktrapport, FTA-rapport per kvartal, FI-underlag (kvartal och år), aktuariefunktionens rapport, ERS-underlag; status och versioner | Skapa utkast (själv eller agent), granska, lämna till compliance |
| **Data och kvalitet** | Datautdrag, kontroller och avvikelser | Godkänn utdrag, flagga fel |
| **Uppdrag** (finns) | Frågor till aktuarieagenten, körningar och journal, spåret *Så togs rapporten fram* | Ge uppdrag, följ, granska |

### 5.2 Skiss: FTA-analys

```text
┌ Aktuarie ─ FTA-analys ────────────────── Period: 2026-Q4 ▾  Grund: SIM-V-2026-01 v1 ┐
│ IB 2026-09-30   41,2 Mkr   ✓ = UB föregående låsta värdering                        │
│                                                                                     │
│  IB ████████████████████████████████████ 41,2                                       │
│  + Premier          ███ +3,1                                     F2                 │
│  − Utbetalningar    █ −0,4                                       F3                 │
│  − Avgifter/skatt   ▏ −0,1                                       F4                 │
│  + Avkastning       ██ +1,2                                      F5                 │
│  ± Dödlighet        ▏ ±0,0                                       E1–E2              │
│  ± Ränteantagande   █ −0,6                                       E17/F6             │
│  ± Oanalyserat      ▏ 0,02  (0,05 % ✓ under tröskel 0,5 %)       E23                │
│  UB ███████████████████████████████████████ 44,4                                    │
│                                                                                     │
│ Kontroller: 7/7 ✓    Agentens kommentar (utkast) ▸    Second opinion: 0 avvikelser  │
│ [Jämför med föregående kvartal]  [Öppna kohort]       [Godkänn och lås – G1]        │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

Talen är påhittade för skissen.

### 5.3 Skiss: Scenarier

```text
┌ Aktuarie ─ Scenarier ─────────────── Bas: värdering 2026-12-31 (låst) ──────────────┐
│ Diskonteringsränta  [−100 ─────●───── +100] bp   −50                                │
│ Dödsrisk            [−20 % ──●─────── +20 %]     −10 %                              │
│ Driftkostnad        [ 0 % ●────────── +50 %]      0 %                               │
│ Avkastningsbana     (●) 3 %  ( ) 0 %  ( ) chock −20 % aktier                        │
│ [Kör scenario]                                    Scenario S-2026-014 · hash 9f3c…  │
│                                                                                     │
│              Bas      Scenario    Δ                                                 │
│ FTA          44,4     46,1       +1,7  Mkr                                          │
│ Garantigap    0,3      0,9       +0,6  Mkr   (kohort 1959–62: dold < 10)            │
│ PR-028-buff.  2,1      2,8       +0,7  Mkr                                          │
│ [Spara]  [Bifoga till rapport]  [Be agenten förklara]          SCENARIO – ej bas    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Kopplingen till compliance och rapportering

Arbetsdelningen följer `harness.md` §9.3. **Aktuarien äger siffrorna, compliance och
rapporteringsagenten äger rapporten och inlämningen.**

```text
aktuarie                               compliance (rapporteringsagent)            FI
valuation_close → låst värdering
                → rapportunderlag ──►  tillämplighet, formkrav, sammanställning
                  (radkoder, period,   mot FFFS 2019:22 → G (människa) ─────────► inlämning
                   källkörningar,      (external, gateway)
                   kontrollsummor)
                ◄── frågor/avvikelser (delegering rapportering → aktuarie)
```

Kontraktet för ett rapportunderlag (förslag): rapport-id, period, version, rader
(radkod, belopp, enhet, källa = värderings- eller analyskörning), kontroller med utfall, ansvarig
och status (*utkast*, *släppt*, *ersatt*). Compliance prövar tillämpligheten (t.ex. om avsnitt G
gäller en produkt med direkt avkastningsfördelning) innan raden krävs av aktuarien.

---

## 7. Produktrapporten

Förslag till innehåll: en årlig **produktrapport för PR-ITP1** som förenar produktöversynen
(produktstyrning: fungerar produkten för målgruppen?) med aktuariell uppföljning (bär produkten
sig?). Mottagare VD och styrelse; underlag till compliance.

| Avsnitt | Innehåll | Kan tas fram i dag? |
|---|---|---|
| 1. Sammanfattning | Slutsatser och rekommendationer först | Agentens utkast |
| 2. Bestånd och rörelser | Antal per tillstånd, in- och utträden, fribrev, åldersfördelning | 🟡 Delvis (`get_company_metrics`; snapshot per tillstånd behövs) |
| 3. Premier | Premievolym per år och månad, premietrappans fördelning, avvikelser | 🟡 Delvis (betalmarkerade premier) |
| 4. Kapital och avkastning | Kundkapital, levererad avkastning, jämförelse med prognos 0/3/5 % | 🔲 Kräver `C` (paket B eller S-04) |
| 5. Avgifter och kostnader | Avgiftsintäkt mot driftkostnad, kostnadsresultat | 🔲 Kräver ekonomi |
| 6. Garanti | Garantinivå, garantigap per kohort, PR-028-buffert | 🔲 Kräver `G_j` och motor |
| 7. Risk- och dödlighetsutfall | Arvsvinster, utfall mot antagande | 🔲 Kräver utbetalningar och dödsfall |
| 8. Känslighet | Scenarier enligt §3.4 | 🟡 Endast produktparametrar i dag |
| 9. Kundutfall och värde | Prognostiserad pension per typfall, kostnadsandel, informationsbesked | 🟡 Typfall ur premiemotorn |
| 10. Avvikelser och åtgärder | Regeländringar, klagomål, föreslagna ändringar (PR-030) | 🟡 Källbevakning finns delvis |

Ej beräknade avsnitt visas som *ej beräknat* med orsak, aldrig som noll. En första version med
avsnitt 1–3, 8 och 9 kan tas fram av aktuarieteamet utan ny motor. Det ger en rapport som
fungerar redan nu och fylls på när motorerna kommer.

---

## 8. Föreslagen byggordning

Förslaget startar inget bygge och ändrar inte prioriteringen i ATT_GORA (OC-3a är närmast).

| Steg | Leverans | Beroenden | Kan börja |
|---|---|---|---|
| **A0** | Designstopp *aktuarieteamets harness och arbetsyta* med val enligt §9 | Detta dokument | Efter dina svar |
| **A1** | Värderings- och förklaringskontrakt (projektplanens första kontraktsarbete) | A0 | Direkt efter A0 |
| **A2** | Produktrapport v0 (avsnitt 1–3, 8, 9) och `get_portfolio_snapshot`, `get_premium_flows` | Befintliga data | Parallellt med A1 |
| **A3** | Teamyta v1: översikt, rapporter och uppdrag på befintliga data | OC-8, A2 | Efter A2 |
| **A4** | Antagandebibliotek som data (`valuation_bases`) med förslag och införande | A1 | Efter A1 |
| **A5** | Startbestånd med `G_j` och `C` (rekonstruerat S-04 eller paket B) | A1, val Q4 | Efter beslut |
| **A6** | Värderingsmotor med kontrollfall, `valuation_runs`, `lock_valuation` | A4, A5 | |
| **A7** | Förändringsanalys och scenariomotor; sidorna FTA-analys och Scenarier | A6 | |
| **A8** | Flödet `valuation_close`, avsättningsunderlag och rapportunderlag till compliance | A7, compliancekontrakt | |
| **A9** | Kassaflödesprognos, erfarenhetsanalys, `assumption_review`, data scientist-agent | A6 | |
| **A10** | Simulerat RKK och ERS-underlag | FI-kalibrering, beslut | Senare |

---

## 9. Öppna frågor till operatören

| Nr | Fråga | Rekommendation |
|---|---|---|
| Q1 | FTA-metod för produkten (§3.1) | B först, C som senare utbyggnad |
| Q2 | Rapporteringsnivå: verklig storlek (under trösklarna) eller "som om" större bolag, för att öva full kvartals- och EU-rapportering? | Verklig storlek, med rapportnivån som parameter |
| Q3 | Vad avses med produktrapport: förslaget i §7, eller en annan rapport (t.ex. FI avsnitt C per produkt)? | §7 |
| Q4 | Startbestånd: vänta på paket B eller rekonstruera `G_j`/`C` som märkt S-04? | Rekonstruera, märkt och ersättningsbart |
| Q5 | Vem är ansvarig aktuarie och aktuariefunktion i simuleringen – du, eller en utsedd fiktiv roll med din inloggning? | Du som operatör, med rollen i sessionen |
| Q6 | Diskonteringskurva: simulerad FI-kurva som versionerad indata nu, eller vänta på marknadsdata? | Versionerad indata nu; FI:s metodändring 2026 prövas av compliance |
| Q7 | Ny agent för aktuariefunktionen, eller granskningsskill + människa (§4.1)? | Skill + människa |

Efter svaren formuleras A0 som beslutsförslag med valbara alternativ. Ingen post i BESLUTSLOGG
skrivs utan ditt godkännande.

---

## 10. Källor

- [FFFS 2019:22 på lagen.nu](https://lagen.nu/fffs/2019:22) – kapitel, avsnitt, frister och
  trösklar (sammanställt 2026-10-31; ska kontrolleras mot den konsoliderade versionen på fi.se)
- [FI: FFFS 2019:22 i registret](https://www.fi.se/sv/vara-register/fffs/sok-fffs/2019/201922/)
- [FFFS 2019:21 på lagen.nu](https://lagen.nu/fffs/2019:21) och
  [FPK:s aktuariella antaganden](https://lawinsider.com/sv/contracts/2or5sm5JCAh) – diskontering med swapräntor, negativa räntor
- [Alecta: försäkringstekniska riktlinjer](https://www.alecta.se/media/f5inriwi/forsakringstekniska-riktlinjer.pdf)
  och [KPA: försäkringstekniska riktlinjer](https://kpa.se/globalassets/trycksaker/kpa-tjanstepensionsforsakring---ftr---2026-01-01---oppen.pdf) – styrelsens beslut, aktuariefunktionens förslag
- [FI: kalibreringar RKK tjänstepension](https://www.fi.se/contentassets/77f3d56daed74051aed8044001cdcd37/kalibreringar-rkk-tjanstepension-ver-02.pdf) – riskkänsligt kapitalkrav
- [Realtid 2026-06-16: FI ändrar regler för tjänstepension](https://www.realtid.se/bors-finans/fi-andrar-regler-tjanstepension/) – ändrad metod för diskonteringsräntan (ej kontrollerad mot FI)
- [EIOPA/ECB: instruktioner för pensionsmallar](https://data.ecb.europa.eu/sites/default/files/2025-05/PensionFunds_instructions_ECB_add-on.pdf) – PF.29.05, PF.29.06
- [Milliman: analysis of change](https://us.milliman.com/en/insight/ifrs-statement-of-comprehensive-income) – stegvis förändringsanalys och avvikelsetyper
- [FI: produktgodkännande (FI-tillsyn 27)](https://www.fi.se/en/published/reports/supervision-reports/2023/fi-supervision-27-non-life-insurance-undertakings-product-approval-processes/) – produktöversyn (skadeförsäkring, används som analogi)
- Interna: `01_domän/aktuariell_grund.md`, `PARAMETERREGISTER.md`, PR-ITP1-020/021/022/028,
  `02_system/harness.md` §9.2–9.3, `01_domän/processer_översikt.md` V-10–12, B-026, B-027,
  B-036, B-037, B-039, B-041
