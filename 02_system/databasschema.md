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
| `policy_states` | Försäkringslägen – tillståndshistorik per försäkring | 🟢 I drift i Lakebase; importerad historik och tjänsteoperationer |
| `policy_benefits` | Försäkringsförmåner – förmåner inom en försäkring | 🟢 I drift i Lakebase; förmånen ålderspension |
| `premium_transactions` | Premietransaktioner (en rad per förmån och månad) | 🟢 I drift i Lakebase med importerad premiehistorik; `corrects_transaction_id` migrerad 2026-10-11 |
| `salary_reports` | Löneunderlag – pensionsmedförande lön per person, arbetsgivare och månad, versionerat | 🟢 Skapad i Lakebase 2026-10-11 (§8b); registrering verifierad i S6 2026-10-12 |
| `base_amounts` | Basbelopp per år (parametertabell för beräkningar) | 🟢 I drift (seedad 2023–2026) |
| `operation_events` / `approval_requests` | Tjänstelagrets händelselogg och godkännandekö (§9b–9c) | 🟢 Skapade i Lakebase i Fas 1f T3a; kö/logg används av tjänstelagret och UI:t |
| `cases` | Ärenden – handläggaragentens arbetsenhet och mandat (§9g) | 🟢 Skapad med agentrollens läsrätt i Lakebase 2026-10-24. Slutverifiering av agentflödet återstår i F5-5–6 |
| `case_work` / `case_messages` / `case_work_days` | Varaktiga ärendeuppdrag, skyddad dialog och daglig budgetbok (§12b) | 🟢 Skapade tomma i Lakebase 2026-10-31 efter backup och operatörens OK; inga direkta agenträttigheter. Schema är avstängt |
| `product_parameters` | Versionerade premieåldrar, premiesatser och brytpunkter (§9h) | 🟢 Skapad och seedad i Lakebase 2026-10-25; agentrollens läsrätt satt. Förändringsoperationer finns; komplett flödesverifiering återstår i 3c-V |
| `portfolios` / `portfolio_holdings` / `trades` | Fristående paper trading-scenarier, instrument och affärsförslag/kvittenser (§9d–9f) | 🟡 Fas 2c: modeller och lokala tester; ej skapade i Lakebase |
| `flows` / `flow_steps` / `flow_gate_decisions` | Flödesmotorn i harness: flöden, steg och grindbeslut (§9i) | 🟡 Fas 3c 3c-2: modeller, motor och tester; migrationen verifierad mot isolerad Postgres; 🟢 skapade i Lakebase 2026-10-26 efter backup `backups/20261026T200423Z` och operatörens OK (tomma, inga agenträttigheter) |
| `valuation_bases` | Antagandebiblioteket: aktuariella grunder och diskonteringskurvor med oföränderligt innehåll (§9j) | 🟡 A4 (B-042): modell, operationer, startgrunder och tester; 🟢 skapad och seedad i Lakebase 2026-10-31 efter backup `backups/20261031T124616Z` och operatörens OK; läsrätt för `agent_aktuarie` satt |

**Kedjan för uppslag:** person → `policies` (personens försäkringar) → `policy_benefits` (förmåner per försäkring) → `premium_transactions` (premier per förmån), med `policy_states` som parallell tidsaxel för försäkringens läge. Alla kopplingar är FK:er så varje fråga "vad hade person X för läge/förmåner/premier vid tidpunkt T" är en join-kedja.

