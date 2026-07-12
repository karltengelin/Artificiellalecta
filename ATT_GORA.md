# Att-göra-lista – ITP1 Administrationsplattform

> Löpande backlog över saker som ska göras, byggas eller utredas. Strukturerad efter prioritet och område.
>
> **Format:** Markera klart med ✅. Lägg till datum och kort kommentar när något genomförs. Saker som inte längre är aktuella stryks ej – arkiveras längst ned.

---

## 📋 Fasplan (beslutad 2026-07-12)

Övergripande ordning för de kommande byggfaserna. Detaljuppgifter ligger under respektive prioritetsrubrik nedan.

1. **Fas 1 – Försäkringssystemet (premiemotorn):** ITP1-domändokument, tabellerna `policies` + `premium_transactions`, premieberäkning som skill, genererad premiehistorik
2. **Fas 2 – Kapitalförvaltning (paper trading, B-019):** placeringsriktlinje i `05_styrdokument/`, tabellerna `portfolios`/`portfolio_holdings`/`trades`, marknadsdata via gratis-API, regelstyrd förvaltningslogik med beslutslogg. Simulerad wallet – inget riktigt kapital (B-003)
3. **Fas 3 – AI-abstraktionslagret (B-009):** blockerar all agentkod – byggs före agenterna
4. **Fas 4 – Handläggar-UI (B-020):** FastAPI-backend + tabellvyer + inbyggd Claude (se utredningen under 🔵 nedan). Kundportal byggs senare på samma backend
5. **Fas 5 – Handläggaragent + `cases`-tabell + första skills**

---

## 🔴 Hög prioritet – grunden

- [x] **2026-07-12** Fas 1a: `01_domän/ITP1_regelverk.md` och `01_domän/försäkringsvillkor.md` skrivna – premietrappan med 2026-belopp (IBB 83 400 kr, brytpunkter 52 125/208 500 kr/mån) verifierade mot Avtalat/Collectum/Regeringen, åldersfönster 25–66 (månadsbaserat), IBB-historik 2023–2026 för retroaktiv mockdata, implementationsregler för premiemotorn i regelverkets §8
- [x] **2026-07-12** Fas 1b: `policies` och `premium_transactions` – dokumenterade i `databasschema.md` (§5–6) och implementerade som SQLAlchemy-modeller. Ett avtal per försäkrad (B-021), kapital härleds ur transaktioner, `calculation_basis` (JSONB) ger revisionsspårbarhet, partiellt unikt index säkrar en ordinarie premie per avtal/månad. DDL Postgres-validerad. `scripts/create_tables.py` skapar tabellerna (körs av operatören)
- [x] **2026-07-12** Fas 1c: Premiemotor som skill – `03_skills/beräkning/beräkna-itp1-premie.md` + `src/skills/calculation/calculate_itp1_premium.py`. Ren beräkningsfunktion (trappa, åldersfönster på månadsnivå, calculation_basis för spårbarhet), 17 tester gröna mot handräknade exempel. Dessutom: `base_amounts`-tabell (schema §7 + modell + seed-skript) och första versionen av `03_skills/skillkatalog.md`
- [x] **2026-07-12** Fas 1e: Försäkringsmodell omdesignad (B-022) – flera försäkringar per person, `policy_states` (tillståndsperioder), `policy_benefits` (förmåner; TGL/familjeskydd förberedda), premier flyttade till förmånsnivå. `scripts/rebuild_insurance_tables.py` bygger om, generatorn skapar försäkring+förmån+lägen+premier
- [x] **2026-07-12** Fas 1d: `scripts/generate_premium_history.py` – skapar ett avtal per försäkrad (AL-NNNNNN, fribrev för avslutade) och premiehistorik 2023-01–2026-06 via premiemotorn med rätt IBB per år, lönedeflator 2,5 %/år bakåt, åldersfönsterkontroll. Idempotent, `--dry-run`-stöd. Hjälpfunktioner sandboxtestade. *(Premiemotorns tester skrevs i Fas 1c – 17 gröna)*

