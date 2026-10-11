# Produktregler – ITP1 ålderspension

> **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Sammanställt dokumentunderlag enligt operatörens uppdrag att färdigställa delprojektet.
> **Ägare:** Operatören. Metadata och gemensamma krav här gäller samtliga PR-filer.
> **Föreslagen tillämpning i simuleringen:** 2026-11-01. Införandet är ett separat beslut; ingen kod eller historik ändras av dokumenten.

Detta är ingången till hela produktspecifikationen. [Försäkringsvillkor v2.0](../försäkringsvillkor.md)
beskriver kundens rättigheter. Reglerna här preciserar utfallet, inklusive undantag,
för nästa byggsession. [Aktuariell grund](../aktuariell_grund.md) och
[parameterregister](../parametrar/PARAMETERREGISTER.md) bestämmer beräkningarna.
[Källregistret](../../04_regulatoriskt/kallregister.md) och tolkningarna visar
vilka externa krav respektive egna bolagsval som ligger bakom.

## Avgränsning och företräde

Endast traditionell ITP1 ålderspension utan återbetalningsskydd. B-002, B-003,
B-021, B-022 och B-027 gäller fortsatt. Flera försäkringar är möjliga för samma
person. Sjukdom och föräldraledighet kan påverka indata eller ge en premie från
en extern betalare; bolaget försäkrar inte dessa risker.

Tvingande tillämplig rätt har företräde framför kollektivavtal, som har företräde
framför egna produktval. Ett gynnande individuellt besked ska utredas enligt FAL,
inte skrivas över av regelmotorn. Olösta verkliga avtalskonflikter går till
behörig människa med båda regelversionerna och det ekonomiska utfallet.
Inom paketet preciserar specialregeln den allmänna regeln. En faktisk motsägelse
blockerar det berörda beslutet tills den är rättad; ingen AI får välja tyst.

**Status betyder dokumentmässigt färdig specifikation, inte driftsatt system,
myndighetsgodkända villkor eller en professionellt validerad försäkringstariff.**
Egna val är gjorda på operatörens mandat i sessionen. Formellt införande och
eventuell beslutsloggspost hanteras samlat i [paketförslaget](../../projekt/04_produktregelverk/PAKET_BESLUTSFORSLAG.md).

## Regelkatalog

