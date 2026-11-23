# Databasschema – ITP1 Administrationsplattform

> Operativ databas för det simulerade tjänstepensionsbolaget. Tabeller definieras som SQLAlchemy-modeller och deployas till Databricks Lakebase (serverless Postgres, B-018 – ersatte Supabase/B-014). Schemat utvecklas iterativt – denna fil dokumenterar det aktuella tillståndet.
>
> **Konvention:** Tabell- och kolumnnamn på engelska (snake_case). Beskrivningar på svenska. Domänbegrepp i texten använder svenska termer (försäkringstagare, försäkrad, premie) och engelska används bara som tekniska identifierare.

---

## 1. Översikt

| Tabell | Domänbegrepp | Status |
|--------|--------------|--------|
| `employers` | Försäkringstagare (arbetsgivare med ITP-avtal) | 🟢 I drift (seedad) |
| `insured_persons` | Försäkrade (anställda som omfattas av ITP1) | 🟢 I drift (seedad) |
| `policies` | Försäkringar (flera per försäkrad möjliga) | 🟢 I drift i Lakebase enligt Fas 1e-modellen (B-022) |
| `policy_states` | Premieförloppet – premiebetalande eller fribrev per försäkring, som tidsperioder (§6) | 🟢 I drift i Lakebase; importerad historik och tjänsteoperationer. Paket B steg 1 (B-047): villkoret smalnat till `premium_paying` och `paid_up` i Lakebase 2026-11-14 (§12) |
| `policy_benefits` | Försäkringsförmåner – förmåner inom en försäkring | 🟢 I drift i Lakebase; förmånen ålderspension |
| `payout_parts` / `payout_part_states` | Uttagsdelar under en förmån och deras pensionsförlopp (§7b) | 🟢 Paket B steg 1 (B-047, P1-PENSION-001 §4): skapade i Lakebase 2026-11-14 efter backup `backups/20261114T150341Z` och Karls OK, med uttagsdel 1 `not_started` för alla 499 förmåner (§12). `agent_forsakring` och `agent_aktuarie` har SELECT (B-048) |
| `ledger_batches` / `ledger_guarantee_parts` / `ledger_capital_entries` / `ledger_controls` | Den operativa kapital- och garantijournalen: verifikationer, garantidelar, kapitalposter per konto och spår, och kontrollposter (§7c) | 🟢 Paket B steg 2 (B-047, P1-PENSION-001 §6): modeller, övergången från S-04, migration och tester; verifierade mot isolerad Postgres. Införda i Lakebase 2026-11-15 efter backup `backups/20261114T231325Z` och Karls OK, med det ingående läget per 2026-10-31 bokat (§12); agentrollerna har inga rättigheter. Paket B steg 3 (P1-PENSION-001 §7): månadsstängning och rättelse i `ledger_batches` (`supersedes_id`, två nya slag); byggt och verifierat lokalt och mot isolerad Postgres. Migrationen införd i Lakebase 2026-11-19 efter backup `backups/20261119T201517Z` (§12); novembers stängning tidigast 2026-12-01. Paket B steg 4: `ledger_guarantee_parts.plan_id` och `plan_kind = 'plan'` för garantidelar omräknade på en beslutad plan; byggt och verifierat lokalt och mot isolerad Postgres, **inte infört i Lakebase**. Paket B steg 5: slaget `company_capital`, posterna på betalningsskulden och bolagskontot och `ck_ledger_capital_entries_accounts`; byggt och verifierat lokalt och mot isolerad Postgres, mergat till main 2026-11-23, **inte infört i Lakebase** |
| `payout_amounts` / `pension_claims` / `pension_claim_fundings` | Beslutade månadsbelopp, månadsrätter per uttagsdel och månad, och senare bolagsstöd till ej finansierade anspråk (§7e) | 🟡 Paket B steg 5 (B-047, B-053, P1-PENSION-001 §5.5): modeller, operationer, migration och tester; verifierade lokalt och mot isolerad Postgres. Mergade till main 2026-11-23; **inte införda i Lakebase**; migrationen efter steg 4:s och Karls separata OK. Agentrollerna får inga rättigheter |
| `payout_requests` / `payout_plans` / `payout_splits` | Kundens begäran om uttag, planversioner per uttagsdel och delningsbeslut (§7d) | 🟡 Paket B steg 4 (B-047, B-051, P1-PENSION-001 §5): modeller, operationer, migration och tester; verifierade lokalt och mot isolerad Postgres. **Inte införda i Lakebase**; migrationen tidigast efter novembers stängning (2026-12-01) och Karls separata OK. Agentrollerna får inga rättigheter |
| `premium_transactions` | Premietransaktioner (en rad per förmån och månad) | 🟢 I drift i Lakebase med importerad premiehistorik; `corrects_transaction_id` migrerad 2026-10-11 |
| `salary_reports` | Löneunderlag – pensionsmedförande lön per person, arbetsgivare och månad, versionerat | 🟢 Skapad i Lakebase 2026-10-11 (§8b); registrering verifierad i S6 2026-10-12 |
| `bank_events` / `payment_allocations` | Inbetalningar enligt banken och deras fördelning på fakturarader eller avstämningskontot (§8e) | 🟢 Paket A steg 4 (B-046): modeller, operationer och lokala tester. Skapade tomma i Lakebase 2026-11-08 med `migrate_premium_flow.py` (§12) efter backup `backups/20261108T075712Z` och Karls OK; agentrollerna har inga rättigheter |
| `invoices` / `invoice_lines` | Fakturor per arbetsgivare och premieperiod, med debet, kredit och rader per förmån och premiekedja (§8d) | 🟢 Paket A steg 3 (B-046): modeller, operationer och lokala tester. Skapade tomma i Lakebase 2026-11-08 med `migrate_premium_flow.py` (§12) efter backup `backups/20261108T075712Z` och Karls OK; agentrollerna har inga rättigheter |
| `salary_files` | Arbetsgivarens löneunderlagsfil per period: innehåll, kontrollsumma, validering och granskningsbeslut (§8c) | 🟢 Paket A steg 2 (B-046): modell, operationer och lokala tester. Skapad tom i Lakebase 2026-11-08 med `migrate_premium_flow.py` (§12), tillsammans med fakturans och bankens tabeller, efter backup `backups/20261108T075712Z` och Karls OK; agentrollerna har inga rättigheter |
| `premium_month_journals` / `premium_receipts` / `premium_month_closes` | Frysta syntetiska månadsunderlag, mottagning med kapital-/garantispår och avstämd FTA-analys | 🟢 Skapade tomma i Lakebase 2026-11-03 efter backup `backups/20261103T212124Z` och separat OK (P6-MANAD-001); inga nya agenträttigheter. [Fält, nycklar och riktad migration](avstamd_fta_manad.md#tabeller-och-lakebase-gräns) |
| `base_amounts` | Basbelopp per år (parametertabell för beräkningar) | 🟢 I drift (seedad 2023–2026) |
| `operation_events` / `approval_requests` | Tjänstelagrets händelselogg och godkännandekö (§9b–9c) | 🟢 Skapade i Lakebase i Fas 1f T3a; kö/logg används av tjänstelagret och UI:t |
| `cases` | Ärenden – handläggaragentens arbetsenhet och mandat (§9g) | 🟢 Skapad med agentrollens läsrätt i Lakebase 2026-10-24. Ärendetyperna `payout_request` och `payout_review` (paket B steg 4) och `company_capital` (steg 5) är inte införda i Lakebase. Agentflödet verifierat i Lakebase 2026-11-02 (F5-5–6). Ärendetypen `salary_file_deviation` (steg 2), `payment_overdue` och kanalen `system` (steg 3) samt `payment_unmatched` (steg 4): CHECK-villkoren `ck_cases_type`, `ck_cases_channel` och `ck_cases_subject` bytta i Lakebase 2026-11-08 av samma migration som premieflödets tabeller (steg 8, §12); de 8 befintliga ärendena oförändrade |
| `case_work` / `case_messages` / `case_work_days` | Varaktiga ärendeuppdrag, skyddad dialog och daglig budgetbok (§12b) | 🟢 Skapade tomma i Lakebase 2026-10-31 efter backup och operatörens OK; inga direkta agenträttigheter. Schema är avstängt |
| `product_parameters` | Versionerade premieåldrar, premiesatser och brytpunkter, samt kapitalavgift och skattebelastning per år (§9h) | 🟢 Skapad och seedad i Lakebase 2026-10-25; agentrollens läsrätt satt. Förändringsoperationer finns; komplett flödesverifiering återstår i 3c-V. 🟢 Kapitalets nycklar (A5) införda i Lakebase 2026-10-31 efter backup `backups/20261031T172901Z` och operatörens OK |
| `portfolios` / `portfolio_holdings` / `trades` | Fristående paper trading-scenarier, instrument och affärsförslag/kvittenser (§9d–9f) | 🟡 Fas 2c: modeller och lokala tester; ej skapade i Lakebase |
| `flows` / `flow_steps` / `flow_gate_decisions` | Uppdragsarkiv för den avvecklade flödesmotorns uppdrag, steg och grindbeslut (§9i) | Skrivskyddad historik i befintliga databaser. Skapades tomma i Lakebase 2026-10-26 efter backup `backups/20261026T200423Z` och operatörens OK. Agentrollerna fick inga rättigheter. Tabellerna ligger utanför schemat för nya databaser |
| `company_missions` | Fråga bolaget: versionerade uppdrag, deluppdrag, granskningar och kvitton | Lokal SQLite-demo. Skapas när bolagsorkestratörens pilot aktiveras. [Pilotens uppdragskontrakt](bolagsorkestrator_pilot.md#uppdragskontrakt-och-gränser) |
| `valuation_bases` | Antagandebiblioteket: aktuariella grunder och diskonteringskurvor med oföränderligt innehåll (§9j) | 🟡 A4 (B-042): modell, operationer, startgrunder och tester; 🟢 skapad och seedad i Lakebase 2026-10-31 efter backup `backups/20261031T124616Z` och operatörens OK; läsrätt för `agent_aktuarie` satt |
| `valuation_extracts` / `valuation_runs` / `valuation_results` | Värderingsmotorn: sparade datautdrag S-04, värderingskörningar med FTA, villkorad återbäring och underskott, och resultat per segment (§9k) | 🟡 A6 (B-042): modeller, operationer, migration och tester; verifierade mot isolerad Postgres. 🟢 Skapade tomma i Lakebase 2026-10-31 efter backup `backups/20261031T173353Z` och operatörens OK; läsrätt för `agent_aktuarie` på körningar och resultat |

**Kedjan för uppslag:** person → `policies` (personens försäkringar) → `policy_benefits` (förmåner per försäkring) → `premium_transactions` (premier per förmån), med `policy_states` som parallell tidsaxel för premieförloppet och `payout_parts` → `payout_part_states` för pensionsförloppet per uttagsdel (§7b). Uttagsdelen bär journalens garantidelar och kapitalposter (§7c). Alla kopplingar är FK:er så varje fråga "vad hade person X för läge/förmåner/premier vid tidpunkt T" är en join-kedja.

**Planerade tabeller (ej i denna omgång):** Kapitalets kassaflödesjournal och premiekoppling byggs senare; se §9d.

**Lokal demotabell i projekt 11.** `change_requests` skapas vid webbstart även i
befintliga demofiler. Den har egen metadata för SQLite och används av
`services.change_requests.ChangeRequests`. `id` är ett UUID och används även
vid omskickad registrering. `requested_by` är den verifierade operatören och
indexeras för listning. `status` börjar som `new` och `created_at` lagras i UTC.
`draft` är det validerade ärendeunderlaget i JSON. Se
[projektplanen för U1](../projekt/11_utveckling_och_andringshantering/PROJEKTPLAN.md#prova-u1-i-demo).

---

## 2. Designprinciper

- **Surrogatnycklar i UUID-format** som primärnyckel (`id`). UUID undviker krockar vid framtida sammanslagningar och hindrar att kundnummer läcker volyminformation utåt.
- **Naturliga nycklar** (org.nr, personnr) lagras separat med `UNIQUE`-constraint för affärslogik och uppslag, men är inte PK.
- **Tidsstämplar `created_at` / `updated_at`** på alla tabeller (`TIMESTAMPTZ`, default `now()`). Triggers för `updated_at` läggs senare.
- **`status`-fält** som ENUM-text (PostgreSQL `CHECK`-constraint) i stället för booleans – möjliggör fler livscykellägen utan migration.
- **GDPR (B-006):** Tabeller med personuppgifter (`insured_persons`) får begränsad agentbehörighet. Behörighetslistor förs i `02_system/agentkarta.md` / agentens egen MD-fil.
- **Soft delete via status** snarare än fysisk radering – behövs för revisionsspårning och regulatorisk arkivering. Hård radering reserveras för GDPR-radering med separat process.

---

## 3. Tabell: `employers` – Försäkringstagare

**Domän:** En arbetsgivare som har tecknat ITP-avtal med Svenskt Näringsliv–PTK och därigenom omfattas av ITP1 för sina anställda födda 1979 eller senare (samt de som valt in).

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK, default `gen_random_uuid()` | Surrogatnyckel |
| `org_number` | `VARCHAR(10)` | NOT NULL, UNIQUE | Svenskt organisationsnummer, 10 siffror utan bindestreck |
| `name` | `VARCHAR(255)` | NOT NULL | Bolagets registrerade namn |
| `industry_code` | `VARCHAR(10)` | NULL | SNI-kod (svensk näringsgrensindelning), 5 siffror |
| `address_street` | `VARCHAR(255)` | NULL | Postadress, gatudel |
| `address_postal_code` | `VARCHAR(6)` | NULL | Postnummer utan mellanslag |
| `address_city` | `VARCHAR(100)` | NULL | Postort |
| `contact_name` | `VARCHAR(255)` | NULL | Kontaktperson (HR/lön) |
| `contact_email` | `VARCHAR(255)` | NULL | Kontakt-e-post |
| `contact_phone` | `VARCHAR(30)` | NULL | Kontakttelefon, fritt format |
| `collective_agreement` | `VARCHAR(50)` | NOT NULL, default `'ITP'` | Kollektivavtal. Endast `'ITP'` stödjs initialt (B-002) |
| `affiliation_date` | `DATE` | NOT NULL | Datum då arbetsgivaren anslöt till ITP |
| `status` | `VARCHAR(20)` | NOT NULL, CHECK in (`'active'`, `'terminated'`, `'paused'`), default `'active'` | Livscykelstatus |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Skapandetid i databasen |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Senast uppdaterad |

**Index:** `org_number` (implicit via UNIQUE), `status` (för filtrering på aktiva).

**Relationer:**
- `employers.id` ← `insured_persons.employer_id` (en arbetsgivare har många försäkrade)
- Koppling till försäkringsavtal går via den försäkrade (`employers` ← `insured_persons` ← `policies`) – `policies` har ingen egen arbetsgivarkolumn

**Ändras via tjänstelagret (Fas 4):** `register_employer` skapar en arbetsgivare med `collective_agreement = 'ITP'` och status `active`; `list_employers` listar utan kontaktpersoner. Status, organisationsnummer och anslutningsdag ändras inte via tjänstelagret ännu.

---

## 4. Tabell: `insured_persons` – Försäkrade

**Domän:** En anställd hos en försäkringstagare som omfattas av ITP1 ålderspension. Premie betalas från månaden den anställde fyller 25 (ITP-avtalets §4 mom 1). Tjänstepension beräknas på utbetald lön upp till 7,5 inkomstbasbelopp (4,5 %) och därutöver (30 %).

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK, default `gen_random_uuid()` | Surrogatnyckel |
| `personal_id_number` | `VARCHAR(12)` | NOT NULL, UNIQUE | Personnummer YYYYMMDDXXXX, 12 siffror utan bindestreck. **Personuppgift – behörighetsskyddad (B-006)** |
| `first_name` | `VARCHAR(100)` | NOT NULL | Förnamn |
| `last_name` | `VARCHAR(100)` | NOT NULL | Efternamn |
| `email` | `VARCHAR(255)` | NULL | Privat e-post (för kundkommunikation) |
| `phone` | `VARCHAR(30)` | NULL | Privat telefon |
| `employer_id` | `UUID` | NOT NULL, FK → `employers(id)` ON DELETE RESTRICT | Nuvarande arbetsgivare |
| `employment_start_date` | `DATE` | NOT NULL | Anställningens startdatum hos `employer_id` |
| `employment_end_date` | `DATE` | NULL | Avslutsdatum, NULL = pågående anställning |
| `monthly_salary_sek` | `NUMERIC(10,2)` | NULL | Aktuell (avtalad) månadslön i SEK, stamdata. NULL om okänd. Inte pensionsmedförande lön (se `salary_reports`, §8b). Ändras med `update_current_salary` |
| `employment_rate` | `NUMERIC(5,2)` | NULL, CHECK between 0 och 100 | Tjänstgöringsgrad i procent (heltid = 100) |
| `itp1_start_date` | `DATE` | NULL | Datum då ITP1-täckning startade. Typiskt månaden efter 25-årsdagen eller anställningsstart |
| `status` | `VARCHAR(20)` | NOT NULL, CHECK in (`'active'`, `'terminated'`, `'retired'`, `'deceased'`), default `'active'` | Livscykelstatus i ITP1-systemet |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Skapandetid i databasen |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Senast uppdaterad |

**Index:**
- `personal_id_number` (UNIQUE, implicit)
- `employer_id` (FK-index för joins)
- `(employer_id, status)` sammansatt index för listning av aktiva försäkrade per arbetsgivare

**Relationer:**
- `insured_persons.employer_id` → `employers.id` (en försäkrad → en arbetsgivare, en arbetsgivare → många försäkrade)
- `insured_persons.id` ← `policies.insured_person_id` (1:N – en person kan ha flera försäkringar, se §5/B-022)

**Ändras via tjänstelagret (Fas 4):** `enroll_insured_person` skapar personen med försäkring, förmån och läget `premium_paying` (§5–7) i en transaktion; `update_current_salary` ändrar `monthly_salary_sek`/`employment_rate`; `update_contact_details` ändrar `email`/`phone`; `set_policy_paid_up` (T3) sätter `employment_end_date` och status `terminated`. Modellen har en arbetsgivare och en anställning per person – återanställning och arbetsgivarbyte kräver anställningshistorik och blockeras (`tjänstelager.md` §9.2).

---

## 5. Tabell: `policies` – Försäkringar

**Domän:** En försäkring tecknad för en försäkrad. En person kan ha **flera** försäkringar (B-022, ersätter B-021:s ett-avtal-regel) – t.ex. en aktiv och ett äldre fribrev. Försäkringens innehåll ligger i `policy_benefits`; dess läge över tid i `policy_states`. **Ingen statuskolumn här** – nuläget är alltid den öppna raden i `policy_states` (en sanning, ingen drift).

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK, default `gen_random_uuid()` | Surrogatnyckel |
| `policy_number` | `VARCHAR(20)` | NOT NULL, UNIQUE | Läsbart försäkringsnummer, format `AL-NNNNNN`. Affärsnyckel mot kund |
| `insured_person_id` | `UUID` | NOT NULL, FK → `insured_persons(id)` ON DELETE RESTRICT, index | Den försäkrade |
| `product_code` | `VARCHAR(20)` | NOT NULL, default `'ITP1'` | Produkt. Endast `'ITP1'` i nuläget (B-002) |
| `signed_date` | `DATE` | NOT NULL | Datum försäkringen tecknades |
| `start_date` | `DATE` | NOT NULL, CHECK ≥ `signed_date` | Ikraftträdande (villkor §2.2) |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

**Relationer:** `insured_persons` 1→N `policies` 1→N `policy_states` / `policy_benefits`.

---

## 6. Tabell: `policy_states` – Premieförloppet

**Domän:** Försäkringens **premieförlopp** som **tidsperioder**: varje rad säger "försäkringen var premiebetalande (eller fribrev) från `valid_from` till `valid_to`". Öppen rad (`valid_to IS NULL`) = nuvarande läge. Frågan "vilket premieläge hade försäkringen 2024-03-15?" = raden där datumet ligger i intervallet.

Sedan paket B steg 1 (B-047 punkt 2, P1-PENSION-001 §4) har en försäkring tre skilda förlopp: **premieförloppet** här, **pensionsförloppet** per uttagsdel i `payout_part_states` (§7b) och betalningsförloppet (månadsrätter, byggs i steg 5). Uttagslägena `in_payout` och `payout_paused` och läget `terminated` från B-022 finns inte längre i tabellen; övergången flyttar uttagslägena till uttagsdel 1 (§12).

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK, default `gen_random_uuid()` | Surrogatnyckel |
| `policy_id` | `UUID` | NOT NULL, FK → `policies(id)` ON DELETE RESTRICT | Försäkringen |
| `state` | `VARCHAR(20)` | NOT NULL, CHECK in (`'premium_paying'`, `'paid_up'`) | Premieläge, speglar villkoren (se nedan) |
| `valid_from` | `DATE` | NOT NULL | Lägets första giltighetsdag |
| `valid_to` | `DATE` | NULL, CHECK (NULL eller ≥ `valid_from`) | Sista giltighetsdag. NULL = pågående |
| `note` | `VARCHAR(255)` | NULL | Orsak/kommentar, t.ex. "Anställning upphörde" |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

**Lägen** (hänvisningar till `01_domän/försäkringsvillkor.md` v2.0):

- `premium_paying` – premiebetalande (villkor §3)
- `paid_up` – fribrev (villkor §7); kan gälla samtidigt som en uttagsdel betalas ut eller är pausad (fall 38)

Att utbetalningen startat, pausats eller avslutats står per uttagsdel i `payout_part_states` (§7b). Avslut i rättighetshänseende sker bara genom slutavräkning eller dödsfall (PB10) och är ett läge på uttagsdelen, inte på försäkringen. Kraven finns i [UTTAG_GEMENSAMT](../01_domän/produktregler/UTTAG_GEMENSAMT.md) och [designstoppet för paket B](../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md).

**Integritet:** Partiellt unikt index på `policy_id` där `valid_to IS NULL` – max ett öppet läge per försäkring. Att perioder inte överlappar valideras på applikationsnivå (Postgres EXCLUDE-constraint kräver btree_gist-extension – utvärderas senare). Index på `(policy_id, valid_from)`.

**Ändras via tjänstelagret (Fas 1f T3, paket B steg 1):** `set_policy_paid_up` stänger den öppna `premium_paying`-perioden och öppnar `paid_up` dagen efter anställningens slut, och validerar hela tidslinjen (en öppen rad, inga överlapp). Sedan steg 1 gäller det även när en uttagsdel betalas ut eller är pausad (fall 38); uttagsdelarnas pensionsförlopp ändras inte. Framtida giltighetsdagar skapas inte: läsningen tolkar den öppna raden som dagens läge. Anslutningen (`enroll_insured_person`) öppnar `premium_paying` och ger förmånen uttagsdel 1 i läget `not_started`.

---

## 7. Tabell: `policy_benefits` – Försäkringsförmåner

**Domän:** En förmån inom en försäkring. Endast premiebestämd ITP1 ålderspension (`retirement_dc`) ingår i beslutat produktscope. TGL och familjeskydd är tekniskt förberedda som typer enligt B-022, men får användas som produkter först om scope utökas genom ett nytt uttryckligt beslut och villkoren uppdateras. Förberedelsen innebär att dessa typer då kan läggas till som ytterligare rader med egna premier och parametrar, utan schemaändring.

| Kolumn | Datatyp | Constraints | Beskrivning |
|---

## 7b. Tabeller: `payout_parts` och `payout_part_states` – Uttagsdelar och pensionsförloppet

> **Status:** Paket B steg 1 (B-047 punkt 2, [P1-PENSION-001 §4](../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md), PB2). Modeller i `src/models/payout_part.py`, läsningar i `src/services/payout_parts.py`, övergången i `src/services/payout_transition.py` och migrationen `scripts/migrations/migrate_payout_parts.py` (§12). Verifierade lokalt och mot isolerad Postgres. **Skapade i Lakebase 2026-11-14** efter backup `backups/20261114T150341Z` och Karls OK: 499 delar nr 1, alla `not_started` (§12). `agent_forsakring` och `agent_aktuarie` har SELECT på båda tabellerna (**B-048**), satt med `grant_agent_role.py` efter migrationen; `agent_compliance` har ingen rätt och inga roller skriver.

**Domän:** En **uttagsdel** är den enhet under en förmån som får egen start, form, plan, garantidelar och månadsrätter (PR-ITP1-024). Varje ålderspensionsförmån har minst del 1. En delning – byggs i steg 4 – ger högst tre delar per ursprunglig förmån, med vald andel och länk till delen den delades från. Garantidelar, kapitalposter och månadsrätter knyts till exakt en del i steg 2 och 5.

### `payout_parts`

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Surrogatnyckel |
| `benefit_id` | `UUID` | NOT NULL, FK → `policy_benefits(id)` ON DELETE RESTRICT, index | Förmånen delen tillhör |
| `part_number` | `INTEGER` | NOT NULL, CHECK 1–3, UNIQUE med `benefit_id` (`uq_payout_parts_benefit_number`) | Delens nummer; del 1 är den ursprungliga |
| `share_of_origin` | `NUMERIC(11,10)` | NOT NULL, CHECK > 0 och ≤ 1, default 1 | Delens andel av den ursprungliga rätten, fastställd vid delningen; marknadsutveckling ändrar den inte |
| `split_from_part_id` | `UUID` | NULL, FK → `payout_parts(id)` ON DELETE RESTRICT, index | Delen som delades |
| `split_date` | `DATE` | NULL | Delningens dag |
| `split_share` | `NUMERIC(11,10)` | NULL, CHECK 0,1–0,9 | Vald andel av den delade delens kapital (minst 10 %, och minst 10 % kvar) |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

**Integritet:** CHECK `ck_payout_parts_split` – del 1 har inga delningsfält; del 2 och 3 har alla tre (länk, dag och andel).

### `payout_part_states`

Delens **pensionsförlopp** som tidsperioder, på samma sätt som `policy_states` bär premieförloppet.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Surrogatnyckel |
| `payout_part_id` | `UUID` | NOT NULL, FK → `payout_parts(id)` ON DELETE RESTRICT | Uttagsdelen |
| `state` | `VARCHAR(20)` | NOT NULL, CHECK in (`'not_started'`, `'in_payout'`, `'paused'`, `'ended'`) | Pensionsläget |
| `end_reason` | `VARCHAR(20)` | CHECK: `final_settlement` eller `death` exakt när `state = 'ended'`, annars NULL | Varför delen är avslutad (PB10) |
| `valid_from` | `DATE` | NOT NULL | Lägets första giltighetsdag |
| `valid_to` | `DATE` | NULL, CHECK (NULL eller ≥ `valid_from`) | Sista giltighetsdag. NULL = pågående |
| `note` | `VARCHAR(255)` | NULL | Orsak/kommentar |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

**Lägen:** `not_started` (delen tar emot premie), `in_payout` (utbetalning pågår), `paused` (utbetalningen är pausad) och `ended` (slutligt, alltid öppet, med orsak). **En framtida plan är inget läge** – den blir en planversion i steg 4.

**Integritet:** Partiellt unikt index `uq_payout_part_states_one_open` på `payout_part_id` där `valid_to IS NULL` – max ett öppet läge per del. CHECK `ck_payout_part_states_ended_open`: `ended` har ingen slutdag. Index på `(payout_part_id, valid_from)`. Överlapp och glapp valideras på applikationsnivå, som för `policy_states`.

**Skrivs av:** anslutningen och premiehistorikens generator (del 1 i `not_started` från förmånens start), övergången (§12) och demodatan. Ingen tjänsteoperation startar, pausar eller avslutar en del i steg 1 – det byggs i steg 4 och 6, och en ny skrivande operation blir `HUMAN_ONLY`.

**Läses av:** `get_insured_overview` och handläggarsidan (delarnas läge per försäkring), `list_insured_persons` (filtret `payout_state`), `get_portfolio_snapshot` (lägena `in_payout`, `payout_paused` och `terminated` räknas ur delarna), S-04-utdraget (en försäkring med en startad eller avslutad del värderas inte, som tidigare) och premieunderlaget (`create_premium_from_salary_report` väljer mottagare bland delar som inte startat under månaden). Med en databasroll som saknar rätten (i dag `agent_compliance`) läses delarna inte: läsningen redovisar pensionsförloppet som ej läst (`services/payout_parts.py`, `payout_readable`).

--------|---------|-------------|-------------|
| `id` | `UUID` | PK, default `gen_random_uuid()` | Surrogatnyckel |
| `policy_id` | `UUID` | NOT NULL, FK → `policies(id)` ON DELETE RESTRICT | Försäkringen |
| `benefit_type` | `VARCHAR(30)` | NOT NULL, CHECK in (`'retirement_dc'`, `'tgl'`, `'family_protection'`) | Tekniskt tillåtna typer; endast `retirement_dc` ingår i beslutat produktscope |
| `start_date` | `DATE` | NOT NULL | Förmånens ikraftträdande |
| `end_date` | `DATE` | NULL | Förmånens upphörande, NULL = löpande |
| `parameters` | `JSONB` | NULL | Förmånsspecifika parametrar; stöd för andra förmånstyper är en teknisk framtidsförberedelse |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

**Integritet:** Unikt index på `(policy_id, benefit_type)` där `end_date IS NULL` – max en pågående förmån av varje typ per försäkring. Historiska (avslutade) förmåner av samma typ tillåts.

**Relationer:** `policy_benefits.id` ← `premium_transactions.benefit_id` (förmånens premier) och ← `payout_parts.benefit_id` (förmånens uttagsdelar, §7b).

---

## 7c. Tabeller: `ledger_batches`, `ledger_guarantee_parts`, `ledger_capital_entries` och `ledger_controls` – Kapital- och garantijournalen

> **Status:** Paket B steg 2 (B-047 punkt 4, [P1-PENSION-001 §6](../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md), PB4).
> - **Var koden finns:** modeller i `src/models/capital_ledger.py`; övergången och läsningarna i `src/services/capital_ledger.py`; A6-källan `ledger` i `src/services/ledger_extract.py`; månadens premier ur paket A i `src/services/ledger_premiums.py`; migrationen i `scripts/migrations/migrate_capital_ledger.py` (§12).
> - **Verifierat:** lokalt och mot isolerad Postgres. Fall 36 och 37 är också verifierade på en återställd kopia av Lakebase-backupen `backups/20261114T150341Z`.
> - **Infört i Lakebase 2026-11-15** efter backup `backups/20261114T231325Z`: migrationen och övergången med var sitt OK från Karl. Det ingående läget per 2026-10-31 är bokat (492 försäkringar, 15 097 garantidelar och kapitalspår). Agentrollerna har inga rättigheter på tabellerna (§12).
> - **Paket B steg 3 (2026-11-19, [P1-PENSION-001 §7](../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md#7-månadsstängningen-pb5)):** månadsstängningen för sparandet i `src/services/month_close.py`, med verifikationsslagen `month_close` och `month_correction` och kolumnen `ledger_batches.supersedes_id`. Migrationen `scripts/migrations/migrate_month_close.py` (§12). Verifierat lokalt och mot isolerad Postgres. **Migrationen införd i Lakebase 2026-11-19** efter backup `backups/20261119T201517Z`; ingen månad är stängd än (B-050).
> - **Paket B steg 4 (2026-11-21, [P1-PENSION-001 §5](../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md#5-begäran-plan-och-belopp-pb3-pb6), Karls val V1–V11):** ändringsmånadens stängning genomför beslutade planer och delningar i steg 1 (§7d). Garantidelarna får `plan_kind = 'plan'` och `plan_id`; delningen bokar kapitalposter med orsaken `split`. Migrationen `scripts/migrations/migrate_payout_plans.py` (§12). Verifierat lokalt och mot isolerad Postgres; **inte infört i Lakebase**.

**Domän:**
- Journalen är **bolagets enda källa** för pensionskapitalet C och garantin G efter övergången från S-04.
- Varje garantidel och kapitalpost hör till exakt en uttagsdel (§7b).
- Posterna är oföränderliga. En rättelse är en ny länkad post, aldrig en ändring.
- Ett **kapitalspår** är paret (uttagsdel, ursprungets garantidel). Summan av en dels spår är delens C.
- Steg 2 bokar det **ingående läget** per 2026-10-31. Steg 3 bokar **månadsstängningen** för sparandet (PR-ITP1-020 steg 1–4 och 8): avkastning, kapitalavgift och skattebelastning per spår samt månadens premier ur paket A med garantidelar. Månaderna stängs i ordning, en stängning per månad.
- Steg 4 genomför i ändringsmånadens stängning, steg 1, beslutade **planer och delningar** (§7d), på värderingen vid föregående månadsslut. En delning flyttar C i ören med största bråkrest och varje G_j proportionellt till den nya delen. En ändrad plan räknar om varje G_j värdebevarande på sin historiska grund: `V_j = G_j × A_gj(gammal plan)` och `G_j_ny = V_j / A_gj(ny plan)`.
- En stängd månad ändras aldrig. En **rättelse** är en ny verifikation med nettodifferensen per spår och orsak som motposter, länkad till versionen den ersätter. Bara den senast stängda månaden kan rättas.

### `ledger_batches`

En verifikation per bokning.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Stabilt id ur innehållet (uuid5), så att granskning och bokning ger samma rad |
| `kind` | `VARCHAR(20)` | NOT NULL, CHECK in (`'opening_s04'`, `'month_close'`, `'month_correction'`, `'company_capital'`) | Verifikationens slag: det ingående läget, en månadsstängning eller en rättelse av en stängd månad (steg 3), eller ägarens insättning på bolagskontot (steg 5, §7e) |
| `period_end` | `DATE` | NOT NULL | Dagen saldona gäller, ett månadsslut |
| `source` | `VARCHAR(30)` | NOT NULL, CHECK in (`'reconstructed_s04'`, `'ledger'`) | Märkningen, samma värden som `valuation_extracts.source` |
| `extract_id` | `UUID` | NULL, FK → `valuation_extracts(id)` ON DELETE RESTRICT | Det sparade S-04-utdraget som det ingående läget bygger på |
| `extract_checksum` | `VARCHAR(64)` | NULL | Utdragets SHA-256 |
| `supersedes_id` | `UUID` | NULL, FK → `ledger_batches(id)` ON DELETE RESTRICT | Versionen en rättelse ersätter: stängningen eller den föregående rättelsen (steg 3) |
| `content` | `JSONB` | NOT NULL | Sammanställningen som granskades. Det ingående läget: metod, utdragets och uppspelningens kontrollsummor, totaler, kontroller och ej överförda försäkringar. En stängning eller rättelse: version, föregående läge, AVK med kontrollsumma, parameterversioner, premierna ur paket A, månadens summor, radernas kontrollsumma och kontroller |
| `checksum` | `VARCHAR(64)` | NOT NULL, UNIQUE, CHECK längd 64 | SHA-256 av `content`, samma som granskningssumman `open_capital_ledger` respektive `close_policy_month` binder |
| `created_by` / `created_at` / `updated_at` | | NOT NULL | |

**Integritet:**
- CHECK `ck_ledger_batches_opening_extract`: det ingående läget har ett utdrag med kontrollsumma.
- Partiellt unikt index `uq_ledger_batches_one_opening` på `kind` där `kind = 'opening_s04'`: övergången görs en gång.
- CHECK `ck_ledger_batches_supersedes`: en rättelse, och bara en rättelse, pekar på versionen den ersätter.
- Partiellt unikt index `uq_ledger_batches_one_close` på `period_end` där `kind = 'month_close'`: en stängning per månad.
- Partiellt unikt index `uq_ledger_batches_supersedes` på `supersedes_id`: varje version ersätts högst en gång, så att versionerna bildar en rak kedja.

### `ledger_guarantee_parts`

En garantidel G_j per ursprung och uttagsdel.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Stabilt id ur ursprunget |
| `batch_id` | `UUID` | NOT NULL, FK → `ledger_batches(id)`, index | Verifikationen som bokade delen |
| `payout_part_id` | `UUID` | NOT NULL, FK → `payout_parts(id)`, index | Uttagsdelen; i det ingående läget alltid del 1, i stängningen den del premien räknades för |
| `origin_kind` | `VARCHAR(20)` | NOT NULL, CHECK in (`'s04_premium'`, `'payment_allocation'`) | Ursprunget: en premierad i S-04 eller en allokering i paket A |
| `premium_transaction_id` | `UUID` | NULL, FK → `premium_transactions(id)` | Premieraden: ursprunget för S-04, den fakturerade raden för en allokering |
| `payment_allocation_id` | `UUID` | NULL, FK → `payment_allocations(id)` | Allokeringen i paket A |
| `premium_sek` | `NUMERIC(14,2)` | NOT NULL, CHECK > 0 | P_j, mottagen nettopremie (PR-ITP1-008) |
| `period_month` / `received_month` / `value_date` | `DATE` | NOT NULL | Premieperiod, mottagningsmånad och värdedag (månadsslutet, PR-ITP1-020 steg 4) |
| `plan_kind` / `plan_start` | | NOT NULL, CHECK in (`'reference_lifelong'`, `'plan'`) | Planen som A_g räknas på: referensplanen (aktuariell_grund.md §3) eller en beslutad uttagsplan (steg 4). `plan_start` är planens första rätt |
| `plan_id` | `UUID` | NULL, FK → `payout_plans(id)` ON DELETE RESTRICT, index | Planversionen när `plan_kind = 'plan'` (steg 4, §7d) |
| `basis_code` / `basis_checksum` | | NOT NULL, CHECK längd 64 | Grunden i `valuation_bases` med kontrollsumma |
| `factor` | `NUMERIC(24,10)` | NOT NULL, CHECK > 0 | A_g vid värdedagen |
| `guarantee_sek_per_month` | `NUMERIC(24,10)` | NOT NULL, CHECK ≥ 0 | G_j i kr/mån; avrundas först i rapporteringen |
| `version` / `reason` / `supersedes_id` | | NOT NULL; CHECK `ck_ledger_guarantee_parts_version` | Version 1 har orsaken `premium`. Delning (`split`) och omräkning (`recalculation`) i steg 4 ger nya versioner med värdedag den första i ändringsmånaden, som ersätter den gällande versionen |
| `source` / `created_by` / tidsstämplar | | NOT NULL | `reconstructed_s04` eller `ledger` |

**Integritet:**
- CHECK `ck_ledger_guarantee_parts_origin`: en S-04-del har en premierad och ingen allokering; en allokeringsdel har en allokering.
- Partiellt unikt index `uq_ledger_guarantee_parts_premium`: högst en version 1 per S-04-premierad.
- Partiellt unikt index `uq_ledger_guarantee_parts_allocation`: högst en version 1 per allokering.
- CHECK `ck_ledger_guarantee_parts_plan_id`: `plan_id` finns precis när `plan_kind = 'plan'` (steg 4).
- Samma premie får inte ge både ett S-04-ursprung och ett ursprung ur paket A (§6.2 p. 5). Det prövas av ledger-utdragets kontroll *en källa per premie*.

### `ledger_capital_entries`

Kapitalposter per konto, uttagsdel och kapitalspår.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | |
| `batch_id` | `UUID` | NOT NULL, FK → `ledger_batches(id)`, index | |
| `account` | `VARCHAR(30)` | NOT NULL, CHECK in (`'customer_capital'`, `'payment_liability'`, `'tax_liability'`, `'inheritance_pool'`, `'company'`, `'suspense'`) | Kontot. Kapital, skuld och pool blandas aldrig i samma saldo. Steg 2 och 3 använder bara kundkapitalet |
| `payout_part_id` | `UUID` | NULL, FK → `payout_parts(id)` | Uttagsdelen |
| `origin_id` | `UUID` | NULL, FK → `ledger_guarantee_parts(id)`, index | Kapitalspårets ursprung |
| `month` | `DATE` | NOT NULL, CHECK första dagen i månaden | Månaden posten hör till |
| `reason` | `VARCHAR(20)` | NOT NULL, CHECK in (`'opening'`, `'premium'`, `'return'`, `'fee'`, `'tax'`, `'pension_debit'`, `'company_support'`, `'pool_in'`, `'pool_out'`, `'split'`, `'company_capital'`) | `opening` är det ingående saldot från S-04. Stängningen använder `return`, `fee`, `tax` och `premium`; avgift och skatt är negativa belopp. Steg 5: `pension_debit` (negativ på kundkapitalet, positiv på skulden), `company_support` (från bolagskontot till skulden) och `company_capital` (insättningen) |
| `amount_sek` / `balance_before_sek` / `balance_after_sek` | `NUMERIC(14,2)` | NOT NULL | Belopp i ören och spårets saldo före och efter |
| `source` / `created_by` / tidsstämplar | | NOT NULL | |

**Integritet:**
- CHECK `ck_ledger_capital_entries_track`: kundkapital har uttagsdel och spår.
- CHECK `ck_ledger_capital_entries_balance`: saldot efter är saldot före plus beloppet. I testdatabasen (SQLite, `ddl_if`) prövas samma regel på halva ören, eftersom SQLite räknar `NUMERIC` som flyttal. Postgres-DDL:en är oförändrad.
- CHECK `ck_ledger_capital_entries_non_negative`: inget negativt kundkapital (§11).
- CHECK `ck_ledger_capital_entries_opening`: det ingående saldot utgår från 0.
- CHECK `ck_ledger_capital_entries_accounts` (steg 5): betalningsskulden och bolagskontot blir aldrig negativa (§7e).
- Unikt `uq_ledger_capital_entries_posting` på (verifikation, konto, del, spår, orsak).
- Index `ix_ledger_capital_entries_track` på (del, spår, månad).

### `ledger_controls`

Kontrollposter för avstämningens led, utan ekonomisk effekt. Varje post har led, väntat och faktiskt värde, skillnad, källor (`JSONB`), utfall och förklaring. Unikt `uq_ledger_controls_step` på (verifikation, led).

Det ingående läget har nio led:
- utdragets kontrollsumma;
- ursprungsspårens uppspelning;
- kapital per försäkring och totalt;
- garanti per försäkring och totalt;
- antal garantidelar;
- antal uttagsdelar;
- ej överförda försäkringar.

En månadsstängning eller rättelse har elva led (steg 3):
- föregående läge;
- avkastning för månaden;
- avgift och skattebelastning;
- kapital per spår och totalt;
- garanti totalt;
- premier ur paket A;
- avstämningskontot;
- startade delar;
- levandestatus;
- standardstart väntar på steg 4.

Efter steg 4:s migration heter det elfte ledet *standardstart*, och ett tolfte led, *rätt enligt plan*, tillkommer. Före migrationen är kontrollposterna och hela sammanställningen identiska med steg 3. *Standardstart* räknar delar med plan,
standardstarter i månaden och nya ärenden; en standardstart eller en rätt enligt plan blockerar till steg 5. *Efter steg 5:s migration bokas de med månadsrätt (§7e).*

**Skrivs av:** `open_capital_ledger` och `close_policy_month` (båda `HUMAN_ONLY`, bara en människa).
- `close_policy_month` bokar månadsstängningen eller rättelsen med granskningssumman ur `prepare_month_close`, i en transaktion med ett transaktionsbundet lås. Samma innehåll igen ger ingen ny effekt; ändrat underlag ger konflikt (tjänstelager §9.16).
- Operationen bokar det ingående läget från S-04 per 2026-10-31 i en transaktion med ett transaktionsbundet lås.
- Den bokar en garantidel och en IB-post per premierad i S-04, märkta `reconstructed_s04` och knutna till uttagsdel 1, plus kontrollposterna och det sparade utdraget.
- Minsta avvikelse stoppar: C per försäkring i ören, G i tio decimaler.
- Samma granskade innehåll igen ger ingen ny effekt. Annat innehåll ger konflikt.
- En försäkring med startad eller avslutad uttagsdel förs inte över; den redovisas som ej överförd.
- Historiska `premium_transactions` ändras inte.

**Läses av:**
- Värderingsmotorn med källan `ledger` (§9k), för det ingående lägets dag och varje stängd månads slut.
- P6-MANAD-001, som IB när det ingående läget finns. Scenariot skriver aldrig tillbaka (§6.3).
- `preview_ledger_premiums`, som visar månadens premier ur paket A:s allokeringar på fakturarader utan att boka dem. Bokningen sker i månadsstängningen (steg 3).
- `prepare_month_close` och `get_month_close` (`HUMAN_ONLY`), som granskar respektive visar en månad.

## 7d. Tabeller: `payout_requests`, `payout_plans` och `payout_splits` – Begäran, uttagsplan och delning

> **Status:** Paket B steg 4 (B-047 punkt 3, [P1-PENSION-001 §5](../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md#5-begäran-plan-och-belopp-pb3-pb6), Karls val V1–V11 2026-11-21, **B-051**).
> - **Var koden finns:** modeller i `src/models/payout_plan.py`; tjänstelogiken i `src/services/payout_plans.py`; operationerna i `src/services/operations/payout_plans.py`; kalender och belopp i `src/skills/calculation/payout_plan.py`; genomförandet i `src/services/month_close.py`; migrationen i `scripts/migrations/migrate_payout_plans.py` (§12).
> - **Verifierat** lokalt (fall 1–12) och mot isolerad Postgres. **Inte infört i Lakebase.**

**Domän:**
- Raderna är oföränderliga. Ett beslut **skriver bara beslutet**; ändringsmånadens stängning genomför det i steg 1 (V2).
- Ett beslut kräver att föregående månadsslut är täckt, av det ingående läget eller en stängd månad, och att ändringsmånaden är öppen.
- En del med rätt under månaden enligt plan blockerar stängningen tills månadsrätten byggs i steg 5 (V3). *Efter steg 5:s migration bokas rätten som anspråk (§7e); standardplanen skrivs då med `origin = 'standard_start'`.*
- Utan tabellerna beter sig stängningen som i steg 3.

### `payout_requests`

En begäran om start, uppskov, paus, förlängning eller delning, prövad mot fristen (UTTAG_GEMENSAMT).

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Stabilt id ur innehållet: samma begäran igen ger samma rad |
| `insured_person_id` / `payout_part_id` | `UUID` | NULL, FK, index | Personen och uttagsdelen; saknas vid okänd identitet |
| `kind` | `VARCHAR(10)` | NOT NULL, CHECK in (`'start'`, `'pause'`, `'extend'`, `'split'`) | `start` gäller också uppskov och ändrad framtida start |
| `change_month` | `DATE` | NOT NULL | Första månad begäran ändrar |
| `content` | `JSONB` | NOT NULL | Kundens val: startmånad, form, N, paus, delningsandel, premiemottagare |
| `received_date` / `channel` / `requester` / `authority_verified` | | NOT NULL; CHECK på kanal och aktör | Mottagningsdag, kanal (samma värden som `cases.channel`), `insured` eller `representative`, verifierad behörighet |
| `deadline` | `DATE` | NOT NULL | Sista kalenderdagen i månaden före ändringsmånaden |
| `outcome` | `VARCHAR(20)` | NOT NULL, CHECK in (`'in_time'`, `'late'`, `'incomplete'`, `'stopped'`, `'blocked'`) | `blocked`: utanför första versionen, t.ex. uttag före 66 (PB1) |
| `proposed_month` | `DATE` | NULL; CHECK `ck_payout_requests_proposal` | Nästa möjliga månad, precis när begäran är sen |
| `missing` | `JSONB` | NOT NULL | Uppgifter som saknas eller hindret |
| `confirms_request_id` | `UUID` | NULL, FK → `payout_requests(id)` | Kundens bekräftelse av ett förslag pekar på den sena begäran |
| `case_id` | `UUID` | NULL, FK → `cases(id)` | Ärendet `payout_request` |
| `checksum` / `registered_by` / tidsstämplar | | NOT NULL | |

### `payout_plans`

En planversion per uttagsdel. En ny version ersätter den förra uttryckligen.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | |
| `payout_part_id` / `version` / `supersedes_id` | | NOT NULL, UNIQUE (del, version); unikt index på `supersedes_id` | Version 1 har ingen föregångare; versionerna bildar en rak kedja |
| `origin` / `request_id` | | NOT NULL, CHECK in (`'request'`, `'standard_start'`) | En begäran har `request_id`. `standard_start` skrivs av 66-månadens stängning efter steg 5:s migration (§7e), med den som stänger som beslutsfattare |
| `change` | `VARCHAR(10)` | NOT NULL, CHECK in (`'start'`, `'pause'`, `'extend'`) | Styr beloppsgolvet (PR-ITP1-009) |
| `effective_month` / `valuation_date` | `DATE` | NOT NULL, index på månaden | Ändringsmånaden och föregående månadsslut som värderingen görs på |
| `form` / `first_right` / `payments` / `pauses` / `end_month` | | NOT NULL utom N och slutmånad; CHECK `ck_payout_plans_payments` | Livsvarig utan N och slutmånad, eller tidsbegränsad med N ≥ 60 och härledd slutmånad. Första rätt är originalstarten |
| `consumed` | `INTEGER` | NOT NULL | Förbrukade rätter enligt kalendern före ändringsmånaden |
| `capital_sek` / `guarantee_sek_per_month` / `capital_amount_sek` | `NUMERIC` | NOT NULL | C, ΣG_j efter omräkning och B = C / A_b |
| `payout_basis_code` / `payout_basis_checksum` / `payout_factor` | | NOT NULL | Utbetalningsgrunden (SIM-B) med kontrollsumma och A_b |
| `m_sek` / `floor_sek` | `NUMERIC(14,2)` | `m_sek` > 0 | M = max(round_half_up(max(G, B)), ceil_öre(ΣG_j), golv) och bindande golv |
| `content` / `checksum` | | NOT NULL, `checksum` UNIQUE | Hela beräkningen med garantidelarnas gamla och nya faktorer; granskningssumman `decide_payout_plan` binder |
| `reason` / `decided_by` / tidsstämplar | | NOT NULL | Motivering och beslutsfattare |

### `payout_splits`

Ett delningsbeslut för en ej startad uttagsdel (PR-ITP1-024).

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Stabilt id; den nya delens id härleds ur det |
| `from_part_id` / `request_id` | `UUID` | NOT NULL, FK | Delen som delas och begäran |
| `new_part_number` | `INTEGER` | CHECK 2–3 | Högst tre delar per försäkring |
| `share` | `NUMERIC(11,10)` | CHECK 0,1–0,9 | Andelen av C och varje G_j som går till den nya delen |
| `effective_month` / `valuation_date` | `DATE` | NOT NULL, UNIQUE (del, månad) | |
| `premium_receiver_number` | `INTEGER` | CHECK 1–3 | Primär premiemottagare med vikt 1 bland ej startade delar (PR-ITP1-015) |
| `capital_sek` / `content` / `checksum` / `reason` / `decided_by` | | NOT NULL, `checksum` UNIQUE | |

**Skrivs av:** `register_payout_request`, `decide_payout_plan` och `split_payout_part`, alla `HUMAN_ONLY` (tjänstelager §9.17).
Stängningen skapar den nya uttagsdelen med läget `not_started`, kapitalposterna `split` och garantidelarnas nya versioner.

**Läses av:** `preview_payout_plan`, `get_payout_part`, månadsstängningen, premieunderlaget (premiemottagaren) och
`ledger_premiums` (en ny premie på en del med beslutad plan får G_j direkt på planen). Ledger-utdraget redovisar en
försäkring med planbaserad garanti som ej beräknad (`payout_plan`) tills A6 kan värdera planer.

## 7e. Tabeller: `payout_amounts`, `pension_claims` och `pension_claim_fundings` – Beloppsbeslut, månadsrätt och bolagsstöd

> **Status:** Paket B steg 5 (B-047 punkt 4 och 6, [P1-PENSION-001 §5.5](../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md), PB6 och PB11, Karls val W1–W12 2026-11-22, **B-053**).
> - **Var koden finns:** modeller i `src/models/pension_claim.py`; tjänstelogiken i `src/services/pension_claims.py`; beräkningen i `src/skills/calculation/pension_claim.py`; operationerna i `src/services/operations/pension_claims.py`; bokningen i stängningens steg 5 i `src/services/month_close.py`; migrationen i `scripts/migrations/migrate_pension_claims.py` (§12).
> - **Verifierat** lokalt och mot isolerad Postgres. Mergat till main 2026-11-23 efter Karls OK; **inte infört i Lakebase.**

**Domän:**
- Raderna skrivs av månadsstängningen i samma transaktion som verifikationen och ändras aldrig.
- Ett **beloppsbeslut** gäller från sin månad till nästa beslut: vid start (även efter uppskov), återstart efter paus, planändring och varje januari (PR-ITP1-009). Beloppet räknas på föregående månadsslut.
- Ett **anspråk** är en uttagsdels bruttorätt för en rättighetsmånad, en gång (PR-ITP1-026). Debiteringen ur kundkapitalet är min(M, C efter kostnader) och fördelas på delens spår (`pension_debit`). Bristen tas från bolagskontot (`company_support`), så långt det räcker (PR-ITP1-028). Resten står som ej finansierat på anspråket.
- Den tidsbegränsade delens sista rätt **slutavräknas**: brutto max(M, C), därefter C = 0 och delen `ended` (PR-ITP1-027).
- **Bolagskontot** (`account = 'company'`) får ägarens insättningar som verifikationer av slaget `company_capital`. Skulden (`payment_liability`) och bolagskontot blir aldrig negativa (`ck_ledger_capital_entries_accounts`).
- Utan tabellerna beter sig stängningen som i steg 4, och utan steg 4:s som i steg 3 (B-052).

### `payout_amounts`

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Stabilt id ur del och månad |
| `payout_part_id` / `plan_id` | `UUID` | NOT NULL, FK RESTRICT, index på delen | Uttagsdelen och planversionen beloppet räknades på |
| `effective_month` | `DATE` | NOT NULL, UNIQUE (del, månad) | Första rättighetsmånad beloppet gäller för |
| `reason` | `VARCHAR(20)` | NOT NULL, CHECK in (`'start'`, `'restart'`, `'plan_change'`, `'january'`) | Varför beloppet beslutas |
| `valuation_date` | `DATE` | NOT NULL | Föregående månadsslut |
| `capital_sek` / `guarantee_sek_per_month` / `capital_amount_sek` | `NUMERIC` | NOT NULL, ≥ 0 | C, ΣG_j och B = C / A_b |
| `payout_basis_code` / `payout_basis_checksum` / `payout_factor` | | NOT NULL, kontrollsumman 64 tecken, faktorn > 0 | Utbetalningsgrunden och A_b |
| `m_sek` / `floor_sek` / `binding` | | `m_sek` > 0; CHECK `binding` in (`'candidate'`, `'guarantee'`, `'floor'`) | M, golvet och vad som band beloppet |
| `batch_id` | `UUID` | NOT NULL, FK → `ledger_batches(id)`, index | Stängningen som beslutade beloppet |
| `content` / `created_by` | | NOT NULL | Hela beräkningen och den som stängde |

### `pension_claims`

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Stabilt id ur del och månad; steg 6:s bankförsök pekar hit |
| `payout_part_id` / `plan_id` / `amount_id` | `UUID` | NOT NULL, FK RESTRICT | Delen, planen och beloppsbeslutet |
| `right_month` / `right_number` | | NOT NULL, UNIQUE (del, månad), index på månaden, löpnummer ≥ 1 | Rättighetsmånaden och rättens nummer i planen |
| `gross_sek` / `from_capital_sek` / `company_support_sek` / `unfunded_sek` | `NUMERIC(14,2)` | NOT NULL; brutto > 0, övriga ≥ 0; CHECK `ck_pension_claims_funding`: brutto = summan | Bruttoanspråket och dess finansiering när det uppkom |
| `final_settlement` | `BOOLEAN` | NOT NULL | Sista rätten i en tidsbegränsad plan (PR-ITP1-027) |
| `payment_day` | `DATE` | NOT NULL | Första svenska bankdagen efter rättighetsmånaden |
| `batch_id` / `created_by` | | NOT NULL, FK, index | Stängningen |

### `pension_claim_fundings`

Senare finansiering av ett ej finansierat anspråk från bolagskontot, bokad i en senare stängning efter en ny insättning, äldsta anspråk först (Karls val W8).

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | |
| `claim_id` / `batch_id` | `UUID` | NOT NULL, FK RESTRICT, index; UNIQUE (anspråk, verifikation) | Anspråket och stängningen som finansierade |
| `amount_sek` | `NUMERIC(14,2)` | NOT NULL, CHECK > 0 | Kvar att finansiera är anspråkets `unfunded_sek` minus summan av finansieringarna |
| `created_by` | | NOT NULL | |

**Skrivs av:** månadsstängningen (`close_policy_month`). Insättningen på bolagskontot skrivs av `register_company_capital` (`HUMAN_ONLY`, tjänstelager §9.18) som verifikation och post i journalen (§7c).

**Läses av:** stängningens kontroller *månadsrätt*, *förbrukade rätter* och *skuld och bolagskonto*, `list_pension_claims` och senare steg 6 (bankuppdrag) och steg 7 (dödsfall). Agentrollerna har inga rättigheter.

---

## 8. Tabell: `premium_transactions` – Premietransaktioner

**Domän:** En rad per **förmån**, kalendermånad och transaktionstyp (B-022: premien hör till förmånen, inte försäkringen). I nuvarande produktscope hanteras bara ålderspensionspremier. Om andra förmånstyper senare godkänns genom ett nytt scopebeslut ska deras premier hållas åtskilda från pensionspremier. Ordinarie ålderspensionspremie beräknas enligt `01_domän/ITP1_regelverk.md` §2/§6. Tabellen är **spårbarhetens kärna**: varje krona i pensionskapitalet ska kunna följas hit och räknas om ur sitt underlag.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK, default `gen_random_uuid()` | Surrogatnyckel |
| `benefit_id` | `UUID` | NOT NULL, FK → `policy_benefits(id)` ON DELETE RESTRICT | Förmånen premien avser |
| `period_month` | `DATE` | NOT NULL, CHECK (dag = 1) | Premiemånaden, alltid månadens första dag |
| `transaction_type` | `VARCHAR(20)` | NOT NULL, CHECK in (`'premium'`, `'adjustment'`, `'fee'`), default `'premium'` | `premium` = ordinarie månadspremie, `adjustment` = korrigering (±), `fee` = kapitalavgift (B-021) |
| `pensionable_salary_sek` | `NUMERIC(10,2)` | NULL, CHECK ≥ 0 | Löneunderlag. NULL för typer utan löneunderlag |
| `amount_sek` | `NUMERIC(12,2)` | NOT NULL | Belopp. Positivt = tillförs, negativt = dras |
| `calculation_basis` | `JSONB` | NULL | Beräkningsunderlag för revision (IBB, brytpunkter, satser, delbelopp) |
| `status` | `VARCHAR(20)` | NOT NULL, CHECK in (`'pending'`, `'invoiced'`, `'paid'`, `'cancelled'`), default `'pending'` | Faktureringsflöde (villkor §4). Kapital tillgodoförs vid `paid` |
| `paid_date` | `DATE` | NULL | Datum betalning mottogs |
| `corrects_transaction_id` | `UUID` | NULL, FK → `premium_transactions(id)` ON DELETE RESTRICT, index; CHECK: bara på `adjustment` | **Fas 1f T3.** Rättelsens ursprungspost – den premierad som en `adjustment` rättar (PR-ITP1-019). NULL för allt annat |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

**Unikhet:** Partiellt unikt index på `(benefit_id, period_month)` där `transaction_type = 'premium'`. **Index:** `(benefit_id, period_month)`, `status`, `corrects_transaction_id`.

**Designnoter:**
- Förmånens kapital = `SUM(amount_sek) WHERE status = 'paid'`; försäkringens kapital = summan över dess förmåner; personens totala = summan över försäkringarna
- `calculation_basis` som JSONB: parametrar varierar per typ och år, används för revision snarare än relationella frågor (B-005)
- Avrundning till hela ören (regelverket §8.5)
- **Rättelser (Fas 1f T3, `correct_premium_transaction`):** ursprungsraden ändras aldrig. En lönerättelse skapar en ny `adjustment`-rad med `corrects_transaction_id` = ursprungsraden, differensen mellan rättad och hittills gällande premie (ursprung + tidigare rättelser), status `pending` (ny fordran eller kredit – kapital först när den tas emot) och fullt underlag i `calculation_basis` (premiemånadens IBB, gammalt och nytt belopp, underlagets referens, regelstatus). Rättelse som skulle minska redan mottagen premie görs inte här – återtag kräver spårad kapitalandel och historisk garantidel (PR-ITP1-019 p.3, PR-ITP1-020) som modellen saknar

---

## 8b. Tabell: `salary_reports` – Löneunderlag

> **Status:** Beslutad av operatören 2026-10-11 (Fas 1f T3, **B-030**). Skapad i Lakebase samma dag med migrationsskriptet (§12) efter backup och avstämning enligt AGENTS.md §4.5.

**Domän:** Pensionsmedförande lön (PR-ITP1-014) för en försäkrad hos en arbetsgivare under en kalendermånad – faktiskt utbetald kontant bruttolön efter löneväxling, i utbetalningsmånaden. Underlaget för premietrappan, som räknas en gång per person, arbetsgivare och månad (PR-ITP1-001). Skiljs från **aktuell lön** som uppgift på personen (`insured_persons.monthly_salary_sek`), som inte är pensionsmedförande underlag, och från **premien** (`premium_transactions`), som är en fordran eller ett mottaget belopp.

Tabellen är **append-only**: en rättelse är en ny version som pekar på den den ersätter. Gällande underlag för en månad är den högsta versionen. En rad med 0,00 är en uttryckligen rapporterad noll; ingen rad betyder att rapport saknas (PR-ITP1-014, PR-ITP1-017).

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK, default `gen_random_uuid()` | Surrogatnyckel |
| `insured_person_id` | `UUID` | NOT NULL, FK → `insured_persons(id)` ON DELETE RESTRICT | Den försäkrade |
| `employer_id` | `UUID` | NOT NULL, FK → `employers(id)` ON DELETE RESTRICT | Arbetsgivaren som betalade ut lönen |
| `period_month` | `DATE` | NOT NULL, CHECK (dag = 1) | Utbetalningsmånaden (rapportmånaden) |
| `version` | `INTEGER` | NOT NULL, CHECK ≥ 1 | 1 = första rapporten; rättelser 2, 3 … |
| `supersedes_id` | `UUID` | NULL, FK → `salary_reports(id)` ON DELETE RESTRICT, UNIQUE | Versionen som rättas. NULL bara för version 1 |
| `pensionable_salary_sek` | `NUMERIC(10,2)` | NOT NULL, CHECK ≥ 0 | Pensionsmedförande lön. 0 = rapporterad noll |
| `source` | `VARCHAR(20)` | NOT NULL, CHECK in (`'employer'`, `'manual'`) | Ursprung: arbetsgivarens rapport eller manuellt registrerat underlag |
| `source_reference` | `VARCHAR(100)` | NULL | Avsändarens referens (lönefil, lönebesked) – dubblettskydd |
| `received_date` | `DATE` | NOT NULL | När underlaget togs emot |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

**Integritet:**
- Unikt `(insured_person_id, employer_id, period_month, version)` – en version per månad
- Unikt `supersedes_id` – en version kan bara ersättas en gång, så kedjan blir linjär och två samtidiga rättelser av samma version kan inte båda sparas
- CHECK: version 1 har ingen föregångare, senare versioner har en
- Partiellt unikt `(employer_id, source_reference)` där referensen finns – samma rapport registreras inte två gånger
- Index `(insured_person_id, period_month)`

**Skrivs av** tjänstelagrets `register_salary_report` (`02_system/tjänstelager.md` §9). Operationen skapar ingen premie och räknar inte om gamla premier – en rättelse av en månad som redan har premie redovisar den berörda premien, som rättas separat med `correct_premium_transaction` (PR-ITP1-019 p.1). Ingen historik skapas retroaktivt: premiehistoriken 2023–2026 har sitt löneunderlag i `premium_transactions.pensionable_salary_sek`.

---

## 8e. Tabeller: `bank_events` och `payment_allocations` – Inbetalningar

> **Status:** Paket A steg 4 (**B-046**, [P1-PREMIE-001](../projekt/01_ärendehantering/PREMIEFLODE_DESIGNSTOPP.md) §4.6–4.7 och §5). Modeller `src/models/bank.py`, operationer i `src/services/operations/payments.py` och lokala tester. **Skapade tomma i Lakebase 2026-11-08** med migrationen i steg 8 (§12), efter backup `backups/20261108T075712Z` och Karls OK.

**Domän:** En bankhändelse är en inbetalning som banken rapporterat. En allokering fördelar en del av den till en fakturarad eller till avstämningskontot. Summan av en händelses allokeringar är alltid händelsens belopp. Allokeringarna är sanningskällan för vad som är betalt (PA6) och ändras aldrig.

### `bank_events`

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Surrogatnyckel |
| `source_system` / `event_id` | `VARCHAR(40)` / `VARCHAR(64)` | NOT NULL, unika tillsammans | Bankens källsystem och händelse-ID |
| `file_reference` / `file_checksum` | `VARCHAR(60)` / `VARCHAR(64)` | NOT NULL | Filen som först rapporterade händelsen |
| `content_checksum` | `VARCHAR(64)` | NOT NULL | SHA-256 över händelsens innehåll; ändrat innehåll ger konflikt |
| `received_date` | `DATE` | NOT NULL | Mottagningsdag |
| `amount_sek` | `NUMERIC(12,2)` | NOT NULL, CHECK > 0 | Inbetalt belopp |
| `payer_org_number` | `VARCHAR(10)` | NOT NULL | Betalaren enligt banken |
| `reference` | `VARCHAR(35)` | NOT NULL | Angiven referens, normalt OCR |
| `created_by` / `created_at` | `VARCHAR(100)` / `TIMESTAMPTZ` | NOT NULL | Vem som läste in filen och när |

### `payment_allocations`

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Surrogatnyckel |
| `bank_event_id` | `UUID` | NOT NULL, FK → `bank_events(id)` | Inbetalningen |
| `kind` | `VARCHAR(20)` | NOT NULL, CHECK in (`invoice_line`, `suspense`) | Fakturarad eller avstämningskontot |
| `invoice_id` / `invoice_line_id` | `UUID` | NULL, FK | Fakturan och raden; raden satt exakt för `invoice_line` |
| `amount_sek` | `NUMERIC(12,2)` | NOT NULL | Positivt för en fakturarad; på avstämningskontot positivt in och negativt vid manuell fördelning |
| `basis` | `VARCHAR(30)` | NOT NULL, CHECK in (`ocr_match`, `manual`, `overpayment`, `unknown_reference`, `wrong_payer`, `manual_release`) | Fördelningsgrund |
| `basis_version` | `VARCHAR(40)` | NOT NULL | `PR-ITP1-018 v1` |
| `allocation_key` | `VARCHAR(64)` | NOT NULL, UNIQUE | Idempotensnyckel |
| `created_by` / `created_at` | `VARCHAR(100)` / `TIMESTAMPTZ` | NOT NULL | Aktör och tidpunkt |

**Integritet:**
- Unikt `(source_system, event_id)` – samma bankhändelse sparas en gång
- CHECK: en radallokering har faktura, rad och positivt belopp; en avstämningspost har ingen rad och ett belopp skilt från noll
- Unik `allocation_key` – ingen dubbel allokering
- Index på händelse, faktura, rad och mottagningsdag

**Skrivs av** `import_bank_file` och `allocate_unmatched_payment`; **läses av** `get_receivables`, `get_invoice` och `check_overdue_invoices` (alla `HUMAN_ONLY`, `02_system/tjänstelager.md` §9.12). Agentrollerna får inga rättigheter på tabellerna i första versionen.

---

## 8d. Tabeller: `invoices` och `invoice_lines` – Fakturor

> **Status:** Paket A steg 3 (**B-046**, [P1-PREMIE-001](../projekt/01_ärendehantering/PREMIEFLODE_DESIGNSTOPP.md) §4.4–4.5 och §5). Modeller `src/models/invoice.py`, operationer i `src/services/operations/invoices.py` och lokala tester. **Skapade tomma i Lakebase 2026-11-08** med migrationen i steg 8 (§12), efter backup `backups/20261108T075712Z` och Karls OK.

**Domän:** En faktura till en arbetsgivare för en premieperiod. En debetfaktura har ordinarie premie, ny debet efter kredit och tillägg. En kreditfaktura krediterar rader på en tidigare debetfaktura och avräknas separat (PR-ITP1-017, -018). Fakturor och rader ändras aldrig.

### `invoices`

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Surrogatnyckel |
| `invoice_number` | `VARCHAR(20)` | NOT NULL, UNIQUE | `INV-NNNNNN` |
| `employer_id` | `UUID` | NOT NULL, FK → `employers(id)` ON DELETE RESTRICT | Betalaren |
| `period_month` | `DATE` | NOT NULL, CHECK (dag = 1) | Premieperioden |
| `invoice_type` | `VARCHAR(10)` | NOT NULL, CHECK in (`debit`, `credit`) | Debet- eller kreditfaktura |
| `ocr_reference` | `VARCHAR(25)` | NOT NULL, UNIQUE | OCR med längd- och kontrollsiffra (modulus 10) |
| `invoice_date` / `due_date` | `DATE` | NOT NULL, CHECK `due_date >= invoice_date` | Fakturadatum; förfallodag 30 dagar till nästa bankdag |
| `total_sek` | `NUMERIC(12,2)` | NOT NULL | Positiv för debet, negativ för kredit |
| `credited_invoice_id` | `UUID` | NULL, FK → `invoices(id)` | Den krediterade debetfakturan; satt exakt för kredit |
| `checksum` | `VARCHAR(64)` | NOT NULL | SHA-256 över fakturans innehåll |
| `created_by` / `created_at` | `VARCHAR(100)` / `TIMESTAMPTZ` | NOT NULL | Vem som skapade fakturan och när |

### `invoice_lines`

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Surrogatnyckel |
| `invoice_id` | `UUID` | NOT NULL, FK → `invoices(id)` | Fakturan |
| `line_number` | `INTEGER` | NOT NULL, unik per faktura | Radnummer |
| `line_type` | `VARCHAR(20)` | NOT NULL, CHECK in (`ordinary`, `rebill`, `additional`, `credit`) | Ordinarie premie, ny debet efter kredit, tillägg på mottagen premie eller kredit |
| `premium_transaction_id` | `UUID` | NOT NULL, FK → `premium_transactions(id)` | Premiekedjans ordinarie premierad |
| `covers` | `JSONB` | NOT NULL | Premieraderna som raden fakturerar |
| `benefit_id` / `policy_id` | `UUID` | NOT NULL, FK | Förmånen och försäkringen; personnumret står inte på fakturan |
| `period_month` | `DATE` | NOT NULL | Premieperioden |
| `amount_sek` | `NUMERIC(12,2)` | NOT NULL | Positivt för debetrader, negativt för kredit |
| `credits_line_id` | `UUID` | NULL, FK → `invoice_lines(id)`, UNIQUE | Den krediterade raden; satt exakt för kredit |

**Integritet:**
- CHECK: debet har positiv summa och ingen krediterad faktura; kredit har negativ summa och en krediterad faktura
- CHECK: kreditrad har negativt belopp och krediterad rad; övriga rader positivt belopp och ingen
- En rad krediteras högst en gång (unikt `credits_line_id`)
- Index `(employer_id, period_month)`, `credited_invoice_id` och `premium_transaction_id`

**Koppling till premieraderna:** fakturaraden pekar på premieraden. Designstoppet §5 föreslog dessutom nullbara kolumner i `premium_transactions` för löneunderlag och fakturarad. De läggs inte till nu. Koden på `main` läser premierader i Lakebase, och en ny kolumn i modellen skulle göra varje läsning ogiltig före migrationen. En premierad kan också ha flera fakturarader (debet, kredit, ny debet). Löneunderlagets id och version står i `calculation_basis` (`salary_report`). Steg 8 inför inga kolumner i `premium_transactions`; Karl godkände 2026-11-08 att kolumnerna utgår. En kolumn för löneunderlaget kan läggas till senare om en läsare behöver den (§12, paket A steg 8).

**Skrivs av** `create_invoice`; **läses av** `get_invoice`, `list_invoices` och `check_overdue_invoices` (alla `HUMAN_ONLY`, `02_system/tjänstelager.md` §9.11). Agentrollerna får inga rättigheter på tabellerna i första versionen.

---

## 8c. Tabell: `salary_files` – Löneunderlagsfiler

> **Status:** Paket A steg 2 (**B-046**, [P1-PREMIE-001](../projekt/01_ärendehantering/PREMIEFLODE_DESIGNSTOPP.md) §4.1–4.2 och §5). Modell `src/models/salary_file.py`, operationer i `src/services/operations/salary_files.py` och lokala tester. **Skapad tom i Lakebase 2026-11-08** med migrationen i steg 8 (§12, designstoppet §11), tillsammans med fakturans och bankens tabeller, efter backup `backups/20261108T075712Z` och Karls OK.

**Domän:** En fil från en arbetsgivare för en period, med en rad per anställd och månad. Filen tas emot och valideras i betrodd kod utan att något registreras. Handläggaren granskar och godkänner eller avslår den. Innehållet ändras aldrig. Vid godkännande registreras giltiga rader i `salary_reports` med källreferensen `<filens referens>:<radnummer>`.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Surrogatnyckel |
| `employer_id` | `UUID` | NOT NULL, FK → `employers(id)` ON DELETE RESTRICT | Avsändande arbetsgivare |
| `period_month` | `DATE` | NOT NULL, CHECK (dag = 1) | Filens period, från 2026-10 (PA1) |
| `file_reference` | `VARCHAR(60)` | NOT NULL | Arbetsgivarens referens för filen |
| `received_date` | `DATE` | NOT NULL | Mottagningsdag |
| `content` | `JSONB` | NOT NULL | Det kanoniska innehållet: huvud och rader (personnummer, månad, lön, `kind`, `corrects_version`) |
| `checksum` | `VARCHAR(64)` | NOT NULL | SHA-256 över `content`; avsändaren räknar likadant och filen tas inte emot om summorna skiljer sig |
| `validation` | `JSONB` | NOT NULL | Varje rads utfall (`valid`/`deviation` med skälkod), saknade premiebetalande personer och sammanställning med lönesumma och förhandsberäknad premie |
| `review_digest` | `VARCHAR(64)` | NOT NULL | SHA-256 över `checksum` och `validation`; godkännandet binder den |
| `status` | `VARCHAR(20)` | NOT NULL, CHECK in (`received`, `approved`, `rejected`) | Filens läge |
| `created_by` / `created_at` | `VARCHAR(100)` / `TIMESTAMPTZ` | NOT NULL | Vem som tog emot filen och när |
| `decided_by` / `decided_at` | `VARCHAR(100)` / `TIMESTAMPTZ` | NULL | Satta exakt när filen är godkänd eller avslagen |
| `decision_note` | `TEXT` | NULL | Motivering; krävs vid avslag |
| `outcome` | `JSONB` | NULL | Vid godkännande: registrerade löneunderlag, premierader, premiesumma och skapade ärenden |

**Integritet:**
- Unikt `(employer_id, file_reference)` – samma referens tas emot en gång. Samma innehåll igen ger samma kvitto; ändrat innehåll ger konflikt
- CHECK: `received` saknar beslut, `approved`/`rejected` har beslutsfattare och tidpunkt
- CHECK: `rejected` har `decision_note`
- CHECK: båda kontrollsummorna är 64 tecken; `period_month` är första dagen i månaden (Postgres- och SQLite-variant)
- Index `(employer_id, period_month)`

**Skrivs av** `import_salary_file`, `approve_salary_file` och `reject_salary_file`; **läses av** `get_salary_file` (alla `HUMAN_ONLY`, `02_system/tjänstelager.md` §9.10). Agentrollerna får inga rättigheter på tabellen i första versionen.

**Personuppgifter:** `content`, `validation` och `outcome` har personnummer och lön (B-006).

---

## 9. Tabell: `base_amounts` – Basbelopp per år

**Domän:** Parametertabell med de basbelopp beräkningar behöver, ett värde per år. Premiemotorn läser härifrån – basbelopp får aldrig hårdkodas i beräkningskod (`01_domän/ITP1_regelverk.md` §6). Uppdateras årligen av operatören när regeringen fastställt nya belopp (november året innan).

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `year` | `INTEGER` | PK | Kalenderår |
| `income_base_amount_sek` | `NUMERIC(10,2)` | NOT NULL, CHECK > 0 | Inkomstbasbelopp (IBB) för året |
| `price_base_amount_sek` | `NUMERIC(10,2)` | NULL, CHECK > 0 | Prisbasbelopp (PBB). NULL tills det behövs (används inte av ålderspensionspremien) |
| `source` | `VARCHAR(255)` | NULL | Källa, t.ex. "Förordning (2025:1002)" |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

**Designnoter:**
- Naturlig nyckel (`year`) som PK – parametertabell, inget behov av surrogatnyckel
- Brytpunkternas belopp lagras **inte** utan härleds i kod ur IBB – en enda sanning, ingen risk för inkonsekvent avrundning i data. Multiplarna (7,5 och 30 IBB) är produktparametrar i `product_parameters` (§9h, B-035)
- Seedas med IBB 2023–2026 ur `01_domän/ITP1_regelverk.md` §6

---

## 9b. Tabell: `operation_events` – Händelselogg för tjänstelagret

**Domän:** Append-only logg över allt som görs via tjänstelagret (B-028, `02_system/tjänstelager.md` §7): utförda ändringar, läsningar av personuppgifter, agentförslag, avslag och nekade agentförsök. Samma spår för handläggare, agenter och skript (B-017). Rader uppdateras eller tas aldrig bort.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `VARCHAR(32)` | PK | Händelse-id (UUID hex) |
| `occurred_at` | `TIMESTAMPTZ` | NOT NULL | När händelsen inträffade |
| `operation` | `VARCHAR(64)` | NOT NULL | Operationens namn, t.ex. `register_salary_report` |
| `kind` | `VARCHAR(20)` | NOT NULL | `read` / `compute` / `write` / `external` |
| `outcome` | `VARCHAR(20)` | NOT NULL, CHECK in (`executed`, `proposed`, `rejected`, `denied`) | Vad som hände |
| `actor_type` | `VARCHAR(10)` | NOT NULL, CHECK in (`human`, `agent`, `system`) | Vem som agerade |
| `actor_id` | `VARCHAR(100)` | NOT NULL | Handläggare, agent eller skript |
| `actor_team` | `VARCHAR(50)` | NULL | Agentens team (B-026) |
| `proposed_by` | `VARCHAR(100)` | NULL | Agent som föreslog (när en handläggare utfört ett godkänt förslag) |
| `approval_id` | `VARCHAR(32)` | NULL | Godkännandeärendet, om något |
| `run_id` / `case_id` | `VARCHAR(100)` | NULL | Agentkörning respektive ärende |
| `reason` | `TEXT` | NULL | Motivering (obligatorisk för ändringar) |
| `rules` | `JSONB` | NULL | Produktregler operationen implementerar |
| `pii` | `BOOLEAN` | NOT NULL | Om operationen rör personuppgifter |
| `input` / `output` | `JSONB` | NULL | Indata och, för ändringar, resultat |
| `detail` | `TEXT` | NULL | T.ex. skäl till nekad åtkomst eller avslag |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

**Index:** `(operation, occurred_at)`, `(actor_id, occurred_at)`, `run_id`.

**Designnoter:**
- Skrivs i **samma transaktion** som operationen – en ändring utan loggrad kan inte uppstå (transaktionsgränsen: `tjänstelager.md` §6.1)
- För utförda ändringar innehåller `detail` regelstatus och filversion vid verkställigheten
- Läsresultat loggas inte (kan vara stora och fulla av personuppgifter) – bara vem som läste vad
- Data här kan inte genereras fram igen – omfattas av backup (`scripts/maintenance/backup_database.py`)

---

## 9c. Tabell: `approval_requests` – Godkännandekö

**Domän:** Agentförslag som väntar på eller har fått beslut av en handläggare (B-028, `02_system/tjänstelager.md` §6). När ett förslag godkänns körs operationen på nytt mot aktuellt läge, utförd av handläggaren.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `VARCHAR(32)` | PK | Ärende-id (UUID hex) |
| `operation` | `VARCHAR(64)` | NOT NULL | Föreslagen operation |
| `input` | `JSONB` | NOT NULL | Föreslagen indata (validerad när förslaget lades) |
| `reason` | `TEXT` | NULL | Agentens motivering |
| `proposed_by` / `proposed_by_team` | `VARCHAR(100)` / `VARCHAR(50)` | NOT NULL / NULL | Agent och team |
| `run_id` / `case_id` | `VARCHAR(100)` | NULL | Agentkörning respektive ärende |
| `status` | `VARCHAR(20)` | NOT NULL, CHECK in (`pending`, `approved`, `rejected`), default `pending` | Läge |
| `decided_by` | `VARCHAR(100)` | NULL | Handläggaren som beslutade |
| `decided_at` | `TIMESTAMPTZ` | NULL | När beslutet togs |
| `decision_note` | `TEXT` | NULL | Handläggarens kommentar |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | `created_at` = när förslaget lades |

**Index:** `status`.

**Designnoter:**
- Ett ärende avgörs med en villkorlig uppdatering (`… WHERE id = … AND status = 'pending'`) i samma transaktion som ändringen och loggraden – av två samtidiga beslut kan bara ett lyckas, och fallerar verkställigheten är ärendet fortfarande `pending` (`tjänstelager.md` §6.1). Ingen schemaändring behövdes för detta

---

## 9d. Tabell: `portfolios` – Simulerade portföljscenarier

**Domän:** En kollektiv, fristående testportfölj enligt B-003/B-019/B-021.
Operatören gav 2026-10-24 mandat att välja modell och fortsätta efter designstoppet;
modellval A–F i [beslutsunderlaget](../projekt/05_kapitalförvaltning/DATAMODELL_BESLUTSFORSLAG.md)
tillämpas. Inget nytt beslut är infört i BESLUTSLOGG. SD-KAP-001 v0.1 är fortsatt
ett ej antaget utkast. Modellerna ger inga handelsbehörigheter.

| Kolumn | Datatyp | Constraints / betydelse |
|---|---|---|
| `id` | UUID | PK, Python-default `uuid4` |
| `scenario_code` | VARCHAR(64) | NOT NULL, UNIQUE, ej blank |
| `name`, `scenario_description` | VARCHAR(200), TEXT | NOT NULL, ej blanka |
| `mode` | VARCHAR(20) | NOT NULL, default och CHECK `paper` |
| `scenario_type` | VARCHAR(20) | NOT NULL, default och CHECK `standalone` |
| `base_currency` | VARCHAR(3) | NOT NULL, default och CHECK `SEK` |
| `settlement_model` | VARCHAR(30) | NOT NULL, default och CHECK `instant_simulated` |
| `starts_at` | TIMESTAMPTZ | NOT NULL, scenariots starttid |
| `opening_cash_sek` | NUMERIC(18,2) | NOT NULL, ≥ 0, ingen standardinsättning |
| `funding_basis` | JSONB | NOT NULL; källa, belopp, tid och mänskligt finansieringsbeslut |
| `guideline_reference`, `guideline_version` | VARCHAR(200), VARCHAR(40) | NOT NULL, ej blanka; styrgrundens identitet/version |
| `guideline_hash` | VARCHAR(64) | NOT NULL, längd 64; underlagets SHA-256 |
| `scenario_basis` | JSONB | NOT NULL; scenario, godkänd uppbyggnadsplan och antaganden |
| `created_at`, `updated_at` | TIMESTAMPTZ | Basmodellens standardfält |

Startkassan är ett uttryckligt finansieringsfaktum, inte ett ändringsbart saldo.
Det ska låsas efter scenariostart av den framtida kapitalgatewayen.
Inga ingående värdepapper, insättningar eller uttag stöds i denna version.
Portföljen ska märkas **fristående portföljtest, inte åtagandetäckning**.

**Saldokontrakt för senare kod:** antal andelar = utförda köp minus utförda
försäljningar; kassa = startkassa minus köpens bruttolikvid plus försäljningarnas
bruttolikvid minus samtliga avslutskostnader. Endast `executed` räknas.
Fri kassa drar dessutom av `max_cash_sek` för `approved` köp; fri säljbar kvantitet
drar av `quantity` för `approved` sälj. Förslag reserverar inget. Avslag frigör
reservationen; utförande ersätter den med faktisk effekt i en transaktion.
Härledningen, reservationerna och saldokontrollen implementeras i ett senare steg.

NAV, aktuella saldon, avkastning och anskaffningsvärden lagras inte. Full §6-NAV
kräver aktuella priser, kassa, säkra fordringar, skulder och upplupna kostnader;
saknade komponenter är **ej beräknade**. `instant_simulated` betyder samtidig
simulerad leverans av andelar och likvid; fonders verkliga avveckling och
fördröjningsstress kräver senare utbyggnad. Godkända försäljningar är inte fri likvid.

**Senare premieinsättningar:** separat planerad kassaflödesjournal med avstämda,
mänskligt godkända batcher. Bara faktiskt betalda och tilldelade premieflöden,
inte en okontrollerad kopia av försäkringskapitalet. En försäkringsnära avstämning
hindrar överlappande källtransaktioner; kapitaldelen får aggregat och unik,
ogenomskinlig källreferens utan individdata. Premier är externa avkastningsflöden.
PR-ITP1-028:s kapitaländamål, finansiering och ALM måste vara avstämda före
beståndskoppling. Ingen import eller sådan journal byggs i Fas 2c.

## 9e. Tabell: `portfolio_holdings` – Portföljens instrument

**Domän:** Instrumentregistrering per portfölj, även vid noll andelar. Antal
och marknadsvärde härleds senare; en registrering bevisar inte köpbehörighet.

| Kolumn | Datatyp | Constraints / betydelse |
|---|---|---|
| `id` | UUID | PK, Python-default `uuid4` |
| `portfolio_id` | UUID | NOT NULL, FK → `portfolios(id)` ON DELETE RESTRICT |
| `instrument_key`, `name` | VARCHAR(100), VARCHAR(200) | NOT NULL, ej blanka; entydig andelsklass, normalt ISIN |
| `market_symbol`, `market_reference` | VARCHAR(100), VARCHAR(100) | NULL; ticker är inte ensam identitet |
| `allocation_bucket` | VARCHAR(30) | NOT NULL, CHECK `sek_fixed_income` / `global_equity` / `swedish_equity` |
| `price_currency` | VARCHAR(3) | NOT NULL, längd 3; handels-/prisvaluta, inte bevis på underliggande valutarisk |
| `instrument_basis_reference` | VARCHAR(200) | NOT NULL, ej blank |
| `instrument_basis_hash` | VARCHAR(64) | NOT NULL, längd 64 |
| `instrument_basis` | JSONB | NOT NULL; mandat, prövning, godkännande, genomlysningskälla/-datum och version |
| `created_at`, `updated_at` | TIMESTAMPTZ | Basmodellens standardfält |

**Unikhet:** `(portfolio_id, instrument_key)`; indexet stöder även portföljuppslag.
Kassa har ingen instrumentrad. Identitet och allokeringsdel ska låsas efter
första affärsförslaget; gamla trades bevarar eget versionsbundet underlag.

Koderna motsvarar mål 55/25/10 % och kassa 10 %. Intervall och övriga limiter
ägs av riktlinjen, inte ändringsbara modellstandarder: räntor 45–70 %, aktier
totalt 25–45 %, globaldel 20–35 %, svensk del 5–15 %, kassa 5–20 %.
Någon limitmotor, instrumentlista eller genomlysning skapas inte i 2c.
Underlag för bl.a. UCITS, fysisk replikering, rating, duration, emittent/grupp,
fondtak, valuta och likviditet behövs före köp. Saknad/för gammal data är
**ej verifierad**, aldrig noll eller antaget godkänt.

## 9f. Tabell: `trades` – Affärsförslag och simulerade avslut

**Domän:** Ett låst köp-/säljförslag med separata kvittenser som fylls i en gång.
Ingen återanvändning av försäkringens `approval_requests` eller `operation_events`.
Livscykel: `proposed → approved → executed`, `proposed → rejected` eller
`approved → rejected`. Utfört/avslaget är slutligt. Agenten får föreslå;
människa måste godkänna även simulerade portföljändringar (harness §9.5).

| Kolumn | Datatyp | Constraints / betydelse |
|---|---|---|
| `id` | UUID | PK, Python-default `uuid4` |
| `portfolio_holding_id` | UUID | NOT NULL, FK → `portfolio_holdings(id)` ON DELETE RESTRICT; portfölj via instrumentet |
| `side`, `status` | VARCHAR(10), VARCHAR(20) | NOT NULL; CHECK `buy`/`sell`, respektive `proposed`/`approved`/`executed`/`rejected`; default `proposed` |
| `quantity`, `limit_price` | NUMERIC(24,10) | NOT NULL, > 0; exakt kvantitet, högsta köppris/lägsta säljpris i prisvalutan |
| `max_cost_sek` | NUMERIC(18,2) | NOT NULL, ≥ 0; kostnadstak |
| `max_cash_sek`, `min_proceeds_sek` | NUMERIC(18,2) | Köp: bara `max_cash_sek`, > 0 inkl. kostnader; sälj: bara `min_proceeds_sek`, ≥ 0 efter kostnader |
| `proposed_at`, `valid_until` | TIMESTAMPTZ | NOT NULL, `valid_until > proposed_at` |
| `proposed_by`, `proposer_type`, `reason` | VARCHAR(100), VARCHAR(10), TEXT | NOT NULL, ej blank aktör/motivering; typ `human`/`agent` |
| `run_reference`, `order_group_reference` | VARCHAR(100), VARCHAR(100) | NULL; gruppreferens ger inte gruppgodkännande |
| `proposal_hash` | VARCHAR(64) | NOT NULL, längd 64; exakt förslag, prisvillkor och versioner |
| `proposal_price_basis`, `proposal_basis` | JSONB | NOT NULL; prisunderlag respektive versionsbundet kontroll-/beslutsunderlag |
| `approved_at`, `approved_by`, `approval_role` | TIMESTAMPTZ, VARCHAR(100), VARCHAR(100) | Alla tillsammans med nedanstående godkännandefält; ej blank aktör/roll |
| `approved_proposal_hash`, `approval_basis` | VARCHAR(64), JSONB | Matchande `proposal_hash` och godkännandekvitto |
| `executed_at`, `execution_price`, `execution_fx_rate` | TIMESTAMPTZ, NUMERIC(24,10), NUMERIC(24,10) | Komplett utförandekvitto tillsammans med nedanstående; pris/faktor > 0 |
| `gross_sek`, `cost_sek` | NUMERIC(18,2) | Utförandets positiva bruttolikvid och kostnad ≥ 0 |
| `execution_price_basis`, `execution_basis` | JSONB | Utförandets pris-/valutakälla och bokningskvitto |
| `rejected_at`, `rejected_by`, `rejection_reason` | TIMESTAMPTZ, VARCHAR(100), TEXT | Komplett avslagskvitto; ej blank aktör/motivering |
| `supersedes_trade_id`, `corrects_trade_id` | UUID | NULL, själv-FK ON DELETE RESTRICT; inte eget id |
| `created_at`, `updated_at` | TIMESTAMPTZ | Basmodellens standardfält |

**CHECK-kontrakt:** varje kvittensgrupp är helt NULL eller helt ifylld (inklusive
JSON-kolumner). `proposed` saknar kvittenser; `approved` har bara godkännandet;
`executed` har godkännande och utförande; `rejected` har avslaget och kan bevara
ett tidigare komplett godkännande, men inget utförande. Godkännandets hash
måste matcha förslagets. `proposed_at ≤ approved_at ≤ executed_at ≤ valid_until`
gäller där respektive tid finns; avslag ligger tidigast vid förslag/godkännande
och får ske efter giltighetstidens slut. Utförandets kostnad får inte överstiga
taket. Pris och SEK-totallikvid måste hålla köp-/säljvillkoren.

**Index:** `(portfolio_holding_id, executed_at)` och `(status, proposed_at)`.
Ett id kan bära högst ett utförande. Delavslut eller upprepad godkännandeomgång
stöds inte. Ändrat förslag ger en ny länkad rad; ett utfört avslut rättas med
ny mänskligt godkänd kompensation, inte omskriven historik.

**Pris- och valutaunderlag:** för prövning och utförande sparas skilda
ögonblicksbilder med instrument/andelsklass, leverantör, källreferens, kurstyp,
marknad/kalender, observationstid, hämtningstid, pris och prisvaluta samt
valutafaktor (SEK per enhet prisvaluta) med egen källa/tid. SEK har faktor 1,
märkt som identitet. Typade utförandekolumner och JSON måste stämma överens.
Bruttolikvid = kvantitet × avslutspris × valutafaktor, `Decimal`, avrundat
till ören med `ROUND_HALF_UP`; kostnaden dras exakt en gång. UTC används för
tidpunkter; kursfärskhet avser relevant handelsdag, inte ett 24-timmarsfönster.

**Begränsning:** CHECK säkrar radens struktur, inte tidigare övergångar,
autentiserad mänsklig identitet, JSON-innehållets schema eller oföränderlighet.
Framtida kapitalgateway ska säkra dessa, kanonisering/hash, länkar inom rätt
portfölj, idempotens, portföljlåsning och reservationer, positiva saldon,
pris-/valutavalidering, färskhet, limiter/stress och revisionsspår även för
passiva brott eller beslut att avstå. Ingen sådan operation byggs i 2c.

**Portabilitet:** generiska constraints, UUID och `JSON(none_as_null=True)` med
JSONB-variant i Postgres. Python-`None` blir SQL NULL, så kvittensgrupperna kan
kontrolleras. SQLite-tester körs med FK-kontroll, men ger inte Postgres
precision, tidszonsskydd eller samtidighetsbevis. Postgres-DDL kompileras lokalt;
ingen extern databas ansluts. `src/models/__init__.py` registrerar tabellerna
för befintligt `scripts/setup/create_tables.py`; skriptet har inte körts.

---

## 9g. Tabell: `cases` – Ärenden

> **Status:** Beslutad av operatören 2026-10-24 (Fas 5, **B-033**, `projekt/01_ärendehantering/ARENDEN_BESLUTSFORSLAG.md`). Modell och lokala tester i F5-1. Skapad i Lakebase 2026-10-24 efter backup `backups/20261024T191154Z` och torrkörning, med operatörens OK (AGENTS.md §4.5); radantalen i övriga tabeller oförändrade.

**Domän:** Ett ärende är något som kommit in och ska handläggas – i v1 ett inrapporterat löneunderlag. Ärendet är handläggaragentens arbetsenhet och mandat: resursmandatet för en agentkörning byggs ur ärendets person, försäkringar, arbetsgivare och period (`harness.md` §5.1), och en körning gäller ett ärende. Ärendenumret är det som står i `case_id` i `operation_events` och `approval_requests` (§9b–9c).

Raden har ärendets **aktuella** status och utfall. Historiken – vem som skapade, bytte status och stängde, när och varför – står i `operation_events` via `case_id`, eftersom varje ändring går genom en tjänsteoperation (B-033 val A). Ingen separat händelsetabell.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK, default `gen_random_uuid()` | Surrogatnyckel |
| `case_number` | `VARCHAR(20)` | NOT NULL, UNIQUE, CHECK form `CASE-NNNNNN` | Ärendenumret; står i `case_id` i kö och logg |
| `case_type` | `VARCHAR(40)` | NOT NULL, CHECK in (`'salary_report'`, `'salary_file_deviation'`, `'payment_overdue'`, `'payment_unmatched'`, `'payout_reconstruction'`, `'payout_request'`, `'payout_review'`, `'company_capital'`) | Ärendetyp. Fler typer läggs till med ny CHECK (B-033 val C). `salary_file_deviation` (paket A steg 2) är en avvikelse i en löneunderlagsfil, `payment_overdue` (steg 3) en förfallen faktura och `payment_unmatched` (steg 4) en inbetalning på avstämningskontot; alla avgörs av människa. CHECK-villkoret byttes i Lakebase av premieflödets migration 2026-11-08 (§12, paket A steg 8). `payout_reconstruction` (paket B steg 1) skapas av övergången för varje uttag som flyttats från försäkringens läge till uttagsdel 1; handläggaren rekonstruerar plan och utbetalningshistorik ur underlag. Villkoret byttes i Lakebase av uttagsdelarnas migration 2026-11-14 (§12); inga sådana ärenden där, eftersom inga uttagslägen fanns. `payout_request` (paket B steg 4) är kundens begäran om uttag, delning eller ändrad plan, och `payout_review` ett ärende som månadsstängningen öppnar när standardstarten inte kan göras: overifierat underlag eller en person som passerat 66 utan plan. Båda avgörs av människa; villkoret vidgas av `migrate_payout_plans.py`, som inte är införd i Lakebase. `company_capital` (paket B steg 5) öppnas av månadsstängningen när bolagskontot inte räcker till ett anspråk och eskaleras till operatören; ärendet gäller bolaget och saknar person och arbetsgivare. Villkoret vidgas av `migrate_pension_claims.py`, som inte är införd |
| `status` | `VARCHAR(20)` | NOT NULL, CHECK in (`open`, `in_progress`, `waiting_approval`, `waiting_info`, `closed`), default `open` | Aktuell status |
| `outcome` | `VARCHAR(20)` | NULL, CHECK in (`approved`, `rejected`, `supplement_requested`, `manual_review`, `no_action`) | Utfall; satt exakt när ärendet är stängt |
| `insured_person_id` | `UUID` | NULL, FK → `insured_persons(id)` ON DELETE RESTRICT | Den försäkrade ärendet gäller |
| `policy_id` | `UUID` | NULL, FK → `policies(id)` ON DELETE RESTRICT | Försäkringen, om ärendet gäller en viss |
| `employer_id` | `UUID` | NULL, FK → `employers(id)` ON DELETE RESTRICT | Arbetsgivaren, t.ex. avsändare av löneunderlaget |
| `period_month` | `DATE` | NULL, CHECK (dag = 1) | Månaden ärendet gäller |
| `channel` | `VARCHAR(20)` | NOT NULL, CHECK in (`manual`, `employer_file`, `customer_portal`, `chatbot`) | Inkommande kanal; `manual` för handläggarens registrering `employer_file` för ärenden ur en godkänd eller avslagen löneunderlagsfil (paket A steg 2) och `system` för ärenden som betrodd bevakning upptäcker (steg 3); övriga reserverade (delprojekt 3 och 7) |
| `received_date` | `DATE` | NOT NULL | Mottagningsdag (PR-ITP1-031) |
| `source_reference` | `VARCHAR(100)` | NULL | Avsändarens referens, t.ex. lönefilens id |
| `due_date` | `DATE` | NULL | Tidsfrist, t.ex. för klagomål (PR-ITP1-030); ingen för löneunderlag i v1 |
| `details` | `JSONB` | NOT NULL | Typens uppgifter, validerade mot en Pydantic-modell per typ i tjänstelagret (B-033 val F). För `salary_report`: rapporterad lön, källa, `kind` och ev. `corrects_version`. För `salary_file_deviation`: skälkod, meddelande, filens id och referens, radnummer och den rapporterade raden. För `payment_overdue`: fakturanummer, OCR, förfallodag, öppet belopp, dagar och eskalering. För `payment_unmatched`: bankhändelsen, belopp, oallokerat belopp, skäl, angiven referens, betalare och ev. faktura |
| `assigned_to` | `VARCHAR(100)` | NULL | Handläggaren som äger ärendet |
| `last_run_id` | `VARCHAR(100)` | NULL | Senaste agentkörningen; journal i `logs/agent_runs/<run_id>.jsonl` |
| `created_by` | `VARCHAR(100)` | NOT NULL | Den som registrerade ärendet |
| `closed_by` / `closed_at` | `VARCHAR(100)` / `TIMESTAMPTZ` | NULL | Satta exakt när ärendet är stängt |
| `closing_note` | `TEXT` | NULL | Anteckning vid stängning; krävs vid `rejected` och `manual_review` |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

**Integritet:**
- Unikt `case_number`
- CHECK: minst en av `insured_person_id` och `employer_id` – ett ärende gäller någon. Undantag: `payment_unmatched`, där betalaren kan vara okänd (paket A steg 4; byts i Lakebase av premieflödets migration, §12), och `company_capital`, som gäller bolaget (paket B steg 5, inte infört). Kanalen `system` (steg 3) byts i samma migration
- CHECK: stängt ärende har `outcome`, `closed_by` och `closed_at`; öppet ärende har inga av dem
- CHECK: `rejected` och `manual_review` har `closing_note` – avslag och manuell prövning motiveras (PR-ITP1-031)
- CHECK: `period_month` är första dagen i månaden (Postgres- och SQLite-variant, §12)
- Index på `status`, `case_type` och `insured_person_id`

**Skrivs av** tjänstelagrets ärendeoperationer (F5-2): `create_case`, `update_case_status` och `close_case` (`HUMAN_ONLY`; harness skriver status efter en körning som systemaktör). Filintagets ärenden skapas av betrodd kod i `approve_salary_file` och `reject_salary_file`, i samma transaktion, med `created_by = salary_file_intake`, bevakningens ärenden i `check_overdue_invoices` med `created_by = invoice_monitor` och matchningens ärenden i `import_bank_file` med `created_by = payment_matching` (P1-PREMIE-001 §6). **Läses av** `list_cases` (`HUMAN_ONLY`) och `get_case` (`AGENT`, bara körningens ärende). Agenten kan inte skapa, ändra eller stänga ärenden.

**Personuppgifter:** `details` kan innehålla lön och fri text (B-006). Gallring följer PR-ITP1-031 och beslutas i tjänstelagerprojektets lagringspolicy.

---

## 9h. Tabell: `product_parameters` – Produktparametrar som versionerad data

**Domän:** Parametrar som styr premieberäkningen och kapitalavräkningen, i versioner med giltighetsintervall (Fas 3c, B-035; kapitalets nycklar A5). En regeländring som bara ändrar ett värde – t.ex. premieåldern – kan därmed nå produktion som en ny version, utan kodändring. Premiemotorn tar parametrarna som indata (`PremiumParameters`); tjänstelagret slår upp versionen som gäller premiemånaden (`services/parameters.py`) och sparar versionerna i `calculation_basis` (`parameters`, `age_window`). Följer parameterregistrets avsnitt *Parameterändring*: värde, enhet, giltighet, källa och beslut.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | |
| `key` | `VARCHAR(60)` | NOT NULL, CHECK | `premium_age_start`, `premium_age_end`, `premium_rate_low`, `premium_rate_high`, `premium_breakpoint_low_ibb`, `premium_breakpoint_high_ibb`, `capital_fee_rate` (PR-ITP1-022), `customer_tax_rate` (PR-ITP1-023) |
| `value` | `NUMERIC(12,6)` | NOT NULL, CHECK ≥ 0 | Värdet i parameterns enhet; åldrar måste vara hela år (kontrolleras vid uppslag) |
| `unit` | `VARCHAR(20)` | NOT NULL, CHECK | `years`, `rate` eller `ibb` |
| `valid_from` | `DATE` | NOT NULL, CHECK månadsförsta | Första månad som omfattas (premiemånad respektive kapitalets avräkningsmånad) |
| `valid_to` | `DATE` | NULL, CHECK ≥ `valid_from` | Sista dag; NULL = tills vidare |
| `rule_id` / `rule_version` | `VARCHAR(20)` / `VARCHAR(10)` | NOT NULL | Produktregeln som bär värdet, t.ex. `PR-ITP1-013` `1.0` |
| `source_ref` | `VARCHAR(60)` | NOT NULL | Källa i källregistret, t.ex. `K-ITP-FIL` |
| `decision_ref` | `VARCHAR(60)` | NOT NULL | Beslutet – B-nummer, flödets grindbeslut eller `B-035 startvärden` |
| `status` | `VARCHAR(20)` | NOT NULL, CHECK | `valid` eller `withdrawn`. Om en version är kommande, gällande eller upphörd härleds av datumen |
| `created_by` | `VARCHAR(100)` | NOT NULL | Aktören som lade versionen |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL | Standardtidsstämplar |

Unikt på `(key, valid_from)`, index på `key`. Två giltiga versioner av samma nyckel samma dag stoppar beräkningen (`BlockedError`) i stället för att en väljs tyst; en saknad parameter för månaden stoppar beräkningen (`NotFoundError`). Överlappskontrollen görs av skrivoperationerna: en ny version avslutar den föregående dagen före, och bara en kommande version per parameter är tillåten. En återkallad version ligger kvar, så samma giltighetsdag kan inte återanvändas.

**Startvärden från 2023-01-01** – samma som premiehistoriken 2023–2026 räknats med: premieålder 25–66 (PR-ITP1-013), satserna 4,5 och 30 % och brytpunkterna 7,5 och 30 IBB (PR-ITP1-001), `decision_ref` `B-035 startvärden`.

**Kapitalets nycklar (A5).** `capital_fee_rate` 0,002 tills vidare (B-021, PR-ITP1-022) och `customer_tax_rate` med en version per kalenderår som slutar 31 december: 0,00219 (2023), 0,00372 (2024), 0,003225 (2025) och 0,00354 (2026) ur `PARAMETERREGISTER.md` (PR-ITP1-023, källa `K-SKV-SLR`). Ett år utan version stoppar kapitalavräkningen, så att föregående års sats aldrig används automatiskt. Läses per månad av `services.parameters.capital_rates` för datautdraget S-04. `schedule_product_parameter_change` gäller bara premiernas nycklar. En ny årssats läggs in med `schedule_customer_tax_rate`, som räknar satsen ur SLR året före (2026-10-31). En ändring av kapitalavgiften kräver PR-ITP1-030:s prövning och har ingen operation.

**Läses av** `get_product_parameters` (`AGENT`, inga personuppgifter), förhandsberäkningen, premierättelsen och datautdraget S-04 (kapitalets nycklar). **Skrivs av** migrationen (startvärden), `schedule_product_parameter_change` och `schedule_customer_tax_rate` (`APPROVAL`) och `withdraw_product_parameter_change` (`HUMAN_ONLY`), med radlås på parameterns versioner (`tjänstelager.md` §9.4). Inga personuppgifter.

---

## 9i. Tabeller: `flows`, `flow_steps` och `flow_gate_decisions` – Uppdragsarkivet

> **Status:** Skrivskyddat arkiv för uppdrag från den tidigare flödesmotorn enligt B-035. Tabellerna infördes i Lakebase 2026-10-26. Befintliga tabeller läses av uppdragsarkivet och ligger utanför det schema som skapas för nya databaser.

**Domän:** sparad beställning, resultat, rapportkvitton, agenternas körjournaler och operatörens beslut. `flow_steps.run_id` pekar till JSONL-journalen i `logs/agent_runs/` och `flow_steps.approval_id` till tjänstelagrets godkännandekö.

Nya uppdrag i Fråga bolaget sparas av bolagsorkestratören i
`company_missions` i den lokala SQLite-demon. Varje rad har en beställare,
miljö, dataset och revision samt ett JSON-dokument med uppdragets tillstånd.
[Pilotens uppdragskontrakt](bolagsorkestrator_pilot.md#uppdragskontrakt-och-gränser)

### `flows`

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `flow_id` | `VARCHAR(20)` | PK, CHECK form `FLOW-NNNNNN` | Flödesnumret |
| `flow_type` | `VARCHAR(60)` | NOT NULL | Flödesdefinitionen, t.ex. `rule_change_parameter` (3c-3) |
| `definition_version` | `VARCHAR(20)` | NOT NULL | Definitionens version när flödet startades |
| `status` | `VARCHAR(30)` | NOT NULL, CHECK in (`running`, `waiting_gate`, `waiting_manual`, `waiting_approval`, `completed`, `rejected`, `cancelled`, `failed`, `reconciliation_required`) | Flödets läge |
| `input` | `JSONB` | NOT NULL | Indata, validerade mot definitionens modell |
| `current_step` | `VARCHAR(60)` | NULL | Sparad nyckel för det aktuella steget |
| `version` | `INTEGER` | NOT NULL, CHECK ≥ 1 | Sparad radversion som användes för optimistisk låsning |
| `created_by` | `VARCHAR(100)` | NOT NULL | Operatören som startade flödet |
| `finished_at` | `TIMESTAMPTZ` | NULL | Satt exakt när flödet är avslutat (`completed`, `rejected`, `cancelled`, `failed`) |
| `note` | `TEXT` | NULL | Skälet vid avslag, avbrott eller fel |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

### `flow_steps`

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Stegets interna id |
| `flow_id` | `VARCHAR(20)` | NOT NULL, FK → `flows(flow_id)` ON DELETE RESTRICT | Flödet |
| `step_key` / `position` | `VARCHAR(60)` / `INTEGER` | NOT NULL, unika per flöde, position ≥ 1 | Stegnyckeln och ordningen enligt definitionen |
| `kind` | `VARCHAR(20)` | NOT NULL, CHECK in (`agent`, `gate`, `manual`, `system`) | Stegets slag |
| `title` | `VARCHAR(200)` | NOT NULL | Stegets rubrik |
| `team` / `agent` | `VARCHAR` | NULL | Team och agent för agentsteg |
| `status` | `VARCHAR(30)` | NOT NULL, CHECK in (`pending`, `running`, `completed`, `waiting`, `rejected`, `failed`, `skipped`, `reconciliation_required`) | Stegets läge |
| `run_id` | `VARCHAR(100)` | NULL | Sparat kör-id för agentstegets journal i `logs/agent_runs/<run_id>.jsonl` |
| `result` | `JSONB` | NULL | Stegets resultat: för agentsteg körningens status och det prövade resultatschemat (`agents.results`), för grindar beslutet, för manuella steg operatörens uppgifter |
| `result_hash` | `VARCHAR(64)` | CHECK satt när steget är `completed` | sha256 av resultatet i kanonisk JSON – det grindarna binder |
| `approval_id` | `VARCHAR(64)` | NULL | Förslaget i `approval_requests` som systemsteget väntade på |
| `artifact_refs` | `JSONB` | NULL | Utkastreferenser (`utkast:<team>/<run_id>/<namn>`) |
| `started_at` / `finished_at` | `TIMESTAMPTZ` | NULL | Tider |
| `completed_by` | `VARCHAR(100)` | NULL | Operatören vid grindar och manuella steg, godkännaren vid ett förslag i kön |
| `error` | `TEXT` | NULL | Fel eller avstämningsanteckning |

### `flow_gate_decisions`

Den tidigare motorn sparade varje grindbeslut som en egen rad.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | |
| `flow_id` | `VARCHAR(20)` | NOT NULL, FK → `flows(flow_id)` | Flödet |
| `step_key` | `VARCHAR(60)` | NOT NULL | Grinden |
| `decision` | `VARCHAR(20)` | NOT NULL, CHECK in (`approved`, `rejected`) | Beslutet |
| `decided_by` | `VARCHAR(100)` | NOT NULL | Operatören |
| `note` | `TEXT` | CHECK krävs vid `rejected` | Anteckning |
| `bound_steps` | `JSONB` | NOT NULL | Stegen vars resultat beslutet gäller |
| `bound_hash` | `VARCHAR(64)` | NOT NULL | Hashen av stegens resultathashar vid beslutet |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | Beslutstiden |

**Arkivvisning:** Uppdragsarkivet visar uppdragets sparade läge, även för
uppdrag som väntade på ett steg eller beslut. Operatören kan läsa
underlag, beslut och körspår samt öppna rapportfiler som stämmer med den
sparade kontrollsumman. Äldre länkar med `FLOW-`-id öppnar samma arkiv.

**Personuppgifter:** inga. Stegens resultat är strukturerat underlag och aggregat (`agents.results`); uppdragstexterna innehåller inga personuppgifter.

---

---

## 9j. Tabell: `valuation_bases` – Antagandebiblioteket

> **Status:** Beslutad i **B-042** (val C och I), byggd lokalt i A4 2026-10-31. Migrationen `scripts/migrations/migrate_valuation_bases.py` är verifierad mot isolerad Postgres 2026-10-31 (`svc_test`): skapar tabellen och startgrunderna, kontrollsummorna håller efter JSONB, idempotent och övriga radantal oförändrade. **Skapad i Lakebase 2026-10-31** efter backup `backups/20261031T124616Z` och operatörens OK (AGENTS.md §4.5).

**Domän:** Aktuariella grunder och diskonteringskurvor som versionerad data (`VARDERINGSKONTRAKT.md` §4). Innehållet (`assumptions`) prövas mot schemat för ändamålet i `services/valuation_bases.py` och ändras aldrig efter att raden skapats. Ett förslag blir en ny rad. När en grund antas avslutas den gällande grunden i samma familj dagen före. Historiska garantigrunder bevaras (B-027).

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | |
| `code` | `VARCHAR(30)` | NOT NULL, UNIQUE | T.ex. `SIM-V-2026-01`, `FI-SIM-2026-10` |
| `family` | `VARCHAR(20)` | NOT NULL, CHECK | `SIM-G`, `SIM-HIST`, `SIM-B`, `SIM-R`, `SIM-V`, `FI-SIM` eller `AVK-SIM` (sedan A5) |
| `purpose` | `VARCHAR(20)` | NOT NULL, CHECK | `guarantee`, `payout`, `risk`, `valuation`, `discount_curve` eller `return_series` |
| `title` | `VARCHAR(200)` | NOT NULL | |
| `assumptions` | `JSONB` | NOT NULL | Antagandena i normaliserad form enligt ändamålets schema |
| `checksum` | `VARCHAR(64)` | NOT NULL, CHECK längd 64 | SHA-256 av kanonisk JSON; prövas vid läsning |
| `source_refs` | `VARCHAR(300)` | NOT NULL | Källor |
| `status` | `VARCHAR(20)` | NOT NULL, CHECK | `proposed`, `adopted` eller `rejected` |
| `valid_from` / `valid_to` | `DATE` | CHECK | Bara för antagna; `valid_to` NULL = tills vidare |
| `decision_ref` | `VARCHAR(100)` | NOT NULL om antagen | Styrelsebeslut eller B-nummer |
| `supersedes_code` | `VARCHAR(30)` | NULL | Grunden förslaget ska ersätta |
| `proposal_reason` / `review_note` | `TEXT` | | Motivering och avslagsanteckning |
| `created_by` / `created_at` / `adopted_by` / `adopted_at` | | | Aktörer och tider |

Partiellt unikt index: högst en antagen, inte avslutad grund per familj (`uq_valuation_bases_one_open`).

**Startgrunder:**
- `SIM-HIST-2023-01` gäller 2023-01-01 till 2026-10-31.
- `SIM-G-2026-01`, `SIM-B-2026-01` och `SIM-R-2026-01` gäller från 2026-11-01 (B-031).
- Den syntetiska kurvan `FI-SIM-2026-10` gäller från 2026-10-31 (B-042, A1 M1).
- `SIM-V-2026-01` gäller från 2026-12-31 (B-042, A1 M2–M5).
- `AVK-SIM-2026-01` gäller från 2023-01-01 (A5, operatörens val 2026-10-31). Det är en syntetisk varierande månadsavkastning 2023-01–2026-10 för rekonstruktionen av pensionskapitalet. Avkastningen är räknad efter direkta placeringskostnader men före avgift och skatt (PR-ITP1-021). **Införd i Lakebase 2026-10-31** genom uppgraderingen i §12, efter backup `backups/20261031T151410Z`.

**Läses av** `list_valuation_bases` och `get_valuation_basis` (`AGENT`, podden `antaganden`). **Skrivs av** migrationen (startgrunderna), `propose_valuation_basis` (`APPROVAL`, PR-ITP1-031), `adopt_valuation_basis` och `reject_valuation_basis` (`HUMAN_ONLY`), med radlås på familjens antagna grunder (`tjänstelager.md` §9.7). `agent_aktuarie` får `SELECT`. Inga personuppgifter.

## 9k. Tabeller: `valuation_extracts`, `valuation_runs` och `valuation_results` – Värderingsmotorn

> **Status:** Beslutad i **B-042** (val I och L), byggd lokalt i A6 2026-10-31. Migrationen `scripts/migrations/migrate_valuation_runs.py` är verifierad mot isolerad Postgres (`svc_test`): skapar de tre tabellerna tomma, identiska kolumner med modellerna, idempotent och övriga radantal oförändrade. **Skapade i Lakebase 2026-10-31** efter backup `backups/20261031T173353Z` och operatörens OK (AGENTS.md §4.5).

**Domän:** FTA-värderingen enligt `VARDERINGSKONTRAKT.md` §5–6. En körning räknar på ett oföränderligt datautdrag och en antagen grund och kurva, och sparar totalerna och resultatet per segment. Belopp lagras med sex decimaler (`NUMERIC(20,6)`) och avrundas till öre först i rapporteringen. Skillen beskrivs i `03_skills/beräkning/fta-vardering.md`.

### `valuation_extracts`

Datautdraget S-04 som körningen räknar på. Samma innehåll sparas en gång.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | |
| `valuation_date` | `DATE` | NOT NULL | Månadsslut |
| `source` | `VARCHAR(30)` | NOT NULL, CHECK | `reconstructed_s04` (S-04) eller `ledger` (den operativa journalen, §7c; per 2026-10-31 och varje stängd månads slut). Det ingående lägets S-04-utdrag sparas här och pekas ut av `ledger_batches.extract_id` |
| `checksum` | `VARCHAR(64)` | NOT NULL, UNIQUE, CHECK längd 64 | Utdragets SHA-256; prövas igen före lås |
| `approved` | `BOOLEAN` | NOT NULL | Kontrollerna i kontraktet §5.3 |
| `policies` / `guarantee_parts` / `capital_sek` | | NOT NULL | Antal och ΣC för översikt |
| `content` | `JSONB` | NOT NULL | Hela utdraget: per försäkring internt id, födelsemånad, läge, plan, garantidelar och kapital, samt månadssummor och kontroller. Inga personnummer eller namn |
| `created_by` / `created_at` | | NOT NULL | |

### `valuation_runs`

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | |
| `valuation_date` | `DATE` | NOT NULL | |
| `purpose` | `VARCHAR(20)` | NOT NULL, CHECK | `base` (kvartalsslut, gällande grund) eller `scenario` (märkt, aldrig bas) |
| `version` | `INTEGER` | NOT NULL, UNIQUE med datum och ändamål | 1, 2, … per datum och ändamål |
| `status` | `VARCHAR(20)` | NOT NULL, CHECK | `draft`, `locked` eller `superseded`. Ett scenario är alltid `draft` |
| `source` | `VARCHAR(30)` | NOT NULL, CHECK | Utdragets märkning, följer med till rapporter |
| `basis_code` / `basis_checksum`, `curve_code` / `curve_checksum` | | NOT NULL | Värderingsgrund (SIM-V) och kurva (FI-SIM) med kontrollsummor |
| `tax_reduction` / `tax_parameter` | `NUMERIC(10,6)` / `VARCHAR(100)` | NOT NULL | s_y och versionen av `customer_tax_rate` |
| `extract_id` / `extract_checksum` | | NOT NULL, FK | Utdraget |
| `code_version` | `VARCHAR(60)` | NOT NULL | Motorns version och hash av källkoden, t.ex. `fta-1.0+…` |
| `result_checksum` | `VARCHAR(64)` | NOT NULL | SHA-256 av resultatet per försäkring och totalerna (kontrollfall K6) |
| `policies`, `capital_sek`, `guarantee_sek_per_month`, `fta_sek`, `expenses_sek`, `surplus_sek`, `deficit_sek` | | NOT NULL | Totaler: antal, ΣC, ΣG, FTA, därav K, VÅ och U |
| `not_calculated` | `JSONB` | NOT NULL | Ej beräknade fall per orsak, med småcellsskydd |
| `checks` / `checks_passed` | `JSONB` / `BOOLEAN` | NOT NULL | Utdraget godkänt, K1, K10 och antal |
| `note` | `TEXT` | NOT NULL | Motiveringen vid körningen |
| `created_by` / `created_at` | | NOT NULL | |
| `locked_by` / `locked_at` / `lock_note` | | NOT NULL om inte `draft` | Vem som låste, när och varför |
| `supersedes_id` | `UUID` | FK till `valuation_runs` | Den låsta körning som en rättelse ersatte |

Partiellt unikt index: högst en låst körning per datum (`uq_valuation_runs_one_locked`). Villkoret `ck_valuation_runs_scenario_never_locked` hindrar att ett scenario låses.

### `valuation_results`

Ett segment per läge och födelsedecennium (`UNIQUE (run_id, state, cohort)`). Celler med 1–9 försäkringar döljs, med kompletterande döljning mot totalen, och sparas utan antal och belopp, bara med `hidden_reason` (CHECK `ck_valuation_results_hidden`). Beloppen är `capital_sek`, `fta_sek`, `expenses_sek`, `surplus_sek` och `deficit_sek`.

**Skrivs av** `run_valuation` (`APPROVAL`, PR-ITP1-028 och PR-ITP1-031; systemsteg eller människa) och `lock_valuation` (`HUMAN_ONLY`, granskningssumma och transaktionsbundet datumlås före radlås på körningen och datumets låsta körning; `tjänstelager.md` §9.8). **Läses av** `list_valuation_runs` och `get_valuation_run` (`AGENT`, podden `aktuariell`), som aldrig läser `valuation_extracts`. `agent_aktuarie` får `SELECT` på `valuation_runs` och `valuation_results`, men ingen rättighet på `valuation_extracts` (`tjänstelager.md` §9.8).

## 9l. Aktuariedialog, erfarenhetsunderlag och analysleveranser

Modeller: `src/models/actuarial_workspace.py`. Gemensamt schema för lokal SQLite
 och Lakebase/Postgres. [Drift och kontrakt](aktuarie_dialog.md).

| Tabell | Nyckel och innehåll | Kontroller |
|---|---|---|
| `actuarial_datasets` | Versions-id, typ, titel, källbundet JSON-underlag, SHA-256, skapare och datum | Typade observationsceller; ingen överskrivning genom tjänsten; import HUMAN_ONLY |
| `actuarial_conversations` | Dialog-id, titel, operatör och datum | Dialogåtkomst binds till verifierad operatör |
| `actuarial_turns` | Körnings-id, dialog-FK, beställningsnyckel, meddelande, status, revision, körreferens och resultat | Unik beställning per dialog; högst en köad/pågående körning per dialog; kontrollerade statusvärden |
| `actuarial_analyses` | Leverans-id, dialog-FK, körreferens, typ, titel, kontrollerat innehåll och SHA-256 | Underlag, analys, diagram, rapport och förslagsjournal binds till dialogen; läsning kontrollerar innehållet |

Tabellerna skrivs av den betrodda dialogadaptern/systemarbetaren. Agentens
begränsade databasroll får inga nya rättigheter. Individutdragen är fortsatt
stängda för agenten. Migration: `scripts/migrations/migrate_actuarial_workspace.py`,
torrkörning som standard och backupkrav vid skarp körning. Införd i Lakebase
2026-11-03 efter backup `backups/20261103T203424Z` och operatörens OK: fyra tomma
tabeller, radantalen i övriga 22 tabeller oförändrade och en andra körning gjorde
ingenting. Erfarenhetsdata importeras separat, aldrig från fabricerade modellutfall.

## 10. Datakvalitet och valideringar

**På applikationsnivå (Python/SQLAlchemy):**
- `org_number` – Luhn-kontroll (10 siffror, sista siffran är kontrollsiffra) – kontrolleras vid `register_employer`
- `personal_id_number` – Luhn-kontroll och datumvalidering – kontrolleras vid `enroll_insured_person` (befintlig genererad data valideras inte i efterhand)
- `affiliation_date` ≤ idag
- `employment_start_date` ≤ `employment_end_date` (om båda satta)
- `itp1_start_date` ≥ datum när personen fyllde 25 (ITP-avtalets §4)
- `policies.start_date` ≥ den försäkrades `itp1_start_date` (om satt)
- `policy_states`: perioder för samma försäkring får inte överlappa (appnivå, se §6)
- `premium_transactions.period_month` inom förmånens aktiva period
- `premium`-transaktioner: `amount_sek` ska vara reproducerbar ur `pensionable_salary_sek` + `calculation_basis` (kontrolleras av `correct_premium_transaction` innan en rad rättas)
- `salary_reports`: månaden inom anställningen hos rapporterande arbetsgivare och inom ITP1-tillhörigheten, inte i framtiden, mottagningsdatum mellan rapportmånadens början och idag (`register_salary_report`)

**På databasnivå (CHECK):**
- `status`-fältens enumvärden
- `employment_rate` mellan 0 och 100
- `monthly_salary_sek` ≥ 0

---

## 11. Säkerhet och behörigheter

- **Tabellen `insured_persons` är PII-bärande** (B-006). Skills som läser/skriver mot den ska deklareras med behörighetslista.
- **Maskning vid analys:** Data scientist-agenten arbetar mot anonymiserade vyer eller aggregat, inte rå PII.
- **Databasroller och radnivåsäkerhet:** `app_backend` (Lakebase, B-018) äger tabellerna och används av handläggar-UI:t, skripten och provkörningen av agentförslag. Försäkringsagenten ansluter med den begränsade rollen `agent_forsakring` (2026-10-24, `harness.md` §5.1): SELECT på försäkringstabellerna och `cases` (Fas 5, verkställt i Lakebase 2026-10-24) samt `product_parameters` (B-035, verkställt i Lakebase 2026-10-25), INSERT på `approval_requests` och `operation_events` (plus SELECT på deras `created_at`/`updated_at` för INSERT … RETURNING), ingen UPDATE/DELETE och inga kapitaltabeller. Rättigheterna står i `src/utils/agent_roles.py`. Kundscope verkställs i harness (`src/agents/scope.py`); radnivåsäkerhet används inte ännu.

---

## 12. Migrationer och versionering

- **Alembic** är planerat men inte uppsatt. Befintliga ändringar görs med riktade, kontrollerade migrationsskript i `scripts/migrations/`, se verifieringarna nedan.
- Grundtabellerna skapades med `Base.metadata.create_all`. Lokala testdatabaser använder fortfarande `create_all`; det uppdaterar inte befintliga tabeller och ska inte användas som generell Lakebase-migration.
- **Ändringar i schemat** dokumenteras här och får ett migrationssteg med torrkörning, förutsättningskontroller och verifiering. Körning mot delad Lakebase kräver backup och samordning enligt AGENTS.md §4.5.
- **Fas 1f T3 (2026-10-11) – första ändringen av en befintlig tabell:** gjord med ett kontrollerat migrationsskript, `scripts/migrations/migrate_t3_schema.py`, i stället för Alembic (som skulle kräva ett nytt beroende – föreslaget som eget steg). Skriptet skapar `salary_reports` och lägger till `premium_transactions.corrects_transaction_id` med sin CHECK och sitt index i **en** transaktion (Postgres-DDL är transaktionell), kontrollerar förutsättningarna först, visar SQL med `--dry-run`, ändrar inga befintliga rader och verifierar radantalen efteråt. Verifierat 2026-10-11 mot en isolerad Postgres 17 (`svc_test`): migrationen från det gamla schemat med data ger samma kolumner, constraints och index som `create_all`, är idempotent och lämnar radantalen oförändrade (`tests/test_services_postgres.py`). Körs mot Lakebase först efter backup (`scripts/maintenance/backup_database.py`) och avstämning enligt AGENTS.md §4.5. `create_all` används inte för den befintliga tabellen. **Ordning:** migrationen är bakåtkompatibel (äldre kod påverkas inte), men koden från Fas 1f T3 läser `corrects_transaction_id` – migrationen ska därför vara körd innan den koden används mot Lakebase. Migrerat i Lakebase 2026-10-11 efter backup `backups/20261011T151353Z` och dry-run; radantalen oförändrade (15 097 premietransaktioner), en andra körning gjorde ingenting
- **Portabla modeller för tester (2026-10-11):** modellerna kan även skapas i en SQLite-databas i minnet, så att tjänstelagret (B-028) testas utan att röra Lakebase. JSON-kolumner är `JSON` med `JSONB`-variant för Postgres, de partiella unika indexen har även `sqlite_where`, och kontrollen att `period_month` är den första i månaden finns i en Postgres- och en SQLite-variant (`ddl_if`). Postgres-DDL:en är verifierat identisk före och efter ändringen – Lakebase påverkas inte och ingen migration behövs. Testdatabasen byggs i `tests/conftest.py` (`insurance_db`). UUID-kolumnerna blir `CHAR(32)` i SQLite (`models/base.py`, 2026-10-25): typnamnet `UUID` gav NUMERIC-affinitet, så en hexform med bara siffror lagrades som tal och kunde inte läsas tillbaka – orsaken till de enstaka slumpvisa felen i testsviten (`tests/test_models_uuid.py`). En befintlig demofil (`data/handlaggare_demo.db`) behåller sina gamla kolumntyper tills den skapas om.
- **Fas 5 F5-1 (2026-10-24) – tabellen `cases` (§9g, B-033):** skapas med `scripts/migrations/migrate_cases.py` (`utils/migration_cases.py`), inte `create_all` – den skulle även skapa kapitalförvaltningens tabeller, som inte finns i Lakebase. Skriptet skapar bara `cases` och dess index i en transaktion, kontrollerar att de refererade tabellerna finns, torrkör som standard och kräver `--apply` och `--backup` för en skarp körning, ändrar inga befintliga rader och verifierar radantalen. Verifierat mot isolerad Postgres (`svc_test`, `tests/test_migration_cases.py`): resultatet är identiskt med `create_all`, idempotent och lämnar övriga tabeller orörda. Villkoret för ärendenumret använder `SUBSTR` i stället för `LIKE 'CASE-%'`, eftersom procenttecknet dubbleras när DDL:en kompileras för psycopg2. `details` sparar Pythons `None` som SQL `NULL` (`none_as_null`), så att `NOT NULL` gäller. **Skapad i Lakebase 2026-10-24 efter backup `backups/20261024T191154Z` och torrkörning, med operatörens OK (AGENTS.md §4.5); radantalen i övriga tabeller oförändrade**. Agentrollens läsrätt på `cases` sattes därefter med `grant_agent_role.py --apply`
- **Fas 3c 3c-P1 (2026-10-25) – tabellen `product_parameters` (§9h, B-035):** skapas med `scripts/migrations/migrate_product_parameters.py` (`utils/migration_product_parameters.py`) enligt samma mönster som `cases`: bara den nya tabellen och dess index, en transaktion, torrkörning som standard, `--apply` kräver `--backup`, radantalen kontrolleras. Migrationen lägger dessutom in startvärdena och **räknar om varje ordinarie premierad** med de lästa parametrarna – minsta avvikelse rullar tillbaka allt. Även torrkörningen gör kontrollen, i en transaktion som rullas tillbaka. Verifierat mot isolerad Postgres (`tests/test_product_parameters.py`): demobeståndet räknas om identiskt, idempotent, och en ändrad premie stoppar migrationen. Tills tabellen finns används paketets värden i koden, märkt i `calculation_basis`. **Uppgradering (A5):** finns tabellen byter samma skript villkoret för nycklar till modellens och lägger in startvärden som saknas (nyckel och giltighetsdag); premierna räknas om på samma sätt. Verifierat mot isolerad Postgres 2026-10-31 från 3c-P1-läget. **Körd mot Lakebase 2026-10-31** efter backup `backups/20261031T172901Z` och torrkörning, med operatörens OK: villkoret för nycklar bytt, fem startvärden inlagda (`capital_fee_rate` och `customer_tax_rate` för 2023–2026), alla 15 097 premier omräknade identiskt, radantalen i övriga tabeller oförändrade och en andra körning gjorde ingenting. Rollernas rättigheter behövde inte ändras (SELECT på hela tabellen). **Ordning i Lakebase:** backup → torrkörning → `--apply` → `grant_agent_role.py --apply` (agentrollen får `SELECT` på tabellen). **Skapad i Lakebase 2026-10-25 efter backup `backups/20261025T090949Z` och torrkörning, med operatörens OK (AGENTS.md §4.5): alla 15 097 premier räknades om identiskt, radantalen i övriga tabeller oförändrade, en andra körning gjorde ingenting; agentrollens läsrätt sattes därefter med `grant_agent_role.py --apply`**
- **Fas 3c 3c-2 (2026-10-25) – historiska uppdragstabeller (§9i, B-035):** migrationen infördes i Lakebase 2026-10-26. Tabellerna används nu för arkivläsning där de redan finns.
- **A4 (2026-10-31) – tabellen `valuation_bases` (§9j, B-042):** skapas med `scripts/migrations/migrate_valuation_bases.py` (`utils/migration_valuation_bases.py`) enligt samma mönster:
  - bara den nya tabellen och dess index, i en transaktion;
  - torrkörning som standard, och `--apply` kräver `--backup`;
  - radantalen kontrolleras före och efter.

  Migrationen lägger in startgrunderna och prövar varje kontrollsumma. Minsta avvikelse rullar tillbaka allt. Verifierat mot isolerad Postgres 2026-10-31 (`tests/test_valuation_bases.py`). **Ordning i Lakebase:** backup → torrkörning → `--apply` → `grant_agent_role.py --team aktuarie --apply`. **Körd mot Lakebase 2026-10-31** efter backup `backups/20261031T124616Z` och torrkörning, med operatörens OK: tabellen och de sex startgrunderna skapade, radantalen i övriga tabeller oförändrade och en andra körning gjorde ingenting. Därefter sattes `agent_aktuarie`s rättigheter, också OC-3a:s kolumnrätter (B-041). Verifierat med rollens egen anslutning: läser grunderna och kontrollsummorna stämmer; nekas UPDATE, DELETE och INSERT på tabellen
- **A5 (2026-10-31) – uppgradering av `valuation_bases`:** samma skript, `migrate_valuation_bases.py`, uppgraderar en befintlig tabell. Villkoren för familj och ändamål byts till modellens (familjen `AVK-SIM`, ändamålet `return_series`) och startgrunder som saknas läggs in. Befintliga grunder ändras inte. Allt sker i en transaktion med torrkörning som standard, kontroll av kontrollsummor och radantal, och skriptet är idempotent. Verifierat mot isolerad Postgres 2026-10-31 från A4-läget, där båda villkoren saknar de nya värdena. **Körd mot Lakebase 2026-10-31** efter backup `backups/20261031T151410Z` och torrkörning, med operatörens OK: villkoren för familj och ändamål bytta, `AVK-SIM-2026-01` inlagd, radantalen i övriga tabeller oförändrade och en andra körning gjorde ingenting. Rättigheterna behövde inte ändras (SELECT på hela tabellen). Verifierat med `agent_aktuarie`s anslutning: läser alla sju grunderna och kontrollsummorna stämmer; nekas UPDATE
- **A6 (2026-10-31) – värderingsmotorns tabeller (§9k, B-042):** skapas med `scripts/migrations/migrate_valuation_runs.py` (`utils/migration_valuation_runs.py`) enligt samma mönster: bara `valuation_extracts`, `valuation_runs` och `valuation_results` med index, tomma, i en transaktion; torrkörning som standard, `--apply` kräver `--backup`, radantalen i övriga tabeller kontrolleras. `valuation_bases` ska finnas. Finns bara en del av tabellerna stoppar migrationen. Verifierat mot isolerad Postgres 2026-10-31 (`tests/test_valuation_runs.py`). **Ordning i Lakebase:** uppgraderingen av `product_parameters` (A5, kapitalets nycklar) först, eftersom värderingen läser skatteavdraget där (införd 2026-10-31); sedan backup → torrkörning → `--apply` → `grant_agent_role.py --team aktuarie --apply`. **Körd mot Lakebase 2026-10-31** efter backup `backups/20261031T173353Z` och torrkörning, med operatörens OK: de tre tabellerna och två index skapade tomma, radantalen i övriga 19 tabeller oförändrade och en andra körning gjorde ingenting. Därefter fick `agent_aktuarie` SELECT på `valuation_runs` och `valuation_results`. Verifierat med rollens egen anslutning: `list_valuation_runs` och läsning av båda tabellerna fungerar; SELECT på `valuation_extracts` samt INSERT, UPDATE och DELETE nekas
- **Paket A steg 8 (2026-11-08) – premieflödet (§8c–8e, §9g, B-046, P1-PREMIE-001 §11):** införs med `scripts/migrations/migrate_premium_flow.py` (`utils/migration_premium_flow.py`) i **en** transaktion: `salary_files`, `invoices`, `invoice_lines`, `bank_events` och `payment_allocations` skapas tomma med index och villkor, och tre CHECK-villkor på `cases` byts mot modellens – `ck_cases_type` (ärendetyperna `salary_file_deviation`, `payment_overdue`, `payment_unmatched`), `ck_cases_channel` (kanalen `system`) och `ck_cases_subject` (`payment_unmatched` får sakna försäkrad och arbetsgivare). Villkoren vidgas bara, så befintliga ärenden uppfyller dem. Tabellerna och villkoren förs in tillsammans, eftersom handläggarsidan slutar visa notisen om saknade tabeller när tabellerna finns. `premium_transactions` ändras inte. Torrkörningen är standard och körs i en `READ ONLY`-transaktion; den visar SQL, villkorens nuvarande definitioner, schemaskillnader mellan modellerna och databasens befintliga tabeller (kolumner, typer, CHECK-namn och index) och hinder, t.ex. standardrättigheter som skulle ge en agentroll åtkomst. `--apply` kräver `--backup`. Den skarpa körningen kontrollerar i samma transaktion modellens kolumner, de bytta villkoren, tomma tabeller, oförändrade radantal och att ingen agentroll har rättigheter på de nya tabellerna; minsta avvikelse rullar tillbaka allt. Delvis infört stoppar. Verifierat mot isolerad Postgres 2026-11-08 (`tests/test_migration_premium_flow.py`): från Lakebase-läget med villkoren från F5-1 blir de fem tabellerna och `cases` identiska med `create_all`, idempotent, och ett `payment_unmatched`-ärende utan försäkrad och arbetsgivare nekas före och godtas efter. Premiekedjan körd på ett migrerat schema med `smoke_test_premium_chain.py --db svc_test_migrerad`: 26 av 26 kontroller, och bara kedjans tabeller ändrades. **Torrkörd mot Lakebase 2026-11-08** efter backup `backups/20261108T075712Z`: 24 satser, de tre villkoren i F5-1:s form, inga schemaskillnader, inga hinder, radantalen i 29 tabeller lästa (bl.a. 15 097 premietransaktioner och 8 ärenden). **Införd i Lakebase 2026-11-08** efter Karls separata OK (§11 punkt 2) och samordning enligt AGENTS.md §4.5 (inga andra klientanslutningar, radantalen lika med backupen): 24 satser i en transaktion. Kontrollerat efteråt med bara läsning: de fem tabellerna finns och är tomma, inga gamla villkor kvar, ingen schemaskillnad mot modellerna för de fem tabellerna och `cases`, inga rättigheter eller standardrättigheter för `agent_forsakring`, `agent_aktuarie` och `agent_compliance`, radantalen i de 29 befintliga tabellerna lika med backupen, och en ny torrkörning ger `already_applied`. **Första operativa perioden 2026-10 (punkt 3), filintag och fakturering, 2026-11-08** efter ytterligare OK: SvenskIndustries AB #02 (en saknad rad, en nolla, en okänd person) och TeknikNorden AB #01 (utan avvikelser), verklig kalender, simulatorns seed 2026, backup `backups/20261108T094751Z`. Två filer godkända, 28 löneunderlag och 28 premierader, fakturorna INV-000001 (30 724,48 kr) och INV-000002 (36 261,66 kr) daterade 2026-11-08 med förfallodag 2026-12-08, och två öppna ärenden `salary_file_deviation` (CASE-000009 okänd person, CASE-000010 saknad rapport). Bara kedjans tabeller ändrades. Skrivskyddad kontroll av §7: 31 av 31 (fall 1–7 och 18 samt spårbarhet, fakturasummor, förfallodag och OCR). **Bankdelen (fall 12, 13 och 15), 2026-11-14** efter Karls OK: backup `backups/20261114T085221Z`, simulatorns seed 2026 och bankdag 2026-11-09, dagen efter fakturadagen. SvenskIndustries delbetalade hälften, 15 362,24 kr; lika mycket står kvar som öppen fordran och de tolv premieraderna förblir `invoiced` (fall 12). TeknikNorden betalade 36 261,66 kr två gånger; fakturan är betald, de 15 premieraderna är `paid` med betalningsdag 2026-11-09 och den andra betalningen ligger på avstämningskontot med ärendet CASE-000011 `payment_unmatched` (fall 13). Samma händelser igen, i samma fil och i en andra fil med egen referens, gav inga nya händelser eller allokeringar (fall 15). Skrivskyddad kontroll: 18 av 18, med inbetalt 87 885,56 kr = fördelat 51 623,90 kr + avstämningskonto 36 261,66 kr och fakturerat − fördelat = 15 362,24 kr i öppna fordringar. Bara `bank_events`, `payment_allocations`, `cases` och `operation_events` fick fler rader. Fall 14 är verifierat lokalt men inte kört i Lakebase. CASE-000011 står öppet hos handläggaren; återbetalning ingår inte i första versionen (PA5). Körskripten för perioden finns i `scripts/simulation/period_2026_10/`. Förfallobevakningen (fall 17) kräver verkliga datum efter förfallodagen, tidigast 2026-12-09; fall 8–11, 14, 16, 19 och 20 är verifierade i `svc_test` men inte körda i Lakebase. **Kolumnerna i `premium_transactions`** (designstoppet §5): inte införda, godkänt av Karl 2026-11-08: fakturaraden pekar redan på premieraden och löneunderlaget står i `calculation_basis`. **Ärendena CASE-000009–000010, 2026-11-14,** efter Karls OK, backup `backups/20261114T091438Z` och kontroll att inga andra klienter var anslutna: SvenskIndustries kompletterande fil `SIM1-5553972661-202610-S2026-K1` har exakt den saknade raden (lön 30 936,00 kr). Den godkändes, och premien 1 392,12 kr fakturerades på INV-000003 med förfallodag 2026-12-14. Intag, godkännande och fakturering är gjorda med ärendenumret, och CASE-000010 är stängt som `approved`. CASE-000009 (okänd person) är stängt som `no_action`, eftersom raden aldrig registrerades. Skrivskyddad kontroll: 15 av 15. Avstämningen går fortfarande ihop: inbetalt 87 885,56 kr är oförändrat och öppna fordringar är 16 754,36 kr (resten av INV-000001 plus INV-000003).

- **Paket B steg 1 (2026-11-14) – uttagsdelar och tre förlopp (§6, §7b, §9g, B-047, P1-PENSION-001 §4):** införs med `scripts/migrations/migrate_payout_parts.py` (`utils/migration_payout_parts.py`) i **en** transaktion:
  1. `payout_parts` och `payout_part_states` skapas med index och villkor, och `ck_cases_type` vidgas med `payout_reconstruction`;
  2. övergången (`services/payout_transition.py`) ger varje ålderspensionsförmån uttagsdel 1 i läget `not_started` från förmånens start – utan ekonomisk effekt – och flyttar eventuella `in_payout`- och `payout_paused`-rader till delen (som `in_payout` och `paused`) med ett rekonstruktionsärende per uttag. Premieförloppet behåller sina rader: ett fribrev före uttaget öppnas igen, och ett premiebetalande läge som slutar samma dag som den registrerade anställningen följs av `paid_up` dagen efter. Mönster som inte går att flytta entydigt (`terminated`, uttagslägen som inte ligger sist, glapp, flera ålderspensionsförmåner) stoppar migrationen;
  3. sist smalnas `ck_policy_states_state` till `premium_paying` och `paid_up`.

  Torrkörningen är standard och körs `READ ONLY`; den visar SQL, villkorens nuvarande definitioner, övergångens plan, schemaskillnader, hinder och radantal. `--apply` kräver `--backup`. Den skarpa körningen kontrollerar modellens kolumner, de bytta villkoren, exakt del 1 med ett öppet läge per förmån, att inga gamla uttagslägen finns kvar, att radantalen i övriga tabeller är oförändrade – utom `policy_states` och `cases` med exakt övergångens rörelser – och att ingen agentroll har rättigheter på de nya tabellerna – läsrätten enligt B-048 sätts därefter med `grant_agent_role.py`. Minsta avvikelse rullar tillbaka allt. Idempotent; delvis infört stoppar. Verifierat mot isolerad Postgres (`tests/test_migration_payout_parts.py`): från Lakebase-läget före steg 1 blir de två tabellerna, `cases` och `policy_states` identiska med `create_all`, och ett gammalt uttagsläge flyttas med rekonstruktionsärende. I Lakebase finns inga uttagslägen, så där skapas bara delarna. Demo- och testdatabaser får samma övergång genom `add_missing_demo_tables`; David Dahl i demon har uttaget på del 1 och ett öppet rekonstruktionsärende. **Ordning:** migrationen ska vara körd innan koden från steg 1 används mot Lakebase, eftersom läsningarna och premieunderlaget läser uttagsdelarna. **Införd i Lakebase 2026-11-14** efter backup `backups/20261114T150341Z`, torrkörning och Karls OK, med samordning enligt AGENTS.md §4.5 (inga andra klientanslutningar, arbetarens schema inte igång). Torrkörningen gav 10 satser, de två villkoren i paket A:s respektive B-022:s form, 499 ålderspensionsförmåner som får del 1, 0 uttag att flytta, inga schemaskillnader och inga hinder. `--apply` gick igenom med alla kontroller i transaktionen. Kontrollerat efteråt med bara läsning (`scripts/simulation/paket_b_steg1/verify.py`, 8 av 8): tabellerna och villkoren stämmer, exakt 499 delar nr 1 med andel 1 och ett öppet `not_started` från förmånens start, inga gamla uttagslägen, inga nya ärenden, radantalen i backupens 34 tabeller oförändrade (bl.a. 527 lägen, 15 126 premietransaktioner, 11 ärenden), och en ny torrkörning ger `already_applied`. Därefter fick `agent_forsakring` och `agent_aktuarie` SELECT på båda tabellerna med `grant_agent_role.py` (torrkörning först; enda tillägget mot tidigare rättigheter, kolumnrätterna oförändrade, B-048). Verifierat med rollernas egna anslutningar (`verify.py --grants`, 16 av 16): båda läser tabellerna och läsningarnas fråga `parts_by_policy` för alla 499 försäkringar; INSERT, UPDATE och DELETE nekas; `agent_compliance` nekas SELECT. Inga loggrader eller andra data skrevs.

- **Paket B steg 2 (2026-11-14) – kapital- och garantijournalen (§7c, B-047, P1-PENSION-001 §6):** införs med `scripts/migrations/migrate_capital_ledger.py` (`utils/migration_capital_ledger.py`) i **en** transaktion.
  - **Vad den gör:** skapar `ledger_batches`, `ledger_guarantee_parts`, `ledger_capital_entries` och `ledger_controls` tomma, med index och villkor. Inga befintliga tabeller, villkor eller rader ändras.
  - **Förutsättningar:** uttagsdelarna (steg 1), premieflödet (paket A) och `valuation_extracts` (A6) ska finnas.
  - **Torrkörning** är standard och körs `READ ONLY`. Den visar SQL, schemaskillnader i befintliga tabeller, hinder (bl.a. standardrättigheter som skulle ge en agentroll åtkomst) och radantal.
  - **Skarp körning:** `--apply` kräver `--backup`. Körningen kontrollerar i samma transaktion modellens kolumner, att tabellerna är tomma, att radantalen i övriga tabeller är oförändrade och att ingen agentroll har rättigheter på tabellerna. Minsta avvikelse rullar tillbaka allt.
  - **Idempotent:** är allt infört görs ingenting; är bara en del infört stoppar migrationen.
  - **Verifierat** mot isolerad Postgres (`tests/test_migration_capital_ledger.py`): från Lakebase-läget efter steg 1 blir de fyra tabellerna identiska med `create_all`. Övergången från S-04 är också provad där, med låset.
  - **Övergången är ett eget ingrepp efter migrationen** (designstoppet §12 punkt 3): `scripts/simulation/paket_b_steg2/open_ledger.py` granskar som standard och bokar med `--apply --backup --reviewed-checksum` genom operationen `open_capital_ledger`. `verify.py` i samma mapp kontrollerar fall 36 och 37 skrivskyddat.
  - **På en återställd kopia av backupen `backups/20261114T150341Z`** gav S-04 per 2026-10-31 den frysta hashen `023946…3fefa`. Övergången bevarade 492 försäkringar och 15 097 garantidelar, med C 42 087 223,57 kr och G 119 195,6502916268 kr/mån exakt per försäkring. Sju försäkringar ligger utanför populationen. A6 med källan `ledger` gav samma FTA, VÅ och U som S-04, och `verify.py` gav 15 av 15.
  - **Ordning i Lakebase:** backup → torrkörning → `--apply` → `open_ledger.py` (granskning) → `open_ledger.py --apply` → `verify.py --backup`. Varje skarpt steg kräver Karls separata OK och samordning enligt AGENTS.md §4.5.
  - **Kodens beroende:** koden fungerar utan tabellerna. Värderingen och P6-MANAD-001 läser då S-04 som förut, och journalens operationer blockeras med hänvisning till migrationen.
  - **Införd i Lakebase 2026-11-15** efter backup `backups/20261114T231325Z` (36 tabeller), med Karls OK för varje skarpt steg:
    - **Torrkörningen** visade de fyra tabellerna med index och villkor. Den visade inga schemaskillnader och inga hinder.
    - **`--apply`** gick igenom med radantalen i övriga tabeller oförändrade. En ny torrkörning ger `already_applied`.
    - **Granskningen** (`open_ledger.py`, `READ ONLY`) gav nio av nio kontroller och den frysta S-04-hashen `023946…3fefa`. Granskningssumman var `d209f58c…02b50`. Den skiljer sig från kopians, eftersom uttagsdelarna har andra id i Lakebase; beloppen är identiska.
    - **Bokningen** gav verifikationen `f42b3e82-4e0a-596d-9c9e-0f5bedffc049`: 492 försäkringar och 15 097 garantidelar och kapitalspår, C 42 087 223,57 kr och G 119 195,6502916268 kr/mån. Sju försäkringar ligger utanför populationen, och ingen försäkring lämnades utan att föras över.
    - **Kontrollen** `verify.py --backup` gav 16 av 16 med bara läsning:
      - fall 36: A6 ur journalen gav FTA 15 895 579,24, VÅ 26 232 775,02 och U 41 130,68 kr, samma som S-04;
      - fall 37: november gav 51 623,90 kr, utan avstämningskontots 36 261,66 kr, och inget är bokat;
      - inga agenträttigheter;
      - övriga radantal som i backupen, utom S-04-utdraget i `valuation_extracts` (0 → 1) och övergångens loggrad i `operation_events` (225 → 226).

- **Paket B steg 3 (2026-11-19) – månadsstängning och rättelse i journalen (§7c, B-047, P1-PENSION-001 §7):** införs med `scripts/migrations/migrate_month_close.py` (`utils/migration_month_close.py`) i **en** transaktion.
  - **Vad den gör:** lägger till `ledger_batches.supersedes_id`, vidgar `ck_ledger_batches_kind` med `month_close` och `month_correction` och skapar `ck_ledger_batches_supersedes`, `uq_ledger_batches_one_close` och `uq_ledger_batches_supersedes`. Inga andra tabeller och inga rader ändras; det ingående läget uppfyller de nya villkoren.
  - **Förutsättning:** journalens fyra tabeller (steg 2) ska finnas.
  - **Torrkörning** är standard och körs `READ ONLY`. Den visar SQL, läget för varje del, hinder (agenträttigheter på journalen) och radantal.
  - **Skarp körning:** `--apply` kräver `--backup`. Körningen kontrollerar i samma transaktion att alla delar finns, modellens kolumner, oförändrade radantal i alla tabeller och att ingen agentroll har rättigheter på journalen. Minsta avvikelse rullar tillbaka allt.
  - **Idempotent:** är allt infört görs ingenting; är bara en del infört stoppar migrationen.
  - **Verifierat** mot isolerad Postgres (`tests/test_migration_month_close.py`): från Lakebase-läget efter steg 2, med det ingående läget bokat, blir `ledger_batches` identisk med `create_all`. Migrationen är idempotent, delvis infört stoppar och det ingående läget är orört. Novemberstängningen är provad där med låset.
  - **Kodens beroende:** kolumnen läses först när den behövs (`deferred`), så steg 2:s läsningar fungerar före migrationen. Månadsstängningens operationer blockeras med hänvisning till migrationen.
  - **Ordning i Lakebase** (Karls val S6): backup → torrkörning → `--apply` → tidigast 2026-12-01, efter novembers sista bankfil: `adopt_avk.py` → `close_month.py` (granskning) → `close_month.py --apply` → `verify.py --backup`, alla i `scripts/simulation/paket_b_steg3/`. Varje skarpt steg kräver Karls separata OK och samordning enligt AGENTS.md §4.5.
  - **Införd i Lakebase 2026-11-19** efter backup `backups/20261119T201517Z` (40 tabeller), med Karls OK och samordning enligt AGENTS.md §4.5 (inga andra klientanslutningar):
    - **Torrkörningen** gav sex satser, alla på `ledger_batches`. Ingen del var införd, och det fanns inga hinder.
    - **`--apply`** gick igenom med alla kontroller i transaktionen. En ny torrkörning ger `already_applied`.
    - **Kontrollerat efteråt** med bara läsning:
      - radantalen i backupens 40 tabeller är oförändrade;
      - agentrollerna har inga rättigheter på journalen;
      - det ingående läget `f42b3e82…` stämmer med sina rader och har `supersedes_id` NULL;
      - ingen månad är stängd.
    - **Granskningarna** (`READ ONLY`) gick också att köra. `adopt_avk.py` gav AVK-SIM-2026-02 med kontrollsumman `b75912c4…ef13`, samma som lokalt. `close_month.py` stoppar, eftersom november inte har tagit slut.
    - **Kvar:** AVK, stängning och `verify.py` tidigast 2026-12-01.

- **Paket B steg 4 (2026-11-21) – begäran, uttagsplan och delning (§7c, §7d, §9g, B-047, P1-PENSION-001 §5, Karls val V1–V11):** införs med `scripts/migrations/migrate_payout_plans.py` (`utils/migration_payout_plans.py`) i **en** transaktion.
  - **Vad den gör:**
    - skapar `payout_requests`, `payout_plans` och `payout_splits` tomma med index och villkor;
    - vidgar `ck_cases_type` med `payout_request` och `payout_review`;
    - lägger till `ledger_guarantee_parts.plan_id` med FK och index, vidgar `ck_ledger_guarantee_parts_plan` med `plan` och skapar `ck_ledger_guarantee_parts_plan_id`.
  - Inga rader ändras; journalens rader uppfyller de nya villkoren.
  - **Förutsättning:** steg 1–3 är införda (uttagsdelarna, journalen och `ledger_batches.supersedes_id`).
  - **Torrkörning** är standard och körs `READ ONLY`. Den visar SQL, läget för varje del, villkorens nuvarande definitioner, hinder (agenträttigheter) och radantal.
  - **Skarp körning:** `--apply` kräver `--backup`. Körningen kontrollerar i samma transaktion modellens kolumner, de bytta villkoren, tomma tabeller, oförändrade radantal och att ingen agentroll har rättigheter på de nya tabellerna eller journalen. Minsta avvikelse rullar tillbaka allt.
  - **Idempotent:** är allt infört görs ingenting; är bara en del infört stoppar migrationen.
  - **Verifierat** mot isolerad Postgres (`tests/test_migration_payout_plans.py`): från läget efter steg 3, med november stängd, blir de tre tabellerna, `cases` och `ledger_guarantee_parts` identiska med `create_all`. Migrationen är idempotent, och delvis infört stoppar. Paket A:s testbestånd i Postgres ger i novemberstängningen planbaserade garantidelar med `plan_id` (fall 2) och en delning med kapital (fall 7), och stängningen är idempotent.
  - **Kodens beroende:** `plan_id` läses först när den behövs (`deferred`) och skrivs bara när den är satt, så stängningen fungerar före migrationen. Då beter den sig som i steg 3, utan ärenden och planer. Operationerna blockeras med hänvisning till migrationen.
  - **Ordning i Lakebase** (Karls val V11): tidigast när novembers stängning är bokad och kontrollerad (2026-12-01) och steg 4 är mergat. Därefter `survey.py` → backup → torrkörning → `--apply` → `verify.py --backup`, i `scripts/simulation/paket_b_steg4/`. Varje skarpt steg kräver Karls separata OK och samordning enligt AGENTS.md §4.5.
  - **Inte införd i Lakebase.**

- **Paket B steg 5 (2026-11-22) – beloppsbeslut, månadsrätt och bolagskonto (§7c, §7e, §9g, B-047, P1-PENSION-001 §5.5, Karls val W1–W12):** införs med `scripts/migrations/migrate_pension_claims.py` (`utils/migration_pension_claims.py`) i **en** transaktion.
  - **Vad den gör:**
    - skapar `payout_amounts`, `pension_claims` och `pension_claim_fundings` tomma med index och villkor;
    - vidgar `ck_ledger_batches_kind` och `ck_ledger_capital_entries_reason` med `company_capital` och skapar `ck_ledger_capital_entries_accounts`;
    - vidgar `ck_cases_type` och `ck_cases_subject` med `company_capital`.
  - Inga rader ändras; journalens poster ligger på kundkapitalet och uppfyller det nya villkoret.
  - **Förutsättning:** steg 1–4 är införda, med `payout_plans` och `ledger_guarantee_parts.plan_id`; annars stoppar migrationen.
  - **Torrkörning** är standard och körs `READ ONLY`. **Skarp körning:** `--apply` kräver `--backup`. Samma kontroller i transaktionen som i steg 4: kolumner, villkor, oförändrade radantal och inga agenträttigheter; minsta avvikelse rullar tillbaka allt.
  - **Idempotent:** är allt infört görs ingenting. Är bara en del av tabellerna införd stoppar migrationen; villkoren avgör inte, eftersom de härleds ur samma modeller som steg 4:s.
  - **Verifierat** mot isolerad Postgres (`tests/test_migration_pension_claims.py`): från läget efter steg 4 blir de tre tabellerna, journalens villkor och `cases` identiska med `create_all`. Migrationen är idempotent; delvis införd och saknat steg 4 stoppar. Paket A:s testbestånd i Postgres ger i novemberstängningen standardplanen, beloppsbeslutet och första rätten med skuld (fall 1 och 14).
  - **Kodens beroende:** utan tabellerna beter sig stängningen som i steg 4 (och utan steg 4:s som i steg 3). Det är prövat mot main:s kod på samma databas (`scripts/simulation/paket_b_steg5/compare_main.py`, B-052). Operationerna blockeras med hänvisning till migrationen.
  - **Ordning i Lakebase** (Karls val W12): novembers stängning, steg 4:s migration och därefter `survey.py` → backup → torrkörning → `--apply` → `verify.py --backup`, i `scripts/simulation/paket_b_steg5/`. Insättningen på bolagskontot behövs först inför den första stängningen med en månadsrätt (PB11). Varje skarpt steg kräver Karls separata OK och samordning enligt AGENTS.md §4.5.
  - Mergad till main 2026-11-23; **inte införd i Lakebase.**

---

## 12b. Ärendeuppdragens schemaändring

**Tillägg 2026-10-31 – ärendeuppdrag:** modellerna i `src/models/case_work.py`
definierar `case_work`, `case_messages` och `case_work_days`. De hör till
betrodd harness och ärendeuppföljning; agentrollerna får ingen direkt åtkomst.
Ärende-/uppdragsreferenser har främmande nycklar, beställningsnyckeln är unik,
arbetsform/status har CHECK-villkor och köanspråk använder villkorlig UPDATE.
Dialog/resultat är personuppgiftsbärande. Fält, indexens användning,
reservationsbok, skydd och migration beskrivs i
[ärendedialog och automation](arendedialog_och_automation.md#data-migration-och-skydd).
Migration: `scripts/migrations/migrate_case_work.py`; införd i Lakebase
2026-10-31 efter backup `backups/20261031T144609Z` och operatörens OK.
Tre tomma tabeller med rätt kolumner, nycklar och index; övriga 17 212 rader
oförändrade. Ägare `app_backend`, inga direkta rättigheter för de tre agentrollerna.
En andra körning gör ingenting. Webbstart och en tom engångskörning av arbetaren
är verifierade; schema/automatbeslut är fortsatt avstängda.

## 13. Hänvisningar

- **B-018** – Databricks Lakebase som databas (ersätter B-014/Supabase); SQLAlchemy som ORM kvarstår
- **B-005** – hybrid dataarkitektur (varför struktur i DB och inte i text)
- **B-006** – behörighetsmodell för PII
- **B-015** – mappstruktur och namnkonvention (engelska i kod, svenska i dokumentation)
- **B-021** – produktförenklingar (kapitalavgift som `fee`-transaktion m.m.)
- **B-022** – försäkringsmodell: flera försäkringar per person, förmåner och tillståndsperioder (ersätter B-021:s ett-avtal-regel)
- **B-047** – paket B, pensions- och månadsavräkning: tre förlopp och uttagsdelar (punkt 2; §6 och §7b)
- **B-003/B-019** – simulerad kapitalförvaltning; modellval i `projekt/05_kapitalförvaltning/DATAMODELL_BESLUTSFORSLAG.md`, tillämpade inom operatörens mandat 2026-10-24, ingen ny beslutsloggspost
- **MASTER_CONTEXT §6** – dataarki­tektur (övergripande)
- Domänregler: `01_domän/ITP1_regelverk.md` (premietrappa, åldersfönster), `01_domän/försäkringsvillkor.md` (livscykel, fakturering)
- SQLAlchemy-modeller: `src/models/employer.py`, `insured_person.py`, `policy.py`, `policy_state.py`, `policy_benefit.py`, `payout_part.py`, `premium_transaction.py`, `salary_report.py`, `base_amount.py`, `operation_event.py`, `approval_request.py`, `portfolio.py`, `portfolio_holding.py`, `trade.py`
- Mockdatagenerering: `scripts/demo/generate_mock_data.py`
- Databas-seed: `scripts/demo/seed_mock_data.py` *(seedar Lakebase via `DATABASE_URL`)*
