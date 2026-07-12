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
| `policies` | Försäkringsavtal (ålderspension ITP1 per försäkrad) | 🟡 Skiss (Fas 1b) |
| `premium_transactions` | Premietransaktioner (en rad per policy och månad) | 🟡 Skiss (Fas 1b) |
| `base_amounts` | Basbelopp per år (parametertabell för beräkningar) | 🟡 Skiss (Fas 1c) |

**Planerade tabeller (ej i denna omgång):** `portfolios`/`portfolio_holdings`/`trades` (Fas 2, B-019), `cases` (ärenden, Fas 5).

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
| `monthly_salary_sek` | `NUMERIC(10,2)` | NULL | Aktuell månadslön i SEK. NULL om okänd |
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
- `insured_persons.id` ← `policies.insured_person_id` (1:1, se §5)

---

## 5. Tabell: `policies` – Försäkringsavtal

**Domän:** Ett försäkringsavtal om ålderspension ITP1 för en försäkrad. Enligt B-021 (endast traditionell förvaltning, ingen valcentral) har varje försäkrad **exakt ett** avtal hos bolaget – därav UNIQUE på `insured_person_id`. Pensionskapitalet lagras inte här utan härleds ur transaktioner (single source of truth); en cachad saldokolumn kan införas senare om prestanda kräver.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK, default `gen_random_uuid()` | Surrogatnyckel |
| `policy_number` | `VARCHAR(20)` | NOT NULL, UNIQUE | Läsbart avtalsnummer, format `AL-NNNNNN` (löpnummer). Affärsnyckel för kommunikation med kund |
| `insured_person_id` | `UUID` | NOT NULL, UNIQUE, FK → `insured_persons(id)` ON DELETE RESTRICT | Den försäkrade. UNIQUE pga B-021 (ett avtal per person) |
| `start_date` | `DATE` | NOT NULL | Ikraftträdande – första dagen i första premiemånaden (villkor §2.2) |
| `end_date` | `DATE` | NULL | Avslutsdatum, NULL = löpande |
| `status` | `VARCHAR(20)` | NOT NULL, CHECK in (`'active'`, `'paid_up'`, `'in_payout'`, `'payout_paused'`, `'terminated'`), default `'active'` | Livscykel, se nedan |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standard­tidsstämplar |

**Statuslivscykel** (speglar villkoren i `01_domän/försäkringsvillkor.md`):

- `active` – premiebetalande (villkor §3)
- `paid_up` – fribrev: anställning upphörd, kapital kvar i förvaltning (villkor §2.4)
- `in_payout` – uttag pågår (villkor §7)
- `payout_paused` – uttag pausat, kapital åter i förvaltning (villkor §7.3)
- `terminated` – avslutat (kapital slututbetalt eller avtal annullerat)

**Index:** `policy_number` och `insured_person_id` (implicita via UNIQUE), `status`.

**Relationer:**
- `policies.insured_person_id` → `insured_persons.id` (1:1 enligt B-021)
- `policies.id` ← `premium_transactions.policy_id` (ett avtal har många transaktioner)

---

## 6. Tabell: `premium_transactions` – Premietransaktioner

**Domän:** En rad per policy, kalendermånad och transaktionstyp. Ordinarie premie beräknas enligt premietrappan i `01_domän/ITP1_regelverk.md` §2/§8. Tabellen är **spårbarhetens kärna**: varje krona i pensionskapitalet ska kunna följas hit, och varje rad ska kunna räknas om från sitt löneunderlag och sina beräkningsparametrar.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK, default `gen_random_uuid()` | Surrogatnyckel |
| `policy_id` | `UUID` | NOT NULL, FK → `policies(id)` ON DELETE RESTRICT | Försäkringsavtalet |
| `period_month` | `DATE` | NOT NULL, CHECK (dag = 1) | Premiemånaden, alltid månadens första dag (t.ex. `2026-06-01`) |
| `transaction_type` | `VARCHAR(20)` | NOT NULL, CHECK in (`'premium'`, `'adjustment'`, `'fee'`), default `'premium'` | `premium` = ordinarie månadspremie, `adjustment` = korrigering (±), `fee` = kapitalavgift enligt B-021 (införs med kapitalberäkningen) |
| `pensionable_salary_sek` | `NUMERIC(10,2)` | NULL, CHECK ≥ 0 | Pensionsmedförande lön som premien beräknats på. NULL för typer utan löneunderlag (`fee`) |
| `amount_sek` | `NUMERIC(12,2)` | NOT NULL | Belopp. Positivt = tillförs kapitalet, negativt = dras (avgifter, korrigeringar nedåt) |
| `calculation_basis` | `JSONB` | NULL | Beräkningsunderlag för revision: `{"ibb": 83400, "breakpoint_low": 52125, "breakpoint_high": 208500, "rate_low": 0.045, "rate_high": 0.30, "amount_low": ..., "amount_high": ...}` |
| `status` | `VARCHAR(20)` | NOT NULL, CHECK in (`'pending'`, `'invoiced'`, `'paid'`, `'cancelled'`), default `'pending'` | Faktureringsflöde enligt villkor §4. Kapital tillgodoförs vid `paid` |
| `paid_date` | `DATE` | NULL | Datum betalning mottogs (sätts vid status `paid`) |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standard­tidsstämplar |

