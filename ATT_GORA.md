# Att-göra-lista – ITP1 Administrationsplattform

> Löpande backlog över saker som ska göras, byggas eller utredas. Strukturerad efter prioritet och område.
>
> **Format:** Markera klart med ✅. Lägg till datum och kort kommentar när något genomförs. Saker som inte längre är aktuella stryks ej – arkiveras längst ned.

---

## 🗂️ Program & delprojekt (B-024)

Hela programmet (visionen om ett AI-native tjänstepensionsbolag) är strukturerat i nio delprojekt, se `MASTER_CONTEXT.md` §4b och mappen `projekt/`. Fasplanen och prioritetslistorna nedan är oförändrade och gäller fortsatt – de hör hemma under specifika delprojekt enligt denna mappning:

- Fas 1 (premiemotor) + regelverksutbyggnad → **Delprojekt 4: Produktregelverk & villkor**
- Fas 2 (paper trading) → **Delprojekt 5: Kapitalförvaltning**
- Fas 4/5 (handläggar-UI + handläggaragent) → **Delprojekt 1: Ärendehantering**

Delprojekt 2 (BI & insikter), 8 (Företagsöversikt, första version `foretagsoversikt.html`) och 9 (Processkartor) är påbörjade och har sina nästa steg i respektive `projekt/<nr>_<namn>/PROJEKTPLAN.md`. Delprojekt 3 (Kundportal), 6 (Avdelningsfunktioner) och 7 (Kundchattbot) har ännu inga detaljerade uppgifter. Även de bryts ut till egna listor i sina projektplaner allt eftersom de påbörjas, istället för att trängas in i denna lista.

---

## 📋 Fasplan (beslutad 2026-07-12)

Övergripande ordning för de kommande byggfaserna. Detaljuppgifter ligger under respektive prioritetsrubrik nedan.

**Justerad byggordning 2026-10-11 (B-028):** försäkringssystemet först (Fas 1 inklusive tjänstelagret, Fas 1f), därefter handläggar-UI:t ovanpå tjänstelagret (Fas 4), och sist agentlagret – harness (Fas 3b) följt av handläggaragenten (Fas 5). Agentverktygen byggs som tunna omslag runt tjänstelagrets operationer. Kapitalförvaltningen (Fas 2) är oberoende och kan gå parallellt. Fasnumren är oförändrade; ordningen är **1 → 1f → 4 → 3b → 5 → 3c**.

1. **Fas 1 – Försäkringssystemet (premiemotorn):** ITP1-domändokument, tabellerna `policies` + `premium_transactions`, premieberäkning som skill, genererad premiehistorik. **Fas 1f – Tjänstelagret** (`02_system/tjänstelager.md`): alla operationer mot försäkringssystemet via ett gemensamt lager som handläggar-UI, agenter och skript använder, med agentåtkomst per operation (bl.a. *endast handläggare*) och händelselogg. Regelstyrda beräkningar och operationer (uttag, paus, garanti, pensionsbelopp) bygger på produktreglerna från delprojekt 4, antagna som PR-ITP1 v1.0 (B-031, gäller från 2026-11-01)
2. **Fas 2 – Kapitalförvaltning (paper trading, B-019):** placeringsriktlinje i `05_styrdokument/`, tabellerna `portfolios`/`portfolio_holdings`/`trades`, marknadsdata via gratis-API, regelstyrd förvaltningslogik med beslutslogg. Simulerad wallet – inget riktigt kapital (B-003)
3. **Fas 3 – AI-abstraktionslagret (B-009):** blockerar all agentkod – byggs före agenterna. ✅ **2026-10-11** byggt i `src/ai/` (B-025). Fortsättning enligt B-026 (`02_system/agentekosystem.md` §12): **Fas 3b** harness v1 (skill-register, poddar, agentloop, körjournal) efter Fas 4 och före Fas 5, **Fas 3c** delegering och flödesmotor inför flaggskeppsscenariot
4. **Fas 4 – Handläggar-UI (B-020):** FastAPI-backend ovanpå tjänstelagret (Fas 1f) + tabellvyer + godkännandekö + inbyggd Claude (se utredningen under 🔵 nedan). Handläggaren gör ändringar för kund via tjänstelagrets operationer. Kundportal byggs senare på samma backend
5. **Fas 5 – Handläggaragent + `cases`-tabell + första skills**

