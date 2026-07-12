# Beslutslogg – ITP1 Administrationsplattform

> Löpande logg över beslut som fattas i projektet. Varje beslut har en motivering så att framtida Claude (och framtida du) förstår *varför* något bestämdes, inte bara *vad*.
>
> **Format:** Nya beslut läggs överst. Ändra inte gamla poster – om ett beslut ändras, lägg in ett nytt och referera till det gamla.

---

## Beslut

### B-022 | 2026-07-12 | Försäkringsmodell med förmåner och tillståndsperioder

**Beslut:** Försäkringsdatamodellen struktureras i tre nivåer med en parallell tidslinje:

1. **`policies` (försäkringar):** en person kan ha **flera** försäkringar. Tabellen bär identitet (försäkringsnummer, produktkod, tecknings- och ikraftträdandedatum) – **ingen statuskolumn**.
2. **`policy_benefits` (förmåner):** försäkringens innehåll modelleras som förmåner med egna start-/slutdatum, typspecifika parametrar (JSONB) och **egna premietransaktioner** (`premium_transactions.benefit_id`). I nuläget endast premiebestämd ålderspension (`retirement_dc`); TGL och familjeskydd är förberedda som typer.
3. **`policy_states` (lägen):** försäkringens läge över tid som tillståndsperioder (`premium_paying`, `paid_up`, `in_payout`, `payout_paused`, `terminated`) med `valid_from`/`valid_to`. Öppen rad = nuläge.

**Motivering:**
- Speglar hur verkliga försäkringssystem modellerar: försäkring → förmåner → tillstånd. När TGL/familjeskydd läggs till krävs ingen schemaändring, och deras premier blandas inte med pensionspremier
- Tillståndsperioder svarar direkt på "vilket läge hade försäkringen vid tidpunkt T?" – krav för handläggning, revision och kundhistorik
- Ingen statuskolumn på `policies` eliminerar risken för dubbla sanningar (status som motsäger lägeshistoriken)
- Uppslagskedjan person → försäkringar → förmåner → premier är rena FK-joins – handläggar-UI:t (B-020) kan bygga vyer utan specialfall

**Övervägda alternativ:**

*Händelselogg i stället för tillståndsperioder* – mer granulär revision, men läget vid en tidpunkt måste härledas ur händelsekedjan. Kan införas senare som komplement (t.ex. i samband med `cases`).

*Premier kvar på försäkringsnivå* – enklare nu, men skulle kräva ombyggnad när fler förmånstyper tillkommer.

**Konsekvenser:**
- Tabellerna byggdes om via `scripts/rebuild_insurance_tables.py`; genererad data återskapas med `scripts/generate_premium_history.py`
- Integritetsregler: max ett öppet läge per försäkring, max en pågående förmån per typ och försäkring, max en ordinarie premie per förmån och månad (partiella unika index). Överlappande lägesperioder valideras på applikationsnivå
- Förmånens kapital = summan av dess betalda transaktioner; försäkringens = summan över förmåner; personens = summan över försäkringar

**Ersätter:** B-021:s regel om ett avtal per försäkrad (UNIQUE på `insured_person_id`). Övriga delar av B-021 (endast traditionell förvaltning, kapitalavgift 0,20 %, ingen flytträtt/efterlevandeskydd i v1.0) kvarstår oförändrade.

---

### B-021 | 2026-07-12 | Produktförenklingar i försäkringsvillkor version 1.0

**Beslut:** Bolagets försäkringsvillkor för ålderspension ITP1 (`01_domän/försäkringsvillkor.md` v1.0) gör tre medvetna förenklingar gentemot det verkliga ITP1-systemet:

1. **Endast traditionell förvaltning** – inget fondval, ingen valcentral. Allt pensionskapital förvaltas kollektivt enligt bolagets placeringsriktlinje.
2. **Kapitalavgift 0,20 % per år** (debiteras månadsvis med 1/12), ingen fast avgift.
3. **Ingen flytträtt och inget efterlevandeskydd** i version 1.0.

