# MASTER_CONTEXT – ITP1 Administrationsplattform

> Detta dokument är projektets fundament. Läs det innan du gör något annat i projektet.
> Uppdatera det löpande när beslut fattas eller scope förändras.

---

## 1. Vision och syfte

Målet är att bygga ett komplett, simulerat tjänstepensionsbolag som administrerar **en enda produkt: ålderspension inom kollektivavtalet ITP1**. Bolaget ska kunna drivas av en enda person med stöd av AI-agenter och automatiserade system.

Detta är en **sandbox/simuleringsmiljö** – inga riktiga kunder, inget riktigt kapital. Syftet är att bygga fungerande processer, system och agenter som speglar hur ett verkligt bolag fungerar.

**Programvision (B-024, B-037):** Målet är ett **artificiellt men hypotetiskt fungerande, AI-native tjänstepensionsföretag**. Agentteam utför det löpande arbete som avdelningarna i ett riktigt bolag skulle göra (handläggning, kapitalförvaltning, aktuariellt arbete, regelefterlevnad, rapportering, kundkommunikation). System och data byggs för att vara tillgängliga för behöriga AI-agenter även utanför dem som byggs i detta projekt. Verksamhetens behov, sammanhängande processer och kontrollkrav styr arkitektur och prioriteringar.

**Gemensam arbetsmiljö för människor och AI:** Operatörscentralen ska ge tillgång
till alla teamens arbetsytor och göra det möjligt att initiera och följa
verksamhetsuppdrag. I teamytorna kan människor och agenter arbeta tillsammans
eller självständigt inom sina mandat, med samma verksamhetsoperationer och
identifierbara underlag och resultat. Människan ska kunna ställa frågor, hitta
dokument, förstå vad teamen gjort, granska leveranser och fatta beslut.
Analysuppdrag ska kunna ge källbundna rapporter eller presentationer i bolagets
grafiska profil. Exempel är beståndsanalys, förklaring av FTA och effekter av
strategiska vägval; exemplen begränsar inte teamens övriga verksamhetsansvar.

**Byggstatus och prioritering:** En beskriven roll, en körbar agentprofil och en
verifierad verksamhetsförmåga är tre olika saker. Prioritering ska ange vilket
sammanhängande arbets- eller verksamhetsförlopp som förbättras, dess beroenden,
ansvar och godkänt resultat. [Riktningsgranskningen 2026-10-27](02_system/riktningsgranskning_2026-10-27.md)
ligger till grund för det dokument- och prioriteringsarbete som operatören
godkänt i chatten samma dag. Närmast förbereds en avgränsad fråge-/rapportkedja
inom projekt 10/2; premie-/betalningsflödet och aktuariell värdering får
samordnade kommande uppdrag. Se ATT_GORA och berörda projektplaner. Detta
förtydligande aktiverar inga nya verktyg eller befogenheter och startar ingen kodimplementation.

**Regeländringar som verksamhetsförmåga:** Bolaget ska kunna hantera ändrade lagar, föreskrifter och kollektivavtal och deras följder för produktregler, villkor, bestånd, beräkningar, system, processer, styrdokument, rapportering och kommunikation. Arbetet ska vara spårbart från källa och konsekvensanalys till godkända åtgärder och uppföljning, med människa-i-loopen (§3.5) på kritiska steg. Vilka delar som berörs avgörs av den aktuella ändringen; parameterändring är ett av flera möjliga fall.

**Demonstrationer:** När bolagets förmågor finns ska de kunna visas genom utvalda scenarier, bland annat en regeländring från källa till genomförande och beståndsinsikt. Scenarierna är exempel på ordinarie verksamhet och får inte styra företagets arkitektur, datamodeller eller byggordning. Ingen hårdkodad demo-knapp eller förutbestämd demoberättelse ska byggas in i bolagets ordinarie arbetsytor. Särskilda testdata, simuleringskällor, skriptade modeller och visningsmanus hålls avgränsade från verksamhetslogiken. Återanvändbara verktyg och flöden verifieras löpande på flera relevanta fall; en lyckad demonstration är inte ett mått på att hela företaget fungerar.