| ID | Regel | Huvudsaklig grund |
|---|---|---|
| [001](PR-ITP1-001-premietrappa.md) | Ordinarie premietrappa | ITP 7.1; egen öresavrundning |
| [002](PR-ITP1-002-tidigarelagt-uttag.md) | Tidigarelagt uttag | ITP 7.5; egen pensioneringskontroll |
| [003](PR-ITP1-003-uppskjutet-uttag.md) | Uppskjuten första start | ITP 7.5 |
| [004](PR-ITP1-004-paus.md) | Paus av utbetalning | ITP-flexibilitet; egen månadshantering |
| [005](PR-ITP1-005-aterupptagande.md) | Återupptagande | Återstående månadsrätter |
| [006](PR-ITP1-006-tidsbegransad-utbetalning.md) | Tidsbegränsad utbetalning | ITP 7.5 |
| [007](PR-ITP1-007-forlangd-utbetalning.md) | Förlängning | ITP-flexibilitet; IL 58 kap. |
| [008](PR-ITP1-008-garanti.md) | Intjänad garanti | B-027; egen tariff |
| [009](PR-ITP1-009-pensionsbelopp.md) | Pension och rörligt tillägg | Egen utbetalningsgrund; IL |
| [010](PR-ITP1-010-dodsfall.md) | Dödsfallsavräkning | ITP; egna avräkningsregler |
| [011](PR-ITP1-011-arvsvinster.md) | Faktiska arvsvinster | Eget kollektiv och fördelningsmetod |
| [012](PR-ITP1-012-anslutning.md) | Anslutning och avtalsparter | ITP; FAL 20 kap. |
| [013](PR-ITP1-013-premieperioder.md) | Premieålder, anställning och fribrev | ITP; Collectums administration |
| [014](PR-ITP1-014-loneunderlag.md) | Pensionsmedförande lön | ITP; Collectums löneslagslista |
| [015](PR-ITP1-015-premiefordelning.md) | Flera försäkringar och premieallokering | B-022; eget fördelningsval |
| [016](PR-ITP1-016-kompletterande-premier.md) | Kompletterande och externt finansierade premier | ITP 7.2; egna mottagningsregler |
| [017](PR-ITP1-017-fakturering.md) | Fakturering, rapportfel och obetalda premier | Egna administrativa villkor |
| [018](PR-ITP1-018-premiemottagning.md) | Brutto, netto, matchning och sen premie | B-021/B-027; eget värdedatum |
| [019](PR-ITP1-019-rattelser.md) | Rättelser, återtag och återkrav | Egna spårbara rättelsebeslut |
| [020](PR-ITP1-020-kapitalordning.md) | Kapital och månadsordning | Egen transaktionsmodell |
| [021](PR-ITP1-021-avkastning.md) | Avkastning och överskott | Egen direktfördelning |
| [022](PR-ITP1-022-avgifter.md) | Kapitalavgift | B-021; egen debiteringsbas |
| [023](PR-ITP1-023-avkastningsskatt.md) | Avkastningsskattens kapitalbelastning | AvPL; egen kundfördelning |
| [024](PR-ITP1-024-deluttag.md) | Deluttag och uppdelning | Eget erbjudande inom ITP-ramen |
| [025](PR-ITP1-025-ordinarie-start.md) | Ordinarie start och fortsatt premie | ITP 7.5; egna processfrister |
| [026](PR-ITP1-026-betalning-och-inkomstskatt.md) | Månadsanspråk, bank och inkomstskatt | Skatteverket; egen betalningsjournal |
| [027](PR-ITP1-027-slutavrakning.md) | Sista utbetalning och avslut | Egen slutavräkning inom ITP-planen |
| [028](PR-ITP1-028-garantifinansiering.md) | Garantiunderskott och bolagskapital | B-027; egen finansieringsmodell |
| [029](PR-ITP1-029-information.md) | Besked, prognoser och produktinformation | FAL; FFFS 2019:21 |
| [030](PR-ITP1-030-andringar-och-klagomal.md) | Villkorsändring, klagomål och undantag | FAL; egen ärendehantering |
| [031](PR-ITP1-031-data-och-beslut.md) | Personuppgifter och mänskliga beslut | GDPR; B-006/B-016 |
| [032](PR-ITP1-032-giltighet-och-historik.md) | Giltighet, historik och övergång | Källdatum; egna simuleringsval |
| [033](PR-ITP1-033-forfoganden.md) | Flytt, återköp, pantsättning och behörighet | IL; B-021; FAL |
| [034](PR-ITP1-034-distribution-och-systemkrav.md) | Distribution, hållbarhet, AI och kontinuitet | Tillämplighetsbedömning; egna produktspärrar |

## Gemensamt regelkontrakt

Alla PR-ITP1-filer ingår i v1.0-paketet; separat filversion kan ökas senare.
Indata ska alltid innehålla identifierad person/avtal/förmån/uttagsdel, händelse-ID,
händelsedatum, mottagningsdatum, avsändarens behörighet och de käll-/parameterversioner
som faktiskt används. Inget standardvärde ersätter saknad obligatorisk uppgift.

Utfall är **godkänd**, **avslagen med regelgrund**, **komplettering** eller
**manuell prövning**. Ett blockerat nytt förslag upphäver inte tidigare rättigheter.
Ett manuellt ärende är en definierad produktprocess: begär angiven uppgift, beräkna
alternativen, låt behörig människa välja rättsligt tillåtet utfall och dokumentera
motivering, ekonomiska motposter och besked. Handläggning skapar ingen dispens
från kollektivavtal eller lag.

Månader avser kalenderperioder i Europe/Stockholm. Pengar redovisas i SEK.
Premier och utbetalningar avrundas med ROUND_HALF_UP till ören, med
PR-009:s avrundningsskydd för utbetalningsbart garantigolv; proportionella
kapitalfördelningar använder största bråkrest så att totalen bevaras.
Aktuariella mellanvärden behåller minst 12 signifikanta siffror. Händelser
raderas inte. Samma händelse-ID får bara ge ett ekonomiskt utfall.

Den konceptuella datamodellen och [täckningskontrollen](../../projekt/04_produktregelverk/LEVERANSKONTROLL.md)
beskriver vad byggsessionen behöver bevara. Databasmigration, regelkod och
automatiserade tester ingår enligt uppdraget inte i denna leverans.