---

## 🔴 Hög prioritet – grunden

- [x] **2026-07-12** Fas 1a: `01_domän/ITP1_regelverk.md` och `01_domän/försäkringsvillkor.md` skrivna – premietrappan med 2026-belopp (IBB 83 400 kr, brytpunkter 52 125/208 500 kr/mån) verifierade mot Avtalat/Collectum/Regeringen, åldersfönster 25–66 (månadsbaserat), IBB-historik 2023–2026 för retroaktiv mockdata, implementationsregler för premiemotorn i regelverkets §8
- [x] **2026-07-12** Fas 1b: `policies` och `premium_transactions` – dokumenterade i `databasschema.md` (§5–6) och implementerade som SQLAlchemy-modeller. Ett avtal per försäkrad (B-021), kapital härleds ur transaktioner, `calculation_basis` (JSONB) ger revisionsspårbarhet, partiellt unikt index säkrar en ordinarie premie per avtal/månad. DDL Postgres-validerad. `scripts/setup/create_tables.py` skapar tabellerna (körs av operatören)
- [x] **2026-07-12** Fas 1c: Premiemotor som skill – `03_skills/beräkning/beräkna-itp1-premie.md` + `src/skills/calculation/calculate_itp1_premium.py`. Ren beräkningsfunktion (trappa, åldersfönster på månadsnivå, calculation_basis för spårbarhet), 17 tester gröna mot handräknade exempel. Dessutom: `base_amounts`-tabell (schema §7 + modell + seed-skript) och första versionen av `03_skills/skillkatalog.md`
- [x] **2026-07-12** Fas 1e: Försäkringsmodell omdesignad (B-022) – flera försäkringar per person, `policy_states` (tillståndsperioder), `policy_benefits` (förmåner; TGL/familjeskydd förberedda), premier flyttade till förmånsnivå. `scripts/migrations/legacy/rebuild_insurance_tables.py` bygger om, generatorn skapar försäkring+förmån+lägen+premier
- [x] **2026-07-12** Fas 1d: `scripts/demo/generate_premium_history.py` – skapar ett avtal per försäkrad (AL-NNNNNN, fribrev för avslutade) och premiehistorik 2023-01–2026-06 via premiemotorn med rätt IBB per år, lönedeflator 2,5 %/år bakåt, åldersfönsterkontroll. Idempotent, `--dry-run`-stöd. Hjälpfunktioner sandboxtestade. *(Premiemotorns tester skrevs i Fas 1c – 17 gröna)*

- [x] **2026-10-11** Lakebase-projektet återskapat – det gamla projektet fanns inte längre i Free Edition (troligen borttaget av Databricks, jfr B-018:s öppna riskpunkt 2). Operatören skapade nytt projekt och rollen `app_backend`; databasen återuppbyggdes med skripten: `create_tables` (7 tabeller), `seed_base_amounts` (2023–2026), `seed_mock_data` (20 arbetsgivare, 500 försäkrade från samma CSV-filer), `generate_premium_history` (498 försäkringar, 15 097 premietransaktioner, 39,0 Mkr). All data är genererad och reproducerbar – ingen förlust
- [x] **2026-07-08** Skapa Databricks Free Edition-konto + Lakebase-instans, uppdatera `DATABASE_URL` och kör seed *(ersatte Supabase-uppgiften, se B-018)* – projekt `artificiellalecta` skapat på `artificiellalecta@gmail.com`, Postgres 18, region AWS (us-east-2). Password-auth aktiverad, native roll `app_backend` skapad. Öppen riskpunkt från B-018 löst: extern SQLAlchemy-anslutning med enkel användarnamn/lösenord fungerar utan problem i Free Edition. Seed kört: 20 arbetsgivare, 500 försäkrade.