Förtydligandet ovan är godkänt och loggat som **B-037** efter operatörens
godkännande i chatten 2026-10-25. [Beslutsunderlaget](02_system/bolagsvision_beslutsforslag.md)
finns bevarat. B-024 och B-035 bevaras som historiska beslut; dokumentförtydligandet ändrar ingen kod, produktregel eller behörighet.

Programmet struktureras i ett antal namngivna delprojekt, se §4b.

---

## 2. Produktavgränsning

**Ingår:**
- Ålderspension ITP1 (premiebestämd, inom kollektivavtalet ITP)

**Ingår inte (medvetna avgränsningar):**
- Sjukpension, familjepension, ITPK
- Andra kollektivavtal (SAF-LO, KAP-KL etc.)
- Direktpension eller individuella pensionslösningar

---

## 3. Designprinciper

**Garantimodell (B-027):** Den traditionella ITP1-produkten ska ge intjänad
pensionsgaranti med hela mottagna nettopremien som garantigrund och 0 %
nettoränta i garantitariffen, utan automatisk garantiförstärkning i första
modellen. Historiska garantidelar bevarar sina antaganden. Produktinriktningen
är beslutad i B-027. Produktpaket PR-ITP1 v1.0 med försäkringsvillkor v2.0 och
valda SIM-grunder är infört genom B-031 och gäller från 2026-11-01. Kodbygget
återstår; professionell tariff-, bestånds- och solvensvalidering krävs före
verklig verksamhet. Se `01_domän/produktregler/README.md` och
`01_domän/aktuariell_grund.md`.

Övergripande principer som gäller all utveckling i projektet. För full motivering bakom varje, se `BESLUTSLOGG.md`.

### 3.1 Modellagnostisk arkitektur
All kod som anropar AI-modeller ska gå via ett **abstraktionslager**, inte direkt mot en specifik leverantörs SDK. Det ska gå att byta modell eller leverantör (OpenAI ↔ Anthropic ↔ andra) genom konfiguration, utan att ändra agentkod eller skills.

**Praktiska konsekvenser:**
- Inga direktanrop till `openai.ChatCompletion` eller `anthropic.messages.create` i agent- eller skillkod
- Modellval, API-nyckel och provider hanteras via konfigurationsfil eller miljövariabler
- Prompter skrivs så generiskt som möjligt så de fungerar mellan leverantörer
- Leverantörsspecifika finesser (t.ex. Anthropics tool use-format eller OpenAIs JSON mode) kapslas in i abstraktions­lagret
- LiteLLM, OpenRouter och egen wrapper är utvärderade i `02_system/ai_abstraktion.md` – beslut: egen tunn wrapper ovanpå de officiella SDK:erna, byggd i `src/ai/` (B-025)

### 3.2 Skills före nya agenter
Default vid ny funktion är att bygga en skill som en befintlig agent får tillgång till – inte att skapa en ny agent. Nya agenter skapas endast när mandatet är fundamentalt annorlunda.

### 3.3 Delat skillsbibliotek med behörighetsmodell
Skills dokumenteras centralt i `03_skills/`. Ren beräkningskod ligger i `src/skills/`; agentverktyg återanvänder tjänstelagrets operationer och domängateways genom harnessens skill-register. Körpolicyn i `src/agents/ecosystem.yaml` bestämmer agenternas poddar och begränsningar. Skills som rör personuppgifter kräver dessutom resursmandat och begränsad databasroll (GDPR, dataminimering).

### 3.4 Hybrid dataarkitektur
Strukturerad data i databas, regler och processer som textfiler. Speglar hur verkliga bolag arbetar.

