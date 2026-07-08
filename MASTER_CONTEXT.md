# MASTER_CONTEXT – ITP1 Administrationsplattform

> Detta dokument är projektets fundament. Läs det innan du gör något annat i projektet.
> Uppdatera det löpande när beslut fattas eller scope förändras.

---

## 1. Vision och syfte

Målet är att bygga ett komplett, simulerat tjänstepensionsbolag som administrerar **en enda produkt: ålderspension inom kollektivavtalet ITP1**. Bolaget ska kunna drivas av en enda person med stöd av AI-agenter och automatiserade system.

Detta är en **sandbox/simuleringsmiljö** – inga riktiga kunder, inget riktigt kapital. Syftet är att bygga fungerande processer, system och agenter som speglar hur ett verkligt bolag fungerar.

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
- Möjliga verktyg att utvärdera: LiteLLM, OpenRouter, eller egen wrapper

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
| Kundadministration | Policys, premiehantering, förmånstagare | 🔲 Ej påbörjat |
| Ärende­hantering | Inkommande ärenden, handläggning, svar | 🔲 Ej påbörjat |
| Regelefterlevnad | Lagkrav, FI-tillsyn, kollektivavtalskrav | 🔲 Ej påbörjat |
| Rapportering | FI-rapporter, intern rapportering, revisionsunderlag | 🔲 Ej påbörjat |
| Internrevision | Kontroller, granskning, avvikelsehantering | 🔲 Ej påbörjat |

---

## 5. Teknisk stack

| Komponent | Val | Kommentar |
|-----------|-----|-----------|
| Programspråk | Python | Primärt för all logik och agenter |
| Databas | Databricks Lakebase (serverless Postgres, Free Edition) | Postgres-kompatibel, gratis för icke-kommersiellt bruk. Åtkomst via SQLAlchemy ORM. Se B-018 (ersätter B-014/Supabase). |
| Dokumentlager | Markdown/textfiler | Regler, processer, villkor |
| AI-leverantörer | OpenAI + Anthropic (modellagnostiskt) | Via abstraktionslager, se 3.1 |
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

*(Detaljerad tabellstruktur dokumenteras separat när den är fastlagd)*

**Dokumentbibliotek** – textbaserade filer för:
- Produktregler och försäkringsvillkor
- Processbeskrivningar
- Regulatoriska krav och tolkningar
- Agentinstruktioner och skills

---

## 7. Mappstruktur i projektet

```
Artificiellalecta/
├── README.md                       ← Projektintro (skrivs senare)
├── pyproject.toml                  ← Python-projektmetadata
├── .gitignore                      ← Skrivs separat
├── .env.example                    ← Mall för miljövariabler
├── MASTER_CONTEXT.md               ← Detta dokument
├── BESLUTSLOGG.md                  ← Alla beslut med motivering
├── ATT_GORA.md                     ← Backlog
│
├── 01_domän/                       ← Domänkunskap (text)
│   ├── ITP1_regelverk.md           (kommer)
│   ├── aktuariell_grund.md         (kommer)
│   ├── försäkringsvillkor.md       (kommer)
│   └── processer_översikt.md       (kommer)
│
├── 02_system/                      ← Systemdokumentation
│   ├── arkitektur.md               (kommer)
│   ├── databasschema.md            (kommer)
│   ├── ai_abstraktion.md           (kommer)
│   ├── agentkarta.md               (kommer)
│   └── agenter/                    ← En MD-fil per agent
│
├── 03_skills/                      ← Skill-beskrivningar (MD)
│   ├── skillkatalog.md             (kommer)
│   ├── data/
│   ├── beräkning/
│   ├── kommunikation/
│   └── regelverk/
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
├── src/                            ← All Python-kod
│   ├── agents/                     ← Agent­implementationer
│   ├── skills/                     ← Skill-implementationer
│   │   ├── data/                   ← (= 03_skills/data/)
│   │   ├── calculation/            ← (= 03_skills/beräkning/)
│   │   ├── communication/          ← (= 03_skills/kommunikation/)
│   │   └── regulatory/             ← (= 03_skills/regelverk/)
│   ├── models/                     ← SQLAlchemy-modeller
│   ├── ai/                         ← Modellagnostiskt abstraktionslager
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
