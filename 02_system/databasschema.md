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
| `policies` | Försäkringar (flera per försäkrad möjliga) | 🟡 Omdesignad (Fas 1e) |
| `policy_states` | Försäkringslägen – tillståndshistorik per försäkring | 🟡 Skiss (Fas 1e) |
| `policy_benefits` | Försäkringsförmåner – förmåner inom en försäkring | 🟡 Skiss (Fas 1e) |
| `premium_transactions` | Premietransaktioner (en rad per förmån och månad) | 🟡 Omdesignad (Fas 1e); kolumnen `corrects_transaction_id` tillkom i Fas 1f T3 (migrerad 2026-10-11) |
| `salary_reports` | Löneunderlag – pensionsmedförande lön per person, arbetsgivare och månad, versionerat | 🟢 Skapad i Lakebase 2026-10-11 (Fas 1f T3, §8b) – tom tills underlag registreras |
| `base_amounts` | Basbelopp per år (parametertabell för beräkningar) | 🟢 I drift (seedad 2023–2026) |
| `operation_events` / `approval_requests` | Tjänstelagrets händelselogg och godkännandekö (§9b–9c) | 🟡 Fas 1f T3a |

**Kedjan för uppslag:** person → `policies` (personens försäkringar) → `policy_benefits` (förmåner per försäkring) → `premium_transactions` (premier per förmån), med `policy_states` som parallell tidsaxel för försäkringens läge. Alla kopplingar är FK:er så varje fråga "vad hade person X för läge/förmåner/premier vid tidpunkt T" är en join-kedja.

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
- `insured_persons.id` ← `policies.insured_person_id` (1:N – en person kan ha flera försäkringar, se §5/B-022)

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

## 6. Tabell: `policy_states` – Försäkringslägen

**Domän:** Tillståndshistorik per försäkring som **tidsperioder**: varje rad säger "försäkringen var i läge X från `valid_from` till `valid_to`". Öppen rad (`valid_to IS NULL`) = nuvarande läge. Frågan "vilket läge hade försäkringen 2024-03-15?" = raden där datumet ligger i intervallet.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK, default `gen_random_uuid()` | Surrogatnyckel |
| `policy_id` | `UUID` | NOT NULL, FK → `policies(id)` ON DELETE RESTRICT | Försäkringen |
| `state` | `VARCHAR(20)` | NOT NULL, CHECK in (`'premium_paying'`, `'paid_up'`, `'in_payout'`, `'payout_paused'`, `'terminated'`) | Läge, speglar villkoren (se nedan) |
| `valid_from` | `DATE` | NOT NULL | Lägets första giltighetsdag |
| `valid_to` | `DATE` | NULL, CHECK (NULL eller ≥ `valid_from`) | Sista giltighetsdag. NULL = pågående |
| `note` | `VARCHAR(255)` | NULL | Orsak/kommentar, t.ex. "Anställning upphörde" |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

**Lägen** (befintlig implementation; hänvisningar till `01_domän/försäkringsvillkor.md` v2.0):

- `premium_paying` – premiebetalande (villkor §3)
- `paid_up` – fribrev (villkor §7)
- `in_payout` – uttag pågår (villkor §8–11)
- `payout_paused` – uttag pausat (villkor §10)
- `terminated` – avslutad

Produktpaket PR-ITP1 v1.0 skiljer premie-, pensions- och betalningsförlopp
och medger flera uttagsdelar. Tabellen ovan beskriver fortfarande den
befintliga modellen, som inte redan implementerar hela paketet. Kraven
för nästa byggsession finns i [UTTAG_GEMENSAMT](../01_domän/produktregler/UTTAG_GEMENSAMT.md).
Denna hänvisningsuppdatering ändrar inget schema eller någon kod.

**Integritet:** Partiellt unikt index på `policy_id` där `valid_to IS NULL` – max ett öppet läge per försäkring. Att perioder inte överlappar valideras på applikationsnivå (Postgres EXCLUDE-constraint kräver btree_gist-extension – utvärderas senare). Index på `(policy_id, valid_from)`.

**Ändras via tjänstelagret (Fas 1f T3):** `set_policy_paid_up` stänger den öppna `premium_paying`-perioden och öppnar `paid_up` dagen efter anställningens slut, och validerar hela tidslinjen (en öppen rad, inga överlapp). Bara för försäkringar vars pension inte har startat – ett läge per försäkring kan inte uttrycka fribrev samtidigt med pågående eller pausad pension (UTTAG_GEMENSAMT). Framtida giltighetsdagar skapas inte: läsningen tolkar den öppna raden som dagens läge.

---

## 7. Tabell: `policy_benefits` – Försäkringsförmåner

**Domän:** En förmån inom en försäkring. Endast premiebestämd ITP1 ålderspension (`retirement_dc`) ingår i beslutat produktscope. TGL och familjeskydd är tekniskt förberedda som typer enligt B-022, men får användas som produkter först om scope utökas genom ett nytt uttryckligt beslut och villkoren uppdateras. Förberedelsen innebär att dessa typer då kan läggas till som ytterligare rader med egna premier och parametrar, utan schemaändring.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK, default `gen_random_uuid()` | Surrogatnyckel |
| `policy_id` | `UUID` | NOT NULL, FK → `policies(id)` ON DELETE RESTRICT | Försäkringen |
| `benefit_type` | `VARCHAR(30)` | NOT NULL, CHECK in (`'retirement_dc'`, `'tgl'`, `'family_protection'`) | Tekniskt tillåtna typer; endast `retirement_dc` ingår i beslutat produktscope |
| `start_date` | `DATE` | NOT NULL | Förmånens ikraftträdande |
| `end_date` | `DATE` | NULL | Förmånens upphörande, NULL = löpande |
| `parameters` | `JSONB` | NULL | Förmånsspecifika parametrar; stöd för andra förmånstyper är en teknisk framtidsförberedelse |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

