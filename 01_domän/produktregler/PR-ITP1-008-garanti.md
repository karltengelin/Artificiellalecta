# PR-ITP1-008 – intjänad pensionsgaranti

> **Version:** 0.1 | **Granskningsstatus:** Utkast | **Implementation:** Saknas
> **Ägare:** Operatören | **Datum:** 2026-10-11 | **Godkänd av/datum:** Ej godkänd
> **Ursprung:** Bolagsgaranti beslutad i B-027; regel och tariff kräver fortsatt granskning före införande.

## Källor, scope och giltighet

[T-ITP1-004](../../04_regulatoriskt/tolkningar/T-ITP1-004-garanti-och-aktuariell-grund.md)
skiljer avtal, föreskrifter och bolagsexempel. Den beräkningsmässiga
preciseringen finns i [aktuariell grund](../aktuariell_grund.md) §3–5.
Giltighetsdag och historiska försäkringar behöver separat godkännande.
Ingen retroaktiv garanti skapas för redan genererad premiehistorik här.

## Indata, regel och utfall

Indata: försäkring/förmån, faktiskt tillförd nettopremie och transaktions-ID,
värderingsdag, referensplan, tariff-ID/version samt tidigare garantidelar.

1. Endast mottagen, tillförd och inte redan garantibehandlad premie ger en
   ny garantidel. Fakturerad eller enbart beräknad premie ger ingen del.
2. Beslutat produktval enligt B-027 är 100 % av mottagen nettopremie som garantigrund,
   med 0 % nettoränta i garantitariffen. Det är ingen garanti om ett visst
   kontosaldo eller betalning till dödsboet.
3. Beräkna delens pensionsbelopp med godkänd tariff och referensplan.
   Spara grund, premie, plan och belopp oföränderligt tillsammans med
   regelversion. Samma transaktion får inte skapa dubbel garanti.
4. Ny grund gäller nya delar från beslutad giltighetsdag. Marknadsfall,
   avgiftsuttag eller en ny tariff får inte automatiskt reducera redan
   intjänade garantidelar för oförändrad plan.
5. Ändrad start, paus eller utbetalningstid ger en dokumenterad omräkning
   enligt §5 i grunden, med varje dels ursprungliga antaganden. Det
   garanterade månadsbeloppet kan då ändras; ursprungligt produkttekniskt
   värde för kvarvarande rätt skyddas enligt föreslagen metod.
6. Premiekorrigering/återtag ska kopplas till den korrigerade transaktionen
   och garantidelen. Undantaget får inte användas som allmän nedskrivning.
   Full rättelsemodell återstår före automatiska återtag.
7. Ingen automatisk garantiförstärkning eller nytt efterlevandeskydd skapas
   av denna regel. Dödsfallsbehandling och arvsvinster kräver egna regler.

Utfall: spårbar garantidel, planomräkning eller manuell utredning vid saknad
grund/underlag. Ingen preliminär tariff får utfärda ett garanterat kundbelopp.

## Acceptansfall och återstående arbete

| Fall | Utfall |
|---|---|
| Premie 1 000 kr fakturerad men inte mottagen | Ingen ny garantidel |
| Samma mottagna transaktion behandlas två gånger | En del, ingen dubblering |
| Kapital faller efter marknadsförlust, oförändrad plan | Garantidelens belopp ändras inte automatiskt |
| Ny framtida tariff har lägre garanti | Tidigare delar behåller sina grundversioner |
| Förlängning av utbetalning | Omräkning per del; inte ett löfte om samma månadsbelopp |
| Historisk premie utan tariffversion | Manuell utredning, ingen tyst tilldelning av dagens tariff |

Produktinriktningen är godkänd i B-027. Granska tariffkalibrering,
beräkningsmetod och övergångsregler innan kod byggs.
Garantin behöver finansiering och kan inte valideras enbart på kundkontot.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Första garantiregel |
