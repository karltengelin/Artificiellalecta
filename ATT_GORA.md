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

Delprojekt 2 (BI & insikter), 8 (Företagsöversikt, första version `foretagsoversikt.html`) och 9 (Processkartor) är påbörjade och har sina nästa steg i respektive `projekt/<nr>_<namn>/PROJEKTPLAN.md`. Delprojekt 3 (Kundportal), 6 (Avdelningsfunktioner) och 7 (Kundchattbot) är ännu inte byggda. För 3 och 6 finns sedan 2026-10-25 en första precisering av beroenden och byggbehov för månadssimulering; detaljerade byggplaner återstår. Uppgifterna bryts ut i projektplanerna allt eftersom projekten påbörjas. Tvärgående behov samlas under **Månadssimulering – byggluckor och samordning** nedan.

---

## 📋 Fasplan (beslutad 2026-07-12)

Övergripande ordning för de kommande byggfaserna. Detaljuppgifter ligger under respektive prioritetsrubrik nedan.

**Justerad byggordning 2026-10-11 (B-028):** försäkringssystemet först (Fas 1 inklusive tjänstelagret, Fas 1f), därefter handläggar-UI:t ovanpå tjänstelagret (Fas 4), och sist agentlagret – harness (Fas 3b) följt av handläggaragenten (Fas 5). Agentverktygen byggs som tunna omslag runt tjänstelagrets operationer. Kapitalförvaltningen (Fas 2) är oberoende och kan gå parallellt. Fasnumren är oförändrade; ordningen är **1 → 1f → 4 → 3b → 5 → 3c**.

1. **Fas 1 – Försäkringssystemet (premiemotorn):** ITP1-domändokument, tabellerna `policies` + `premium_transactions`, premieberäkning som skill, genererad premiehistorik. **Fas 1f – Tjänstelagret** (`02_system/tjänstelager.md`): alla operationer mot försäkringssystemet via ett gemensamt lager som handläggar-UI, agenter och skript använder, med agentåtkomst per operation (bl.a. *endast handläggare*) och händelselogg. Regelstyrda beräkningar och operationer (uttag, paus, garanti, pensionsbelopp) bygger på produktreglerna från delprojekt 4, antagna som PR-ITP1 v1.0 (B-031, gäller från 2026-11-01)
2. **Fas 2 – Kapitalförvaltning (paper trading, B-019):** placeringsriktlinje i `05_styrdokument/`, tabellerna `portfolios`/`portfolio_holdings`/`trades`, marknadsdata via gratis-API, regelstyrd förvaltningslogik med beslutslogg. Simulerad wallet – inget riktigt kapital (B-003)
3. **Fas 3 – AI-abstraktionslagret (B-009):** blockerar all agentkod – byggs före agenterna. ✅ **2026-10-11** byggt i `src/ai/` (B-025). Fortsättning enligt B-026 (`02_system/agentekosystem.md` §12): **Fas 3b** harness v1 (skill-register, poddar, agentloop, körjournal) efter Fas 4 och före Fas 5, **Fas 3c** delegering och flödesmotor inför flaggskeppsscenariot
4. **Fas 4 – Handläggar-UI (B-020):** FastAPI-backend ovanpå tjänstelagret (Fas 1f) + tabellvyer + godkännandekö + inbyggd Claude (se utredningen under 🔵 nedan). Handläggaren gör ändringar för kund via tjänstelagrets operationer. Kundportal byggs senare på samma backend. ✅ **2026-10-12** v1 byggd (S1–S5, se sektionen Fas 4 nedan) – utan inbyggd Claude, som kommer efter harness
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
- [ ] **Fullständig styrdokumentsstruktur** i `05_styrdokument/` – minimal grund för kapitalförvaltningen finns sedan 2026-10-24 (Fas 2a), med struktur, ägarskap, revisionscykel och standardmetadata. Antagande, fullständigt styrdokumentsregister, övriga policies och bolagets samlade kontrollsystem återstår
- [ ] **Gemensamt designspråk för bolaget** – Digital klarhet vald och designgrund v1.0 dokumenterad (B-034, `06_design/`). Återanvändbara komponenter, färdiga mallar och införande i hemsidor, kundportal, handläggargränssnitt, rapporter och presentationer återstår. Se arbetsgång och leveranser under **Grafisk identitet och designsystem** nedan
- [x] **2026-05-16** Definiera databasschema – `02_system/databasschema.md` + SQLAlchemy-modeller för `employers` och `insured_persons`. Övriga tabeller (policies, premium_transactions, portfolio_holdings, cases) skjuts upp till de behövs.
- [x] **2026-05-16** Sätta upp Google-konto för det fiktiva bolaget – Artificiellalecta@gmail.com
- [x] **2026-05-16** Skapa Supabase-konto och projekt – Artificiellalecta-projektet, region Europe *(databasval ersatt av B-018, se Arkiv)*

---

## 🎨 Grafisk identitet och designsystem – hög prioritet

Tillagt **2026-10-24** på operatörens begäran. Tvärgående arbete för hela bolaget.
**Digital klarhet är vald genom B-034.** Designspecifikation v1.0 och visuell
referens finns i [`06_design/`](06_design/README.md), med första gemensamma
designvärden i `src/design/digital_clarity.tokens.json`. Handläggar-UI:t är pilotyta sedan
2026-10-24. Färdiga mallar och införande i företagsöversikten återstår. Målet är ett modernt, stilrent
och sammanhållet uttryck som känns igen i alla kanaler.

**Arbetsordning:** Använd den valda designgrunden när nästa större
gränssnitt eller dokumentmall byggs. Fortsätt bygga funktion stegvis med den grunden.
Befintliga ytor anpassas successivt när de vidareutvecklas. Backend-, regel- och
agentarbete kan fortsätta enligt fasplanen; ingen total ombyggnad av fungerande system
behövs för att införa formspråket. Valet av riktning är klart; konkreta komponenter
och färdiga mallar granskas när de införs.

