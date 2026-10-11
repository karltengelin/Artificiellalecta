# PR-ITP1-009 – pensionsbelopp och rörligt tillägg

> **Version:** 0.1 | **Granskningsstatus:** Utkast | **Implementation:** Saknas
> **Ägare:** Operatören | **Datum:** 2026-10-11 | **Godkänd av/datum:** Ej godkänd
> **Ursprung:** Föreslagen utbetalningsmodell inom produktinriktning B-027, inte extern enhetlig tariff.

## Källor, scope och indata

[T-ITP1-004](../../04_regulatoriskt/tolkningar/T-ITP1-004-garanti-och-aktuariell-grund.md),
[aktuariell grund](../aktuariell_grund.md) och
[gemensamma uttagsförutsättningar](UTTAG_GEMENSAMT.md).
Endast ITP1 ålderspension; ingen automatisk ändring av premie eller produktscope.
Ingen giltighetsdag eller teknisk implementation är fastställd.

Indata: godkänd uttagsplan och dess kvarvarande månadsrätter, kapital vid
angiven värderingsdag, garantidelar med grundversioner, godkänd
utbetalningsgrund samt livs-/avslutsstatus och skatte-/avtalsklassificering.

## Regel och utfall

1. Räkna vid första start, återstart, ändrad utbetalningsplan och enligt
   föreslaget bolagsval årligen inför januari. Mellan beslutstillfällena
   gäller senast godkänt belopp om ingen annan giltig ändring inträffar.
2. Fastställ `G` genom att summera garantidelarnas belopp för samma plan.
   Använd inte aktuell utbetalningsgrund för att skriva om garantin.
3. Beräkna kapitalbaserat belopp `B` enligt grunden §6. Föreslaget rörligt
   tillägg är `max(0, B − G)` och brutto-månadsbelopp `max(G, B)`.
   Garantin betalas inte en andra gång ovanpå detta belopp.
4. Pröva tillämpliga skatte-/avtalskrav på beloppsförlopp. Ett tillägg får
   inte sänkas fritt bara för att det kallas rörligt. Prognos, beslutat
   bruttobelopp, skatteavdrag och banköverföring är olika uppgifter.
5. Paus ger inget nytt månadsbelopp för pausmånader. Återstart använder
   återstående rätt, inte en ny full utbetalningsperiod. Originalstart
   och tidigare intjänade delar bevaras.
6. Visa kapital, garantibelopp, tillägg, brutto, grundversioner och planerad
   slutmånad eller livsvarig form. Spara faktorer och underlag med hög
   precision; betald summa avrundas enligt grunden §7.
7. Saknad godkänd grund eller otillräckligt finansierat garantiunderskott
   ger manuell prövning före automatisk verkställighet. Ingen kundgaranti
   skrivs ned och inget kapital skapas utan finansieringstransaktion.
   Ett ogiltigt förslag upphäver inte ett redan giltigt betalningsbeslut.

## Acceptansfall

Syntetiska beloppsfall med angivna faktorer, inte godkända kundtariffer:

| Indata/fall | Utfall |
|---|---|
| `G = 100`, `B = 130` | Tillägg 30, brutto 130, inte 230 |
| `G = 100`, `B = 80` | Tillägg 0, bruttoförslag 100; finansieringen ska kontrolleras |
| Individens kön ändras, övriga indata lika | Samma beräknade pensionsbelopp |
| 48 månadsrätter kvar efter paus | Faktor för 48 rättigheter, inte 60 nya |
| Livsvarig grund saknar hantering av höga åldrar | Blockerad automatisk beräkning, inget uppskattat belopp |
| Rörligt tillägg minskar vid årlig omräkning | Skatte-/avtalsprövning före nytt beslut |

## Återstår

Kalibrering, kostnad/skatt, överskottsfördelning, underskottsfinansiering,
tariffregister och transaktionsmodell. Ordinarie utbetalning, dödsmånad och
slutavräkning behöver kompletterande processregler. B-027 godkänner
produktinriktningen, inte samtliga beräknings- och omräkningsparametrar här.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Första beloppsregel |