- [x] **2026-07-08** Skapa Databricks Free Edition-konto + Lakebase-instans, uppdatera `DATABASE_URL` och kör seed *(ersatte Supabase-uppgiften, se B-018)* – projekt `artificiellalecta` skapat på `artificiellalecta@gmail.com`, Postgres 18, region AWS (us-east-2). Password-auth aktiverad, native roll `app_backend` skapad. Öppen riskpunkt från B-018 löst: extern SQLAlchemy-anslutning med enkel användarnamn/lösenord fungerar utan problem i Free Edition. Seed kört: 20 arbetsgivare, 500 försäkrade.

- [x] **2026-05-15** Skriva `02_system/agentkarta.md` – tio agentskelett i `02_system/agenter/` plus agentkarta (commit `b88da94`)
- [x] **2026-07-12** Skriva `03_skills/skillkatalog.md` – första versionen skapad i Fas 1c med premiemotorn + planerade skills. Underhålls löpande
- [ ] **Bygga ut `04_regulatoriskt/`** – bryta ner regelverkskartan i underdokument per regelverk (LTF, FFFS:er, DORA, GDPR, IDD, SFDR, AI-förordningen, skatt)
- [ ] **Skapa styrdokumentsstruktur** i `05_styrdokument/` – skriva `styrdokumentshierarki.md` som definierar struktur, ägarskap, revisionscykel och standardmetadata för alla styrdokument
- [x] **2026-05-16** Definiera databasschema – `02_system/databasschema.md` + SQLAlchemy-modeller för `employers` och `insured_persons`. Övriga tabeller (policies, premium_transactions, portfolio_holdings, cases) skjuts upp till de behövs.
- [x] **2026-05-16** Sätta upp Google-konto för det fiktiva bolaget – Artificiellalecta@gmail.com
- [x] **2026-05-16** Skapa Supabase-konto och projekt – Artificiellalecta-projektet, region Europe *(databasval ersatt av B-018, se Arkiv)*

---

## 🟠 Fas 2 – Kapitalförvaltning (paper trading)

- [ ] **Fas 2a: Minimal `05_styrdokument/styrdokumentshierarki.md`** – bara det som krävs för att kunna anta placeringsriktlinjen (fullständig version kvarstår under Hög prioritet)
- [ ] **Fas 2b: Placeringsriktlinje** i `05_styrdokument/03_riktlinjer/` – tillgångsslag, allokeringslimiter, rebalanseringsregler; skriven som om ett verkligt tjänstepensionsbolag (LTF/Solvens II-anda, aktsamhetsprincipen)
- [ ] **Fas 2c: Tabeller `portfolios`, `portfolio_holdings`, `trades`** – wallet = portfölj med startkassa (t.ex. 1 000 kr simulerade)
- [ ] **Fas 2d: Marknadsdata-skill** – gratis-API (t.ex. yfinance), hämta kurser för riktlinjens tillgångsslag
- [ ] **Fas 2e: Förvaltningslogik** – regelstyrd i första versionen (ingen LLM förrän Fas 3): allokera enligt riktlinjen, rebalansera vid avvikelse, logga varje beslut med motivering. Koppla premieinflödet från Fas 1 till portföljen

---

## 🟡 Medium prioritet – domänkartläggning

- [ ] **Specificera AI-abstraktionslagret** i `02_system/ai_abstraktion.md` – utvärdera LiteLLM/OpenRouter vs egen wrapper, definiera gränssnitt
- [ ] **Kartlägga processer** i `01_domän/processer_översikt.md` (kundärenden, premiehantering, rapportering, etc.)
- [x] **2026-07-12** Skriva ut försäkringsvillkor för ITP1 ålderspension i `01_domän/försäkringsvillkor.md` *(gjordes i Fas 1a)*
- [ ] **Dokumentera aktuariell grund** – antaganden, tabeller, beräkningsmodeller
- [ ] **Designa regelförändringsflöde** – multi-agent-flöde som triggas när ett regelverk ändras: compliance-agent gör tolkning och konsekvensanalys, utvecklaragent identifierar kodpåverkan, kommunikationsagent förbereder ev. kundkommunikation. Dokumenteras i `02_system/regelförändringsflöde.md`. Ett av undantagen från B-008 (kräver olika mandat).

