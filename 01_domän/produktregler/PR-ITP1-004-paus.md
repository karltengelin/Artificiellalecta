# PR-ITP1-004 – paus i pågående utbetalning

> **Version:** 0.1 | **Granskningsstatus:** Utkast | **Implementation:** Saknas
> **Ägare:** Operatören | **Upprättad:** 2026-10-11 | **Godkänd av/datum:** Ej godkänd
> **Ursprung:** ITP:s flexibilitetsöverenskommelse; föreslagna bolagsval för pausplan.

## Källor, giltighet och indata

K-ITP-FLEX, K-IL-UTTAG-2026 58 kap. 11–11 b §§ och jämförelse
K-ALECTA-UTTAG-2026 §8, se [T-ITP1-002](../../04_regulatoriskt/tolkningar/T-ITP1-002-uttag-och-paus.md).
[Gemensamma förutsättningar](UTTAG_GEMENSAMT.md) gäller. Indata omfattar
vald försäkring, pausens första månad och avtalad återstartsmånad.

## Regel och utfall

1. Försäkringen ska ha ett pågående uttag (`in_payout`), och utbetalningstid
   ska återstå vid pausstart. Ännu inte påbörjat uttag hanteras som ändrad
   första start, inte paus. Avslutad utbetalning kan inte pausas.
2. Enligt föreslaget bolagsval pausas hela pågående uttaget från vald
   försäkring i hela månader. Återstart ska ligga minst en månad efter
   pausstart. Partiell paus inom samma försäkring går till manuell utredning.
   Andra försäkringar för samma person fortsätter enligt sina planer.
3. Tillämpa gemensam ansökningsfrist. Ingen särskild pausavgift eller
   hälsoprövning. Ingen begränsning till första fem åren, ett enda tillfälle
   eller uttag startade efter lagändringen införs i föreslaget ITP-villkor.
4. Vid verkställighet ändras tillståndet till `payout_paused`; inget nytt
   månadsbelopp för pausmånaderna skapas. Redan intjänade men obetalda
   belopp från tidigare månader påverkas inte av pausbeslutet.
5. Förvaltning och ordinarie kapitalavgift fortsätter. Premieplikten ändras
   inte genom paus. En tidsbegränsad plan behåller återstående antal
   utbetalningsmånader; pausen förskjuter planens slut med pausmånaderna.
   Livsvarig pension får inget slutdatum av pausen.
6. Bekräfta pausperiod, återstart och påverkan på planerat slut. Ändring av
   återstart ersätter befintlig pausplan och följer PR-ITP1-005.

## Acceptansfall

| Fall | Förväntat utfall |
|---|---|
| Paus november 2026–januari 2027, återstart februari | Tre pausmånader, inget nytt månadsbelopp dessa månader |
| 60-månadersplan med 12 förbrukade månader | 48 återstår också efter tre månaders paus; slut flyttas tre månader |
| Två försäkringar, begäran gäller bara den ena | Endast vald försäkring pausas |
| Begäran om att pausa halva samma utbetalning | Manuell utredning, ingen automatisk kapitaldelning |
| Paus efter sex års livsvarigt uttag | Kan prövas; ingen automatisk femårsgräns |
| Ingen första utbetalning har skett | Ändra startplan, inte övergång till `payout_paused` |

## Återstår och versionshistorik

Data- och betalningsflöde enligt gemensamt dokument måste byggas.
En tillsvidarepaus utan avtalad återstart omfattas inte av detta utkast;
det är en administrativ avgränsning som behöver godkännas. Ingen kod finns.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Första utkast |