### 3.5 Människa-i-loopen för externa handlingar
Alla agentåtgärder som påverkar omvärlden (mail till kund, rapportinlämning, transaktioner) ska godkännas manuellt innan utskick. Agenter förbereder – människan beslutar.

### 3.6 Markdown som primärt informationsformat
All information i projektet sparas i första hand som **Markdown-filer** (.md). PDF eller andra format genereras från Markdown vid behov – när en människa ska läsa ett formellt beslut, en rapport eller liknande.

**Praktiska konsekvenser:**
- Styrdokument, processbeskrivningar, regelverkstolkningar, agentinstruktioner, beslut, journalanteckningar – allt skrivs som Markdown
- PDF används som *leveransformat*, inte som arbetsformat
- En md→PDF-pipeline sätts upp (t.ex. Pandoc) för formell dokumentgenerering
- Skäl: Markdown är textbaserat (LLM-vänligt), versionskontrollerbart, mänskligt läsbart i råform, och konverterbart till andra format

### 3.7 Människa som fullständig operatör
Systemet ska alltid kunna styras manuellt av en människa, på samma nivå som en agent. Varje åtgärd en agent kan utföra – lägga till en kund, uppdatera en policy, trigga ett flöde – ska också kunna utföras direkt av operatören via Cowork eller annat gränssnitt. Agenter kör på autopilot; operatören kan alltid ta manuell kontroll.

Självständigt arbete är målbilden. Varje aktiverad förmåga behöver verifierade
utlösare, mandat, väntan, återhämtning och mänsklig uppföljning. Centralen ger
överblick och vägar till arbetet; enskilda ärenden och domängodkännanden stannar
i sina specialistytor. Ett avslutat agentanrop är inte i sig en granskad leverans.

### 3.8 Ett tjänstelager för människor och agenter
Alla operationer mot försäkringssystemet går via ett gemensamt tjänstelager (`src/services/`) som handläggar-UI, agenter och skript använder. Ett centralt register bestämmer vad agenter får göra med varje operation: utföra direkt, föreslå för godkännande, eller ingenting alls (*endast handläggare*). Skrivande operationer vars produktregel inte är godkänd är alltid endast handläggare. Varje ändring loggas med vem som gjorde den och varför. Se `02_system/tjänstelager.md` och B-028.

### 3.9 Gemensamt grafiskt designspråk – Digital klarhet

Bolagets grafiska riktning är **Digital klarhet** (B-034): indigo, ljusa ytor,
DM Sans och mjukare former. Webb, handläggargränssnitt, rapporter, dokumentation
och presentationer ska använda samma grund, även när de skapas av olika agenter.
Specifikation och visuell referens finns i [`06_design/`](06_design/README.md);
gemensamma designvärden i `src/design/digital_clarity.tokens.json`.
Designgrunden är dokumenterad och tillämpad i handläggar-UI:t, som är pilotytan.
Webbens CSS-variabler genereras där ur tokenfilen. Lokala mallar för
[A4-rapporter](06_design/rapportmall.md) och [16:9-presentationer](06_design/presentationsmall.md)
återanvänder samma tokenfil, typsnittshantering och diagramstil. Gemensamma
genereringsskills, gatewaykoppling och införande i övriga ytor byggs stegvis
enligt ATT_GORA. Designspråket ändrar inte tjänstelagrets
behörigheter eller den beslutade webbarkitekturen.

---

## 4. Bolagets funktionsområden

Dessa områden ska på sikt täckas av system och/eller agenter:

| Område | Beskrivning | Status |
|--------|-------------|--------|
| Kapitalförvaltning | Placering av premiereserver, portföljövervakning | 🟡 Påbörjat – styrdokumentshierarki och placeringsriktlinje som beslutsutkast (Fas 2a/2b); datamodell för paper trading byggd/testad lokalt (Fas 2c, 2026-10-24), ej skapad i Lakebase. Antagande, gateway, marknadsdata och förvaltningslogik återstår |
| Aktuariell verksamhet | Reservberäkningar, antaganden, riskanalys | 🟡 SIM-grund och parameterregister införda genom B-031; agentprofil och premieeffektanalys för parameterändringar byggda. FTA-metod (Alecta-modellen), harness och arbetsyta beslutade i B-042; värderingskontrakt A1 fastställt produktrapport v0 (A2) och antagandebibliotek (A4) byggda lokalt. Modellverifiering 3c-V samt värderings-, garanti- och ALM-motorer återstår |
| Kundadministration | Försäkringar, löneunderlag och premiehantering inom ITP1 ålderspension utan efterlevande-/återbetalningsskydd | 🟡 Påbörjat – datamodell för arbetsgivare, försäkrade, försäkringar/förmåner/lägen och premier (B-022), premiemotor som skill, seedad databas med premiehistorik 2023–2026, tjänstelager med läs- och skrivoperationer, inklusive anslutning av ny försäkrad och stamdata (B-028, B-030, B-032) |
| Ärende­hantering | Inkommande ärenden, handläggning, svar | 🟡 Handläggar-UI v1 och ärenden med handläggaragent för `salary_report` byggda (Fas 4/5). `cases` och agentrollens rättigheter finns i Lakebase. Slutverifiering av agentflödet från 2026-11-01, fler ärendetyper och självständiga körningar återstår |
| Regelefterlevnad | Lagkrav, FI-tillsyn, kollektivavtalskrav | 🟡 Regelverkskarta, källregister, underlag och tio tolkningar finns. Compliance-profil, källäsning, utkast och parametertolkning byggda; modellverifiering 3c-V och generell regeländringshantering återstår. Styrdokumentshierarki och placeringsriktlinje är beslutsutkast |
| Rapportering | Tillämpliga myndighetsrapporter, intern rapportering, revisionsunderlag | 🟡 Rapportmall och avgränsade analysrapporter finns; rapportkontrakt, samlad verksamhetsrapportering och rapporteringsagent återstår |
| Internrevision | Kontroller, granskning, avvikelsehantering | 🔲 Ej påbörjat |

Se §4b för hur arbetet mot dessa områden struktureras i konkreta delprojekt.

---

## 4b. Delprojektöversikt (program) — B-024

Arbetet mot visionen i §1 struktureras i tio namngivna delprojekt plus ett tvärgående arkitekturramverk. B-024 inrättade de åtta första; delprojekt 9 lades till 2026-10-11 och delprojekt 10 (operatörscentral på VD-nivå) planerades 2026-10-25 på operatörens begäran, utan nytt beslutsnummer. Varje delprojekt har en projektmapp i `projekt/` (se §7) med en `PROJEKTPLAN.md` som ger ett avgränsat uppdrag – tänkt att kunna ges till Codex eller en egen Claude Code-session utan att den behöver känna till hela repot.

Redan påbörjade delprojekt (1, 4, 5) flyttar **inte** redan byggd dokumentation/kod in i projektmappen – den pekar bara till var den befintliga grunden ligger. Kod, när den byggs, läggs under det centrala `src/`-trädet (B-015) snarare än i egna per-projekt-src-mappar, för att inte bryta den enda importerbara paketroten.