**Motivering:**
- Kollektiv traditionell förvaltning gör Fas 2 (paper trading, B-019) till *en* portfölj att förvalta i stället för individuella val – premieinflödet kan kopplas direkt till portföljen utan valcentralslogik
- I verkligheten ligger dessa roller dessutom hos skilda aktörer (Collectum som valcentral, flera valbara bolag) – att simulera hela den strukturen tillför komplexitet utan motsvarande lärvärde i detta skede
- En kapitalavgift ger bolaget en intäktsström, vilket behövs för att ekonomiagenten (framtida fas) ska ha något att bokföra; 0,20 % ligger i paritet med verkliga ITP1-upphandlade bolag
- Efterlevandeskydd är redan utanför scope (B-002); flytträtt kräver motpartslogik som saknar mening i en simulering med ett enda bolag

**Konsekvenser:**
- `policies`-tabellen (Fas 1b) behöver inte kolumner för sparform eller fondval i första versionen
- Avgiftsuttag ska implementeras när kapitalberäkning byggs (kapitalavgift som månatlig transaktion)
- Fondval, valcentralsroll och flytträtt är kandidater för senare versioner – återinförs i så fall genom nytt beslut och ny villkorsversion
- Villkorens ändringslogg och detta beslut ska hållas i synk vid framtida versioner

---

### B-020 | 2026-07-12 | Handläggar-UI byggs före kundportalen

**Beslut:** Av de två planerade webbgränssnitten byggs **handläggargränssnittet först** (admin-UI enligt utredningen i ATT_GORA: FastAPI-backend, tabellvyer mot Lakebase, inbyggd Claude-agent). Kundportalen (se pensionssaldo, pausa uttag m.m.) byggs senare, ovanpå samma FastAPI-backend.

**Motivering:**
- Utredningen för admin-UI:t är redan gjord (ATT_GORA 🔵) – arkitektur, komponenter och designfrågor är kartlagda
- Handläggar-UI:t kräver ingen kundautentisering – för en sandbox räcker enkelt skydd, medan en kundportal väcker autentiserings- och behörighetsfrågor som inte behöver lösas nu
- Kundportalens kärnfunktioner (t.ex. pausa uttag) kräver uttags-/utbetalningslogik som inte finns än – handläggar-UI:t behöver bara läsa och redigera data som redan finns i databasen
- Operatörsprincipen (B-017) gynnas direkt: handläggar-UI:t blir operatörens gränssnitt mot bolaget
- Gemensam backend gör att kundportalen sedan blir ett frontend-tillägg, inte ett nytt systembygge

**Övervägda alternativ:**

*Alternativ 1: Kundportalen först* – mer synligt demoresultat, men blockeras av saknad uttagslogik och autentiseringsfrågor.

*Alternativ 2: Båda parallellt* – enhetlig arkitektur från start men mest arbete och delad fokus; avvisat i detta skede.

**Konsekvenser:**
- Fas 4 i ATT_GORA:s fasplan avser handläggar-UI:t; kundportalen läggs som senare fas
- Backenden designas från start för två klienter (handläggare, kund) – API:t ska inte anta att anroparen är intern
- Utestående designfrågor i ATT_GORA-utredningen (sessionshistorik, filrättigheter, autentisering) beslutas när Fas 4 påbörjas

---

### B-019 | 2026-07-12 | Kapitalförvaltning som paper trading – inget riktigt kapital

**Beslut:** Kapitalförvaltningen byggs som **paper trading**: en simulerad wallet/portfölj i databasen (startkassa t.ex. 1 000 kr, simulerade), riktiga marknadsdata via gratis-API (t.ex. yfinance), och förvaltningslogik som placerar enligt en intern placeringsriktlinje i `05_styrdokument/` – skriven som om ett verkligt tjänstepensionsbolag investerade. Inget riktigt kapital används.

**Motivering:**
- Bekräftar B-003 (sandbox, inget riktigt kapital) – helautomatisk AI-handel med riktiga pengar hade rivit upp den principen
- §3.5 (människa-i-loopen) kräver ändå manuellt godkännande av transaktioner – helautomatisk exekvering med riktiga pengar vore dubbelt oförenlig med befintliga principer
- Läroeffekten är nästan identisk: portföljlogik, riktlinjeefterlevnad, rebalansering och beslutsloggning byggs och testas lika väl mot simulerad kassa med riktiga kurser
- Slipper mäklar-API, depåavtal och regulatorisk gråzon kring automatiserad handel
- Premieinflödet från försäkringssystemet (Fas 1) kan kopplas som insättningar till portföljen – bolaget hänger ihop end-to-end utan externa beroenden

**Övervägda alternativ:**

