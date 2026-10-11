# PR-ITP1-006 – tidsbegränsad utbetalning

> **Version:** 0.1 | **Granskningsstatus:** Utkast | **Implementation:** Saknas
> **Ägare:** Operatören | **Upprättad:** 2026-10-11 | **Godkänd av/datum:** Ej godkänd
> **Ursprung:** ITP1:s minimitid; föreslagna bolagsval för månadsplan och administration.

## Källor, giltighet och förutsättningar

K-ITP-AVTAL-2026 punkt 7.5 och K-IL-UTTAG-2026 58 kap. 11–11 b och 20 §§,
med bolagsjämförelser enligt
[T-ITP1-003](../../04_regulatoriskt/tolkningar/T-ITP1-003-tidsbegransad-utbetalning.md).
[Gemensamma förutsättningar](UTTAG_GEMENSAMT.md) gäller, inklusive frist,
godkännande och ännu inte bestämt ikraftträdande.
Startålder prövas separat enligt PR-ITP1-002/003; tidsval ändrar inte åldersrätten.

Regeln avser hela uttaget från en vald ITP1-försäkring. Partiell eller blandad
utbetalningsform inom samma försäkring går till manuell utredning.

## Indata och regel

Utöver gemensam indata behövs valt totalt antal utbetalningsmånader `N`,
första startmånad `S`, redan förbrukade månadsrätter `D`, planerade
pausperioder och godkänd aktuariell grund med garantihantering.

1. Utan aktivt annat val används livsvarig form. För tidsbegränsad form
   ska den försäkrade välja ett helt antal månader `N ≥ 60` före första
   start enligt gemensam frist. Förslaget inför ingen fast maxlängd.
   Negativt, saknat eller icke-helt antal kompletteras eller avvisas.
2. Före första start kan valt antal månader ändras, även förkortas, så
   länge den nya planen uppfyller minimitiden och fristen. Efter start
   används PR-ITP1-007 för förlängning; förkortning tillåts inte i förslaget.
3. Visa form, start, planerad sista utbetalningsmånad, beräknat brutto-
   månadsbelopp och att pensionen upphör efter vald tid. Markera prognos
   respektive beslutat belopp; nettobelopp kräver separat skatteavdrag.
4. Utan paus är sista utbetalningsmånad `S + (N − 1)` månader.
   Förbrukad tid ökar en gång per månadsrätt enligt planen, inte per
   bankförsök. Återstående tid är `N − D`. Pausmånader förbrukar ingen tid.
   Avtalad slutmånad flyttas med pausmånaderna enligt PR-ITP1-004/005.
5. Beräkna månadsbelopp enligt godkänd aktuariell grund, kapital och
   återstående tid. Spåra regel- och grundversion samt garanti/överskott.
   Förutbestämd period innebär inte ett oföränderligt belopp. En formel
   `kapital / N` får inte ersätta den godkända beräkningsgrunden.
   Se [modellutkast till aktuariell grund](../aktuariell_grund.md) och
   [PR-ITP1-009](PR-ITP1-009-pensionsbelopp.md); tariffer är ännu inte godkända.
6. Efter sista avtalade månadsrätten ska inga nya månadsbelopp skapas från
   planen. Obetalda äldre belopp ligger kvar för avräkning. Automatisk
   försäkringsavslutning kräver att inga skyldigheter eller andra relevanta
   flöden återstår. Kapital får inte automatiskt sättas till noll eller
   betalas ut som en extra klumpsumma; slutavräkning behöver egen grund.
7. Vid dödsfall har dödsfallsregeln företräde. Återstående utbetalningstid
   är inget löfte om betalning till efterlevande. Dödsmånadens slutavräkning
   och kapitalbehandling hanteras separat inom ålderspensionsprodukten.

## Acceptansfall

| Fall | Förväntat utfall |
|---|---|
| Val 59 månader | Avslag för ordinarie ITP1 |
| Val 60, 61 eller 120 månader | Tidsvalet kan godkännas; övriga förutsättningar prövas separat |
| Val 300 månader | Ingen automatisk avvisning enligt en generell 20-årsgräns; föreslaget erbjudande har ingen sådan gräns |
| Start november 2026, 60 månader, ingen paus | Sista planerade månad oktober 2031 |
| Samma plan, paus november 2027–januari 2028 | Återstart februari 2028; 48 månader återstår, sista månad januari 2032 |
| 120 månader ändras till 60 före start i rätt tid | Kan prövas; ändringen är före start |
| Samma förkortning efter start | Avslag enligt föreslaget bolagsvillkor |
| Sista månadsrättens banköverföring misslyckas | Betalningen kvarstår som skuld; ingen ny månadsrätt skapas vid nytt försök |

## Utfall, implementation och öppna frågor

Utfall är en versionshanterad plan, komplettering, manuell prövning eller
motiverat avslag enligt gemensamt dokument. Datamodell, garanti,
aktuariell grund, informationsrutiner och slutavräkning återstår.
Ingen kod är byggd och ingen beslutsloggpost eller villkorsversion antas här.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Första regel för tidsbegränsad utbetalning |