| Nr | Delprojekt | Projektmapp | Kort scope | Status | Befintlig grund |
|----|-----------|-------------|------------|--------|-----------------|
| 1 | Ärendehantering & handläggar-UI | `projekt/01_ärendehantering/` | Handläggarens gränssnitt + bakomliggande backend för att handläggningar ska påverka systemen | 🟡 Handläggar-UI v1 verifierat i Lakebase. Ärenden och agent för löneunderlag byggda; `cases`/roll införda i Lakebase. Slutverifiering av agentflödet återstår från 2026-11-01 | Fas 4/5, B-020/B-033, `src/web/`, `src/agents/case_runs.py` |
| 2 | BI & insikter | `projekt/02_bi_insikter/` | Koppla försäkringssystem + databaser till indikatorer/BI; agent som svarar på datafrågor | 🟡 IBB-analys och tjänsteoperation för parameterändringars premieeffekt byggda; dashboard och Genie beslutade, ej driftsatta | B-018 (Lakebase), B-029, `src/analytics/`, `src/services/operations/portfolio_impact.py` |
| 3 | Kundportal | `projekt/03_kundportal/` | Låtsas-hemsida: se pension, förmåner, pausa/skjuta upp utbetalning | 🔲 Ej påbörjat | Nämnd som senare fas i B-020 |
| 4 | Produktregelverk & villkor | `projekt/04_produktregelverk/` | Tolka gällande regelverk till produktregler och försäkringsvillkor | 🟢 Dokumentunderlag klart och infört (B-031, gäller från 2026-11-01); kodbygge separat | `01_domän/`, `04_regulatoriskt/` |
| 5 | Kapitalförvaltning | `projekt/05_kapitalförvaltning/` | Paper trading-portfölj + gränssnitt för att analysera innehav och styra allokering | 🟡 Fas 2a/2b: dokumentutkast; 2c: datamodell byggd/testad lokalt, ej i Lakebase. Antagande och handelsfunktion återstår | Fas 2, B-019, `05_styrdokument/` |
| 6 | Avdelningsfunktioner | `projekt/06_avdelningsfunktioner/` | Ekonomi, aktuariell värdering, risk och rapportunderlag; samordning med administration och kapital | 🟡 Behov och första kontraktsarbete preciserade 2026-10-27; aktuarieteamets metod, harness och arbetsyta beslutade (B-042), värderingskontrakt A1 fastställt. Ekonomi-/FTA-motorer och körbara funktioner återstår | SIM-underlag, processöversiktens V-10–12, paket A/B och planerat värderingskontrakt |
| 7 | Kundchattbot | `projekt/07_kundchattbot/` | Chattbot på kundwebben som svarar på regelverks-/villkorsfrågor om kundens försäkring | 🔲 Ej påbörjat | Bygger på 3 + 4 |
| 8 | Företagsöversikt | `projekt/08_företagsöversikt/` | Drillbar HTML-översikt åt dig som projektledare – hur bolaget hänger ihop, med skisser | 🟡 Statisk ögonblicksbild uppdaterad 2026-10-25 mot main @ 5fd10ab: tio projekt, tre agentprofiler, 25 operationer och kvarstående verksamhetsbygge; inga livevärden | `projekt/08_företagsöversikt/foretagsoversikt.html` |
| 9 | Processkartor | `projekt/09_processkartor/` | Processkartor över agenternas arbete: utlösare, mandat, verktyg, resultat och godkännanden; levererar till delprojekt 8 | 🟡 Plan upplagd | Första målflödet i `projekt/02_bi_insikter/DASHBOARD_DESIGN.md` |
| 10 | Operatörscentral | `projekt/10_operatörscentral/` | Karls VD-arbetsyta: bolagsläge, konsolidering när underlag finns, team/agentkostnader, datafrågor och inriktningsbeslut om modellpolicy och budget | 🟡 OC-0 godkänd (B-038); OC-1 och smal OC-2 lokalt byggda/testade 2026-10-26 på `/central`. Full logg-/BI-integration, Lakebase-verifiering och styrning återstår | Projekt 2:s BI-design, harness/AI-lager och specialistgränssnitt |

