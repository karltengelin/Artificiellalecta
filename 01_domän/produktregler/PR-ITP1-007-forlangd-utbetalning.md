# PR-ITP1-007 – förlängning efter första start
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Avtalsrätt och skatteram; egen planhantering.
**Källor:** K-ITP-FLEX, K-IL-UTTAG-2026 i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-003](../../04_regulatoriskt/tolkningar/T-ITP1-003-tidsbegransad-utbetalning.md).
**Villkor:** [§10 i v2.0](../försäkringsvillkor.md).

## Regel

En påbörjad tidsbegränsad del kan upprepade gånger få fler betalnings-
månader eller bli livsvarig, även efter fem utbetalningsår. Begäran måste
komma före ändringsmånad och innan alla rättigheter förbrukats.
Ingen ändringsavgift eller hälsoprövning.

Nytt totalt antal N_ny ska vara större än föregående N. Återstår
N_ny − redan förbrukade rättigheter; inte N_ny och inte minst 60 nya.
Paus ändrar kalenderns slut, inte N. Livsvarig del kan pausas men inte
göras tidsbegränsad i vårt erbjudande. Förkortning efter start avslås.

Garantidelarna omräknas värdebevarande på ursprunglig grund. Pension
räknas på samma kapital en gång. Tidsbegränsad gren följer planen enligt
IL 11 b. Övergång till livsvarig gren får första omräknade belopp som ny
nivå för återstående del av de första 60 månadsrätterna enligt vår
försiktiga tillämpning av IL 11. Enbart paus är ingen sådan förlängning.

## Kontrollfall

12 av 60 förbrukade, ändras till 120: 108 kvar. 59 av 60 förbrukade,
ändras till 61 totalt: 2 kvar. 60 av 60 redan förbrukade: avslås som
för sent; rättelse av handläggningsfel är en separat prövning i PR-019.