**Planerade tabeller (ej i denna omgång):** Kapitalets kassaflödesjournal och premiekoppling byggs senare; se §9d.

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
| `case_type` | `VARCHAR(40)` | NOT NULL, CHECK in (`'salary_report'`) | Ärendetyp. Fler typer läggs till med ny CHECK (B-033 val C) |
| `status` | `VARCHAR(20)` | NOT NULL, CHECK in (`open`, `in_progress`, `waiting_approval`, `waiting_info`, `closed`), default `open` | Aktuell status |
| `outcome` | `VARCHAR(20)` | NULL, CHECK in (`approved`, `rejected`, `supplement_requested`, `manual_review`, `no_action`) | Utfall; satt exakt när ärendet är stängt |
| `insured_person_id` | `UUID` | NULL, FK → `insured_persons(id)` ON DELETE RESTRICT | Den försäkrade ärendet gäller |
| `policy_id` | `UUID` | NULL, FK → `policies(id)` ON DELETE RESTRICT | Försäkringen, om ärendet gäller en viss |
| `employer_id` | `UUID` | NULL, FK → `employers(id)` ON DELETE RESTRICT | Arbetsgivaren, t.ex. avsändare av löneunderlaget |
| `period_month` | `DATE` | NULL, CHECK (dag = 1) | Månaden ärendet gäller |
| `channel` | `VARCHAR(20)` | NOT NULL, CHECK in (`manual`, `employer_file`, `customer_portal`, `chatbot`) | Inkommande kanal; `manual` i v1, övriga reserverade (delprojekt 3 och 7) |
| `received_date` | `DATE` | NOT NULL | Mottagningsdag (PR-ITP1-031) |
| `source_reference` | `VARCHAR(100)` | NULL | Avsändarens referens, t.ex. lönefilens id |
| `due_date` | `DATE` | NULL | Tidsfrist, t.ex. för klagomål (PR-ITP1-030); ingen för löneunderlag i v1 |
| `details` | `JSONB` | NOT NULL | Typens uppgifter, validerade mot en Pydantic-modell per typ i tjänstelagret (B-033 val F). För `salary_report`: rapporterad lön, källa, `kind` och ev. `corrects_version` |
| `assigned_to` | `VARCHAR(100)` | NULL | Handläggaren som äger ärendet |
| `last_run_id` | `VARCHAR(100)` | NULL | Senaste agentkörningen; journal i `logs/agent_runs/<run_id>.jsonl` |
| `created_by` | `VARCHAR(100)` | NOT NULL | Den som registrerade ärendet |
| `closed_by` / `closed_at` | `VARCHAR(100)` / `TIMESTAMPTZ` | NULL | Satta exakt när ärendet är stängt |
| `closing_note` | `TEXT` | NULL | Anteckning vid stängning; krävs vid `rejected` och `manual_review` |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

**Integritet:**
- Unikt `case_number`
- CHECK: minst en av `insured_person_id` och `employer_id` – ett ärende gäller någon
- CHECK: stängt ärende har `outcome`, `closed_by` och `closed_at`; öppet ärende har inga av dem
- CHECK: `rejected` och `manual_review` har `closing_note` – avslag och manuell prövning motiveras (PR-ITP1-031)
- CHECK: `period_month` är första dagen i månaden (Postgres- och SQLite-variant, §12)
- Index på `status`, `case_type` och `insured_person_id`

**Skrivs av** tjänstelagrets ärendeoperationer (F5-2): `create_case`, `update_case_status` och `close_case` (`HUMAN_ONLY`; harness skriver status efter en körning som systemaktör). **Läses av** `list_cases` (`HUMAN_ONLY`) och `get_case` (`AGENT`, bara körningens ärende). Agenten kan inte skapa, ändra eller stänga ärenden.

**Personuppgifter:** `details` kan innehålla lön och fri text (B-006). Gallring följer PR-ITP1-031 och beslutas i tjänstelagerprojektets lagringspolicy.

---

## 9h. Tabell: `product_parameters` – Produktparametrar som versionerad data

**Domän:** Parametrar som styr premieberäkningen, i versioner med giltighetsintervall (Fas 3c, B-035). En regeländring som bara ändrar ett värde – t.ex. premieåldern – kan därmed nå produktion som en ny version, utan kodändring. Premiemotorn tar parametrarna som indata (`PremiumParameters`); tjänstelagret slår upp versionen som gäller premiemånaden (`services/parameters.py`) och sparar versionerna i `calculation_basis` (`parameters`, `age_window`). Följer parameterregistrets avsnitt *Parameterändring*: värde, enhet, giltighet, källa och beslut.

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | |
| `key` | `VARCHAR(60)` | NOT NULL, CHECK | `premium_age_start`, `premium_age_end`, `premium_rate_low`, `premium_rate_high`, `premium_breakpoint_low_ibb`, `premium_breakpoint_high_ibb` |
| `value` | `NUMERIC(12,6)` | NOT NULL, CHECK ≥ 0 | Värdet i parameterns enhet; åldrar måste vara hela år (kontrolleras vid uppslag) |
| `unit` | `VARCHAR(20)` | NOT NULL, CHECK | `years`, `rate` eller `ibb` |
| `valid_from` | `DATE` | NOT NULL, CHECK månadsförsta | Första premiemånad som omfattas |
| `valid_to` | `DATE` | NULL, CHECK ≥ `valid_from` | Sista dag; NULL = tills vidare |
| `rule_id` / `rule_version` | `VARCHAR(20)` / `VARCHAR(10)` | NOT NULL | Produktregeln som bär värdet, t.ex. `PR-ITP1-013` `1.0` |
| `source_ref` | `VARCHAR(60)` | NOT NULL | Källa i källregistret, t.ex. `K-ITP-FIL` |
| `decision_ref` | `VARCHAR(60)` | NOT NULL | Beslutet – B-nummer, flödets grindbeslut eller `B-035 startvärden` |
| `status` | `VARCHAR(20)` | NOT NULL, CHECK | `valid` eller `withdrawn`. Om en version är kommande, gällande eller upphörd härleds av datumen |
| `created_by` | `VARCHAR(100)` | NOT NULL | Aktören som lade versionen |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL | Standardtidsstämplar |