**Integritet:** Unikt index på `(policy_id, benefit_type)` där `end_date IS NULL` – max en pågående förmån av varje typ per försäkring. Historiska (avslutade) förmåner av samma typ tillåts.

**Relationer:** `policy_benefits.id` ← `premium_transactions.benefit_id` (förmånens premier).

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

> **Status:** Beslutad av operatören 2026-10-11 (Fas 1f T3). Skapad i Lakebase samma dag med migrationsskriptet (§12) efter backup och avstämning enligt AGENTS.md §4.5.

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
- Brytpunkterna (7,5 IBB/12 och 30 IBB/12) lagras **inte** utan härleds i kod – en enda sanning, ingen risk för inkonsekvent avrundning i data
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
- Data här kan inte genereras fram igen – omfattas av backup (`scripts/backup_database.py`)

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

## 10. Datakvalitet och valideringar

**På applikationsnivå (Python/SQLAlchemy):**
- `org_number` – Luhn-kontroll (10 siffror, sista siffran är kontrollsiffra)
- `personal_id_number` – Luhn-kontroll och datumvalidering
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
- **Databasroller och radnivåsäkerhet:** Sätts upp i senare iteration när agentidentiteter och roller är definierade. Initialt körs all åtkomst via den native Postgres-rollen `app_backend` (Lakebase, B-018).

---

## 12. Migrationer och versionering

- **Alembic** används för schemamigrationer (planerat, ej uppsatt än).
- `employers` och `insured_persons` är skapade direkt via `Base.metadata.create_all` (före Alembic). `policies` och `premium_transactions` skapas på samma sätt i Fas 1b; Alembic införs senast när första ändringen av en befintlig tabell behövs.
- **Ändringar i schemat** dokumenteras alltid här först – sedan genereras Alembic-migration.
- **Fas 1f T3 (2026-10-11) – första ändringen av en befintlig tabell:** gjord med ett kontrollerat migrationsskript, `scripts/migrate_t3_schema.py`, i stället för Alembic (som skulle kräva ett nytt beroende – föreslaget som eget steg). Skriptet skapar `salary_reports` och lägger till `premium_transactions.corrects_transaction_id` med sin CHECK och sitt index i **en** transaktion (Postgres-DDL är transaktionell), kontrollerar förutsättningarna först, visar SQL med `--dry-run`, ändrar inga befintliga rader och verifierar radantalen efteråt. Verifierat 2026-10-11 mot en isolerad Postgres 17 (`svc_test`): migrationen från det gamla schemat med data ger samma kolumner, constraints och index som `create_all`, är idempotent och lämnar radantalen oförändrade (`tests/test_services_postgres.py`). Körs mot Lakebase först efter backup (`scripts/backup_database.py`) och avstämning enligt AGENTS.md §4.5. `create_all` används inte för den befintliga tabellen. **Ordning:** migrationen är bakåtkompatibel (äldre kod påverkas inte), men koden från Fas 1f T3 läser `corrects_transaction_id` – migrationen ska därför vara körd innan den koden används mot Lakebase. Migrerat i Lakebase 2026-10-11 efter backup `backups/20261011T151353Z` och dry-run; radantalen oförändrade (15 097 premietransaktioner), en andra körning gjorde ingenting
- **Portabla modeller för tester (2026-10-11):** modellerna kan även skapas i en SQLite-databas i minnet, så att tjänstelagret (B-028) testas utan att röra Lakebase. JSON-kolumner är `JSON` med `JSONB`-variant för Postgres, de partiella unika indexen har även `sqlite_where`, och kontrollen att `period_month` är den första i månaden finns i en Postgres- och en SQLite-variant (`ddl_if`). Postgres-DDL:en är verifierat identisk före och efter ändringen – Lakebase påverkas inte och ingen migration behövs. Testdatabasen byggs i `tests/conftest.py` (`insurance_db`).

---

## 13. Hänvisningar

- **B-018** – Databricks Lakebase som databas (ersätter B-014/Supabase); SQLAlchemy som ORM kvarstår
- **B-005** – hybrid dataarkitektur (varför struktur i DB och inte i text)
- **B-006** – behörighetsmodell för PII
- **B-015** – mappstruktur och namnkonvention (engelska i kod, svenska i dokumentation)
- **B-021** – produktförenklingar (kapitalavgift som `fee`-transaktion m.m.)
- **B-022** – försäkringsmodell: flera försäkringar per person, förmåner och tillståndsperioder (ersätter B-021:s ett-avtal-regel)
- **MASTER_CONTEXT §6** – dataarki­tektur (övergripande)
- Domänregler: `01_domän/ITP1_regelverk.md` (premietrappa, åldersfönster), `01_domän/försäkringsvillkor.md` (livscykel, fakturering)
- SQLAlchemy-modeller: `src/models/employer.py`, `insured_person.py`, `policy.py`, `policy_state.py`, `policy_benefit.py`, `premium_transaction.py`, `salary_report.py`, `base_amount.py`, `operation_event.py`, `approval_request.py`
- Mockdatagenerering: `scripts/generate_mock_data.py`
- Databas-seed: `scripts/seed_supabase.py` *(namnet är historiskt – seedar Lakebase via `DATABASE_URL`)*