- [x] **2026-05-15** Skriva `02_system/agentkarta.md` – tio agentskelett i `02_system/agenter/` plus agentkarta (commit `b88da94`)
- [x] **2026-07-12** Skriva `03_skills/skillkatalog.md` – första versionen skapad i Fas 1c med premiemotorn + planerade skills. Underhålls löpande
- [x] **2026-10-11** **Bygga ut produktnära `04_regulatoriskt/`** – källregister, tolkningar och underlag per regelverk för ITP, LTF, FFFS, FAL, skatt, GDPR, DORA, distribution, SFDR, AI och AML (delprojekt 4). Bolagets fullständiga policies och rapportering hör till egna verksamhetsprojekt
- [x] **2026-10-11** **Delprojekt 4: sammanhängande produktpaket** – PR-ITP1 v1.0 (34 regler), villkor v2.0, tio tolkningar och leveranskontroll; infört genom B-031, gäller från 2026-11-01. Regelkod, migrationer och automatiserade regeltester görs i senare sessioner
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

## 🔴 Fas 1f – Tjänstelagret (B-028) – byggs nu

Design: `02_system/tjänstelager.md`. Byggs i den tvärgående chatten (alternativ A); Codex fortsätter med produktreglerna i delprojekt 4. Reglerna är antagna (B-031, gäller från 2026-11-01); regelspecifika operationer byggs med pensions- och betalningsmotorn.