Unikt på `(key, valid_from)`, index på `key`. Två giltiga versioner av samma nyckel samma dag stoppar beräkningen (`BlockedError`) i stället för att en väljs tyst; en saknad parameter för månaden stoppar beräkningen (`NotFoundError`). Överlappskontrollen görs av skrivoperationerna: en ny version avslutar den föregående dagen före, och bara en kommande version per parameter är tillåten. En återkallad version ligger kvar, så samma giltighetsdag kan inte återanvändas.

**Startvärden från 2023-01-01** – samma som premiehistoriken 2023–2026 räknats med: premieålder 25–66 (PR-ITP1-013), satserna 4,5 och 30 % och brytpunkterna 7,5 och 30 IBB (PR-ITP1-001), `decision_ref` `B-035 startvärden`.

**Läses av** `get_product_parameters` (`AGENT`, inga personuppgifter), förhandsberäkningen och premierättelsen. **Skrivs av** migrationen (startvärden), `schedule_product_parameter_change` (`APPROVAL`) och `withdraw_product_parameter_change` (`HUMAN_ONLY`), med radlås på parameterns versioner (`tjänstelager.md` §9.4). Inga personuppgifter.

---

## 9i. Tabeller: `flows`, `flow_steps` och `flow_gate_decisions` – Flödesmotorn

> **Status:** Beslutade i **B-035** (`flaggskeppsflöde.md` §6, val E och J). Modeller, motor och lokala tester i Fas 3c 3c-2 (2026-10-25). Migrationen `scripts/migrations/migrate_flows.py` är verifierad mot isolerad Postgres och **körd mot Lakebase 2026-10-26** efter backup `backups/20261026T200423Z` och operatörens OK (AGENTS.md §4.5): tre tomma tabeller ägda av `app_backend`, övriga radantal oförändrade, en andra körning gjorde ingenting. Agentrollerna har inga rättigheter på tabellerna – motorn skriver dem med den betrodda anslutningen.

**Domän:** Ett flöde är en körning av en flödesdefinition i harness, t.ex. flaggskeppets regeländring: agentsteg, grindar där operatören beslutar, manuella steg och systemsteg. Tabellerna hör till harness (`src/agents/flows/`), inte till försäkringstjänstelagret (`harness.md` §4.3). De skrivs bara av flödesmotorn via den betrodda anslutningen, med operatören som aktör för grindbeslut och manuella steg. Agenternas körjournal ligger kvar som JSONL i `logs/agent_runs/` och länkas med `flow_steps.run_id` (val J). Ett förslag i tjänstelagrets godkännandekö länkas med `flow_steps.approval_id`; grinden ersätter aldrig det godkännandet.

