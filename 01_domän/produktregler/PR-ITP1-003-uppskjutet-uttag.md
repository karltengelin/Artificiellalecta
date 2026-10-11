# PR-ITP1-003 – uppskjutet uttag

> **Version:** 0.1 | **Granskningsstatus:** Utkast | **Implementation:** Saknas
> **Ägare:** Operatören | **Upprättad:** 2026-10-11 | **Godkänd av/datum:** Ej godkänd
> **Ursprung:** ITP-avtalets rätt att begära annan start; egna administrativa val.

## Källor, giltighet och indata

K-ITP-AVTAL-2026 punkt 7.5 och jämförelse K-ALECTA-UTTAG-2026 §8,
se [T-ITP1-002](../../04_regulatoriskt/tolkningar/T-ITP1-002-uttag-och-paus.md).
[Gemensamma förutsättningar](UTTAG_GEMENSAMT.md) gäller. Indata omfattar
befintlig planerad start, önskad ny start och utbetalningsform.

## Regel och utfall

1. Uttag får ännu inte ha påbörjats. Normal start är 66-årsmånaden om inget
   annat har begärts. Uppskjutet uttag avser första start efter denna månad.
   Att flytta en tidigare plan till en annan månad före 66 är i stället en
   ändring av tidigarelagt uttag enligt PR-ITP1-002.
2. Begäran ska vara komplett senast månaden före den start som annars skulle
   verkställas. En senare ändring av en uppskjuten plan följer samma frist.
   Redan verkställd start får inte göras ogjord; pröva paus i stället.
3. Registrera ny första startmånad och behåll förvaltningen. Ingen generell
   slutålder på 70 år införs: de kontrollerade källorna ger inte stöd för den.
   Hög ålder får inte ensam utlösa tvångsuttag eller automatiskt avslag.
4. Premieplikt prövas separat. Uppskjutet uttag gör inte försäkringen till
   fribrev och förlänger inte automatiskt arbetsgivarens premieplikt.
5. Vid start beräknas pensionen med då tillämplig godkänd grund. Ett senare
   uttag är inte en garanti för större månadsbelopp. Vald tidsbegränsad
   utbetalning ska vara minst 60 utbetalningsmånader.

## Acceptansfall

| Fall | Förväntat utfall |
|---|---|
| Född 1960-10-15, inget annat val | Normal planerad start oktober 2026 |
| Begäran i september 2026 om start oktober 2028 | Planen ändras före normal start; inget uttag i oktober 2026 |
| Ännu inget uttag, önskad start vid 72 | Ingen avvisning på grund av repots gamla 70-årsgräns |
| Första utbetalning redan verkställd | Inte uppskjutande; pröva paus enligt PR-ITP1-004 |
| Uppskjuten start men premiebetalningen har upphört | Fribrev enligt premiereglerna, oberoende av uppskjutandet |

## Återstår och versionshistorik

Informationsrutinen inför ordinarie start behöver specificeras. Externa
ersättningssituationer som kan påverka startvillkor behöver separat prövning;
Alectas särregel för rätt till ITP sjukpension införs inte automatiskt i vår
produkt. Inget nytt sjukpensionsåtagande skapas. Ingen kod finns för regeln.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Första utkast |