- [x] **2026-10-11** **T1: Grunden** – operationskontrakt, operationsregister, **åtkomstregistret** `src/services/access_register.yaml` (en rad per operation, ändras där), aktörer (handläggare/agent/system), åtkomstkontroll med nivåerna `AGENT`/`APPROVAL`/`HUMAN_ONLY` och golven (saknas i registret → endast handläggare; `external` → minst godkännande; regel som inte är `godkänd` → endast handläggare), godkännandemekanism och händelselogg. Tester som visar att en agent inte kan utföra en `HUMAN_ONLY`-operation. Avgör hur tjänstelagret testas mot databasen (JSONB kräver Postgres). *Klart: `src/services/` med 42 tester; godkännandekön och händelseloggen ligger i minnet/JSONL tills databastabellerna kommer i T3. Testdatabasfrågan avgörs i T2, när första operationen läser databasen*
- [x] **2026-10-11** **T2: Första läsoperationerna** – försäkringsöversikt per försäkrad, premiehistorik, förhandsberäkning av premie (premiemotorn, PR-ITP1-001). *Klart: `src/services/operations/` (alla tre `AGENT` i registret), 16 tester mot en testdatabas i minnet (modellerna gjorda portabla, Postgres-DDL verifierat oförändrad). Verifierat mot Lakebase 2026-10-11 efter återuppbyggnaden: översikt och premiehistorik stämmer mot varandra, förhandsberäkningen ger 10 708,13 kr*
- [x] **2026-10-11** **Backup före T3** – `scripts/maintenance/backup_database.py` skriver alla tabeller till `backups/<tidsstämpel>/` (JSONL + manifest, gitignorerat), `scripts/maintenance/restore_database.py` läser in till tomma tabeller. Första backupen tagen (15 097 premietransaktioner m.m., 9,6 MB). *Kör regelbundet – t.ex. Windows Schemaläggaren – och alltid före större ändringar*
- [x] **2026-10-11** **Produktregler för T3 finns** – delprojekt 4 levererade regelpaketet PR-ITP1 v1.0 (34 regler, bl.a. PR-ITP1-014 löneunderlag och PR-ITP1-019 rättelser). T3:s operationer kopplas till paketets regler. Tjänstelagret läser det nya formatet: regler med status *specificerad* räknas som ej godkända tills paketet är infört
- [x] **2026-10-12** **Koordinering med delprojekt 4 vid införandebeslutet för PR-ITP1 v1.0** – operatören antog paketet (B-031). Raden `> **Införandebeslut:** B-031 | **Gäller från:** 2026-11-01` står i `01_domän/produktregler/README.md`. Tjänstelagret ser reglerna som *kommande* till 2026-10-31 och som godkända från 2026-11-01; då blir `register_salary_report` och `set_policy_paid_up` `APPROVAL` för agenter enligt registret, medan `correct_premium_transaction` förblir `HUMAN_ONLY`. Testerna som utgick från ett ej infört paket prövar nu det läget i en kopia av regelmappen
- [ ] **2026-11-01: generera om operationsförteckningen** – förteckningen visar regelstatus för dagens datum. Kör `python scripts/documentation/list_operations.py` 2026-11-01 eller senare och committa, annars fallerar `tests/test_services_listing.py` från den dagen (*kommande* blir *godkänd* och effektiv nivå blir `APPROVAL`)
- [x] **2026-10-11** **T3a: Händelselogg och godkännandekö i databasen** – tabellerna `operation_events` och `approval_requests` (`databasschema.md` §9b–9c), används automatiskt med databasanslutning: loggraden skrivs i samma transaktion som ändringen, kön överlever omstarter. 5 tester mot testdatabasen
- [x] **2026-10-11** **Godkännandets transaktionshantering rättad** – review visade att ett godkännande kunde spara ändring och loggrad men inte ärendets status, så att ett nytt försök verkställde igen. Nu en transaktion per anrop (`services/transaction.py`): status, ändring och loggrad – liksom förslag och avslag med sina loggrader – sparas tillsammans eller inte alls. Ärendet tas med en villkorlig UPDATE (radlås i Postgres), så samtidiga godkännanden inte kan verkställa två gånger; operationer får inte göra egna commits; agentförslag provkörs mot aktuellt läge. Ingen schemaändring. Tester i `tests/test_services_transactions.py`; verifierat mot Postgres 2026-10-11 (`tests/test_services_postgres.py`, isolerad databas `svc_test`)
- [x] **2026-10-11** **T3: Första skrivoperationerna** – modellval stämda av med operatören (B-030). `register_salary_report` (ersätter planerade `register_salary_change`; ny tabell `salary_reports`, löneunderlag per person/arbetsgivare/månad, ny rapport eller rättelse som ny version) och `set_policy_paid_up` (avanmälan + fribrev, bara ej startad pension, ingen framtidsdatering) är `APPROVAL`. `correct_premium_transaction` (länkad rättelserad via ny kolumn `corrects_transaction_id`; ej mottagen premie och tillägg på mottagen – minskning av mottagen premie blockeras) är `HUMAN_ONLY`. Läsoperationen `get_salary_reports` är ny. Stödda och blockerade fall: `02_system/tjänstelager.md` §9.1. Migration: `scripts/migrations/migrate_t3_schema.py`. **Verifierat mot Postgres 2026-10-11:** `tests/test_services_postgres.py` (7 tester) mot den isolerade databasen `svc_test` i Lakebase-projektet (Postgres 17, READ COMMITTED) – samtidiga godkännanden, löneunderlag, premierättelser och fribrev ger ett utfall, och migrationen från det gamla schemat blir identisk med `create_all`. **Lakebase:** Migrerat i Lakebase 2026-10-11 efter backup `backups/20261011T151353Z` och dry-run; radantalen oförändrade (15 097 premietransaktioner), en andra körning gjorde ingenting; läskontroll efteråt i skrivskyddad anslutning (schema, constraints, index, läsoperationerna och kapitalet 39,0 Mkr stämmer). Inget skrivprov mot Lakebase (operatörens beslut). `terminate_policy` är uppskjuten som egen punkt nedan
- [ ] **`terminate_policy` – uppskjuten från T3.** Slutavräkning (PR-ITP1-027) och dödsfallsavräkning (PR-ITP1-010) kräver uttagsdelar, månadsanspråk, betalningsskuld och kapitaljournal – byggs med pensions-/betalningsmotorn, inte som en lägesändring
- [ ] **Separat premieläge** – fribrev under pågående eller pausad pension kräver att premieförloppet skiljs från pensionsläget (UTTAG_GEMENSAMT); dagens `policy_states` har ett läge per försäkring. Tas med uttagsmodellen
- [ ] **Premie ur löneunderlag** – fakturering och fördelning av ordinarie premie från `salary_reports` (PR-ITP1-001/015/017) är ett eget steg; registreringen skapar ingen premie
- [ ] **Godkännandekö för handläggaren** – `tjänstelager.md` §6 och `agentekosystem.md` nämner ett CLI i Fas 1f; det finns inte än (kön nås via `ServiceLayer.approve/reject`). Byggs här eller direkt i handläggar-UI:t (Fas 4)
- [x] **2026-10-11** **T4: Förteckning över operationer** – `02_system/tjänstelager_operationer.md` genereras med `python scripts/documentation/list_operations.py` (utan databas och modellanrop): typ, produktregler med status, PII, registrets nivå, effektiv nivå och skäl, hämtat från `ServiceLayer.decision()`. Deterministisk; `tests/test_services_listing.py` fallerar om filen inte är aktuell. Regelstatus tar nu även hänsyn till `Gäller från` i införandebeslutet (*kommande* = ej godkänd)