*Alternativ 1: Riktiga 1 000 kr, operatören exekverar* – agenten föreslår ordrar, operatören lägger dem manuellt hos mäklare. Förenligt med §3.5 men manuellt arbete per order och kräver depå; ger marginellt mervärde över paper trading. Kan omprövas senare när förvaltningslogiken är beprövad.

*Alternativ 2: Helautomatisk handel med riktigt kapital* – avvisat: bryter B-003 och §3.5.

**Konsekvenser:**
- Fasplanens Fas 2 i ATT_GORA: styrdokumentshierarki (minimal) + placeringsriktlinje, tabellerna `portfolios`/`portfolio_holdings`/`trades`, marknadsdata-skill, regelstyrd förvaltningslogik
- Första versionen av förvaltningslogiken är regelstyrd kod (ingen LLM) – agentautonomi införs efter att AI-abstraktionslagret (B-009, Fas 3) är byggt
- Varje förvaltningsbeslut loggas med motivering (spårbarhetskrav, jfr B-016)
- Om riktigt kapital någonsin införs krävs ett nytt beslut som uttryckligen ersätter både detta och B-003

---

### B-018 | 2026-07-08 | Databricks Lakebase ersätter Supabase som databas

**Beslut:** Som databas används **Databricks Lakebase** (serverless Postgres, Free Edition) istället för Supabase. All databasåtkomst i Python sker fortfarande via **SQLAlchemy** – ingen ändring av ORM-lagret eftersom Lakebase är Postgres-kompatibel över standardprotokollet.

**Motivering:**
- Projektet är ett PoC för en "AI-first"-strategi i tjänstepensionsbranschen – Databricks ekosystem (BI, analys, framtida ML/aktuariella modeller) passar den ambitionen bättre än Supabase, som bara är en databas
- Karl har befintlig vana vid Databricks, vilket sänker tröskeln för att bygga vidare på analys-/rapporteringssidan
- Lakebase är Postgres-kompatibel "under huven" – SQLAlchemy-modellerna som redan är skrivna (`employers`, `insured_persons`) kräver ingen omskrivning, till skillnad från klassiska Databricks Delta-tabeller (som saknar riktig auto-increment, CHECK-constraints, Enum-stöd)
- Free Edition är gratis (icke-kommersiellt bruk), i linje med B-003 (sandbox/simulering) och B-014:s ursprungliga kostnadsresonemang

**Övervägda alternativ:**

*Alternativ 1: Behåll Supabase (B-014 oförändrat)*
Fördelar: redan uppsatt, väldokumenterat, inga öppna frågor kvar. Nackdelar: inget naturligt BI/analyslager, mindre i linje med AI-first-ambitionen.

*Alternativ 2: Klassiskt Databricks (Delta Lake + SQL Warehouse)*
Fördelar: helt Databricks-nativt. Nackdelar: SQLAlchemy-dialekten saknar stöd för centrala OLTP-mönster (auto-increment, constraints) – dåligt pass för transaktionella tabeller som `premium_transactions` och `cases`.

**Konsekvenser:**
- `DATABASE_URL` i `.env` byts från Supabase pooler-URI till Lakebase-instansens Postgres-anslutningssträng (`postgresql://...@ep-....databricks.com/databricks_postgres?sslmode=require`)
- ATT_GÖRA:s hög-prioritetspunkt om Supabase connection pooler görs om till motsvarande Lakebase-uppgift (skapa instans, hämta connection string, kör `seed_supabase.py` – döps eventuellt om)
- **Öppen riskpunkt att verifiera praktiskt innan seed körs:** (1) om extern SQLAlchemy-anslutning med enkel användarnamn/lösenord fungerar i Free Edition utan kontonivå-service principal, (2) om fair-use-kvoten i Free Edition kan stänga av en aktiv databasinstans mitt i drift
- MASTER_CONTEXT §5 (teknisk stack) uppdateras: raden "Databas" ändras från "Supabase (managed PostgreSQL)" till "Databricks Lakebase (serverless Postgres, Free Edition)"

**Ersätter:** B-014

---

### B-017 | 2026-05-16 | Människa som fullständig operatör

**Beslut:** Systemet designas för dual-mode: agenter kör normalt på autopilot, men operatören kan när som helst ta manuell kontroll och utföra samma åtgärder direkt – via Cowork, MCP-kopplingar eller annat gränssnitt. Ingen åtgärd ska vara agentexklusiv.

