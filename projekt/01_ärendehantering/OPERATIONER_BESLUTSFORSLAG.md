# Beslutsförslag: nya operationer för handläggar-UI:t (Fas 4, S4)

> **Status:** Förslag 2026-10-12. Väntar på operatörens val. Inget är byggt.
> **Underlag:** PR-ITP1-012 (anslutning), -013 (premieperioder), -014 (löneunderlag), -016 (kompletterande premier), -029 (information), -031 (data och beslut); försäkringsvillkor v2.0 §2–3 och §14; `02_system/databasschema.md` §3–7; `02_system/tjänstelager.md` §4 och §9.1.
> **Bygger på:** B-017, B-022, B-028, B-030, B-031.

---

## 1. Varför

Handläggaren kan i dag läsa en försäkrad, registrera löneunderlag, sätta fribrev, rätta premier och avgöra
agentförslag. Fyra vanliga åtgärder saknar operation i tjänstelagret:

1. lägga till en ny anställd med anslutning,
2. ändra aktuell lön på personen,
3. ändra kontaktuppgifter,
4. lägga till eller ändra en arbetsgivare.

Utan operationer kan UI:t inte göra dem, eftersom webbkoden bara får anropa tjänstelagret.

## 2. Förslaget i korthet

| Operation | Typ | Produktregler | PII | Register | Effektiv nivå för agenter i dag → från 2026-11-01 | Schemaändring |
|---|---|---|---|---|---|---|
| `enroll_insured_person` | `write` | PR-ITP1-012, -013 | Ja | `APPROVAL` | `HUMAN_ONLY` → `APPROVAL` | Nej |
| `update_current_salary` | `write` | – | Ja | `HUMAN_ONLY` | `HUMAN_ONLY` (ingen produktregel) | Nej |
| `update_contact_details` | `write` | PR-ITP1-031 | Ja | `HUMAN_ONLY` | `HUMAN_ONLY` | Nej |
| `register_employer` | `write` | PR-ITP1-012 | Ja (kontaktperson) | `HUMAN_ONLY` | `HUMAN_ONLY` | Nej |
| `update_employer_details` *(valfri)* | `write` | PR-ITP1-012 | Ja (kontaktperson) | `HUMAN_ONLY` | `HUMAN_ONLY` | Nej |
| `list_employers` | `read` | – | Nej | `AGENT` | `AGENT` | Nej |

Handläggare får alltid utföra alla operationer (B-017). Ingen operation kräver schemaändring. De fall som
skulle kräva en schemaändring (anställningshistorik, lönehistorik, nytt läge före premieålder) blockeras med
skäl och regel, och tas upp i §5.

---

## 3. Operationerna

### 3.1 `enroll_insured_person` – ny anställd och anslutning

**Vad den gör.** Allt skapas i en transaktion:

- **Den försäkrade** (`insured_persons`), med status `active`, arbetsgivare, anställningens start, ITP1 från,
  och valfritt aktuell lön, tjänstgöringsgrad, e-post och telefon.
- **En försäkring** (`policies`, nästa lediga `AL-NNNNNN`, produkt `ITP1`).
- **En förmån** (`policy_benefits`, `retirement_dc`).
- **Läget `premium_paying`** (`policy_states`) från ITP1-tillhörighetens start.

Ingen premie skapas, och inga historiska premier räknas fram. Premie ur löneunderlag är ett eget steg i ATT_GORA.

**Indata.**

| Fält | Krav |
|---|---|
| `personal_id_number` | 12 siffror, giltigt datum och Luhn |
| `first_name`, `last_name` | Obligatoriska |
| `employer_org_number` | Obligatoriskt |
| `employment_start_date` | Obligatoriskt |
| `itp1_start_date` | Dokumenterad tillhörighetsdag |
| `employment_category` | `ordinary`, `ceo`, `owner`, `posted_abroad` eller `opted_out` |
| `affiliation_reference` | Arbetsgivarens anmälan, t.ex. filreferens |
| `monthly_salary_sek`, `employment_rate`, `email`, `phone` | Valfria |

**Produktregler.**

- **PR-ITP1-012.** Det krävs identifierad arbetsgivare, person, anställning och dokumenterad ITP1-tillhörighet
  med giltighetsperiod. Födelseår avgör inte avdelning, så det finns ingen åldersgräns uppåt för anslutningen.
  VD, ägare, utlandsanställda och avstående kräver ett uttryckligt beslut. Avtalsstarten följer den
  dokumenterade dagen, inte en påhittad månadsförsta.
- **PR-ITP1-013.** Premie betalas från 25-årsmånaden till månaden före 66 år. Ett avtal kan registreras före
  premieåldern.

**Datum på försäkringen.** `signed_date` = `start_date` = `itp1_start_date`. Det är samma sak som den
genererade historiken gör. Databasen kräver `start_date ≥ signed_date`, så registreringsdagen kan inte vara
`signed_date` vid en retroaktiv anslutning. Registreringsdagen och anmälans referens hamnar i stället i
händelseloggen och i lägets `note`.

