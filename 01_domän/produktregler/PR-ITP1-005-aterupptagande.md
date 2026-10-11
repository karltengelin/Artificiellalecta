# PR-ITP1-005 – återupptagande efter paus

> **Version:** 0.2 | **Granskningsstatus:** Utkast | **Implementation:** Saknas
> **Ägare:** Operatören | **Upprättad:** 2026-10-11 | **Godkänd av/datum:** Ej godkänd
> **Ursprung:** ITP:s flexibilitetsöverenskommelse; egna verkställighets- och beräkningskrav.

## Källor, giltighet och indata

K-ITP-FLEX, K-IL-UTTAG-2026 58 kap. 11–11 b §§ och jämförelse
K-ALECTA-UTTAG-2026 §8, se [T-ITP1-002](../../04_regulatoriskt/tolkningar/T-ITP1-002-uttag-och-paus.md).
[Gemensamma förutsättningar](UTTAG_GEMENSAMT.md) gäller. Indata omfattar
aktiv pausplan, faktisk tidigare start, återstående tid, kapital,
aktuariell grund/version och tillämplig skatterättslig gren.

## Regel och utfall

1. Försäkringen ska vara `payout_paused` med återstående rätt till pension.
   Avtalad återstart verkställs utan ny ansökan. Önskad ändring ska vara
   komplett enligt gemensam frist före ändringsmånaden. Framtida ändring
   får inte skapa en överlappande pausplan eller en andra första start.
2. Kontrollera livs-/avslutsstatus före verkställighet. Ingen återstart efter
   dödsfall eller avslut, och inget nytt efterlevandeskydd genom återstart.
3. Räkna om månadsbeloppet med kapital, aktuell ålder, återstående tid och
   godkänd aktuariell grund. Kontrollera tillämpliga beloppskrav enligt
   58 kap. 11–11 b §§ och avtal; samma eller högre belopp får inte
   förutsättas utan denna prövning. Saknad grund ger manuell prövning och
   blockerad automatisk betalning, inte nollbelopp eller uppskattat belopp.
4. Bekräfta nytt belopp, återstart och planerat slut. Övergå till `in_payout`
   först vid faktisk verkställighet. Första ursprungliga startdatumet och
   tidigare utbetalningshistorik ska behållas.
5. Inga retroaktiva belopp skapas för avtalade pausmånader. Återstart är
   inte en ny 60-månadersperiod: tidigare förbrukade månader räknas av.
   En förlängning utöver pausens effekt kräver eget beslut enligt
   [PR-ITP1-007](PR-ITP1-007-forlangd-utbetalning.md).
   Förkortning efter första start tillåts inte i föreslaget villkor.
6. Ingen särskild ändringsavgift eller hälsoprövning införs för återstarten.
   Ny förtida pensioneringsprövning vid återstart införs inte automatiskt;
   ursprungliga villkor och ändrade förhållanden behöver separat utredning.

## Acceptansfall

| Fall | Förväntat utfall |
|---|---|
| Paus november–januari, avtalad återstart februari | Återstart februari utan ny ansökan efter kontroller |
| 12 av 60 månader förbrukade före paus | 48 utbetalningsmånader återstår, inte 60 nya |
| Återstart flyttas från februari till mars med komplett begäran i januari | Ersatt plan; ytterligare en pausmånad och motsvarande förskjutet slut |
| Dödsfall i januari före avtalad februariåterstart | Ingen februariutbetalning eller återstart |
| Beräknat belopp lägre än före paus | Pröva skatte-/avtalsgrund; varken generellt avslag eller automatiskt godkännande |
| Aktuariell grund saknas | Automatisk betalning blockeras och manuell prövning skapas |

## Återstår och versionshistorik

Aktuariell grund, garanti och tillämplig skatte-/avtalsgren är nödvändiga före
beloppsimplementation. Regler för misslyckad teknisk verkställighet behöver
säkerställa att en avtalad återstart inte felaktigt registreras som fortsatt
frivillig paus. Ingen kod finns för denna regel.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Första utkast |
| 0.2 | 2026-10-11 | Koppling till separat förlängningsregel |