## 🟢 Lägre prioritet – när grunden står

- [ ] **Sätta upp md→PDF-pipeline** – välja verktyg (Pandoc eller WeasyPrint), definiera mallar för formella dokument (rapporter, kundbrev, styrelseprotokoll)
- [ ] **Standardmall för officiella dokument** – logga, sidhuvud/sidfot, signaturplats, sidnumrering, dokument-ID, versionsinfo. Tas i samband med PDF-pipelinen
- [ ] **Bygga första agent: Handläggaragent** (ärendehantering)
- [ ] **Bygga kommunikationsagent** – äger bred utgående kommunikation (kundutskick, mailbesvarande, standardiserade meddelanden). Separerad från handläggaragenten för att skilja ärendelogik från kommunikationsarbete. Mandat motiveras i BESLUTSLOGG när agenten byggs (avsteg från B-008).
- [ ] **Bygga första skills:** `hämta-kunddata`, `skriv-kundmail`, `tolka-itp1-fråga`
- [ ] **Skill: complianceöversyn** (på compliance-agenten) – proaktiv genomgång av regelverkskartan mot styrdokument och processer. Rapporterar gap och misstänkta diskrepanser. Triggas manuellt eller schemalagt. Skapas som `03_skills/regelverk/complianceöversyn.md` + `src/skills/regulatory/compliance_review.py`.
- [ ] **Sätta upp koppling Cowork ↔ Gmail** (MCP)
- [ ] **Generera testdata** – fiktiva kunder, policys, transaktioner

## 🔵 Utredning & planering – admin-gränssnitt med inbyggd Claude

- [ ] **Designa och bygg admin-UI med inbyggd Claude-agent** *(kopplat till B-017)*

  Målet är en admin-flik i bolagets webbgränssnitt där operatören kan chatta
  med Claude direkt i bolagskontext – utan att behöva öppna Cowork separat
  eller ange sökvägar manuellt.

  **Hur mappåtkomst fungerar:**
  Bolagsmappens sökväg konfigureras en gång i serverns miljövariabler (`.env`).
  Varje ny konversation får automatiskt tillgång till mappstrukturen via
  förkonfigurerade fil-verktyg – samma princip som Cowork, men utan manuellt
  mappval. Operatören pekar ut bolagsmappen en gång vid installation; därefter
  är det transparent.

  **Tekniska komponenter att bygga:**

  1. **Python-backend (FastAPI)** – tar emot meddelanden från admin-UI:n,
     anropar Claude API med systemprompt + verktyg, returnerar svar.
     Sessionshistorik sparas per konversation (troligen i Supabase).

  2. **Systemprompt (förkonfigurerad)** – laddas automatiskt vid varje
     konversation. Innehåller: bolagskontext (vad Artificiellalecta är),
     sökväg till bolagsmappen, aktiva regler och vilka verktyg som finns.
     Operatören behöver inte skriva något i första prompten.

  3. **Fil-verktyg** – Claude kan lista, läsa och skriva filer i bolagsmappen
     och dess undermappar. Definieras server-side med rot-sökväg från `.env`.
     Scopat till bolagsmappen – Claude kan inte nå filer utanför.

  4. **Lakebase-verktyg** *(B-018)* – CRUD-operationer mot databasen (hämta kunder,
     lägg till kund, uppdatera policy etc.). Definieras som Claude-tools i
     backenden med Lakebase-anslutningen från `.env`.

  5. **Frontend-chatyta** – enkel React- eller HTML-komponent inbyggd i
     admin-fliken. Skickar meddelanden till Python-backenden, visar svar.
     Inga Claude API-nycklar exponeras i frontenden.

  6. **Tabell-vyer** – enkla datavyer i admin-UI:n för att bläddra i
     databasens tabeller (kunder, policys, transaktioner etc.). Hämtas
     via Python-backenden, visas som filtrerbara tabeller i frontenden.
     Databricks-webbgränssnittet används som debuggingverktyg under utveckling;
     tabell-vyerna i admin-UI:n är den långsiktiga lösningen.

  **Utestående designfrågor att besluta:**
  - Ska sessionshistorik sparas (och i så fall var – Lakebase?)?
  - Vilka fil-operationer ska vara tillåtna (enbart läsa, eller även skriva)?
  - Autentisering till admin-fliken – enkel lösenordsskydd räcker för sandbox?
  - Ska samma backend användas av både agenter och mänsklig operatör,
    eller separata ingångar?

  **Beroenden:** Databricks Lakebase-instans måste vara uppsatt (se hög-prioritet).
  Bolagsmappens slutliga sökväg måste vara bestämd.