**Operatörscentral på VD-nivå:** projekt 10 samlar ledningsöverblick och styrning.
Enskilda handläggarärenden och deras godkännanden stannar i specialiserade gränssnitt;
centralen visar trender, teamresultat och väsentliga ledningsfrågor. Den gemensamma
frågeingången planeras via teamens ledande agenter, med Karl som högsta beslutsfattare.
Projekt 2 äger BI-måtten enligt B-029, medan projekt 8 behåller sin projektkarta.
Se `02_system/operatörscentral.md` och det godkända
[OC-0-underlaget](02_system/operatörscentral_beslutsforslag.md) (B-038).
OC-5 och 3b-9 ska använda en gemensam versionssatt modell-/budgetkälla hos
harness efter kontrollerad övergång från YAML/env. Befogenheter ligger kvar
i granskad konfiguration; designbeslut och skiss aktiverar inga runtimefunktioner.
Den första läsleveransen OC-1/smal OC-2 finns nu lokalt på `/central`, med
bolagsaggregat, teamstatus, deklarerade kostnadsunderlag och synliga dataluckor.
Se [drift och begränsningar](02_system/operatörscentral_drift.md). Styrning
och nya agentuppdrag är fortfarande separata byggpaket.

**Tvärgående: Agentekosystem-design.** Hur agenter organiseras i team med egna orkestrerare, delade skill-poddar, modellval och nyckelhantering (jfr tidigare experiment "agent-factory") är inte ett eget delprojekt utan det arkitekturramverk alla delprojekt ovan ska byggas enligt. Agenterna körs i en harness – allt runt modellen som gör den till en agent (loop, instruktioner, verktyg, kontexthantering, guardrails) – med samma motor för alla team, konfigurerad per team med teamets verktyg och guardrails. Ramverket är beslutat i B-026 och beskrivs i `02_system/agentekosystem.md`; det vidareutvecklar B-008/B-009/B-016. Kvarvarande öppna frågor listas där (§13).

---

## 5. Teknisk stack

