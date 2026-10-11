# PR-ITP1-004 – paus av påbörjad utbetalning
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Avtalsrätt till flexibilitet; egen månadshantering.
**Källor:** K-ITP-FLEX, K-IL-UTTAG-2026 i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-002](../../04_regulatoriskt/tolkningar/T-ITP1-002-uttag-och-paus.md).
**Villkor:** [§10 i v2.0](../försäkringsvillkor.md).

## Regel och grund

ITP-parternas flexibilitet och IL:s ramar, se T-002/T-003. Kunden får
upprepade gånger pausa en påbörjad **hel uttagsdel** minst en hel månad.
Begäran anger första pausmånad och bestämd återstartsmånad. En del av
månadsbeloppet kan inte pausas; separata uttagsdelar kan däremot pausas
oberoende. Ingen särskild avgift eller hälsoprövning.

Paus gäller från en månads början efter fristprövning. Inga månadsanspråk
uppkommer under pausen. Pausmånader förbrukar inte betalningsmånader,
men överlevnad under pausen ingår i omräkningsfaktorn. Kapitalet fortsätter
förvaltas med avgift/skatt och faktisk arvsvinst. Premieflöde påverkas
inte automatiskt. För tidsbegränsad plan flyttas kalenderns slut fram
med antal pausmånader; avtalat antal betalningsmånader ändras inte.

Ny plan ersätter uttryckligen föregående pausplan; överlapp förenas först
efter kundens bekräftelse. Önskan om paus utan återstart ger komplettering
med val av datum, inte en tyst obestämd paus. Efter den sista förbrukade
månadsrätten finns ingen pågående rätt att pausa.

## Kontrollfall

60 månader med 12 förbrukade, paus 3 månader: 48 rättigheter kvar,
slutmånad flyttad 3 månader. Bankfel är ingen paus. Avliden under paus
ger ingen dödsmånadsrätt på den delen och ingen återstart enligt PR-010.
