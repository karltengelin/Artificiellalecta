# PR-ITP1-005 – återupptagande efter paus
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Egen sammanhängande tillämpning av avtals-/skatteramen.
**Källor:** K-ITP-FLEX, K-IL-UTTAG-2026 i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-002](../../04_regulatoriskt/tolkningar/T-ITP1-002-uttag-och-paus.md).
**Villkor:** [§10 i v2.0](../försäkringsvillkor.md).

## Regel

Återstart sker vid början av den godkända återstartsmånaden om delen är
levande, pausad och har kvar rättigheter. Ingen ny ansökan krävs för
redan beslutat datum. Ändring av datum kräver samma frist/bekräftelse som
en annan ändring. Dödsfall eller avslut har företräde.

Behåll första faktiska start och förbrukade rättigheter. Återstående
period är avtalat totalt antal minus förbrukade månadsrätter, exklusive
paus. Ingen ny 60-månadersperiod krävs efter en paus. Livsvarig rätt har
ingen sista månad. Beräkna garanti och pension enligt PR-008/009 på
värderingen månaden före återstart, med PR-009:s beloppsgolv.

Bank- eller skattehinder stoppar verkställighet av betalning men är inte
ytterligare kundvald paus; månadsanspråk uppkommer enligt PR-026.
Efter ny paus måste nytt datum vara beslutat, inte härlett från en
utebliven överföring.

## Kontrollfall

12 av 60 förbrukade: återstart använder 48, inte 60. En ren paus i den
livsvariga planens första 60 rättigheter får enligt vår försiktiga
skattetillämpning inte sänka återstartens brutto under senaste belopp;
en verklig förlängning kan ge ny nivå enligt PR-007/009.