### `flows`

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `flow_id` | `VARCHAR(20)` | PK, CHECK form `FLOW-NNNNNN` | Flödesnumret |
| `flow_type` | `VARCHAR(60)` | NOT NULL | Flödesdefinitionen, t.ex. `rule_change_parameter` (3c-3) |
| `definition_version` | `VARCHAR(20)` | NOT NULL | Definitionens version när flödet startades |
| `status` | `VARCHAR(30)` | NOT NULL, CHECK in (`running`, `waiting_gate`, `waiting_manual`, `waiting_approval`, `completed`, `rejected`, `cancelled`, `failed`, `reconciliation_required`) | Flödets läge |
| `input` | `JSONB` | NOT NULL | Indata, validerade mot definitionens modell |
| `current_step` | `VARCHAR(60)` | NULL | Stegnyckeln som står på tur; NULL när flödet är klart |
| `version` | `INTEGER` | NOT NULL, CHECK ≥ 1 | Version för optimistisk låsning: varje ändring är en villkorlig UPDATE på den lästa versionen |
| `created_by` | `VARCHAR(100)` | NOT NULL | Operatören som startade flödet |
| `finished_at` | `TIMESTAMPTZ` | NULL | Satt exakt när flödet är avslutat (`completed`, `rejected`, `cancelled`, `failed`) |
| `note` | `TEXT` | NULL | Skälet vid avslag, avbrott eller fel |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` | Standardtidsstämplar |

### `flow_steps`

| Kolumn | Datatyp | Constraints | Beskrivning |
|--------|---------|-------------|-------------|
| `id` | `UUID` | PK | Stegets id; står i `RunRequest.flow_step_id` och körjournalen |
| `flow_id` | `VARCHAR(20)` | NOT NULL, FK → `flows(flow_id)` ON DELETE RESTRICT | Flödet |
| `step_key` / `position` | `VARCHAR(60)` / `INTEGER` | NOT NULL, unika per flöde, position ≥ 1 | Stegnyckeln och ordningen enligt definitionen |
| `kind` | `VARCHAR(20)` | NOT NULL, CHECK in (`agent`, `gate`, `manual`, `system`) | Stegets slag |
| `title` | `VARCHAR(200)` | NOT NULL | Stegets rubrik |
| `team` / `agent` | `VARCHAR` | NULL | Team och agent för agentsteg |
| `status` | `VARCHAR(30)` | NOT NULL, CHECK in (`pending`, `running`, `completed`, `waiting`, `rejected`, `failed`, `skipped`, `reconciliation_required`) | Stegets läge |
| `run_id` | `VARCHAR(100)` | NULL | Agentkörningen; journal i `logs/agent_runs/<run_id>.jsonl`. Sätts innan körningen startar |
| `result` | `JSONB` | NULL | Stegets resultat: för agentsteg körningens status och det prövade resultatschemat (`agents.results`), för grindar beslutet, för manuella steg operatörens uppgifter |
| `result_hash` | `VARCHAR(64)` | CHECK satt när steget är `completed` | sha256 av resultatet i kanonisk JSON – det grindarna binder |
| `approval_id` | `VARCHAR(64)` | NULL | Förslaget i `approval_requests` som systemsteget väntar på |
| `artifact_refs` | `JSONB` | NULL | Utkastreferenser (`utkast:<team>/<run_id>/<namn>`) |
| `started_at` / `finished_at` | `TIMESTAMPTZ` | NULL | Tider |
| `completed_by` | `VARCHAR(100)` | NULL | Operatören vid grindar och manuella steg, godkännaren vid ett förslag i kön |
| `error` | `TEXT` | NULL | Fel eller avstämningsanteckning |

### `flow_gate_decisions`

Append-only: ett beslut är en ny rad, ingen rad ändras.

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

**Regler i motorn:** ett steg tas med en villkorlig UPDATE på `flows.version`, så att två klick inte kör samma steg två gånger. Grindbeslutet kräver att operatörens hash är densamma som underlagets just då. Innan ett senare steg tas räknas varje godkänd grind om, och ändrat underlag stoppar flödet. Ett steg som var `running` när motorn startade om blir `reconciliation_required` och avgörs av operatören.

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
- **Fas 3c 3c-P1 (2026-10-25) – tabellen `product_parameters` (§9h, B-035):** skapas med `scripts/migrations/migrate_product_parameters.py` (`utils/migration_product_parameters.py`) enligt samma mönster som `cases`: bara den nya tabellen och dess index, en transaktion, torrkörning som standard, `--apply` kräver `--backup`, radantalen kontrolleras. Migrationen lägger dessutom in startvärdena och **räknar om varje ordinarie premierad** med de lästa parametrarna – minsta avvikelse rullar tillbaka allt. Även torrkörningen gör kontrollen, i en transaktion som rullas tillbaka. Verifierat mot isolerad Postgres (`tests/test_product_parameters.py`): demobeståndet räknas om identiskt, idempotent, och en ändrad premie stoppar migrationen. Tills tabellen finns används paketets värden i koden, märkt i `calculation_basis`. **Ordning i Lakebase:** backup → torrkörning → `--apply` → `grant_agent_role.py --apply` (agentrollen får `SELECT` på tabellen). **Skapad i Lakebase 2026-10-25 efter backup `backups/20261025T090949Z` och torrkörning, med operatörens OK (AGENTS.md §4.5): alla 15 097 premier räknades om identiskt, radantalen i övriga tabeller oförändrade, en andra körning gjorde ingenting; agentrollens läsrätt sattes därefter med `grant_agent_role.py --apply`**
- **Fas 3c 3c-2 (2026-10-25) – flödesmotorns tabeller (§9i, B-035):** skapas med `scripts/migrations/migrate_flows.py` (`utils/migration_flows.py`) enligt samma mönster: bara `flows`, `flow_steps` och `flow_gate_decisions` med index, i en transaktion, torrkörning som standard, `--apply` kräver `--backup`, radantalen kontrolleras. Finns bara en del av tabellerna stoppar migrationen. Verifierat mot isolerad Postgres (`tests/test_migration_flows.py`): identiskt med `create_all`, idempotent, övriga tabeller orörda. Agentrollerna får ingen rätt till tabellerna – flödesmotorn skriver med den betrodda anslutningen. **Ej körd mot Lakebase**
- **A4 (2026-10-31) – tabellen `valuation_bases` (§9j, B-042):** skapas med `scripts/migrations/migrate_valuation_bases.py` (`utils/migration_valuation_bases.py`) enligt samma mönster:
  - bara den nya tabellen och dess index, i en transaktion;
  - torrkörning som standard, och `--apply` kräver `--backup`;
  - radantalen kontrolleras före och efter.

  Migrationen lägger in startgrunderna och prövar varje kontrollsumma. Minsta avvikelse rullar tillbaka allt. Verifierat mot isolerad Postgres 2026-10-31 (`tests/test_valuation_bases.py`). **Ordning i Lakebase:** backup → torrkörning → `--apply` → `grant_agent_role.py --team aktuarie --apply`. **Körd mot Lakebase 2026-10-31** efter backup `backups/20261031T124616Z` och torrkörning, med operatörens OK: tabellen och de sex startgrunderna skapade, radantalen i övriga tabeller oförändrade och en andra körning gjorde ingenting. Därefter sattes `agent_aktuarie`s rättigheter, också OC-3a:s kolumnrätter (B-041). Verifierat med rollens egen anslutning: läser grunderna och kontrollsummorna stämmer; nekas UPDATE, DELETE och INSERT på tabellen
- **A5 (2026-10-31) – uppgradering av `valuation_bases`:** samma skript, `migrate_valuation_bases.py`, uppgraderar en befintlig tabell. Villkoren för familj och ändamål byts till modellens (familjen `AVK-SIM`, ändamålet `return_series`) och startgrunder som saknas läggs in. Befintliga grunder ändras inte. Allt sker i en transaktion med torrkörning som standard, kontroll av kontrollsummor och radantal, och skriptet är idempotent. Verifierat mot isolerad Postgres 2026-10-31 från A4-läget, där båda villkoren saknar de nya värdena. **Körd mot Lakebase 2026-10-31** efter backup `backups/20261031T151410Z` och torrkörning, med operatörens OK: villkoren för familj och ändamål bytta, `AVK-SIM-2026-01` inlagd, radantalen i övriga tabeller oförändrade och en andra körning gjorde ingenting. Rättigheterna behövde inte ändras (SELECT på hela tabellen). Verifierat med `agent_aktuarie`s anslutning: läser alla sju grunderna och kontrollsummorna stämmer; nekas UPDATE

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
- **B-003/B-019** – simulerad kapitalförvaltning; modellval i `projekt/05_kapitalförvaltning/DATAMODELL_BESLUTSFORSLAG.md`, tillämpade inom operatörens mandat 2026-10-24, ingen ny beslutsloggspost
- **MASTER_CONTEXT §6** – dataarki­tektur (övergripande)
- Domänregler: `01_domän/ITP1_regelverk.md` (premietrappa, åldersfönster), `01_domän/försäkringsvillkor.md` (livscykel, fakturering)
- SQLAlchemy-modeller: `src/models/employer.py`, `insured_person.py`, `policy.py`, `policy_state.py`, `policy_benefit.py`, `premium_transaction.py`, `salary_report.py`, `base_amount.py`, `operation_event.py`, `approval_request.py`, `portfolio.py`, `portfolio_holding.py`, `trade.py`
- Mockdatagenerering: `scripts/demo/generate_mock_data.py`
- Databas-seed: `scripts/demo/seed_mock_data.py` *(seedar Lakebase via `DATABASE_URL`)*