**Motivering:**
- Sänker tröskeln för att komma igång – operatören kan agera manuellt tidigt medan automatiseringen byggs upp stegvis
- Möjliggör undantag och krissituationer utan att behöva vänta på att en agent triggas
- Cowork + Supabase MCP ger operatören ett naturligt gränssnitt för direkta databasoperationer, utan att skriva kod
- Speglar hur verkliga bolag fungerar: system och människor agerar parallellt, inte i serie

**Konsekvenser:**
- MCP-koppling till Supabase prioriteras även för operatörens direkta bruk, inte bara för agentdrift
- Gränssnitt och behörigheter designas så att manuella och automatiserade åtgärder lämnar samma spår i databasen (samma tabeller, samma loggning)
- Dokumenterat i MASTER_CONTEXT §3.7 som stående designprincip

---

### B-016 | 2026-05-15 | Hybrid orchestration som agentarkitektur

**Beslut:** Agentsamverkan i systemet struktureras som en hybrid mellan två mönster:

- **Dynamisk samverkan** – agenter känner till varandras gränssnitt och kan anlita varandra ad hoc för ostrukturerade, oförutsägbara uppgifter i vardagsarbetet.
- **Orkestrerade flöden** – fördefinierade, sekventiella workflows för kända processer med tydliga triggers. Dokumenteras i `02_system/Agentsystem/`, en MD-fil per flöde.

Orkestrerade flöden används när processen (a) involverar flera agenter i en känd ordning, (b) är compliance-kritisk och måste vara granskningsbar, eller (c) kräver manuellt godkännande vid varje etapp.

**Motivering:**
- Regelverksförändringar, ORSA-processen och rapporteringscykler måste vara deterministiska och fullt spårbara – en tillsynsmyndighet ska kunna följa exakt vad som hände i vilken ordning. Det utesluter ren dynamisk samverkan för dessa processer.
- Dynamisk samverkan är tillräcklig och mer flexibel för ad hoc-uppgifter där utfallet inte är förutsägbart i förväg.
- Hybrid-modellen är etablerad best practice i multi-agent-system (jfr LangGraph, Autogen, CrewAI) och kombinerar spårbarhet med flexibilitet.

**Övervägda alternativ:**

*Alternativ 1: Ren dynamisk samverkan*
Agenter har kopplingar och avgör själva när och hur de anlitar varandra. Fördelar: flexibelt, hanterar oförutsedda situationer bra. Nackdelar: svårt att granska i efterhand, oförutsägbart beteende i compliance-kritiska processer, svårare att felsöka.

*Alternativ 2: Ren orkestrering*
Alla agentinteraktioner definieras i förväg som strukturerade flöden. Fördelar: maximalt spårbart och deterministiskt. Nackdelar: orimlig overhead för vardagsarbete, skalerar dåligt – varje ny interaktionstyp kräver ett nytt dokumenterat flöde.

**Konsekvenser:**
- `02_system/Agentsystem/` skapas för orkestrerade flöden (en MD-fil per flöde)
- Kända kandidater för orkestrerade flöden: regelförändringsflödet, ORSA-processen, rapporteringscykeln
- Varje orkestrerat flöde dokumenterar trigger, inblandade agenter, godkännandesteg och spårbarhetskrav

---

### B-015 | 2026-05-14 | Mappstruktur: dokumentation och kod separerade

**Beslut:** Projektets mappstruktur separerar dokumentation (svenska namn, numrerade mappar i roten) från Python-kod (i `src/`, engelska namn).

- **Dokumentation:** `01_domän/`, `02_system/`, `03_skills/`, `04_regulatoriskt/`, `05_styrdokument/` – svenska namn OK
- **Kod:** `src/agents/`, `src/skills/`, `src/models/`, `src/ai/`, `src/utils/` – engelska namn
- **Övrigt:** `tests/`, `data/`, `scripts/` på rotnivå

För skills och agenter används mönstret att *instruktion (MD)* ligger i dokumentationsmappen och *implementation (Python)* ligger i `src/`. En skill identifieras alltså av två filer:

- `03_skills/data/hämta-kunddata.md` (instruktion)
- `src/skills/data/get_customer_data.py` (implementation)

**Motivering:**
- Pythons modulnamn klarar inte svenska tecken (`å`, `ä`, `ö`) – `import skills.beräkning` är ogiltigt
- Att bygga ihop instruktion och kod i samma mapp (alternativ "skill = en mapp") fungerar inte med svenska kategorinamn
- Separationen bevarar svensk dokumentationsestetik utan att kompromissa med kodens importerbarhet
- Mappning mellan svenska och engelska kategorinamn dokumenteras i MASTER_CONTEXT §7