**Unikhet:** Partiellt unikt index på `(policy_id, period_month)` där `transaction_type = 'premium'` – max en ordinarie premie per avtal och månad. Korrigeringar och avgifter kan förekomma flera gånger samma månad.

**Index:** `(policy_id, period_month)` för kontoutdrag per avtal, `status` för faktureringsflödet.

**Relationer:**
- `premium_transactions.policy_id` → `policies.id`

**Designnoter:**
- `amount_sek` är signerad och `NUMERIC(12,2)` (rymmer stora korrigeringar); saldo = `SUM(amount_sek) WHERE status = 'paid'`
- `calculation_basis` som JSONB i stället för egna kolumner: parametrarna varierar per typ och år, och används för revision/felsökning snarare än relationella frågor (jfr hybridprincipen B-005)
- Avrundning: premier avrundas till hela ören vid beräkning (regelverket §8.5)

---

## 7. Tabell: `base_amounts` – Basbelopp per år

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
- Brytpunkterna (7,5 IBB/12 och 30 IBB/12) lagras **inte** utan härleds i kod – en enda sanning, ingen risk för inkonsekvent avrundning i data
- Seedas med IBB 2023–2026 ur `01_domän/ITP1_regelverk.md` §6

---

## 8. Datakvalitet och valideringar

**På applikationsnivå (Python/SQLAlchemy):**
- `org_number` – Luhn-kontroll (10 siffror, sista siffran är kontrollsiffra)
- `personal_id_number` – Luhn-kontroll och datumvalidering
- `affiliation_date` ≤ idag
- `employment_start_date` ≤ `employment_end_date` (om båda satta)
- `itp1_start_date` ≥ datum när personen fyllde 25 (ITP-avtalets §4)
- `policies.start_date` ≥ den försäkrades `itp1_start_date` (om satt)
- `premium_transactions.period_month` inom policyns aktiva period
- `premium`-transaktioner: `amount_sek` ska vara reproducerbar ur `pensionable_salary_sek` + `calculation_basis`

**På databasnivå (CHECK):**
- `status`-fältens enumvärden
- `employment_rate` mellan 0 och 100
- `monthly_salary_sek` ≥ 0

---

## 9. Säkerhet och behörigheter

- **Tabellen `insured_persons` är PII-bärande** (B-006). Skills som läser/skriver mot den ska deklareras med behörighetslista.
- **Maskning vid analys:** Data scientist-agenten arbetar mot anonymiserade vyer eller aggregat, inte rå PII.
- **Databasroller och radnivåsäkerhet:** Sätts upp i senare iteration när agentidentiteter och roller är definierade. Initialt körs all åtkomst via den native Postgres-rollen `app_backend` (Lakebase, B-018).

---

## 10. Migrationer och versionering

- **Alembic** används för schemamigrationer (planerat, ej uppsatt än).
- `employers` och `insured_persons` är skapade direkt via `Base.metadata.create_all` (före Alembic). `policies` och `premium_transactions` skapas på samma sätt i Fas 1b; Alembic införs senast när första ändringen av en befintlig tabell behövs.
- **Ändringar i schemat** dokumenteras alltid här först – sedan genereras Alembic-migration.

---

## 11. Hänvisningar

- **B-018** – Databricks Lakebase som databas (ersätter B-014/Supabase); SQLAlchemy som ORM kvarstår
- **B-005** – hybrid dataarkitektur (varför struktur i DB och inte i text)
- **B-006** – behörighetsmodell för PII
- **B-015** – mappstruktur och namnkonvention (engelska i kod, svenska i dokumentation)
- **B-021** – produktförenklingar (ett avtal per försäkrad, kapitalavgift som `fee`-transaktion)
- **MASTER_CONTEXT §6** – dataarki­tektur (övergripande)
- Domänregler: `01_domän/ITP1_regelverk.md` (premietrappa, åldersfönster), `01_domän/försäkringsvillkor.md` (livscykel, fakturering)
- SQLAlchemy-modeller: `src/models/employer.py`, `src/models/insured_person.py`, `src/models/policy.py`, `src/models/premium_transaction.py`
- Mockdatagenerering: `scripts/generate_mock_data.py`
- Databas-seed: `scripts/seed_supabase.py` *(namnet är historiskt – seedar Lakebase via `DATABASE_URL`)*