- [x] **2026-10-24 Visuell riktning och designgrund v1** – fyra riktningar jämförda på rapport, slide och handläggarvy. Operatören valde **Digital klarhet** (B-034). Färger, DM Sans, ordmärke/markör, luft, layout, ikon-/bildstil, diagramstil och läsbarhet dokumenterade i `06_design/designsprak.md`; vald visuell referens bevarad i `06_design/digital_klarhet.html`
- [ ] **Gemensamma designvärden och återanvändning** – första versionshanterade tokenfilen finns i `src/design/digital_clarity.tokens.json` (v1.0, B-034). Koppla dessa värden till webbens CSS och dokument-/presentationsmallar så att kanalerna inte får separata, manuellt underhållna paletter. Bygg vidare på FastAPI/Jinja2/HTMX för handläggar-UI:t; välj inga nya frontendramverk enbart för formspråkets skull. *2026-10-24, webben klar:* `src/web/static/tokens.css` genereras ur tokenfilen (`scripts/web/build_design_tokens.py`, `src/design/web_css.py`), och `app.css` har inga egna färgvärden (`tests/test_design_web_css.py`). Dokument- och presentationsmallar återstår
- [ ] **Fullständigt logotyppaket** – vidareutveckla ordmärket och den enkla indigorutan från Digital klarhet till vektororiginal, frizon och exportvarianter för webb, dokument och presentationer
- [ ] **Pilot och stegvis införande i gränssnitten** – tillämpa grunden på en representativ handläggarvy med tabell, formulär, status, fel och godkännande. Utvärdera tillsammans med rapport- och slideexemplen innan grunden breddas. Återanvänd layout och komponenter i fortsatt UI-arbete; planera anpassning av företagsöversikten, kommande hemsidor och kundportalen. Dashboarden följer grunden inom Databricks möjligheter enligt B-029; eventuella begränsningar dokumenteras. *2026-10-24, pilot genomförd:* hela handläggar-UI:t har Digital klarhet: sidhuvud med ordmärke och aktiv meny, kort, tabeller, formulär, statusmärken, felrutor, godkännandekön och ärendesidorna. Verifierat i webbläsaren mot demodatabasen, även på smal skärm. Kvar: operatörens granskning tillsammans med rapport- och slideexemplen, och därefter breddning
- [ ] **Rapport- och presentationsmallar** – gemensamma mallar för rapport/kundbrev samt presentation med titelbild, innehåll, nyckeltal, tabell och diagram. Dokumentmallarna kopplas till md→PDF-pipelinen nedan; Markdown förblir arbetsformat enligt B-012. En rapport, presentation och webbyta ska kännas som samma bolag även när informationsmängd och layout skiljer sig
- [ ] **Gemensamma skills: skapa rapport/dokumentation och skapa presentation** *(tillagt 2026-10-24 på operatörens begäran)* – planera `skapa-dokumentation` (`create_documentation`, även rapporter) och `skapa-presentation` (`create_presentation`) som två centralt underhållna skills i den gemensamma podden `dokument`, tillgängliga för samtliga team och agenter genom granskad montering. Varje skill tillhör en podd; samma implementation, mallar och designversion återanvänds av alla. Ingen kopia per team/podd och ingen ny agent krävs enbart för formatering (B-007/B-008/B-026). Domänagenten ansvarar för fakta och analys; kommunikation äger de gemensamma mallarna och utveckling den tekniska genereringen. Se `02_system/agentekosystem.md` §5.5 och planerade skills i `03_skills/skillkatalog.md`
- [ ] **Enhetligt svar från valfri agent/team** – när operatören ställer en sakfråga ska agenten använda den gemensamma rapport-/dokumentationsförmågan; presentation används när operatören begär det eller uppdraget anger det formatet. En kort rapport kan visas direkt i chatten; längd och detaljnivå anpassas till frågan. Gemensam grundstruktur: slutsats/svar först, underlag och källor, antaganden/osäkerhet samt eventuella nästa steg. Fullständiga dokument och slides använder de gemensamma mallarna och designvärdena. Koppla användningsregeln till agenternas instruktioner och uppdrag i harness; verifiera med representativa uppdrag till flera team att rätt skill, mallversion och struktur används. Enbart tillgång till skillen garanterar inte användning
- [ ] **Kontrollerad dokumentgenerering** – bygg på dokumentgatewayen och avgränsade utkast enligt `02_system/harness.md` §5.2. Samma mallar får användas i en separat skyddad väg för behöriga PII-underlag; den allmänna dokumentpodden får inte lagra personuppgifter. Innehåll, källor, period och mallversion följer med leveransen. Bestäm resursgränser för binära exporter separat från Markdown-gränserna. Skapande av utkast ger inte rätt att ändra gällande dokument, skicka eller publicera. Externa leveranser följer befintliga godkännanden och gateways. Rapporteringsagenten används för sitt rapporteringsmandat och samordning, och kan återanvända samma två skills
- [ ] **Instruktioner och visuell leveranskontroll** – dokumentera hur människor och agenter hittar rätt version av specifikationen, komponenterna och mallarna. Nya leveranser ska återanvända dessa. Kontrollera representativa webb-, rapport- och presentationsresultat visuellt samt att statusfärger, enheter, perioder och diagram betyder samma sak mellan kanalerna

---

## 🟠 Fas 2 – Kapitalförvaltning (paper trading)