| Komponent | Val | Kommentar |
|-----------|-----|-----------|
| Programspråk | Python | Primärt för all logik och agenter |
| Databas | Databricks Lakebase (serverless Postgres, Free Edition) | Postgres-kompatibel, gratis för icke-kommersiellt bruk. Åtkomst via SQLAlchemy ORM. Se B-018 (ersätter B-014/Supabase). |
| Dokumentlager | Markdown/textfiler | Regler, processer, villkor |
| Webbgränssnitt | FastAPI + Jinja2 + HTMX | Handläggar-UI:t (Fas 4) ovanpå tjänstelagret, bara lokalt, inget Node eller byggsteg. Se `02_system/handläggar-ui.md` |
| AI-leverantörer | OpenAI + Anthropic (modellagnostiskt) | Via eget abstraktionslager i `src/ai/` (B-025), se 3.1 och `02_system/ai_abstraktion.md` |
| AI-arbetsmiljö | Claude API + Claude Cowork | Utveckling och agentkörning |
| Versionskontroll | Git + GitHub | Repo: [Artificiellalecta](https://github.com/karltengelin/Artificiellalecta.git). Kopplas in via Cowork-connector. |

---

## 6. Dataarki­tektur (övergripande)

**Operativ databas** – strukturerad data med tabeller för bl.a.:
- Försäkringstagare (arbetsgivare)
- Försäkrade (anställda)
- Policys/försäkringsavtal
- Premietransaktioner
- Portfölj­innehav
- Ärenden

*(Detaljerad tabellstruktur: se `02_system/databasschema.md`)*

**Dokumentbibliotek** – textbaserade filer för:
- Produktregler och försäkringsvillkor
- Processbeskrivningar
- Regulatoriska krav och tolkningar
- Agentinstruktioner och skills

---

## 7. Mappstruktur i projektet

```
Artificiellalecta/
├── README.md                       ← Projektintro
├── pyproject.toml                  ← Python-projektmetadata
├── .gitignore                      ← Exkluderar hemligheter, cache m.m.
├── .env.example                    ← Mall för miljövariabler (aldrig värden)
├── CLAUDE.md                       ← Stående arbetsregler för Claude/Cowork
├── MASTER_CONTEXT.md               ← Detta dokument
├── BESLUTSLOGG.md                  ← Alla beslut med motivering
├── ATT_GORA.md                     ← Backlog
├── DEMO_ANTECKNINGAR.md            ← Demoanteckningar (uppdateras bara på begäran)
│
├── 01_domän/                       ← Domänkunskap (text)
│   ├── ITP1_regelverk.md           ← Kollektivavtalets regler (premietrappa, åldrar, basbelopp)
│   ├── aktuariell_grund.md         ← Specificerad SIM-modell, infört (B-031); verklig validering separat
│   ├── försäkringsvillkor.md       ← Bolagets villkor för ålderspension ITP1 (v2.0)
│   ├── produktregler/              ← Produktpaket PR-ITP1 v1.0, 34 regler (B-031)
│   ├── parametrar/                 ← Parameterregister och SCB:s dödlighetstabell
│   ├── historik/                   ← Tidigare villkorsversioner
│   └── processer_översikt.md       ← verksamhetsförmågor, byggluckor och månadssimulering
│
├── 02_system/                      ← Systemdokumentation
│   ├── arkitektur.md               (kommer)
│   ├── databasschema.md            ← Tabellstruktur och SQLAlchemy-modeller (B-018, B-022)
│   ├── ai_abstraktion.md           ← AI-lagret: utvärdering, gränssnitt, roller, nycklar (B-009/B-025)
│   ├── agentekosystem.md           ← Team, skill-poddar, samverkan, modellval (B-026)
│   ├── operatörscentral.md         ← Planerad VD-arbetsyta, datafrågor, agentekonomi och styrning
│   ├── flaggskeppsflöde.md          ← avgränsat parameterändringsflöde och separat framtida visningsscenario (B-035/B-037)
│   ├── tjänstelager.md             ← Operationer för handläggare, agenter och skript (B-028)
│   ├── tjänstelager_operationer.md ← Genererad förteckning: operationer, agentnivå och skäl (T4)
│   ├── handläggar-ui.md            ← Handläggar-UI:t: start, databasval, sidor och gränser (Fas 4)
│   ├── skriptkatalog.md             ← Kodbas, körverktyg, beroenden och körordning
│   ├── agentkarta.md               ← Översikt över alla agenter
│   ├── agenter/                    ← En MD-fil per agent (10 st)
│   └── Agentsystem/                ← Orkestrerade flöden, en MD-fil per flöde (B-016)
│
├── 03_skills/                      ← Skill-beskrivningar (MD)
│   ├── skillkatalog.md             ← Index över alla skills med behörigheter
│   ├── data/
│   ├── beräkning/
│   ├── kommunikation/
│   ├── regelverk/
│   └── utveckling/
│
├── 04_regulatoriskt/               ← Lager 1: regelverkskällor
│   ├── regelverkskarta.md
│   ├── kallregister.md             ← Källor med kontrollerade versioner
│   ├── tolkningar/                 ← Tolkningar T-ITP1-001–010
│   ├── 01_huvudregim/
│   ├── 02_tvärgående/
│   └── 03_bevakning/
│
├── 05_styrdokument/                ← Lager 3: interna styrdokument
│   ├── styrdokumentshierarki.md    ← Minimal grund, beslutsutkast (Fas 2a)
│   ├── 01_styrelse/
│   ├── 02_policies/
│   ├── 03_riktlinjer/
│   │   └── placeringsriktlinje.md ← Beslutsutkast för paper trading (Fas 2b)
│   └── 04_processer/
│
├── 06_design/                       ← Digital klarhet: designspråk och visuell referens (B-034)
│   ├── README.md
│   ├── designsprak.md
│   └── digital_klarhet.html         ← Bevarad referens med exempeldata
│
├── projekt/                         ← Delprojektens PROJEKTPLAN.md (B-024 + operatörsuppdrag, se §4b)
│   ├── 01_ärendehantering/
│   ├── 02_bi_insikter/
│   ├── 03_kundportal/
│   ├── 04_produktregelverk/
│   ├── 05_kapitalförvaltning/
│   ├── 06_avdelningsfunktioner/
│   ├── 07_kundchattbot/
│   ├── 08_företagsöversikt/
│   ├── 09_processkartor/
│   └── 10_operatörscentral/         ← VD-plan, skiss och koppling till BI/harness
│
├── src/                            ← All Python-kod
│   ├── agents/                     ← Harness, körpolicy och gateways (regelverk, dokument)
│   ├── skills/                     ← Skill-implementationer
│   │   ├── data/                   ← (= 03_skills/data/)
│   │   ├── calculation/            ← (= 03_skills/beräkning/)
│   │   ├── communication/          ← (= 03_skills/kommunikation/)
│   │   ├── regulatory/             ← (= 03_skills/regelverk/)
│   │   └── development/            ← (= 03_skills/utveckling/)
│   ├── models/                     ← SQLAlchemy-modeller
│   ├── ai/                         ← Modellagnostiskt abstraktionslager (ai_config.yaml, providers/)
│   ├── services/                   ← Tjänstelagret (B-028): kontrakt, access_register.yaml, godkännande, händelselogg
│   ├── web/                        ← Handläggar-UI:t (Fas 4): sidor, templates/, static/ – anropar bara tjänstelagret
│   ├── analytics/                  ← Analyser och scenarier (delprojekt 2)
│   ├── design/                     ← Gemensamma designvärden (digital_clarity.tokens.json) och webbens CSS-variabler ur dem
│   └── utils/                      ← Gemensam kod
│
├── tests/                          ← Tester
├── data/                           ← Mockdata, testdata
└── scripts/                        ← Körverktyg; se 02_system/skriptkatalog.md
    ├── setup/                      ← Tabeller och grundparametrar
    ├── demo/                       ← Fiktiva personer och premiehistorik
    ├── maintenance/                ← Backup och återställning
    ├── migrations/                 ← Schemaändringar; äldre engångsskript i legacy/
    ├── diagnostics/                ← Databas- och AI-kontroller
    ├── analysis/                   ← Manuella analyskörningar
    ├── documentation/              ← Genererade förteckningar
    └── web/                        ← Start av handläggar-UI:t, skrivbordsgenväg och designvärden för webben
```

**Mappnamnskonvention:**
- Dokumentationsmappar i roten använder svenska namn (`beräkning`, `regelverk` etc.)
- Python-kod under `src/` använder engelska namn eftersom Pythons modulnamn inte hanterar `å`, `ä`, `ö`
- En skill har sin instruktion (MD-fil) i `03_skills/<kategori>/` och sin implementation (Python-fil) i `src/skills/<category>/` enligt mappning ovan
- Varje `projekt/<nr>_<namn>/` innehåller en `PROJEKTPLAN.md` (scope, status, beroenden) och ev. egen `docs/`-undermapp. Kod för delprojektet läggs ändå i det centrala `src/`-trädet, inte i en egen src-mapp under projektmappen – annars bryts principen om en enda importerbar paketrot

---

## 8. Arbetsflöde med Claude

| Var | Används till |
|-----|-------------|
| **Claude.ai (detta projekt)** | Strategi, planering, beslut, review, skriva dokument |
| **Claude Cowork** | Exekvering, bygge av kod, dokumentproduktion, agenter som kör |
| **Claude Code och Codex** | Parallellt bygge i egna worktrees och brancher (B-023, `AGENTS.md`) |

**Instruktion till Claude:** Läs alltid MASTER_CONTEXT innan du påbörjar en uppgift i detta projekt. Kontrollera även BESLUTSLOGG.md för relevanta beslut. Om något verkar saknas eller är oklart, fråga användaren innan du fortsätter.

---

## 9. Hänvisningar

- **BESLUTSLOGG.md** – alla beslut med motivering
- **ATT_GORA.md** – backlog och prioriterade nästa steg