---

## 🟠 Fas 3b–3c – Harness och agentsamverkan (B-026)

Begrepp och design: `02_system/agentekosystem.md` (§1 begrepp, §4–6, §12 byggordning). **Byggs efter Fas 4** (B-028) – agentverktygen kapslar in tjänstelagrets operationer. Fas 3b blockerar Fas 5 (handläggaragenten).

**Fas 3b – Harness v1**
- [ ] **3b-1: `src/agents/ecosystem.yaml`** – team, agenter, poddmontering och gränser (steg- och kostnadstak). Avgör den öppna formatfrågan i `agentekosystem.md` §13
- [ ] **3b-2: Skill-kontrakt och skill-register** – skills är tunna omslag runt tjänstelagrets operationer (och rena beräkningar); registret bygger verktygsdefinitioner (`ToolSpec`) ur operationernas indatamodeller (§5.2, `tjänstelager.md` §8)
- [ ] **3b-3: Guardrails i harness** – agenten ser och kan bara anropa verktyg ur sina poddar; `HUMAN_ONLY`-operationer visas aldrig; nekade skills; tester som visar att otillåtna verktyg inte går att anropa
- [ ] **3b-4: Agentloopen** – instruktion ur `02_system/agenter/<agent>.md`, `ai.bind(team, agent, run_id)`, append-only historik, steg- och kostnadstak (§4.2)
- [ ] **3b-5: Godkännande i harness** – harness hanterar svaret *väntar på godkännande* från tjänstelagret (kön finns där sedan Fas 1f, T3) och rapporterar det i körjournalen (§5.3)
- [ ] **3b-6: Körjournal** – JSONL per körning i `logs/agent_runs/`, länkad till anropsloggen via `run_id` (§4.3)
- [ ] **3b-7: Första poddarna** – `berakning` (premiemotorn) och läsoperationerna från tjänstelagret; skillkatalogen får pod-kolumn
- [ ] **3b-8: Tester och röktest** – agentkörningar mot `FakeProvider` utan nätverk, plus ett röktest mot riktig modell
- [ ] **3b-9: Admin-sida – Agentteam → Körgränser** *(tillagd 2026-10-12 på operatörens begäran)* – operatören kan se effektiva gränser och ändra kostnadsbudget, modellsteg, verktygsanrop, aktiv tidsgräns och delegeringsgränser per team/agent. Validera värden och arv mellan globala, team-, agent- och rotgränser. Spara varaktigt med konfigurationsversion och ändringslogg (tid, aktör, tidigare och nytt värde); bestäm relationen till `ecosystem.yaml` så att samma inställning inte får två sanningskällor. Nya körningar använder den nya versionen; pågående körningar behåller sin version. Endast autentiserad operatör får ändra; befogenheter och godkännandekrav hanteras separat. **Beroenden:** handläggar-UI:t (Fas 4), 3b-1 och 3b-4; delegeringskontroller aktiveras med 3c-1. Inställningarna hör till harness, utanför försäkringstjänstelagret. Startgränser: `02_system/harness.md` §6.3.