- [x] **2026-10-24** **Fas 2a: Minimal [styrdokumentshierarki](05_styrdokument/styrdokumentshierarki.md)** – dokumentleverans klar som beslutsutkast (SD-STYR-001 v0.1): struktur, ägarskap, revisionscykel och standardmetadata. Antagande och giltighetsdag återstår; fullständig version kvarstår under Hög prioritet
- [x] **2026-10-24** **Fas 2b: [Placeringsriktlinje](05_styrdokument/03_riktlinjer/placeringsriktlinje.md)** – dokumentleverans klar som beslutsutkast (SD-KAP-001 v0.1): tillgångsslag, målvikter 55 % räntor/35 % aktier/10 % kassa, allokerings- och risklimiter, likviditet, ALM, stress och rebalansering. LTF är huvudregim, Solvens II-anda används för riskstyrning; all förvaltning är simulerad. Antagande och giltighetsdag återstår; ingen förvaltningsfunktion är implementerad
- [x] **2026-10-24** **Fas 2c: Tabeller `portfolios`, `portfolio_holdings`, `trades`** – [modellval A–F](projekt/05_kapitalförvaltning/DATAMODELL_BESLUTSFORSLAG.md) tillämpade efter operatörens mandat att välja modell och fortsätta. Portabla SQLAlchemy-modeller och lokala tester; schema §§9d–9f. Explicit startkassa, innehav/saldon härleds senare ur utförda avslut, separata godkännande-/utförande-/avslagskvittenser och prisunderlag. Registrerade via `models` för befintligt `create_tables.py`, som inte har körts; **ej skapade i Lakebase**. Ingen handelsfunktion, marknadsdata, förvaltningslogik eller premiekoppling byggd
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
- [x] **2026-10-12** **Godkännandekö för handläggaren** – byggd direkt i handläggar-UI:t (Fas 4, S3) i stället för ett CLI: `/godkannanden` med lista, godkänn och avslå via `ServiceLayer.approve/reject`. Kön läses med den nya läsoperationen `list_approval_requests` (`HUMAN_ONLY`), se `02_system/handläggar-ui.md`
- [x] **2026-10-11** **T4: Förteckning över operationer** – `02_system/tjänstelager_operationer.md` genereras med `python scripts/documentation/list_operations.py` (utan databas och modellanrop): typ, produktregler med status, PII, registrets nivå, effektiv nivå och skäl, hämtat från `ServiceLayer.decision()`. Deterministisk; `tests/test_services_listing.py` fallerar om filen inte är aktuell. Regelstatus tar nu även hänsyn till `Gäller från` i införandebeslutet (*kommande* = ej godkänd)

---

## 🔴 Fas 4 – Handläggar-UI v1 (B-020, B-028) – byggs nu

Design och drift: `02_system/handläggar-ui.md`. Kod: `src/web/` (FastAPI + Jinja2 + HTMX, inget byggsteg), start `python scripts/web/start_ui.py`. UI:t anropar bara tjänstelagret; bara lokalt (127.0.0.1), ingen inloggning i v1. Branch `claude/handlaggare-ui-v1-1fa1e7`.

- [x] **2026-10-12** **S1: Grund** – app, konfiguration (`HANDLAGGARE_ID`, `HANDLAGGARE_DB` = demo/svc_test/lakebase – Lakebase bara uttryckligen), layout, sök på personnummer eller försäkringsnummer, översikt, löneunderlag och premiehistorik. Lokal demodatabas med fiktivt bestånd (`src/utils/demo_data.py`); Host-kontroll och formulärtoken
- [x] **2026-10-12** **S2: Skrivformulär** för `register_salary_report`, `set_policy_paid_up` och `correct_premium_transaction` – stopp och krockar visas med skäl, regel och *Ingenting har ändrats*; förhandsberäkning av premie
- [x] **2026-10-12** **S3: Godkännandekö och händelselogg** – lista, godkänn och avslå; händelser totalt och per försäkrad. Nya läsoperationer `list_approval_requests`, `count_approval_requests`, `get_operation_events` (`HUMAN_ONLY`)
- [x] **2026-10-12** **S4: Designstopp** – beslutsförslag `projekt/01_ärendehantering/OPERATIONER_BESLUTSFORSLAG.md`, godkänt av operatören med valen A–D och loggat som **B-032**
- [x] **2026-10-12** **S5: Nya operationer (B-032)** – `enroll_insured_person` (`APPROVAL`), `update_current_salary`, `update_contact_details`, `register_employer` (`HUMAN_ONLY`) och `list_employers` (`AGENT`) med formulär och tester; ingen schemaändring (`tjänstelager.md` §9.2)
- [x] **2026-10-12** **S6: Skarp verifiering i Lakebase.** Före körningen:
  - backup `backups/20261012T193537Z`, med 500 försäkrade, 498 försäkringar och 15 097 premietransaktioner;
  - kontroll att T3-schemat redan fanns (`migrate_t3_schema.py --dry-run`);
  - operatörens OK enligt AGENTS.md §4.5.

  Via UI:t mot Lakebase anslöts den märkta verifieringsposten **Vera Verifiering (19920417-1236, AL-000499)** hos BilFöretaget AB #15, med ITP1 från 2026-10-01. Därefter ändrades aktuell lön från 38 000 till 39 500 kr, löneunderlag på 39 500 kr registrerades för 2026-10, och fribrevet sattes med sista dag 2026-10-11.

  Kontroll i en skrivskyddad transaktion:
  - Person, försäkring, förmån och läget premiebetalande 2026-10-01–2026-10-11 finns, följt av fribrev från 2026-10-12.
  - Löneunderlaget v1 finns. Inga premier skapades.
  - Händelseloggen har fyra utförda ändringar med `karl`, motivering och regelstatus (*kommande, gäller från 2026-11-01*).
  - Ett stoppat försök (lön för avslutad anställning) ändrade ingenting.
  - Radantal efteråt: personer 501, försäkringar 499, lägen 527, löneunderlag 1, premier 15 097 (oförändrat).

  Godkännandekön kan inte provas skarpt före 2026-11-01, eftersom agenter inte kan föreslå skrivningar förrän PR-ITP1 v1.0 gäller. Den är provad i demodatabasen, mot `svc_test` och i testerna

