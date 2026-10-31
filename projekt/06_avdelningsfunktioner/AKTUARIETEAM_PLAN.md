# Aktuarieteamet – arbetssätt, harness och arbetsyta (utredning och planförslag)

> **Version:** 0.2 | **Datum:** 2026-10-31 | **Status:** Utredning och förslag. Inget beslut,
> ingen kod, ingen ny behörighet. Operatörens svar på Q1–Q7 (2026-10-31) är inarbetade och
> [designstoppet A0](AKTUARIETEAM_BESLUTSFORSLAG.md) är godkänt och loggat som **B-042**.
> Kontraktet A1 finns i [VARDERINGSKONTRAKT.md](VARDERINGSKONTRAKT.md).
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

**Operatörens val 2026-10-31: efterlikna Alecta.** Det motsvarar alternativ A nedan.
Alectas försäkringstekniska riktlinjer (beslutade av styrelsen 2025-12-18) och
årsredovisningen för 2025 beskriver metoden för Alecta Optimal Pension, som är premiebestämd
traditionell ITP1-försäkring:

- **FTA är prospektiv och avser bara garantin.** Avsättningen är kapitalvärdet av det
  garanterade försäkringsåtagandet (riktlinjerna §4). Den beräknas med aktsamma antaganden och
  på samma sätt för solvens och redovisning. Diskontering sker med en räntekurva enligt 4 kap.
  i FFFS 2019:21. Kapitalvärdet av framtida driftskostnader och avkastningsskatt ingår, liksom
  optioner (flytt, ändrad uttagsålder, premieupphörande) när de är materiella.
- **Pensionskapitalet är retrospektivt.** Retrospektivreserven byggs månadsvis med premier,
  återbäringsränta ur faktisk totalavkastning, belastning för avkastningsskatt och
  driftskostnader samt arvsvinst (§6.2.2). Överskottet fördelas preliminärt enligt
  kontributionsprincipen och betalas ut som tilläggsbelopp: kapitalet fördelat med
  prognosantaganden minus garanterad pension, lägst noll (§6.2, §6.2.3).
- **Överskottet över garantin är inte garanterat.** Alecta är ömsesidigt och redovisar det som
  preliminärt fördelad återbäring i eget kapital (årsredovisningen, not 1).
- **Kollektiv konsolideringsnivå.** Marknadsvärdet av fördelningsbara tillgångar delat med
  kundernas samlade pensionskapital plus underskott till följd av garanti. Målet är 100 % med
  intervallet 98–102 % (§6.2.1).
- **Flytt och återköp.** Värdet är pensionskapitalet, lägst kapitalvärdet av den garanterade
  förmånen (§5.1, §5.4).
- **FTA-förändringen förklaras per orsak** i förvaltningsberättelsen: premier och utbetalningar,
  skillnaden mellan premiegrunder och avsättningsantaganden, ändrad räntekurva, löpande
  förräntning efter frigjord skatt och driftskostnader, nya dödlighetsantaganden och övrigt.

Vår produkt har redan samma retrospektiva sida: `C` med direkt fördelad faktisk avkastning
(PR-020/021). Det som tillkommer är den prospektiva FTA-värderingen av garantin på en egen
värderingsgrund.

| Alternativ | FTA per försäkring | Status |
|---|---|---|
| **A** Garanterat åtagande + villkorad återbäring (Alecta-modellen) | Kapitalvärdet av garanterad pension `G` på värderingsgrunden (FI-kurva, aktsam dödlighet, driftskostnader, avkastningsskatt) | **Beslutat, B-042** |
| B Kundkapital med garantigolv | max(`C`, garantins värde) | Ej valt |
| C A + garantins tidsvärde | Stokastisk värdering av garantin | Möjlig senare utbyggnad |

**Storheterna i alternativ A:**

```text
FTA_i  = kapitalvärdet av G_i på SIM-V (prospektivt)
VÅ_i   = max(0, C_i − FTA_i)     villkorad återbäring, inte garanterad
U_i    = max(0, FTA_i − C_i)     underskott till följd av garanti, bärs av bolagets kapital (PR-028)
Konsolideringsnivå = fördelningsbara tillgångar / (Σ C_i + Σ U_i)
```

Faktisk avkastning påverkar alltså `C` och därmed villkorad återbäring, men inte FTA. FTA rör
sig med nya garantidelar, utbetalningar, förräntning, dödlighet och antaganden.