**Mappning skill-kategorier:**
| Dokumentation (sv) | Kod (en) |
|--------------------|----------|
| `03_skills/data/` | `src/skills/data/` |
| `03_skills/beräkning/` | `src/skills/calculation/` |
| `03_skills/kommunikation/` | `src/skills/communication/` |
| `03_skills/regelverk/` | `src/skills/regulatory/` |

**Konsekvenser:**
- `pyproject.toml` pekar på `src/` som paketrot
- `__init__.py` finns i alla Python-paket
- Skillkatalogen (`03_skills/skillkatalog.md`) listar både MD- och Python-filens sökväg per skill

---

### B-014 | 2026-05-14 | Supabase + SQLAlchemy som databaslager

**Beslut:** Som databas används **Supabase** (managed PostgreSQL i molnet). All databasåtkomst i Python sker via **SQLAlchemy** som ORM/abstraktionslager. Tabeller definieras som Python-klasser, inte som rå SQL.

**Motivering:**
- **Supabase free-tier** räcker för sandbox-skala (500 MB databas, 50 000 MAUs, obegränsade API-anrop) och kostar 0 kr
- Riktig PostgreSQL → projektmiljön speglar verkligheten (i linje med projektets simuleringssyfte)
- Inget Docker eller lokal serveruppsättning krävs
- Webb-UI för att kika på data direkt – bra för debugging och inspektion under utveckling
- **SQLAlchemy** abstraherar bort databasleverantören: schemat följer med vid byte. Samma princip som vår modellagnostiska AI-arkitektur (B-009)
- Schema-versionering via Alembic blir naturlig nästa steg

**Konsekvenser:**
- Skapa Supabase-konto och projekt (se ATT_GORA)
- Spara connection string och API-nycklar säkert – aldrig i Git (skäl till att `.gitignore` är prioriterat)
- All ny kod som rör data skrivs mot SQLAlchemy-modeller, inte direkt SQL
- Backup-strategi behövs på sikt (free-tier saknar automatisk backup)
- **Notera:** Projekt på free-tier pausas efter 7 dagars inaktivitet men kan startas manuellt igen utan dataförlust

---

### B-013 | 2026-05-14 | Git + GitHub som versionskontroll