**Följdpunkter från Fas 4:**
- [ ] **Anställningshistorik** (tabell `employments`) – återanställning, arbetsgivarbyte, flera anställningar och löneunderlag efter avslutad anställning (PR-ITP1-013). Schemaändring enligt T3-mönstret
- [ ] **Lönehistorik för aktuell lön** – i dag bara aktuellt värde; tidigare värden står i händelseloggen
- [ ] **Namnbyte** som identitetsuppgift (`HUMAN_ONLY`)
- [ ] **Ändra arbetsgivarens uppgifter** (`update_employer_details`) och **arbetsgivarens avslut/paus** med avanmälan av alla försäkrade
- [ ] **Försäkringsbesked vid anslutning** (villkor §14, PR-ITP1-029) – `external`, med kommunikationsagenten
- [ ] **Interna id:n i UI:ts adresser** i stället för personnummer, när verklig autentisering eller kundportalen byggs
- [ ] **Inbyggd Claude i handläggar-UI:t** – efter harness (Fas 3b), se utredningen under 🔵

---

## 🟠 Fas 3b–3c – Harness och agentsamverkan (B-026)

Begrepp och design: `02_system/agentekosystem.md` (§1 begrepp, §4–6, §12 byggordning). **Byggs efter Fas 4** (B-028) – agentverktygen kapslar in tjänstelagrets operationer. Fas 3b blockerar Fas 5 (handläggaragenten).