---

## 💭 Att utreda / oklart

- [ ] **Git branch-strategi** – kör main direkt i tidigt skede, eller feature branches + PR redan från start?
- [ ] Hur ska godkännandeflöden fungera (mail till kund ska godkännas innan utskick)?
- [ ] Loggning och spårbarhet – hur sparas agentbeslut?
- [ ] Backup-strategi för databas och dokument

---

## ✅ Klart

- [x] **2026-05-14** Skriva MASTER_CONTEXT.md
- [x] **2026-05-14** Skapa beslutslogg
- [x] **2026-05-14** Skapa att-göra-lista (detta dokument)
- [x] **2026-05-14** Ta emot regelverkskarta som grund för `04_regulatoriskt/`
- [x] **2026-05-14** Koppla Cowork till GitHub-repot Artificiellalecta via connector
- [x] **2026-05-14** Lägga upp grunddokumenten i repot (MASTER_CONTEXT, BESLUTSLOGG, ATT_GORA, regelverkskarta) som första commit
- [x] **2026-05-14** Skriva `.gitignore` – exkludera API-nycklar, `.env`, databasfiler, cache, virtuella miljöer m.m.
- [x] **2026-05-14** Beslut om databas – PostgreSQL via Supabase (B-014)
- [x] **2026-05-16** Databasschema, SQLAlchemy-modeller (`employers`, `insured_persons`), mockdatagenerator och seed-script

---

## 🗄️ Arkiv

### Guide: Skapa Supabase-projekt *(arkiverad 2026-07-08 – databasval ersatt av B-018/Databricks Lakebase)*

1. Gå till **supabase.com** och klicka på *Start your project* (eller *Sign in* om du redan har konto)
2. Logga in – enklast via GitHub-kontot du redan har (då hänger projekten ihop) eller via e-post
3. Klicka på *New project*. Välj vilken organisation det ska tillhöra (din egen personliga räcker)
4. Fyll i:
   - **Project name:** `Artificiellalecta` (eller liknande)
   - **Database password:** Generera ett starkt lösenord. **Spara det säkert** (lösenordshanterare) – det går inte att se igen efteråt
   - **Region:** Välj `Europe (Stockholm)` eller `Europe (Frankfurt)` – närmast = snabbast
   - **Pricing plan:** Free
5. Vänta ~2 minuter medan projektet sätts upp
6. När det är klart, gå till **Project Settings → API**. Spara följande (men lägg dem ALDRIG i Git):
   - **Project URL** (ser ut som `https://xxxxx.supabase.co`)
   - **anon public key** (för läsåtkomst)
   - **service_role key** (för full åtkomst – behandlas som lösenord)
7. Gå till **Project Settings → Database** och spara **connection string** (för SQLAlchemy)

**Tips:** Logga in i projektet minst en gång i veckan så pausas det inte. Eller acceptera att det pausas – det räcker att klicka *Restore project* om så händer.

### Byt DATABASE_URL till Supabase Connection Pooler *(arkiverad 2026-07-08 – ersatt av Lakebase-uppgiften under Hög prioritet)*

Direktanslutningen `db.<projref>.supabase.co:5432` var IPv6-only på free-tier och föll på vanliga svenska hemnät. Lösningen hade varit att byta till Connection Pooler-URI:n (`aws-0-<region>.pooler.supabase.com:6543`) via Transaction-fliken i Supabase. Blev inaktuell när B-018 ersatte Supabase med Databricks Lakebase innan uppgiften hanns slutföras.
