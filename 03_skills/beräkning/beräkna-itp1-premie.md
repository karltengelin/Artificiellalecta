# Skill: Beräkna ITP1-premie

> **Kategori:** beräkning
> **Implementation:** `src/skills/calculation/calculate_itp1_premium.py`
> **Domänregler:** `01_domän/ITP1_regelverk.md` §2–§4, §8
> **Behörighet:** Ingen PII-åtkomst – skillen arbetar på lönebelopp och datum, inte personuppgifter. Fri att använda för alla agenter (B-006 ej tillämplig)
> **Status:** 🟢 Implementerad (Fas 1c)

---

## Syfte

Beräknar ålderspensionspremie enligt ITP1:s premietrappa för en given månadslön och premiemånad. Detta är bolagets premiemotor – all premieberäkning i systemet ska gå genom denna skill, aldrig egna ad hoc-formler.

## Ingångar

| Parameter | Typ | Beskrivning |
|---|---|---|
| `monthly_salary_sek` | Decimal | Pensionsmedförande lön för månaden (regelverket §3) |
| `income_base_amount_sek` | Decimal | IBB för premieåret (hämtas ur `base_amounts`-tabellen) |
| `birth_date` | date *(valfri)* | Den försäkrades födelsedatum – aktiverar åldersfönsterkontroll |
| `period_month` | date *(valfri)* | Premiemånaden – krävs om `birth_date` anges |
| `parameters` | PremiumParameters *(valfri)* | Åldersgränser, satser, brytpunkter och versionsetiketter. Tjänstelagret hämtar premiemånadens värden ur `product_parameters`; direktanrop utan parametrar använder paketets startvärden |

## Utfall

`PremiumCalculation` med:

- `total_premium_sek` – total månadspremie, avrundad till hela ören
- `amount_low_sek` / `amount_high_sek` – lägre respektive högre premiedelen (startvärden 4,5 % och 30 %)
- `calculation_basis` – dict med IBB, brytpunkter och satser, redo att lagras i `premium_transactions.calculation_basis` (spårbarhet, databasschema §6)
- `in_age_window` – om personen är i parametrarnas premiefönster, med startvärden 25–66 (bara när `birth_date` givits; utanför fönstret blir premien 0)

## Regler (regelverket §8)

1. Trappans startvärden: 4,5 % av lön upp till 7,5 × IBB/12; 30 % av lönedel mellan 7,5 och 30 × IBB/12; 0 % däröver. Godkända versionerade parametrar kan ändra satser och brytpunkter
2. Brytpunkter härleds ur IBB – aldrig hårdkodade belopp
3. Åldersfönster på **månadsnivå** enligt `parameters.age_start`/`age_end`, med startvärden från 25-årsmånaden till månaden före 66
4. Premie ≥ 0, avrundas till hela ören (ROUND_HALF_UP)
5. Negativ lön ger fel (ValueError) – korrigeringar hanteras som `adjustment`-transaktioner, inte negativa premier

## Exempel (IBB 2026 = 83 400 kr, brytpunkt 52 125 kr/mån)

| Månadslön | Premie | Kommentar |
|---|---|---|
| 35 000 kr | 1 575,00 kr | 4,5 % rakt av |
| 52 125 kr | 2 345,63 kr | Exakt på brytpunkten |
| 80 000 kr | 10 708,13 kr | 2 345,63 + 30 % × 27 875 |
| 250 000 kr | 49 258,13 kr | Taket: lön över 208 500 ger ingen premie |

## Avgränsningar

- Hämtar **inte** data själv – anroparen ansvarar för lön (lönerapport) och IBB (`base_amounts`). Skillen är en ren beräkningsfunktion, deterministisk och lätt att testa
- Skapar inga transaktioner – det gör anropande flöde (Fas 1d/premiekörning)