**Fas 3b – Harness v1**
- [x] **2026-10-24** **3b-1: `src/agents/ecosystem.yaml`** – team, agenter, poddmontering och gränser (steg- och kostnadstak). Formatfrågan i `agentekosystem.md` §13 avgjord: samlad fil (`harness.md` §3.3). *Klart: `src/agents/ecosystem.py` validerar strikt (okända fält, dubbla YAML-nycklar, agent med poddar/sidoeffekter/gränser utöver teamets, dubbla mappningar, `external`, okända nekanden, omklassning av PII eller sidoeffekt) mot tjänstelagrets register, AI-lagrets roller och instruktionernas team-rad. `RunRequest`/`RunResult` i `src/agents/run.py`. Effektiv profil med samtliga skäl och versionsbild (kontrollsummor för policy, åtkomstregister, instruktion och produktregler) i `src/agents/profile.py`; visas med `python scripts/documentation/show_agent_profile.py`. Startgränser enligt `harness.md` §6.3. Första profilen: `forsakring`/`case_handler` med poddarna `kunddata` och `berakning`; `regelverk` och `dokument` väntar på sina gateways*
- [x] **2026-10-24** **3b-2: Skill-kontrakt och skill-register** – skills är tunna omslag runt tjänstelagrets operationer (och rena beräkningar); registret bygger verktygsdefinitioner (`ToolSpec`) ur operationernas indatamodeller (§5.2, `tjänstelager.md` §8). *Klart: `src/agents/skills.py`. Schemat är `{data, reason}` (motivering krävs vid skrivning; inga identitetsfält), okända fält nekas på alla nivåer, anropet går via `ServiceLayer.execute` som agent, APPROVAL ger "föreslå" och ett väntesvar med approval-id. Ingen jokerteckenmappning – operationerna från Fas 4 S5 (`list_employers`, `enroll_insured_person` m.fl.) är omappade och stängda tills de får en poddrad. 67 tester (`tests/test_agents_*.py`). Verktyg med personuppgifter döljs tills PII-podden har sin databasroll (se 3b-3), så i dag är bara `calculate_premium_preview` öppen för handläggaragenten*
- [x] **2026-10-24** **3b-3: Guardrails i harness** – agenten ser och kan bara anropa verktyg ur sina poddar; `HUMAN_ONLY`-operationer visas aldrig; nekade skills; tester som visar att otillåtna verktyg inte går att anropa. *Klart: `src/agents/dispatcher.py` prövar varje anrop – även påhittade och tidigare visade – och hela gruppen i ett modellsvar innan något körs: dubbla call-id, dolt/okänt verktyg, okända fält (falsk identitet), ändrad eller indragen policy under körningen och resursmandatet. Ett nej stoppar gruppen; ett förslag som väntar på godkännande stoppar resten av gruppen. Resursmandatet `src/agents/scope.py` (`ExecutionScope`, byggs av betrodd kod med `scope_for_person`): en försäkrad, dess försäkringar och arbetsgivare, högst 24 månader; stängt som standard (öppen period, id som inte går att pröva och nästlade indata nekas) och resultat med andra personer lämnas inte ut. 25 nya tester, bl.a. mot testbeståndet. PII-verktygen kräver dessutom att tjänstelagret ansluter med teamets begränsade databasroll – se punkten nedan*
- [x] **2026-10-24** **Lakebase-roll för PII-podden `kunddata`** – minimal roll för agentens tjänstelager (läsa försäkringsdata, lägga till förslag och loggrader, ingen uppdatering/radering av logg eller direkt affärs-DML), `harness.md` §5.1. *2026-10-24: operatören skapade rollen `agent_forsakring` (ingen superuser, inga medlemskap) med anslutningar i `.env`. Byggt: två anslutningar i tjänstelagret – agentens roll för läsningar, förslag och loggrader, `app_backend` för provkörning av förslag (`validation_session_factory`, `services.db.agent_service_layer`); rättigheterna i `src/utils/agent_roles.py` sätts med `scripts/setup/grant_agent_role.py` (torrkörning som standard); PII-verktyg visas bara när tjänstelagret ansluter med teamets roll (ersätter spärren `PII_DATABASE_ROLE_READY`). 20 rollprov mot isolerad Postgres gröna (`tests/test_agents_postgres_role.py`). **Infört i Lakebase 2026-10-24** efter operatörens OK (AGENTS.md §4.5): `grant_agent_role.py --apply`, verifierat med rollens egen anslutning – läser beståndet (501 försäkrade, 499 försäkringar, 15 097 premietransaktioner), nekas UPDATE/DELETE, radlås och läsning av loggens innehåll. Ingen data ändrad*
- [x] **2026-10-24** **3b-4: Agentloopen** – instruktion ur `02_system/agenter/<agent>.md`, `ai.bind(team, agent, run_id)`, append-only historik, steg- och kostnadstak (§4.2). *Klart: `src/agents/loop.py` (`run_agent`, `build_context`). Kontext = kort bolagskontext, agentens instruktion, datum och uppdraget; inget förladdas. Före varje modellanrop prövas modellsteg, kostnad, aktiv tid och kontextstorlek – ett nått tak stoppar utan extra anrop; ett svar efter tidstaket eller över kostnadstaket får inga verktyg körda; okänd kostnad stoppar. Väntan på godkännande avslutar utan fler modellanrop, säkerhetsbrott ger `blocked`, tjänstelagrets stopp `needs_human`, vanliga fel får rättas högst två gånger per felklass (`harness.md` §6.4); `refusal`/avklippt/motsägande svar blir aldrig `completed`. Dispatchern skiljer nu säkerhetsbrott (okända fält) från rättningsbara värdefel. 21 tester mot FakeProvider. **Kvar:** tidstaket prövas mellan anrop – ett pågående modellanrop avbryts inte (kräver worker/avbokning, §6.3)*
- [x] **2026-10-24** **3b-5: Godkännande i harness** – harness hanterar svaret *väntar på godkännande* från tjänstelagret (kön finns där sedan Fas 1f, T3) och rapporterar det i körjournalen (§5.3). *Klart: körningen slutar som `waiting_approval` utan fler modellanrop (3b-4) och journalför `approval_wait`. `src/agents/continuation.py`: operatören startar en länkad fortsättning (eget run-id, `continuation_of`, samma rot). `prepare_continuation` läser förslagens utfall via den betrodda anslutningen, vägrar så länge något väntar, nekar skillen för varje avgjord operation (ett godkännande anropas aldrig igen, ett avslag följs inte av ett likadant förslag) och ger bara rotkörningens kvarvarande budget (steg, verktygsanrop, kostnad, aktiv tid). Rå historik återanvänds inte – ny kontext byggs med utfallen*
- [x] **2026-10-24** **3b-6: Körjournal** – JSONL per körning i `logs/agent_runs/`, länkad till anropsloggen via `run_id` (§4.3). *Klart: `src/agents/journal.py`, händelserna `run_started` (versionsbild, tak), `policy_resolved`, `model_returned`, `tool_denied`, `tool_intent` (före tjänstelagret), `tool_completed`, `approval_wait`, `approval_observed`, `run_ended` (förbrukning för segmentet och roten). En skrivare per körning, varje rad synkas till disk; kan journalen inte skrivas görs inget mer. Inga råa personuppgifter: indata, resultat och modelltext som hash; fri text från uppdrag och modell (mål, motiveringar, sammanfattning, avslagsanteckning) bara som hash och längd, systemmeddelanden maskerade (skärpt 2026-10-24 efter röktestet, där en modellsammanfattning med namn och födelsedatum passerade maskeringen). Harness vägrar starta med `AI_LOG_CONTENT` på när agenten har PII-verktyg. 16 tester. **Senare (3c):** journalen i Lakebase (`agent_runs`/`agent_steps`) och invocation-id genom tjänstelagret för entydig koppling till händelseloggen*
- [x] **2026-10-24** **3b-7: Första poddarna** – `berakning` (premiemotorn) och läsoperationerna från tjänstelagret; skillkatalogen får pod-kolumn. *Klart: poddarna `kunddata` och `berakning` finns i `ecosystem.yaml` sedan 3b-1. `03_skills/skillkatalog.md` har pod-kolumn och en genererad tabell över körpolicyns skills (podd, operation, typ, PII, åtkomstregistrets nivå, behöriga agenter) samt omappade operationer – `python scripts/documentation/list_skills.py`, kontrolleras av `tests/test_agents_listing.py`*
- [x] **2026-10-24** **3b-8: Tester och röktest** – agentkörningar mot `FakeProvider` utan nätverk, plus ett röktest mot riktig modell. *Klart: FakeProvider-tester för hela kedjan (3b-1–3b-6) och demokörningen `src/agents/demo.py`. Röktestet `python scripts/diagnostics/smoke_test_agent.py --run` är förberett: handläggaragenten mot det fiktiva demobeståndet i minnet, bara läsning och beräkning, billigaste modellen per leverantör, tak 6 modellsteg och 0,10 USD; utan `--run` görs inga anrop. **Kört 2026-10-24** mot båda leverantörerna (`claude-haiku-4-5`, `gpt-6-luna`): alla kontroller gröna – premien 2 025 kr via verktyget, läsning ur beståndet, inga förslag, 2 modellsteg och 3 verktygsanrop var, totalt 0,012 USD. Första körningen avslöjade två fel som är rättade: Anthropics strikta läge avvisade `minimum` i verktygsschemat (AI-lagret flyttar nu värdegränser till beskrivningen, `src/ai/schema.py`) och journalen läckte namn via fri text (se 3b-6)*
- [ ] **3b-9: Admin-sida – Agentteam → Körgränser** *(tillagd 2026-10-12 på operatörens begäran)* – operatören kan se effektiva gränser och ändra kostnadsbudget, modellsteg, verktygsanrop, aktiv tidsgräns och delegeringsgränser per team/agent. Validera värden och arv mellan globala, team-, agent- och rotgränser. Spara varaktigt med konfigurationsversion och ändringslogg (tid, aktör, tidigare och nytt värde); bestäm relationen till `ecosystem.yaml` så att samma inställning inte får två sanningskällor. Nya körningar använder den nya versionen; pågående körningar behåller sin version. Endast autentiserad operatör får ändra; befogenheter och godkännandekrav hanteras separat. **Beroenden:** handläggar-UI:t (Fas 4), 3b-1 och 3b-4; delegeringskontroller aktiveras med 3c-1. Inställningarna hör till harness, utanför försäkringstjänstelagret. Startgränser: `02_system/harness.md` §6.3.