**Beslut:** Git används som versionskontrollsystem. Hela projektets kodbas och dokumentation lagras i GitHub-repot [Artificiellalecta](https://github.com/karltengelin/Artificiellalecta.git). Cowork kopplas till repot via GitHub-connector.

**Motivering:**
- Git är de facto-standard – stort ekosystem, väl integrerat med Cowork och alla större verktyg
- GitHub ger versionshistorik, ändringsspårning och möjlighet till samarbete på sikt
- Markdown-filer (B-012) diffas bra i Git – passar perfekt med vår dokumentstrategi
- Cowork har inbyggd connector som möjliggör att agenter och utvecklare jobbar mot samma repo

**Konsekvenser:**
- All kod och alla dokument (inkl. MASTER_CONTEXT, beslutslogg, styrdokument, regelverk) versioneras i samma repo
- `.gitignore` måste sättas upp för att exkludera API-nycklar, `.env`-filer, databasfiler etc. (tas vid behov, separat post i ATT_GORA)
- Behöver besluta om branch-strategi senare (main + feature branches? Eller direkt mot main i tidigt skede?)

---

### B-012 | 2026-05-14 | Markdown som primärt informationsformat

**Beslut:** All information i projektet sparas i första hand som Markdown-filer. PDF (eller andra format) genereras från Markdown vid behov – när en människa ska läsa formella beslut, rapporter eller utskick.

**Motivering:**
- Markdown är ren text och därmed lätt för LLM att läsa och tolka, till skillnad från PDF som ofta har komplex struktur
- Markdown är versionskontrollerbart (fungerar väl med Git, diffar är läsbara)
- Markdown är mänskligt läsbart även i råform – ingen specialprogramvara krävs
- Markdown konverteras enkelt till PDF, HTML, DOCX vid behov (Pandoc, WeasyPrint m.fl.)
- PDF låser fast layout men förlorar semantisk struktur – passar leverans, inte arbete

**Konsekvenser:**
- Styrdokument, processbeskrivningar, regelverkstolkningar, agentinstruktioner, beslut, journalanteckningar skrivs alltid som Markdown
- En md→PDF-pipeline ska sättas upp för formell dokumentgenerering
- Mallar (styrdokumentsmallar etc.) skrivs som Markdown med metadata-block i toppen

---

### B-011 | 2026-05-14 | Compliance-agent äger både regelverk och styrdokument

**Beslut:** En enda compliance-agent ansvarar för både regelverkskunskap och styrdokumentsstruktur. Ingen separat styrdokuments-agent skapas.

**Motivering:**
- Regelverk och styrdokument är tätt sammankopplade – ändras en regel kan styrdokument behöva uppdateras, och vice versa
- Att splittra ansvaret skulle skapa agent-till-agent-kommunikation som vi vill undvika (se B-008)
- Skillsbiblioteket räcker för att täcka olika operationer (slå upp regelverk, granska styrdokument, kontrollera efterlevnad etc.)

**Konsekvenser:**
- Compliance-agenten får skills för både regelverksuppslag och styrdokumentshantering
- Andra agenter kan eskalera till compliance-agenten vid juridiskt tveksamma fall – ett av undantagen från B-008

---

### B-010 | 2026-05-14 | Fyrlagermodell för regelefterlevnad

**Beslut:** Regelefterlevnad i projektet struktureras i fyra lager:
1. **Regelverkskällor** (`04_regulatoriskt/`) – ursprungliga lagar, förordningar, föreskrifter
2. **Tolkningar** – översättning av regelverk till operativa konsekvenser för bolaget
3. **Styrdokument** (`05_styrdokument/`) – interna policies, riktlinjer, processer
4. **Operativt arbete** – det dagliga arbetet som agenter och människor utför

Styrdokument ska alltid referera tillbaka till de regelverk de implementerar.

**Motivering:**
- Speglar hur verkliga tjänstepensionsbolag arbetar (LTF/FFFS 2019:21 förutsätter denna struktur)
- Möjliggör spårbarhet – varje regel går att följa till sitt ursprung
- Skiljer på "vad lagen säger" och "vad vi har bestämt" – båda måste vara dokumenterade men inte i samma fil
- Förenklar uppdatering vid regelverksförändringar – tydligt vad som måste revideras

**Konsekvenser:**
- Två separata mappstrukturer i projektet: `04_regulatoriskt/` och `05_styrdokument/`
- Varje styrdokument ska ha standardiserad metadata i toppen (syfte, ägare, beslutas av, refererade regelverk, versionshistorik)

---

### B-009 | 2026-05-14 | Modellagnostisk arkitektur via abstraktionslager

**Beslut:** All kod som anropar AI-modeller ska gå via ett abstraktionslager, inte direkt mot en specifik leverantörs SDK. Det ska gå att byta modell eller leverantör (OpenAI ↔ Anthropic ↔ andra) genom konfiguration, utan att ändra agentkod eller skills.

**Motivering:**
- Undviker inlåsning hos en enskild leverantör
- Modeller utvecklas snabbt – nya, bättre eller billigare modeller kommer löpande
- Olika modeller passar olika uppgifter (en agent kan använda en kraftfull modell, en annan en billigare för enklare uppgifter)
- API-priser och tillgänglighet ändras över tid
- Möjliggör jämförande utvärdering av modellers prestanda inom projektet

**Konsekvenser:**
- Inga direktanrop till `openai.ChatCompletion` eller `anthropic.messages.create` i agent- eller skillkod
- Modellval, API-nyckel och provider hanteras via konfigurationsfil eller miljövariabler
- Prompter skrivs så generiskt som möjligt – leverantörsspecifika finesser kapslas in i abstraktionslagret
- Behöver utvärdera färdiga lösningar (LiteLLM, OpenRouter) eller bygga egen wrapper
- Lägg till `02_system/ai_abstraktion.md` för att specificera lagret

---

### B-008 | 2026-05-14 | Arkitekturprincip: hellre fler skills än fler agenter

**Beslut:** När en ny funktion ska byggas, default är att skapa en eller flera skills som en befintlig agent får tillgång till. Skapa inte en ny agent om det inte krävs ett distinkt mandat eller ansvar.

**Motivering:**
- Agent-till-agent-kommunikation riskerar att tappa kontext vid varje överlämning
- Multi-agent-flöden innebär fler LLM-anrop, vilket är dyrare och långsammare
- Färre agenter = enklare felsökning (tydligt vem som fattade vilket beslut)
- Skills är återanvändbara mellan agenter; en ny agent är en helt ny enhet att underhålla

**Undantag:** Multi-agent är motiverat när olika delar av arbetet kräver fundamentalt olika mandat (t.ex. handläggare som eskalerar till compliance), när parallellt arbete är meningsfullt, eller när det finns behörighetsskillnader.

---

### B-007 | 2026-05-14 | Delat skillsbibliotek med behörighetsmodell

**Beslut:** Alla skills ligger i ett centralt bibliotek (`03_skills/`). Varje agent har en deklarerad lista över vilka skills den får använda – inte alla agenter får tillgång till alla skills.

**Motivering:**
- Delat bibliotek undviker duplicering – en uppdatering slår igenom överallt
- Centralt index gör skills upptäckbara, så samma funktion inte byggs två gånger
- Behörighetsmodellen behövs för GDPR-efterlevnad och säkerhetshygien (se B-006)
- Tydlig agentdefinition: man ser direkt vad varje agent har för verktygslåda

---

### B-006 | 2026-05-14 | Skills med kunddataåtkomst ska ha begränsad behörighet

**Beslut:** Skills som hämtar, ändrar eller exponerar personuppgifter får inte vara tillgängliga för alla agenter. Varje sådan skill ska ha en uttrycklig lista över vilka agenter som är behöriga.

**Motivering:**
- GDPR: dataminimeringsprincipen kräver att endast den som faktiskt behöver data får åtkomst
- Exempel: Kapitalförvaltningsagenten behöver aggregerade portfölj­data, inte enskilda kunders personuppgifter
- Säkerhetshygien: minskar attackytan om en agent kompromiteras eller får felaktiga instruktioner
- Internrevision/spårbarhet: tydligt vem som hade rätt att se vad

---

### B-005 | 2026-05-14 | Hybrid dataarkitektur: databas + dokumentlager

**Beslut:** Strukturerad data (kunder, policys, transaktioner) lagras i en databas. Regler, processer, villkor och instruktioner lagras som textfiler.

**Motivering:**
- Speglar hur verkliga bolag arbetar
- Databas ger frågbarhet och dataintegritet för operativa flöden
- Dokumentlager ger versionerbara, läsbara regelverk som både människor och AI kan tolka

---

### B-004 | 2026-05-14 | Python som primärt programspråk

**Beslut:** All kod skrivs i Python där inte annat motiveras.

**Motivering:**
- Bred ekosystem för dataanalys, aktuariella beräkningar, API-integrationer
- Användarens preferens
- God Claude-kompetens i språket

---

### B-003 | 2026-05-14 | Sandbox/simulering, inga riktiga kunder

**Beslut:** Plattformen byggs som ett simulerat bolag med fiktiv data. Inga riktiga kunder eller riktigt kapital hanteras.

**Motivering:**
- Möjliggör experiment och felsteg utan reglerings- eller skaderisk
- Kringgår tillståndskrav från Finansinspektionen
- Möjliggör utveckling av processer som speglar verkligheten

---

### B-002 | 2026-05-14 | Scope begränsat till ITP1 ålderspension

**Beslut:** Endast ålderspension inom kollektivavtalet ITP1 ingår. Sjukpension, familjepension, ITPK, andra kollektivavtal och individuella lösningar är utanför scope.

**Motivering:**
- Begränsar komplexitet till en hanterbar nivå
- Möjliggör djupare detaljerings­grad inom ett tydligt avgränsat område
- ITP1 är en välanvänd och väldokumenterad produkt – bra för simulering

---

### B-001 | 2026-05-14 | Master-kontextdokument som projektets fundament

**Beslut:** `MASTER_CONTEXT.md` är det dokument som alla Claude-sessioner och agenter ska läsa först. Det innehåller vision, scope, arkitektur och status.

**Motivering:**
- Garanterar att varje ny session har samma utgångspunkt
- Förebygger drift och inkonsekvenser mellan sessioner
- Fungerar som onboardingdokument för framtida agenter

---

## Mall för nya beslut

```
### B-XXX | YYYY-MM-DD | [Kort titel]

**Beslut:** [Vad bestämdes]

**Motivering:**
- [Varför]
- [Varför]

**Konsekvenser:** [Vad det innebär praktiskt, om relevant]

**Ersätter:** [Referens till tidigare beslut om det är en ändring]
```
