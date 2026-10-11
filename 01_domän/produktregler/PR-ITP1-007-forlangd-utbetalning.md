# PR-ITP1-007 – förlängd utbetalningstid

> **Version:** 0.1 | **Granskningsstatus:** Utkast | **Implementation:** Saknas
> **Ägare:** Operatören | **Upprättad:** 2026-10-11 | **Godkänd av/datum:** Ej godkänd
> **Ursprung:** ITP:s flexibilitetsöverenskommelse; föreslagna bolagsval för ändringsplan.

## Källor, giltighet och indata

K-ITP-FLEX, K-IL-UTTAG-2026 58 kap. 11–11 b och 20 §§ samt bolagsjämförelse
K-ALECTA-UTTAG-2026 §8, se
[T-ITP1-003](../../04_regulatoriskt/tolkningar/T-ITP1-003-tidsbegransad-utbetalning.md).
[Gemensamma förutsättningar](UTTAG_GEMENSAMT.md) gäller, inklusive giltighet,
frist och dokumenterat godkännande.

Indata: befintlig tidsbegränsad plan, gammalt totalantal månader `N`, önskat
nytt totalantal `N_ny` eller livsvarig form, ändringsmånad, förbrukade
månadsrätter `D` vid ändring samt kapital och godkänd beräkningsgrund.
Ny total tid ska anges från ursprunglig start, inte från ändringsmånaden.

## Regel och utfall

1. Första utbetalningen ska ha börjat och planen fortfarande ha tid kvar
   vid ändringen. Försäkringen kan vara `in_payout` eller `payout_paused`.
   Val före första start hanteras enligt PR-ITP1-006. Avslutad plan återöppnas
   inte som en förlängning och ålderspension förlängs inte efter dödsfall.
2. Vid tidsbegränsad förlängning krävs helt antal `N_ny > N`, minst 60
   månader totalt. Ny återstående tid är `N_ny − D`, inte `N_ny` nya
   månader. Samma total tid ändrar inte planen; kortare tid avslås enligt
   föreslaget villkor. Kunden ska bekräfta total och återstående tid.
3. Föreslaget bolagsval medger även övergång till livsvarig form, efter
   särskild aktuariell och skatterättslig prövning. Detta får inte godkännas
   enbart genom att sätta ett mycket stort antal månader. En redan
   livsvarig plan kan inte förlängas till ett senare slutdatum eller
   omvandlas till tidsbegränsad form efter start enligt detta förslag.
4. Tillämpa gemensam frist; ändringen ska få effekt senast planens sista
   kvarvarande utbetalningsmånad. Sen begäran går till manuell prövning
   utan att sista utbetalningen stoppas automatiskt eller görs ogjord.
   Upprepade förlängningar tillåts, även efter fem utbetalningsår, utan
   särskild ändringsavgift eller hälsoprövning. Ingen fast maxlängd införs.
5. Räkna om framtida månadsbelopp och kontrollera tillämplig skatte-/avtalsgren.
   Kunden får nytt belopp eller tydligt markerad prognos samt ny slutmånad
   före bekräftelse. Belopp kan ändras; inget bestämt förhållande mellan
   gamla och nya belopp garanteras. Äldre månadsrätter ändras inte.
6. Vid paus behålls avtalad återstart. Förlängning är inte i sig ett
   återstartbeslut och pausmånader räknas inte in i förbrukad tid.
   Beloppsbeslut för återstart samordnas med PR-ITP1-005; ingen dubbel
   ändringsplan eller dubbel omräkning med samma effekt skapas.
7. Verkställ först när kontrollerna är klara och giltighetsmånaden infaller.
   Bevara ursprunglig start och förbrukad tid. Om ändringen inte kan
   godkännas ska den befintliga giltiga planen fortsätta; oklar ny
   beräkningsgrund får inte tyst upphäva ett befintligt betalningsbeslut.

## Acceptansfall

| Fall | Förväntat utfall |
|---|---|
| 12 månader förbrukade av 60, ändras till 120 totalt | 108 månader återstår efter ändringen |
| 59 av 60 förbrukade, ändras till 61 totalt, frist uppfylld | Två återstår; inte krav på 60 nya månader |
| Start november 2026, 12 förbrukade, tre pausmånader; 120 totalt från återstart februari 2028 | 108 återstår, sista planerade månad januari 2037 |
| Ändring till 120 totalt begärs under paus | Pausen och avtalad återstart består |
| 72 av 120 förbrukade, ändras till 180 totalt | Kan prövas också efter fem utbetalningsår; 108 återstår |
| 60 ändras till 48 efter start | Avslag enligt föreslaget bolagsvillkor |
| 60 ändras till livsvarigt | Särskild prövning; ingen automatisk utfästelse utan godkänd grund |
| Sista månaden redan slutbetald och planen avslutad | Ingen återöppning enligt denna regel |

## Implementation och öppna frågor

Ingen kod finns. Aktuariell grund, garanti, tillämplig skatterätt och
versionshanterad uttagsplan behövs före driftsättning. Bolagsval, inklusive
övergång till livsvarigt och hantering nära sista utbetalningen, behöver
godkännas tillsammans med villkorsförslaget.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Första regel för förlängning |