**Fas 3c – Samverkan (inför flaggskeppsscenariot)**
- [x] **2026-10-25** **3c-0: Designstopp** – beslutsförslag [`02_system/flaggskeppsflöde.md`](02_system/flaggskeppsflöde.md): flödesmotorn, parametrar som versionerad data (`product_parameters`), teamen compliance och aktuarie, gateways för `regelverk`, `dokument` och `bestand`, och en minimal flaggskeppsdemo (fiktiv premieålder 66 → 67). Godkänt med valen A–L och loggat som **B-035**
- [x] **2026-10-25** **3c-P1: Produktparametrar som data** – `product_parameters` (`databasschema.md` §9h) med startvärden från 2023-01-01, `PremiumParameters` i premiemotorn (dagens konstanter är standard), uppslag per premiemånad i `services/parameters.py` för förhandsberäkningen och premierättelsen, versionerna i `calculation_basis`, och läsoperationen `get_product_parameters` (`AGENT`, `tjänstelager.md` §9.4). Migrationen `migrate_product_parameters.py` räknar om varje premie och rullar tillbaka vid minsta avvikelse. `agent_forsakring` får `SELECT` på tabellen i `agent_roles.py`. 24 tester (`tests/test_product_parameters.py`), även mot isolerad Postgres. **Infört i Lakebase 2026-10-25** efter operatörens OK (AGENTS.md §4.5): backup `backups/20261025T090949Z`, torrkörning och `--apply` – alla 15 097 premier räknades om identiskt, radantalen oförändrade, en andra körning gjorde ingenting – därefter `grant_agent_role.py --apply` (dagens rättigheter plus `SELECT` på `product_parameters`). Verifierat med rollens egen anslutning genom agentens tjänstelager: `get_product_parameters` ger de sex startvärdena, förhandsberäkningen 2 025,00 kr för 45 000 kr med versionen i underlaget; rollen har bara `SELECT` på tabellen
- [ ] **3c-P2: Ändra parametrar** – `schedule_product_parameter_change` (`APPROVAL`), `withdraw_product_parameter_change` (`HUMAN_ONLY`), överlappskontroll, UI-sidan `/parametrar`
- [ ] **3c-G: Gateways** `regelverk` (läsning) och `dokument` (utkast), fiktiv källa `K-SIM-ITP-2027`
- [ ] **3c-B: Beståndsinsikt** – `estimate_parameter_change_impact` med undertryckning; demobeståndet utökas med en äldre kohort
- [ ] **3c-T: Teamen** `compliance` och `aktuarie` – profiler, instruktioner, uppdragsmallar, resultatscheman
- [ ] **3c-V: Röktest och demomanus** – demo och `svc_test`, sedan Lakebase efter backup, roll `agent_aktuarie` och OK
- [ ] **3c-1: Delegering mellan team** – `delegate_to_team` med strukturerat uppdrag, `parent_run_id`, djup- och kostnadstak (§6.1)
- [ ] **3c-2: Flödesmotor** – persisterat tillstånd och godkännandesteg; tabeller för flöden, godkännanden och körjournal i `databasschema.md` (körning mot Lakebase enligt AGENTS.md §4.5)
- [ ] **3c-3: Första flödet** – regelförändrings-/flaggskeppsflödet (§6.2)

**Senare:** MCP-exponering av poddar (§9), anropsloggen i databasen, kostnadsindikatorer per team. *(Lakebase-rollen för PII-poddar är flyttad till före aktivering av `kunddata`, se operatörspunkten under 3b-3.)*

---

## 🔴 Fas 5 – Handläggaragent och ärenden (B-026, B-028)

Fas 3b är klar (3b-1–3b-8). Nästa steg är ärendet som agentens arbetsenhet och mandat.

