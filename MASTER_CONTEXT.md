# MASTER_CONTEXT – ITP1 Administrationsplattform

> Detta dokument är projektets fundament. Läs det innan du gör något annat i projektet.
> Uppdatera det löpande när beslut fattas eller scope förändras.

---

## 1. Vision och syfte

Målet är att bygga ett komplett, simulerat tjänstepensionsbolag som administrerar **en enda produkt: ålderspension inom kollektivavtalet ITP1**. Bolaget ska kunna drivas av en enda person med stöd av AI-agenter och automatiserade system.

Detta är en **sandbox/simuleringsmiljö** – inga riktiga kunder, inget riktigt kapital. Syftet är att bygga fungerande processer, system och agenter som speglar hur ett verkligt bolag fungerar.

**Programvision (B-024):** Utöver att bygga produkten (ovan) är det övergripande målet att visa upp ett **AI-native tjänstepensionsbolag** – en organisation där agentteam utför det löpande arbete som avdelningarna i ett riktigt bolag skulle göra (handläggning, kapitalförvaltning, aktuariellt arbete, regelefterlevnad, rapportering, kundkommunikation), och där system och data är byggda för att vara tillgängliga för vilken AI-agent som helst att arbeta mot – inte bara de agenter som byggs i detta projekt.

**Flaggskeppsscenario:** Det viktigaste som ska kunna demonstreras när programmet är klart är ett fullständigt, spårbart flöde från regelverksändring till produktion: en ändring i ett nationellt regelverk (t.ex. ändrad pensionsålder) tolkas av agenter till konkreta produktregler, dessa produktregler sätts i produktion i försäkringssystemet, och agenterna tar fram en business insight om hur ändringen påverkar det befintliga beståndet – allt på ett strömlinjeformat och säkert sätt, med människa-i-loopen (§3.5) på kritiska steg.

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
Alla skills ligger centralt i `03_skills/`. Varje agent har en deklarerad lista över vilka skills den får använda. Skills som rör personuppgifter har begränsad behörighet (GDPR, dataminimering).

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

---

## 4. Bolagets funktionsområden

Dessa områden ska på sikt täckas av system och/eller agenter:

| Område | Beskrivning | Status |
|--------|-------------|--------|
| Kapitalförvaltning | Placering av premiereserver, portföljövervakning | 🔲 Ej påbörjat |
| Aktuariell verksamhet | Reservberäkningar, antaganden, riskanalys | 🔲 Ej påbörjat |
| Kundadministration | Policys, premiehantering, förmånstagare | 🟡 Påbörjat – datamodell för arbetsgivare, försäkrade, försäkringar/förmåner/lägen och premier (B-022), premiemotor som skill, seedad databas med premiehistorik 2023–2026 |
| Ärende­hantering | Inkommande ärenden, handläggning, svar | 🔲 Ej påbörjat |
| Regelefterlevnad | Lagkrav, FI-tillsyn, kollektivavtalskrav | 🔲 Ej påbörjat |
| Rapportering | FI-rapporter, intern rapportering, revisionsunderlag | 🔲 Ej påbörjat |
| Internrevision | Kontroller, granskning, avvikelsehantering | 🔲 Ej påbörjat |

Se §4b för hur arbetet mot dessa områden struktureras i konkreta delprojekt.

---

## 4b. Delprojektöversikt (program) — B-024

Arbetet mot visionen i §1 struktureras i åtta namngivna delprojekt plus ett tvärgående arkitekturramverk. Varje delprojekt har en projektmapp i `projekt/` (se §7) med en `PROJEKTPLAN.md` som ger ett avgränsat uppdrag – tänkt att kunna ges till Codex eller en egen Claude Code-session utan att den behöver känna till hela repot.

Redan påbörjade delprojekt (1, 4, 5) flyttar **inte** redan byggd dokumentation/kod in i projektmappen – den pekar bara till var den befintliga grunden ligger. Kod, när den byggs, läggs under det centrala `src/`-trädet (B-015) snarare än i egna per-projekt-src-mappar, för att inte bryta den enda importerbara paketroten.