**Fas 3c – Samverkan (inför flaggskeppsscenariot)**
- [ ] **3c-1: Delegering mellan team** – `delegate_to_team` med strukturerat uppdrag, `parent_run_id`, djup- och kostnadstak (§6.1)
- [ ] **3c-2: Flödesmotor** – persisterat tillstånd och godkännandesteg; tabeller för flöden, godkännanden och körjournal i `databasschema.md` (körning mot Lakebase enligt AGENTS.md §4.5)
- [ ] **3c-3: Första flödet** – regelförändrings-/flaggskeppsflödet (§6.2)

**Senare:** MCP-exponering av poddar (§9), anropsloggen i databasen, egen Lakebase-roll för PII-poddar (sätts upp av operatören), kostnadsindikatorer per team.

---

## 🟡 Medium prioritet – domänkartläggning

- [x] **2026-10-11** Specificera AI-abstraktionslagret i `02_system/ai_abstraktion.md` – LiteLLM, OpenRouter och egen wrapper utvärderade; egen tunn wrapper beslutad (B-025) och byggd i `src/ai/` (Anthropic Messages API + OpenAI Responses API, roller `fast`/`standard`/`deep` med reserv hos andra leverantören, team-nycklar, anropslogg, 81 tester). Agentekosystemet designat i `02_system/agentekosystem.md` (B-026)
- [ ] **Operatör: lägg in API-nycklar och kör röktestet** – `ANTHROPIC_API_KEY` och `OPENAI_API_KEY` i `.env`, sedan `pip install -e .[dev]` i huvudrepots `.venv` och `python scripts/diagnostics/smoke_test_ai.py` (några ören). Verifierar båda adaptrarna, verktygsloop och korsleverantörsreserv mot riktiga API:er
- [ ] **Kartlägga processer** i `01_domän/processer_översikt.md` (kundärenden, premiehantering, rapportering, etc.)
- [x] **2026-07-12** Skriva ut försäkringsvillkor för ITP1 ålderspension i `01_domän/försäkringsvillkor.md` *(gjordes i Fas 1a)*
- [x] **2026-10-12** **Dokumentera aktuariell SIM-grund** – låst SCB-tabell 2025, unisex, förbättring och marginal, oändlig svans, garantidelar, annuiteter, arvsvinst och bolagsfinansiering i `01_domän/aktuariell_grund.md` och `01_domän/parametrar/PARAMETERREGISTER.md`, med räkneexempel i leveranskontrollen. Produktinriktning B-027; införd som del av PR-ITP1 v1.0 genom B-031, gäller från 2026-11-01. Professionell tariffvalidering för verklig verksamhet är en separat aktivitet.
- [x] **2026-05-15** **Designa regelförändringsflöde** – multi-agent-flöde som triggas när ett regelverk ändras: compliance-agent gör tolkning och konsekvensanalys, utvecklaragent identifierar kodpåverkan, kommunikationsagent förbereder ev. kundkommunikation. Dokumenterat i `02_system/Agentsystem/regelförändringsflöde.md` och utökat till flaggskeppsflödet i `02_system/agentekosystem.md` §6.2 (B-026). Ett av undantagen från B-008 (kräver olika mandat). Implementeras i Fas 3c (3c-3)