- [x] **2026-10-24** **F5-0: Designstopp** – beslutsförslag `projekt/01_ärendehantering/ARENDEN_BESLUTSFORSLAG.md` (2026-10-24): tabellen `cases`, ärendeoperationer, resursmandat ur ärendet (`scope_for_case`) och första flödet *nytt löneunderlag* med UI-sidorna `/arenden`. Godkänt 2026-10-24 med valen A–H enligt rekommendationerna och loggat som **B-033**; byggstegen F5-1–F5-6 står i förslagets §7
- [x] **2026-10-24** **F5-1: Tabellen `cases`** – `databasschema.md` §9g, modellen `src/models/case.py` och migrationen `scripts/migrations/migrate_cases.py` (bara `cases`, torrkörning som standard). Databasens villkor provade i SQLite (`tests/test_models_cases.py`), migrationen mot isolerad Postgres (`tests/test_migration_cases.py`). Skapad i Lakebase i F5-5
- [x] **2026-10-24** **F5-2: Ärendeoperationer** – `create_case`, `list_cases`, `update_case_status`, `close_case` (`HUMAN_ONLY`) och `get_case` (`AGENT`) med åtkomstrader och tester; operationsförteckningen genereras om. *Klart: `src/services/operations/cases.py`, stödda och blockerade fall i `tjänstelager.md` §9.3. Tjänstelagret sätter nu `case_id` ur indatans `case_number` (och för `create_case` ur resultatet), så ärendets historik är händelserna med dess nummer; kontext och indata som anger olika ärenden stoppas. `close_case` blockeras medan förslag i ärendet väntar, och `approved` kräver en genomförd ändring i ärendet. 18 tester (`tests/test_services_cases.py`). `get_case` är omappad i körpolicyn tills F5-3*
- [x] **2026-10-24** **F5-3: Harness** – `scope_for_case`, `case_number` i resurskontrollen, uppdragsmall per ärendetyp, `get_case` i podden `kunddata`, status efter körning. *Klart: `src/agents/case_runs.py` (`run_case`, `request_for_case`, `record_run_status`) och `scope_for_case`/`case_and_scope` i `src/agents/scope.py`. Mandatet = ärendets försäkrade med alla försäkringar, ärendets och personens arbetsgivare, 24 månader till och med ärendets månad; stängt ärende eller ärende utan försäkrad ger inget mandat. Resurskontrollen prövar `case_number`/`case_id` mot körningens ärende (i indata och resultat). Uppdragsmallen för `salary_report` innehåller ärendenumret men inga personuppgifter. Efter körningen skriver harness `waiting_approval` eller `in_progress` och `last_run_id` som systemaktör. `agent_forsakring` får `SELECT` på `cases` i `agent_roles.py` (verkställs i Lakebase i F5-5). 9 nya tester, varav ett mot Postgres med den riktiga rollen*
- [x] **2026-10-24** **F5-4: UI** – `/arenden`, registrering, detalj med *Starta agent*, resultat, kostnad och journal. *Klart: `src/web/routes/cases.py`, `src/web/agent.py` och mallarna `cases.html`, `form_case.html`, `case.html`; beskrivning i `handläggar-ui.md` §4. Agenten körs synkront, en åt gången, med simulerad roll i demo/`svc_test` och riktig roll mot Lakebase. Handläggarens egen registrering av löneunderlaget bär ärendenumret. `list_approval_requests` och `get_operation_events` fick urval på ärende; godkännandekön säger *förslag* i stället för *ärende*. Demo- och testdatabasen får nya tabeller vid start. 12 nya UI-tester mot FakeProvider; sidorna verifierade i webbläsaren mot demodatabasen (utan riktig agentkörning)*
- [ ] **F5-5: Lakebase** – migration och rättigheter för `agent_forsakring` på `cases` efter backup och operatörens OK (AGENTS.md §4.5); skarp verifiering. *2026-10-24, efter operatörens OK: backup `backups/20261024T191154Z` (17 164 rader), torrkörning, `migrate_cases.py --apply` (tabellen `cases` med villkor, nycklar och index; övriga radantal oförändrade, bl.a. 501 försäkrade och 15 097 premietransaktioner) och `grant_agent_role.py --apply` (dagens rättigheter plus `SELECT` på `cases`). Verifierat med rollens egen anslutning: läser `cases` och beståndet, nekas UPDATE, DELETE, INSERT och radlås på `cases`; `get_case` genom agentens tjänstelager når tabellen. **Kvar:** skarp verifiering med ett märkt verifieringsärende via UI:t mot Lakebase, som S6 – agentförslaget kan läggas först från 2026-11-01*
- [ ] **F5-6: Röktest av hela flödet** – ärende → agent → förslag → godkännande → stängt, efter 2026-11-01

## 🧩 Månadssimulering – byggluckor och samordning

Tillagt **2026-10-25** på operatörens begäran efter kartläggning av löpande verksamhet.
Gemensamt underlag och gap-ID:n: [processöversikten](01_domän/processer_översikt.md).
Detta fångar behov för fortsatt planering; det ändrar inte beslutad fasordning eller
produktscope. Paketen A–C är förslag att avgränsa vid designstart, inga nya fasnummer.

- [ ] **Paket A: sammanhängande premie- och betalningsflöde (V-01–03)** – samordna befintliga punkter om anställningshistorik och premie ur löneunderlag med faktura, kompletteringsinstruktion, bankhändelse, matchning, delbetalning och underlag till kapital/garanti. Fastställ gemensamma kontrakt och verifieringsfall mellan projekt 1, 4, 5 och 6; undvik dubbla motorer
- [ ] **Paket B: pensions- och månadsavräkning (V-04–06, V-11)** – avgränsa ett bygguppdrag för uttagsdelar, separat premie-/pensions-/betalningsförlopp, historiska garantier, kapitaljournal, månadsrätt/skuld, skatt, bankkvitton, dödsfall och slutavräkning. Följ PR-020:s månadsordning; klargör samordningen mellan projekt 1/6 och kapitalförvaltningen. Kundportalen ska använda samma tjänsteoperationer
- [ ] **Paket C: månadssimulator – design och ansvar** – avgränsa S-01–06 nedan och välj hur befintlig harness/flödesmotor återanvänds. Ett första avgränsat premiescenario kan byggas före full pensionsmånad; märk kvarstående led. Projekt 9 dokumenterar, men äger inte därmed en ny runtime
- [ ] **S-01: simuleringsklocka och kalender** – gemensamt affärsdatum, bankdagar, förfallodatum och periodslut; håll verklig loggtid och aktiva körbudgetar åtskilda från simulerad tid, med oförändrade behörighets- och godkännandekrav
- [ ] **S-02: händelsegenerator/scenario** – versionsbundet scenario med seed, ordning, volymer, beroenden och testhändelser för löner, anställningar, kundval och avvikelser
- [ ] **S-03: simulerade motparter** – arbetsgivare/kund/bank och vid behov rapportmottagare med meddelanden, svar, fördröjning, retur och okänt utfall genom definierade kontrakt
- [ ] **S-04: avstämt startbestånd** – pensionsplaner, historiska garantier, kassa/portfölj, fordringar, skulder och eget kapital. Befintlig mockhistorik och B-035:s äldre kohort är delunderlag, inte ett komplett ekonomiskt startläge
- [ ] **S-05: isolerad körning och återställning** – scenario-/köridentitet, startpunkt, återställning och fortsatt körning efter beslut; återanvänd befintlig backup och körjournal där det passar
- [ ] **S-06: facit och månadens acceptanskontroller** – oberoende väntade utfall, avstämningar, inga dubbla ekonomiska effekter, rättigheter/tidsfrister samt kvalitet och agentkostnad. Konkretisera processöversiktens åtta acceptanskriterier med testbelopp
- [ ] **Ekonomi och aktuariella kontroller (V-10–11)** – bryt ned projekt 6:s målbild till bokförings-/avstämningsmodell, månadsbokslut samt garanti-/reserv-/FTA-/ALM- och finansieringskontroller. Premiehistorik, kundkapital och reserv är olika underlag
- [ ] **Rapportkontrakt för simuleringen (V-12)** – välj första interna månadsrapporten och senare externa rapporter; fastställ mottagare, tillämplighet, period, mått, datakällor, granskning och kvitto. Inget generellt månatligt rapportkrav till kollektivavtalsparterna antas
- [ ] **Ärendetyper, intag och kommunikation (V-08–09)** – konkretisera fortsättningen efter `salary_report`: arbetsgivarfil, regelstyrda avvikelser, pensionsbegäranden och klagomål med tidsfrister, samt verifierat sakunderlag, mottagare, godkända besked och leveranskvitton

