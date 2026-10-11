# PR-ITP1-017 – fakturering och obetalda premier
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Egna administrativa villkor inom kollektivramen.
**Källor:** K-FAL i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-006](../../04_regulatoriskt/tolkningar/T-ITP1-006-premie-lon-och-anslutning.md).
**Villkor:** [§4 i v2.0](../försäkringsvillkor.md).

## Regel

Fakturera månadsvis i efterskott, 30 kalenderdagar från fakturadatum.
Om förfallodagen inte är svensk bankdag flyttas den till nästa bankdag.
Samla godkända premieunderlag och redovisa ordinarie/kompletterande belopp
separat med person, period, rättelse och mottagare. Skatt på arbetsgivarens
pensionskostnad är arbetsgivarens fråga, inte kundkapital eller vår riskpremie.

Saknad/ogiltig lön skapar avvikelse och uppgift till arbetsgivaren.
Inget antagande om föregående lön eller noll. Oberoende korrekta rader
kan faktureras; avvikelsen och senare tilläggsfaktura måste vara synliga.
Dubblett lönerapport ersätter inte senaste giltiga rapport utan uttrycklig
versionsrelation. Omfakturering krediterar gammal post innan ny debiteras.

Efter förfallodag: påminnelse och ärende efter 1 dag, operatörseskalering
efter 30 dagars dröjsmål. Vår simulation tar ingen påminnelseavgift eller
dröjsmålsränta. Förfallna premier är fordringar, inte pensionskapital.
Befintliga mottagna premier/garantier påverkas inte av dröjsmålet.

Ingen automatisk uppsägning, pensionstopp eller radering av tidigare
intjänande vid arbetsgivarens betalningsfel. Verklig kollektivavtalsgaranti/
Collectumfordran måste ha verifierat externt beslut innan den tillförs;
vi skapar inte sådan finansiering i simuleringen.

## Kontrollfall

L=0 giltigt rapporterad: noll premie, inget saknad-lönärende.
L saknas: komplettering, inte noll eller föregående månad.
Betalning saknas: fordran kvar; ingen ny garantidel förrän netto mottas.