| Nr | Delprojekt | Projektmapp | Kort scope | Status | Befintlig grund |
|----|-----------|-------------|------------|--------|-----------------|
| 1 | Ärendehantering & handläggar-UI | `projekt/01_ärendehantering/` | Handläggarens gränssnitt + bakomliggande backend för att handläggningar ska påverka systemen | 🟡 Utredning klar | Fas 4/5, B-020 |
| 2 | BI & insikter | `projekt/02_bi_insikter/` | Koppla försäkringssystem + databaser till indikatorer/BI; agent som svarar på datafrågor | 🔲 Ej påbörjat | B-018 (Lakebase) |
| 3 | Kundportal | `projekt/03_kundportal/` | Låtsas-hemsida: se pension, förmåner, pausa/skjuta upp utbetalning | 🔲 Ej påbörjat | Nämnd som senare fas i B-020 |
| 4 | Produktregelverk & villkor | `projekt/04_produktregelverk/` | Tolka gällande regelverk till produktregler och försäkringsvillkor | 🟡 Pågår | `01_domän/`, `04_regulatoriskt/` |
| 5 | Kapitalförvaltning | `projekt/05_kapitalförvaltning/` | Paper trading-portfölj + gränssnitt för att analysera innehav och styra allokering | 🟡 Utredning klar | Fas 2, B-019 |
| 6 | Avdelningsfunktioner | `projekt/06_avdelningsfunktioner/` | Funktioner per avdelning, bl.a. en aktuariell modul för premiesättning kopplad till FI-krav | 🔲 Ej påbörjat | — |
| 7 | Kundchattbot | `projekt/07_kundchattbot/` | Chattbot på kundwebben som svarar på regelverks-/villkorsfrågor om kundens försäkring | 🔲 Ej påbörjat | Bygger på 3 + 4 |
| 8 | Företagsöversikt | `projekt/08_företagsöversikt/` | Drillbar HTML-översikt åt dig som projektledare – hur bolaget hänger ihop, med skisser | 🔲 Ej påbörjat | — |

**Tvärgående: Agentekosystem-design.** Hur agenter organiseras i team med egna orkestrerare, delade skill-poddar, modellval och nyckelhantering (jfr tidigare experiment "agent-factory") är inte ett eget delprojekt utan det arkitekturramverk alla delprojekt ovan ska byggas enligt. Agenterna körs av en gemensam harness som tvingar igenom varje teams guardrails (vilka verktyg teamet får använda, vad som kräver godkännande). Ramverket är beslutat i B-026 och beskrivs i `02_system/agentekosystem.md`; det vidareutvecklar B-008/B-009/B-016. Kvarvarande öppna frågor listas där (§13).

---

## 5. Teknisk stack

| Komponent | Val | Kommentar |
|-----------|-----|-----------|
| Programspråk | Python | Primärt för all logik och agenter |
| Databas | Databricks Lakebase (serverless Postgres, Free Edition) | Postgres-kompatibel, gratis för icke-kommersiellt bruk. Åtkomst via SQLAlchemy ORM. Se B-018 (ersätter B-014/Supabase). |
| Dokumentlager | Markdown/textfiler | Regler, processer, villkor |
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
│   ├── aktuariell_grund.md         (kommer)
│   ├── försäkringsvillkor.md       ← Bolagets villkor för ålderspension ITP1

│   └── processer_översikt.md       (kommer)
│
├── 02_system/                      ← Systemdokumentation
│   ├── arkitektur.md               (kommer)
│   ├── databasschema.md            ← Tabellstruktur och SQLAlchemy-modeller (B-018, B-022)
│   ├── ai_abstraktion.md           ← AI-lagret: utvärdering, gränssnitt, roller, nycklar (B-009/B-025)
│   ├── agentekosystem.md           ← Team, skill-poddar, samverkan, modellval (B-026)
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
│   ├── 01_huvudregim/
│   ├── 02_tvärgående/
│   └── 03_bevakning/
│
├── 05_styrdokument/                ← Lager 3: interna styrdokument
│   ├── styrdokumentshierarki.md    (kommer)
│   ├── 01_styrelse/
│   ├── 02_policies/
│   ├── 03_riktlinjer/
│   └── 04_processer/
│
├── projekt/                         ← Delprojektens PROJEKTPLAN.md (B-024, se §4b)
│   ├── 01_ärendehantering/
│   ├── 02_bi_insikter/
│   ├── 03_kundportal/
│   ├── 04_produktregelverk/
│   ├── 05_kapitalförvaltning/
│   ├── 06_avdelningsfunktioner/
│   ├── 07_kundchattbot/
│   └── 08_företagsöversikt/
│
├── src/                            ← All Python-kod
│   ├── agents/                     ← Agent­implementationer
│   ├── skills/                     ← Skill-implementationer
│   │   ├── data/                   ← (= 03_skills/data/)
│   │   ├── calculation/            ← (= 03_skills/beräkning/)
│   │   ├── communication/          ← (= 03_skills/kommunikation/)
│   │   ├── regulatory/             ← (= 03_skills/regelverk/)
│   │   └── development/            ← (= 03_skills/utveckling/)
│   ├── models/                     ← SQLAlchemy-modeller
│   ├── ai/                         ← Modellagnostiskt abstraktionslager (ai_config.yaml, providers/)
│   └── utils/                      ← Gemensam kod
│
├── tests/                          ← Tester
├── data/                           ← Mockdata, testdata
└── scripts/                        ← Engångsskript, datagenerering
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

**Instruktion till Claude:** Läs alltid MASTER_CONTEXT innan du påbörjar en uppgift i detta projekt. Kontrollera även BESLUTSLOGG.md för relevanta beslut. Om något verkar saknas eller är oklart, fråga användaren innan du fortsätter.

---

## 9. Hänvisningar

- **BESLUTSLOGG.md** – alla beslut med motivering
- **ATT_GORA.md** – backlog och prioriterade nästa steg
