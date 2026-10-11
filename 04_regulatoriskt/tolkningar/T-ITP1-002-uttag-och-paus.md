# T-ITP1-002 – uttagsålder, uppskjutande och paus

> **Status:** Utkast | **Version:** 0.2 | **Ägare:** Operatören
> **Upprättad och källkontrollerad:** 2026-10-11 | **Godkänd av/datum:** Ej godkänd
> **Omfattning:** ITP1 ålderspension enligt B-002, B-021 och B-022. Ingen implementation.

## Fråga och källunderlag

Vilka externa krav och egna villkor behövs för tidigarelagd start, uppskjuten
start, paus i pågående utbetalning och återupptagande?

Se [källregistret](../kallregister.md) för daterade länkar och avgränsningar.

| Källa | Bestämmelse/avsnitt | Användning |
|---|---|---|
| K-ITP-AVTAL-2026 | Avdelning 1, punkt 7.5 | Ålder och utbetalningsform |
| K-IL-UTTAG-2026 | 58 kap. 10–11 b och 20 §§ | Skatterättsliga ramar och tillämplighet |
| K-ITP-FLEX | Avtalats information om parternas överenskommelse | Paus och förlängning inom ITP |
| K-ALECTA-UTTAG-2026 | Försäkringsvillkor §8 och information om paus | Jämförelse för operativa bolagsval, inte vårt avtal |

## Resonemang och slutsatser

**Ålder och form:** Avtalspunkt 7.5 ersätter vårt tidigare antagande om 63 år.
Den stöder inte heller vår generella slutgräns på 70 år. Reglerna nedan använder
avtalets åldrar och form; månadernas detaljhantering anges som eget bolagsval.
ITP2:s regler om uppskjutet uttag får inte överföras till ITP1.

**Skatt:** 58 kap. 10 § har undantag från huvudgränsen vid sjukersättning eller
Skatteverkets medgivande. Ett skatteundantag ger inte i sig rätt till tidigare
ITP1-uttag. Sådana ansökningar behöver separat avtalsprövning.

11 § medger paus och förlängning under de första fem utbetalningsåren och
reglerar beloppsförloppet. 11 a § medger vissa sänkningar. För tidsbegränsad
pension enligt allmän pensionsplan hänvisar 11 b § i stället till planen.
Tillämplig gren ska därför fastställas innan en beloppskontroll byggs. Ett
ovillkorligt krav på samma eller högre belopp efter varje paus vore fel.
Den simulerade produkten är inte automatiskt en godkänd allmän pensionsplan
bara för att dokumentet använder namnet ITP1; definitionen i 20 § ska prövas.

**Paus:** Lagstiftningens möjlighet och ITP-överenskommelsens rättigheter ska
skiljas från bolagens ansökningsfrister. En paus stoppar utbetalning; den
upphäver inte försäkringen eller automatiskt arbetsgivarens premieplikt.
Kapitalet förvaltas också under pågående uttag och behöver därför inte
”återgå” till förvaltning vid paus.

**Pensioneringssyfte:** Alectas villkor kräver prövning av arbete,
arbetsmarknadstillgänglighet och vissa ersättningar vid förtida uttag.
Vi föreslår motsvarande kontroll för helt uttag. Det är ett föreslaget
bolagsvillkor med detta jämförelseunderlag; punkt 7.5 ensam fastställer inte
detaljerna. Partiellt uttag och ersättningskombinationer lämnas till manuell
utredning, inte automatisk rätt eller automatiskt avslag.
Det innebär inte att bolaget erbjuder sjukpension eller sjukförsäkring.

## Föreslagna bolagsval och alternativ

| Fråga | Förslag för simuleringen | Alternativ/avgränsning |
|---|---|---|
| Första tidiga utbetalningsmånad | Månaden efter 55-årsmånaden | Avtalet anger ålder; val av denna månadsgräns är vårt förslag |
| Ansökningstid | Komplett begäran senast sista dagen i föregående månad, svensk tid | Annan frist kan väljas; ingen extern universell frist har fastställts |
| Pausens omfattning | Hela pågående uttaget från vald försäkring | Partiellt uttag inom försäkring kräver separat design |
| Pausens längd | Hela månader, minst en, ingen fast maxlängd eller antal | Återstartsdatum bestäms; tillsvidarepaus behöver egen rutin |
| Tidsbegränsad pension | Minst 60 utbetalningsmånader; paus förbrukar inga månader | Se PR-ITP1-006/007 och T-ITP1-003 för tidsval och förlängning |
| Förkortning efter start | Tillåts inte i föreslaget villkor | Bolagsval; inte ett påstående om ett generellt lagförbud |

## Operativa konsekvenser

- [PR-ITP1-002](../../01_domän/produktregler/PR-ITP1-002-tidigarelagt-uttag.md): start före ordinarie ålder.
- [PR-ITP1-003](../../01_domän/produktregler/PR-ITP1-003-uppskjutet-uttag.md): ändra ännu inte påbörjad start.
- [PR-ITP1-004](../../01_domän/produktregler/PR-ITP1-004-paus.md): stoppa pågående utbetalning.
- [PR-ITP1-005](../../01_domän/produktregler/PR-ITP1-005-aterupptagande.md): starta efter paus.
- [Gemensamma förutsättningar](../../01_domän/produktregler/UTTAG_GEMENSAMT.md): granskning, data och systemkoppling.
- [Förslag till villkorsändring](../../projekt/04_produktregelverk/VILLKORSANDRING_UTTAG.md): ersättning av §7, ej antagen.

## Giltighet och öppna frågor

Källkontrollen avser förhållandena 2026-10-11. Den ger ingen retroaktiv
giltighet åt bolagsvalen. Operatören behöver godkänna valen och övergången till
ny villkorsversion innan implementation. Aktuariell grund, garantin F-004,
allmän pensionsplan och partiella uttag måste utredas före automatiska beslut
om berörda uttag. Tidsbegränsad utbetalning och förlängning beskrivs separat i
[T-ITP1-003](T-ITP1-003-tidsbegransad-utbetalning.md) och PR-ITP1-006/007.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Första källgrundade uttagsutkast |
| 0.2 | 2026-10-11 | Hänvisning till tidsbegränsad utbetalning och förlängning |
