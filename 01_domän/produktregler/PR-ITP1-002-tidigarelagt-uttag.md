# PR-ITP1-002 – tidigarelagt uttag

> **Version:** 0.1 | **Granskningsstatus:** Utkast | **Implementation:** Saknas
> **Ägare:** Operatören | **Upprättad:** 2026-10-11 | **Godkänd av/datum:** Ej godkänd
> **Ursprung:** ITP-avtalets åldersram; föreslagna bolagsval för månader och pensioneringskontroll.

## Källor, giltighet och indata

K-ITP-AVTAL-2026 punkt 7.5, K-IL-UTTAG-2026 58 kap. 10 § och
K-ALECTA-UTTAG-2026 §8, se [T-ITP1-002](../../04_regulatoriskt/tolkningar/T-ITP1-002-uttag-och-paus.md).
[Gemensamma förutsättningar](UTTAG_GEMENSAMT.md) gäller, inklusive status,
villkorskoppling, begäransfrist och kommande godkännande/ikraftträdande.

Utöver gemensam indata behövs intyg om arbete, tillgänglighet på
arbetsmarknaden och relevant extern ersättning vid önskad start.
Efterfråga inte medicinska diagnoser för detta och inför ingen hälsoprövning.

## Regel och utfall

1. Första uttaget ska ännu inte ha påbörjats. Önskad månad ska vara före
   66-årsmånaden och, enligt föreslaget bolagsval, tidigast månaden efter
   55-årsmånaden. Start från 66-årsmånaden är ordinarie eller senare start.
2. Kontrollera komplett begäran enligt gemensam frist. Livsvarigt eller
   minst 60 utbetalningsmånader kan väljas.
3. **Föreslaget villkor för helt förtida uttag:** Den försäkrade intygar att
   arbete och tillgänglighet på arbetsmarknaden vardera understiger åtta
   timmar per vecka samt att hen inte får eller har ansökt om sjukpenning,
   sjukersättning eller arbetsskadeersättning från Försäkringskassan eller
   utländsk motsvarighet vid starten.
4. Partiellt uttag, partiell ersättning och andra undantag skickas till
   manuell utredning. Ingen automatisk uppdelning av försäkringen eller
   utvidgning av produktscope görs. Fullt arbete som inte uppfyller föreslaget
   villkor ger motiverat avslag på helt förtida uttag.
5. Begäran före 55 år avslås enligt ordinarie avtalsregel; åberopat
   skatteundantag går till separat avtalsprövning. Ingen automatisk utbetalning.
6. Godkänd begäran skapar en plan. Vid start sker beloppsberäkning enligt
   godkänd aktuariell grund och övergång till `in_payout`. Tidigare start
   medför inget löfte om ett bestämt belopp eller en bestämd minskning.

## Acceptansfall

| Fall | Förväntat utfall i förslaget |
|---|---|
| Född 1971-10-15, start oktober 2026 | För tidigt enligt föreslagen månadsgräns; avtalsåldern och bolagsvalet skiljs åt |
| Samma person, november 2026, komplett begäran 31 oktober och villkoren uppfyllda | Kan godkännas, förutsatt godkänd beräkningsgrund |
| Samma start, begäran 1 november | Ingen retroaktiv start; nästa månad föreslås för bekräftelse |
| Helt uttag vid 60 år, fortsatt arbete 40 timmar/vecka | Avslag enligt föreslaget pensioneringsvillkor |
| 25 % uttag och partiell extern ersättning | Manuell utredning, inte heluttagsregeln |
| Vald tid 36 månader | Avslag för ordinarie ITP1; skatterättsliga undantag överförs inte automatiskt |

## Återstår och versionshistorik

Pensioneringsvillkoret behöver operatörens godkännande och avtalskontroll
mot ITP-nämndens tillämpliga bestämmelser. Partiella uttag kräver egen regel
och modell. Ingen kod eller tekniska tester finns för denna regel.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Första utkast |