## 🟢 Lägre prioritet – när grunden står

- [ ] **Sätta upp md→PDF-pipeline** – välja verktyg (Pandoc eller WeasyPrint), definiera mallar för formella dokument (rapporter, kundbrev, styrelseprotokoll)
- [ ] **Standardmall för officiella dokument** – logga, sidhuvud/sidfot, signaturplats, sidnumrering, dokument-ID, versionsinfo. Tas i samband med PDF-pipelinen
- [ ] **Bygga första agent: Handläggaragent** (ärendehantering)
- [ ] **Bygga kommunikationsagent** – äger bred utgående kommunikation (kundutskick, mailbesvarande, standardiserade meddelanden). Separerad från handläggaragenten för att skilja ärendelogik från kommunikationsarbete. Mandat motiveras i BESLUTSLOGG när agenten byggs (avsteg från B-008).
- [ ] **Bygga första skills:** `hämta-kunddata`, `skriv-kundmail`, `tolka-itp1-fråga`
- [ ] **Skill: complianceöversyn** (på compliance-agenten) – proaktiv genomgång av regelverkskartan mot styrdokument och processer. Rapporterar gap och misstänkta diskrepanser. Triggas manuellt eller schemalagt. Skapas som `03_skills/regelverk/complianceöversyn.md` + `src/skills/regulatory/compliance_review.py`.
- [ ] **Sätta upp koppling Cowork ↔ Gmail** (MCP)
- [x] **2026-07-12** **Generera testdata** – fiktiva kunder, policys, transaktioner. Arbetsgivare och försäkrade 2026-05-16, försäkringar och premiehistorik 2023–2026 i Fas 1d; återskapat i nya Lakebase-projektet 2026-10-11

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
     anropar modellen via AI-lagret (`src/ai/`, B-009 – inte direkt mot
     Claude API) med systemprompt + verktyg, returnerar svar.
     Sessionshistorik sparas per konversation (troligen i Lakebase, B-018).

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

- [x] **2026-10-11** **Git branch-strategi** – en namngiven branch per uppgift och AI-verktyg, merge till main efter operatörens OK (B-023, `AGENTS.md` §4)
- [ ] Hur ska godkännandeflöden fungera (mail till kund ska godkännas innan utskick)? *(ramverk beslutat i B-026: sidoeffektsklasser, `02_system/agentekosystem.md` §5.3. Godkännandekön och flaggan* endast handläggare *finns i tjänstelagret sedan Fas 1f T3 – tabellen `approval_requests`, `02_system/tjänstelager.md` §4 och §6, B-028. Kvar: gränssnitt för kön och externa handlingar som utskick)*
- [ ] Loggning och spårbarhet – hur sparas agentbeslut? *(ramverk beslutat i B-025/B-026: anropslogg `02_system/ai_abstraktion.md` §10 + körjournal `02_system/agentekosystem.md` §4.3. Tjänstelagrets händelselogg finns i Lakebase sedan Fas 1f T3a (`operation_events`); körjournalen byggs i Fas 3b och dess lagring i Lakebase avgörs i Fas 3c)*
- [ ] Backup-strategi för databas och dokument *(aktualiserad 2026-10-11: Lakebase-projektet försvann. Genererad data återskapas med skripten, men data som skapas av handläggare och agenter via tjänstelagret – händelselogg, godkännanden, ändringar – går inte att återskapa. Delvis löst samma dag: `scripts/maintenance/backup_database.py` och `restore_database.py`, backup togs före T3. Kvar: schemalagd körning. Dokumenten versioneras i git)*

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