**Stöds:**

- ny person hos en aktiv arbetsgivare;
- `itp1_start_date` senast i dag, inte före anställningens start och inte före arbetsgivarens anslutning till ITP;
- retroaktiv anslutning, utan premier;
- person under 25 år, där avtalet registreras och premien börjar i 25-årsmånaden (se val A i §4).

**Blockeras (`BlockedError` med regel):**

| Fall | Varför |
|---|---|
| `employment_category` ≠ `ordinary` | Uttryckligt anslutnings- eller undantagsbeslut krävs (PR-ITP1-012) |
| ITP1-start i framtiden | Ingen framtidsdatering. Läsningen tolkar den öppna raden som dagens läge |
| 66 år eller äldre vid ITP1-start | Ingen ordinarie premie. Frivillig premie 66–67 kräver arbetsgivarens beslut (PR-ITP1-016) |
| Arbetsgivaren är inte aktiv | – |
| Annat kollektivavtal än ITP | B-002 |
| Personnumret finns redan | Är personen aktiv är det en `ConflictError`. Är den avslutad är det en återanställning eller ett arbetsgivarbyte, och då behövs anställningshistorik som modellen saknar (§5) |

**Samtidighet.** Nästa försäkringsnummer räknas fram ur det högsta befintliga. Krockar två samtidiga
anslutningar fångar databasens unikhetsregel det, och resultatet blir `ConflictError` (försök igen).

**Nivå.** `APPROVAL`. En agent kan förbereda anslutningar ur arbetsgivarens anmälningsfil, och handläggaren
godkänner. Regelgolvet ger `HUMAN_ONLY` till 2026-11-01.

**Utanför operationen.** Försäkringsbeskedet vid anslutning (villkor §14, PR-ITP1-029) är en `external`-handling
som byggs senare med kommunikationsagenten. Resultatet anger att beskedet inte är skickat.

### 3.2 `update_current_salary` – aktuell lön på personen

**Vad den gör.** Ändrar `insured_persons.monthly_salary_sek` och valfritt `employment_rate`.

**Hur den skiljer sig från löneunderlaget.** Aktuell lön är stamdata: avtalad månadslön enligt arbetsgivaren.
Den visas i översikten och kan användas som antagande i prognoser. Den är **inte** pensionsmedförande lön.
Enligt PR-ITP1-014 får avtalad lön inte ersätta faktiskt utbetald lön, så ändringen skapar ingen premie och
inget löneunderlag. B-030 avvisade just den här operationen som löneoperation, och den byggs nu som ren
stamdataändring. UI:t visar skillnaden tydligt: formuläret länkar till *Registrera löneunderlag* för det som
påverkar premien.

**Historik.** Modellen har bara aktuellt värde. Händelseloggen sparar tidigare och nytt värde i resultatet,
vilket räcker i v1.

**Blockeras:**

- avliden, pensionerad eller avslutad anställning, eftersom aktuell lön då saknar mening (`BlockedError`);
- oförändrat värde (`ConflictError`).

**Nivå.** `HUMAN_ONLY`. Ingen produktregel styr aktuell lön, och regelgolvet (*write utan regel*) gör den
`HUMAN_ONLY` för agenter oavsett registret. Ska agenter uppdatera den ur arbetsgivarens filer behövs först en
data- eller produktregel från delprojekt 4.

### 3.3 `update_contact_details` – kontaktuppgifter

**Vad den gör.** Ändrar `email` och `phone` på den försäkrade. Ett värde kan också tas bort.

**Indata.** Nya värden och `source`: `insured`, `employer` eller `other`. Motiveringen anger hur personen
verifierades.

**Produktregel.** PR-ITP1-031: rätt person ska verifieras, och bara nödvändiga uppgifter behandlas. Namnbyte
är en identitetsuppgift och ingår inte (§5). Personnummer ändras aldrig.

**Blockeras:**

- avliden försäkrad, där dödsboets kontakt hanteras i avräkningen (PR-ITP1-010);
- ogiltigt format (valideringsfel);
- oförändrade värden (`ConflictError`).

**Nivå.** `HUMAN_ONLY`. Att byta e-post är en känd väg för kontokapning, så en människa ska verifiera tills
kundportalen har riktig autentisering.

### 3.4 Arbetsgivare – `register_employer`, `update_employer_details` och `list_employers`

**`register_employer`.** Ny försäkringstagare med:

- organisationsnummer (10 siffror, Luhn),
- namn,
- anslutningsdag till ITP (senast i dag),
- valfri SNI-kod, adress och kontaktperson.

Kollektivavtalet är alltid `ITP` (B-002). Ett befintligt organisationsnummer ger `ConflictError`.

**`update_employer_details`** *(valfri i v1)*. Ändrar adress och kontaktperson. Den ändrar inte status, och
ändrar inte organisationsnummer eller anslutningsdag. När en arbetsgivare avslutas eller pausas berörs alla
dess försäkrade (avanmälan), så det är ett eget, senare flöde.