## 🟡 Medium prioritet – domänkartläggning

- [x] **2026-10-11** Specificera AI-abstraktionslagret i `02_system/ai_abstraktion.md` – LiteLLM, OpenRouter och egen wrapper utvärderade; egen tunn wrapper beslutad (B-025) och byggd i `src/ai/` (Anthropic Messages API + OpenAI Responses API, roller `fast`/`standard`/`deep` med reserv hos andra leverantören, team-nycklar, anropslogg, 81 tester). Agentekosystemet designat i `02_system/agentekosystem.md` (B-026)
- [ ] **Operatör: lägg in API-nycklar och kör röktestet** – `ANTHROPIC_API_KEY` och `OPENAI_API_KEY` i `.env`, sedan `pip install -e .[dev]` i huvudrepots `.venv` och `python scripts/diagnostics/smoke_test_ai.py` (några ören). Verifierar båda adaptrarna, verktygsloop och korsleverantörsreserv mot riktiga API:er
- [ ] **Kartlägga processer** i [`01_domän/processer_översikt.md`](01_domän/processer_översikt.md) – första verksamhets- och gapöversikt dokumenterad 2026-10-25, med byggluckor, samordning och acceptanskriterier för månadssimulering. Detaljerade processkartor och verifierade nulägesflöden återstår i projekt 9
- [x] **2026-07-12** Skriva ut försäkringsvillkor för ITP1 ålderspension i `01_domän/försäkringsvillkor.md` *(gjordes i Fas 1a)*
- [x] **2026-10-12** **Dokumentera aktuariell SIM-grund** – låst SCB-tabell 2025, unisex, förbättring och marginal, oändlig svans, garantidelar, annuiteter, arvsvinst och bolagsfinansiering i `01_domän/aktuariell_grund.md` och `01_domän/parametrar/PARAMETERREGISTER.md`, med räkneexempel i leveranskontrollen. Produktinriktning B-027; införd som del av PR-ITP1 v1.0 genom B-031, gäller från 2026-11-01. Professionell tariffvalidering för verklig verksamhet är en separat aktivitet.
- [x] **2026-05-15** **Designa regelförändringsflöde** – multi-agent-flöde som triggas när ett regelverk ändras: compliance-agent gör tolkning och konsekvensanalys, utvecklaragent identifierar kodpåverkan, kommunikationsagent förbereder ev. kundkommunikation. Dokumenterat i `02_system/Agentsystem/regelförändringsflöde.md` och utökat till flaggskeppsflödet i `02_system/agentekosystem.md` §6.2 (B-026). Ett av undantagen från B-008 (kräver olika mandat). Implementeras i Fas 3c (3c-3)

## 🟢 Lägre prioritet – när grunden står

- [ ] **Sätta upp md→PDF-pipeline** – välja verktyg (Pandoc eller WeasyPrint), koppla mallar för formella dokument (rapporter, kundbrev, styrelseprotokoll) till den gemensamma designgrunden under **Grafisk identitet och designsystem** ovan
- [ ] **Standardmall för officiella dokument** – logga, sidhuvud/sidfot, signaturplats, sidnumrering, dokument-ID, versionsinfo. Tas i samband med PDF-pipelinen och återanvänder bolagets gemensamma designgrund ovan
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

  **Läget 2026-10-12:** Komponent 1 (FastAPI-backend) och 6 (vyer) finns i handläggar-UI v1 (Fas 4), byggda ovanpå tjänstelagret i stället för direkta tabellvyer. Autentisering: v1 är bara lokalt utan inloggning. Delad backend: människor och agenter använder samma tjänstelager. Chatten (komponent 1–5 med modellanrop) byggs efter harness.

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
- [ ] Hur ska godkännandeflöden fungera (mail till kund ska godkännas innan utskick)? *(ramverk beslutat i B-026: sidoeffektsklasser, `02_system/agentekosystem.md` §5.3. Godkännandekön och flaggan* endast handläggare *finns i tjänstelagret sedan Fas 1f T3 – tabellen `approval_requests`, `02_system/tjänstelager.md` §4 och §6, B-028. Gränssnittet för kön finns i handläggar-UI:t sedan Fas 4 (`/godkannanden`). Kvar: externa handlingar som utskick)*
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