**Redovisning (operatörens val Q1b).** Bolaget har en ägare som skjuter till kapital (PR-028)
och liknar därför ett aktiebolag. Villkorad återbäring redovisas som en egen post bland
skulderna, skild från eget kapital. Det skiljer sig från Alecta, som är ömsesidigt.

**Följder för produktdokumenten** (flaggas här men ändras inte): `aktuariell_grund.md` §1 och
PR-ITP1-021 kallar hela `C` kundkapital. Med alternativ A är `C − FTA` villkorad återbäring,
alltså inte garanterad. Det stämmer med PR-021 ("ingen individuell rätt till en viss framtida
avkastning"), men begreppet bör stämmas av i villkoren (§4–6) och kundinformationen innan
FTA-motorn byggs. Den ändringen hör till projekt 4. Konsolideringsnivån kräver en tillgångssida,
som saknas så länge kapitalförvaltningen är pausad. Tills dess visas nivån som *ej beräknad*.

### 3.2 FTA-analys för vår produkt

Stegordningen följer Alectas förklaring av FTA-förändringen. Varje steg räknas om i motorn
så att stegens summa är exakt UB − IB:

| Steg | Orsak | FI-koppling (år) |
|---|---|---|
| 0 | IB = föregående låsta värderings UB (hård kontroll) | F1 |
| 1 | Premier: nya garantidelar värderade på FTA-grunden | F2 |
| 2 | Skillnad mellan garantigrunden (SIM-G, 0 % ränta) och FTA-grunden för nya garantidelar | E8 |
| 3 | Utbetald garanterad pension och slutavräkningar | F3 |
| 4 | Löpande förräntning efter frigjord avkastningsskatt och driftskostnader | F4, F5 |
| 5 | Dödlighetsresultat: avgångar och frigjord avsättning | E1–E2, E29–E48 |
| 6 | Planändringar: uttagsstart, paus, deluttag | E11 |
| 7 | Ändrad diskonteringsränta (ny kurva) | E17, F6 |
| 8 | Ändrade övriga antaganden (dödlighet, kostnad, skatt) | E11, F6 |
| 9 | Modell-, metod- och dataändringar (egen rad, aldrig gömd i oanalyserat) | – |
| 10 | Oanalyserat = UB − (IB + steg 1–9). Över tröskel → stopp och mänsklig granskning | E23 |
| 11 | UB = ny värdering | – |

Antagandeändringar (7–8) läggs sist så att de mäts på beståndet vid periodens slut. Ordningen
är fast och versionerad, eftersom den påverkar hur differensen fördelas.

**Avstämning av villkorad återbäring.** Bredvid FTA-analysen visas pensionskapitalets rörelse:
premier, återbäringsränta (faktisk avkastning), avgifter och skatt, utbetalningar och arvsvinst.
Kontrollen är att `ΣVÅ − ΣU = ΣC − FTA` vid både IB och UB.

### 3.3 FTA-bokföring för oss

Ekonomiteamet och huvudboken finns inte (V-10). Förslag till mellanläge: aktuarien tar fram ett
**avsättningsunderlag** med verifikationsförslag (period, post, belopp, underlagets
kontrollsumma) som godkänns av människa och sparas som underlag. När ekonomi byggs tar dess
bokföringstjänst emot samma underlag. Kontoplanen fastställs av ekonomi; aktuarien levererar
belopp per analyssteg, inte konton. Underlaget har två delar: förändring i
livförsäkringsavsättning (FTA) och förändring i villkorad återbäring.

### 3.4 Simulering av antagandeändringar

Aktuarien och agenten ska kunna köra "tänk om"-scenarier mot en låst basvärdering:

| Scenariodimension | Exempel | Utfall |
|---|---|---|
| Diskonteringsränta | Parallellskift ±50/±100 bp, ny kurva, FI:s ändrade metod | ΔFTA, Δvillkorad återbäring, Δunderskott, räntekänslighet (duration) |
| Dödlighet | −10/−20 % dödsrisk, annan förbättringstakt, annan unisexvikt | ΔFTA, livslängdsrisk, ΔPR-028-buffert |
| Kostnader | Driftkostnad +10 %, ändrad kapitalavgift (kräver PR-030-prövning) | Kostnadsresultat, avsättning för kostnader |
| Avkastning | Avkastningsbana 0/3/5 % eller chock −20 % aktier | `C`, villkorad återbäring och underskott per kohort, kapitalbehov (FTA påverkas inte) |
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
6. **Storheter.** Resultatscheman anger storhet (`C`, `G`, `V_g`, FTA, villkorad återbäring,
   underskott, premieeffekt) och grund. En premieeffekt eller ett garantivärde kan inte
   presenteras som FTA.
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

**Klickbar skiss:** [aktuarie-arbetsyta.html](aktuarie-arbetsyta.html) visar alla nio sidor
i ett påhittat exempelläge (20 januari 2027) med syntetiska tal. Den är en designreferens
som inte skriver något, inte kör någon agent och inte är kopplad till systemet.

### 5.1 Sidor

| Sida | Innehåll | Handlingar |
|---|---|---|
| **Översikt** | Årshjul med kommande leveranser och FI-frister; senaste låsta värdering; nyckeltal (FTA, villkorad återbäring, underskott till följd av garanti, oanalyserat, konsolideringsnivå); öppna avvikelser; väntande granskningar | Starta periodens flöde |
| **Värderingar** | Lista per datum och grund med status (utkast, låst, rättad); detalj med indata och hashar, resultat per kohort och tillstånd, kontrollernas utfall | Kör värdering, jämför, lås (grind) |
| **FTA-analys** | Vattenfall IB → steg 1–10 → UB, med FI-radkoppling; avstämning av villkorad återbäring; klick ner till kohort; oanalyserat markerat | Kommentera steg, godkänn analys |
| **Bokföringsunderlag** | Avsättningsunderlag per period, verifikationsförslag, status och avstämning | Godkänn eller avslå förslag |
| **Antaganden** | Grunder och versioner, diff mellan versioner, källor; erfarenhetsanalys | Skapa förslag, se känslighet, för in styrelsebeslut |
| **Scenarier** | Välj bas; skjutreglage och fält för ränta, dödlighet, kostnad, avkastning och beteende; resultat bas mot scenario | Kör, spara, bifoga till rapport |
| **Rapporter** | Katalog: produktrapport, FTA-rapport per kvartal, FI-underlag (kvartal och år), aktuariefunktionens rapport, ERS-underlag; status och versioner | Skapa utkast (själv eller agent), granska, lämna till compliance |
| **Data och kvalitet** | Datautdrag, kontroller och avvikelser | Godkänn utdrag, flagga fel |
| **Uppdrag** (finns) | Frågor till aktuarieagenten, körningar och journal, spåret *Så togs rapporten fram* | Ge uppdrag, följ, granska |

### 5.2 Skiss: FTA-analys

```text
┌ Aktuarie ─ FTA-analys ────────────────── Period: 2026-Q4 ▾  Grund: SIM-V-2026-01 v1 ┐
│ IB 2026-09-30   29,8 Mkr   ✓ = UB föregående låsta värdering                        │
│                                                                                     │
│  IB ██████████████████████████████ 29,8                                             │
│  + Premier (nya garantidelar)  ███ +3,1                          F2                 │
│  − Garantigrund → FTA-grund    █ −1,05                           E8                 │
│  − Utbetald pension            ▏ −0,3                            F3                 │
│  + Förräntning                 ▏ +0,2                            F4/F5              │
│  ± Dödlighet                   ▏ ±0,0                            E1–E2              │
│  + Ändrad ränta                ▏ +0,4                            E17/F6             │
│  ± Oanalyserat                 ▏ 0,05 (0,16 % ✓ under 0,5 %)     E23                │
│  UB ████████████████████████████████ 32,2                                           │
│                                                                                     │
│ Villkorad återbäring 11,4 → 12,2 · underskott 0,25 → 0,30 · ΣVÅ − ΣU = ΣC − FTA ✓   │
│ Kontroller: 7/7 ✓    Agentens kommentar (utkast) ▸    Second opinion: 0 avvikelser  │
│ [Jämför med föregående kvartal]  [Öppna kohort]       [Godkänn och lås – G1]        │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

Talen är påhittade för skissen.

### 5.3 Skiss: Scenarier

```text
┌ Aktuarie ─ Scenarier ─────────────── Bas: värdering 2026-09-30 (låst) ──────────────┐
│ Diskonteringsränta  [−100 ─────●───── +100] bp   −50                                │
│ Dödsrisk            [−20 % ──●─────── +20 %]     −10 %                              │
│ Driftkostnad        [ 0 % ●────────── +50 %]      0 %                               │
│ Avkastningsbana     (●) 3 %  ( ) 0 %  ( ) chock −20 % aktier                        │
│ [Kör scenario]                                    Scenario S-2027-014 · hash 9f3c…  │
│                                                                                     │
│                        Bas    Scenario    Δ                                         │
│ FTA                    29,8    33,1      +3,3  Mkr                                  │
│ Villkorad återbäring   11,4     8,2      −3,2  Mkr                                  │
│ Underskott (garanti)    0,25    0,42     +0,17 Mkr  (kohort 1959–62: dold < 10)     │
│ Konsolideringsnivå     ej beräknad – tillgångssidan saknas                          │
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
| 2. Bestånd och rörelser | Antal per tillstånd, in- och utträden, fribrev, åldersfördelning | ✅ `get_portfolio_snapshot` (A2) |
| 3. Premier | Premievolym per år och månad, premietrappans fördelning, avvikelser | ✅ `get_premium_flows` (A2); premietrappans fördelning återstår |
| 4. Kapital och avkastning | Kundkapital, levererad avkastning, jämförelse med prognos 0/3/5 % | 🔲 Kräver `C` (paket B eller S-04) |
| 5. Avgifter och kostnader | Avgiftsintäkt mot driftkostnad, kostnadsresultat | 🔲 Kräver ekonomi |
| 6. Garanti och återbäring | Garantinivå, FTA, villkorad återbäring och underskott per kohort, PR-028-buffert | 🔲 Kräver `G_j` och motor |
| 7. Risk- och dödlighetsutfall | Arvsvinster, utfall mot antagande | 🔲 Kräver utbetalningar och dödsfall |
| 8. Känslighet | Scenarier enligt §3.4 | 🟡 Premiesatsen under brytpunkten +0,5 procentenhet (A2); värderingskänslighet efter A7 |
| 9. Kundutfall och värde | Prognostiserad pension per typfall, kostnadsandel, informationsbesked | 🟡 Premie per typlön (A2); prognostiserad pension återstår |
| 10. Avvikelser och åtgärder | Regeländringar, klagomål, föreslagna ändringar (PR-030) | 🟡 Källbevakning finns delvis |

Ej beräknade avsnitt visas som *ej beräknat* med orsak, aldrig som noll. En första version med
avsnitt 1–3, 8 och 9 kan tas fram av aktuarieteamet utan ny motor. Det ger en rapport som
fungerar redan nu och fylls på när motorerna kommer.

---

## 8. Föreslagen byggordning

Förslaget startar inget bygge och ändrar inte prioriteringen i ATT_GORA (OC-3a är närmast).

| Steg | Leverans | Beroenden | Kan börja |
|---|---|---|---|
| **A0** | Designstopp: [beslutsförslag](AKTUARIETEAM_BESLUTSFORSLAG.md) | Detta dokument | ✅ Godkänt 2026-10-31 (B-042) |
| **A1** | [Värderings- och förklaringskontrakt](VARDERINGSKONTRAKT.md) (projektplanens första kontraktsarbete) | A0 | ✅ Fastställt 2026-10-31 |
| **A2** | Produktrapport v0 (avsnitt 1–3, 8, 9) och `get_portfolio_snapshot`, `get_premium_flows` | Befintliga data | ✅ Byggt och testat lokalt 2026-10-31: flödet `product_report` och adaptern `ProductReportConsole`. Postgres-proven godkända 2026-10-31 mot `svc_test` (79 av 79, inklusive operationerna med rollen `agent_aktuarie`). Röktest mot riktig modell godkänt samma dag: `claude-opus-5` i demo med `--avvikelser`, 23 av 23 kontroller, 0,34 USD (`scripts/diagnostics/smoke_test_product_report.py`). Vyerna kommer i A3 |
| **A3** | Teamyta v1: översikt, rapporter och uppdrag på befintliga data | OC-8, A2 | Efter A2 |
| **A4** | Antagandebibliotek som data (`valuation_bases`) med förslag och införande | A1 | ✅ Byggt och testat lokalt 2026-10-31: tabell, fem operationer, podden `antaganden` (läsning) och startgrunderna. Postgres-proven godkända mot `svc_test` (migrationen och rollen `agent_aktuarie`). Skapat i Lakebase 2026-10-31 efter backup och OK, och läsrätten verifierad med rollens anslutning. Agentens förslagsväg öppnas i A9 |
| **A5** | Rekonstruerat startbestånd S-04 med `G_j` och `C` (svar Q4) | A1 | Efter A1 |
| **A6** | Värderingsmotor med kontrollfall, `valuation_runs`, `lock_valuation` | A4, A5 | |
| **A7** | Förändringsanalys och scenariomotor; sidorna FTA-analys och Scenarier | A6 | |
| **A8** | Flödet `valuation_close`, avsättningsunderlag och rapportunderlag till compliance | A7, compliancekontrakt | |
| **A9** | Kassaflödesprognos, erfarenhetsanalys, `assumption_review`, data scientist-agent | A6 | |
| **A10** | Simulerat RKK och ERS-underlag | FI-kalibrering, beslut | Senare |

---

## 9. Operatörens svar 2026-10-31

| Nr | Fråga | Svar |
|---|---|---|
| Q1 | FTA-metod | Efterlikna Alecta: garanterat åtagande + villkorad återbäring (alternativ A, §3.1) |
| Q1b | Var redovisas överskottet över garantin? | Villkorad återbäring som skuld, eftersom bolaget har en ägare (PR-028) |
| Q2 | Rapporteringsnivå mot FI | Verklig storlek, med rapportnivån som parameter |
| Q3 | Produktrapport | Förslaget i §7 |
| Q4 | Startbestånd | Rekonstruera `G_j` och `C` som märkt S-04, ersätts när paket B finns |
| Q5 | Ansvarig aktuarie och aktuariefunktion | Operatören (Karl), med rollen i sessionen |
| Q6 | Diskonteringskurva | Versionerad indata nu; compliance prövar FI:s metodändring 2026 som källändring |
| Q7 | Aktuariefunktionens granskning | Granskningsskill + människa, ingen egen agent |

Svaren låg till grund för [beslutsförslaget A0](AKTUARIETEAM_BESLUTSFORSLAG.md), som operatören
godkände 2026-10-31. Beslutet är loggat som B-042.

---

## 10. Källor

- [FFFS 2019:22 på lagen.nu](https://lagen.nu/fffs/2019:22) – kapitel, avsnitt, frister och
  trösklar (sammanställt 2026-10-31; ska kontrolleras mot den konsoliderade versionen på fi.se)
- [FI: FFFS 2019:22 i registret](https://www.fi.se/sv/vara-register/fffs/sok-fffs/2019/201922/)
- [FFFS 2019:21 på lagen.nu](https://lagen.nu/fffs/2019:21) och
  [FPK:s aktuariella antaganden](https://lawinsider.com/sv/contracts/2or5sm5JCAh) – diskontering med swapräntor, negativa räntor
- [Alecta: försäkringstekniska riktlinjer](https://www.alecta.se/media/f5inriwi/forsakringstekniska-riktlinjer.pdf),
  beslutade av styrelsen 2025-12-18 – §4 FTA, §5 återköp och flytt, §6.2 premiebestämd
  försäkring och retrospektivreserv
- [Alecta: års- och hållbarhetsredovisning 2025](https://www.alecta.se/media/kgfg3n0t/alectas-ars-och-hallbarhetsredovisning-2025.pdf)
  – förklaring av FTA-förändringen, konsolideringsnivå, not 1 om över- och underskott
- [KPA: försäkringstekniska riktlinjer](https://kpa.se/globalassets/trycksaker/kpa-tjanstepensionsforsakring---ftr---2026-01-01---oppen.pdf) – styrelsens beslut, aktuariefunktionens förslag
- [FI: kalibreringar RKK tjänstepension](https://www.fi.se/contentassets/77f3d56daed74051aed8044001cdcd37/kalibreringar-rkk-tjanstepension-ver-02.pdf) – riskkänsligt kapitalkrav
- [Realtid 2026-06-16: FI ändrar regler för tjänstepension](https://www.realtid.se/bors-finans/fi-andrar-regler-tjanstepension/) – ändrad metod för diskonteringsräntan (ej kontrollerad mot FI)
- [EIOPA/ECB: instruktioner för pensionsmallar](https://data.ecb.europa.eu/sites/default/files/2025-05/PensionFunds_instructions_ECB_add-on.pdf) – PF.29.05, PF.29.06
- [Milliman: analysis of change](https://us.milliman.com/en/insight/ifrs-statement-of-comprehensive-income) – stegvis förändringsanalys och avvikelsetyper
- [FI: produktgodkännande (FI-tillsyn 27)](https://www.fi.se/en/published/reports/supervision-reports/2023/fi-supervision-27-non-life-insurance-undertakings-product-approval-processes/) – produktöversyn (skadeförsäkring, används som analogi)
- Interna: `01_domän/aktuariell_grund.md`, `PARAMETERREGISTER.md`, PR-ITP1-020/021/022/028,
  `02_system/harness.md` §9.2–9.3, `01_domän/processer_översikt.md` V-10–12, B-026, B-027,
  B-036, B-037, B-039, B-041