**`list_employers`.** Ger organisationsnummer, namn, status, anslutningsdag och antal aktiva försäkrade, utan
kontaktperson. Det är den lista anslutningsformuläret väljer arbetsgivare ur.

**PII.** Kontaktpersonen är en personuppgift, så skrivningarna är `pii=True`. Listan visar ingen
kontaktperson och loggas inte.

**Nivå.** Skrivningarna är `HUMAN_ONLY`, eftersom en ny försäkringstagare är ett nytt avtal och därför ett
mänskligt beslut. Listan är `AGENT`.

### 3.5 Gemensamt

**Webbformulär.** Varje operation får ett formulär med motivering, samma felvisning som i S2 och tester med
TestClient mot SQLite.

| Formulär | Var |
|---|---|
| Ny försäkrad | Startsidan och arbetsgivarlistan |
| Ändra lön | Översikten |
| Ändra kontaktuppgifter | Översikten |
| Arbetsgivare | Egen sida `/arbetsgivare` |

**Personnummer.** Luhn- och datumkontroll läggs i `services/operations/common.py` och används också av
anslutningen.

**Förteckningen.** `tjänstelager_operationer.md` genereras om.

---

## 4. Modellval att stämma av

| | Fråga | Rekommendation | Alternativ |
|---|---|---|---|
| A | Läge för en anslutning före 25 år | `premium_paying` från tillhörighetens start, med notering om premie från 25-årsmånaden. Premiemotorns åldersfönster ger ingen premie före dess | Blockera under 25 i v1 · nytt läge, t.ex. `enrolled` (schemaändring) |
| B | Befintligt personnummer, avslutad anställning (återanställning eller ny arbetsgivare) | Blockera med skäl. Anställningshistorik byggs som eget steg | Skriv över arbetsgivare och datum på personen, vilket tappar historiken. Avvisas |
| C | Ska `update_current_salary` få en regel så att agenter kan använda den? | Nej, `HUMAN_ONLY` utan regel i v1 | Be delprojekt 4 om en dataregel för aktuell lön |
| D | Arbetsgivaroperationer i v1 | `register_employer` och `list_employers`. `update_employer_details` ingår om du vill | Ingen arbetsgivaroperation; anslutning bara hos befintliga arbetsgivare |

## 5. Utanför v1 (förslag till ATT_GORA)

- **Anställningshistorik** (tabell `employments`). Behövs för återanställning, arbetsgivarbyte, flera
  anställningar och för att knyta löneunderlag till en avslutad anställning (PR-ITP1-013). Kräver schemaändring
  och migration enligt T3-mönstret.
- **Lönehistorik för aktuell lön.** I dag finns bara händelseloggen.
- **Namnbyte**, som identitetsuppgift (`HUMAN_ONLY`).
- **Arbetsgivarens avslut eller paus**, med avanmälan av alla försäkrade.
- **Försäkringsbesked vid anslutning**, en `external`-handling med kommunikationsagenten.
- **Premie ur löneunderlag**, som redan finns i ATT_GORA.

## 6. Beslutsförslag (för beslutsloggen – operatören sätter numret)

> **Beslut:** Tjänstelagret utökas med operationer för handläggar-UI:t (Fas 4):
>
> - `enroll_insured_person` (anslutning av ny anställd: person, försäkring, förmån och `premium_paying` i en
>   transaktion, PR-ITP1-012/013, `APPROVAL`),
> - `update_current_salary` (aktuell lön som stamdata, skild från löneunderlaget i PR-ITP1-014, `HUMAN_ONLY`
>   utan produktregel),
> - `update_contact_details` (e-post och telefon, PR-ITP1-031, `HUMAN_ONLY`),
> - `register_employer` (`HUMAN_ONLY`) och `list_employers` (`AGENT`)[, samt `update_employer_details`
>   (`HUMAN_ONLY`)].
>
> Ingen schemaändring. Försäkringens `signed_date` och `start_date` sätts till den dokumenterade
> ITP1-tillhörighetsdagen. Personer under 25 år ansluts med `premium_paying` från tillhörighetens start, och
> premien börjar i 25-årsmånaden. Återanställning, arbetsgivarbyte, anslutning med undantagskategori, framtida
> datum och anslutning från 66 år blockeras med skäl och regel. Anslutningen skapar ingen premie och skickar
> inget besked.
>
> **Motivering:** UI:t får bara anropa tjänstelagret (B-028), och de här åtgärderna behövs för vardaglig
> handläggning. Modellen bär dem utan schemaändring. Det som kräver anställnings- eller lönehistorik blockeras i
> stället för att skriva över data. Aktuell lön hålls isär från pensionsmedförande lön, som B-030 krävde.
>
> **Konsekvenser:** Åtkomstregistret får sex rader, förteckningen genereras om och `tjänstelager.md` §9 och
> `handläggar-ui.md` uppdateras. Anställningshistorik, lönehistorik, namnbyte, arbetsgivarens avslut och
> försäkringsbesked läggs i ATT_GORA.
>
> **Preciserar:** B-028 och B-030.
