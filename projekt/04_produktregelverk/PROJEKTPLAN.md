# Projekt 4 – produktregelverk och försäkringsvillkor

> **Leverans:** 2026-10-11 | **Status:** Dokumentunderlag färdigställt enligt sessionens utökade uppdrag.
> Del av programmet i MASTER_CONTEXT §4b, B-024. Samlat införande är separat.

## Uppdrag och resultat

Färdigställa en sammanhängande uppsättning produktregler och villkor för
**traditionell ITP1 ålderspension utan efterlevandeskydd** som försäkringssystemet
sedan kan byggas efter. Operatören har gett mandat att göra efterforskningar,
egna tolkningar och produktval för hela dokumentpaketet i samma session.

[Produktpaket PR-ITP1 v1.0](../../01_domän/produktregler/README.md) innehåller
34 regler och ett gemensamt regelkontrakt. [Villkor v2.0](../../01_domän/försäkringsvillkor.md)
täcker hela livscykeln. [Aktuariell grund](../../01_domän/aktuariell_grund.md)
och [parameterregister](../../01_domän/parametrar/PARAMETERREGISTER.md)
anger valda SIM-grunder, faktisk sparad SCB-tabell och exakta årsparametrar.

[Regelverkskartan](../../04_regulatoriskt/regelverkskarta.md), källregistret,
underlag per regelverk och tio tolkningar visar externa krav och egna val.
[Leveranskontrollen](LEVERANSKONTROLL.md) visar täckning, räkneexempel,
dokumentkontroller och gränssnitt till andra projekt.
[Paketförslaget](PAKET_BESLUTSFORSLAG.md) samlar det formella införandet.

## Färdiga områden

| Område | Regler |
|---|---|
| Tillhörighet, premieålder, anställning, lön och premietrappa | 001, 012–014 |
| Fördelning, komplettering, fakturering, mottagning och rättelse | 015–019 |
| Kapital, avkastning, avgift och avkastningsskatt | 020–023 |
| Garanti, pensionsbelopp och bolagsfinansiering | 008–009, 028 |
| Ordinarie/tidig/sen start, deluttag och tidsbegränsad/livsvarig plan | 002–003, 006, 024–025 |
| Paus, återstart och förlängning | 004–005, 007 |
| Bank, inkomstskatt, sista rätt, dödsfall och arvsvinst | 010–011, 026–027 |
| Information, ändring, klagomål, data och förfoganden | 029–031, 033 |
| Giltighet/historik och tvärgående produktkrav | 032, 034 |

Tidigare frågor F-001–008 är dokumentmässigt lösta; slutsatser och
hänvisningar finns i [arbetssättet](ARBETSSATT.md). Äldre delförslag om
uttag, garanti och dödsfall pekar nu till det samlade paketet.
B-027:s beslutade garantiinriktning behålls.

## Avgränsning och överlämning

Operatören har uttryckligen flyttat **bygga regler i systemet och koppla
källa → tolkning → regel → kod → test** till en senare session.
Ingen regelkod, DB-migration, datagenerering, agentimplementation eller
automatisk bank-/myndighetsanslutning har utförts här.

Byggsessionen ska använda paketet som ett helt kontrakt, framför allt
premie/pensions-/betalningsstatus, månadsordning, historiska garantidelar,
separat betalningsskuld, faktiska poolmedel och bolagsfinansiering.
Den ska pröva befintlig kod/datamodell mot hela paketet; dokumentationen
innebär inte att nuvarande tabeller redan stöder det.

Verkligt bolagstillstånd, professionell tariff-/beståndsvalidering, solvens,
bokslut, DORA-/GDPR-policies och faktisk hållbarhetsinformation är
verksamhetsprocesser i andra delprojekt. Det är inte öppna produktval
som lämnas till en språkmodell i byggsessionen.

## Flaggskeppsscenario

Dokumenterat första scenario: ny IBB-årsparameter → tolkning och berörd
premietrappa → ändringsbesked/konsekvens för bestånd → byggsessionens
kod-/testkoppling. Scenariot har en verklig återkommande regelkälla och
behöver ingen uppfunnen ändring av pensionsåldern.
